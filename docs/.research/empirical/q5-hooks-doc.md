# Q5 — Hook types, ConfigChange semantics, terminalSequence allowlist

## Question

For the push-based-detection design decision:
1. What hook TYPES does Claude Code support per the primary doc? Does an `"http"` hook type
   exist, on which events, and with what semantics (long-lived endpoint vs per-event POST)?
2. `ConfigChange` hook exact semantics — does a mid-session settings write take effect for
   OTHER hooks?
3. `terminalSequence` hook output (v2.1.141+) — is OSC 133 really excluded from its allowlist?

## Method

No live tmux session used (doc-research question, not a driving question). Exact commands run:

```bash
mkdir -p /Users/m5air/source/fable/agent-state-driver/docs/.research/empirical
uv run /Users/m5air/.claude/skills/web-scraper/scripts/scrape.py \
  "https://code.claude.com/docs/en/hooks" --links --md
# -> .research/prior-art-search/20260805_203654_164874_web-scraper_..._b27ebd76.md (102,150 chars)

claude --help          # local flag cross-check
claude --version       # -> 2.1.222 (Claude Code)
grep -in 'hook' /Users/m5air/.claude/cache/changelog.md   # local changelog cross-check
```

Then grepped/read the scraped markdown for `http`, `configchange`, `terminalsequence`,
`osc 133`, `allowlist`, and cross-referenced hits against `claude --help` output and
`~/.claude/cache/changelog.md`.

Primary source scraped: `https://code.claude.com/docs/en/hooks` (single page — this doc
covers hook types, ConfigChange, and terminalSequence together; no separate reference
subpage was linked for these three topics, confirmed by inspecting the `--links` output).

## Observed

### 1. Hook types — five types exist, `http` is one of them

Doc frontmatter description (verbatim):

> "Reference for Claude Code hook events, configuration schema, JSON input/output formats,
> exit codes, async hooks, HTTP hooks, prompt hooks, and MCP tool hooks."

Verbatim, on hook handler types:

> "Each object in the inner `hooks` array is a hook handler: the shell command, HTTP endpoint,
> MCP tool, LLM prompt, or agent that runs when the matcher matches. There are five types:"

Verbatim, from the `/hooks` menu description:

> "The menu displays all five hook types: `command`, `prompt`, `agent`, `http`, and `mcp_tool`."

**`http` semantics — per-event POST, NOT a long-lived endpoint:**

> "Claude Code runs hooks at specific points during a session. When an event fires and a
> matcher matches, Claude Code passes JSON context about the event to your hook handler.
> For command hooks, input arrives on stdin. For HTTP hooks, it arrives as the POST request
> body."

> "Claude Code sends the hook's JSON input as the POST request body with
> `Content-Type: application/json`. The response body uses the same JSON output format as
> command hooks. Error handling differs from command hooks: non-2xx responses, connection
> failures, and timeouts all produce non-blocking errors that allow execution to continue.
> To block a tool call or deny a permission, return a 2xx response with a JSON body
> containing `decision: "block"` or a `hookSpecificOutput` with `permissionDecision: "deny"`."

HTTP response handling (verbatim):

> "HTTP hooks use HTTP status codes and response bodies instead of exit codes and stdout:
> - 2xx with an empty body: success, equivalent to exit code 0 with no output
> - 2xx with a plain text body: success, the text is added as context
> - 2xx with a JSON body: success, parsed using the same JSON output schema as command hooks
> - Non-2xx status: non-blocking error, execution continues
> - Connection failure or timeout: non-blocking error, execution continues"

This is unambiguously **per-event, stateless POST/response** — Claude Code is the client
making one HTTP request per fired event, not a server holding a persistent connection. There
is no mention anywhere in the page of streaming, SSE, websockets, or a long-lived listener
for `http` hooks (the doc does separately mention SSE capping for **MCP** servers — "response
bodies now capped at 16 MB per SSE frame" — but that is the MCP transport, not the `http`
hook type, and is a different mechanism).

**Which events support `http`:** doc's own capability table (verbatim):

> "Events that support all five hook types (command, http, mcp_tool, prompt, and agent):
> PermissionDenied, PermissionRequest, PostToolBatch, PostToolUse, PostToolUseFailure,
> PreToolUse, Stop, SubagentStop, TaskCompleted, TaskCreated, TeammateIdle,
> UserPromptExpansion, UserPromptSubmit
>
> command, http, and mcp_tool hooks but not prompt or agent:
> ConfigChange, CwdChanged, DirectoryAdded, Elicitation, ElicitationResult, FileChanged,
> InstructionsLoaded, Notification, PostCompact, PreCompact, SessionEnd, StopFailure,
> SubagentStart, WorktreeCreate, WorktreeRemove
>
> SessionStart and Setup support command and mcp_tool hooks. They don't support http,
> prompt, or agent hooks."

