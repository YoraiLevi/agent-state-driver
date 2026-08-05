# Extraction: the terminal-middle-layer gist, for state detection

Source documents (read in full): `docs/.research/gist-prior-research/terminal-middle-layer-map.md`
(988 lines, research date 2026-08-02) and its companion
`docs/.research/gist-prior-research/sources-consulted.md` (390 lines, 395 retrievals).

That gist answers a different question than ours — "what owns the PTY under an ADE on
Windows" — but its taxonomy axis 2.6 ("Agent-state derivation strategy") and section 5
("Interface Options Map") are a direct hit on our problem: detecting state of a TUI agent.
This file extracts only what transfers.

## Verdict (what matters for our design)

- **Three architectures exist for deriving agent state, not two.** (1) vendor-emitted
  structured events (OTel, JSONL, hooks) — cheapest, most reliable, but vendor-specific and
  requires the agent to cooperate; (2) native typed state from a VT-model-owning layer
  (peek/wait/snapshot verbs) — works on any TUI, costs you owning a terminal emulator; (3)
  external heuristic scraping (regex/OSC-title over rendered screen) — works on anything,
  but the gist found a **documented, reproduced production bug class**: whole-buffer text
  matching goes stale when a TUI redraws in place, so an idle indicator seen once keeps
  matching after the state changed (gist section 2.6, citing `awslabs/cli-agent-orchestrator#182`).
  This directly validates the PITFALLS.md finding "`❯` is not an idle signal" — it's the
  same failure class, independently discovered twice.
- **The convergent fix for scraping, from two unrelated projects, is: anchor to bottom-N
  lines or the OSC window-title, never match the whole screen, and add NOT-gates against
  stale artifacts.** This is a concrete, actionable mitigation for our scraping-based
  detector, not just a warning.
- **Claude Code's own OTel span `claude_code.tool.blocked_on_user` is a first-class,
  vendor-emitted "waiting on a human" signal with no PTY needed at all** — this is very
  plausibly the highest-leverage single fact in the gist for our project: for Claude Code
  specifically, we may not need scraping for at least one of our five target states
  (waiting-on-permission / waiting-on-input) if the OTel exporter is enabled.
- **Claude Code hooks (`PreToolUse`, `Stop`, `SubagentStop`, `Notification`, etc.) are a
  write-and-notify path, and 13 of them support an `http` hook type** — meaning our driver
  could register itself as a long-lived HTTP endpoint Claude Code posts to at state
  transitions, instead of polling a terminal at all. `SessionStart`/`Setup` do not support
  `http` (only `command`/`mcp_tool`) — a gap to design around if we need boot-time detection.
- **`wait(id, {idle|text|exit}, timeout)` is a verb that three independent, unrelated
  projects (boo, rmux, andyk/ht) converged on as the primitive for making a session
  scriptable.** If we build a native-typed-state detector (own a VT parser), this is the
  verb shape to expose, not raw screen dumps.
- **Nothing in this document addresses turn-boundary detection directly** (it is scoped to
  PTY session *ownership/survival*, not agent *conversational* state) — its state-detection
  content is confined to axis 2.6 and the `blocked_on_user` OTel fact. Do not over-read this
  gist as a state-detection study; it is a session-persistence study that happens to touch
  state detection at one axis.

## Mechanisms found

### 1. Vendor-emitted structured events (gist axis 2.6, pole 1)

Mechanism: the agent CLI itself emits typed events, out of band from the rendered terminal.

- **Claude Code OTel**: 34 named `claude_code.*` identifiers — a mix of metrics
  (`cost.usage`, `token.usage`, `session.count`, `lines_of_code.count`), events, and spans
  (`tool.execution`, `hook`). The state-relevant one is **`claude_code.tool.blocked_on_user`**
  — "is the agent stuck waiting on a human" with no PTY read required. Enable via
  `CLAUDE_CODE_ENABLE_TELEMETRY=1` (not an `OTEL_*` var); content redacted by default,
  opt-in per-field env vars. Caveat: Claude Code strips `OTEL_*` vars from every subprocess
  it spawns, including hooks — config does not reach grandchildren. (gist line 574, 239)
- **Claude Code hooks**: five types (`command`, `prompt`, `agent`, `http`, `mcp_tool`).
  `PreToolUse` returns `permissionDecision` (allow/deny/ask/defer) + `updatedInput`; this is
  how a headless driver answers a permission prompt without ever touching the PTY.
  `AskUserQuestion`/`ExitPlanMode` normally block in `-p` mode; a hook can answer them via
  `updatedInput`. 13 of the lifecycle events support `http` hooks (a long-lived process you
  own becomes the endpoint) — but `SessionStart`/`Setup` only support `command`/`mcp_tool`.
  As of v2.1.199, an MCP tool marked `_meta["anthropic/requiresUserInteraction"]` cannot be
  headlessly approved via `updatedInput` — an explicit opt-out tool authors control. (gist
  line 572, section 3.8)
