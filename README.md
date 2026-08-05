# agent-state-driver

Reliable **state detection** and **programmatic driving** of interactive CLI AI agents
(Claude Code, Codex, and friends) — cross-platform (macOS / Linux / Windows).

## The problem

An interactive AI agent in a terminal is a byte stream with no machine-readable state.
"Is it working? Idle? Waiting on a permission dialog? Waiting on a shell prompt? Dead?"
Every orchestrator answers this by guessing — usually `sleep N` or polling for a prompt
character that is on screen even mid-generation. Guesses don't compose: a fleet of agents
driven by guesses fails silently.

This repo builds the answer properly:

1. **Prior-art research** — how existing projects (cultureagent, claude-squad, tmux drivers,
   pexpect lineage, hook systems) detect agent state, and where each approach lies.
2. **Functional design** — an explicit state model, detection channels compared by
   failure mode, one interface over tmux (Unix) and ConPTY middle layers (Windows).
3. **Prototypes** — multiple, under this one umbrella, raced against each other on
   identical scenarios: screen-scrape driver, hooks-based sentinel, transcript watcher.
4. **Failure-mode analysis** — organized by mechanism (silent failure, misdetection,
   false success), with declared coverage.

## Status

Early. See [STATE.md](STATE.md) for current ground truth, [docs/](docs/) for research
and design as they land, and the issue tracker for live progress.

## Layout

```
docs/                     settled facts, design docs
docs/.research/           active research artifacts (promoted to docs/ when settled)
  gist-prior-research/    prior research: drivable shell sessions on Windows (ConPTY
                          middle layers, PTY-as-a-service) — the Windows foundation
prototypes/               one directory per prototype, raced by a shared harness
```