So `http` hooks are supported on 26 of the ~28 documented events — everything except
`SessionStart` and `Setup`.

**Security gate on `http` hooks** (relevant to design — you can't just point one anywhere):

> "allowedHttpHookUrls: when defined at any settings level, Claude Code runs an HTTP hook
> handler only if its URL matches the merged allowlist
> httpHookAllowedEnvVars: when defined, Claude Code interpolates only the environment
> variables on that list into hook headers"

Local cross-check — `claude --help` and `~/.claude/cache/changelog.md`: `--help` output has
no `--http-hook`-style flag (hooks are settings-only, not CLI flags, consistent with doc).
Changelog corroborates the type's existence and evolution:

> changelog.md:3371: "Added HTTP hooks, which can POST JSON to a URL and receive JSON
> instead of running a shell command"
> changelog.md:2759: "Added `WorktreeCreate` hook support for `type: \"http\"` — return the
> created worktree path via `hookSpecificOutput.worktreePath` in the response JSON"

Both changelog entries independently confirm the "POST JSON / receive JSON" per-event
semantics — no mention of a persistent connection anywhere in either source.

### 2. `ConfigChange` semantics

Verbatim:

> "Runs when a configuration file changes during a session. Use this to audit settings
> changes, enforce security policies, or block unauthorized modifications to configuration
> files. ConfigChange hooks fire for changes to settings files, managed policy settings,
> and skill files. The `source` field in the input tells you which type of configuration
> changed, and the optional `file_path` field provides the path to the changed file."

> "ConfigChange hooks can block configuration changes from taking effect. Use exit code 2
> or a JSON `decision` to prevent the change. **When blocked, the new settings are not
> applied to the running session.**"

> "`policy_settings` changes can't be blocked. Hooks still fire for `policy_settings`
> sources, so you can use them for audit logging, but any blocking decision is ignored.
> This ensures enterprise-managed settings always take effect."

**Does a mid-session settings write take effect for OTHER hooks?** The doc states this
directly, separately from the `ConfigChange` section, under "Disable or remove hooks":

> "Direct edits to hooks in settings files are normally picked up automatically by the
> file watcher."

Read together with the ConfigChange blocking language ("When blocked, the new settings are
**not** applied" implies the converse: when not blocked, they ARE applied to the running
session), this is a live hot-reload mechanism, not a restart-required one.

Local changelog cross-check confirms the same hot-reload mechanism exists and has had bugs
in it (i.e., it is a real, exercised code path, not aspirational doc text):

> changelog.md line ~1652 (v2.1 era, exact line quoted from scrape above): "Fixed a
> regression in settings hot-reload where symlinked settings files caused misattributed
> change events and spurious `ConfigChange` hooks"

This is strong corroboration: the phrase "settings hot-reload" in the changelog is Anthropic's
own internal name for exactly this mechanism, and the bug report ("spurious ConfigChange
hooks" from symlink misattribution) proves the watcher-driven reload is real production
behavior, not merely documented intent.

**Caveat (INFERRED, not directly stated):** The doc says edits are "picked up automatically
by the file watcher" for *hook* config, and separately that ConfigChange fires for
"settings files, managed policy settings, and skill files" generally. It does **not**
state, in so many words, "a write to setting X takes effect for hook Y already registered
this session" as a general claim about all settings (only hooks are explicitly named as
picked-up-live). Treat "hot reload applies to hook definitions specifically" as OBSERVED;
"hot reload applies to all settings uniformly" as INFERRED from the general phrasing and
the ConfigChange blocking language, not a direct quote.

### 3. `terminalSequence` allowlist — is OSC 133 excluded?

Verbatim, version gate:

> "The `terminalSequence` field requires Claude Code v2.1.141 or later."

Verbatim, purpose:

> "Hooks run without a controlling terminal, so writing escape sequences directly to
> `/dev/tty` fails. Instead, return the escape sequence in the `terminalSequence` field and
> Claude Code emits it for you through its own terminal write path. This is race-free, works
> inside tmux and GNU screen, and works on Windows where there is no `/dev/tty`."

Verbatim, the full allowlist:

> "The field accepts a string of one or more allowlisted escape sequences:
> - OSC 0,1,2: window and icon titles
> - OSC 9: iTerm2, ConEmu, Windows Terminal, and WezTerm notifications, including 9;4 taskbar
>   progress
> - OSC 99: Kitty notifications
> - OSC 777: urxvt, Ghostty, and Warp notifications
> - Bare BEL"

Verbatim, rationale for the restriction:

> "`terminalSequence` is the supported replacement for hooks that previously wrote escape
> sequences directly to `/dev/tty`. **The allowlist is restricted to sequences that can't
> move the cursor or alter colors, so a hook can never corrupt an on-screen prompt.**"

**OSC 133 (shell-integration / prompt-marking sequences — the ones a terminal uses to know
"a new prompt/command started/ended") is NOT in the enumerated list.** The list is
exhaustive as written (OSC 0/1/2, OSC 9, OSC 99, OSC 777, bare BEL) — five items, no
"etc." or "and others." OSC 133 is absent by omission, and the stated rationale ("can't move
the cursor or alter colors") is consistent with excluding OSC 133, since OSC 133 sequences
are semantic markers a *host terminal* uses for command-boundary detection, not something
Claude Code emitting from inside a hook would need or was designed to expose — this doc
gives Claude Code no channel for a hook to emit OSC 133 on its own behalf.

CONFIRMED — OSC 133 is excluded from the terminalSequence allowlist, by direct enumeration
in the primary doc.

## Verdict

**ANSWERED-YES** on all three sub-questions, all with direct verbatim primary-source
quotes, cross-checked against local `claude --version` (2.1.222 — postdates the v2.1.141
terminalSequence gate and all cited changelog entries) and `~/.claude/cache/changelog.md`.

- `http` hook type: EXISTS. Per-event POST/JSON-response, NOT a long-lived endpoint —
  Claude Code is the client, one request per fired event, non-2xx/timeout/connection-failure
  all degrade to non-blocking (fail-open). Supported on 26 of ~28 events; NOT on
  `SessionStart`/`Setup`. Gated by `allowedHttpHookUrls` allowlist.
- `ConfigChange`: fires on settings/policy/skill file changes; can block (exit 2 / JSON
  decision) EXCEPT `policy_settings` changes, which always take effect. Hook config edits
  are picked up live via a file watcher ("settings hot-reload") — OBSERVED for hook
  definitions specifically, corroborated by a changelog bug fix in that exact subsystem.
  Whether *every* setting type hot-reloads for other hooks mid-session the same way is
  INFERRED, not directly stated as a blanket rule in this doc.
- `terminalSequence`: CONFIRMED OSC 133 is excluded. The allowlist is a closed enumeration
  of 5 items (OSC 0/1/2, OSC 9, OSC 99, OSC 777, bare BEL), explicitly restricted to
  sequences that "can't move the cursor or alter colors" — OSC 133 prompt-marking is
  outside that design intent and outside the list.

Nothing here required a live nested-claude tmux session; this was pure primary-doc
research per the task's own instruction ("no live session").

## Design consequence

- **Push-based detection via `http` hooks is viable but bounded**: an external state-driver
  service CAN receive live push notifications on Stop/PreToolUse/PostToolUse/Notification/etc.
  via an `http` hook pointed at a local listener (e.g. `http://127.0.0.1:PORT/event`), gated
  by `allowedHttpHookUrls`. But it is fire-and-forget per event with fail-open semantics on
  error — the driver cannot rely on delivery guarantees, cannot hold a connection open across
  events, and gets nothing on `SessionStart`/`Setup` (must fall back to `command`/`mcp_tool`
  there). This is a genuine alternative/complement to polling via tmux `capture-pane`, not
  a replacement for it in all cases — some session-lifecycle moments are `http`-blind.
- **`terminalSequence` cannot be used to emit OSC 133 shell-integration markers** from a
  hook to signal command-boundary state to an outer terminal multiplexer/driver. Any design
  that wanted "hook writes OSC 133 so the outer tmux/terminal driver can detect prompt
  boundaries the way a shell would" is foreclosed by this allowlist — it only reaches
  window-title/notification/bell channels, not cursor- or boundary-marking sequences. State
  detection that needs terminal-native prompt boundaries must keep using the busy-indicator
  polling approach in PITFALLS.md, not terminalSequence.
- **ConfigChange gives a legitimate mid-session hook-reconfiguration channel**: a driver
  could have a bootstrap hook rewrite `settings.json` to add more hooks mid-session and have
  them picked up live (per the file-watcher behavior), rather than requiring a session
  restart — useful for adaptive/staged detection setups. But this is confirmed only for hook
  definitions; do not generalize to "any setting hot-reloads for any consumer" without
  further verification if the design leans on that harder.
