# Cross-platform portability — Phase 4

## What this proves, and what it does not

The portability check drives `prototypes/mockagent/mock_claude.py` — a deterministic
stand-in that replays the exact rendered shapes recorded from live 2.1.222 sessions —
and asserts each detector signal reads correctly.

**Proves:** the shipped detector (`patterns.classify_screen`, imported directly by the
check — sabotaging it fails the run) and the sidecar lifecycle behave identically across
OS, tmux version, and Python version.
> **SUPERSEDED (2026-08-06):** the Linux claim below was closed by a real-CLI run on
> WSL2 Ubuntu 26.04 — see `docs/results/linux/`. The paragraph is kept for provenance.

**Does not prove:** real-CLI behavior on the target OS. Real-claude-on-**Linux** is declared
UNVERIFIED (blocked: devbox requires a Tailscale SSH browser approval only the owner can
grant; putting the owner's OAuth credentials into a container was rejected as a way around it).

Real-CLI behavior on **Windows** IS verified separately and directly — an interactive
`claude.exe` was hosted, driven and observed on all four channels on windesk. That leg did
not need the mock.

## Results

| Platform | tmux | Python | Result |
|---|---|---|---|
| macOS 25.5.0 (arm64) | 3.7b | 3.9.6 | **16/16** |
| Debian bookworm (podman, arm64) | 3.3a | 3.11.2 | **16/16** (re-run after the detector was wired in) |
| Windows 11 build 26200 | n/a (node ConPTY host) | node 26.3.0 | **all 4 channels verified live** — see `docs/.research/empirical/windows-leg.md` |

Signals verified identically on both: trust dialog copy, idle prompt, busy spinner shape,
the past-tense completion form NOT matching the busy predicate, the tool-run line, the
permission dialog copy, and the full sidecar lifecycle (created → idle → busy → waiting +
waitingFor → idle → deleted on clean exit).

## The defect this check found on its first run

`completion is NOT busy-shaped` **failed on macOS**: the busy regex matched a *stale
spinner line in tmux scrollback* from a frame seconds earlier. The drivers were capturing
`-S -60`, i.e. matching liveness over history — violating the design's own C3 ("anchor to
the bottom, never the whole buffer") and reproducing `awslabs/cli-agent-orchestrator#182`.

Fixes: liveness is now read from the **visible pane only** (`capture-pane -p`, no `-S`),
`patterns.classify_screen` anchors to `TAIL_LINES` internally regardless of what it is
handed, and the harness's independent oracle anchors the same way. The mock was also
corrected to repaint in place (cursor-home + erase-to-EOL) rather than `\x1b[2J`, which
was scrolling a frame per second into history — not how the real TUI behaves.

That is the value of a deterministic fixture: a real session masked this defect because
its in-place redraw kept scrollback clean; the mock surfaced it in one run, for free.

## Reproducing

```
python3 prototypes/mockagent/portability_check.py                  # host
podman build -t asd-portcheck -f prototypes/mockagent/Containerfile prototypes/mockagent
podman run --rm -v "$PWD:/work:ro,Z" asd-portcheck \
    python3 /work/prototypes/mockagent/portability_check.py        # linux
```
No credentials, no API cost, exit 0 on success.
