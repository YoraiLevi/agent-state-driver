# Prior-art synthesis: how agent state is actually detected

Synthesis of seven independent research passes under `docs/.research/prior-art/`
(`gist-windows-sessions.md`, `gist-middle-layer-map.md`, `cultureagent.md`,
`tmux-orchestrators.md`, `terminal-drivers.md`, `expect-lineage.md`, `hooks-inventory.md`),
all dated 2026-08-05. Every claim below carries its provenance as
`[researcher-file → original citation]`. Where a citation is second-hand (a researcher
quoting a gist quoting a source) it is labelled **2nd-hand**. Inference added by this
synthesis is labelled **(INFERRED)**.

Target state space, per HANDOFF.md: `working / idle / waiting-on-permission /
waiting-on-input / dead`.

---

## Verdict

- **No surveyed project distinguishes all five target states from a terminal.** The richest
  terminal-layer taxonomies are 2-3 states (`Running|Ready|Loading|Paused`, `starting|running|
  exited` + `isActive`). Every project that reaches a 3+ state taxonomy got there by leaving
  the terminal entirely (SDK callbacks, hooks, JSON-RPC). Our five-state goal is unprecedented
  in this survey and must be treated as a research claim, not a port of someone's design.
- **`working` is unsolved everywhere, including by projects that defined it.** cultureagent
  ships `STATE_WORKING` in its enum and its own wire-contract doc says no backend emits it —
  "no backend has an observable tool-execution boundary" [cultureagent.md → `presence.md`
  Activity States table; `clients/shared/presence_emitter.py:35,51`]. Screen-scrapers can
  only prove "pixels changed," which is not the same claim.
- **The three-pole taxonomy is real and independently reached**: vendor-emitted structured
  events > native typed VT state > external heuristic scraping [gist-middle-layer-map.md,
  gist axis 2.6; terminal-drivers.md reached the same ranking independently from different
  repos]. But poles 1 and 3 answer *different questions*: pole 1 works only for an agent
  **you spawned**, pole 3 is the only pole that observes an agent **someone else launched**.
  That is not a quality ranking, it is a scope split, and our HANDOFF.md mission spans both.
- **Screen-scraping's dominant failure mode has a name, a bug report, and a convergent fix.**
  In-place TUI redraw leaves stale status text on screen alongside the new state
  (`awslabs/cli-agent-orchestrator#182`, Kiro CLI: "retains 'Kiro is working' … alongside the
  new idle prompt" → "Handoff delegations never complete") [both gist files, 2nd-hand]. Fix,
  converged on by two unrelated projects: anchor to bottom-N lines or the OSC title, never
  the whole buffer, plus NOT-gates for stale artifacts. This is the external instance of
  PITFALLS.md's "`❯` is not an idle signal."
- **Dead ≠ one mechanism.** cultureagent is the only project that separates *clean death*
  (EOF/socket close → `offline`) from *silent wedge* (heartbeat stale → `presumed_hung`,
  90s threshold vs 30s heartbeat) [cultureagent.md → `presence.md` Stale-Busy Watchdog;
  `culture_core/config.py:74-85`]. No hook on either Claude Code or Codex fires for a
  SIGKILL [hooks-inventory.md]. Liveness must come from outside the agent, always.
- **Two "independent corroborations" in the researcher set are actually one source.**
  `claude_code.tool.blocked_on_user` and `cli-agent-orchestrator#182` each appear in two
  researcher files, but both files extract the *same* upstream gist. Neither was
  independently re-fetched. Treat both as single-sourced and verify before designing on them.

---

## 1. Taxonomy of detection channels

Nine channels emerged. Six map cleanly to the brief's categories; three are distinct enough
to break out (activity-timers, telemetry, self-report heartbeat).

### 1.1 Screen-scrape — rendered-text matching

**Mechanism.** Capture a pane's rendered text (`tmux capture-pane -p [-e -J] [-S -N]`,
`wezterm cli get-text`, `kitten @ get-text`), ANSI-strip it, regex/substring match against
known TUI copy.

**States it can prove.** Strictly: *"this glyph sequence is currently rendered."* Everything
else is inference. In practice projects extract:
- waiting-on-permission — via a literal from the vendor's own dialog:
  `"No, and tell Claude what to do differently"` (Claude), `"(Y)es/(N)o/(D)on't ask again"`
  (Aider), `"Yes, allow once"` (Gemini) [tmux-orchestrators.md → claude-squad
  `session/tmux/tmux.go:225-235`].
- working — via a busy indicator: `esc to interrupt` plus a *rotating verb set*
  (`Marinating`, `Clauding`, `Simmering`, `Considering the Greeting`, `I'm Feeling Lucky`)
  [tmux-orchestrators.md → vibetunnel `web/src/client/components/terminal-chat-view.ts:~688-708`].

**Latency.** Poll-interval-bound. Observed: 500 ms (claude-squad `app/app.go:956`); adaptive
30/120/300 s (primeline `determine_interval()`).

