# Windows middle-layer options for state detection & driving of CLI AI agents

Extracted from `docs/.research/gist-prior-research/persistent-shell-sessions-windows.md` (1787
lines, read in full), filtered to what matters for detecting agent state (working / idle /
waiting-on-permission / waiting-on-input / dead) and driving an agent programmatically on
Windows. That source is itself a research gist — an outside document, not an internal finding —
so treat its claims at the confidence level it states them (verified-in-source vs INFERRED vs
never-run). Line numbers below cite the gist, not our own code.

## Verdict (what matters for our design)

- **The no-PTY, vendor-native channel is the strongest state-detection mechanism on Windows,
  and it needs no PTY layer at all.** Claude Code's own `-p --input-format stream-json
  --output-format stream-json` (NDJSON over ordinary pipes) + hooks (write path, can answer
  permission prompts headlessly) + OpenTelemetry `claude_code.tool.blocked_on_user` (read path,
  literally the "is it stuck on a human" signal) + the JSONL transcript tree together cover
  "working / idle / waiting-on-permission / dead" without touching ConPTY, nesting, resize, or
  double-VT-parsing at all (gist lines 26-70, 1444-1458). This is the same shape our own
  PITFALLS.md and CLAUDE.md hooks-channel plan already points at — the gist is independent
  corroboration, not a new idea.
- **If we must own a PTY (to see literal on-screen bytes or let a human attach), "who owns
  CreatePseudoConsole" is non-negotiable and settled: own-from-birth only.** Late-attach
  (`AttachConsole` into a console we didn't spawn) is a read-only escape hatch at best, never a
  foundation — every "counterexample" (including node-pty itself) turns out to attach to its
  own spawned child (gist lines 129-140, 578, 651, 1338-1347). For our driver this means: if we
  want a PTY-level view of a Windows agent, we must be the one that launches it, not something
  bolted on afterward.
- **Screen-scraping for agent state is a documented, convergent bug class, not a theoretical
  worry — the fix pattern is "anchor to bottom N lines / OSC title, add NOT-gates for stale
  redraw artifacts."** A shipped project (`awslabs/cli-agent-orchestrator#182`) hit exactly our
  failure mode: a TUI redraw left "is working" text on screen alongside a new idle prompt, so a
  naive scraper never saw idle (gist lines 472-486). This directly validates PITFALLS.md's
  existing rule ("`❯` is not an idle signal... gate on the busy indicator being ABSENT plus N
  stable polls") — the gist gives us an external, independently-discovered instance of the same
  trap plus its known remedy.
- **Vendor-emitted structured events (OTel + hooks + JSONL) are the cheapest, most reliable
  state-detection channel and cost nothing structurally (they never touch the PTY, so they
  survive an ADE/terminal-emulator swap for free) — but they are per-vendor plumbing.** Claude
  Code's telemetry/hooks/JSONL are Claude Code's; Codex's `exec --json` + rollout JSONL is a
  separate implementation of the same shape (gist lines 486, 1152, 1458). If we support multiple
  agent CLIs we are writing N integrations, not one.
- **"Native typed state" (a PTY-owning daemon with a built-in VT parser exposing `wait_for_text`
  / `snapshot()` / `peek --idle`) is the other legitimate pole for state detection, and it is
  "only as good as the emulator"** (gist line 477). rmux (`wait_for_text`, `snapshot()`), quil
  (`MsgScreenshotPaneResp{Text,CursorX,CursorY}`), boo (`wait --idle`, `peek --json`) are the
  named examples. This is the shape to copy if we decide we need PTY-level fidelity: don't
  scrape raw bytes ourselves, use (or build) a typed peek/wait primitive over a VT model.
- **No candidate's driving verbs have ever been tested with no console attached — this is the
  single cheapest, highest-value experiment we should run ourselves before betting on any
  PTY-owning daemon as our driver.** The gist calls this Q23, "2 hours, can kill the entire PTY
  branch" (gist lines 1249-1253, 1425, 1590, 1683). If a Windows Service / Scheduled Task /
  headless caller can't invoke `zellij list-sessions`-shaped verbs, any PTY daemon we pick is a
  human-facing multiplexer, not a machine-drivable middle layer — and the no-PTY route wins by
  default for our use case.
- **Resize and prefix-key handling have no bearing on state DETECTION but matter for DRIVING**:
  there is no SIGWINCH on Windows (`ResizePseudoConsole` must be called explicitly at every hop,
  gist line 175), and no candidate is known to support "no prefix key at all on the headless
  path" (gist lines 253, 476, 1476) — relevant only if our driver ever needs to send raw
  keystrokes through a nested multiplexer rather than through a typed `send(id, bytes)` verb.

## Mechanisms found

### 1. No-PTY vendor-native channel (Claude Code `-p` stream-json + hooks + OTel + JSONL)

**What it is.** Not a middle layer at all — an architecture that spawns the agent with no PTY,
so none of the Windows PTY problems (ConPTY handshake, nesting, resize, double-VT-parse) apply
(gist lines 26-70, 1182).

**What it can OBSERVE, concretely:**
- **Duplex NDJSON stream** (`claude -p --input-format stream-json --output-format stream-json
  --verbose --include-hook-events --forward-subagent-text --include-partial-messages
  --replay-user-messages`) — full message-level transcript in and out, over ordinary pipes (gist
  lines 30-42).
- **Hooks as the write/detect path**: five types — `command`, `prompt` (LLM evaluates), `agent`
  (spawns a verifier), `http` (POST to a URL we own — "your middle layer can BE the endpoint"),
  `mcp_tool`. `PreToolUse` returns `permissionDecision: allow/deny/ask/defer` + `updatedInput`
  that replaces the tool call's arguments — and per the docs, returning `allow` +
  `updatedInput` satisfies `AskUserQuestion`/`ExitPlanMode`'s normal block in headless mode. This
  is the mechanism for *driving through* a permission prompt without a human (gist lines 44,
  1148-1150).
  - Caveat: `SessionStart`/`Setup` support only `command`/`mcp_tool` hooks, not `http`/`prompt`/
    `agent` — and `mcp_tool` on those two events is unreliable because MCP servers haven't
    finished connecting yet. `command` is the only dependable bootstrap hook (gist lines 48-50).
  - Caveat: as of v2.1.199, a tool marked `_meta["anthropic/requiresUserInteraction"]` cannot
    have its approval auto-skipped by a hook, even with `allow`+`updatedInput` (gist line 52).
- **OpenTelemetry as the read/liveness path**: 34 named `claude_code.*` identifiers (metrics +
  events + spans, not 34 events). `claude_code.tool.blocked_on_user` is explicitly the
  "is-the-agent-stuck-waiting-for-a-human" signal (gist line 54). Master switch is
  `CLAUDE_CODE_ENABLE_TELEMETRY=1` — deliberately **not** an `OTEL_*` var, the most common way
  people fail to enable it. Traces need `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` additionally.
  Content is redacted by default; opt in per field (`OTEL_LOG_TOOL_DETAILS` etc). Claude Code
  strips all `OTEL_*` exporter vars from every subprocess it spawns, including hooks — so
  telemetry config does not propagate to grandchild processes; must be re-set there (gist lines
  56-68, 1150).
- **JSONL transcript tree** at `~/.claude/projects/<project>/<session>.jsonl` — verified on
  native Windows 11 build 26200 to be a tree, not a flat file: sibling `<session-uuid>/`
  directory holds `subagents/agent-<id>.jsonl` + `agent-<id>.meta.json` sidecars
  (`{agentType, description, toolUseId, spawnDepth}`), plus `tool-results/` and `workflows/` —
  subagent fan-out topology is readable from the filesystem alone. Undocumented, version-fragile
  internals; `CLAUDE_CONFIG_DIR` relocates the whole tree; `cleanupPeriodDays` garbage-collects
  it (gist lines 68, 1150).
- **`terminalSequence` (v2.1.141+)**: a hook can push OSC escape sequences through Claude Code's
  own terminal write path even with no controlling terminal — "works on Windows where there is
  no /dev/tty." Allowlist: OSC 0/1/2 (titles), OSC 9 incl. 9;4 taskbar progress, OSC 99, OSC 777,
  bare BEL — restricted to sequences that can't move cursor or alter colors (so no OSC 133).
  Useful as an out-of-band structured signal a nested middle layer could parse (gist line 1156).

**Where it lies/fails:**
- **Cross-platform behavioral parity is INFERRED, never measured.** The flags are documented
  without platform qualification and the transport is ordinary pipes, but nobody has run this on
  both Windows and Linux and diffed output — flagged repeatedly as the single load-bearing
  untested claim of the whole architecture (gist lines 42, 1154, 1456, 1727).
- **Does not attach to an existing interactive TUI** — it's a way to *spawn* an agent headlessly
  from the start, not a way to observe/drive one already running under a human's terminal (gist
  lines 42, 70, 1182).
