# agent-state-driver

Reliable **state detection** and **programmatic driving** of interactive CLI AI agents.
Verified against the real CLI on **macOS** and **Windows**; on **Linux** the detector is
verified against a deterministic fixture only (see Honest coverage).

## The problem

An AI agent running in a terminal is, to any supervisor, a byte stream with no
machine-readable state. *Is it working? Idle? Waiting on a permission dialog? Waiting for
input? Dead?* Orchestrators answer this by guessing — `sleep 30`, or polling for a prompt
character that is on screen **even mid-generation**. Guesses don't compose: a fleet driven
by guesses fails silently, and silent failure is the expensive kind.

This repo answers it with evidence: a prior-art survey, a state model, a failure-mode
analysis, four working prototypes raced against an independent referee, and cross-platform
proof.

## Headline findings

**1. There is a vendor-written status file absent from every project we surveyed.**
Claude Code writes `~/.claude/sessions/<pid>.json` per interactive session:

```json
{"sessionId":"…","status":"waiting","waitingFor":"permission prompt","kind":"interactive"}
```

It is machine-readable, led the corresponding transcript record by 9–18 ms in the three
observations we made (single observations, raw records not retained), needs
no settings write and no spawn ownership — so it works on a session **a human started by
hand** — and it is **schema-identical on macOS and Windows** with one exception —
`procStart` is a Windows FILETIME integer string, not a ctime string, which is
exactly the field that breaks a naive parser. It appears in none of the projects
in our survey and in no vendor doc we read. It answers the hardest state directly:
`waitingFor: "permission prompt"` is what the OpenTelemetry `blocked_on_user` span
promised and then failed to deliver live: that span is exported only when the block
**ends**, so its observation lag is **unbounded** — measured at 37.9 s for a 32.9 s
block, of which 5.0 s was export.
→ [docs/discovery-session-sidecar.md](docs/discovery-session-sidecar.md)

**2. Hooks can be retrofitted onto a *running* session.**
Writing the project `.claude/settings.json` mid-session takes effect on the next dispatch —
proven causally in both directions (install → fires, remove → stops). The prior-art survey
had concluded that observing a human-launched session was screen-scraping only. Together
with the sidecar, that conclusion is dead.

**3. Denying a permission dialog emits no event at all.**
On macOS, re-probed with a 13-event set including `PermissionDenied`, `PostToolUseFailure`
and `StopFailure`: silent across 50 s and 145 s of observation. On Windows, observed with a
7-event set over an 11 s window — a weaker probe, and stated as such. A hook-only
observer latches "waiting for permission" **forever**. The transcript is equally blind:
zero appends for a full 79.6 s dialog window (observed live; raw record not retained). Only the sidecar and the screen see it.
This is the single strongest argument for fusing channels rather than picking the best one.

**4. No single channel wins.**

| Prototype | Channels | Score | Strength | Fatal gap |
|---|---|---|---|---|
| A `scrape-driver` | screen + process | 6/7 | needs zero vendor cooperation | version-volatile UI copy; unresolvable false-busy |
| B `hook-sentinel` | hooks + process | 6/7 | fastest turn boundaries (send→complete 3.4 s) | cannot clear the permission latch |
| C `transcript-watch` | transcript + sidecar + process | **7/7** | durable, no settings write | blind before the first prompt |
| D `fused` | sidecar + screen + process | 6/7 | reports conflicts instead of guessing | inherits screen's poll latency |

→ [docs/results/RACE-macos.md](docs/results/RACE-macos.md)

## What the building found that the reading did not

Every one of these was caught by running code against real sessions, and each is now a
rule in [PITFALLS.md](PITFALLS.md):

- **`esc to interrupt` is intermittent**, not absent and not reliable — present in 4 of 14
  captures during generation, gone entirely during tool calls. It was the recommended busy
  signal. A detector gated on it silently reads "idle" while the agent works.
- **Terminal-gone is not agent-dead.** The process outlives its terminal by 0.81–1.31 s,
  and indefinitely if detached. Two of the four prototypes reported `dead` with the process
  provably alive — the exact silent-misdetection class this project exists to eliminate.
  Records: [docs/results/s6b/](docs/results/s6b/) (`premature: true` with
  `pid_alive_before`/`after` both true, plus the post-fix passes).
- **Motion is necessary but not sufficient for busy.** A statusline with a live wall-clock
  moves the screen hash while idle. The fused driver caught this live as
  `conflict: sidecar=idle screen=busy` and refused to guess — record:
  [docs/results/conflict/](docs/results/conflict/).
- **Never match liveness over scrollback** — it holds spinner lines from earlier frames.
  Found by a mock fixture on its first run; a real session had masked it.

## Layout

```
docs/design/functional-design.md      state model, channel reliability, fusion rules, FMA
docs/discovery-session-sidecar.md     the undocumented vendor status channel
docs/results/                         race scores, portability, raw JSONL records
docs/.research/prior-art/             prior-art survey + synthesis (C1–C11, Q1–Q11)
docs/.research/empirical/             live probes that settled each open question
prototypes/common/SPEC.md             the driver contract all prototypes implement
prototypes/{scrape-driver,hook-sentinel,transcript-watch,fused}/
prototypes/harness/                   the independent referee
prototypes/mockagent/                 deterministic fixture + cross-platform check
```

## Try it

Zero credentials, zero API cost — drives a deterministic mock through the full state
machine and asserts the **shipped** detector (`patterns.classify_screen`) reads each state
correctly. Sabotaging `patterns.py` fails this check; that dependency is the point:

```bash
python3 prototypes/mockagent/portability_check.py        # 16/16 on macOS and Linux
```

Against a real session (spends API turns):

```bash
python3 prototypes/harness/run.py \
    --driver prototypes/fused/driver.py --scenarios S1,S2,S4,S6 --out results/
```

Requires `tmux` and Python 3.9+ on macOS/Linux. On Windows the hosting layer is a
~90-line node ConPTY host instead of tmux; every detection channel is unchanged
(→ [windows-leg.md](docs/.research/empirical/windows-leg.md)).

## Honest coverage

Verified against the real CLI: one build (2.1.222); states `starting`, `busy`, `idle`,
`waiting:permission`, `dead`; on macOS (full race) and Windows (all four channels).
Linux: detector + sidecar lifecycle via the fixture only.

**Not verified:**
- real-CLI-on-Linux — blocked on host access, not on effort
- **attached-posture driving** — the mechanism is proven (hook retrofit, Q1) and the
  enabler is proven (sidecar needs no spawn ownership), but **no driver implements an
  `attach` verb** and no scenario exercises it
- `conflict` as a *scored referee outcome* — the fused driver emitted it live
  (record committed) but no harness scenario asserts it
- `waiting:input` against a real question dialog; `presumed_hung` live; compaction
- HTTP hooks and `-p --output-format stream-json` (surveyed, never built)
- concurrent sessions; Windows persistence across logoff/reboot

Every number above traces to a record under `docs/results/` or a probe under
`docs/.research/empirical/`, except the two explicitly marked "raw record not retained".
Where two probes disagreed, a third experiment settled it and both originals are cited
(→ [q7-q8-reconciliation.md](docs/.research/empirical/q7-q8-reconciliation.md)).
This section was rewritten after an adversarial review of the repo's own claims.

## License

MIT
