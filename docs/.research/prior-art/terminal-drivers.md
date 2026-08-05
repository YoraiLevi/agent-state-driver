# Prior art: terminal-session drivers and remote-control layers for AI agents

Scope: how existing tools detect turn-completion / busy-idle / permission-wait state of an
interactive CLI AI agent, and how they drive it. Covers VibeTunnel, Omnara, happy-cli
(Happy Coder), tmux MCP servers, and wezterm/kitty remote-control APIs as drivable surfaces.

## Verdict

- **Three fundamentally different mechanism classes exist, ranked by reliability**: (1) SDK/API
  wrapping (happy-cli — subscribes to structured message/hook events, no screen state at all),
  (2) hook/notification channel tapping (VibeTunnel's Claude-specific bell hack, Claude Code's
  own hook system), (3) terminal screen-scraping with regex/sentinel heuristics (tmux-mcp,
  wezterm/kitty cli, VibeTunnel's generic-shell prompt detector). Class 1 is exact but requires
  the agent expose an SDK; class 3 is universal but fundamentally heuristic and admits false
  positives/negatives — this maps directly onto our own design's three candidate approaches
  (prototypes A/B/C in HANDOFF.md).
- **VibeTunnel does not solve "is Claude done" generically — it special-cases Claude by
  patching the binary and forcing it onto the terminal-bell notification channel.** It runs
  `claude config set --global preferredNotifChannel terminal_bell` so Claude emits ASCII BEL
  (``) on turn-completion, then listens for that bell server-side
  (`web/src/server/services/bell-event-handler.ts`). This is a real, working "Claude finished
  its turn" signal, but it depends on an internal Claude Code config knob that could change
  or be removed, and by VibeTunnel's own admission needed a workaround when it stopped firing.
- **VibeTunnel also patches the Claude CLI binary in-place to disable an anti-debugging
  check** (`web/src/server/utils/claude-patcher.ts`) — it detects `if(X())process.exit(1)`
  patterns tied to a function they call `PF5()` and neuters them. This is the single most
  load-bearing and fragile mechanism found: it string-matches minified JS in the Claude binary
  and rewrites it on disk (with backup/restore). It is Claude-Code-version-coupled and would
  break silently on any obfuscation change — a pattern **we must avoid**: no binary patching.
- **No prior-art tool has a genuine "idle vs. waiting-on-permission vs. waiting-on-input"
  taxonomy at the terminal-scraping layer.** VibeTunnel's own session model only has
  `'starting' | 'running' | 'exited'` (`web/src/shared/types.ts:54`); "activity" is a derived,
  timestamp-based boolean (5s silence timeout in `activity-status.ts`), not a state machine.
  Anything richer than busy/idle, at the terminal layer, is bespoke to us.
- **happy-cli is the strongest example of doing this right by not doing it at the terminal
  layer at all.** It runs the Claude Agent SDK in-process, intercepts tool calls via a
  `canCallTool` callback (`permissionHandler.ts`), and gets permission-wait state as a typed
  event (`onPermissionRequestCallback`) rather than inferring it from pixels/text. This is only
  possible because Claude Code (and Codex, which happy-cli also drives) exposes an SDK/hook
  surface — it is not applicable to arbitrary opaque CLI TUIs, which is presumably why our
  project also needs the terminal-scraping fallback.
- **tmux-mcp and wezterm/kitty CLIs are pure remote-control surfaces with zero AI-state
  awareness** — they give you `capture-pane`/`get-text` and a sentinel-marker completion
  hack for plain shell commands (`TMUX_MCP_START` / `TMUX_MCP_DONE_<uuid>` echoed and grepped
  for). None of them distinguish "process alive but idle" from "process waiting on stdin" from
  "process dead" — that inference is left entirely to whoever calls them. kitty's
  `state:needs_attention` window flag (driven by bell/OSC-777) and wezterm's
  `pane:is_alt_screen_active()` are the only two built-in booleans in this whole survey that
  come from the terminal emulator itself rather than from scraping text, and both are cheap,
  cross-platform-relevant signals worth reusing.
- **Windows support is thin across the board.** VibeTunnel's npm package explicitly does not
  support Windows yet (README, tracked in amantus-ai/vibetunnel#252); tmux itself doesn't run
  natively on Windows (WSL/Cygwin only); kitty and wezterm both run natively on Windows and
  their CLI/remote-control surfaces are the most credible cross-platform building blocks found
  here — worth prioritizing if we lean on a terminal-emulator-level API rather than tmux.

## Mechanisms found

### VibeTunnel (amantus-ai/vibetunnel, 4,625 stars, active)

"Turn any browser into your terminal & command your agents on the go." Node/Bun server + Mac
menu-bar app + iOS app; forwards a local PTY session to a browser/mobile client.

**What it can observe / exact mechanism:**
- **Generic shell activity (busy/idle only, no waiting-on-permission distinction):**
  `computeActivityStatus()` in `web/src/server/pty/activity-status.ts:29` — `isActive` is
  `true` iff `status === 'running'` AND `now - max(lastOutputTimestamp, lastInputTimestamp,
  lastModified, startedAt) <= 5000ms` (`DEFAULT_ACTIVITY_IDLE_TIMEOUT_MS`). Pure silence-timer
  heuristic: any 5s pause in PTY output reads as idle, regardless of whether the process is
  actually waiting on a decision or just thinking silently.
- **Shell prompt detection (for title-bar injection, not agent state):**
  `web/src/server/utils/prompt-patterns.ts` — a single pre-compiled regex
  (`UNIFIED_PROMPT_END_REGEX`) matching common shell prompt terminators (`$ > # % ❯ ➜`) after
  stripping ANSI, plus per-shell patterns (bash/zsh/fish/powershell/python). Used only to know
  when it's safe to inject an OSC-2 terminal-title escape sequence, not exposed as agent state.
- **Claude-specific "your turn" signal — the interesting one:** VibeTunnel forces Claude Code
  to emit a terminal BEL (``) on turn completion by setting
  `claude config set --global preferredNotifChannel terminal_bell` (documented explicitly in
  `docs/push-notification.md` under Troubleshooting, framed as a fix for when Claude's built-in
  "Your Turn" notification silently stops firing). The PTY layer detects ASCII 7 in the output
  stream and routes it through `BellEventHandler.processBellEvent()`
  (`web/src/server/services/bell-event-handler.ts:79`), which fires a push notification
  ("🔔 Terminal Activity … triggered a bell") without any further filtering or correlation
  ("Ultra-simple bell event handler" per the file's own docstring — a prior, more complex
  correlation/dedup version was apparently ripped out).
- **Binary patching to survive Claude's anti-debugging check:**
  `web/src/server/utils/claude-patcher.ts` reads the resolved Claude CLI binary, verifies it's
  really Claude (shebang has `node` + file contains `Anthropic PBC`), then regex-replaces
  `if(<fn>())process.exit(1);` (multiple spacing/exit-code variants, referencing an internal
  function they nickname `PF5()`) with `if(false)process.exit(1);`, writing the patched binary
  back over the original (keeping a temp backup, restored via `process.on('exit'/'SIGINT'/
  'SIGTERM')` handlers). This exists because Claude Code apparently detects when its stdout is
  being piped/inspected non-interactively and self-terminates; VibeTunnel needs to intercept
  that stream to add its bell-forcing/title-injection behavior, so it defeats the check. This
  is inherently version-coupled reverse-engineering of Claude Code internals, not a stable API.
- **Command-duration and exit-code notifications (generic, not Claude-specific):** per
  `docs/push-notification.md` — "Your Turn" style notifications also fire for any shell command
  running >3s (tracked by a Swift-side `SessionMonitor`) or exiting non-zero. Native mac
  implementation is `mac/VibeTunnel/Core/Services/NotificationService.swift` (not fetched in
  full — file listing only) using `UserNotifications` framework over a `/ws` WebSocket
  subscription to server-side `ServerEvent` frames (`sessionStart`, `sessionExit`,
  `commandFinished`, `commandError`, `bell`).

**States distinguished:** `starting | running | exited` (session-level, `shared/types.ts:54`)
crossed with a derived `isActive` boolean. No permission-wait or input-wait state exists as a
first-class concept anywhere in the codebase explored.

**Where it lies / fails:**
- Silence-timer idle detection (5s) will misclassify a model that is "thinking" (no tool output,
  no prompt) for >5s as idle, and will misclassify a fast permission dialog that renders
  instantly as still "active" until the 5s window elapses — no distinct waiting-on-permission
  detection at all at the terminal layer.
- The Claude bell mechanism depends on an internal config flag
  (`preferredNotifChannel: terminal_bell`) whose own docs describe it as a fallback needed
  because the primary in-app notification broke — i.e., even VibeTunnel's authors have observed
  this channel to be unreliable across Claude Code versions.
- Binary patching is the highest-risk technique in this survey: it string-matches minified/
  obfuscated JS inside the shipped Claude binary. Any change to Claude Code's build/obfuscation
  breaks it silently (the code already has 3 regex variants to survive minor formatting drift,
  which is itself evidence of prior breakage). **We should not adopt this pattern.**
- No Windows support in the (cross-platform) npm distribution as of the current README
  (tracked upstream at amantus-ai/vibetunnel#252); native app is Mac-only. Linux is supported.

### happy-cli / Happy Coder (slopus/happy-cli, 558 stars; slopus/happy-server, 367 stars)

"Happy Coder CLI to connect your local Claude Code to mobile device." Runs the **Claude Agent
SDK directly in-process** (and also drives Codex) rather than spawning/scraping a Claude Code
terminal session — architecturally closest to "class 1" (SDK wrapping) in our verdict.

**What it can observe / exact mechanism:**
- **Permission-wait state, exactly, as a typed SDK callback — no scraping at all.**
  `src/claude/utils/permissionHandler.ts` implements `handleToolCall` as the SDK's
  `canCallTool(toolName, input, mode, {signal})` hook. When a tool call isn't pre-allowed
  (checked against `allowedTools`/`allowedBashLiterals`/`allowedBashPrefixes` sets) and the
  permission mode isn't `bypassPermissions`/`acceptEdits`, it registers a `PendingRequest`,
  fires `onPermissionRequestCallback`, sends a push notification ("Permission Request — Claude
  wants to …"), and updates a structured `agentState.requests[id]` map
  (`permissionHandler.ts:~185-205`) — this *is* the waiting-on-permission state, delivered as
  data, not inferred from text.
- **Turn-completion / idle state, also as SDK-level bookkeeping**, cross-referenced in the Codex
  driver: `emitReadyIfIdle()` (tested in `src/codex/__tests__/emitReadyIfIdle.test.ts`) only
  emits a "ready" event and notifies when `pending === null AND queueSize() === 0 AND
  !shouldExit` — i.e., idle is "no pending SDK message and empty outbound queue," a precise
  state-machine condition rather than a silence timer.
- **Session lifecycle via Claude Code's own hook system**, for out-of-process visibility:
  `src/claude/utils/generateHookSettings.ts` writes a temporary `settings.json` registering a
  `SessionStart` hook (`matcher: "*"`) that shells out to `session_hook_forwarder.cjs <port>`,
  POSTing session-change events (new/resume/compact) to happy-cli's local HTTP server. This is
  the same mechanism class HANDOFF.md flags to inventory ("Claude Code hooks (Stop,
  Notification, PreToolUse, SessionStart/SessionEnd, statusline)").
- Also present: `src/claude/utils/sessionScanner.ts`, `claudeCheckSession.ts`,
  `claudeFindLastSession.ts` (JSONL transcript-file based session discovery — same family as
  our "transcript JSONL" mechanism in HANDOFF.md) — not fully read, but names/fixtures
  (`__fixtures__/permission-prompt-aborted-with-interrupt.jsonl`) confirm they parse Claude
  Code's on-disk transcript format for permission-abort events specifically.

**States distinguished:** working (SDK streaming), idle/ready (`emitReadyIfIdle`), waiting-on-
permission (`PendingRequest` + `agentState.requests`), denied/approved/canceled (
`completedRequests[id].status`). This is the richest state taxonomy found in this survey,
because it's sourced from the SDK's own event types rather than reconstructed from a terminal.

**Where it lies / fails:**
- Only works because Claude Code (and Codex) expose an in-process Agent SDK / hook surface;
  **not generalizable to opaque CLI TUIs** that don't ship an SDK — which is presumably most of
  the "any CLI agent" surface our project needs to cover. It solves the Claude-Code-specific
  case completely and gives us zero coverage for the terminal-scraping case.
- Its own `resolveToolCallId` matching (`permissionHandler.ts` — matches by tool name + deep-
  equal input, most-recent-first) has a documented 1s-retry escape hatch for "what if we got
  permission before the tool call [was recorded]" — i.e., a real race condition the authors
  hit and patched with a `delay(1000)` + retry rather than a structural fix.
- Not evaluated for Windows support in this pass (file tree only; no platform-gating code read).

### tmux MCP servers ("tmux mcp" search, ~9 independent implementations found)

Surveyed: `nickgnd/tmux-mcp` (298 stars, most starred, actively maintained — used as the
reference implementation), plus smaller forks (`bnomei`, `MadAppGang`, `jonrad`, `PsychArch`,
`lox`, `rinadelph`, `Orad` — all <50 stars, not explored in depth; convergent design, see below).

**What it can observe / exact mechanism (nickgnd/tmux-mcp):**
- Pure tmux passthrough exposed as MCP tools/resources: `list-sessions`, `list-windows`,
  `list-panes`, `capture-pane`, `execute-command`, `get-command-result`, plus session/window/
  pane CRUD (`src/index.ts`). No AI-agent-specific state at all — it's a generic remote-control
  surface, same tier as raw `tmux capture-pane`/`send-keys`.
- **Completion detection for `execute-command` is a sentinel-marker hack, shell-commands only:**
  `src/tmux.ts:239-263` — wraps the user's command as
  `echo "TMUX_MCP_START"; <command>; echo "TMUX_MCP_DONE_<uuid>"` before sending it, then
  presumably polls `capture-pane` output for the end marker to know the command finished (marker
  constants at `tmux.ts:239-240`; the polling loop itself wasn't fetched in this pass). This is
  the same "sentinel echo + poll pane" pattern our own PITFALLS.md and `drive-nested-claude`/
  `tmux-interactive-driver` skills already use for driving nested Claude sessions — confirms
  it's the standard technique for *shell command* completion, but it is structurally inapplicable
  to a fullscreen interactive TUI (Claude Code's own interface) which never returns to a shell
  prompt between turns — there's no exit code or prompt-return event to sentinel around.
- A `--shell-type` CLI flag exists specifically because the server needs to know the shell to
  correctly read the command's exit status — an explicit admission that completion detection is
  shell-syntax-dependent, not terminal-content-dependent.

**States distinguished:** none, beyond "command pending / command has a result." No idle/dead/
waiting-on-input concept.

**Where it lies / fails:**
- Sentinel-marker technique only works for one-shot shell commands issued *by* the MCP server
  itself; it cannot detect state changes in a long-running interactive program (like an agent
  CLI) that the user is driving turn-by-turn, because there's no re-injected sentinel around
  each of the *agent's own* internal state transitions — this is the same limitation PITFALLS.md
  already documents for our own tmux driving of nested Claude sessions (busy indicator absence +
  N stable polls, not sentinel echoing).
- Requires tmux, which is not native on Windows (WSL/Cygwin/MSYS only) — none of the surveyed
  tmux-mcp forks claim native Windows support.

### wezterm and kitty remote-control / CLI (terminal-emulator-level surfaces, not agent-aware)

Both are terminal emulators with a first-class scriptable remote-control protocol, independent
of any specific multiplexer (tmux) or agent framework. Neither has any concept of "AI agent
state" — they're building blocks for scraping/observing a pane, one layer below tmux-mcp.

**wezterm (`wezterm/wezterm`, 28,199 stars)** — docs sourced directly from repo (`docs/cli/…`,
`docs/config/lua/pane/…`) because the rendered wezfurlong.org pages failed to fetch via the
scraper (JS-rendered site; noted as a fetch failure, not a content gap).
- `wezterm cli get-text [--start-line N --end-line N] [--escapes]` — dumps a pane's screen
  text (main screen only by default, negative line numbers reach into scrollback) to stdout.
  Plain polling/diffing surface, same tier as `tmux capture-pane`.
- `wezterm cli list [--format json]` — enumerates window/tab/pane IDs, size, **title**, and
  CWD. Title is attacker/app-controlled (via OSC-2 escape, same mechanism VibeTunnel uses for
  its own title injection) so it's a moderately trustworthy but spoofable "what's running" hint.
- `pane:is_alt_screen_active()` (Lua API, since 20220807) — boolean: is the pane in the
  terminal's alternate-screen mode. Fullscreen TUIs (vim, less, and *most* fullscreen agent
  CLIs like Claude Code's own interactive mode) switch to the alt screen; a plain shell prompt
  does not. **This is a real, cheap, terminal-emulator-native signal for "a fullscreen
  interactive program currently owns this pane" that none of the tmux/vibetunnel tooling
  surfaced** — worth prototyping as a coarse busy/foreground-TUI discriminator, distinct from
  scraping actual pane text.
- Runs natively on Windows, macOS, and Linux (single Rust binary, no tmux dependency).

**kitty (`sw.kovidgoyal.net/kitty`, docs scraped directly)**
- `kitten @ get-text --extent {screen|all|selection|first_cmd_output_on_screen|
  last_cmd_output|last_non_empty_output|last_visited_cmd_output|alternate|
  alternate_scrollback}` — notably richer than wezterm's/tmux's plain screen dump: the four
  `*_cmd_output*` extents return **just the last command's output**, but this requires kitty's
  own shell-integration (shell hooks that mark prompt/command boundaries) to be enabled — i.e.
  kitty already solved "where does this command's output start/end" for shell commands, using
  the same class of shell-hook instrumentation Claude Code's own hooks provide for agent turns.
- **`state:needs_attention`** — a window/tab match-expression state, settable via `kitten @
  ls`/`--match state:needs_attention` queries. Driven by the terminal bell / OSC 777 desktop
  notification escape sequences a program can emit to mark itself as wanting attention — this
  is the terminal-emulator-native equivalent of VibeTunnel's bell-based Claude hack, but generic
  and standardized (any program, not just a patched Claude binary) and exposed as a first-class
  window-state boolean rather than a raw byte the caller must intercept.
- Kitty's remote-control protocol requires `allow_remote_control` in `kitty.conf` or a password;
  runs natively on Windows, macOS, Linux.

**States distinguished (both):** none agent-specific. wezterm gives you alt-screen-active
(TUI-vs-shell) as a boolean; kitty gives you needs-attention (bell-driven) as a boolean. Both
are lower-level primitives we could compose into our own state machine, not ready-made
solutions.

**Where they lie / fail:**
- Neither observes process exit code, PTY silence duration, or any notion of "waiting on
  permission" vs "waiting on input" — both are pure terminal-content/terminal-state APIs;
  all agent-specific interpretation is left to the caller (this is a strictly lower layer than
  tmux-mcp, VibeTunnel, or happy-cli).
- `needs_attention` and alt-screen-active are only as reliable as the target program's own
  escape-sequence discipline: an agent CLI that never emits BEL/OSC-777 never sets
  `needs_attention`; one that never switches to the alt screen (e.g. a bare Python-prompt-style
  Claude Code fallback UI) never sets `is_alt_screen_active`. Both would need to be verified
  empirically against Claude Code's real terminal output, not assumed from spec.
- `wezfurlong.org`'s rendered docs pages failed to fetch via the web-scraper tool in this pass
  (JS-heavy site) — content here is sourced from the GitHub repo's raw markdown instead, which
  is the primary source anyway, but flagging the tool failure per instructions.

### Omnara (omnara-ai/omnara, 2,659 stars) — surveyed at file-tree depth only

"The API for production-grade agents." Mobile+web dashboard with CLI wrappers for driving
agents including Claude Code (`src/integrations/cli_wrappers/claude_code/claude_wrapper_v3.py`)
and a GitHub Action integration. File-tree signals only (contents not read in this pass, time-
boxed): `apps/mobile/src/utils/statusHelpers.ts`, `apps/web/src/utils/statusUtils.ts`, and a
`session_reset_handler.py` suggest a client-side status-derivation layer distinct from the
wrapper itself, plus `src/backend/api/push_notifications.py` for a notification channel. **Not
independently verified** — flagged as a follow-up if deeper Omnara investigation is warranted;
everything above about Omnara is inferred from file names only, not read code (INFERRED).

## Sources

- VibeTunnel repo — https://github.com/amantus-ai/vibetunnel (file contents read via `gh api`:
  `web/src/server/pty/activity-status.ts`, `web/src/server/utils/claude-patcher.ts`,
  `web/src/server/utils/prompt-patterns.ts`, `web/src/server/services/bell-event-handler.ts`,
  `web/src/server/utils/terminal-title.ts`, `web/src/shared/types.ts`, `docs/push-notification.md`,
  `docs/claude.md`, `native/vt-fwd/src/title.rs`, `README.md`)
- happy-cli repo — https://github.com/slopus/happy-cli (file contents read:
  `src/claude/utils/generateHookSettings.ts`, `src/claude/utils/permissionHandler.ts`,
  `src/codex/__tests__/emitReadyIfIdle.test.ts`; file tree only otherwise)
- happy-server repo — https://github.com/slopus/happy-server (metadata only, not explored)
- tmux-mcp (reference impl) — https://github.com/nickgnd/tmux-mcp (file contents read:
  `src/index.ts`, `src/tmux.ts`, `README.md`)
- Other tmux MCP forks (metadata only, not explored in depth): bnomei/tmux-mcp,
  MadAppGang/tmux-mcp, jonrad/tmux-mcp, PsychArch/tmux-mcp-tools, lox/tmux-mcp-server,
  rinadelph/tmux-mcp, Orad/tmux-mcp-server
- wezterm repo docs (fetched via `gh api` after wezfurlong.org rendered site failed to scrape) —
  https://github.com/wezterm/wezterm — `docs/cli/cli/get-text.md`, `docs/cli/cli/list.md`,
  `docs/config/lua/pane/is_alt_screen_active.md`
- kitty remote-control docs (scraped successfully) —
  https://sw.kovidgoyal.net/kitty/remote-control/
- Omnara repo — https://github.com/omnara-ai/omnara (file tree only, contents not read —
  see caveat above)