- **Per-vendor plumbing**: every channel above is Claude Code's own. Codex's equivalent (`exec
  --json` + rollout JSONL at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` + `resume --last`)
  is a structurally similar but separately-implemented shape — cross-vendor convergence is
  evidence the pattern is real, but we'd write and maintain N integrations for N agent CLIs
  (gist lines 486, 1152, 1158, 1452, 1458).

### 2. PTY-owning session daemons (own-from-birth ConPTY daemons)

**What they are.** A process that calls `CreatePseudoConsole` itself, spawns the agent as its
child, and holds the `HPCON` handle — the only architecture that actually works on Windows for
PTY ownership (gist lines 107, 131, 578, 665). Seven standalone candidates surveyed: **psmux,
Zellij, rmux, herdr, oly, qscreen, quil** — plus three embedded-in-a-larger-product
(`wezterm-mux-server`, OpenCode's `/pty`, `ao pty-host`).

**How a driver would OBSERVE state through each — the payload-type test that decides
scrape-vs-typed:**
- **"Native typed state" pole (best for our purposes)** — daemon owns a VT parser internally and
  exposes typed peek/wait/snapshot calls, so *we* never parse raw bytes ourselves:
  - **rmux**: `wait_for_text`, `snapshot()`, typed SDKs in Rust/Python/TypeScript — described as
    "exactly the primitives a headless driver needs... you are not scraping a screen, you are
    asking a typed question" (gist lines 748-762).
  - **quil**: MCP surface (18 tools) including `MsgScreenshotPaneResp{Text, CursorX, CursorY}`
    (gist lines 855, 1197).
  - **boo** (POSIX-only, not Windows-relevant directly but same idea): `wait --idle`, `peek
    --json` (gist lines 477, 1304).
  - The verb-set synthesis proposes `wait(id, {idle|text|exit}, timeout)` and
    `status(id) → {alive, pid, exit_code, blocked_on_user?}` as non-negotiable primitives any
    driver needs (gist lines 1197-1201).
- **"Parallel model, raw live path" pole** — daemon keeps a VT model for snapshots/scrollback but
  ships raw child bytes on the live stream, so an external consumer (e.g. our own state detector,
  or the ADE's own xterm.js) can be the only VT parser: qscreen `AttachMode::Bytes`, oly
  `ServerMessage::Data{data: Vec<u8>}`, quil `PaneOutputPayload{Data []byte}`, psmux `-CC`
  `%output` (asterisked — see below) (gist lines 220, 424-430).
- **"External heuristic scraping" pole — the one to avoid.** Regex/OSC-title matching over
  another program's rendered screen. Convergent bug: `awslabs/cli-agent-orchestrator#182`,
  "Kiro CLI 2.0 TUI redraws the screen in-place... retains 'Kiro is working' from earlier
  rendering alongside the new idle prompt" → "Handoff delegations never complete." Two
  independent projects landed on the same fix: **anchor to bottom N lines or the OSC title,
  never the whole screen; add NOT-gates for stale artifacts** (gist lines 472-486). Judgment
  from the gist: scraping is disqualified as an *architecture* for headless use because a
  stale-buffer misread has nobody to notice it with no human in the loop (gist line 486).

**Where they lie/fail — Windows-specific mechanics that break driving, not just observing:**
- **ConPTY's DA1 startup handshake**: on creation, ConPTY sends `CSI c` (DA1, "what kind of
  terminal are you?") and waits up to 3 seconds for a reply; answering instantly took one
  measured spawn from 2121ms to 142ms. Get this wrong and every spawn (including ones our driver
  triggers) costs ~2s and looks like generic slowness (gist lines 145-159). Only psmux
  verifiably answers it (dedicated regression test); oly deliberately does NOT answer DA1 in
  detached mode despite being "widely credited" with doing so (gist lines 155-158, 803).
- **`PSEUDOCONSOLE_INHERIT_CURSOR` + slow CPR reply = indefinite hang before any child code
  runs** — no logs, nothing to attach a debugger to (gist lines 161-163).
- **No SIGWINCH on Windows** — resize is a call (`ResizePseudoConsole`) the owner must make
  explicitly at every nesting hop, or it silently never happens; a driver that resizes a pane
  must propagate that resize itself (gist line 175, 1198).
- **Double-ConPTY nesting (our exact topology: ADE spawns middle layer spawns agent) has never
  been empirically tested for ANY candidate** — explicitly flagged as the single largest
  untested area, "including oly, whose supposed nested-agent tests were found not to exist"
  (gist lines 257, 1518, 1694, 1735).
- **tmux control-mode (`-CC`) — the most decade-hardened driving interface — is reported to get
  corrupted by ConPTY when nested**: ConPTY silently eats the DCS escape the protocol is detected
  with and interleaves its own cursor sequences, corrupting the line-based protocol our driver
  would be parsing. Source scopes this to the SSH case; generalizing to a node-pty-style nested
  ConPTY is explicitly flagged as INFERRED, not verified, though corroborated by two independent
  Microsoft issue threads (gist lines 230-232, 1024-1028).
- **String-typed wires silently and permanently corrupt Unicode** — relevant because agent CLIs
  emit heavy Unicode (the `✳` in Claude Code's own window title already broke quil's emulator).
  psmux's `%output` ring runs `String::from_utf8_lossy` before escaping, so a multi-byte char
  split across two drains becomes U+FFFD forever (gist lines 228, 697, 1474, 878). If our driver
  consumes a daemon's byte stream to detect state, prefer a byte-typed wire, not a string-typed
  one.
- **Headless verbs (no console attached) are untested for literally every candidate** — this is
  the gist's own top-priority open question (Q23, "2 hours, can kill the entire PTY branch") and
  directly answers "can we drive this from a Windows Service / Scheduled Task / our own headless
  process at all" (gist lines 1249-1253, 1425, 1590-1646, 1683).
- **Unauthenticated local IPC**: several candidates (psmux's cross-session port, oly's named
  pipe) have no ACL/handshake, meaning any local process on the machine could read/inject into an
  agent session we're driving. Only rmux gets namespacing (identity-scoped pipe name derived
  from SID+integrity level) and ACL right simultaneously (gist lines 1385-1391).

