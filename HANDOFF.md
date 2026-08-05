# HANDOFF

For the next session/agent picking this up cold. Read STATE.md first, then this, then PITFALLS.md.

## Mission (one paragraph)

Build and prove a reliable, cross-platform (macOS/Linux/Windows) system for detecting the
state of interactive CLI AI agents (working / idle / waiting-on-permission / waiting-on-input /
dead) and driving them programmatically. Deliverables: grounded prior-art research, functional
design + failure-mode analysis, multiple raced prototypes, honest documentation — all in
`YoraiLevi/agent-state-driver`. Autonomous task: do not stop for confirmation on prototyping;
prove things by running them; never endanger the user's Claude subscription (bounded loops,
no unattended spend amplification).

## Operating agreements

- GitHub issues are the progress ledger; tasks/worktrees for delegation; Opus/Sonnet subagents
  for parallel work (this session runs Fable — use cheaper models where the work is mechanical).
- Engineering skills to follow: quality-standards (evidence over claims, FMA, both paths),
  format-document-rules, reproducible-instructions, explain-with-trees for architecture.
- Docs lifecycle: docs/.research/ (active) → docs/ (settled) → .archive/ (retired).
- Heartbeat via ScheduleWakeup keeps the session alive; each beat: check task list,
  advance the lowest-numbered unblocked phase, reconcile STATE.md.

## Where things live

- Repo: https://github.com/YoraiLevi/agent-state-driver · local `~/source/fable/agent-state-driver`
- Prior research (Windows PTY middle layers): `docs/.research/gist-prior-research/`
- Named prior art to mine: `agentculture/cultureagent` (per-backend harness — claude/codex/
  copilot/acp state detection), `agentculture/culture` + `agentirc` (coordination layer above),
  OriNachum's blog `agentic-human`, claude-squad, VibeTunnel, Omnara, tmux MCP servers,
  pexpect/expect lineage, terminal-bench.
- Hooks channel to inventory: Claude Code hooks (Stop, Notification, PreToolUse, SessionStart/
  SessionEnd, statusline), transcript JSONL files under `~/.claude/projects/`, codex equivalents.
