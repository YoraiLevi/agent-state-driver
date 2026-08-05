# Event-channel inventory: hooks, transcripts, and stream-json as alternatives to screen-scraping

Scope: enumerate every non-screen-scraping channel that can signal the state of an
interactive CLI AI agent (working / idle / waiting-on-permission / waiting-on-input / dead),
for Claude Code and OpenAI Codex CLI. Grounds `agent-state-driver`'s functional design.

## Verdict

- **`Notification` (Claude Code) is the single best "waiting" signal**, but only from
  v2.1.198+: `notification_type` includes `agent_needs_input` (permission/input wait) and
  `agent_completed`. Before that version there is no dedicated "I am now waiting" event —
  you infer it from `Stop` (turn ended) plus absence of further activity.
- **`PermissionRequest` fires exactly at the moment a permission dialog is about to show**,
  with `tool_name`/`tool_input` — this is a provable, zero-latency "waiting-on-permission"
  signal for both Claude Code and Codex, and both let a hook auto-answer it (skipping the
  dialog) or merely observe it (`decision` omitted) to detect without interfering.
- **`Stop`/`SubagentStop` mark turn-end but do NOT mean "idle forever"**: Claude Code's
  `Stop` input carries `background_tasks` and `session_crons` arrays (v2.1.145+) precisely
  so a hook can distinguish "done" from "paused, waiting on background work to wake it."
  Miss this and a driver will misclassify a session with in-flight async work as dead/idle.
  Codex's `Stop` hook lacks this field — Codex has no visible background-task registry.
  (INFERRED from absence in the docs' Stop input table.)
- **Hooks alone cannot see "working" (mid-generation, no tool call yet)** — no hook fires
  while the model is only streaming text; `MessageDisplay` fires on text-render batches but
  is explicitly "display-only" (doesn't reach the model/transcript) and only in Claude Code,
  not Codex. `stream-json` (`--include-partial-messages`) is the only channel that sees
  token-by-token progress, and only from a process you spawned with `-p`, not an
  already-running interactive session.
- **The transcript JSONL is a durable log, not a live event bus**: it is written to as the
  session progresses so it CAN be tailed (`tail -f`), but every "state" fact you'd want
  (turn duration, compaction, subagent stop) is already better exposed as a first-class hook
  event with a stable schema — the JSONL's `type`/`subtype` shapes are explicitly
  undocumented and the docs warn "the transcript format isn't a stable interface" (Codex)
  and imply the same for Claude Code (no schema reference exists; only `/docs/hooks` is
  documented).
- **Codex's hook surface is a near-1:1 clone of Claude Code's**, missing only:
  `MessageDisplay`, `Notification`, `PreCompact`/`PostCompact` blocking nuance is present but
  `background_tasks`/`session_crons` are absent, and only `type: "command"` hooks work today
  (`prompt`/`agent` types are parsed but skipped). Codex's `notify` config key is a *third*,
  older, narrower channel: fires only on `agent-turn-complete`, i.e. functionally a same-info
  subset of `Stop`.
- **`claude -p --output-format stream-json --include-hook-events` is the one channel that
  merges hook events and generation events into a single ordered stream** — verified live on
  this machine (see Mechanism 4) — making it the strongest channel for a driver that itself
  launches the agent process, but it is useless for attaching to an already-running
  interactive `claude` session, since hook events there go to `~/.claude/settings.json`
  hook processes and the transcript file, not to any stream a separate process can subscribe to.

## Mechanisms found

### 1. Claude Code hooks (full event enumeration)

Source: `https://docs.claude.com/en/docs/claude-code/hooks` (canonical URL resolves to
`https://code.claude.com/docs/en/hooks`), scraped 2026-08-05, saved to
`.research/prior-art-search/20260805_193943_680138_web-scraper_..._c1102c8c.md`.

**Cadence** (per the doc's own framing): once per session (`SessionStart`, `SessionEnd`);
once per turn (`UserPromptSubmit`, `Stop`, `StopFailure`); once per tool call
(`PreToolUse`, `PostToolUse`, except `EndConversation`).

**Full event list, one row per event, with what it proves and where it fails as a state signal:**

| Event | Fires when | Key payload fields | State it proves | Where it lies/fails |
|---|---|---|---|---|
| `SessionStart` | new session or resume; `source` = `startup`/`resume`/`clear`/`compact` | `source`, optional `model`, `agent_type`, `session_title` | session boundary | fires again on every `--resume`, so it is not a "process just launched" signal in a driver that reattaches |
| `Setup` | only `--init-only`, or `--init`/`--maintenance` with `-p` | `trigger`: `init`/`maintenance` | one-time provisioning ran | never fires on normal interactive startup — useless for live state |
| `InstructionsLoaded` | CLAUDE.md / rules file loaded, at start or lazily | `load_reason` | context load, not agent state | not a state signal at all; observability only |
| `UserPromptSubmit` | user submits a prompt, before Claude processes it | `prompt` | "about to start working" | fires even for prompts that get blocked; doesn't confirm the model actually started generating |
| `UserPromptExpansion` | typed `/skill` or MCP prompt command expands | `expansion_type`, `command_name`, `command_args` | slash-command dispatch | covers only the direct-invoke path PreToolUse misses; not a general "start of turn" signal |
| `MessageDisplay` | assistant text streams to screen, per render batch | `delta`, `index`, `final` | mid-generation progress ("working") | **display-only** — doesn't reach the transcript or the model; the only channel that sees token-level progress from a hook, but its output can't be read back by an external driver except by intercepting the hook's own stdout/stderr |
| `PreToolUse` | after Claude builds tool params, before the call runs | `tool_name`, `tool_input`, `tool_use_id` | "about to call a tool" (still working) | fires for tool calls that will be silently denied — doesn't itself mean the tool ran |
| `PermissionRequest` | Claude Code is about to show a permission dialog (or would auto-deny in a context that can't prompt) | `tool_name`, `tool_input`, `permission_suggestions` | **exact waiting-on-permission instant** | doesn't fire for calls that don't need permission (bypass mode, already-allowed); if no hook decides, denies calls that "can't prompt" (e.g. background subagents in `-p`), so a passive hook here can't distinguish "denied because no dialog possible" from "waiting for the human" without checking session mode |
| `PostToolUse` | tool completes successfully | `tool_input`, `tool_response` | tool finished, back to "working" | doesn't fire on failure — see next row |
| `PostToolUseFailure` | tool that started executing fails | `error`, `is_interrupt` | tool errored | doesn't fire for calls rejected before execution (bad name, schema validation, permission denial) |
| `PostToolBatch` | once per resolved batch of parallel tool calls, before next model call | `tool_calls[]` | batch-level "still working" | no per-tool granularity; only fires when a batch completes, not per call |
| `PermissionDenied` | the **auto-mode classifier** denies a call | `tool_name`, `tool_input`, `reason` | classifier-driven denial (not human denial) | only fires in auto mode; a manual dialog denial, a `PreToolUse` hook block, or a deny-rule match do NOT fire this event — a driver relying on it will miss most denials |
| `Notification` | Claude Code sends any notification | `message`, `title`, `notification_type` | **general-purpose "tell the user something" channel**, incl. `agent_needs_input` and `agent_completed` (**v2.1.198+ only**) | on versions before 2.1.198 there is no `agent_needs_input`/`agent_completed` — the event exists but without the two most useful state-inference types |
| `SubagentStart` | subagent spawned via Agent tool | `agent_id`, `agent_type` | subagent began | matcher can be spoofed by plugin-scoped names (`my-plugin:reviewer`) needing anchored regex |
| `SubagentStop` | subagent finished responding | `stop_hook_active`, `agent_id`, `last_assistant_message`, `background_tasks`, `session_crons` | subagent turn ended | `background_tasks`/`session_crons` here are the **parent session's**, not the subagent's — can't tell if the *subagent itself* left async work behind |
| `TaskCreated` | via `TaskCreate` tool | `task_id`, `task_subject` | task-list state change | orchestration bookkeeping, not agent liveness |
| `TaskCompleted` | via `TaskUpdate` tool, or teammate finishing with open tasks | `task_id`, `task_subject` | task-list state change | same caveat |
| `Stop` | **main agent finished responding** (not on user interrupt — that's silent) | `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons` | **turn-end / candidate-idle**, and (v2.1.145+) distinguishes "fully done" from "paused for background work" via the two arrays | Claude Code caps auto-continuation at "8 consecutive blocks" — a hook that keeps returning `block` eventually gets overridden, so `Stop` firing repeatedly isn't proof of true completion until that cap is hit; also **does not fire on user Ctrl-C interrupt**, so a killed turn looks like silence, not a `Stop` event |
| `StopFailure` | turn ends due to an API error (rate limit, auth) instead of normal Stop | `error`, `error_details`, `last_assistant_message` | **agent died from an API-level failure**, distinct from a clean stop | output/exit code ignored — pure observability, can't be used to react |
| `TeammateIdle` | an agent-team teammate about to go idle after its turn | `teammate_name`, `team_name` | idle-transition for multi-agent teams specifically | not applicable to a single-agent session |
| `ConfigChange` | a settings/policy/skill file changes mid-session | `source`, `file_path` | config drift, not agent state | — |
| `CwdChanged` | `cd` executed | `old_cwd`, `new_cwd` | side info | — |
| `DirectoryAdded` | `/add-dir` or SDK `register_repo_root` | `directory`, `source` | side info | — |
| `FileChanged` | a *watched* file changes on disk | `file_path`, `event` | side info | matcher literally must name the file; not a generic FS watcher |
| `WorktreeCreate`/`WorktreeRemove` | worktree lifecycle | `name` / `worktree_path` | side info | — |
| `PreCompact`/`PostCompact` | before/after context compaction | `trigger` (`manual`/`auto`), `custom_instructions` / `compact_summary` | **agent paused for compaction — looks like "working" but is actually internal housekeeping**, can take many seconds | a driver watching only tool activity will see a long gap here with no tool calls and could misclassify as idle/hung; compaction is also visible in the transcript as `system`/`compact_boundary` (verified, see Mechanism 2) |
| `SessionEnd` | session ends; `reason` field (clear/logout/exit/etc.) | `reason` | **process is about to exit or has exited its logical session** | fires on `/clear` too, which is not process death — must not conflate `SessionEnd` with "process is dead" |
| `Elicitation`/`ElicitationResult` | an MCP server requests user input mid-task, and the response | `mcp_server_name`, `message`, `requested_schema` / `action`, `content` | **a THIRD kind of "waiting for human"**, distinct from tool permission — an MCP tool asking a question | easy to miss if a driver only watches `PermissionRequest`/`Notification`; this is a separate dialog type entirely |

**Turn-duration signal found directly in the transcript, not the hooks doc** — see Mechanism 2.

**Latency**: hooks are synchronous subprocess spawns in the Claude Code process itself (for
`type: "command"`) — they fire at the exact moment of the lifecycle point, so latency is
sub-millisecond dispatch plus your handler's own startup cost (fork/exec, ~5-20ms typical for
a shell script). HTTP hooks add network RTT. This makes hooks the lowest-latency channel of
the four investigated here, categorically faster than polling a transcript file or
screen-scraping a render.

**Where hooks fail structurally, regardless of event choice:**
- They require the target Claude Code session to have been launched with the hook already
  registered in a settings file — you cannot retrofit hooks onto an already-running,
  externally-launched session.
- `disableAllHooks: true` and workspace-trust dialogs can silently prevent a hook from ever
  running, with no channel telling the outside driver "your hook was never installed."
- No hook exists for "process crashed / was SIGKILLed" — `SessionEnd` requires a graceful
  exit path; a hard kill leaves no event at all. (INFERRED: the doc lists `SessionEnd`
  reasons but a killed process cannot run a hook to report its own death.)

### 2. Transcript JSONL (`~/.claude/projects/<dir>/<session>.jsonl`)

Inspected live on this machine: `~/.claude/projects/-Users-m5air-source-project-proposals/`,
8 session files, one with 650 lines across `mode`, `permission-mode`, `bridge-session`,
`file-history-snapshot`, `user`, `attachment`, `assistant`, `last-prompt`, `system`,
`ai-title` top-level `type` values (counted with `python3 -c "..."` over every line, see
transcript at `0b76c6fd-fb85-476c-b269-a44af67749bd.jsonl`).

**Top-level record `type` values found, one file each:**

- **`user`** — has `message.content` (string or content-block array for tool_result),
  `promptId`, `uuid`, `parentUuid` (builds the turn tree), `timestamp`, `cwd`, `version`,
  `gitBranch`. A `tool_result` content block carries `tool_use_id` and `content` (string).
- **`assistant`** — `message.content` is an array of blocks: `text`, `thinking` (with
  `signature`), `tool_use` (`id`, `name`, `input`, `caller.type`). `message.usage` carries
  full token accounting including `iterations[]` (per-model-round breakdown) — useful for
  cost tracking, not state.
- **`system`**, distinguished by `subtype` (only found by scanning *all 8* session files —
  a single file does not exhibit every subtype):
  - `turn_duration` — `durationMs`, `messageCount` — **fires once at turn end**,
    functionally the transcript-side mirror of the `Stop` hook but with wall-clock duration
    baked in. This is the cleanest "turn just ended, here's how long it took" signal in the
    file itself.
  - `stop_hook_summary` — `hookCount`, `hookInfos[].command`/`durationMs`, `hookErrors[]`,
    `preventedContinuation`, `hasOutput`, `level`. **Proves whether a Stop hook actually ran
    and whether it errored** — directly useful for verifying a driver's own hook fired (a
    hook that silently failed to install would never produce this record).
  - `compact_boundary` — `compactMetadata.trigger` (`manual`/`auto`), `preTokens`,
    `postTokens`, `cumulativeDroppedTokens`, `durationMs`, `preservedSegment`/`preservedMessages`
    (UUID ranges kept). Confirms the `PreCompact`/`PostCompact` gap noted above: this is where
    a long silent gap in tool activity gets its explanation.
  - `local_command` — `content` (e.g. `<local-command-stdout>...</local-command-stdout>`),
    fires for slash-commands like `/compact` run by the user directly.
- **`mode`** / **`permission-mode`** — single-field session-level records
  (`mode: "normal"`, `permissionMode: "default"`) — snapshot the operating mode at a point in
  time, not an event about a specific action.
- **`bridge-session`** — `bridgeSessionId`, `lastSequenceNum` — ties this local session to a
  Remote Control / cloud bridge session (relevant if driving via `claude code on the web`,
  not local CLI).
- **`file-history-snapshot`** — `trackedFileBackups`, `timestamp` — file edit checkpoint,
  not agent state.
- **`attachment`** — observed subtype `deferred_tools_delta` with `addedNames`/`removedNames`
  — records tool-list changes (e.g. deferred-tool loading), not conversation state.
- **`last-prompt`** / **`ai-title`** — UI convenience metadata (resume-picker label,
  auto-generated session title).

**What this channel proves that hooks don't**: it is the *only* channel inspected here that
persists `turn_duration` (wall-clock) and `stop_hook_summary` (hook execution proof) without
any hook configuration required — these `system` records appear to be written by Claude Code
itself, not by user-configured hooks (INFERRED: no corresponding hook event is documented for
`turn_duration`; it looks like an internal instrumentation record).

**Turn-boundary structure**: `parentUuid` on `user`/`assistant` records forms a linked list —
walking from a `user` record's `uuid` forward through `assistant` records whose `parentUuid`
chains back to it, until the next `user` record, delimits one turn. Combined with the
`turn_duration` system record's `messageCount`, a consumer can validate it walked the correct
span.

**Latency and failure modes**:
- This is a file, not a push channel — a driver must `tail -f` or poll `stat`'s mtime/size.
  Latency is therefore bounded by polling interval or filesystem-event-notification latency
  (inotify/FSEvents/ReadDirectoryChangesW), not by Claude Code itself.
- No documented schema exists for this file (confirmed: neither `docs.claude.com` nor
  `code.claude.com` publish a transcript JSONL reference — only the hooks and headless-mode
  docs are canonical). Every field name and `type`/`subtype` value here was **reverse-engineered
  from a live file on this machine**, so this is Claude-Code-version-dependent and could
  silently change format between releases with no deprecation notice.
- The file can be resumed/forked (`forkedFrom` field observed on a `local_command` record) —
  a driver walking the file by line number alone, without tracking `sessionId`/`forkedFrom`,
  could misattribute records from a forked session to the wrong logical conversation.

### 3. OpenAI Codex CLI hooks and `notify`

Sources: `https://raw.githubusercontent.com/openai/codex/main/docs/config.md` (fetched via
`curl`, confirms Codex's own docs now redirect to `developers.openai.com`),
`https://developers.openai.com/codex/config-advanced` and
`.../codex/config-reference` and `.../codex/hooks` (all scraped 2026-08-05, saved under
`.research/prior-art-search/20260805_1940*`).

Codex has **two independent channels**, not one:

**(a) `notify` config key** — `notify = ["python3", "/path/to/notify.py"]` in
`~/.codex/config.toml`. Invokes an external program with a single JSON argument
(`sys.argv[1]`, not stdin) on **currently only `agent-turn-complete`**. Payload fields:
`type`, `thread-id`, `turn-id`, `cwd`, `input-messages`, `last-assistant-message`. This is
explicitly narrower than Claude Code's `Stop` hook — one event type only, no permission-wait
signal, no tool-level events. Distinct from `tui.notifications` (built-in TUI toast, can
filter by `agent-turn-complete`/`approval-requested`) and `tui.notification_method`
(`auto`/`osc9`/`bel` terminal escape codes) — three different, overlapping mechanisms for
"tell someone something happened," none of which is a general event bus.

**(b) Lifecycle hooks** (`hooks.json` or inline `[hooks]` in `config.toml`) — structurally
near-identical to Claude Code's hook system (same three-level nesting: event → matcher group
→ handler array; same `type: "command"` shape). Confirmed events (from
`.../codex/hooks` page, "Hooks run at different points" table plus per-event sections):

| Event | Cadence | Matches Claude Code's | Codex-specific notes |
|---|---|---|---|
| `SessionStart` | once/session | `SessionStart` | `source`: `startup`/`resume`/`clear`/`compact` |
| `SessionEnd` | once/session | `SessionEnd` | doesn't run for subagents; fires after 30 min idle-and-unopened, not just on exit |
| `SubagentStart`/`SubagentStop` | per subagent | same | `SubagentStop` input lacks any `background_tasks` equivalent — no way to see in-flight async work |
| `UserPromptSubmit` | per turn | same | matcher not supported (ignored if set) |
| `PreToolUse`/`PostToolUse` | per tool call | same | covers `Bash`, `apply_patch` (aliased to `Edit`/`Write`), MCP tools, and other local function tools incl. `update_plan`, `spawn_agent`; explicitly **excludes hosted tools like WebSearch** — "these don't use the local function-tool hook path" |
| `PermissionRequest` | on approval-needed calls | same | matches `tool_name`; same allow/deny shape (`hookSpecificOutput.decision.behavior`); **doesn't fire for calls that don't need approval** — same blind spot as Claude Code |
| `PreCompact`/`PostCompact` | around compaction | same | — |
| `Stop` | per turn | same | `decision: "block"` here **creates a new continuation prompt from the reason text**, acting as an injected user turn — a materially different mechanism from Claude Code's "keep going" block, worth flagging for anyone porting a Stop-hook driver between the two CLIs |

**Not present in Codex, present in Claude Code**: `MessageDisplay`, `Notification`
(the `agent_needs_input`/`agent_completed` types), `PermissionDenied` (classifier-specific),
`TeammateIdle`, `ConfigChange`, `CwdChanged`, `FileChanged`, `WorktreeCreate/Remove`,
`Elicitation`/`ElicitationResult`, `TaskCreated`/`TaskCompleted`, `InstructionsLoaded`,
`UserPromptExpansion`, `StopFailure`, `PostToolUseFailure`, `PostToolBatch`.

**Critical operational caveat unique to Codex**: hooks require **explicit user trust** —
"Codex requires you to review and trust the exact hook definition" via `/hooks`, hashed
against the hook's current content; a changed hook is re-flagged for review. A driver that
programmatically writes a new hook into `hooks.json` will not have it actually run until a
human (or `--dangerously-bypass-hook-trust`) trusts it — this is a deployment blocker Claude
Code does not have (Claude Code hooks run once configured, no separate trust step, aside from
the general workspace-trust dialog for hooks defined inside skills/subagents).

**Only `type: "command"` hooks work today** — Codex parses but silently skips `prompt` and
`agent` hook types, and the `async` flag is parsed but "asynchronous command hooks aren't
supported yet" — meaning every Codex hook blocks the agent loop while it runs, unlike Claude
Code's `async: true` command hooks.

### 4. `claude -p --output-format stream-json --include-hook-events` as a unified channel

**Verified live on this machine** (macOS, Claude Code v2.1.222, no `--bare`):

```
claude -p "reply with exactly: hi" --output-format stream-json --include-hook-events --verbose
```

produced, in order, on stdout:
1. `{"type":"rate_limit_event", ...}`
2. `{"type":"system","subtype":"hook_started","hook_id":"...","hook_name":"UserPromptSubmit","hook_event":"UserPromptSubmit",...}`
3. `{"type":"system","subtype":"hook_response","hook_id":"...","hook_name":"UserPromptSubmit","output":"","stdout":"","stderr":"","exit_code":0,"outcome":"success",...}`
4. `{"type":"system","subtype":"init","cwd":"/private/tmp","tools":[...],"mcp_servers":[...],"model":"...","permissionMode":"default","slash_commands":[...],"capabilities":[...],...}`
5. `{"type":"assistant","message":{...,"content":[{"type":"text","text":"hi"}],...}}`

(Command was killed at 15s to bound cost before a `result` event and any `Stop`
`hook_started`/`hook_response` pair could print — those are documented but not captured live
in this run.)

This confirms, per the docs (`.research/prior-art-search/20260805_194048_537269_..._headless_1db7c751.md`):
- `system/init` is the first event unless startup events (`hook_started`/`hook_progress`/
  `hook_response` for `SessionStart`/`Setup` hooks) precede it — matches what was captured.
- Every configured hook, not just `SessionStart`, emits `hook_started` → (optional
  `hook_progress`) → `hook_response` triplets **inline in the same stream** as generation
  events, when `--include-hook-events` is set. This means a single consumer reading this one
  stream sees both "the model is now generating" (`assistant` events, refined further by
  `--include-partial-messages` for token deltas) and "a hook just fired for event X" without
  needing a second channel.
- `system/api_retry` fires before an API retry — a distinct "still working, just slow"
  signal not available from any hook.
- Subagent messages carry `parent_tool_use_id`; `--forward-subagent-text` (or
  `CLAUDE_CODE_FORWARD_SUBAGENT_TEXT`) is required to see subagent text/thinking, not just
  its tool calls, v2.1.211+.

**What it proves**: every state a hook can prove (permission wait, stop, tool activity), PLUS
mid-generation token progress via `--include-partial-messages`, PLUS retry-in-progress — the
most complete single channel found.

**What it cannot see / structural limits**:
- It only exists for a process **you spawned** with `-p`. It cannot attach to an
  already-running interactive `claude` TUI session — there is no equivalent "attach and
  stream" mode documented; the interactive TUI does not expose this stream externally.
- `-p` is fundamentally headless/non-interactive: `AskUserQuestion` and `ExitPlanMode` "require
  user interaction and normally block in non-interactive mode" — so if you need a state
  detector that also lets a *human* answer permission dialogs interactively, `-p` is the wrong
  process mode; you'd be back to hooks/transcript-watching on an interactive session, or to
  the `PreToolUse` `"defer"` decision (documented, not exercised live here) that lets a
  wrapping process pause the tool call, collect an answer via its own UI, and resume with
  `claude -p --resume <session-id>`.
- Latency for this channel is bounded by process-spawn + first-token latency for the initial
  event, then streams live thereafter — comparable to hooks for hook-derived events, and
  strictly better than transcript-polling for text generation, since `--include-partial-messages`
  has no file-write/poll step in between.

## Sources

- [Hooks reference — Claude Code Docs](https://docs.claude.com/en/docs/claude-code/hooks) (canonicalizes to `https://code.claude.com/docs/en/hooks`) — full event enumeration, JSON schemas, exit-code semantics. Scraped copy: `.research/prior-art-search/20260805_193943_680138_web-scraper_https___docs.claude.com_en_docs_claude-code_hooks_c1102c8c.md`
- [Headless mode / `claude -p` — Claude Code Docs](https://docs.claude.com/en/docs/claude-code/headless) — `--output-format stream-json`, `--include-hook-events`, `--include-partial-messages`, subagent forwarding. Scraped copy: `.research/prior-art-search/20260805_194048_537269_web-scraper_https___docs.claude.com_en_docs_claude-code_headless_1db7c751.md`
- `claude --help` (local, v2.1.222) — confirms `--include-hook-events` flag text verbatim.
- Live transcript files on this machine: `~/.claude/projects/-Users-m5air-source-project-proposals/*.jsonl` (8 sessions inspected for `type`/`subtype` coverage).
- Live `claude -p --output-format stream-json --include-hook-events` run in `/tmp` (this session, 2026-08-05) — raw output captured at `/tmp/claude_stream_test.jsonl`.
- [Codex `config.md` (raw, main branch)](https://raw.githubusercontent.com/openai/codex/main/docs/config.md) — points to `developers.openai.com` as the current docs home; confirms `[hooks]`/`requirements.toml` `allow_managed_hooks_only`.
- [Codex config-advanced — developers.openai.com](https://developers.openai.com/codex/config-advanced) — `notify`, `tui.notifications`, hook file locations. Scraped copy: `.research/prior-art-search/20260805_194026_324353_web-scraper_..._config-advanced_820d8647.md`
- [Codex config-reference — developers.openai.com](https://developers.openai.com/codex/config-reference) — full config key table incl. `notify` type. Scraped copy: `.research/prior-art-search/20260805_194029_293733_web-scraper_..._config-reference_d8077255.md`
- [Codex hooks — developers.openai.com (learn.chatgpt.com/docs/hooks)](https://developers.openai.com/codex/hooks) — full Codex hook event enumeration, trust model, matcher table, tool coverage table. Scraped copy: `.research/prior-art-search/20260805_194041_179601_web-scraper_..._hooks_900a3774.md`
- `curl -s https://api.github.com/repos/openai/codex/contents/docs` — confirms current doc file list in the Codex repo (config.md, exec.md, etc. are now thin redirects to developers.openai.com).