**Maturity/named tools, with driving-relevant verbs:**

| Tool | State-observation primitive | Driving verbs | Windows maturity |
|---|---|---|---|
| **psmux** | Full VT owner (TUI) / raw-by-intent `-CC` `%output` (but see string-corruption caveat) | tmux `-CC` control mode (send commands, get `%begin`/`%end`/`%output`) + full tmux CLI verb set | Windows-only, 3140★, most decade-hardened interface (5+ independent `-CC` implementers), but headless-verbs untested and has an unauthenticated cross-session port (gist 675-706) |
| **rmux** | Typed `wait_for_text`, `snapshot()` | 90+ tmux-compatible verbs + typed SDKs (Rust/Python/TS) | Best security model (identity-scoped pipe), single-author bus-factor risk, nesting untested (gist 744-763) |
| **Zellij** | Full VT owner, no typed peek/wait found | CLI verbs, but **no verified detached-start invocation exists** — blocks even step 1 of driving it headlessly | Best-verified Windows port (0.44.0), 34.6k★, explicit nesting policy knob (`nested_session_handling`) (gist 709-741) |
| **quil** | Typed `MsgScreenshotPaneResp{Text,CursorX,CursorY}` | MCP surface, 18 tools — agent can drive it with the same mechanism it already uses for tools | Richest agent-facing surface but ubuntu-only CI, zero Windows external issues filed, a defect that deletes a live daemon's socket on second launch (gist 851-878) |
| **oly** | Raw bytes (`ServerMessage::Data`) + separate VT model for snapshots | Named-pipe IPC + HTTP/WS + push notifications | Real windows-latest PTY CI (rare in this field), but no ACL on its pipe, and does NOT answer DA1 in detached mode despite reputation (gist 797-825) |
| **`ao pty-host`** | Raw bytes, 8-message binary protocol | `GetOutput(lines)`, `Status`, `Kill`, `SendMessage` | Closest architectural match to "the layer we want" — detached survival, scrollback replay, resize arbitration (`applyLargestLocked`, sizes to largest attached client), orphan recovery via on-disk registry — but it's a `Hidden:true` internal subcommand with no compatibility promise, and loopback-only with no auth (gist 934-958) |
| **OpenCode `/pty`** | Raw-ish (UTF-8 string wire, has decode bugs) | REST+WS, cursor-resumable replay | Best-shaped attach API (ticket auth, resumable cursor) but undocumented (nowhere on opencode.ai) and dies with `opencode serve` (L1+, not L2 — doesn't survive the host) (gist 909-932) |

### 3. Late-attach (out-of-band, sideways-reaching) — explicitly NOT a driving foundation

**What it is.** `AttachConsole(pid)` into a console the middle layer did not spawn — the "reach
into an already-running agent" fantasy. Windows consoles are multi-client objects
(`GetConsoleProcessList` enumerates attached processes), which is *why* this looks plausible
(gist lines 115-127).

**What it can observe:** At best, read-only screen scraping via `ReadConsoleOutputCharacter` —
and even that is unreliable: the one production empirical attempt (`pywinauto#492`) got attach
success but `ReadConsoleOutputCharacter` returning **ten spaces**, and it didn't work at all
against `cmd.exe` or PuTTY (gist line 123). NVDA is the one production system that reads this
way — and it never writes. winpty/wexpect read AND write but own the console from birth, so they
never actually late-attach (gist lines 123-125).

**Where it fails as a driving mechanism:**
- Microsoft has explicitly told developers not to build on the write half: `WriteConsoleInput`
  carries an "Important" banner calling it "no longer a part of our ecosystem roadmap" and a
  "wrong-way verb for this buffer" (gist line 121, 1342).
- Reading is gated by integrity level — a lower-integrity process cannot read a higher-integrity
  console (directional; same-user/same-integrity siblings unaffected) (gist line 119, 1343).
- **The most commonly cited "proof" that late-attach works — node-pty — actually disproves it**:
  it hands `AttachConsole` the PID of a process it spawned itself
  (`src/windowsPtyAgent.ts:149`), so it's another own-from-birth system in disguise (gist line
  133, 578).
