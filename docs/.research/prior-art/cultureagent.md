# Prior art: `cultureagent` (OriNachum / agentculture)

**Correction to the task brief:** there is no `agentculture/cultureagent` git repo. `cultureagent`
is a **PyPI package** (`pip install cultureagent`, currently `0.13.0`) that backs the
`agentculture/culture` orchestrator — `culture`'s `culture_core/clients/*` modules are thin
re-export shims (`from cultureagent.clients.claude.config import *`) over the real code, which
ships only as an installed wheel. Confirmed: `culture/pyproject.toml:33` pins
`"cultureagent~=0.13.0"`; `culture/culture_core/clients/claude/config.py:1-22` is a shim with the
docstring "the implementation lives in cultureagent; bug reports go upstream." No public git
history for `cultureagent` itself was found (searched `agentculture` org's 75 repos and
`OriNachum`'s repos — neither lists it). This research installed the wheel with
`uv pip install "cultureagent[backend-claude,backend-acp,backend-copilot,backend-colleague]==0.13.0"`
into a scratch venv and read the extracted source directly (paths below are under
`.../scratchpad/cadl-venv/lib/python3.14/site-packages/cultureagent/`).

## Verdict (what matters for our design)

- **None of the five backends here drive a CLI's terminal UI at all.** Every backend talks to a
  programmatic API one layer below the TUI: Claude via the `claude_agent_sdk.query()` async
  generator, Codex/ACP via JSON-RPC over stdio to `codex app-server` / an ACP-speaking subprocess,
  Copilot via `github-copilot-sdk`'s `CopilotClient`/session objects, and "colleague" isn't even a
  subprocess — it's an in-process Python object (`ColleagueHarness`). **This is a fundamentally
  different problem than ours**: we need to detect state of an agent's *interactive terminal UI*
  (PTY/screen), because we don't control the agent's internals. cultureagent sidesteps our exact
  problem by only supporting backends it can drive structurally.
- **Permission dialogs are eliminated at the source, not detected-and-answered.** Claude:
  `permission_mode="bypassPermissions"` in `ClaudeAgentOptions` (`claude/agent_runner.py:148`).
  Codex: `"approvalPolicy": "never"` at `thread/start` PLUS an unconditional auto-approve handler
  for `exec_approval_request` / `file_change_approval_request` / `patch_apply_approval_request`
  that replies `{"approved": true}` to every request (`codex/agent_runner.py:320-326,390-398`).
  ACP: unconditional auto-approve of `session/request_permission` the same way
  (`acp/agent_runner.py:382-383,414-422`). Copilot: `PermissionHandler.approve_all` passed at
  session creation (`copilot/agent_runner.py:98`). **There is no "detect a permission dialog and
  answer it" logic anywhere in this codebase** — worth noting as a design option we have that
  they don't need: if we control agent launch flags, bypass-permission modes remove an entire
  state (waiting-on-permission) from the state machine. PITFALLS.md already flags
  `bypassPermissions` as a footgun for nested agents / permission classifiers — this confirms it's
  the industrial no-dialogs escape hatch, with the tradeoffs that implies.
- **"Working" (tool execution) is a defined-but-unimplemented state across all backends.**
  `STATE_WORKING` exists in the enum and in `BUSY_STATES`
  (`clients/shared/presence_emitter.py:35,51`) and the wire-contract doc says outright: *"`working`
  is part of the contract, but as of cultureagent 0.13.0 no backend has an observable
  tool-execution boundary, so no emitter sends it yet"* (`culture/protocol/extensions/presence.md`,
  Activity States table). Their actual state machine collapses to five *reachable* states:
  `idle → listening → thinking → (idle) → draining → offline`. Even a mature, funded prior-art
  project has not solved "tool call is running" as a distinct observable state — that's a genuine
  gap our design needs to either accept or solve better.
- **Dead-agent detection is two independent mechanisms layered, neither of which is "watch the
  screen."** (1) *Process-exit-triggered*: subprocess backends detect death via EOF on the
  stdout-reader loop → `on_exit(returncode)` → the daemon's crash-recovery state machine
  (`_on_agent_exit`, `base_daemon.py:800-834`): a sliding-window crash counter
  (`MAX_CRASH_COUNT=3` in `CRASH_WINDOW_SECONDS=300`) opens a circuit breaker after 3 crashes in 5
  minutes, else schedules `_delayed_restart` after `CRASH_RESTART_DELAY=5`s
  (`base_daemon.py:56-58`). (2) *Heartbeat-staleness-triggered* ("presumed-hung"), for the case
  where the process is alive but wedged and never closes its socket: a `stale-busy watchdog` flags
  a resident `presumed_hung` when it was last in a busy state and its last PRESENCE heartbeat is
  older than `stale_after_seconds` (default 90s, must be `>` the 30s heartbeat interval) — this is
  computed **at read time**, server-side, not client-side (`protocol/extensions/presence.md`,
  Stale-Busy Watchdog section; server config `culture_core/config.py:74-85`, resource-view field
  `culture_core/resource_view.py:96`). **This two-tier design (hard-exit vs. soft-hang) is directly
  reusable in our functional design** even though their transport (IRC heartbeats) doesn't apply
  to us.
