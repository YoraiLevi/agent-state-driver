# STATE

Ground truth of the project. Updated every session that moves state.

## Current phase

Phase 5 (docs + publication) — in progress. Phases: 0 infra ✅ · 1 prior-art ✅ ·
2 design + FMA ✅ · 3 prototypes + harness ✅ · 4 cross-platform ✅ · 5 docs 🔄.

An adversarial review of the repo's own claims was run and its findings applied
(README overclaims corrected, missing evidence records committed, the portability check
rewired to exercise the shipped detector). See git log 2026-08-05.

Phase 3 results (docs/results/RACE-macos.md): four prototypes — A scrape, B hooks,
C transcript+sidecar, D fused — raced under an independent referee. C 7/7, A/B/D 6/7;
B's only failure is the real permission latch (denial emits no hook event).

Phase 4 so far (docs/results/PORTABILITY.md): mock-agent fixture + portability check
pass 15/15 on macOS (tmux 3.7b, py3.9.6) AND Debian/podman (tmux 3.3a, py3.11.2).
Windows leg COMPLETE — interactive claude.exe hosted via node-pty (ConPTY) +
@xterm/headless, all four channels verified live; the sidecar is schema-identical to macOS
apart from procStart (FILETIME). Real-claude-on-Linux remains UNVERIFIED (devbox blocked on
owner's Tailscale approval; credentials-into-container rejected as a workaround).

Phase 1 results: docs/.research/prior-art/ — 7 researcher files + SYNTHESIS.md (9-channel
taxonomy, 14-project comparison, conclusions C1-C11, open questions Q1-Q11). Q11 settled
first-hand: transcript layout is flat session JSONLs + per-session subagents/ sidecar trees,
on BOTH macOS and Windows (this machine's ~/.claude/projects contains windesk project dirs).

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

- Finish Phase 5: close issue #5, final read-through of every doc for claim/evidence match.
- Blocked on owner: Tailscale SSH approval for devbox, to verify real-claude-on-Linux.
- Unbuilt and declared: an `attach` verb (attached posture), HTTP hooks, stream-json mode.