- Two further boundaries (foreign-SID console, session-0 boundary) are believed to block it
  entirely but are explicitly flagged as INFERRED, never observed to fail (gist line 139, 1724).
- **Conclusion for our design**: if we want to attach to an agent session someone else already
  launched (e.g. a human's existing terminal), there is no working Windows mechanism for that.
  We must insert ourselves at spawn time.

### 4. Interface/wire shapes relevant to a driver (from "Interface shapes" section)

Useful menu for how our own driving/observation channel should be shaped, independent of which
daemon (if any) we build on:

- **CLI verbs** — trivially scriptable, no client library, same verb string usable from shell,
  hook, or human — "nothing has to be re-learned when the human leaves the loop." Costs:
  per-call spawn latency, no push/streaming, must poll for state (gist lines 996-1016).
- **Binary wire protocols** — exact byte fidelity; WezTerm's codec is the standout for explicit
  version-skew tolerance (varint-encoded length/ident/serial so client/server survive version
  drift) — directly relevant to us since our driver and the agent CLI's version will drift
  independently over time (gist lines 1051-1061).
- **HTTP/WebSocket** — console-independence is inherent (a network client needs no console at
  all — the one property every PTY-owning CLI candidate is *untested* on). Costs: port/bind/auth
  become our problem; loopback binding is NOT an auth boundary (`ao pty-host`'s own source
  comment: "any local process on this host can connect to the assigned port") (gist lines
  1063-1076).
- **MCP** — good *additional* surface, bad *only* surface: a stdio MCP server cannot own
  persistent sessions because the client spawns and reaps it. Only a server the middle layer
  runs independently works for persistence (gist lines 1106-1116).
- **The verb set every candidate converged on independently** (directly reusable as our own
  driver's API surface): `spawn`, `list`, `attach(id,{cursor}) → {replay,cursor,stream}` (must
  carry a resumable cursor), `detach`, `send(id,bytes)`/`send_keys(id,keys)`,
  `get_output(id,lines)`/`snapshot(id)→{text,cursor_x,cursor_y}`, `resize(id,cols,rows)`,
  `status(id)→{alive,pid,exit_code,blocked_on_user?}`, `kill(id,signal)`,
  `wait(id,{idle|text|exit},timeout)` (gist lines 1190-1201).

## Sources

- Primary source for this whole extraction: `docs/.research/gist-prior-research/persistent-shell-sessions-windows.md`
  (local file, 1787 lines, read in full 2026-08-05) — itself a research gist citing GitHub repos,
  Microsoft docs, and issue threads; treat second-hand per its own confidence labels
  (verified-in-source / INFERRED / never-run).
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks) — five hook types,
  `SessionStart`/`Setup` exclusions, `terminalSequence`.
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) — `stream-json`
  flags.