- **State transitions are edge-triggered and code-boundary-driven by explicit design principle:**
  *"transitions are driven only by observable code boundaries — never by model self-report"*
  (`presence_emitter.py:9-10`, restated in the wire-contract doc). Concretely only two boundaries
  fire in practice across all backends: (a) work dispatch → `listening` (mention/DM past the
  accept-gate, or a poll dispatch) — `base_daemon.py:572,681`, `claude/daemon.py:236`,
  `acp/daemon.py:357`; (b) LLM call open/close → `thinking`/`idle` via the
  `presence_thinking()` async context manager wrapped around every backend's
  `harness.llm.call` span (`presence_emitter.py:232-253`, used identically in
  `claude/agent_runner.py:197`, `codex/agent_runner.py:457`, `copilot/agent_runner.py:200`,
  `acp/agent_runner.py:462`). This is the single common integration point across five otherwise
  wildly different backend architectures — a validated pattern: wrap the "waiting on the model"
  boundary once per backend, get a uniform signal for free.
- **The `colleague` backend proves "no subprocess" is a legitimate 5th shape.** Its
  `agent_runner.py` is 44 lines and explicitly documents *"there is NO subprocess coding-agent for
  colleague... its brain IS colleague's own `ColleagueHarness`"* (`colleague/agent_runner.py:1-18`).
  If we ever need to support an in-process/library-embedded agent (not spawned as a CLI at all),
  this is the shape: no PTY, no stdio, no JSON-RPC — just direct method calls with the same
  `presence_thinking()` wrapper applied around the harness turn.

## Mechanisms found

### Claude backend (`clients/claude/`)

- **Driving mechanism**: `claude_agent_sdk.query(prompt=..., options=ClaudeAgentOptions(...))`
  — an async generator over structured SDK message objects. NOT a PTY, NOT `claude -p` subprocess,
  NOT tmux. `agent_runner.py:8-17,144-155,176-188`.
- **Options set**: `model`, `cwd`, `permission_mode="bypassPermissions"`,
  `setting_sources=["project"]`, and `resume=<session_id>` once a session exists
  (`agent_runner.py:144-155`).
- **States distinguished**: message-type dispatch inside the async generator —
  `ResultMessage` (session/error bookkeeping, `_handle_result_message`, line 157) vs.
  `AssistantMessage` (fires `on_message` callback, line 163-167). No separate "tool running" event
  is surfaced to the presence layer; tool-use/tool-result blocks are converted to dicts
  (`_content_block_to_dict`, line 31-41) purely for the supervisor's own observation, not fed into
  the presence state machine.
- **Turn timeout / hang detection**: `asyncio.wait_for(self._stream_turn(prompt), timeout=...)`
  (default `_C.DEFAULT_TURN_TIMEOUT_SECONDS`) — on `TimeoutError`, calls `on_exit(1)`, which routes
  into the shared crash-recovery machine (`agent_runner.py:207-228`). This is the "wedged SDK
  stream" dead-detection path — a pure timeout, no polling of any external signal.
- **Permission dialogs**: eliminated via `bypassPermissions` — never detected, because they never
  occur.
- **Where it fails**: SDK-internal — if the SDK's async generator itself wedges without raising,
  only the outer `asyncio.wait_for` timeout catches it (coarse: whole-turn granularity, not
  per-tool-call).

### Codex backend (`clients/codex/`)

- **Driving mechanism**: spawns `codex app-server` as a subprocess
  (`asyncio.create_subprocess_exec("codex", "app-server", stdin=PIPE, stdout=PIPE,
  stderr=DEVNULL)`, `agent_runner.py:113-120`) and speaks **JSON-RPC 2.0 over stdio** — one JSON
  object per line, `id`-correlated requests/responses via `asyncio.Future`, uncorrelated
  `method`-only lines treated as notifications (`_dispatch_jsonrpc_message`,
  `agent_runner.py:249-261`). This is a structured protocol, not scraping ANSI terminal output.
- **States distinguished** via notification methods: `turn/started` → `self._busy = True`
  (`agent_runner.py:333-335`); `item/agentMessage/delta` → streams into an accumulated-text
  buffer; `thread/tokenUsage/updated` → caches per-turn token breakdown; `turn/completed` →
  `self._busy = False`, flushes accumulated text, sets `self._turn_done` event
  (`agent_runner.py:361-369`); `error` → also clears busy/turn_done (`agent_runner.py:371-377`).
