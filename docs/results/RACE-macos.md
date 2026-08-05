# Comparative race — macOS, 2026-08-05

claude 2.1.222 · macOS 25.5.0 · tmux 3.7b · Python 3.9.6 · scenarios S1,S2,S4,S6.
Raw per-run records: `*.results.jsonl` in this directory.

Ground truth is the harness's own observation, never the driver's report:
death is scored from **PID exit** (not from the kill command returning), and busy
is derived from the harness's own independent capture — with `ok: null` when a
window closed before the driver could be asked. Inconclusive is never a pass.

## Scores

| Prototype | Channels | Score | Failure |
|---|---|---|---|
| **C transcript-watch** | transcript JSONL + sidecar + process | **7/7** | — |
| **D fused** | sidecar + screen + process | 6/7 | 1 inconclusive (turn ended mid-call) |
| **A scrape-driver** | screen + process | 6/7 | 1 inconclusive (turn ended mid-call) |
| **B hook-sentinel** | hooks + process | 6/7 | **S4 real failure**: cannot clear the permission latch — denial emits no hook event |

## Latency (seconds)

| Transition | A scrape | B hooks | C transcript | D fused |
|---|---|---|---|---|
| launch → first idle | 17.4 | **4.0** | 13.0 | 13.3 |
| send → turn complete | 11.7 | **3.4** | 5.5 | 9.6 |
| send → permission dialog | 3.1 | 7.5 | **2.1** | **2.1** |
| true death → detected | 0.04 | 0.04 | 0.04 | 0.03 |

Measured incidentally and repeatedly: **terminal death → process death = 0.81-1.31 s**.
That gap is the silent-misdetection window that scenario S6b exists to police.

## Read as

- **No single channel wins.** B is fastest on turn boundaries (hook dispatch ~0.1 s) but
  structurally cannot clear a permission latch. C scores highest here but is blind to the
  entire pre-first-prompt window and to a pending dialog by transcript alone — it passes
  because it also reads the sidecar. A is the only one needing no vendor cooperation at
  all, and pays for it in latency and in a false-busy it cannot resolve alone.
- **The fused driver's value is not its score, it is what it refuses to do.** It caught a
  live disagreement (`sidecar=idle screen=busy`) caused by a statusline wall-clock moving
  the screen hash while idle, and reported `conflict` instead of inventing a state. That
  disagreement is invisible to every single-channel prototype.
- **B's S4 failure is correct behavior scored as a failure**, and both facts should stand:
  the permission latch is unclearable from hooks alone, and B reports `conflict` rather
  than guessing.

## Declared coverage

Verified: S1 launch→idle, S2 trivial turn, S4 permission dialog + denial (causally, via
file absence), S6/S6b death including the premature-death probe. One build (2.1.222), one
OS (macOS), one host. NOT covered here: S5 question dialog, S7 long-idle watchdog,
compaction, `presumed_hung` live, attached posture, Linux, Windows.