- [Claude Code monitoring/telemetry](https://code.claude.com/docs/en/monitoring-usage) — the 34
  `claude_code.*` identifiers.
- [awslabs/cli-agent-orchestrator#182](https://github.com/awslabs/cli-agent-orchestrator/issues/182) —
  the documented screen-scraping stale-redraw bug (closed `completed` 2026-04-20; proves the
  failure mode occurred, not that any current tool is broken today).
- [rmux](https://github.com/Helvesec/rmux), [quil](https://github.com/artyomsv/quil),
  [psmux](https://github.com/psmux/psmux), [oly/open-relay](https://github.com/slaveOftime/open-relay),
  [Zellij](https://github.com/zellij-org/zellij), [`ao pty-host`/Agent Orchestrator](https://github.com/Untrivial-ai/agent-orchestrator),
  [OpenCode](https://github.com/anomalyco/opencode) — named PTY daemons discussed above.
- [microsoft/terminal#7019](https://github.com/microsoft/terminal/issues/7019) — DA1 handshake
  timing (closed `not_planned`, maintainer comments continue post-closure).
- [microsoft/terminal#19621](https://github.com/microsoft/terminal/issues/19621) — ConPTY
  passthrough breaking tmux control mode (open, filed by a Microsoft member).
- [pywinauto#492](https://github.com/pywinauto/pywinauto/issues/492) — the empirical late-attach
  failure (`ReadConsoleOutputCharacter` returning ten spaces).