**Platform coverage.** tmux: no native Windows (WSL/Cygwin only); claude-squad is broken
outright on native Windows because `creack/pty` compiles an `ErrUnsupported` stub
(issue #275) [tmux-orchestrators.md]. wezterm and kitty are native on all three OSes and are
the most credible cross-platform capture surfaces found [terminal-drivers.md].

**How it lies.**
| Lie | Evidence |
|---|---|
| Stale redraw — old status text survives an in-place partial redraw, so a whole-buffer match never sees the state change | `awslabs/cli-agent-orchestrator#182` (2nd-hand, both gist files) |
| Prompt glyph is always rendered, including mid-generation | PITFALLS.md, ours; primeline's idle regex `>\s*$\|\$\s*$` reproduces the trap with **no** stable-poll debounce — a single capture decides [tmux-orchestrators.md → `heartbeat.sh:103-121`] |
| Literal dialog copy is a vendor UI string with no compat promise; a copy change breaks detection **silently**, no error | tmux-orchestrators.md, across claude-squad + primeline + vibetunnel |
| Busy vocabulary is a rotating set, not a fixed string — single-literal matching is already known-incomplete today | vibetunnel chrome-filter list, above |
| Capture itself can error and hang the consumer | claude-squad issue #216, "Error capturing pane content after starting cs" — froze the UI until crash |
| Blank-row padding / ANSI escapes defeat naive matching | PITFALLS.md (ours); primeline ships a 5-stage `sed -E` ANSI-strip before any regex [`heartbeat.sh:48-56`] |

### 1.2 Activity timers and content hashing — "something changed" without meaning

Mechanically distinct from 1.1: no semantics are extracted, only change/no-change.

**Mechanism.** Either hash the captured pane and diff against the previous tick
(claude-squad `HasUpdated()`, SHA-256, `session/tmux/tmux.go:200-243`), or timestamp raw PTY
bytes and threshold the silence (VibeTunnel `computeActivityStatus()`,
`isActive = now - max(lastOutput, lastInput, lastModified, startedAt) <= 5000ms`,
`web/src/server/pty/activity-status.ts:29`) [tmux-orchestrators.md and terminal-drivers.md
— **independently cross-read the same file and agree**].

**States it can prove.** A binary busy/quiet. Nothing more.

**Latency.** Hash-diff: one tick (500 ms). Silence-timer: cannot declare idle faster than
the threshold — VibeTunnel is structurally ≥5 s late on every idle transition.

**Platform coverage.** Byte-timestamping is platform-neutral (needs only a PTY read);
hash-diff inherits the capture layer's constraints (1.1).

**How it lies.** Both directions, and this is the sharpest finding in the survey:
- **False busy**: a spinner frame, a clock, or a bell artifact changes the hash with zero
  agent progress [tmux-orchestrators.md].
- **False idle**: a long silent `Bash` command produces no output for minutes → no hash diff,
  no bytes → reported `Ready`/idle while genuinely working [tmux-orchestrators.md]. VibeTunnel
  has the same hole at 5 s for silent model thinking [terminal-drivers.md].
- **Propagation drift**: VibeTunnel #541 — Mac app and web UI disagreed on the same session's
  active/idle state; one signal, two consumers, out of sync.

### 1.3 Harness hooks — vendor lifecycle callbacks

**Mechanism.** Register a handler in a settings file; the agent process invokes it
synchronously at named lifecycle points. Claude Code exposes ~30 events; Codex exposes a
near-1:1 subset [hooks-inventory.md, full enumeration tables, scraped from
`code.claude.com/docs/en/hooks` and `developers.openai.com/codex/hooks`, 2026-08-05].

**States it can prove.**
| Target state | Hook | Confidence |
|---|---|---|
| waiting-on-permission | `PermissionRequest` (both CLIs) — fires *at* the dialog instant with `tool_name`/`tool_input`; observable passively by omitting `decision` | **Proof**, zero inference |
| waiting-on-input (2nd kind) | `Elicitation` / `ElicitationResult` — an MCP server asking a question, a *different* dialog type from tool permission | Proof, but easily missed |
| waiting (either kind) | `Notification` with `notification_type: agent_needs_input` / `agent_completed` — **Claude Code v2.1.198+ only**, no Codex equivalent | Proof, version-gated |
| turn-end / candidate-idle | `Stop` / `SubagentStop`; carries `background_tasks` + `session_crons` (v2.1.145+) so "done" is distinguishable from "paused for async work" | Proof of turn-end, **not** of idle-forever |
| working (tool granularity) | `PreToolUse` → `PostToolUse` / `PostToolUseFailure` / `PostToolBatch` | Proof of tool activity only |
| working (generation, no tool) | none — `MessageDisplay` is explicitly display-only and its output never reaches an external reader | **Blind spot** |
| dead | none on either CLI | **Blind spot** |
| internal stall that looks like a hang | `PreCompact`/`PostCompact` — compaction can take many seconds with zero tool activity | Proof, if you subscribe |

**Latency.** Lowest of any channel: synchronous in-process dispatch + handler startup
(~5-20 ms for a shell script; HTTP hooks add RTT) [hooks-inventory.md].

**Platform coverage.** The hook mechanism is platform-neutral; *implementations* are not —
claude-flow's own `hooks.json` declares itself POSIX-only (`/bin/bash`, `jq`, `xargs`) and
"known-broken on native Windows," with an unreferenced legacy Node hook set alongside it
[tmux-orchestrators.md, quoted from the repo's own `description` field].

**How it lies / fails.**
- **Cannot be retrofitted onto a running session** — the hook must be in a settings file when
  the session starts [hooks-inventory.md]. This is the single hardest constraint on the
  channel and it collides directly with "observe a session a human already launched."
- **Silent non-installation**: `disableAllHooks: true` or a workspace-trust dialog can prevent
  a hook from ever running with no signal to the outside driver [hooks-inventory.md]. Partial
  mitigation exists: the transcript's `system`/`stop_hook_summary` record proves whether a
  Stop hook actually ran and whether it errored (see 1.4).
- **Codex requires explicit per-hook trust**, hashed against content — a driver that writes a
  hook programmatically gets nothing until a human trusts it via `/hooks` or
  `--dangerously-bypass-hook-trust`. Claude Code has no such gate. **Deployment blocker
  unique to Codex** [hooks-inventory.md].
- **Codex hooks are all blocking** — `async: true` is parsed but unimplemented; `prompt`/
  `agent` hook types are parsed and silently skipped [hooks-inventory.md].
- `PermissionRequest` does not fire for calls that need no permission (bypass mode,
  pre-allowed), and in contexts that *cannot* prompt it drives an auto-deny — a passive
  observer cannot tell "denied, no dialog possible" from "waiting for a human" without also
  knowing the session mode [hooks-inventory.md].
- `Stop` does **not** fire on user Ctrl-C interrupt — a killed turn looks like silence
  [hooks-inventory.md].
- `PermissionDenied` fires only for *auto-mode classifier* denials — manual dialog denial, a
  `PreToolUse` block, and deny-rule matches all produce nothing [hooks-inventory.md].
- `SessionEnd` fires on `/clear` too — conflating it with process death is a bug
  [hooks-inventory.md].

**Unresolved between researchers.** gist-middle-layer-map reports five hook *types*
(`command`, `prompt`, `agent`, `http`, `mcp_tool`) with `http` on 13 events (2nd-hand via the
gist). hooks-inventory scraped the canonical hooks doc directly and enumerated events
exhaustively but reported **no hook-type taxonomy at all**. Not a contradiction — a
non-corroboration. The `http`-hook-as-long-lived-endpoint idea is architecturally load-bearing
if true and rests on one second-hand source. **Verify against the primary doc before designing
on it.**

### 1.4 Transcript watching — the durable on-disk log

**Mechanism.** Tail `~/.claude/projects/<project>/<session>.jsonl` (Claude Code) or
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (Codex). Reverse-engineered live on this
machine across 8 sessions [hooks-inventory.md].

**States it can prove.** Uniquely, two things no hook exposes:
- `system`/`turn_duration` (`durationMs`, `messageCount`) — turn-end **with wall clock**,
  written with no hook configured.
- `system`/`stop_hook_summary` (`hookCount`, `hookInfos[].command/durationMs`, `hookErrors[]`,
  `preventedContinuation`) — **proof a hook actually ran**, the only antidote to the
  silent-non-installation failure in 1.3.

Also present: `system`/`compact_boundary` (explains long silent gaps), `mode`/`permission-mode`
records, `assistant` blocks with `tool_use`, and a `parentUuid` linked list that delimits turn
boundaries [hooks-inventory.md].

**Latency.** Not a push channel. Bounded by your poll/FS-watch (inotify / FSEvents /
ReadDirectoryChangesW), not by the agent.

**Platform coverage.** Plain files; the Windows layout was verified to be a *tree*, not a flat
file — sibling `<session-uuid>/subagents/agent-<id>.jsonl` + `.meta.json` sidecars carrying
`{agentType, description, toolUseId, spawnDepth}`, so subagent fan-out topology is readable
from the filesystem alone [gist-windows-sessions.md, 2nd-hand, stated verified on Windows 11
build 26200].

**How it lies.**
- **No published schema on either vendor.** Every field name above was reverse-engineered.
  Codex's docs explicitly warn "the transcript format isn't a stable interface"
  [hooks-inventory.md].
- Sessions **fork** (`forkedFrom` observed) — a consumer tracking line numbers without
  `sessionId`/`forkedFrom` will misattribute records across logical conversations.
- `CLAUDE_CONFIG_DIR` relocates the whole tree; `cleanupPeriodDays` garbage-collects it
  [gist-windows-sessions.md, 2nd-hand].
- happy-cli parses this format for permission-abort events and ships a fixture named
  `permission-prompt-aborted-with-interrupt.jsonl` — evidence the format is usable and that
  the interrupt case needed a dedicated fixture [terminal-drivers.md].

### 1.5 Protocol modes — structured stdio the driver spawns

**Mechanism.** Run the agent in a non-interactive/structured mode and read typed events:
`claude -p --output-format stream-json` (+ `--include-hook-events`,
`--include-partial-messages`, `--forward-subagent-text`, `--replay-user-messages`,
`--input-format stream-json` for duplex); `codex exec --json`; `codex app-server` JSON-RPC
over stdio; ACP JSON-RPC over stdio; or the in-process Agent SDK.

**States it can prove.** The most complete set found anywhere:
- working, at **token granularity** — `--include-partial-messages`; nothing else in this
  survey sees mid-generation progress [hooks-inventory.md].
- working, still-alive-just-slow — `system/api_retry` fires before an API retry; no hook
  equivalent exists [hooks-inventory.md].
- hook lifecycle **inline in the same ordered stream** — `hook_started` → optional
  `hook_progress` → `hook_response` triplets, verified live on this machine (v2.1.222)
  [hooks-inventory.md, raw capture at `/tmp/claude_stream_test.jsonl`].
- turn boundaries as protocol events: Codex `turn/started` → `self._busy = True`,
  `turn/completed` → `False` [cultureagent.md → `clients/codex/agent_runner.py:333-335,361-369`];
  ACP `agent_message_chunk`/`agent_thought_chunk` → busy, presence of `stopReason` → not busy
  [cultureagent.md → `clients/acp/agent_runner.py:388-401`].
- waiting-on-permission as a **typed callback**: happy-cli's `canCallTool` →
  `PendingRequest` + `onPermissionRequestCallback` + `agentState.requests[id]`
  [terminal-drivers.md → `src/claude/utils/permissionHandler.ts:~185-205`]; Omnara's
  `permission_prompt_tool_name = mcp__omnara__approve`
  [tmux-orchestrators.md → `src/integrations/headless/claude_code.py:~137-145`].
- idle as a **state-machine predicate**, not a timer: happy-cli's `emitReadyIfIdle()` fires
  only when `pending === null && queueSize() === 0 && !shouldExit`
  [terminal-drivers.md → `src/codex/__tests__/emitReadyIfIdle.test.ts`].

**Latency.** Streams live after process spawn; strictly better than transcript polling for
generation events, comparable to hooks for hook-derived events [hooks-inventory.md].

**Platform coverage.** Ordinary pipes, no PTY. **Cross-platform behavioral parity is INFERRED
and never measured** — nobody has run this on Windows and Linux and diffed the output; the
upstream gist flags this as its own single load-bearing untested claim
[gist-windows-sessions.md, gist lines 42, 1154, 1456, 1727].

**How it lies / fails.**
- **It cannot attach to an already-running interactive TUI.** Stated independently by three
  researchers [hooks-inventory.md; gist-windows-sessions.md; gist-middle-layer-map.md]. This
  is the channel's defining boundary.
- `-p` is headless: `AskUserQuestion` and `ExitPlanMode` normally block in non-interactive
  mode [hooks-inventory.md]. A documented `PreToolUse` `"defer"` decision plus
  `claude -p --resume <session-id>` is the escape hatch — **documented, not exercised live**.
- Anthropic closed native network-attach twice as `not_planned`
  (`anthropics/claude-code#24365`, `#6686`) — no vendor rescue is coming for the
  attach-to-existing-session case [gist-middle-layer-map.md, 2nd-hand].
- Per-vendor plumbing: N agent CLIs means N integrations [both gist files, cultureagent.md].
- **SDK hangs need double-wrapping.** cultureagent wraps `send_and_wait`'s own 120 s timeout
  in an outer `asyncio.wait_for` with the comment *"if send_and_wait's own 120s timeout
  doesn't fire (SDK ignores it, hangs before that, or wedges in a different layer), this
  wraps the whole turn"* [cultureagent.md → `clients/copilot/agent_runner.py:190-232`].
  Structured protocols wedge too.
- **Race, documented**: happy-cli's `resolveToolCallId` matches permission → tool-call by
  name + deep-equal input, most-recent-first, with a `delay(1000)` + retry escape hatch for
  "we got permission before the tool call was recorded" [terminal-drivers.md]. Typed events
  still arrive out of order.
- **Poll-fallback even in a typed protocol**: cultureagent's ACP backend polls
  `while self._busy: await asyncio.sleep(0.1)` because `stopReason` can arrive either in the
  RPC response *or* an async `session/update` and the code cannot predict which
  [cultureagent.md → `clients/acp/agent_runner.py:447-455`].

### 1.6 Telemetry — OpenTelemetry

**Mechanism.** `CLAUDE_CODE_ENABLE_TELEMETRY=1` (note: *not* an `OTEL_*` var — the most common
way people fail to enable it) exports 34 named `claude_code.*` identifiers; traces need
`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` additionally [both gist files, 2nd-hand].

**States it can prove.** One, and it is the one we want most:
**`claude_code.tool.blocked_on_user`** — a vendor-emitted "the agent is stuck waiting for a
human," with no PTY involved.

**Latency.** Unmeasured by any researcher. OTel exporters batch by default, so this is
plausibly the *slowest* of the structured channels **(INFERRED — no researcher measured it)**.

**Platform coverage.** Env-var driven, platform-neutral in principle; unverified in practice.

**How it lies / fails.**
- Content is redacted by default; each field is separately opt-in (`OTEL_LOG_TOOL_DETAILS`
  etc.).
- **Claude Code strips all `OTEL_*` exporter vars from every subprocess it spawns, including
  hooks** — telemetry config does not reach grandchildren and must be re-set there.
- **Single-sourced.** Both gist files trace to the same upstream gist; neither researcher
  re-fetched `code.claude.com/docs/en/monitoring-usage` independently. The most attractive
  fact in the survey has the weakest independent support.

### 1.7 PTY-layer and terminal-emulator signals

**Mechanism.** Signals carried in the byte stream or exposed by the emulator itself, below
any text matching.

| Signal | What it proves | Where it fails |
|---|---|---|
| ASCII BEL (`\a`) | "agent says: your turn." VibeTunnel forces it on via `claude config set --global preferredNotifChannel terminal_bell` and catches it server-side [terminal-drivers.md → `web/src/server/services/bell-event-handler.ts:79`] | Depends on an internal config knob VibeTunnel's own docs describe as a fallback *because the primary notification broke*. The handler is "ultra-simple" with no correlation/dedup — a prior correlating version was removed |
| OSC 777 / `state:needs_attention` (kitty) | Same idea, standardized and exposed as a first-class window boolean via `kitten @ ls --match state:needs_attention` [terminal-drivers.md] | Only as good as the target's escape-sequence discipline — an agent that never emits BEL/OSC-777 never sets it |
| `pane:is_alt_screen_active()` (wezterm Lua) | "a fullscreen TUI currently owns this pane" — a cheap TUI-vs-shell discriminator no tmux tooling surfaced [terminal-drivers.md] | Coarse; says nothing about the TUI's internal state; an agent with a non-alt-screen fallback UI never sets it |
| OSC 133 semantic prompt markers (`A`/`B`/`C`/`D;<exit>`) | **The one genuinely non-heuristic readiness signal that exists** — "the shell is at a fresh prompt, exit code N" [expect-lineage.md → Contour/vtdn/wezterm specs, `microsoft/tui-test` `shell-use`] | Requires *shell* cooperation via injected rc hooks, and **goes silent for the entire time a fullscreen TUI owns the terminal** — precisely the interval our problem lives inside |
| OSC-2 window title | Cheap anchor for state matching; the convergent scraping fix names it explicitly | App-controlled and spoofable [terminal-drivers.md]; VibeTunnel injects into it itself |
| `terminalSequence` hook output (v2.1.141+) | A hook can push OSC 0/1/2, OSC 9 (incl. 9;4 taskbar progress), OSC 99, OSC 777, bare BEL through Claude Code's own write path **even with no controlling terminal** — "works on Windows where there is no /dev/tty" [gist-windows-sessions.md, 2nd-hand] | Allowlisted to sequences that cannot move the cursor or alter colour — **OSC 133 is excluded**. An out-of-band structured signal a nesting layer could parse |

**The PTY layer itself proves nothing.** Verified four ways independently: `pexpect`, winpty,
ConPTY, and wezterm's `portable-pty` all expose exactly a `Read`, a `Write`, and process
exit-status polling — `MasterPty::{resize, get_size, try_clone_reader, take_writer,
process_group_leader, as_raw_fd}` + `Child::{try_wait, wait, process_id, kill}`, read directly
from `pty/src/lib.rs` [expect-lineage.md]. There is no readiness concept on any platform. On
Windows specifically, **winpty *is* a screen-buffer poller by construction** — it starts a
hidden console and "polls the hidden console's screen buffer for changes and generates a
corresponding stream of output" [expect-lineage.md, winpty README verbatim]. Polling-based
screen inference is not a hack we invented; it is how the OS-level tooling works.

### 1.8 Process-tree and OS-level liveness

**Mechanism.** PID/process enumeration, exit codes, EOF on a child's stdout.

**States it can prove.** `dead` — and essentially only `dead`, but it proves it better than
anything else, because it is the only channel that survives the agent's own death.
- EOF on the stdout reader → `on_exit(returncode)` → crash recovery
  [cultureagent.md → `clients/codex/agent_runner.py:290-318`].
- Clean exit (code 0) → `agent_complete` webhook, no restart; nonzero → sliding crash window
  `MAX_CRASH_COUNT=3` / `CRASH_WINDOW_SECONDS=300` → circuit breaker, else
  `CRASH_RESTART_DELAY=5` s [cultureagent.md → `base_daemon.py:56-58,800-834`].
- **Turning a stall into a death, deliberately**: cultureagent's timeout paths `.terminate()`
  the subprocess so EOF fires and *one* recovery path handles both hang and crash
  [cultureagent.md → `clients/acp/agent_runner.py:480-501`, noted as a deliberate fix for
  their issue #349 where ACP timeouts previously never reached crash recovery].

**How it lies.** claude-flow's `swarm-monitor.sh` is the anti-pattern: `ps aux | grep` counts
divided by a magic constant (`agentic_flow_count / 2`, floor 1), an admitted estimate with no
liveness check, so a zombie inflates the count forever [tmux-orchestrators.md]. Process
existence is not agent liveness.

**Platform coverage.** Universal in concept; every implementation surveyed is POSIX-shaped.

### 1.9 Self-reported heartbeat and staleness watchdogs

**Mechanism.** The agent (or its wrapper) periodically asserts its own state; a supervisor
ages that assertion out.

**States it can prove.** `presumed_hung` — the silent-wedge case no other channel catches.
cultureagent: `presumed_hung = state in BUSY_STATES and (now - last_refresh) >
stale_after_seconds`, computed **server-side at read time**, `stale_after_seconds=90` vs
`heartbeat_interval_seconds=30`, with a fail-fast config assertion that stale must exceed the
heartbeat [cultureagent.md → `presence.md` Stale-Busy Watchdog; `culture_core/config.py:74-85`;
`culture_core/resource_view.py:96`].

**Latency.** Worst case = the stale threshold. 90 s in the only real implementation found.

**How it lies.** **Self-report is only as good as the reporter.** primeline's `heartbeat.sh`
externally polls only the orchestrator's own pane; every worker's state comes from a JSON file
the worker writes about itself, so a worker that crashes *before its first self-report* is
never flagged stuck at all, and one that hangs is caught only by a blunt 3×-interval staleness
heuristic [tmux-orchestrators.md → `_orchestrator/heartbeat.sh`, `collect_workers()`].
cultureagent's own design principle is the correction: *"transitions are driven only by
observable code boundaries — never by model self-report"*
[cultureagent.md → `presence_emitter.py:9-10`].

---

## 2. Comparison: projects × mechanism × states

Channel codes: **SS** screen-scrape · **AT** activity-timer/hash · **HK** harness hooks ·
**TR** transcript · **PR** protocol/stdio/SDK · **OT** telemetry · **PTY** PTY/emulator
signals · **PS** process/OS · **HB** self-report heartbeat.

| Project | Channel(s) | States distinguished | Key limit |
|---|---|---|---|
| **claude-squad** (8.2k★, Go) | SS + AT | `Running` (hash changed) · `Ready` (static, no known dialog literal) · collapsed auto-answered prompt branch · `Loading`/`Paused` (lifecycle, not detection) | No waiting-on-input state at all; native Windows broken (#275); AutoYes keystroke unreliable (#151) |
| **primeline claude-tmux-orchestration** (39★, Bash) | SS + HB | busy vs idle (orchestrator pane only, regex) · workers: free-text self-reported status + derived "stuck" from timestamp staleness | Single-capture decision, no debounce; workers never externally verified; failure modes inferred from source, no issues filed |
| **claude-flow** (67k★) | PS + HK | none in the busy/idle sense — process counts + tool-call boundaries | `ps\|grep`/2 heuristic; hooks POSIX-only, self-declared broken on native Windows |
| **VibeTunnel** (4.6k★) | AT + PTY (BEL) + SS (prompt regex, title only) | `starting\|running\|exited` × `isActive` boolean (5 s silence) | No permission/input-wait concept anywhere; BEL channel depends on a config knob known to have broken; **patches the Claude binary in place** to defeat an anti-debug check (`claude-patcher.ts`, 3 regex variants = evidence of prior breakage) |
| **Omnara** (2.7k★) | PR (SDK) | processing · waiting-on-user-input (`requires_user_input=True`) · waiting-on-permission (`permission_prompt_tool_name` MCP callback) — cleanest 3-way split in the survey | Headless SDK only; does not observe a TUI a human is also watching. *Note: read at code depth by tmux-orchestrators.md, at file-tree depth only by terminal-drivers.md which flagged it INFERRED — the deeper read stands.* |
| **happy-cli** (558★) | PR (Agent SDK) + HK (`SessionStart` forwarder) + TR | working · idle (`emitReadyIfIdle`, state predicate) · waiting-on-permission (`canCallTool`) · denied/approved/canceled — **richest taxonomy found** | Requires the target to ship an SDK; documented permission↔tool-call race patched with `delay(1000)`+retry |
| **cultureagent 0.13.0** (PyPI, 5 backends) | PR (SDK + JSON-RPC ×3 + in-process) + PS + HB | reachable: `idle → listening → thinking → (idle) → draining → offline`; plus server-side `presumed_hung`. `working` **defined and never emitted** | Never touches a TUI; permission dialogs *eliminated* (`bypassPermissions`, `approvalPolicy: never`, `approve_all`) rather than detected |
| **tmux-mcp** (298★) + ~8 forks | SS passthrough | none — "command pending / has result" via `TMUX_MCP_START`/`TMUX_MCP_DONE_<uuid>` sentinels | Sentinel works only for one-shot shell commands the server itself issued; structurally inapplicable to a TUI that never returns to a prompt. Needs `--shell-type` — an admission that completion detection is shell-syntax-dependent |
| **wezterm / kitty CLIs** | PTY + SS | none agent-specific; two primitives: `is_alt_screen_active()`, `state:needs_attention` | Pure terminal APIs; all interpretation is the caller's. **Both native on Windows/macOS/Linux — the most credible cross-platform base found** |
| **terminal-bench** (2.5k★) | PS (shell sentinel) + PR | "the shell command returned" — `<cmd>; tmux wait -S done`, polled under `timeout` | Deliberately avoids our problem: every agent adapter (Claude Code `-p`, `codex exec`, `goose run --recipe`) runs the agent **non-interactively**, so the TUI never renders |
| **pexpect / expect** | SS over raw stream | whatever regex the caller supplies; `TIMEOUT`/`EOF` sentinels (default 30 s) | No framework readiness signal by design. `spawn` unavailable on Windows; docs steer to pipe-based `PopenSpawn` or unmaintained `winpexpect`/`wexpect` |
| **winpty / ConPTY / portable-pty** | PTY plumbing | alive/exit-status only | No readiness concept on any platform. winpty *is* a screen-buffer differ internally |
| **PTY daemons** (psmux, rmux, Zellij, quil, oly, `ao pty-host`, OpenCode `/pty`) | PTY + native typed VT state | rmux `wait_for_text`/`snapshot()`; quil `MsgScreenshotPaneResp{Text,CursorX,CursorY}`; boo `wait --idle`/`peek --json`; convergent `status(id) → {alive,pid,exit_code,blocked_on_user?}` | All 2nd-hand via the gist. Headless verbs untested for **every** candidate; double-ConPTY nesting untested for every candidate; Zellij has no verified detached-start invocation at all |

---

## 3. Load-bearing conclusions the functional design must honor

**C1. Channel choice is determined by who spawned the agent, not by channel quality.**
If we spawn it, hooks + stream-json + transcript give near-complete state. If a human spawned
it, those channels are unavailable — hooks cannot be retrofitted [hooks-inventory.md],
stream-json cannot attach [three researchers], and on Windows late-attach into a foreign
console is not a working mechanism at all (`WriteConsoleInput` carries a Microsoft "no longer
part of our ecosystem roadmap" banner; the one production empirical attempt,
`pywinauto#492`, got attach success but `ReadConsoleOutputCharacter` returning ten spaces)
[gist-windows-sessions.md, 2nd-hand]. **The design must declare these as two products, or
declare own-from-birth as a hard precondition.**

**C2. Never gate on a single capture. Ever.** Every project that decided state from one
snapshot has a documented false-positive path: primeline's undebounced `>\s*$` idle regex,
the Kiro stale-redraw bug, VibeTunnel's 5 s timer. PITFALLS.md's "busy-indicator ABSENT + N
stable polls" is the field-standard mitigation, not a workaround
[expect-lineage.md's explicit judgement].

**C3. When scraping, anchor to bottom-N lines or the OSC title, never the whole buffer, and
add NOT-gates for stale artifacts.** Independently converged on by two unrelated projects
[both gist files, 2nd-hand from `cli-agent-orchestrator#182`].

**C4. Match busy indicators as a *set*, and version-pin it.** Claude Code's busy vocabulary
rotates (`Marinating`, `Clauding`, `Simmering`, …) and permission-dialog copy is an unversioned
UI string. Any literal-matching detector needs: a set not a substring, a declared
compatible-version range, and a self-test that fails loudly when no member of the set has been
seen in a session that clearly ran. Silent misdetection is the observed failure mode
[tmux-orchestrators.md, across three projects].

**C5. `dead` requires an out-of-band liveness check and must be two states, not one.** No hook
fires on SIGKILL on either CLI [hooks-inventory.md]. Adopt cultureagent's two-tier split:
hard-exit (EOF/exit code → `dead`) and soft-wedge (staleness → `presumed_hung`), with a
threshold strictly greater than the heartbeat interval, computed by the observer at read time
rather than asserted by the observed [cultureagent.md].

**C6. `working` must be defined as what we can actually prove, not as a wish.** Options with
evidence: tool-call brackets (`PreToolUse`→`PostToolUse`, proof of tool activity only), token
deltas (`--include-partial-messages`, the only true mid-generation signal), or screen change
(proves nothing about the agent). cultureagent defined `working` and never emitted it. Pick a
provable definition and name its blind spots in the doc.

**C7. Turn-end is not idle.** `Stop` carries `background_tasks`/`session_crons` specifically so
a consumer can tell "done" from "paused for async work," and `PreCompact`/`PostCompact` produce
long silent gaps that look identical to a hang. A detector that maps `Stop` → idle will
misclassify both [hooks-inventory.md].

**C8. There are at least three distinct "waiting" states, not two.** Tool permission
(`PermissionRequest`), MCP elicitation (`Elicitation`), and plain user input
(`Notification: agent_needs_input`, v2.1.198+). Our five-state model currently has two
waiting slots. Either merge deliberately and say so, or add the third
[hooks-inventory.md].

**C9. Bypass modes are the industrial escape hatch for permission-wait, and the design should
treat "waiting-on-permission" as *optional* when we control launch flags.** All five
cultureagent backends eliminate the state at the source (`bypassPermissions`,
`approvalPolicy: never` + unconditional auto-approve, `approve_all`) and contain zero
dialog-detection logic [cultureagent.md]. PITFALLS.md already flags bypass as a nested-agent
footgun — the tension is real and the design must state which side it picks and why.

**C10. Never patch the target binary, and prefer bytes-typed wires.** VibeTunnel's
`claude-patcher.ts` (regex-rewriting minified JS in the shipped Claude binary to defeat an
anti-debug `process.exit(1)`) is the single riskiest technique in the survey and already
carries three regex variants from prior breakage [terminal-drivers.md]. Relatedly, if we ever
consume a daemon's byte stream, prefer a byte-typed wire: psmux runs `String::from_utf8_lossy`
before escaping, so a multi-byte char split across two drains becomes U+FFFD permanently — and
Claude Code's own `✳` already broke quil's emulator [gist-windows-sessions.md, 2nd-hand].

**C11. Prefer one integration point per backend, at the "waiting on the model" boundary.**
cultureagent gets a uniform signal across five wildly different backend architectures by
wrapping exactly one thing — `presence_thinking()` around each backend's `harness.llm.call`
span — plus one work-dispatch edge. Edge-triggered, no-op on unchanged state, with `draining`
sticky so a late in-flight call cannot undo a shutdown signal
[cultureagent.md → `presence_emitter.py:118-129,232-253`]. That is a validated shape for our
adapter interface.

---

## 4. Open questions requiring empirical testing in our prototypes

Ordered by how much design they can kill.

**Q1. Can hooks be retrofitted onto a running Claude Code session?** hooks-inventory says no
(hooks are read from settings at session start). But Claude Code also ships a `ConfigChange`
hook that fires when a settings file changes mid-session, which implies *some* live re-read.
If a settings-file write mid-session activates a new hook, the entire "attach to a
human-launched session" branch changes character. **Test: start a session, write a hook,
trigger the event, check for the handler firing and for a `stop_hook_summary` record.**
*Kills or unlocks: the whole own-from-birth precondition (C1).*

**Q2. Do the driving/observation verbs work with no console attached (Windows Service /
Scheduled Task / headless caller)?** Untested for **every** PTY-daemon candidate; the upstream
gist rates it "2 hours, can kill the entire PTY branch" [gist-windows-sessions.md, gist Q23].
*Kills: any PTY-owning-daemon architecture on Windows.*

**Q3. Does `claude -p --output-format stream-json` produce byte-identical event shapes on
Windows and on macOS/Linux?** Flagged as the single load-bearing never-measured claim of the
no-PTY architecture. **Test: same prompt, same flags, diff the NDJSON on both.**
*Kills: cross-platform parity assumptions in the hooks/stream prototype.*

**Q4. Verify `claude_code.tool.blocked_on_user` first-hand.** The most attractive fact in the
survey is single-sourced through one gist. Enable `CLAUDE_CODE_ENABLE_TELEMETRY=1`, drive a
real permission prompt, confirm the identifier exists, confirm what it is (metric? span?
event?), and **measure its emit-to-observe latency** — no researcher measured it.
*Unlocks: a PTY-free waiting-on-permission signal.*

**Q5. Verify the hook-type taxonomy, especially `http`.** Five types with `http` on 13 events
is second-hand and un-corroborated by the researcher who read the primary doc (see 1.3). If
`http` hooks are real, our driver can be a long-lived endpoint instead of a poller —
architecturally different. *Unlocks or removes: push-based detection.*

**Q6. Read `operonlab/tmux-agent-status`'s `docs/detection-matrix.md` directly.** Named by
gist-middle-layer-map as "the single most on-topic artifact in the whole 395-retrieval sweep,"
cited but never extracted by anyone. It is a primary-source detection matrix for exactly our
problem. Also unread: `OEN-Tech/tmuxai`'s detection code, and the `kiro_cli` poller inside
`awslabs/cli-agent-orchestrator`.

**Q7. Characterize the two known false-idle holes empirically.** (a) A long silent `Bash`
tool call: does it produce *zero* screen change for its duration? For how long? (b) Compaction:
how long is the silent gap, and is it distinguishable from a hang from the screen alone?
Both are the specific inputs that break hash-diff and silence-timer detectors
[tmux-orchestrators.md, hooks-inventory.md]. *Determines: whether AT-class signals are usable
at all, or only as a corroborator.*

**Q8. Does Claude Code's interactive TUI use the alternate screen, and does it emit BEL /
OSC 777?** Both `pane:is_alt_screen_active()` and `state:needs_attention` are cheap,
cross-platform, emulator-native booleans — but both are only as good as the target's escape
discipline and neither was verified against real Claude Code output
[terminal-drivers.md, explicitly flagged as assumed-from-spec]. *Unlocks: two free coarse
signals on the only cross-platform-native capture surfaces we found.*

**Q9. Measure per-channel latency on one machine, one prompt.** No researcher produced a
comparative measurement. Instrument the same turn through hooks, transcript-tail, stream-json,
OTel, and a 500 ms screen poll, and record time-to-detect for each transition.
*Determines: the corroboration hierarchy in the detector's fusion logic.*

**Q10. Does the `PreToolUse` `"defer"` + `claude -p --resume <session-id>` flow actually
work?** Documented, never exercised [hooks-inventory.md]. It is the only documented path to
"pause a permission decision, collect an answer through our own UI, resume" — i.e. driving
without bypass mode. *Unlocks: permission-driving without the C9 bypass tradeoff.*

**Q11. Is the transcript JSONL a tree on macOS/Linux too?** The subagent-sidecar tree
structure was verified on Windows 11 build 26200 [gist-windows-sessions.md, 2nd-hand]; the
live inspection done on this machine [hooks-inventory.md] found flat session files and did not
report subagent subdirectories. Not necessarily a conflict — possibly a version or
subagent-usage difference — but **the two researchers describe different on-disk layouts and
this needs one command to settle.**

---

## 5. Conflicts and single-source flags

| Item | Status |
|---|---|
| Transcript JSONL layout: tree with subagent sidecars vs flat session files | **Conflict, unresolved.** gist-windows-sessions (2nd-hand, Windows) vs hooks-inventory (first-hand, macOS). See Q11 |
| Hooks retrofittable onto a live session | **Tension.** hooks-inventory: no. `ConfigChange` hook's existence implies partial live re-read. See Q1 |
| Hook types incl. `http` on 13 events | **Single-sourced, un-corroborated** by the researcher who read the primary doc. See Q5 |
| `claude_code.tool.blocked_on_user` | **Single-sourced.** Two researcher files, one upstream gist, zero independent fetches. See Q4 |
| `awslabs/cli-agent-orchestrator#182` stale-redraw bug | **Single-sourced** the same way — appears twice, derives once. The *failure class* is independently corroborated by our own PITFALLS.md, so the conclusion is safe even though the citation is not doubled |
| Omnara's mechanism | **Depth conflict, resolved.** terminal-drivers.md read file names only and self-flagged INFERRED; tmux-orchestrators.md read `src/integrations/headless/claude_code.py`. The code-level read stands |
| VibeTunnel `activity-status.ts` 5 s silence timer | **Independently cross-read by two researchers, agreeing.** The most solidly established mechanism fact in the survey |
| `agentculture/cultureagent` as a git repo | **Brief was wrong.** It is a PyPI-only wheel (`cultureagent==0.13.0`); no public git history exists. Source read from the installed wheel [cultureagent.md] |
| `tmux-composer`, Piebald-AI `agent-farm` | **Do not exist** as agent-orchestration projects; ruled out by direct enumeration [tmux-orchestrators.md] |

---

## Sources

Primary inputs are the seven researcher files in this directory; each carries its own full
`## Sources` section with file:line and URL citations. Highest-value primary sources named
across them, for follow-up:

- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks) — full event enumeration; scraped copy under `.research/prior-art-search/`
- [Claude Code headless mode](https://docs.claude.com/en/docs/claude-code/headless) — `stream-json`, `--include-hook-events`, `--include-partial-messages`
- [Claude Code monitoring/telemetry](https://code.claude.com/docs/en/monitoring-usage) — the 34 `claude_code.*` identifiers incl. `tool.blocked_on_user` (**not independently fetched — see Q4**)
- [Codex hooks](https://developers.openai.com/codex/hooks) — Codex event set, trust model, tool-coverage table
- [operonlab/tmux-agent-status `docs/detection-matrix.md`](https://github.com/operonlab/tmux-agent-status/blob/main/docs/detection-matrix.md) — **most on-topic unread artifact in the entire survey (Q6)**
- [awslabs/cli-agent-orchestrator#182](https://github.com/awslabs/cli-agent-orchestrator/issues/182) — the stale-redraw bug in the reporter's own words
- [anthropics/claude-code#24365](https://github.com/anthropics/claude-code/issues/24365) and #6686 — native network-attach declined twice as `not_planned`
- [pywinauto#492](https://github.com/pywinauto/pywinauto/issues/492) — the empirical Windows late-attach failure
- [smtg-ai/claude-squad](https://github.com/smtg-ai/claude-squad) `session/tmux/tmux.go` — the reference hash-diff + literal-match implementation
- [slopus/happy-cli](https://github.com/slopus/happy-cli) `src/claude/utils/permissionHandler.ts` — the richest state taxonomy found
- [omnara-ai/omnara](https://github.com/omnara-ai/omnara) `src/integrations/headless/claude_code.py` — `permission_prompt_tool_name` as a structural permission signal
- [harbor-framework/terminal-bench](https://github.com/harbor-framework/terminal-bench) `terminal_bench/terminal/tmux_session.py` — the `tmux wait -S done` sentinel
- [wez/wezterm](https://github.com/wez/wezterm) `pty/src/lib.rs` — proof the PTY layer exposes no readiness primitive
- [rprichard/winpty](https://github.com/rprichard/winpty) — README's screen-buffer-polling admission
- [OSC 133 spec (Contour)](https://contour-terminal.org/vt-extensions/osc-133-shell-integration/) — the one non-heuristic readiness signal, and its TUI-shaped blind spot