- **Approval methods**: `exec_approval_request`, `file_change_approval_request`,
  `patch_apply_approval_request` — all routed to `_auto_approve`, which unconditionally replies
  `{"approved": true}` (`agent_runner.py:320-326,390-398`). Combined with
  `"approvalPolicy": "never"` at `thread/start` (`agent_runner.py:140`) — belt-and-suspenders
  against permission stalls.
- **Turn timeout / dead detection**: outer `asyncio.timeout(self._turn_timeout)` wraps
  `turn/start` + waiting on `self._turn_done` (`agent_runner.py:449-484`); on timeout, the
  subprocess is `.terminate()`d so the reader loop sees EOF → `_cleanup_codex_process` →
  `on_exit(returncode)` → daemon crash-recovery (`agent_runner.py:415-448,281-289`) — i.e. a
  *stuck* turn is converted into a *process-death* event so one recovery path handles both.
  Genuine process death (crash) is detected the same way: `readline()` returns empty bytes → EOF
  → loop exits → cleanup (`agent_runner.py:290-318`).

### Colleague backend (`clients/colleague/`)

- **Driving mechanism**: none — no subprocess at all. The "runner" is
  `colleague.resident.harness.ColleagueHarness`, an in-process Python object run under an
  agent-lifecycle "pump-bridge" `Supervisor`; `build_runner()` is a 44-line honesty-shim that
  explicitly refuses to fabricate a fake subprocess-shaped runner
  (`colleague/agent_runner.py:1-44`).
  This backend proves the harness supports library-embedded agents as their own architectural
  shape, distinct from PTY/subprocess/SDK.
- **States distinguished**: only `listening` (work dispatched, `colleague/runtime/transport.py:
  265-277`) and `thinking`/`idle` via the shared `presence_thinking()` wrapper around its one
  bounded `engine.work` turn — no separate death/timeout handling was found in the runner itself
  (delegated entirely to whatever `ColleagueHarness`/Supervisor do internally, out of scope of this
  package).

### Copilot backend (`clients/copilot/`)

- **Driving mechanism**: `github-copilot-sdk`'s `CopilotClient` (which itself spawns the
  `copilot` CLI as a subprocess, per `SubprocessConfig`) plus a `create_session()` /
  `session.send_and_wait()` request/response API (`copilot/agent_runner.py:80-121,216-225`). The
  culture code never touches the copilot CLI's stdio directly — it's one layer above, calling into
  the vendor SDK's Python objects.
- **States distinguished**: coarse request/response only — no streaming deltas, no
  intermediate notifications observed in this module; a single `send_and_wait(text,
  timeout=INNER_SDK_TIMEOUT_SECONDS)` call per turn, wrapped in an *outer* `asyncio.wait_for`
  timeout as a second safety net in case the SDK's own timeout doesn't fire
  (`copilot/agent_runner.py:190-232`).
  Comment explicitly says: *"if send_and_wait's own 120s timeout doesn't fire (SDK ignores it,
  hangs before that, or wedges in a different layer), this wraps the whole turn."* — i.e. even the
  SDK author distrusts the SDK's own hang detection and double-wraps it.
- **Permission dialogs**: `PermissionHandler.approve_all` passed to `create_session()`
  (`copilot/agent_runner.py:98`) — same "eliminate, don't detect" pattern.
- **Dead detection**: any exception (including timeout) → `_handle_turn_error()` →
  `on_exit(1)` unless already stopping (`copilot/agent_runner.py:178-188`) → shared crash recovery.

### ACP backend (`clients/acp/`) — generic Agent Client Protocol (Cline, OpenCode, etc.)

- **Driving mechanism**: same shape as Codex — spawn the ACP-speaking CLI as a subprocess
  (`acp_command`, e.g. `["opencode", "acp"]`) and speak JSON-RPC over stdio, including a stderr
  reader task that logs everything from stderr as a diagnostic channel
  (`acp/agent_runner.py:159-166,356-372`).
- **States distinguished**: `session/update` notifications with
  `sessionUpdate: "agent_message_chunk" | "agent_thought_chunk"` → `self._busy = True`, accumulate
  text; presence of `"stopReason"` in the update → `self._busy = False`, flush
  (`agent_runner.py:388-401`). A **busy-poll fallback** exists on top of the event-driven signal:
  after sending a prompt, `_handle_prompt_result` does `while self._busy and self._running: await
  asyncio.sleep(0.1)` (`agent_runner.py:447-455`) — the only place in this whole codebase that
  polls rather than reacting to a pushed event, because ACP's `stopReason` can arrive either in the
  synchronous RPC response OR via an async `session/update`, and the code isn't sure which will
  happen so it polls the flag either way.
