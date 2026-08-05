# Prototype contract — driver interface and scenario suite

All prototypes implement this contract so the harness can race them on identical scenarios.
Grounded in docs/design/functional-design.md sections 2-4 (state model, channels, fusion).

## States

`starting · busy · idle · waiting:permission · waiting:input · presumed_hung · dead`

Attributes accompany states, not replace them: `idle` may carry
`{"background_work": true}`; every report carries evidence.

## Interface (language-neutral; v1 implementations are Python 3 stdlib-only)

Each prototype is an executable `driver.py` with subcommands, communicating JSON on stdout
(one object per line where streaming). Exit code 0 = command succeeded; nonzero = driver
error (never used to encode agent state).

```
driver.py launch --workdir D [--session-name N]     -> {"id": ..., "state": "starting"}
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
```

Rules binding all implementations (from FMA):

1. `state` must never decide from a single capture (C2): busy/idle requires the composite
   gate — busy-regex OR hash-motion ⇒ busy; regex-absent AND ≥3 stable 1 s captures ⇒ idle.
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
