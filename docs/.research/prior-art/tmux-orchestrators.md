# Prior art: how existing tmux/multi-agent orchestrators detect Claude Code state

Research pass over projects that market "manage multiple Claude Code sessions" or drive Claude
Code programmatically. Read via `gh api`/`gh search` (github-search skill's CLI path; the `gh`
route was used directly since exact repo names were known) — no web-scraper needed, all evidence
came from source files and issues fetched through the GitHub API.

## Verdict (what matters for our design)

- **The dominant pattern is pane-content polling + string/regex matching, not a documented
  protocol.** claude-squad, the tmux-orchestration heartbeat script, and VibeTunnel all resolve
  to the same primitive: `tmux capture-pane`, hash or diff it, grep it for known substrings.
  There is no cross-tool "busy" API — everyone reverse-engineers Claude Code's TUI output.
- **Content-hash-diff is the most robust "busy vs settled" signal found, but it only proves
  "the screen changed", not "Claude is thinking."** claude-squad's `HasUpdated()` (SHA-256 of
  the captured pane, compared each tick) is a strictly more reliable busy/idle primitive than
  keyword grepping alone, because a spinner frame change alone will hash-differ — confirms our
  PITFALLS.md rule of gating on stable polls, not a single snapshot.
- **The specific "waiting on permission" state is universally detected via a hardcoded literal
  substring of Claude Code's own dialog text**, not any structural signal: claude-squad greps
  for `"No, and tell Claude what to do differently"`; primeline's watchdog and VibeTunnel grep
  for `"esc to interrupt"` / spinner verbs. This is inherently version-fragile — any Claude Code
  UI-copy change silently breaks every one of these tools with no error, only silent misdetection.
- **Nobody found distinguishes "waiting-on-permission" from "waiting-on-input" reliably from the
  pane alone** — both render as "idle-looking, cursor visible" states; tools either collapse
  them into one `hasPrompt`/`idle` bucket (claude-squad, primeline) or sidestep the problem
  entirely by using the Claude Code SDK's structural permission-callback hook instead of pane
  scraping (Omnara). That SDK-hook path is the only mechanism seen that gets a *true* signal
  for "waiting on permission" — everything else is inference from rendered text.
- **The self-report failure mode is real and undocumented as a limitation by its authors**:
  primeline's `heartbeat.sh` treats worker `status` fields as ground truth from JSON files the
  workers themselves write (`workers/*.json`), while only the orchestrator's own pane is polled
  externally via `check_pane_idle`. A hung/crashed worker that never updates its own status file
  is invisible to the heartbeat's own polling loop except via the blunt "stale timestamp" check.
- **claude-flow (67k stars, most popular result) is not a counterexample worth modeling** — it
  does not scrape tmux panes for individual agent turn-state at all. Its "swarm monitor" is a
  `ps aux | grep` process-count heuristic, and its real state signal is Claude Code's official
  hooks (`PreToolUse`/`PostToolUse`/`Stop`/`PreCompact`), which is the mechanism our own
  HANDOFF.md already flags as the channel to inventory — this cross-validates hooks as the
  higher-fidelity alternative to pane scraping, confirmed independently by a second project (Omnara).

## Mechanisms found

### smtg-ai/claude-squad (8,237 stars, Go, actively maintained)

**Repo:** https://github.com/smtg-ai/claude-squad — manages multiple Claude Code/Aider/Codex/
Gemini/Amp tmux sessions with git worktrees, one tmux pane per agent, via a Bubble Tea TUI.

**Exact mechanism** (`session/tmux/tmux.go:220-243`, `app/app.go:240-260`,
`daemon/daemon.go:44-58`):
1. Every tick (500 ms, `app/app.go:956` `tickUpdateMetadataCmd`), for each active instance:
   `tmux capture-pane -p -e -J -t <session>` captures the full pane with ANSI codes preserved.
2. The captured string is SHA-256 hashed (`session/tmux/tmux.go:200-243`, `statusMonitor.hash`)
   and compared to the previous tick's hash. Any diff → `updated = true`.
3. Independently, the same capture is grepped for a literal confirmation-dialog substring, one
   per backend (`tmux.go:225-235`):
   - Claude: `"No, and tell Claude what to do differently"`
   - Aider: `"(Y)es/(N)o/(D)on't ask again"`
   - Gemini: `"Yes, allow once"`
   → sets `hasPrompt = true`.
