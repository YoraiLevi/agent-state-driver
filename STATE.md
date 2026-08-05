# STATE

Ground truth of the project. Updated every session that moves state.

## Current phase

Phase 0 (infrastructure) — in progress. Phases: 0 infra · 1 prior-art research ·
2 functional design + FMA · 3 prototypes · 4 cross-platform proof · 5 docs + publication.

## Decisions locked

- Umbrella repo `YoraiLevi/agent-state-driver`, working dir `~/source/fable/agent-state-driver`.
- Multiple prototypes under one repo, compared by a shared scenario harness — not one blessed design.
- State model must cover at least: working / idle / waiting-on-permission / waiting-on-input / dead.
- Detection channels to evaluate: screen-scrape, harness hooks, transcript (JSONL) watching, process tree.
- Cross-platform target: macOS (local), Linux (podman), Windows (windesk over Tailscale, or documented best-effort).
- Subscription safety: bounded workflows, no unbounded agent loops, no bypassPermissions on spend-capable sessions.

## Environment facts (verified 2026-08-05)

- macOS host: Darwin 25.5.0, tmux 3.7b, podman 6.0.2, gh authenticated as YoraiLevi.
- claude CLI 2.1.222. `--safe-mode` keeps auth working; virgin `CLAUDE_CONFIG_DIR` breaks auth (hits login picker) — verified live.
- Readiness ground truth for Claude Code TUI: `❯` prompt is rendered even mid-generation; the true busy
  signal is `esc to interrupt` presence; a settle count is needed because the spinner clears before final render.
- **windesk: WORKING** — `devic@windesk` (pubkey SSH). Windows 11 (NT 10.0.26200), pwsh 7.6.3 default
  shell, git, Docker Desktop, podman, WSL, node, claude.exe 2.1.222. NO tmux. Beware: `claude` is an
  `Invoke-Claude` profile wrapper (auto-mode, skip-permissions, strict-mcp, cd-to-claude-tmp, resets
  mouse-tracking escapes) — drive `claude.exe` directly. `%TEMP%\claude-tmp` holds prior experiments
  incl. altscreen_1049.txt (alt-screen buffer notes) — mine in Phase 1/2.
- devbox: `yorai@devbox` is the right user but Tailscale SSH hangs awaiting (likely) browser approval —
  owner action needed; Linux falls back to local podman meanwhile.

## Prior research in hand

- `docs/.research/gist-prior-research/` — 3,164 lines on persistent drivable shell sessions on native
  Windows 11: ConPTY session daemons, PTY-as-a-service, agent-drivable control surfaces + sources manifest.

## Next

- Phase 1 research workflow (parallel subagents): cultureagent deep-read, broad prior-art sweep,
  hooks inventory, gist digestion, synthesis into detection-channel taxonomy.
