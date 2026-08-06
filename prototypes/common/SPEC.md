# Prototype contract — driver interface and scenario suite

All prototypes implement this contract so the harness can race them on identical scenarios.
Grounded in docs/design/functional-design.md sections 2-4 (state model, channels, fusion).

## States

`starting · busy · idle · waiting:permission · waiting:input · presumed_hung · dead`
plus the meta-state `conflict`.

Attributes accompany states, not replace them: `idle` may carry
`{"background_work": true}`; every report carries evidence.

**`conflict` is a first-class reported state** (ambiguity raised by prototype B, resolved
2026-08-05). It means: channels disagree, or a channel latched a state it cannot clear.
It is deliberately NOT one of the seven agent states — it describes the *observer*, not the
agent — but it must be reportable in the `state` field so a consumer cannot mistake an
unresolved observation for a resolved one. `attrs.conflict: true` accompanies it, with
`attrs.reason` naming the mechanism (e.g. `permission_latch_unresolved_by_event_channel`).
Silently picking a winner is forbidden.

## Interface (language-neutral; v1 implementations are Python 3 stdlib-only)

Each prototype is an executable `driver.py` with subcommands, communicating JSON on stdout
(one object per line where streaming). Exit code 0 = command succeeded; nonzero = driver
error (never used to encode agent state).

```
driver.py launch --workdir D [--session-name N]     -> {"id": ..., "state": <state at return>,
                                                        "settled": <optional post-startup state>}
driver.py state  --id I                             -> {"state": S, "attrs": {...},
                                                        "evidence": [{"channel": C,
                                                          "signal": ..., "at": ts}]}
driver.py wait   --id I --until S[,S2...] --timeout T   -> final state report (exit 0)
                                                           or {"error":"timeout", last} (exit 3)
driver.py send   --id I --text "..."                -> sends text + Enter; refuses (exit 4)
                                                       unless state is idle, unless --force
driver.py answer --id I --option N                  -> answers a waiting:* dialog
driver.py screen --id I [--lines N]                 -> current capture (debug)
driver.py kill   --id I                             -> terminate + cleanup

driver.py list                                      -> {"sessions":[{sessionId,pid,cwd,
                                                        status,waitingFor,alive}]}
driver.py attach --session-id S [--socket SOCK]     -> adopt a session this process did
                                                       NOT launch
```

Rules binding all implementations (from FMA):

1. `state` must never decide busy/idle from a single **screen** capture (C2): the composite
   gate is busy-regex OR hash-motion ⇒ busy; regex-absent AND ≥3 stable 1 s captures ⇒ idle.
   *Clarified 2026-08-05 (raised by prototype B):* this binds the **screen** channel only.
   For the event channel a single hook line IS proof of its event — but a state built on it
   must still fuse process liveness into every report, because no hook fires on SIGKILL.
   The invariant behind the rule: no state may rest on one observation that a single missed
   or stale render can invert.
2. Every report carries `evidence`. Channel disagreement ⇒ `"conflict": true` in attrs,
   never silent resolution.
3. `dead` from the process channel only. `presumed_hung` computed observer-side:
   busy-asserted AND no evidence refresh > `stale_after` (default 120 s; must be > poll
   interval; config-asserted at startup).
4. Launch handles the trust dialog unconditionally (Q7).
5. No `--dangerously-skip-permissions`, no user-global config writes, no binary patching.
6. Dialog literals live in `patterns.py` as versioned SETS with a self-test hook: a session
   that provably showed a dialog (harness ground truth) with zero literal matches must
   fail loudly, not return unknown.
7. `launch`'s `state` field is whatever state holds **when it returns**; a driver that waits
   out startup SHOULD also return `settled`. Consumers (and the harness) must never compare
   `launch.state` across prototypes — call `state`/`wait` for a comparable reading.
   *(Divergence found between A and B, resolved 2026-08-05.)*
8. `attach` must declare its own degradation. Without a reachable terminal the sidecar
   and process channels still give busy/idle/waiting/dead, but dialog option rows are
   unreadable — so dialogs can be DETECTED and never ANSWERED. Report
   `screen_available: false` and say what is impossible; do not silently expose an
   `answer` verb that cannot work.
9. A driver must never resolve a channel disagreement or an unclearable latch by picking a
   winner. Report `conflict` with `attrs.reason`. Guessing is the failure this project exists
   to eliminate.

## Scenario suite (harness contract)

Each scenario yields ground-truth timestamps the harness knows by construction; a prototype
is scored on (a) correct state sequence, (b) detection latency vs ground truth, (c) zero
silent misdetections (wrong state with confident evidence).

| # | Scenario | Ground truth source |
|---|---|---|
| S1 | launch → first idle | trust dialog answered by harness; idle = prompt accepting |
| S2 | trivial turn ("Reply with exactly: pong") | send time; completion via transcript turn_duration record |
| S3 | silent foreground tool (ping -c 30 -i 1 127.0.0.1 >/dev/null; pre-allowed) | tool span from transcript PostToolUse/durations |
| S4 | permission dialog (un-allowed touch command), then denied by harness | dialog literal appearance (harness's own capture) + answer time |
| S5 | question dialog (AskUserQuestion-style prompt) | as S4 |
| S6 | kill -9 mid-turn | kill timestamp |
| S7 | idle 90 s (no false busy; watchdog must NOT fire) | wall clock |

Runs are recorded as JSONL: `{scenario, prototype, event, state, t_detect, t_truth, delta_ms}`.
The harness must run on a stranger's machine: no hardcoded paths, claude binary resolved
from PATH, all state under a --workdir.