4. State transition logic (`app/app.go:244-250`):
   - `updated == true` → `Status = Running`
   - `updated == false && hasPrompt == true` → auto-tap Enter (if AutoYes), stay effectively
     in a permission-wait loop
   - `updated == false && hasPrompt == false` → `Status = Ready` (idle, prompt for user)
   - Separately, `Status = Loading` while `instance.Start()` is in flight, and `Status = Paused`
     when the worktree/session is detached (not a live-detection state, a lifecycle state).
5. Trust/first-run dialogs handled the same way: literal-substring match on
   `"Do you trust the files in this folder?"` or `"new MCP server"` → auto-tap Enter
   (`tmux.go:157-174`, `CheckAndHandleTrustPrompt`).
6. A separate always-on daemon (`daemon/daemon.go`) does the *same* `HasUpdated()` poll on a
   configurable interval purely to auto-tap-Enter through permission prompts (AutoYes mode) even
   when no UI is attached — i.e., the daemon is a second, independent poller hitting the same
   `tmux capture-pane`.

**States distinguished:** `Running` (screen changed since last tick), `Ready` (screen static,
no known prompt substring), a collapsed prompt-handling branch (screen static + prompt substring
found — auto-answered, never surfaced as its own UI state to the human operator), `Loading`
(app-level: `Start()` in flight), `Paused` (app-level: worktree detached, not a live signal).
There is no distinct "waiting-on-input" state — "Ready" is used for both "waiting for user to
type a message" and, ambiguously, immediately after a permission dialog is auto-answered.

**Where it lies / fails:**
- Hash-diff triggers on **any** pixel-equivalent change — including a spinner tick, a timestamp
  in the transcript, or terminal-bell artifacts — so `Running` can be true even when Claude is
  not doing real work, and conversely a long silent Bash command produces zero hash-diff and
  will misreport `Ready` even though the agent is genuinely busy (issue titled "Error capturing
  pane content after starting cs", #216 — capture-pane itself errored out mid-session and froze
  the whole UI until the tool crashed).
- Literal substring matching is tied to the exact wording of Claude Code's own confirmation
  dialog. Any upstream Claude Code UI-copy change (a real risk — Anthropic ships CLI updates
  frequently) silently breaks `hasPrompt` detection with no error surfaced.
- `-y`/AutoYes mode is reported broken by users independent of the state-detection mechanism —
  issue #151 ("yolo mode (autoyes) not working") shows that even when the state signal fires
  correctly, the auto-answer keystroke doesn't always land, and a maintainer comment concedes
  the real fix is `--dangerously-skip-permissions` rather than fighting the TUI.