- **Permission dialogs**: `session/request_permission` notification → unconditional
  auto-approve, same pattern as Codex (`agent_runner.py:382-383,414-422`).
- **Timeout / dead detection**: outer `asyncio.timeout(self._turn_timeout)` around the whole
  send+poll; on timeout, explicitly terminates the subprocess so EOF triggers the same
  cleanup→on_exit→crash-recovery path used everywhere else, with a comment noting this was a
  deliberate fix (issue #349) — earlier versions apparently let ACP timeouts silently not reach
  crash recovery (`agent_runner.py:480-501`). One retry-once-on-timeout wrapped around
  `session/prompt` itself, separate from the outer turn timeout (`agent_runner.py:424-445`).

### Shared state machine (`clients/shared/presence_emitter.py`, `base_daemon.py`)

- **States**: `idle`, `listening`, `thinking`, `working` (defined, unused), `draining`, `offline`
  (`presence_emitter.py:32-48`). `BUSY_STATES = {listening, thinking, working, draining}` — these
  keep the heartbeat alive; `idle`/`offline` don't (`presence_emitter.py:51`).
- **State machine semantics** (`PresenceTracker.transition`, `presence_emitter.py:118-129`):
  edge-triggered (no-op if state unchanged), and `draining` is **sticky** — once draining, only
  `offline` can follow, so a late in-flight LLM call finishing mid-shutdown can't flip the resident
  back to `idle` and undo the drain signal.
- **Wire encoding**: `PRESENCE :<json>` IRC verb, `{state, since, task?, tokens_in?, tokens_out?}`,
  512-byte IRC line cap enforced by dropping `task` first if oversized
  (`presence_emitter.py:66-95`).
- **Heartbeat**: while busy, re-emits every `heartbeat_interval_s` (default 30) so a slow-but-alive
  turn doesn't look stale; cancelled the instant the tracker leaves a busy state
  (`presence_emitter.py:218-229`).
- **Crash-recovery constants**: `MAX_CRASH_COUNT=3`, `CRASH_WINDOW_SECONDS=300`,
  `CRASH_RESTART_DELAY=5` (`base_daemon.py:56-58`); `_on_agent_exit` distinguishes clean exit
  (code 0, fires `agent_complete` webhook, no restart) from crash (any nonzero code → sliding
  crash-time window → circuit breaker after 3 in 5 min, else scheduled restart) —
  `base_daemon.py:800-834`.
- **Server-side stale-busy watchdog** ("presumed-hung"): computed at read time by the IRC server
  (agentirc), not the client — `presumed_hung = state in BUSY_STATES and (now - last_refresh) >
  stale_after_seconds`, default `stale_after_seconds=90` vs. `heartbeat_interval_seconds=30`, with a
  fail-fast config assertion that stale threshold must exceed the heartbeat interval
  (`culture/protocol/extensions/presence.md` "Stale-Busy Watchdog"; config fields
  `culture/culture_core/config.py:74-85`; resource-view field
  `culture/culture_core/resource_view.py:96`). This is the mechanism that answers "the process
  died without a clean disconnect" (network partition, `SIGKILL` without socket FIN) — clean death
  instead reads as `offline` because the socket closes and the server infers offline without a
  final PRESENCE line (`presence_emitter.py:191-199`, doc section "Activity States" row `offline`).

## Sources

- **PyPI package** `cultureagent` v0.13.0 — installed via `uv pip install`, no public repository
  found; source read from the installed wheel at
  `/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/cadl-venv/lib/python3.14/site-packages/cultureagent/`
  (paths cited above are relative to this root).
- [github.com/agentculture/culture](https://github.com/agentculture/culture) — the orchestrator
  that consumes `cultureagent`; cloned shallow to
  `/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/culture`.
  Key files read: `pyproject.toml`, `culture_core/clients/*/config.py` (re-export shims),
  `protocol/extensions/presence.md` (wire-contract design doc), `culture_core/config.py`,
  `culture_core/resource_view.py`.
- **agentirc, `agentculture/culture`'s IRC server** — NOT separately cloned; its behavior for
  presence aggregation is documented (and independently mirrored) in `culture`'s
  `protocol/extensions/presence.md` and `culture_core/resource_view.py`, which was sufficient to
  confirm the presence/busy representation without a second clone (agentirc issue #53 is cited
  in-doc as the adoption record). If deeper agentirc-side implementation detail is needed later,
  clone `agentculture/agentirc` directly — it was not read in this pass.
- `agentculture` org repo listing — `gh api orgs/agentculture/repos --paginate` (75 repos; no
  `cultureagent` among them, confirming the PyPI-only distribution model).
