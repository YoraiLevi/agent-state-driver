# PITFALLS

Hard-won traps. Read before working on this project. Each entry: trap → fix.

## Driving Claude Code through tmux

- **`❯` is not an idle signal.** The input prompt is rendered the whole time, including
  mid-generation. Gate readiness on the busy indicator (`esc to interrupt`) being ABSENT,
  plus N stable screen polls (spinner clears before the final render settles).
- **`send-keys` text and Enter must be separate calls.** `-l` for literal text; a combined
  call gets words interpreted as key names.
- **`capture-pane -p` returns the visible screen padded with blank rows.** Scroll back
  (`-S -N`) and strip blanks, or you read an empty answer.
- **Grey ghost text in the input box is an autocomplete hint, not input.** `C-u` cannot
  clear it; ignore it — it vanishes when real characters land.
- **Prose is not proof.** The model narrates plausibly whether or not a construct ran.
  Assert on machine signals (sentinel files, settings writes, log lines) with a causal
  control (remove the sentinel before the action).

## claude CLI flags (v2.1.222, verified live)

- **`--bare` severs subscription auth.** It reads ONLY `ANTHROPIC_API_KEY`/apiKeyHelper —
  never OAuth or keychain. On a claude.ai plan it launches and cannot authenticate.
  Use `--safe-mode` for config isolation with working auth.
- **Virgin `CLAUDE_CONFIG_DIR` breaks auth too** — credentials live inside the config dir;
  a throwaway dir boots to the theme picker then the login picker and blocks unattended runs.
- **`--permission-mode bypassPermissions` on a nested agent is a footgun** (and gets
  blocked by permission classifiers). Answer dialogs via send-keys instead; make bypass opt-in.

## Shell / cross-OS

- **macOS bash 3.2 + `set -u`: `"${arr[@]}"` on an empty array is a fatal error.**
  Guard with `${arr[@]+"${arr[@]}"}`.
- **zsh interactive prompts reject `#` comments** (`INTERACTIVE_COMMENTS` off by default).
  Worse, `VAR=x #comment` silently makes VAR a per-command env var, not a shell variable.
- **Bare slash commands get MSYS-path-mangled on Windows Git-Bash hosts** (`/config` →
  `C:/Program Files/Git/config`). Prefix `MSYS_NO_PATHCONV=1` or drive from PowerShell.

## Infrastructure

- **windesk/devbox reject user `m5air`;** devbox is Tailscale SSH. Don't loop blind
  username guesses over SSH — each attempt is slow; discover the user via tailscale CLI
  or host configs first.
- **Serial SSH probes with 4-5s timeouts stack up fast** — 8 probes blew a 90s budget.
  Probe in parallel with short timeouts, or discover before probing.