- Cross-platform is broken outright on native Windows: `creack/pty` (their PTY dependency)
  compiles a stub with `ErrUnsupported` on non-Unix `GOOS`, so `tmux new-session` fails
  immediately on Windows (issue #275) — the whole approach is Unix-PTY-only unless run under WSL.

### primeline-ai/claude-tmux-orchestration (39 stars, Bash, active as of 2026-07-30)

**Repo:** https://github.com/primeline-ai/claude-tmux-orchestration — spawns Claude Code
"workers" as parallel tmux panes with a bash heartbeat loop coordinating them via files.

**Exact mechanism** (`_orchestrator/heartbeat.sh`):
1. ANSI-strip pipeline (`strip_ansi`, lines ~48-56) runs a 5-stage `sed -E` before any regex —
   explicit acknowledgment that raw `capture-pane` output must be de-escaped before matching or
   idle-detection regexes silently never match.
2. `check_pane_idle()` (lines ~103-121) captures only the **last 12 lines**
   (`tmux capture-pane -t "$target" -p -S -12`) and applies two regex passes in strict order:
   - Busy override (checked first): `(Running|thinking|Searching|Reading|Writing|Editing)` → busy
   - Idle: `(❯[\s ]*$|>\s*$|waiting for input|claude\s+code\s+v[0-9.]+|\$\s*$)` → idle
   - Anything matching neither → **assumed busy** (documented "safe default").
3. This idle check is only ever run against the **orchestrator's own pane**
   (`ORCH_PANE="${SESSION_NAME}:0"`), never against individual worker panes — worker liveness is
   inferred entirely from self-reported JSON files (`workers/*.json`, read by `collect_workers()`,
   status field free-text: `working|running|in_progress|waiting|blocked|done|stopped|error`).
4. `send_to_pane()` (lines ~137-160) implements exactly the two-call send-keys pattern our own
   PITFALLS.md documents independently: literal `send-keys -l` for text, a separate `send-keys
   Enter`, then a **delivery verification** step — capture-pane again and grep for the first 40
   chars of the sent message — with up to 3 retries on failure.
5. Adaptive polling interval (`determine_interval()`, lines ~180-220): 30 s if any worker's
   self-reported `updated` timestamp is stale by more than 3× the normal interval ("stuck"),
   120 s if any worker is actively `working`/`waiting`, 300 s if no workers exist ("idle" —
   this is a *resource-saving* idle, unrelated to agent-busy/idle).
6. A second script, `rate-limit-watchdog.sh`, greps pane output independently for a *different*
   state signal — API rate-limiting — via a literal pattern list (`"Rate limit"`, `"429"`,
   `"overloaded"`, etc.) and drives a scripted resume message after a cooldown, explicitly
   because pasting a rate-limit error back to Claude makes it "use a workaround instead of
   retrying" (documented rationale in the script's own header comment).

**States distinguished (orchestrator pane only):** idle vs busy (binary, via regex), plus, for
workers, whatever free-text status string the worker script chose to self-report (no external
verification) and a derived binary "stuck" flag from timestamp staleness.

**Where it lies / fails:**
- The idle regex `>\s*$|\$\s*$` matches on `>` or `$` at end of line — this is precisely the
  false-idle-signal trap PITFALLS.md already flags for us ("`❯` is not an idle signal... gate on
  busy indicator being ABSENT"): a mid-generation frame that happens to have a shell prompt
  string embedded in printed output (e.g. Claude echoing a shell command) can false-positive
  idle. The script has no equivalent of our "N stable polls" debounce — a single capture decides.
- Worker state is **not verified externally at all** — a worker whose pane hung (e.g., crashed
  mid-write, or blocked on a dialog it never self-reports) is invisible to the heartbeat except
  through the 3×-interval staleness heuristic, which only fires for workers that were *already*
  self-reporting `working`/`waiting` before going silent; a worker that crashes before writing
  its first status file is never flagged "stuck" at all.
- No open GitHub issues exist for this repo (only 39 stars, low usage) — the failure modes above
  are inferred from source, not corroborated by field reports. (INFERRED)

### ruvnet/claude-flow (67,092 stars — most popular hit, but NOT a pane-scraper)

**Repo:** https://github.com/ruvnet/claude-flow — "agent meta-harness" / swarm orchestration
framework. Despite topping star-count for "manage multiple Claude Code sessions" style searches,
it does **not** implement tmux pane-based turn-state detection.

**Exact mechanism found:**
- `.claude/helpers/swarm-monitor.sh`: counts *processes*, not conversation turns —
  `ps aux | grep -E "agentic-flow"` / `grep -E "mcp.*start"` / `grep -E "(agent|swarm|coordinator)"`,
  divides/estimates an "active agent count" heuristically (`agentic_flow_count / 2`, with a
  floor of 1 if any process exists), and writes a JSON activity snapshot every 5 s. This answers
  "is *something* running" at the OS level, not "is *this* Claude Code session mid-turn,
  idle, or blocked on a dialog."
- The actual per-turn state signal is Claude Code's own **hooks system**
  (`.claude-plugin/hooks/hooks.json`): `PreToolUse`/`PostToolUse` (matched on `Bash` and
  `Write|Edit|MultiEdit`), `PreCompact`, and `Stop` events invoke a shell shim
  (`ruflo-hook.sh`) that always exits 0 (`|| true` on every command, explicitly so a hook
  failure never blocks a Claude Code turn). This is a structural, Anthropic-documented signal
  rather than inferred text — it independently corroborates HANDOFF.md's plan to inventory
  Claude Code hooks as a detection channel.
- The hooks manifest itself documents a real cross-platform gap (from its own `_platform` field
  and description): it is POSIX-only (`/bin/bash`, `jq`, `xargs`) and "known-broken on native
  Windows", with a separate, unaudited legacy Node-based (`ruflo-hook.cjs`) hook set that the
  POSIX manifest never references — i.e., the project's own hook implementation is fragmented
  and not verified to work identically across the Bash and Node paths. (Directly quoted from the
  repo's own hooks.json description field.)

**States distinguished:** none in the busy/idle/waiting sense we need — process-existence and
tool-call boundaries only, no notion of "waiting on permission" vs "waiting on user input" vs
"dead".

**Where it lies / fails:** the process-count heuristic is a poor proxy — `agentic_flow_count / 2`
is an admitted estimate, not a measurement, and a single hung/zombie process inflates the count
indefinitely with no liveness check.

### amantus-ai/vibetunnel (4,625 stars, TypeScript/Swift, active)

**Repo:** https://github.com/amantus-ai/vibetunnel — "turn any browser into your terminal &
command your agents on the go"; runs a PTY-backed web terminal with session activity tracking,
plus a native macOS menu-bar app.

**Exact mechanism:**
- `web/src/server/pty/activity-status.ts` (`computeActivityStatus`): a **generic, agent-agnostic**
  activity heuristic — not Claude-specific. Tracks `lastOutputTimestamp`/`lastInputTimestamp` on
  the raw PTY byte stream; `isActive = (now - max(lastOutput, lastInput, lastModified, startedAt))
  <= idleTimeoutMs` with `DEFAULT_ACTIVITY_IDLE_TIMEOUT_MS = 5000`. This only answers "did any
  byte cross the PTY in the last 5 s" — it cannot distinguish "Claude is generating" from "a
  long-running shell command that happens to print nothing" from "user is typing slowly."
- A separate, Claude-specific text-classification path exists in
  `web/src/client/components/terminal-chat-view.ts` (line ~688-700): a large literal/line-based
  filter list explicitly built to recognize and strip Claude Code TUI chrome —
  `'esc to cancel'`, `'esc to interrupt'`, `'bypass permissions on'`, plus Claude's own randomized
  "verb" status words (`'Marinating'`, `'Clauding'`, `'Simmering'`, `'Considering the Greeting'`,
  `"I'm Feeling Lucky"`) and status-bar fragments (`auto`/`manual`/`plan` mode indicators). This
  confirms Claude Code's busy-indicator vocabulary is **not a fixed string** — it rotates through
  a set of playful verbs, so any detector keying on one literal (e.g., just `"esc to interrupt"`)
  is correct today but should expect the surrounding word list to keep growing; a regex/set
  membership check, not a single substring, is the robust form. This particular list is used to
  filter noise out of a derived terminal *title*, not directly to gate a busy/idle status field —
  but it is the most complete enumeration of Claude Code TUI chrome found in any of these repos.

**States distinguished:** binary active/inactive per PTY session (generic timeout-based), decoupled
from any Claude-specific semantic state.

**Where it lies / fails:** issue #541 ("All sessions shown as 'Idle' in the Mac app") — the web
UI and the native Mac app disagree on the same session's active/idle status, i.e. two consumers
of what should be one activity signal drifted out of sync, an integration bug rather than a
detection-algorithm bug, but it demonstrates that even a simple last-byte-timestamp heuristic is
easy to get inconsistent across surfaces if the propagation path isn't single-sourced.

### omnara-ai/omnara (2,659 stars, Python/TypeScript, active) — the SDK-hook counterexample

**Repo:** https://github.com/omnara-ai/omnara — "the API for production-grade agents"; runs
Claude Code **headlessly** (not attached to a visible interactive tmux pane) via the official
`claude_code_sdk` Python SDK and relays turns through a webhook/mobile app.

**Exact mechanism** (`src/integrations/headless/claude_code.py`):
- Uses `ClaudeSDKClient`/`ClaudeCodeOptions` from the official Claude Code SDK, **not** a PTY or
  tmux pane at all.
- Registers a custom MCP server/tool named `mcp__omnara__approve` and passes it as
  `permission_prompt_tool_name` in `ClaudeCodeOptions` (lines ~137-145) — permission requests are
  intercepted **structurally** through the SDK's own permission-callback mechanism, not inferred
  from rendered dialog text. This is a materially different, higher-fidelity signal than every
  pane-scraping project above: the SDK itself tells the integration "a permission decision is
  needed right now," rather than the integration guessing from a regex match on terminal output.
- "Waiting on user input" is likewise explicit and structural: `send_to_omnara(...,
  requires_user_input=True)` is called at defined points in the turn loop (e.g. line ~421,
  "Waiting for initial user input...") — a boolean flag set by the orchestration code at a known
  point in the SDK's async conversation loop, not inferred post-hoc from output.

**States distinguished:** turn-boundary-accurate "processing" vs "waiting on user input" vs
"waiting on permission" (via the dedicated approve-tool callback) — the cleanest three-way split
found in this survey, because it is derived from SDK call structure rather than terminal text.

**Where it lies / fails:** this mechanism is only available because Omnara runs Claude Code
**headlessly through the SDK**, not by driving the interactive TUI a human would otherwise use
in a terminal/tmux pane. It does not generalize to "detect state of an existing interactive CLI
session someone is also watching/typing into" — the exact problem this project (agent-state-driver)
is scoped to solve. It is included here specifically because it proves a structural, non-scraped
signal for at least "waiting on permission" *exists* in Claude Code's own SDK, which is relevant
prior art for our hooks-channel investigation even though the mechanism itself isn't directly
reusable for TUI-attached detection. (INFERRED: no GitHub issues were searched for this repo —
time-boxed out of this pass given the mechanism's inapplicability to our TUI-attached use case.)

### Not found / ruled out

- **`tmux-composer`**: no project by that name manages Claude Code sessions. The closest name
  match, `possibilities/tmux-composer-cli` (2 stars), is a generic tmux layout/session composer
  unrelated to AI-agent state detection (contains one incidental `claude-chats.ts` file, not
  explored further — too low-signal to warrant the budget).
- **Piebald-AI "agent-farm"**: no such repository exists in the `Piebald-AI` GitHub org (24 repos
  enumerated directly via `gh api users/Piebald-AI/repos`); their closest projects
  (`claude-code-lsps`, `claude-code-chats`, `claude-code-themes`, `claude-code-system-prompts`)
  are about Claude Code *tooling/theming*, not multi-session state detection or orchestration.

## Sources

- claude-squad — https://github.com/smtg-ai/claude-squad
  - `session/tmux/tmux.go` (capture-pane, hash-diff, literal prompt matching) — read in full via `gh api repos/smtg-ai/claude-squad/contents/session/tmux/tmux.go`
  - `session/instance.go` (Status enum: Running/Ready/Loading/Paused) — read in full
  - `app/app.go` (500 ms tick loop, state-transition logic ~line 240-260, 954-960)
  - `daemon/daemon.go` (independent AutoYes poller, full file read)
  - Issue #275 — https://github.com/smtg-ai/claude-squad/issues/275 (Windows PTY unsupported)
  - Issue #216 — https://github.com/smtg-ai/claude-squad/issues/216 (capture-pane error freezes UI)
  - Issue #151 — https://github.com/smtg-ai/claude-squad/issues/151 (AutoYes unreliable)
- primeline-ai/claude-tmux-orchestration — https://github.com/primeline-ai/claude-tmux-orchestration
  - `_orchestrator/heartbeat.sh` (full file read: ANSI-strip, idle regex, adaptive interval, send-verify)
  - `_orchestrator/rate-limit-watchdog.sh` (partial read: rate-limit pattern list, resume-message rationale)
  - Blog referenced in script header: https://primeline.cc/blog/tmux-orchestration (not fetched independently — cited by the script itself)
- ruvnet/claude-flow — https://github.com/ruvnet/claude-flow
  - `.claude/helpers/swarm-monitor.sh` (full file read: process-count heuristic)
  - `.claude-plugin/hooks/hooks.json` (full file read: hook events used, POSIX-only caveat quoted from its own description field)
- amantus-ai/vibetunnel — https://github.com/amantus-ai/vibetunnel
  - `web/src/server/pty/activity-status.ts` (full file read: generic byte-timestamp activity heuristic)
  - `web/src/client/components/terminal-chat-view.ts` (partial read, lines ~688-708: Claude Code TUI chrome/verb filter list)
  - Issue #541 — https://github.com/amantus-ai/vibetunnel/issues/541 (Mac app vs web UI activity-status disagreement)
- omnara-ai/omnara — https://github.com/omnara-ai/omnara
  - `src/integrations/headless/claude_code.py` (partial read, grep-targeted: SDK permission-callback and requires_user_input flag)
- Negative/ruled-out findings — `gh api users/Piebald-AI/repos` (full org repo listing); `gh search repos "tmux-composer"` (no matching orchestrator)