- **Claude Code JSONL transcripts**: `~/.claude/projects/<project>/<session>.jsonl`, one
  line per event; it is a *tree* not a flat file — subagent fan-out is readable from
  `subagents/agent-<id>.jsonl` + `.meta.json` sidecars (`{agentType, description,
  toolUseId, spawnDepth}`). Undocumented internals, version-fragile; `cleanupPeriodDays`
  garbage-collects it. (gist line 575)
- **`claude -p --input-format stream-json --output-format stream-json --verbose`**: a
  full-duplex NDJSON channel over ordinary pipes, no PTY at all. Companion flags
  `--include-hook-events`, `--forward-subagent-text`, `--include-partial-messages`,
  `--replay-user-messages`. Scoping caveat: this is headless/print mode — it does **not**
  attach to an existing interactive TUI session; it's an alternative architecture where you
  spawn the agent with no PTY from the start, not a way to observe an existing terminal
  session. (gist line 576)
- **Codex** `exec --json` + rollout JSONL at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`,
  `resume --last`. Cited as cross-vendor convergence on the same shape (structured event
  stream + resumable session file) as Claude Code — evidence this is a real pattern, not
  vendor idiosyncrasy. (gist line 578)
- **OpenCode**: `opencode serve` exposes `GET /global/event` SSE plus `/tui/*` routes to
  drive the TUI programmatically. (gist line 579)

Where this fails/lies: vendor-specific (every agent needs its own integration); config
surface changes across versions (undocumented JSONL internals); OTel is heavily gated
behind multiple env vars and redacted by default; hooks can't reach bootstrap events over
HTTP.

### 2. Native typed state — own a VT parser (gist axis 2.6, pole 2)

Mechanism: a middle layer maintains its own terminal emulator (VT100 grid model) and
exposes typed queries over it, rather than raw bytes.

- **boo** (coder/boo, Zig, libghostty-vt): ships `wait --idle` and `peek --json` as
  first-class CLI verbs. POSIX-only.
- **rmux**: exposes a typed `snapshot()` call plus a Rust/Python/TS SDK.
- **quil** (Go, MCP server): `MsgScreenshotPaneResp{Text, CursorX, CursorY}` — structured
  screen state over MCP tool calls.
- **andyk/ht**: embeds the `avt` VT emulator so callers query the *rendered screen*, not
  the raw byte stream. Explicitly "wrap any binary with a terminal interface for easy
  programmatic access" — the shape gist calls out as "the shape to copy, not the tool to
  use" since it's POSIX-only (uses `forkpty`+`nix`).
- The synthesized universal verb set (gist section 5.1) includes `status(id) →
  {alive, pid, exit_code, blocked_on_user?}`, `get_output(id, lines)` /
  `snapshot(id) → {text, cursor_x, cursor_y}`, and `wait(id, {idle|text|exit}, timeout)`
  — the last one independently reinvented by boo, rmux, and ht.

Where this fails/lies: "only as good as the emulator" (gist's own one-line caveat on this
pole) — a VT model can itself drift from the real screen on resize races, alt-screen
mishandling, or Unicode splitting across read boundaries (documented elsewhere in the gist
as `String::from_utf8_lossy` truncating multi-byte chars at ring-buffer boundaries — a
bytes-to-string bug class, not specific to any one tool).

### 3. External heuristic scraping (gist axis 2.6, pole 3) — most relevant to us

Mechanism: regex or OSC-title matching over another program's *rendered* screen, with no
cooperation from the agent and no owned VT model beyond whatever capture mechanism is used.

Named instances: **tmux-agent-status**, **tmuxai**, and a **kiro_cli poller** (inside
`awslabs/cli-agent-orchestrator`).

**The documented failure mode, directly relevant to our PITFALLS.md entry "`❯` is not an
idle signal":**
`awslabs/cli-agent-orchestrator#182` — "Kiro CLI 2.0 TUI redraws the screen in-place…
retains 'Kiro is working' from earlier rendering alongside the new idle prompt"; impact
stated in the issue: "Handoff delegations never complete." This is a whole-buffer text
match going stale because the TUI redrew a subset of the screen in place, leaving old
status text visually present alongside a new (different) actual state. Issue status:
**closed as `completed` 2026-04-20**, title `fix(kiro_cli):` — the underlying bug was
fixed, but the gist treats this as valid evidence the *failure mode* is real and hit in
production, not evidence any specific tool is broken today.

**The convergent mitigation, independently reached by two projects** (gist doesn't name
which two beyond the three listed, but frames it as a shared discipline): anchor matches
to the **bottom-N lines** of the screen or to the **OSC window-title**, never match the
whole screen buffer, and add **NOT-gates** to reject matches against known-stale artifacts.

`operonlab/tmux-agent-status` ships an actual `docs/detection-matrix.md` (cited in
sources-consulted.md #119, retrieved successfully) — this is a primary source specifically
about detecting agent state over tmux and was **not deeply read into this gist's body
text** (only cited as a source, not quoted/extracted); it is worth a direct follow-up read
since it is the single most on-topic artifact in the whole 395-retrieval sweep for our
problem.

Where this fails/lies: whole-screen matching in the presence of in-place partial redraws;
any TUI (like Kiro CLI 2.0) that leaves old rendered text visible alongside new state until
the next full clear. Judgement in the gist: scraping is disqualified as an *architecture*
for headless/unattended use specifically because a stale-buffer misread "has nobody to
notice it when no human is in the loop" — not because any given instance is currently
broken. For a driver system like ours (headless, no human watching), this is the load-
bearing risk to design against if we go the scraping route at all.

### Interface shapes relevant to exposing/consuming state (gist section 5)

Seven shapes catalogued; the state-detection-relevant ones:

- **Structured event stream (no control plane)**: zero PTY, survives ADE swaps for free,
  vendor-maintained — Claude Code OTel + JSONL tree, Codex rollout JSONL, OpenCode
  `/global/event` SSE. Read-only for observation; a separate mechanism is needed for the
  write/drive path.
- **HTTP + WebSocket**: SSE/WS gives push notification rather than poll — relevant if we
  want to be *notified* of state transitions rather than continuously scraping.
- **MCP**: agent can drive itself with no glue, but "a stdio MCP server cannot own
  persistent sessions — the client spawns it. Only a server the middle layer runs
  independently works." No terminal-state naming convention exists across MCP servers.

### What was explicitly foreclosed

Anthropic closed both `claude serve`/network-attach requests as `not_planned`
(`anthropics/claude-code#24365` and `#6686`) — do not design assuming Claude Code will
grow a native network-attachable session API. This strengthens the case for either the
OTel/hooks/JSONL vendor-event channel, or an external scraping/VT-owning layer, as the two
real options — there is no third "just ask Claude Code" option coming.

## Sources

Everything below is drawn from `sources-consulted.md`'s 395-retrieval manifest, filtered to
what is highest-value for *our* problem (state detection of TUI agents), not the gist's own
problem (PTY session ownership on Windows). All were retrieved 2026-08-02 by the gist's
author; I did not re-fetch any of them myself — flagging that as inherited evidence, not
independently verified in this pass.

- **`operonlab/tmux-agent-status` — `docs/detection-matrix.md`** —
  https://github.com/operonlab/tmux-agent-status/blob/main/docs/detection-matrix.md
  (sources-consulted.md #119, web-scraper, retrieved ok). Highest-value single source found
  for our problem: a primary-source detection matrix for agent state over tmux. The gist
  cites it only as an instance of the "external heuristic scraping" pole; it was not
  extracted or quoted in the gist body. **Recommend reading this directly before designing
  our scraping detector.**
- **`awslabs/cli-agent-orchestrator#182`** —
  https://github.com/awslabs/cli-agent-orchestrator/issues/182 (sources-consulted.md #116,
  retrieved ok). Primary evidence for the stale-whole-buffer-match failure mode; closed/fixed,
  but documents the bug and its impact ("Handoff delegations never complete") in the
  reporter's own words.
- **`OEN-Tech/tmuxai`** — https://github.com/OEN-Tech/tmuxai (sources-consulted.md #118,
  retrieved ok). Named as a scraping-pole instance; not independently extracted here — worth
  reading its detection code directly.
- **Claude Code hooks documentation** — `code.claude.com/docs/en/hooks` (multiple
  sources-consulted entries: #1 top-level fetch, plus line-anchored citations throughout the
  gist at `:134`, `:146`, `:152`, `:182-192`, `:221`, `:328`, `:549`). Primary source for the
  five hook types, the `http` hook type's 13-event scope, and the `blocked_on_user`-adjacent
  headless-answer mechanics.
- **Claude Code monitoring/OTel docs** — `code.claude.com/docs/en/monitoring-usage`
  (sources-consulted.md #98, retrieved ok). Primary source for the 34 `claude_code.*`
  identifiers and the `blocked_on_user` span.
- **Claude Code CLI reference** — `code.claude.com/docs/en/cli-reference`
  (sources-consulted.md #151, retrieved ok). Source for `--input-format stream-json` /
  `--output-format stream-json` and companion flags.
- **`anthropics/claude-code#24365`** — https://github.com/anthropics/claude-code/issues/24365
  and **`#6686`** (sources-consulted.md #70, retrieved ok). Evidence Anthropic declined
  native network-attach twice; relevant to whether we should wait for a vendor solution
  (no) or build our own.
- **`awslabs/cli-agent-orchestrator` (repo, not just the one issue)** — home of the
  kiro_cli poller mentioned generically in axis 2.6; not itself in the manifest as a
  separate retrieval beyond issue #182, so its detection code was not independently
  fetched by the gist's author either.

## What this gist does NOT cover (gap for our own research)

- No treatment of Codex's or Copilot's own state-detection surfaces beyond the one-line
  Codex `exec --json` mention.
- No treatment of turn-boundary detection specifically (start-of-turn vs end-of-turn), only
  the coarser working/blocked_on_user binary.
- No mention of `agentculture/cultureagent`, OriNachum's blog, claude-squad's own state
  logic, VibeTunnel, or Omnara — all named in our own HANDOFF.md as prior art to mine but
  absent from this gist's 395-retrieval sweep. Those need separate research passes.
