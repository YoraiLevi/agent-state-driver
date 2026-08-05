# PITFALLS

Hard-won traps. Read before working on this project. Each entry: trap → fix.

## Driving Claude Code through tmux

- **`❯` is not an idle signal.** The input prompt is rendered the whole time, including
  mid-generation.
- **`esc to interrupt` is not a reliable busy signal either** (superseded 2026-08-05 —
  see docs/.research/empirical/q7-q8-reconciliation.md). It is intermittent: absent during
  foreground tool calls (replaced by the ctrl+b background hint), absent 0/75 samples in
  some session configurations, present only intermittently even during plain generation.
  A gate on it silently reads "idle" for whole session classes.
  **The correct composite gate (verified on 2.1.222):**
  busy = spinner-verb line `^[✢✳✶✽✻·*]\s+\w+…\s*\(\d+s` OR tool line `⎿\s+Running…\s*\(\d+s`;
  idle = busy-regex absent AND ≥3 consecutive byte-identical ANSI-stripped captures
  (busy screens re-render every ≤1 s via the elapsed-seconds tickers; idle screens are
  byte-stable for tens of seconds). Exclude past-tense forms (`\w+ed for \d+s`).
- **`send-keys` text and Enter must be separate calls.** `-l` for literal text; a combined
  call gets words interpreted as key names.
- **`capture-pane -p` returns the visible screen padded with blank rows.** Scroll back
  (`-S -N`) and strip blanks, or you read an empty answer.
- **Grey ghost text in the input box is an autocomplete hint, not input.** `C-u` cannot
  clear it; ignore it — it vanishes when real characters land.
- **`hasTrustDialogAccepted` in a project's `.claude/settings.json` does NOT suppress the
  folder-trust dialog** (verified 2.1.222, Q7 probe). The launch sequence must handle the
  trust dialog unconditionally (wait for it, `Enter` accepts).
- **Foreground `sleep` is blocked for nested sessions** by this harness's inherited Bash
  guard. Timing probes must use `ping -c N -i 1 127.0.0.1 > /dev/null` as the silent workload.
- **`claude config get` can hang indefinitely** (observed: `preferredNotifChannel`, 120 s+,
  killed). Wrap any `claude config` invocation in a timeout.
- **tmux `capture-pane` cannot see transient OSC/BEL sequences** — it replays stored cells,
  not control strings. For byte-level evidence (BEL, OSC 9/777, alt-screen enters), run the
  TUI under `script -q raw.log …` and grep the raw log; the raw log is the load-bearing
  evidence, not the capture.
- **Prose is not proof.** The model narrates plausibly whether or not a construct ran.
  Assert on machine signals (sentinel files, settings writes, log lines) with a causal
  control (remove the sentinel before the action).

## Hook channel (v2.1.222, verified live by prototype B)

- **Denying a permission dialog emits NO hook event at all.** Verified twice with an
  extended 13-event set installed (incl. `PermissionDenied`, `PostToolUseFailure`,
  `StopFailure`): after pressing "No" the tool is interrupted, the TUI returns to an empty
  prompt, and the event log stays silent for 50 s and 145 s of observation. **A hook-only
  observer latches `waiting:permission` forever.** Any hook-based detector MUST fuse a
  screen or transcript channel to close this hole, and must surface the unresolved latch
  as a conflict rather than guessing.
- **`Notification` lags `PermissionRequest` by 5-6 s** — corroborating signal only, never
  the primary one. It carries a structured `notification_type` (e.g. `"permission_prompt"`)
  alongside the prose `message`: classify on the type, which is far less copy-volatile.
- **No hook fires on SIGKILL** (C5 confirmed live) — process liveness is mandatory.
- **PID discovery substring trap.** claude spawns `/bin/zsh -c source ~/.claude/shell-snapshots/…`
  children whose argv contains "claude". A substring match latches a transient child; when
  it exits, the process channel reports `dead` for a live agent. Anchor on argv[0] basename
  and take the tmux pane's direct child.
- **Hook-log appends must stay under PIPE_BUF to be atomic.** Cap the payload, strip
  newlines, and use TSV framing — JSON-wrapping-JSON loses the whole event on truncation.

## Windows hosting (verified live on windesk, 2026-08-05)

- **Hook commands cannot use `>>` redirection on Windows.** The redirect is eaten by an
  outer shell and `cmd` then runs interactively, capturing the hook's stdin payload
  instead of writing a sentinel. Hook commands must be script invocations that read stdin
  (`node hook.js`, `pwsh -File hook.ps1`).
- **`Start-Process -RedirectStandardOutput/-RedirectStandardError` silently kills a
  ConPTY spawn.** Do not redirect std handles when hosting a PTY.
- **A process launched from an SSH command dies when that SSH session ends.** To detach,
  register a per-user scheduled task (`schtasks`) — verified surviving into a later,
  separate SSH session.
- **fnm's `node` is not on any non-interactive PATH** — use the absolute path.
- **`procStart` in the sidecar is a Windows FILETIME integer string**, not a ctime string
  like macOS. Any parser must handle both.

## Screen capture region (found by the mock-agent fixture, 2026-08-05)

- **Never match liveness over scrollback.** `capture-pane -S -N` returns history, which
  contains spinner lines from earlier frames — so a busy regex matches on a session that
  has been idle for minutes. Capture the **visible pane only** (`capture-pane -p`, no
  `-S`) for state decisions, and anchor pattern matching to the last ~15 non-blank lines
  regardless. Scrollback is for debugging output, never for "what is happening now".
  (Same class as `awslabs/cli-agent-orchestrator#182`. A real session masks this because
  in-place redraw keeps history clean — only a fixture that repaints via `\x1b[2J`
  exposes it, which is itself the lesson: test the detector against adversarial rendering.)

## Liveness (silent-misdetection class — found by harness S6b, 2026-08-05)

- **Terminal-gone is NOT agent-dead.** `tmux has-session` returning false means the
  terminal died; the claude process outlives it by ~1 s (SIGHUP propagation) and
  indefinitely if detached or wedged. Two of the four prototypes shipped this defect and
  reported `dead` with the process provably alive (verified: pid alive before AND after
  the claim). Gate liveness on the agent PID.
- **Cache the PID at launch.** The sidecar that names it is deleted on clean shutdown, so
  a lookup at death time fails exactly when it is needed — and the driver silently falls
  back to the terminal proxy it was trying to avoid.
- **A liveness test must be able to fail.** Racing the ~1 s SIGHUP window gave two
  consecutive INCONCLUSIVE runs. `SIGSTOP` the agent first: a stopped process cannot act
  on its terminal's death, making the window deterministic — and it models the real
  detached/wedged case. Never score an inconclusive run as a pass.

## Session sidecar `~/.claude/sessions/<pid>.json` (see docs/discovery-session-sidecar.md)

- **Edge-triggered, not a heartbeat.** `statusUpdatedAt` does not advance while a state
  persists (24 s of a pending dialog, unchanged; a live busy session showed a 23-min-old
  timestamp). Staleness proves nothing — never build a watchdog on it.
- **Death handling differs by kind**: clean exit **deletes** the file; `SIGKILL` leaves it
  with a **stale status**. Always gate reads on `kill -0 <pid>`.
- **Look it up by `sessionId`, not PID.** When claude is launched as the tmux pane command
  it *is* the pane process, so `pgrep -P <pane_pid>` returns nothing (this cost a probe run).
- **Transcript JSONL does not exist until the first prompt** — a pure transcript watcher
  cannot observe launch→first-idle at all; the sidecar covers that window.

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
