# Persistent, Programmatically Drivable Shell Sessions on Native Windows 11 — A Working Engineer's Guide

You have a coding-agent CLI that runs for hours. It is doing something long — a refactor across a worktree, a test loop, a migration — and right now the only thing keeping it alive is a terminal pane inside a desktop app. Close the app, restart it after an update, or swap it for a different one, and every running agent dies with it. That is not a hypothetical failure: agentic development environments churn fast.

**A word on "the census", because this guide leans on it throughout.** The census is the candidate pool behind this document: projects reached through GitHub topic search, GitHub code search and targeted follow-up, with every load-bearing claim checked against source code, release artifacts, or a project's own primary documentation. Its reach has a hard bound — anything not indexed by GitHub code search, including self-hosted forges and unreleased internal tools, is outside it by construction rather than absent from the world (see [Coverage gaps](#coverage-gaps)). Superlatives in this guide ("the only identity-scoped namespace found anywhere") are scoped to that pool and mean nothing beyond it.

That census recorded **six ADEs that died or closed in the eight months before it was written**, and it can name all six: **Crystal** (deprecated February 2026, and it produced *two* descendants rather than one — Nimbalyst, the named successor, and Pane, which still carries a renamed `docs/CRYSTAL_ARCHITECTURE.md`), **Terragon** (shut down January/February 2026), **Roo Code** (archived, last push 2026-05-15, no stated reason), **Vibe Kanban** (sunset 2026-04-24 at 27,622 stars — its second-to-last commit is literally "Add README sunsetting banner"), **DevPod** (abandoned; its last release is `v0.7.0-alpha.34` from 2025-06-23), and **Daytona** (closed-sourced June 2026, leaving 72k stars on a repository whose root now contains only a README and an assets folder). One method rule falls straight out of that list and is worth carrying: **a last-push date more than sixty days old needs a specific check for a shutdown notice, not just a date** — "stale" and "sunset" look identical in repository metadata, and this research conflated them once.

Concretely, the shape you are working against is a **spawn chain**. An **ADE** (Agentic Development Environment — a desktop app that spawns coding-agent CLIs, typically one per git worktree, each in its own terminal pane) spawns the agent today, and in doing so it calls `CreatePseudoConsole` and holds the resulting handle. In this case the ADE is ORCA (`stablyai/orca`, Electron plus node-pty). What you want is one more link in that chain: **the ADE spawns your middle layer; your middle layer calls `CreatePseudoConsole` and holds the `HPCON`; the agent CLI runs as its child.** The usual phrasing — "a layer under the shell and above the agent" — is spatially confusing, because the shell and the agent occupy the same slot and the middle layer is *above* the agent in the spawn tree, not below it. What matters is who holds the handle. The hook point for inserting that link already exists and is verified in source: ORCA's per-agent launch command is overridable through `agentCmdOverrides`, declared in `src/shared/types.ts` and consumed at `src/shared/tui-agent-launch-command.ts:30`, where the lookup is `const override = args.cmdOverrides[args.agent]`. You give it a different command; that command is your middle layer. A worked example of the override entry is in [If you are wrapping under ORCA specifically](#if-you-are-wrapping-under-orca-specifically).

**And a note on "any ADE", because the swap is the entire point.** An override hook like ORCA's is what makes a middle layer insertable at all, so it is worth knowing which other ADEs have one. Among **native-Windows** ADEs the census found four that document a genuine free-form "point me at any executable" hook a third party can use without forking source: **ORCA** (`agentCmdOverrides`); **kandev** (`kdlbs/kandev`, AGPL-3.0 — Settings → Agents → Add TUI Agent, the command string parsed with `strings.Fields`, documented in `docs/public/agents-and-profiles.md`); **Pane** (`dcouple/Pane`, AGPL-3.0 plus attribution — `--tool-command <command>`, documented in `docs/RUNPANE_CLI_CONTRACT.md`); and **Zed** (`agent_servers` in `settings.json` — but ACP-shaped, so the spawned process must speak ACP JSON-RPC rather than own a raw PTY, and that reading was never re-verified in any pass of this research). Three more document an override at least as good and are out on **platform** rather than on override: cmux (`cmux.json`, `cmux hooks setup --agent`; macOS only), superset (the best-documented override of any candidate, but its own README says "Windows/Linux untested"), and sculptor ("run and manage *any* terminal-based agents"; Mac, Linux and Linux-ARM64 downloads only). **The conclusion to carry: override hooks are not rare; native-Windows override hooks are.** Note also which project does *not* have one — Agent Orchestrator, whose 30 compiled Go packages under `backend/internal/adapters/agent/` leave no way to point it at an arbitrary CLI. That matters because its `ao pty-host` subsystem is otherwise the closest architectural match to the layer described here.

Three constraints frame everything that follows, and they are pass/fail. **Native Windows 11, no WSL** — anything POSIX-only, WSL-required, or Linux-container-only is out. **Open source** — commercial tools appear here only as context. **Headless-first** — anything that needs a human attached, or a GUI, to be useful has failed the thing you are actually buying. A fourth consideration is a *weighting* rather than a filter: **cross-platform is a plus, not a requirement**, so Windows-only is a demerit and not a disqualifier. There is a fifth property that is not a constraint at all and *would* kill candidates: **nestability**. Your middle layer runs *inside* the ADE's own PTY, so prefix-key collisions, resize propagation, alt-screen handling, mouse passthrough and double VT parsing are live problems rather than academic ones. Be clear that it has killed nothing yet, though — **double-ConPTY nesting has never been empirically tested for any candidate in this research**, so it is a hazard with no measurements behind it. Every star count, release date and status in this guide is a snapshot taken 2026-08-02; those numbers churn weekly. One rule for re-checking them: read a repository's `pushed_at`, never its `updated_at`, because the latter ticks on stars and watches and flipped a staleness verdict once during this research.

**Every tool in this space is an answer to four questions, and the four are independent of each other.** Read them once; the rest of this guide points back at them by their handles.

1. **Owner** — *who calls the PTY-spawn API.* On Windows that is `CreatePseudoConsole`, and whoever calls it holds the resulting `HPCON` handle, which makes that process the session's owner and the only party in the world that can resize it.
2. **Lifetime** — *whether that owner outlives the client that started it.* This guide grades persistence L0 to L3: L0 dies with the connection, L1 survives a client disconnecting, L2 survives the ADE being killed or upgraded, L3 survives a reboot.
3. **Rendezvous** — *what address the client and the owner meet at.* A named pipe, a loopback TCP port, an AF_UNIX socket, an HTTP endpoint. Note in passing that AF_UNIX has been a genuine Windows transport since Windows 10 1803, so a `UnixListener` in somebody's source proves nothing about platform support in either direction.
4. **Payload** — *what crosses that boundary.* Raw child bytes, or a parsed screen model re-rendered back into ANSI — the answer that decides whether your terminal grid gets built twice on every keystroke.

Answer **Owner, Lifetime, Rendezvous and Payload** for any tool, including ones nobody has written yet, and you know what it is, what it costs you, and which of your problems it leaves untouched. Everything else — verb sets, config formats, star counts, whose Rust it is — hangs off those four answers.

## When you need a session daemon, and when you do not

Reach for a **PTY-owning session daemon** when the agent process must survive the thing that launched it, when a human has to be able to walk up and type into a session that is already running, or when you need to know what is *actually on the screen* — because a TUI's rendered state is the only place some information exists. Reach for a **no-PTY channel** when you only need to start work, observe it, answer its questions and collect its results. That second case is more of the job than it first appears, and the tooling for it is better than the tooling for the first.

**The strongest headless option owns no PTY at all.** `claude -p` with `--input-format stream-json --output-format stream-json` is a full-duplex NDJSON channel over ordinary pipes: you write newline-delimited JSON to stdin, you read newline-delimited JSON from stdout, and there is no console, no ConPTY, no terminal emulator and therefore no nesting problem anywhere in the picture.

```powershell
# Full-duplex NDJSON over ordinary pipes. Drive this from any language that can spawn a process.
claude -p `
  --input-format stream-json `
  --output-format stream-json `
  --verbose `
  --include-hook-events `
  --forward-subagent-text `
  --include-partial-messages `
  --replay-user-messages
```

The flags are documented without platform qualification in the [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference), and `--forward-subagent-text` carries a `parent_tool_use_id` so you can reassemble the subagent tree. **Be clear-eyed about two things.** First, "behaves identically on Windows and Linux" is an *inference*, not a verified measurement: the flags are unqualified and the transport is ordinary pipes, but nobody has run this on both platforms and diffed the output. It is the load-bearing cross-platform claim of the whole no-PTY architecture and it is untested. Second, this is print/headless mode. It **does not attach to an existing interactive TUI** — it is a way to build a middle layer that spawns the agent with no PTY in the first place.

**Hooks are the write path, and they can answer prompts with no human present.** The [hooks reference](https://code.claude.com/docs/en/hooks) documents **five** hook types, not the three that get repeated in blog posts: `command`, `prompt` (an LLM evaluates the decision), `agent` (spawns an agentic verifier), `http` (POSTs the event JSON to a URL and reads the decision out of the response) and `mcp_tool` (calls a tool on an already-connected MCP server), governed by an `allowedHttpHookUrls` policy allowlist. `PreToolUse` returns a `permissionDecision` of allow/deny/ask/defer plus an `updatedInput` that **replaces** the tool's arguments, and the docs state the headless trick outright: "AskUserQuestion and ExitPlanMode require user interaction and normally block in non-interactive mode with the `-p` flag. Returning `permissionDecision: "allow"` together with `updatedInput` satisfies that requirement." The `http` type is the important one architecturally — **your middle layer can BE the endpoint**, a long-lived process you own, which sidesteps the fact that a stdio MCP server cannot hold persistent sessions because the client spawns and reaps it.

Three limits on that, all load-bearing and all easy to miss. *(Citation note for all three: the [hooks reference](https://code.claude.com/docs/en/hooks) is a rendered HTML page with no stable line numbering, so the line numbers below are into a plain-text extraction of it and are given only as a locator. The quoted phrase is the checkable part — search the page for it.)*

First, the hooks reference states — under the hook-type menu, at extracted line 549 and again at line 221 — that **"SessionStart and Setup support command and mcp_tool hooks. They don't support http, prompt, or agent hooks"**, so the two bootstrap events a middle layer most wants to own are exactly where the HTTP-endpoint trick is unavailable. Thirteen events do support all five, including `PreToolUse`, `PermissionRequest`, `Stop`, `SubagentStop` and `UserPromptSubmit`, so the technique is intact where it counts.

Second — and this narrows the remedy for the first, so read them together — the same page states at extracted line 469 that **"MCP tool hooks are available on every hook event once Claude Code has connected to your MCP servers. `SessionStart` and `Setup` typically fire before servers finish connecting, so hooks on those events should expect the 'not connected' error on first run."** The obvious fallback for the bootstrap events is "use `mcp_tool` or `command` there", and half of that fallback is unreliable at exactly those two events. **The only dependably available bootstrap hook type is `command`.**

Third, at extracted line 328: **"As of v2.1.199, an MCP tool whose server marks it with `_meta["anthropic/requiresUserInteraction"]` is stricter: a hook can't skip its approval prompt with 'allow', with or without `updatedInput`"** — the headless-answering trick has an explicit opt-out that individual tool authors control, so a tool you depend on can decide to block you.

**OpenTelemetry is the liveness channel, and it costs you nothing structurally** — it does not touch the PTY, so it survives an ADE swap for free. Claude Code emits **34 named `claude_code.*` identifiers**; note that this is a *mix of metrics, events and spans*, not 34 events, so do not quote it as an event count. The one that matters when no human is watching is `claude_code.tool.blocked_on_user` — "is the agent stuck waiting for someone".

```powershell
$env:CLAUDE_CODE_ENABLE_TELEMETRY      = '1'   # the master switch, and it is NOT an OTEL_* var
$env:CLAUDE_CODE_ENHANCED_TELEMETRY_BETA = '1' # traces, not just metrics
$env:OTEL_LOG_TOOL_DETAILS             = '1'   # content is redacted by default; opt in per-field
```

Three separable things live in that block, and it is worth taking them one at a time.

**The switch.** `CLAUDE_CODE_ENABLE_TELEMETRY=1` is the master switch and it is deliberately *not* an `OTEL_*` variable, which is the single most common way people fail to turn this on. Traces additionally require `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`; the `claude_code.hook` span on top of that requires `ENABLE_BETA_TRACING_DETAILED=1`, a `BETA_TRACING_ENDPOINT`, and org allowlisting. `TRACEPARENT` is inherited by both Bash and PowerShell subprocesses — but the hooks reference warns (extracted line 152) that **"Claude Code removes `OTEL_*` exporter variables from every subprocess it spawns, including hooks,"** so your telemetry config does not reach grandchildren and you must re-establish it there yourself.

**The redaction defaults.** Content is redacted by default and you opt in field by field: `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`, `OTEL_LOG_ASSISTANT_RESPONSES` and `OTEL_LOG_RAW_API_BODIES` — the last of which has a `=file:<dir>` mode that writes untruncated request and response bodies to disk behind a `body_ref` path. Turn that one on deliberately or not at all.

**The transcript tree.** Alongside telemetry there is a durable record: the JSONL transcripts under `~/.claude/projects/<project>/<session>.jsonl`, which are a **tree, not a file**. Inspecting one on native Windows 11 (build 26200) shows a sibling `<session-uuid>/` directory holding `subagents/agent-<id>.jsonl` plus `agent-<id>.meta.json` sidecars carrying `{agentType, description, toolUseId, spawnDepth}`, alongside `tool-results/` and `workflows/` — so the subagent fan-out topology is readable from the filesystem alone. These internals are undocumented and version-fragile; `CLAUDE_CONFIG_DIR` relocates the whole tree and `cleanupPeriodDays` garbage-collects it, so anything treating JSONL as durable needs its own retention policy.

**So state plainly what PTY ownership buys that none of the above can — and be careful with the usual formulation, because the obvious one is false.** It is tempting to say PTY ownership buys "the exact on-screen state". It does not: **reconstructing on-screen state requires the byte stream plus a VT emulator, not a PTY.** asciinema's relay does exactly that and never touches a PTY — its own [streaming documentation](https://docs.asciinema.org/manual/server/streaming/) states that "the server maintains comprehensive state for each active stream by running the whole stream through asciinema's own virtual terminal emulator." What PTY ownership buys is one step upstream: **the byte stream itself** — the bytes a full-screen TUI paints, which it paints only because something is presenting itself as a terminal to it, and which appear in no structured event anywhere. Given those bytes, anyone with an emulator can derive the screen. So the two things are: **the byte stream of a program that insists on a terminal**, and **a human being able to type into a live session**. If neither is on your requirements list, the no-PTY architecture dominates and most of this guide is optional reading — every hard Windows problem in it (the ConPTY startup handshake, nesting, prefix-key collisions, resize propagation, double VT parsing) simply does not arise, because you never own a PTY. If either one is on the list, no amount of structured-event plumbing substitutes, and you are shopping for a daemon.

**Before you build anything, check whether Windows already does it.** A disconnected RDP session keeps every process running with a live console, and you reattach by reconnecting; `tscon` moves a session between connections. That is persistence plus reattach, in the box, with no third-party code. It fails you on granularity — it is whole-session, so there is no per-worktree agent tab — and [Microsoft's `tscon` documentation](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tscon) states "You can't connect to the console session" and "You must have Full Control access permission or Connect special access permission". (The often-repeated companion claim that client SKUs allow only one interactive session is *not* on that page and no separate source for it was recorded here; treat it as folklore worth checking against your own SKU before you plan around it.) But if your real requirement is "my long-running work should not die when I close the laptop lid," measure this before writing a line of Rust.

**Do not plan around this being solved upstream.** [#24365](https://github.com/anthropics/claude-code/issues/24365) — "Expose ACP over network transport (`claude serve`) for remote…", an unambiguous network-attach request — was stale-bot-closed on 2026-03-14 and locked on 2026-03-21, with 3 total reactions and 3 of its 4 comments from bots. That one closure is what the conclusion rests on. A second issue, [#6686](https://github.com/anthropics/claude-code/issues/6686), is often cited alongside it and carries less weight than it looks: it was closed `not_planned` on 2026-02-09 despite 551 reactions, but its title is "Feature Request: Add support for Agent Client Protocol (ACP)" — plain ACP support, not network attach — and Claude Code is an ACP implementer today, so that request was closed `not_planned` and the feature shipped anyway. **Read the record as declined once, clearly, on the thing you care about**, rather than as declined twice. Either way it is a weak bet that Claude Code grows a natively network-attachable session, which is precisely what strengthens the case for an external layer that does not depend on it.

## How to read this document

The rest of this guide is organised by option, not by verdict. Each candidate gets the same treatment: what it is, how it works, the commands to install and drive it, and the specific way it fails in the real world. Read the framing section above and the playbook at the end; read the option sections that survive your own answers to **Owner, Lifetime, Rendezvous and Payload**. There is no ranking here, because the ranking depends on which of the four you cannot compromise on — and the playbook opens with [a filter ladder](#run-your-own-constraints-as-a-filter-first) that turns your answers into a shortlist mechanically.

**One convention for every command block in this guide.** Where the shell matters, the target is **PowerShell 7+ (`pwsh`)**. Windows PowerShell 5.1 differs in two ways that bite here: `Add-Type -MemberDefinition` behaves the same but `*>` stream redirection and the default `[Console]::OutputEncoding` do not, and the latter can silently mangle UTF-8 on a pipe into a native executable. Where a block spells out `powershell.exe`, that is deliberate and the reason is stated in place.

| Section | What is in it |
|---|---|
| [When you need a session daemon, and when you do not](#when-you-need-a-session-daemon-and-when-you-do-not) | The no-PTY channel, what PTY ownership uniquely buys, and what Windows already gives you for free |
| [How a persistent terminal session actually works on Windows](#how-a-persistent-terminal-session-actually-works-on-windows) | ConPTY's startup handshake, the flags that mislead, who owns the handle, the nesting hazards, and PowerShell probes for every one of them |
| [Ten axes for placing any tool, including ones that do not exist yet](#ten-axes-for-placing-any-tool-including-ones-that-do-not-exist-yet) | The checks that outlive this census, a placement matrix, a worked example, and seven traps that will misclassify a tool |
| [The seven standalone daemons](#the-seven-standalone-daemons) | psmux, Zellij, rmux, herdr, oly, qscreen, quil — install commands, transports, and each one's characteristic failure |
| [Three that live inside a larger product](#three-that-live-inside-a-larger-product) | `wezterm-mux-server`, OpenCode's undocumented `/pty` API, and `ao pty-host` — working code you extract rather than install |
| [The PTY-as-a-service lineage](#the-pty-as-a-service-lineage-terminal-over-http-websocket-or-ssh) | terminado, ttyd, upterm, gotty, Eclipse Theia, ghostel, and the two reference implementations worth reading even though you cannot run them |
| [Interface shapes: the eight ways a middle layer can be driven](#interface-shapes-the-eight-ways-a-middle-layer-can-be-driven) | CLI verbs, tmux control mode, binary wire protocols, HTTP/WS, MCP, JSON-RPC, SSH, and the no-PTY NDJSON channel |
| [The verb set an ADE-agnostic middle layer has to expose](#the-verb-set-an-ade-agnostic-middle-layer-has-to-expose) | The ten verbs every candidate converged on independently, plus namespacing and auth |
| [The convergence: three ecosystems, one shape](#the-convergence-three-ecosystems-one-shape) | A coding agent, a MUD engine and a Lisp REPL arriving at the same architecture |
| [What does not exist](#what-does-not-exist) | The standards, ports and guarantees you would otherwise spend a week searching for |
| [The column that can disqualify every PTY candidate at once](#the-column-that-can-disqualify-every-pty-candidate-at-once) | "Verbs with no console attached" — untested everywhere, two hours to settle |
| [Comparison tables](#comparison-table-candidates-that-own-a-pty) | Three of them: PTY owners, the PTY-as-a-service lineage, and the POSIX-only ancestors |
| [What this does not solve](#what-this-does-not-solve) | Containers, late attach, the node-pty defects live in ORCA today, unauthenticated local IPC, and the platform's own limits |
| [The playbook: what to pick and how to verify](#the-playbook-what-to-pick-and-how-to-verify) | The decision that matters most, then situation by situation |
| [The verification ritual](#the-verification-ritual) | The five steps that prove a session really survived. A success message from the tool proves nothing |
| [Open questions](#open-questions) | Twenty-six, each with a next step, a cost, and what the answer changes — plus the order to run the first three in |
| [Coverage gaps](#coverage-gaps) | The inferences flagged as inferences, and everything nobody has run |
| [Primary sources by category](#primary-sources-by-category) | Grouped so you can re-verify without redoing the research |

## How a persistent terminal session actually works on Windows

Before any tool in this guide makes sense, you need the mechanism. Almost every wrong intuition about middle layers on Windows comes from importing a Unix mental model that does not apply.

On Unix, a pseudo-terminal is a **pair of file descriptors** created out of `/dev/ptmx`. The master end is a file descriptor like any other: you can `dup` it, pass it over a Unix socket to another process, inherit it across `fork`, and hand ownership of a live session from one program to another. On Windows there is no such pair. [`CreatePseudoConsole`](https://learn.microsoft.com/en-us/windows/console/createpseudoconsole) returns an **`HPCON`** — an opaque handle to a **console host process** that the OS spawns on your behalf (a headless `conhost.exe`, or `OpenConsole.exe` if you bundle one), which sits between your two anonymous pipes and the child, translating a VT byte stream into classic Windows console API calls and back. Three properties of that arrangement generate every consequence in this section: **the console is a process, not a file**; **the handle belongs to whoever created it**, and is not something you pass around; and **the console is a multi-client object** that several processes can be attached to at once. Get those three right and the rest of the Windows story is derivable.

### Why the POSIX multiplexers cannot be ported

You will not find tmux on native Windows, and you will not find a port of it. What the census contains is **reimplementations of tmux's verb set** — psmux (a Rust tmux-workalike), rmux (90+ tmux-compatible verbs) — written from scratch on ConPTY. That is not an accident of nobody trying; it falls out of the three properties above, and the ancestors say so in their own words. GNU screen's original beta-test README states the dependency directly: "Since 'screen' uses pseudo-ttys, the select system call, and UNIX-domain sockets, it will not run under a system that does not include these features of 4.2 and 4.3 BSD UNIX". That file is preserved as an artifact in [`Orc/screen`](https://github.com/Orc/screen) — and two provenance details are worth stating, because the usual retelling gets both wrong: **the file carries no date**, and the distribution channel it names is **`mod.sources`**, not `net.sources`. dtach's [README](https://github.com/crigler/dtach) is narrower and just as fatal: it "assumes that the host system uses POSIX termios, and has a working forkpty function available". And reptyr — the POSIX answer to the structurally identical problem of grabbing the I/O of a process you did not spawn, via `ptrace` — has **no Windows analogue after 10+ years**, and the research located no attempted port; read that as evidence the platform makes it hard rather than as proof the niche is empty, because absence of a port is absence of evidence.

The three missing pieces, concretely: there is no `forkpty`; there is no master fd to hand to a second process, only an `HPCON` bound to its creator; and **there is no `SIGWINCH`** (see the fourth item below). The causal chain from those three to "no port exists" is reasoning, not a maintainer's statement — but each link is verified independently, and every Windows-native candidate in this guide behaves exactly as the chain predicts.

### AttachConsole, and what "multi-client object" buys you

A Windows console is a shared object. Multiple processes attach to one console; [`GetConsoleProcessList`](https://learn.microsoft.com/en-us/windows/console/getconsoleprocesslist) enumerates them; and [`AttachConsole(pid)`](https://learn.microsoft.com/en-us/windows/console/attachconsole) lets a process with no console of its own join the console that some other process is already using. That is the entire reason a "late attach" story looks plausible on Windows when it is impossible on Unix — the object you would need to join genuinely is joinable.

Two hard constraints bound it, and both are documented rather than folklore. **A Win32 process can own only one console at a time**, which is why the single working late-attach control loop found anywhere ([`reubenlavin08/cc-discord-remote`](https://github.com/reubenlavin08/cc-discord-remote), MIT, 0 stars, dormant since 2026-06-08, one 159 KB `bot.py`) spawns a throwaway `console_helper.py` per operation rather than corrupt its own stdio. And **reading is gated by integrity level**: in [microsoft/terminal#5468](https://github.com/microsoft/terminal/issues/5468) — created 17:14:15 and closed `Resolution-By-Design` at 17:21:46, seven minutes later — DHowett-MSFT wrote "A lower-integrity process is not allowed to read the console output of a higher-integrity console. **In general, there is no reason to ever use the ReadConsoleOutput API.**" Note the rule is *directional*: same-user, same-integrity siblings (which an ADE's children are) are unaffected; it bites only for elevated agents, cross-user, or session 0.

Microsoft's stance on the write half is blunter still, and the attribution matters because it comes from two separate callouts on [the `WriteConsoleInput` page](https://learn.microsoft.com/en-us/windows/console/writeconsoleinput). The **Important** banner calls the API "console platform functionality that is **no longer a part of our ecosystem roadmap**". A separate **Tip** in Remarks says: "This API is not recommended and does not have a virtual terminal equivalent… This operation is considered the **wrong-way verb** for this buffer. Applications remoting via cross-platform utilities and transports like SSH **may not work as expected** if using this API." [The classic-vs-VT page](https://learn.microsoft.com/en-us/windows/console/classic-vs-vt) names the class: input injection and output scraping "provide a vector to cross security and privilege-levels or domains". `AttachConsole` itself survives in the still-condoned exceptions list, for process bookkeeping.

**The characteristic failure of the late-attach path** is that it half-works, convincingly, and then does not. [pywinauto#492](https://github.com/pywinauto/pywinauto/issues/492), filed by a pywinauto maintainer in 2018 and still open, records his own 2022 empirical attempt: `AttachConsole` succeeded, `ReadConsoleOutputCharacter` returned **ten spaces**, and it did not work at all against `cmd.exe` or PuTTY. The mature implementations each pick one half and never both: [**NVDA**](https://github.com/nvaccess/nvda) late-attaches but only ever reads (`winConsoleHandler.py`, `AttachConsole(processID)` + `GetConsoleProcessList(2)` + `ReadConsoleOutputCharacter`), and it is a shipping, actively-maintained screen reader rather than a demo — the code claim is what the repository link supports; how widely deployed NVDA is has no source here. [**winpty**](https://github.com/rprichard/winpty) and **wexpect** read *and* write but own the console from birth, so they never call `AttachConsole` at all. Every half has a production implementation and the halves never combine — which is the shape of the finding, rather than a reusable library you can pick up. `cc-discord-remote`'s own notes fill in the rest: `ReadConsoleOutputCharacter` sees **only the visible viewport, never scrollback**; concurrent human typing plus programmatic writes garble the transcript, so it enforces "one client per session at a time"; and "the JSONL format and session-registry layout are undocumented internals". It documents its constraints as workarounds rather than solutions, which is what makes it worth citing for engineering notes and not worth taking as a dependency.

**And winpty deserves a paragraph of its own, because its life story is the argument for ConPTY.** [`rprichard/winpty`](https://github.com/rprichard/winpty) (1,380 stars, MIT, last push 2024-02-19) is the pre-ConPTY answer: `ReadConsoleOutputW` plus `WriteConsoleInputW`, wrapped into a reusable read-and-write loop and **exposed over named pipes** — exactly the shape a middle layer wants. It shipped for a decade inside Git for Windows, MSYS2, Cygwin, pywinpty and node-pty's winpty backend, and it is now dormant and superseded. **Its existence-and-supersession is the cleanest single argument for building on ConPTY rather than on console scraping.** One live residue is worth knowing about because it is a real escape hatch: VS Code's own workaround for the node-pty `AttachConsole` crash is the setting `terminal.integrated.windowsEnableConpty: false`, which falls back to winpty. If you ever see that setting recommended, that is what it does.

Also worth naming rather than conflating: late attach is not a *nested* topology at all. It is an out-of-band, sideways-reaching daemon — a different shape from every other option in this guide.

### Who owns the session: whoever called the PTY-spawn API

**Whoever calls `CreatePseudoConsole` owns the `HPCON`, and the `HPCON` holder is the only party that can resize the console.** There is no transfer, no fd-passing, no adoption. Every working implementation in the census — psmux, Zellij, rmux, herdr, oly, qscreen, quil, `wezterm-mux-server`, `ao pty-host`, upterm — spawns its own child and holds the handle from birth. That is not a stylistic convergence; it is the only pole that works.

One apparent counterexample deserves killing, because it gets re-derived every time someone re-researches this: **node-pty was thought to prove late-attach works. It does not.** In `src/windowsPtyAgent.ts:149`, `this._innerPid = connect.pid;` — the PID it hands to `AttachConsole` is the process **node-pty spawned itself**. It re-enters its own child's console from a disposable fork. It is another own-from-birth system.

The consequences for you are three, and they are the reason the rest of this guide is shaped the way it is:

- **Insertion has to happen at spawn time.** If your middle layer is going to own the PTY, the ADE must launch it — which is exactly what an overridable per-agent launch command such as ORCA's `agentCmdOverrides` (`src/shared/types.ts`, consumed at `src/shared/tui-agent-launch-command.ts:30`) is for. There is no supported way to slide underneath an agent that is already running.
- **Late attach is a read-only escape hatch at best**, per the evidence above. It is fine as an out-of-band inspection trick; it is not a foundation.
- **Two boundaries are believed to block it entirely, and both are inference.** That a foreign-SID console is not `AttachConsole`-able, and that the session-0 boundary blocks `AttachConsole` (relevant if you were thinking of hosting the middle layer as a Windows Service, which runs in session 0 as SYSTEM while you and the ADE run in session 1+), are both *inferred* from two documented facts — console objects are per-session, and the call takes a PID — and **neither has ever been observed to fail**. Treat them as strong priors, not as measurements. The service route has a second, established problem anyway: agent CLIs authenticate from the user profile (`~/.claude/`, `~/.codex/auth.json`), which a SYSTEM service does not have.

### The four things a middle layer must get right on Windows

This is the build spec. Get these four wrong and the layer either stalls, hangs, renders blank, or silently runs at the wrong size forever.

**1. Answer ConPTY's startup handshake, or eat multi-second stalls.** When you create a pseudo-console, *you* are the terminal on the other end of those pipes, and ConPTY expects you to behave like one. It opens by sending **DA1** — the `CSI c` "primary device attributes" query, meaning "what kind of terminal are you?" — and it waits for your reply.

*Citation status first, because it changes how you should read the quotes.* All of the quotes below are verbatim and were read in full, but they live in comments on [microsoft/terminal#7019](https://github.com/microsoft/terminal/issues/7019), which is **closed as `not_planned` since 2023-09-29**, was created 2020-07-22, and is titled *"conpty exhibits pathological performance on scrolling region redraw (repaints entire screen)"*. Post-closure comments from maintainers are legitimate evidence; the state is disclosed so nobody mistakes this for an open, tracked commitment.

lhecker (MSFT), in a comment dated 2026-06-10: "it sends you a DA1 request, which you're expected to respond to, because you're using a PTY, not just setting up any random pipes. **It waits 3s for a response.** It's not multiple queries with 1s waits each." DHowett (MEMBER), in the same issue: "If you have the ability to answer them, _answer them._ If you do not… that would mean you are not a terminal emulator."

A measured data point in the same thread took startup from **2121 ms to 142 ms** by answering instantly. **That measurement is a third-party application developer's** (the commenter `Eyalm321`), **not a Microsoft benchmark** — a distinction that is easy to lose by filing it among the Microsoft attributions.

**Characteristic failure:** every single spawn costs about two seconds instead of about 140 ms, and it looks like general slowness rather than a protocol bug, so it gets blamed on the agent CLI.

Of the small candidates, **psmux verifiably answers the handshake** — it has a dedicated regression test at `tests-rs/test_cpr_responder.rs`.

**oly is widely credited with answering it too, and reading the code shows that is wrong in the case that matters.** The function usually cited is `extract_query_responses_no_client`, in `src/session/pty.rs`, and it does answer terminal-capability queries with no client attached — but it answers **CPR, DSR and the OSC 10/11 colour probes**, and its own comment lists what it deliberately excludes: "**Do NOT respond to: PrimaryDeviceAttributes (DA1)**, SecondaryDeviceAttributes (DA2), XtVersion (XTVERSION), DecPrivateModeReport (DECRPM), KittyKeyboard… These should only be answered by a real terminal or interactive client. Answering them in detached mode can cause interference with user input and corrupt the output stream." There is a unit test asserting exactly that. oly *can* emit a DA1 reply — the generator produces `\x1b[?62;c` — but not on the detached path. **DA1 is the query that costs you the three seconds**, so on oly's detached path the stall is not answered away; it is deliberately left to whoever is upstream. That is a defensible design choice about not corrupting a byte stream, and it is not the same claim as "oly answers ConPTY's startup handshake". Do not carry the shorter version.

Nothing is known either way about the other five daemons. This is the single most load-bearing design requirement of the four: get it wrong and every spawn costs seconds, or hangs.

**2. Do not set `PSEUDOCONSOLE_INHERIT_CURSOR` unless you can answer `ESC[6n` fast.** `ESC[6n` is **CPR**, the cursor-position report request; the expected reply is `CSI row ; col R`. The flag is value `0x1`, and it is one of only **three `dwFlags` consumers** in current ConPTY — three read sites spanning four bits, `0x1`, `0x08`, `0x10` and `0x20` (see the next subsection). The clearest statement of the hazard is in psmux's vendored PTY layer, `crates/portable-pty-psmux/src/win/psuedocon.rs:125-133` — the misspelled filename is the source's, the Windows symbol is spelled `PSEUDOCONSOLE_INHERIT_CURSOR` — which **deliberately drops the flag** and carries a dedicated regression test. Its comment: "With it, conhost emits an `ESC[6n` cursor-position request at startup and will not service a child's console connection until the host answers it. So if that reply is sent later than the child's connect attempt, the child blocks in `ConsoleCreateConnectionObject` during process initialization (a single thread, before any user code runs) until the reply arrives: a temporary stall if it is merely late, **indefinite if it never comes**."

**Characteristic failure:** the agent never starts and never prints anything, because it is wedged inside process initialisation before a line of its own code runs — there is nothing to attach a debugger to and nothing in its logs. **WezTerm sets this flag; node-pty sets it when `inheritCursor` is passed.** If your middle layer sets it, you have taken on a hard real-time obligation to answer CPR before your child's connect attempt.

**3. Load a bundled `conpty.dll` by absolute path, or not at all.** psmux refuses sideloading entirely, and its comment at `psuedocon.rs:45-51` explains why: "terminal emulators like WezTerm bundle their own conpty.dll + OpenConsole.exe, and the DLL search order can pick those up when psmux runs inside such a terminal. Using a foreign conpty.dll causes blank panes and broken I/O."

The hazard is real but specific to *how* you load, and the census splits cleanly on that. **Hijackable:** WezTerm's `portable-pty` uses a bare relative name, `Path::new("conpty.dll")`. **Safe:** quil (`filepath.Join(filepath.Dir(exe), "conpty.dll")`) and node-pty (`PathCombineW(currentDir, L"conpty\\conpty.dll")`) both resolve absolute paths. Note node-pty resolves a *different export name* on the bundled path (`ConptyCreatePseudoConsole` rather than kernel32's `CreatePseudoConsole`), and that `ClearPseudoConsole` is bundled-only.

**Characteristic failure:** blank panes and broken I/O, appearing only when your layer happens to be launched from inside a terminal that ships its own ConPTY — so it reproduces on one developer's machine and not another's.

Bundling is still the right call, but for a soberer reason than "Microsoft endorses it". In the same #7019 thread (again: closed `not_planned` since 2023-09-29), DHowett's recommendation of the ConPTY NuGet package is a **refusal to backport**: "I'm sorry. When we backport… The architectural shift in ConPTY as of 1.22 is too broad for us to adequately contain. Use the NuGet package; it updates way faster than Windows." The instruction is the same — bundle it — but the reason is that fixes will *not* reach the in-box ConPTY, which is a stronger argument for bundling and a weaker one about blessing. (Precision on the citation: that comment says only "the NuGet package". The package identifier usually quoted alongside it, `Microsoft.Windows.Console.ConPTY`, **does not appear anywhere in #7019** and carries no separate source here — the refusal-to-backport reading is what the thread supports; confirm the package name on NuGet before you put it in a manifest.) quil (`scripts/fetch-conpty.sh`, SHA256-pinned), node-pty (`third_party/conpty`, 1.25.260303002), WezTerm and ghostel all bundle it.

Two live caveats on the bundled path. **The ABI has drifted**: node-pty declares `ConptyClearPseudoConsole(HPCON hPC)` while `microsoft/terminal src/inc/conpty-static.h:44` declares `ConptyClearPseudoConsole(HPCON hPC, BOOL keepCursorRow)` — a one-argument call against a two-argument export, on the `useConptyDll` path. Drift runs both ways: node-pty also declares `ConptyClosePseudoConsoleTimeout`, which the current public header does not export. And **no compatibility matrix exists**, from Microsoft or anyone, for running a newer bundled `conpty.dll` / `OpenConsole.exe` against an older or locked-down Windows Server Core or LTSC host.

**4. Resize does not propagate by itself — there is no `SIGWINCH` analogue.** [`ResizePseudoConsole(HPCON, COORD)`](https://learn.microsoft.com/en-us/windows/console/resizepseudoconsole) is an explicit call made by whoever owns the handle. A child console app only learns about it by reading a `WINDOW_BUFFER_SIZE_EVENT` off its console input buffer — which a byte-stream-only consumer never sees. So resize is a message you must route yourself, at every hop, or it silently does not happen.

Two shipping solutions exist, and they take opposite approaches:

- **psmux's pipe mode asks the outer terminal in band**, using XTWINOPS `CSI 18 t` ("how big are you?"), waiting 500 ms for a `CSI 8 ; rows ; cols t` reply and **falling back to a hardcoded 120x30** if none arrives (`src/ssh_input.rs:2016-2039`, `src/main.rs:4112-4130`).
- **Zellij polls.** It calls `crossterm::terminal::size()` every 50 ms on the VT-reader path (`zellij-client/src/os_input_output_windows.rs:95` doc-comment, `:176` sleep), and separately runs a 100 ms poller at `:38`/`:52`.

**Characteristic failure, and it is a silent-corruption class rather than a cosmetic one:** whether Electron/xterm.js answers `CSI 18 t` by default is **unknown** — xterm.js gates `windowOptions` behind opt-in flags. If it does not answer, psmux's pipe mode runs at 120x30 forever and every TUI inside it wraps against a size nothing on screen agrees with.

The purest instance of the failure is [`Watfaq/PowerSession-rs`](https://github.com/Watfaq/PowerSession-rs), an asciicast recorder on ConPTY (MIT, 295 stars, pushed 2026-07-24, Windows-only): it calls `CreatePseudoConsole` once, sized from `GetConsoleScreenBufferInfo` at startup, and **never calls `ResizePseudoConsole` anywhere** — a repo-wide symbol search returns zero hits, so a mid-recording resize of the outer pane cannot propagate. **Split the evidence from the citation on that one, because they are at different strengths:** the finding was made by reading the ConPTY backend at source, but the exact file and line were not recorded when it was made and could not be recovered afterwards. Treat the behaviour as verified and the pointer as missing. Two more things about that project generalise past it: its own open issue #272 records that it may not honour `ASCIINEMA_SERVER_URL` and that `upload` is not gated behind `auth`; and more importantly, **a recorder captures everything that transits the PTY, including secrets.** That warning applies to every scrollback-replay and session-recording candidate in this guide, not just to this one.

The node-pty ABI drift in item 3 bears on this item too: a stale one-argument prototype against a two-argument export is exactly the kind of mismatch that surfaces as a resize or a clear that silently does nothing.

### The creation flags: one live, two dead, one actively harmful

You will be tempted to copy a flag list from another project. Do not, without checking it against the current implementation, because three of the commonly-copied bits are wrong today.

The complete set of `dwFlags` consumers in `microsoft/terminal src/winconpty/winconpty.cpp` is three lines:

```cpp
169: const auto inheritCursor   = (dwFlags & PSEUDOCONSOLE_INHERIT_CURSOR)   ? L"--inheritcursor "   : L"";
170: const auto ambiguousIsWide = (dwFlags & PSEUDOCONSOLE_AMBIGUOUS_IS_WIDE) ? L"--ambiguousIsWide " : L"";
173: switch (dwFlags & PSEUDOCONSOLE_GLYPH_WIDTH__MASK)
```

A code search over the repository returns **zero hits each** for `PSEUDOCONSOLE_RESIZE_QUIRK`, `PSEUDOCONSOLE_WIN32_INPUT_MODE` and `PSEUDOCONSOLE_PASSTHROUGH_MODE`. The current public flag list in `src/inc/conpty-static.h` is `INHERIT_CURSOR (0x1)`, `GLYPH_WIDTH__MASK 0x18` / `GLYPH_WIDTH_GRAPHEMES 0x08` / `GLYPH_WIDTH_WCSWIDTH 0x10` / `GLYPH_WIDTH_CONSOLE 0x18`, and `AMBIGUOUS_IS_WIDE (0x20)`. Three consequences:

1. **Passing `0x2 | 0x4` is a no-op.** A middle layer on `portable-pty` confers no flag advantage over an ADE on node-pty. If you have read somewhere that it does, delete the claim.
2. **Passing `0x8` is actively harmful.** `switch (dwFlags & 0x18)` matches `case PSEUDOCONSOLE_GLYPH_WIDTH_GRAPHEMES (0x08)`, so anything still ORing the stale `PASSTHROUGH_MODE` value **silently selects grapheme-based width measurement**. The dead symbol appears in **148 files** in a global GitHub code search for `PSEUDOCONSOLE_PASSTHROUGH_MODE` — including psmux, `Sora-bluesky/winsmux`, `aws/amazon-q-developer-cli` and vibetunnel — so it is propagating through the exact candidate pool you are shopping in. (That count is a snapshot from one search on one date and no query string or platform was recorded with it; re-run the search rather than quoting the number.)
3. **`win32-input-mode` as a creation flag is dead; as a mode it is alive.** It is negotiated in band at runtime with `CSI ?9001h`, not requested at creation.

**The method rule this produced, and it generalises:** when you find a flag or a `#define`, check the **consumer**, not the header. Absence from a public header proves only "undocumented" — `0x2` and `0x4` are equally absent from that header and were treated as live features for years. Presence in a header proves nothing about whether anything reads it.

### Nesting: your middle layer runs inside the ADE's ConPTY

This is the topology you are actually buying into: the ADE spawns your middle layer through node-pty (so, a ConPTY), and your middle layer spawns the agent through a second ConPTY. Five things about that stack behave differently from the single-layer case.

**Nesting itself is a designed, negotiated scenario, not an accident.** Microsoft's own keyboard-handling spec (`microsoft/terminal doc/specs/#4999 - Improved keyboard handling in Conpty`, lines 299-322) works through the chain `WT → conpty[1] → wsl → conpty[2] → cmd.exe`: "Conpty[2] will ask for `win32-input-mode` from conpty[1] when conpty[2] first boots up. As conpty[1] is just a conhost that knows how to handle `win32-input-mode`, it will switch its own VT input handling into `win32-input-mode`." The same spec confirms the cost is by design: each layer re-encodes `INPUT_RECORD`s to VT and back.

**Double VT parsing is no longer an OS-level problem, and the conclusion that it is has been retired.** [microsoft/terminal PR #17510](https://github.com/microsoft/terminal/pull/17510), merged and closed 2024-08-01T20:38:11Z under the title "A minor ConPTY refactoring: Goodbye VtEngine Edition", states: "any VT output that an application generates will now be given to the terminal **unmodified**." Issue #1173 closed as `completed` at 2024-08-01T20:38:13Z — **two seconds later**. Since August 2024, ConPTY passes application VT output through unmodified by default.

**What is still lost at each hop is your own doing, and it is a design choice you make.** There are three poles for terminal-state ownership, and only one of them costs you fidelity.

- An **opaque relay** keeps no screen model. dtach's README states it plainly: "dtach does not have a terminal emulation layer, and passes the raw output stream of the program to the attached terminals." Nothing is lost in transit; nothing can be redrawn on reattach either.
- A **full VT owner** parses every escape into a grid and re-emits rendered ANSI. screen, tmux, Zellij, psmux's TUI mode and herdr are here. This is the pole where a nested layer becomes a second renderer.
- **Parallel model with a raw live path** keeps a VT model for snapshots, resize bookkeeping and scrollback while shipping **raw child bytes** on the live path: qscreen's `AttachMode::Bytes` (`crates/qscreen-protocol/src/lib.rs:56-61`), oly's `ServerMessage::Data { data: Vec<u8> }` (`src/http/ws.rs:36-46`), quil's `PaneOutputPayload { Data []byte }` (`internal/ipc/protocol.go:204-208`), and psmux's `-CC` `%output` pane-output ring (`src/server/mod.rs:1222-1227`).

*Vocabulary, once, because it recurs:* **`-CC` is tmux's control mode** — a line-based machine protocol in which the client sends tmux commands on stdin and the server answers with `%begin` / `%end` / `%output` lines on stdout, so the outer program owns rendering while tmux owns sessions. It gets its own treatment among the interface shapes below.

**The test that places any tool: does the live-path payload type carry `bytes` / `Vec<u8>` / `[]byte`, or a string?** In the third pole the ADE's own xterm.js can be the only VT parser in the chain while the daemon still replays scrollback on reattach.

**One entry in that third pole needs its asterisk stated here rather than buried.** psmux's `-CC` `%output` ring is *octal-escaped*, which is a byte-oriented encoding, and that is why it is placed in the third pole. But the drain that feeds the escaping runs `String::from_utf8_lossy(&bytes)` first, at `src/server/mod.rs:1225` — **the bytes are already destroyed before they are escaped.** So psmux `-CC` is in the third pole by design intent and in the second pole by the strict payload-type test. Where this guide later tells you to prefer wires that carry `bytes`, psmux `-CC` does not qualify on the strict reading, and you should know which reading you are relying on.

**String-typed wires lose bytes, permanently, and this is the most under-appreciated failure in the field.** psmux does `String::from_utf8_lossy(&bytes)` on each ring drain before escaping (`src/server/mod.rs:1225`), so a multi-byte character split across two drains becomes U+FFFD **and stays that way**. The same class of bug is in OpenCode's `/pty` wire (`packages/core/src/pty/protocol.ts`): its frames are described as "raw UTF-8 terminal chunks" but the payload type is a JS `string`, and `chunks(data: string)` slices at `REPLAY_CHUNK = 64 * 1024` using `String.slice` — i.e. **UTF-16 code units**, so a surrogate pair straddling a replay-chunk boundary is split into lone surrogates; meanwhile `decodeInput` uses `new TextDecoder("utf-8", { fatal: true })` inside a `try { … } catch { return undefined }`, so **invalid UTF-8 on the input path is silently dropped**, as the file's own comment says. This is a property of string-typed terminal transports generally, not one project's defect. It matters here because agent CLIs emit heavy Unicode: the `✳` in Claude Code's own window title already broke quil's emulator.

**Control-mode corruption — the finding, with its antecedent restored.** psmux's maintainer, in `src/main.rs:4188-4193`: "**When running over SSH with a ConPTY console**, Windows ConPTY silently consumes DCS escape sequences (including the `\x1bP1000p` that iTerm2 uses to detect tmux control mode) and also interleaves its own cursor positioning sequences into the output, **corrupting the line-based protocol**." The remedy the source gives is likewise SSH-specific: "the SSH client must disable PTY allocation so that stdin/stdout are raw pipes: `ssh -T user@host tmux -CC`."

**The generalisation is inference, not the source's claim, and it should be labelled as such wherever it is repeated.** The mechanism — ConPTY eating DCS and injecting cursor sequences — plausibly generalises to any ConPTY sitting between a `-CC` server and its client, including a node-pty one. The source does not say that. Two independent pieces of evidence make the inference a reasonable prior rather than a guess: lhecker's note on #7019 that passthrough-mode ConPTY "already injects VT sequences into stdout irrespective of the VT parser state", and [microsoft/terminal#19621](https://github.com/microsoft/terminal/issues/19621), filed by DHowett (MEMBER) and **open**: "This will impact tmux control mode, as ConPTY will send `\x1B` to terminal and promptly terminate the in-flight exchange. All in-band signaling from ConPTY must be suppressed when passing through a DCS." So passthrough — the fix for double parsing — makes this particular bug worse.

<a id="test-the-cure-before-the-disease"></a>

**Test whether the cure is reachable before you test whether the disease exists. This is the canonical statement of that rule; everywhere else in this guide points back here.** The documented remedy for `-CC` corruption is "give the child raw pipes". An Electron ADE that spawns through node-pty spawns through a ConPTY, always. So the prior question is not "does ConPTY corrupt `-CC` in my topology" but **"can an overridable launch command produce a raw-pipe child at all?"** — because if it cannot, the corruption question is moot, `-CC` control mode is simply unavailable in this topology regardless of what a corruption test would have found, and psmux drops to its plain CLI verbs. Two hours of reading ORCA's spawn path settles the prior question (Q1a); an afternoon settles the corruption question (Q1); and the cheap one can make the expensive one unnecessary. Both are in [Open questions](#open-questions) below.

Second-order, and a straight hit against cross-platform uniformity: psmux's own `docs/control-mode.md:391` records that "ConPTY may normalize line endings and process certain cursor movement sequences internally. `%output` data may look slightly different from what a Unix tmux session would produce."

**Resize desync between layers is unfixable from outside, per Microsoft.** [microsoft/terminal#15976](https://github.com/microsoft/terminal/issues/15976) was promoted to a megathread — "we're promoting this to a megathread cause this is a Hard problem" — and the in-process ConPTY spec (`doc/specs/#13000`, lhecker) names it "**unsolvable**" in the current architecture: the drift is between **ConPTY's buffer and the hosting terminal's buffer, two separate processes**, and a named MUTEX is explicitly rejected on ABBA-deadlock grounds. The consequence for you is direct: **a nested middle layer that keeps its own screen model becomes a third independent representation** of the same screen.

**Prefix keys are the least-researched nesting concern, and the honest answer is that nobody knows.** The question is whether a multiplexer's prefix chord eats the ADE's keybindings, and whether it can be rebound or disabled with no human attached.

| Candidate | Has a prefix? | Rebindable? | Disable-able for headless use? |
|---|---|---|---|
| psmux | Yes, tmux-style `C-b` | Inferred yes — tmux-compatible config implies `set prefix`, **not verified** | Unknown |
| Zellij | Yes, `Ctrl` modes rather than a single prefix | Inferred yes — keybindings are a first-class KDL config section | Unknown |
| rmux | Yes, tmux-compatible | Inferred yes, same reasoning as psmux | Unknown |
| herdr | Yes | Unknown — but its Windows-beta page lists "**Prefix input-source switching \| unsupported**" (`windows-beta.mdx`), the only primary-source statement about prefixes on Windows found anywhere in this research | Unknown |
| qscreen, oly, quil, `ao pty-host`, OpenCode `/pty` | Unknown — single-pane or network-attached designs may have no prefix at all | Unknown | Unknown |
| `docker attach` (as a design reference) | Yes, `CTRL-p CTRL-q` | **Yes, documented** — `--detach-keys`, per-container or global ([docs.docker.com/reference/cli/docker/container/attach/](https://docs.docker.com/reference/cli/docker/container/attach/)) | Yes, by remapping to an unused chord |

**The only documented remapping mechanism in the entire census belongs to docker, not to any multiplexer candidate.** Every multiplexer's rebindability above is an inference from "it has a config file" — nobody has set the key and confirmed no chord is intercepted. And for a headless-first middle layer the right target is stronger than rebinding anyway: **no prefix at all on the headless path**, with the prefix existing only when a human attaches. None of the candidates is known to offer that.

Two more nesting hazards live in the outer layer and are worth knowing before you blame your own code: pasting more than 5 KiB into a slow-reading app **deadlocks the whole terminal** and stops Ctrl-C from working ([microsoft/terminal#17384](https://github.com/microsoft/terminal/issues/17384), open since 2024-06-06); and a handful of VT-passthrough issues remain open in [#17643](https://github.com/microsoft/terminal/issues/17643) — `COMMON_LVB_GRID_HORIZONTAL` to SGR 53 translation dropped, `VtIo::Writer::WriteInfos` not verifying per-character width, `SetConsoleActiveScreenBuffer` destroying grapheme clusters. Cooked-read reflow, `ScrollConsoleScreenBuffer`, the DA3 truncation and the PSReadLine SGR issue are all **fixed** — do not carry those forward as hazards.

Finally, a scoping note about all of the above: **double-ConPTY nesting has not been empirically tested by any candidate in this research.** The mechanism is documented; the behaviour of these specific tools inside a second ConPTY is not. That includes the one candidate widely credited with having nested-agent tests — oly — where the thing that created the impression was not a README but a **test fixture**: `tests/output-copilot.log`, a recorded ANSI dump that no live-agent test ever opens. The distinction matters and is set out in the oly entry and in [the worked example](#worked-example--placing-a-tool-that-isnt-in-the-census).

### How to check any of this yourself

Everything below runs on native Windows 11 in `pwsh`, with no build tools. Run each one **inside an ADE pane** as well as in a plain terminal — the difference between the two answers is the whole point.

**Disclosure before you paste any of it.** These probes are **new code written for this guide, not code taken from any project, and none of them has been executed anywhere**. The Win32 semantics behind each one are cited above; the PowerShell wrapping them is not evidence of anything. That is the same standard this guide applies to the install commands, and it applies here too — the "you should see" line under each probe is what turns a run into a result, and if what you see is different, the probe is the first thing to suspect, not the platform.

**Is the in-box ConPTY there, and which build are you on?** The passthrough behaviour is corroborated at `build >= 22621` by two independent Rust implementations converging on the same magic number (psmux and rmux). **No primary Microsoft source pins that threshold**, and neither implementation's constant was recorded here with a file path, so the corroboration is real but not locatable from this document — treat the build number as a heuristic, not a contract, and grep for `22621` in either tree if you need the citation.

```powershell
$sig = @'
[DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
public static extern IntPtr GetModuleHandleW(string name);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern IntPtr GetProcAddress(IntPtr module, string proc);
'@
$k = Add-Type -MemberDefinition $sig -Name Conpty -Namespace Probe -PassThru
$h = $k::GetModuleHandleW('kernel32.dll')
'CreatePseudoConsole','ResizePseudoConsole','ClosePseudoConsole','ClearPseudoConsole' |
  ForEach-Object { '{0,-22} {1}' -f $_, ($k::GetProcAddress($h, $_) -ne [IntPtr]::Zero) }
"OS build: $([Environment]::OSVersion.Version.Build)"
```

**You should see:** `True` for the first three, and **`False` for `ClearPseudoConsole` — that is the correct, healthy answer**, not a failure. `ClearPseudoConsole` is a bundled-only export, as item 3 above establishes; kernel32 does not export it, and the bundled `conpty.dll` spells it `ConptyClearPseudoConsole` anyway. A machine that answers `True` on that row would be the surprising one.

**See the multi-client console for yourself.** This is `GetConsoleProcessList` — the same call NVDA uses for liveness. Run it in a plain console, then inside an ADE pane, then inside a nested multiplexer, and watch the attached set change.

```powershell
$sig = @'
[DllImport("kernel32.dll", SetLastError=true)]
public static extern uint GetConsoleProcessList(uint[] list, uint count);
'@
$k = Add-Type -MemberDefinition $sig -Name Con -Namespace Probe2 -PassThru
$buf = New-Object uint32[] 64
$n = $k::GetConsoleProcessList($buf, 64)
"attached processes: $n"
if ($n -gt 0) {
  $buf[0..($n - 1)] | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } |
    Select-Object Id, ProcessName
} else {
  "no console attached (this is the console-less case; GetConsoleProcessList returned 0)"
}
```

**You should see:** a small count — typically 1 or 2 in a plain console (the shell, plus its host on some configurations), and more inside an ADE pane or a nested multiplexer, which is the point of running it in all three places. **The `if ($n -gt 0)` guard is load-bearing, not defensive tidiness:** in PowerShell `0..-1` evaluates to the sequence `0, -1`, so an unguarded `$buf[0..($n-1)]` on a zero result indexes element 0 and element 63 and prints two garbage PIDs — precisely in the console-less case you most want a clean answer for.

**Does whatever is above you answer DA1 and `CSI 18 t`?** This is the cheapest way to find out whether you will pay the 3-second stall, and whether psmux's in-band sizing can work in your ADE. Save it as `da1-probe.ps1` and run it as a separate process rather than pasting it into a live session — PSReadLine competes for input and the reply characters vanish before your read loop sees them. It only works in an interactive session: `[Console]::KeyAvailable` throws when stdin is redirected.

```powershell
# da1-probe.ps1
$e = [char]27
function Ask([string]$seq, [int]$ms = 500) {
  while ([Console]::KeyAvailable) { [void][Console]::ReadKey($true) }   # drain
  [Console]::Write($seq)
  Start-Sleep -Milliseconds $ms
  $r = ''
  while ([Console]::KeyAvailable) { $r += [Console]::ReadKey($true).KeyChar }
  if ($r -eq '') { '(no reply)' } else { $r -replace [regex]::Escape([char]27), '<ESC>' }
}
"DA1   ESC[c    -> " + (Ask "$e[c")      # expect something like <ESC>[?1;0c
"SIZE  ESC[18t  -> " + (Ask "$e[18t")    # expect <ESC>[8;<rows>;<cols>t
```

```powershell
pwsh -NoProfile -File .\da1-probe.ps1
```

A note on `"$e[c"`, because it looks like a bug and is not: PowerShell does not expand index syntax inside an expandable string, so `$e` interpolates and `[c` is literal. "Fixing" it to `"$e[c]"` or `"${e}[c"` changes what is written to the terminal — leave it alone.

**You should see:** on the DA1 line, something of the form `<ESC>[?1;0c` or `<ESC>[?62;...c` — any reply at all is a pass. `(no reply)` means nothing above you is behaving as a terminal, and a child that waits on DA1 will burn its full 3 seconds on every spawn. On the size line, `<ESC>[8;<rows>;<cols>t` is a pass; `(no reply)` run **inside an ADE pane** means xterm.js is not answering XTWINOPS and psmux's pipe mode would sit at 120x30 forever.

**Does resize actually reach the child?** Run this inside an ADE pane and drag the pane border.

```powershell
while ($true) { '{0}x{1}' -f [Console]::WindowWidth, [Console]::WindowHeight; Start-Sleep 1 }
```

**You should see:** the printed dimensions change within a second of the drag, and match the pane you are looking at. The correct number is whatever your pane actually is — the test is that it *tracks*, not that it hits a particular value. Numbers that never change mean `ResizePseudoConsole` is not being called on that hop, which is item 4's failure, live. Numbers that change but settle on `120x30` are the psmux in-band-sizing fallback, which is a different failure with the same symptom.

**Which input path will a multiplexer choose?** Zellij's Windows input selection keys off `TERM` and `WT_SESSION`; when neither is set it picks the native-console path, which is implemented and conservative. This is a config check, not a hazard — but you want to know the answer before you debug anything else.

```powershell
"TERM='$env:TERM'  WT_SESSION='$env:WT_SESSION'  ConEmuANSI='$env:ConEmuANSI'"
```

**You should see:** all three empty inside an ADE pane, and `WT_SESSION` populated inside Windows Terminal. Empty is the answer that means Zellij takes its native-console `INPUT_RECORD` path.

**Does late attach reach an agent your ADE spawned?** Save this as `attach-probe.ps1`. It calls `FreeConsole` first, which destroys the caller's own console — that is why it must run as a throwaway process with its output redirected to a file, and it is the same "one console per process" constraint that forced `cc-discord-remote` into a helper-per-operation design.

```powershell
# attach-probe.ps1  —  usage: pwsh -NoProfile -File .\attach-probe.ps1 1234
$sig = @'
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint pid);
[DllImport("kernel32.dll", SetLastError=true)] public static extern uint GetConsoleProcessList(uint[] l, uint c);
'@
$k = Add-Type -MemberDefinition $sig -Name A -Namespace Probe3 -PassThru
[void]$k::FreeConsole()
$ok  = $k::AttachConsole([uint32]$args[0])
$err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
$buf = New-Object uint32[] 64
$n   = if ($ok) { $k::GetConsoleProcessList($buf, 64) } else { 0 }
"attach=$ok err=$err attached=$n"
```

```powershell
# Find the agent's PID, then probe it from a separate process.
# Note: no angle brackets anywhere — in PowerShell `<` is a reserved redirection
# operator and a bare <PID> placeholder is a parse error, not a blank to fill in.
Get-Process claude, node, pwsh -ErrorAction SilentlyContinue | Select-Object Id, ProcessName
$targetPid = 1234                      # <-- put the agent's PID here
pwsh -NoProfile -File .\attach-probe.ps1 $targetPid > "$env:TEMP\attach-probe.txt" 2>&1
Get-Content "$env:TEMP\attach-probe.txt"
```

**You should see:** `attach=True err=0 attached=N` with N at least 1 on a successful attach, or `attach=False err=5` (access denied) / `err=6` (invalid handle) on a refusal — and the error number is the useful part, because it tells you *which* boundary stopped you.

A successful attach tells you the boundary is crossable in your topology. It does **not** tell you that reading works — remember pywinauto's ten spaces — so if you care, follow it with a `ReadConsoleOutputCharacter` call and compare what comes back against what is on screen. And keep the general rule in mind while reading any of these results: **a tool reporting success proves nothing.** A `CreatePseudoConsole` that returned `S_OK`, a spawn that printed a prompt, and a resize call that returned without error are all compatible with a session that is silently the wrong size, silently losing bytes to a lossy string conversion, and silently three seconds slower per spawn than it needs to be.

## Ten axes for placing any tool, including ones that do not exist yet

The census in the next section has a shelf life measured in months — six ADEs died or closed in the eight before this was written, and every star count in it is a snapshot that will be wrong by the time you act on it. **The axes below do not rot the same way**, because each one asks a question about a design decision rather than about a project's health, and each one comes with a check you can run against a repository you have never opened.

That is the point of this section. When a new multiplexer shows up on Hacker News next spring, you should not have to redo any of this. You should be able to clone it, run ten checks, and know within twenty minutes what it is, whether it can sit under your shell, and which single property it forfeits. **A judgement about the census, stated as one: every candidate that survived this survey forfeits exactly one of {maturity, Windows-nativeness, standalone packaging, contract stability}** — not one, all of them, and each a different one. That is a reading of eleven tools, not a law about tools in general, and a project written next year is free to falsify it. The axes are how you find out which property a new arrival forfeits before you have built anything on top of it.

**Four of these ten axes are the four framing questions, restated as repo-checkable tests.** Ownership timing is **Owner**; persistence scope is **Lifetime**; transport binding is **Rendezvous**; terminal-state ownership is **Payload**. The other six — session/window coupling, namespace model, command-language uniformity, extensibility mechanism, agent-state derivation, substrate stance — are the ones that decide between tools that answered the four identically, which is most of the field.

**An axis earns its place here only if a different answer changes what you would build.** "Written in Rust" is not an axis. "Ships raw child bytes on the live path versus re-rendered ANSI" is, because one of those means your ADE's xterm.js is the only VT parser in the chain and the other means you are paying for two. Four of these ten replaced earlier formulations that turned out to be false; the last subsection keeps those as **standing traps**, because each is a mistake a competent engineer makes independently and one of them — reading a Unix socket in source as proof of a POSIX-only tool — is actively wrong on modern Windows.

### The ten checks at a glance

| Axis | The question | The fastest check | What the wrong answer costs you |
|---|---|---|---|
| Session/window coupling | Does one binary own both persistence and layout? | Does `split` / `new-window` / `select-pane` exist in `--help`? | You inherit a layout engine you do not want, and cannot swap it |
| Terminal-state ownership | Does the live path carry bytes or a rendered screen? | The payload type of the live-output message: `Vec<u8>`/`[]byte` vs `String` | A second VT parse, and fidelity lost at every hop |
| Namespace model | Who can collide with you, and who can squat on your endpoint? | Read the **default** socket/pipe name construction, then grep for an ACL | Two projects sharing a daemon; a hostile local process harvesting your I/O |
| Command-language uniformity | Do a script, a hook and a human speak the same verbs? | Does the same verb string work as `tool verb`, as a config line, and as a keybinding? | Two grammars to learn and to keep in sync when the human leaves the loop |
| Extensibility mechanism | What shape does an extension take? | Shell string, wire protocol, plugin binary, embedded interpreter, or typed SDK | You write and maintain the client library yourself |
| Agent-state derivation | How do you learn the agent is idle, blocked, or done? | Grep for a VT/emulator dependency, and for a regex over screen text | Silent stale-buffer misreads with no human to notice them |
| Substrate stance | Does it wrap tmux, replace it, or skip the PTY entirely? | Is `tmux` a prerequisite or a spawned binary? Is there a PTY library at all? | A POSIX dependency smuggled in under a cross-platform README |
| Transport binding | What actually carries the IPC, and is it safe on Windows? | Grep for the four transport signatures below | A daemon that compiles on Windows and an endpoint anyone can read |
| Persistence scope | What exactly survives what? | Kill the spawning tree, then try to attach from a **new** client | A "persistent" tool that dies with the ADE — the one thing you are buying |
| Ownership timing | Does it spawn the child or attach to a stranger's console? | Whose PID goes into the attach call? | Months spent on late-attach, which nothing in the field makes work |

Read down a column to compare the field on one decision. Read across a row to characterise one tool. **The disqualifying answer usually falls out of a single cell**, which is the property that makes this worth doing at all — see the worked example near the end, where a candidate is refuted entirely by the transport cell.

### Session/window coupling — does one binary own both jobs?

| Pole | What it means | How to determine it | Where the field lands |
|---|---|---|---|
| Monolithic | One binary owns session persistence **and** pane/window layout | One executable, and killing it loses both the layout and the sessions | screen, tmux, Zellij, psmux, rmux, herdr, boo |
| Split | Persistence and layout are separate, swappable programs | The layout program appears as an *argument* to the session program, and can be replaced with any other command | abduco + dvtm |
| Session-only | No layout concept at all | No `split`, `new-window` or `select-pane` verb exists anywhere in the CLI | dtach, qscreen (single pane by design), upterm |

**The split pole is the closest existing precedent for what you are shopping for** — a session layer that deliberately does not own rendering, because your ADE already owns rendering. abduco's author says it in as many words on [the abduco/dvtm writeup](https://brain-dump.org/blog/abduco-dvtm-a-lightweight-alternative-to-tmux-and-screen/): "these are two distinct features: window and session management shouldn't be intermingled." **The idea travels; the code does not.** Both halves are dormant — abduco's last commit is 2020-04-30, dvtm's 2021-03-06 — and both are POSIX-only.

The practical reading for a middle layer: **a monolithic tool is not disqualified, it is over-specified.** You will be paying for and nesting a layout engine whose panes you never use, and its layout keybindings become prefix-key collisions inside your ADE's own PTY.

### Terminal-state ownership: three poles, and the double parse is optional

The three poles were introduced under [Nesting](#nesting-your-middle-layer-runs-inside-the-ades-conpty) above; here they are as a placement check. The axis's original formulation ("rendering multiplexer versus transparent byte-passer") was a binary and it was wrong: **there is a third pole, and most modern candidates sit in it.**

| Pole | Behaviour | How to determine it | Where the field lands |
|---|---|---|---|
| Opaque relay | No screen model; forwards bytes verbatim; cannot redraw on reattach | No VT or emulator crate in the dependency manifest at all | dtach — its README states it plainly: "dtach does not have a terminal emulation layer, and passes the raw output stream of the program to the attached terminals" |
| Full VT owner | Parses every escape into a grid, re-emits rendered ANSI | The live-path payload type is a **string** or a rendered-cell struct, not a byte slice | screen, tmux, Zellij, psmux TUI mode, herdr, ripple's `VtLiteState` |
| Parallel model, raw live path | Maintains a VT model for snapshot, resize and scrollback bookkeeping, but ships **raw child bytes** on the live path | The live-path payload carries `bytes` / `Vec<u8>` / `[]byte`, **and** a separate VT model exists for snapshots | qscreen `AttachMode::Bytes` (`crates/qscreen-protocol/src/lib.rs:56-61`); oly `ServerMessage::Data { data: Vec<u8> }` (`src/http/ws.rs:36-46`); quil `PaneOutputPayload { Data []byte }` (`internal/ipc/protocol.go:204-208`); psmux `-CC` `%output`, an octal-escaped pane-output ring (`src/server/mod.rs:1222-1227`) — **on intent only; see the note below the table** |

**The widely repeated "the double parse is unavoidable" framing is false.** It is avoidable today, with shipped interfaces, in three of the four small candidates, and all four citations above are verified in source.

**The same check demotes candidates that are otherwise among the best-shaped in the census, which is why the axis is worth having.** Apply it to OpenCode's `/pty` and it lands in the second pole, not the third: its outbound frames are *described* as "raw UTF-8 terminal chunks", but the payload type in `packages/core/src/pty/protocol.ts` is a JavaScript `string`, with the surrogate-splitting and silent-drop consequences set out under [Nesting](#nesting-your-middle-layer-runs-inside-the-ades-conpty). Apply it strictly to psmux's `-CC` `%output` and the same thing happens for the same reason: the ring is octal-escaped, which is byte-oriented, but the drain runs `String::from_utf8_lossy` at `src/server/mod.rs:1225` *before* the escaping, so the escape encodes bytes that have already been through a lossy conversion. **Both are placed in the third pole on design intent and fall to the second pole on the strict test.** Say which reading you are using whenever you rely on either.

**How to run this check on a tool you have never seen:** find the message type the server sends on every output tick — not the snapshot type, not the scrollback type — and look at the field's declared type. A `String`, a `text` field, or a JSON-encoded payload puts it in the second pole no matter what the README calls it.

### Namespace model — who can collide with you, and who can squat on you

Ordered worst to best. **The poles are about who can collide with you, not about the transport** — those are two different axes, and collapsing them is exactly how oly ends up misplaced.

| Pole | Mechanism | How to determine it | Where the field lands |
|---|---|---|---|
| Machine-global default | The default name contains no user, SID or project component, so two users on one host collide | Read the socket or pipe name construction: is there any per-user or per-project component in the **default** path? | oly — default `open-relay.oly.sock`, no user component (`src/config.rs:123-126`) |
| Single fixed instance, per-user | One instance per user by construction, with no way to run two side by side | The name embeds a user component but no `-L`-style label, and no env var overrides it | qscreen — `\\.\pipe\qscreen-<user>` (`crates/qscreen-shared/src/lib.rs:6-11`) |
| Socket-name-as-namespace | The socket or pipe name **is** the namespace, selectable per invocation | A `-L`/`-S` flag or a name env var exists | tmux `-L`/`-S`, psmux `-L`/`-S`, rmux `-L`, and oly via `OLY_SOCKET_NAME` |
| Env-var home split | A whole state directory per instance | An env var relocates the entire state root, not just the socket | quil `QUIL_HOME`, Claude Code `CLAUDE_CONFIG_DIR` |
| Identity-scoped | The namespace is derived from user SID plus integrity level, not from a string the caller picks | The name is *computed* from `GetTokenInformation`-class data, so it cannot be spoofed by argument | rmux — `\\.\pipe\{prefix}-{sid}-il-{integrity}-{label}` (`crates/rmux-ipc/src/endpoint.rs`) |

**Identity-scoped is the only pole where the namespace cannot be entered by a process that merely guesses a string, and only rmux is in it.** What that buys is specific: it removes an entire class of collision and squatting, and it matters exactly to the degree that some *other* local process might want in. On a machine where you are the only account and the threat model does not include a hostile local process, this axis stops discriminating between candidates and the choice moves elsewhere. On a shared or multi-user machine it is the first filter. Everything below the top pole depends on the pipe's ACL for actual security — and **only rmux and qscreen set one.**

**The trap this axis sets, and the correction that comes out of it.** The easy first reading is that oly's socket name is hardcoded, which would put it at the bottom of the table with no isolation knob at all. It is not hardcoded: `src/config.rs:123-126` reads `std::env::var("OLY_SOCKET_NAME").ok().and_then(normalize_optional_string).unwrap_or_else(|| "open-relay.oly.sock".to_string())` — an env-var-selectable name with a machine-global *default*, which is the same pole as tmux. **The correction stands, and the real defect is on a different axis entirely:** oly's pipe is created with no ACL and no `FILE_FLAG_FIRST_PIPE_INSTANCE`, so a hostile local process can pre-create it and harvest client connections. The isolation knob exists; the access control does not. The evidence, and what the project says about it, is in the oly entry among the standalone daemons below.

So: **check the default, not the constant, and check the ACL separately from the name.** Namespacing and access control are different problems, a tool can pass one and fail the other, and reading one string in one file would never have found the defect that matters here.

### Command-language uniformity — do a script, a hook and a human speak the same verbs?

| Pole | How to determine it | Where the field lands |
|---|---|---|
| One grammar usable from shell, config file, and keybinding | The same verb string works as `tool verb`, as a config-file line, and as a keybinding target | tmux (its manual page has a whole "COMMAND PARSING AND EXECUTION" section), psmux, rmux (90+ tmux-compatible verbs) |
| Separate keybinding table bolted onto a distinct config syntax | The config file's grammar and the CLI's grammar do not overlap | screen |
| Discoverability-first on-screen hinting | The primary interface is a rendered hint bar, and CLI verbs are secondary | Zellij, whose README states the goal as "must not sacrifice simplicity for power" |

**Why this axis matters specifically for a headless middle layer:** the first pole is the only one where a script, a hook and a human all speak the same language, so **nothing has to be re-learned when the human leaves the loop.** With the third pole you are driving a tool whose designers optimised the path you will never use.

### Extensibility mechanism — what shape does an extension take?

| Pole | How to determine it | Where the field lands |
|---|---|---|
| Shell hooks and pipes | Extension points take a shell command string | tmux hooks, `pipe-pane`, screen backtick |
| External wire protocol | A documented framing exists that a non-child process can speak | tmux `-CC` control mode, psmux `-CC`, qscreen `ScreenFrame`, the WezTerm mux codec |
| Sandboxed compiled plugin runtime | Plugins ship as compiled artifacts against a schema'd host API | Zellij WASM plugins, protobuf-schema'd [since 0.38.0](https://zellij.dev/news/session-manager-protobuffs/) |
| Embedded scripting runtime | An interpreter is linked in and the config file is a program | WezTerm (Lua config plus an event API) |
| Typed SDK | A published client library exists in at least one language, with types | rmux (Rust, Python and TypeScript, with `session` / `pane` / `snapshot` / `wait_for_text`), herdr (third-party TypeScript and Python clients) |

For your use case the second and fifth poles are the ones that pay. **A wire protocol you can speak from any language is what makes the layer ADE-independent**; a typed SDK is that plus somebody else maintaining the client. Note that herdr's SDKs are third-party, which means the contract you would depend on is not the one the project promises to keep.

### Agent-state derivation — how you learn the agent is idle, blocked, or done

| Pole | Mechanism | Where the field lands | Characteristic failure |
|---|---|---|---|
| Vendor-emitted structured events | The agent CLI itself emits typed events | Claude Code OpenTelemetry plus JSONL transcripts plus `stream-json`; Codex `--json` rollout events; OpenCode `/global/event` SSE | Vendor-specific, and the config surface changes under you |
| Native typed state | The multiplexer owns a VT parser and exposes typed peek/wait/snapshot | boo `wait --idle` and `peek --json`, rmux `snapshot()`, quil `MsgScreenshotPaneResp{Text,CursorX,CursorY}`, andyk/ht | Only as good as the emulator |
| External heuristic scraping | Regex or OSC-title matching over another program's rendered screen | tmux-agent-status, tmuxai, the kiro_cli poller | **A documented convergent bug** — see below |

**How to determine which pole a tool is in:** grep for a VT or emulator dependency, and grep for a regex over screen text. Structured-event consumers have neither. Native-typed-state tools have the emulator. Scrapers have the regex and no emulator.

**The scraping failure is documented, not theoretical.** [`awslabs/cli-agent-orchestrator` issue #182](https://github.com/awslabs/cli-agent-orchestrator/issues/182) records it: "Kiro CLI 2.0 TUI redraws the screen in-place… retains 'Kiro is working' from earlier rendering alongside the new idle prompt", with the stated impact "Handoff delegations never complete." Two projects independently landed on the same mitigation: **anchor to the bottom N lines or to the OSC title, never to the whole screen, and add NOT-gates for stale artifacts.**

**Two disclosures on that citation, because they change how much weight it carries.** First, issue #182 is **closed as `completed` on 2026-04-20** and its title begins `fix(kiro_cli):` — the bug was fixed. It remains valid evidence that the failure mode is real and was hit in production by a shipped project; it is *not* evidence that any current tool is broken today. Second, `awslabs/cli-agent-orchestrator` (the AWS project cited here) and `Untrivial-ai/agent-orchestrator` (the home of `ao pty-host`, discussed elsewhere in this guide) are **different, unrelated projects** that happen to share a name.

**The judgement, with the headless constraint applied:** scraping is disqualified as an *architecture* — not because any specific instance is broken today, but because a stale-buffer misread has nobody to notice it when no human is in the loop. Between the remaining two poles, **vendor-emitted structured events cost nothing structurally** — they do not touch the PTY at all, so they survive an ADE swap for free — which makes them the cheapest channel to add and a reasonable default *if* you are willing to write and maintain a separate integration per agent vendor. Native typed state costs you a VT emulator's fidelity and buys you one channel that works for every agent uniformly. That is the actual trade, and which side of it you want depends on how many agent CLIs you intend to support.

**One number to state precisely, because it is quoted wrongly.** The 34 `claude_code.*` identifiers named in the opening section are not 34 events: the set mixes metrics (`cost.usage`, `token.usage`, `session.count`, `lines_of_code.count`), events, and spans (`tool.execution`, `hook`). Say "34 named `claude_code.*` identifiers".

### Substrate stance — wrap tmux, replace it, or skip the PTY

| Pole | How to determine it | Where the field lands |
|---|---|---|
| Wrap tmux, keep it as substrate | `tmux` appears as a hard prerequisite in the install docs, or as a spawned binary in source | tmuxai, tmux-agent-status, tmux-message-bus, claude-squad, uzi, Agent Orchestrator on Darwin and Linux |
| Replace tmux with a new PTY-owning binary | A PTY library appears in the dependency manifest and no tmux prerequisite exists | psmux, quil, oly, qscreen, Zellij, rmux, herdr, boo |
| No multiplexer at all, no PTY | No PTY library anywhere; the agent is spawned with ordinary pipes | Claude Code `-p --input-format stream-json`; Codex `app-server`; OpenHands EventStream; the GitHub Actions runner |

**On native Windows the first pole is a disqualifier disguised as an architecture choice**, which is why it is worth checking early and cheaply: a `tmux` prerequisite anywhere in the install path means WSL.

**The criterion that decides between the second and third poles, stated independently of any one project:** a session layer is necessary exactly when the *agent host* does not own process lifecycle end to end. If the agent tool spawns, supervises and outlives its own processes, a multiplexer underneath is dead weight. If the host dies and takes its children with it, the multiplexer is the only thing that makes sessions survivable.

That line is not this guide's invention — an independent practitioner draws the same one. [Galen Guan writes](https://guancyxx.cn/en/blog/tmux-skills-ai-agents): "For Claude Code and OpenClaw users working through SSH-disconnected sessions, tmux is essential infrastructure. For Hermes users, it's an unnecessary abstraction layer" — Hermes being an agent tool whose own terminal tool owns process lifecycle end to end, and OpenClaw one that, like Claude Code, does not. Treat that as corroboration, not proof: it is a third-party blog writing about somebody else's tools, not any project's own documentation.

**Applied to your situation:** ORCA spawns agent CLIs through its own in-process node-pty, so sessions die with ORCA. It is on the "essential infrastructure" side of the line by construction. The wrapper is not invented-here syndrome; it is the consequence of where ORCA puts the PTY.

### Transport binding — four poles, and why "it uses a Unix socket" tells you nothing

The original binary formulation ("POSIX-only versus native-Windows") misclassifies candidates outright. **AF_UNIX is a real Windows transport since Windows 10 1803**, so a `UnixListener` in source is no longer proof of a POSIX-only daemon. This is the single most important correction in the taxonomy and the subsection below returns to it.

| Pole | The grep that proves it | Where the field lands |
|---|---|---|
| `cfg(unix)`-gated UDS or `forkpty` | `std::os::unix::net`, `std.posix`, `forkpty`, or `nix` with terminal features | dtach, abduco, boo (`std.posix` in 11 files), ht (`src/pty.rs`, `forkpty` plus `nix`), tuios, gotty — whose `creack/pty` `start_windows.go` is literally `return nil, ErrUnsupported` |
| Cross-platform AF_UNIX shim | UDS routed through a shim crate | WezTerm (`wezterm-uds/src/lib.rs`: `#[cfg(windows)] use uds_windows::UnixStream`), Codex (`codex-rs/uds/src/lib.rs:1` "Cross-platform async Unix domain socket helpers"; line 162 `#[cfg(windows)]` dispatches to `uds_windows::UnixListener::bind`) |
| Windows named pipes | `\\.\pipe\`, `CreateNamedPipeW`, `interprocess::GenericNamespaced`, `tokio::net::windows::named_pipe` | oly, qscreen, Zellij, rmux, herdr, node-pty (conin/conout) |
| TCP loopback | `TcpListener::bind("127.0.0.1:0")` | psmux (control and cross-session), `ao pty-host`, Warp `local_control` (`http://127.0.0.1:PORT/v1/control`), pywinpty's internal bridge |
| Naked AF_UNIX on all platforms | `net.Listen("unix", …)`, unconditional | quil (`internal/ipc/server.go:311`) — works on Windows 10 17063+, but `os.Chmod(path, 0600)` is a **no-op on Windows** and there is no `SO_PEERCRED`, so the socket's only protection is the parent directory's ACL |

Run all five greps at once from the repo root:

```powershell
# Ripgrep, single-quoted so PowerShell passes the regex through untouched.
# (Select-String -Pattern takes the same patterns if you would rather not install rg.)
rg -n 'std::os::unix::net|std\.posix|forkpty|net\.Listen\("unix"'   # POSIX-shaped
rg -n 'uds_windows|interprocess::|GenericNamespaced'                # shimmed, or named-pipe crate
rg -n 'CreateNamedPipeW|named_pipe|pipe\\'                          # named pipes
rg -n 'TcpListener::bind|net\.Listen\("tcp"'                        # loopback TCP
rg -n 'FILE_FLAG_FIRST_PIPE_INSTANCE|SECURITY_ATTRIBUTES|security_descriptor|ImpersonateNamedPipeClient'   # does it defend the endpoint?
```

That last line is the one people skip. **The two AF_UNIX poles differ in hygiene, not in portability** — both work on Windows 10 17063+. The difference is that a shim crate documents the platform intent and centralises the fallbacks, whereas a naked `net.Listen("unix", …)` leaves the caller believing POSIX socket semantics still apply. **Neither pole gets kernel-enforced permissions on Windows**: `SO_PEERCRED` does not exist there, and `chmod` or `os.Chmod` on an AF_UNIX path is a no-op. Whichever pole you are in, an AF_UNIX socket on Windows is protected only by the ACL on its parent directory. **A properly ACL'd named pipe is strictly stronger; a loopback TCP port is strictly weaker** — any local process can scan it.

**Two crates are the de-facto answers, arrived at independently.** WezTerm and Codex both landed on `uds_windows`; Zellij, herdr and oly all landed on `interprocess`. WezTerm's own `docs/multiplexing.md` states the consequence flatly: "Unix domains are supported on all systems, even Windows."

### Persistence scope: what exactly survives what

**How to determine the level, and this one is an experiment rather than a grep:** kill the spawning process, then ask two questions — is the child still running, and can a *new* client re-attach to it? Both yes is level 2. Child alive but no re-attach path means the tool is a supervisor, not a session host. Neither is level 0.

| Level | Meaning | Where the field lands |
|---|---|---|
| **L0 — none** | A new process per connection, killed on disconnect | ttyd (`src/protocol.c:377-383` — `LWS_CALLBACK_CLOSED` unconditionally kills the per-connection `pss->process`), wetty (`src/server/spawn.ts`, `.on('disconnect', () => term.kill())`), terminado `UniqueTermManager` |
| **L1 — survives client disconnect** | The session lives as long as the host process | upterm, sshx, terminado `NamedTermManager`, ACP — the Agent Client Protocol, covered among the interface shapes below — whose `session/load` restores conversation state, not a process |
| **L1+ — L1 plus cursor-resumable replay** | Survives client disconnect *and* a reconnecting client resumes from an absolute output cursor rather than replaying from zero. **Still dies with the host process, so it is not L2** | OpenCode `/pty` (`packages/core/src/pty/protocol.ts`) — the only instance found anywhere |
| **L2 — survives the ADE** | A detached daemon outlives whoever spawned it | psmux, quil, oly, qscreen, Zellij (`zellij-client/src/lib.rs:463-480`, `CREATE_NO_WINDOW \| CREATE_NEW_PROCESS_GROUP`), rmux, `ao pty-host` (`conpty/spawn_windows.go` — `CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS` "so the host survives daemon exit"), `wezterm-mux-server --daemonize` |
| **L3 — survives a host reboot** | State is restored across a full restart | **cmux** (`manaflow-ai/cmux`, Swift + AppKit, GPL-3.0-or-later, 25,483 stars, **macOS only**), whose FAQ claims "the state survives a full computer restart… Agent sessions like Claude Code, Codex, and OpenCode come back too" — the only level-3 claim found anywhere in this research, and one you cannot check on Windows because the product does not run there. It is quoted from cmux's own FAQ, which was read once and for which no URL was recorded; treat the claim as reported rather than verified |

**L2 is the level that defines the thing you are shopping for.** It is also the level a README will claim on the strength of L1 behaviour, which is why the check is a kill command and not a document. Substitute your candidate's binary name and verbs into `$tool` below — the block is written with variables rather than `<placeholders>` because in PowerShell `<` is a reserved redirection operator and a bare `<tool>` is a parse error, not a blank:

```powershell
# 0. Name the thing under test once.
$tool = 'psmux'          # or zellij / rmux / herdr …

# 1. Start the daemon the way the ADE would: from a shell you are about to destroy.
#    Start-Process gives you a genuinely separate console host, so killing it later
#    does not take down the terminal you are typing in.
$parent = Start-Process pwsh -PassThru -ArgumentList '-NoExit','-Command',"$tool new -s probe"

# 2. Record the daemon's PID *before* you kill anything — it is the thing under test.
$daemon = Get-Process | Where-Object { $_.ProcessName -like "*$tool*" } |
          Select-Object Id, ProcessName, StartTime
$daemon
$daemonPid = $daemon[0].Id

# 3. Kill the spawning shell the way a crash would. NOT `taskkill /T` — see below.
Stop-Process -Id $parent.Id -Force

# 4. From a brand-new shell: is the daemon alive, and can a NEW client take the session over?
Get-Process -Id $daemonPid -ErrorAction SilentlyContinue   # alive?  -> at least L1
& $tool ls                                                 # visible to a new client?
& $tool attach -t probe                                    # re-attachable?  -> L2
```

Steps 2 and 4 are the honest version of the test: a tool passes L2 only when a **different** client process, started after the original died, can drive the session. **Do not reach for `taskkill /T`** — it walks `ParentProcessId` and kills a correctly-detached daemon anyway, so it measures the process tree rather than the design; the full reasoning, and the Job-Object variant that is worth testing separately and knowingly, are in [The verification ritual](#the-verification-ritual). These verbs are assembled from each project's own documentation and verb list and have not been executed on a Windows machine in any pass, so treat the exact spellings as a starting point and the *shape* of the test as the thing to preserve.

### Ownership timing: settled, and recorded so you do not re-open it

This is not really an axis, because one pole is refuted outright and there is nothing left to place. It keeps its slot because it is the question that gets re-opened every time somebody re-researches this area.

**Own-from-birth** — the wrapper spawns the child and holds the `HPCON` from the first instruction — is the only viable pole, and every working implementation found does it. **Late attach**, reaching into a console the wrapper did not spawn via `AttachConsole(pid)`, is a read-only escape hatch at best. The evidence is under [AttachConsole](#attachconsole-and-what-multi-client-object-buys-you) and [Who owns the session](#who-owns-the-session-whoever-called-the-pty-spawn-api) above; the short version is that node-pty, the one piece of prior art everybody cites, hands `AttachConsole` the PID of a process **it spawned itself** (`src/windowsPtyAgent.ts:149`), so it proves the opposite of what it is cited for. **Nothing found anywhere late-attaches to a foreign console and drives it**, with the single exception of one hobby project.

**The check, on a repository you have never opened:** grep for `AttachConsole` and `CreatePseudoConsole`, then read whose PID goes into the attach call. If it is the tool's own child, it is own-from-birth whatever the README implies.

### The placement matrix — every live candidate on all ten axes

Rows are the candidates that survived the census. Read a column to compare one design decision across the field; read a row to characterise one tool. Cells are pole names, abbreviated; `—` means the axis does not apply to that candidate's shape.

| Candidate | Coupling | State ownership | Namespace | Command lang | Extensibility | Agent state | Substrate | Transport | Persist | Timing |
|---|---|---|---|---|---|---|---|---|---|---|
| **psmux** | Monolithic | Full VT (TUI) / raw-*by-intent* (`-CC`) — the `%output` ring is octal-escaped but drained through `String::from_utf8_lossy` first, so on the strict payload-type test it is full VT | Socket-name (`-L`/`-S`) | One grammar | Wire protocol (`-CC`) | Native typed | Replace | TCP loopback | L2 | Own-from-birth |
| **Zellij** | Monolithic | Full VT owner | Socket-name | Hint-first | WASM plugins | Native typed | Replace | Named pipes | L2 | Own-from-birth |
| **rmux** | Monolithic | Full VT owner | **Identity-scoped** | One grammar | Typed SDK | Native typed | Replace | Named pipes | L2 | Own-from-birth |
| **herdr** | Monolithic | Full VT owner | Socket-name | One grammar | Typed SDK (3rd-party) | Native typed | Replace | Named pipes | L2 (beta) | Own-from-birth |
| **oly** | Monolithic | **Parallel/raw** | Socket-name (`OLY_SOCKET_NAME`), machine-global default | One grammar | HTTP/WS | Native typed | Replace | Named pipes | L2 | Own-from-birth |
| **qscreen** | Session-only | **Parallel/raw** | Single fixed (per-user) | One grammar | Wire protocol | Native typed | Replace | Named pipes | L2 | Own-from-birth |
| **quil** | Monolithic | **Parallel/raw** | Env-var home (`QUIL_HOME`) | One grammar | MCP (18 tools) | Native typed | Replace | **Naked AF_UNIX** | L2 | Own-from-birth |
| **`wezterm-mux-server`** | Monolithic | Full VT owner | Socket-name (domains) | One grammar | Lua + wire codec | Native typed | Replace | AF_UNIX shim | L2 | Own-from-birth |
| **OpenCode `/pty`** | Session-only | Full VT (UTF-8 string wire) | — (HTTP, per-server) | — | HTTP/WS | Vendor events | No multiplexer | HTTP/WS | **L1+** | Own-from-birth |
| **`ao pty-host`** | Session-only | **Parallel/raw** | Registry file per session | — | Binary wire protocol | Vendor events | Replace | TCP loopback | L2 | Own-from-birth |
| **upterm** | Session-only | Opaque relay (SSH) | — (SSH keys) | One grammar | — | — | Replace | SSH | L1 | Own-from-birth |
| **No-PTY architecture** | — | — (no VT at all) | Env-var home (`CLAUDE_CONFIG_DIR`) | CLI + NDJSON | Hooks (`http` / `mcp_tool`) | **Vendor events** | No multiplexer | pipes / HTTP | you own it | — |

Two things to notice in the columns rather than the rows. **The persistence column is nearly uniform** — almost everything that survives to this table is L2, which means persistence is table stakes and not a differentiator. **The namespace and transport columns are where the field actually disagrees**, and they are the two columns with security consequences.

### Worked example — placing a tool that isn't in the census

The procedure is mechanical, and the fastest way to show that is to run it on something the census dismissed in one line. Here is [`mobydeck/atch`](https://github.com/mobydeck/atch) — a C project, 318 stars, pushed 2026-03-20, whose own description is "atch lets you attach and detach terminal sessions" — walked through all ten axes from scratch. **Note the language, because the checks have to be translated:** the greps in this section are written in Rust idiom (crate, manifest, `cfg(unix)`) and the equivalents in a C tree are a different set of strings — look for `libvterm`/`vtparse`/`terminfo` where you would look for a VT crate, for the `Makefile`/`configure.ac`/`#include <termios.h>` where you would read `Cargo.toml`, and for `#ifdef _WIN32` where you would read `#[cfg(unix)]`. The axis does not change; the string you grep for does.

1. **Coupling** — no `split` / `new-window` / `select-pane` verb in the CLI, so **session-only**.
2. **State ownership** — no VT or terminal-emulation dependency anywhere in the build (no `libvterm`, no vendored parser, nothing in the `Makefile`), and it forwards the child's stream, so **opaque relay**. No redraw on reattach.
3. **Namespace** — the socket path comes from an argument, so **socket-name-as-namespace**.
4. **Command language** — one small verb set, no config-file grammar, so **one grammar**, trivially.
5. **Extensibility** — none published, so no pole.
6. **Agent state** — nothing typed exposed, so no pole; a consumer would have to scrape, which the headless constraint disqualifies.
7. **Substrate** — owns its own PTY, no tmux prerequisite, so **replace**.
8. **Transport** — POSIX sockets and `forkpty` throughout, with no `#ifdef _WIN32` branch and no Windows build path at all, so **POSIX-gated UDS**. **This is the disqualifying cell.**
9. **Persistence** — a detached daemon, re-attachable, so **L2**.
10. **Timing** — spawns its own child, so **own-from-birth**.

**Refuted, on the native-Windows constraint, decided entirely by axis 8.** Two properties of that outcome are worth naming, because they are what you get from running the procedure rather than forming an impression. **The conclusion falls out of a single cell** — you did not have to weigh L2 persistence against the missing plugin system, because a POSIX-only transport ends the conversation. And **the reason is recorded in a form the next reader can re-check in one grep**, which is what stops the same tool being re-evaluated in six months. Every refuted candidate in the census was reached this way.

The sequence in commands, against a repo you just cloned:

```powershell
# Variables, not <angle brackets>: `<` is a reserved redirection operator in PowerShell.
$repo = 'https://github.com/mobydeck/atch'
$tool = 'atch'
git clone $repo tool
Set-Location tool

& $tool --help                                          # axes 1 and 4: which verbs exist?
rg -n 'vt100|vte|termwiz|ghostty|charmbracelet/x/vt|libvterm'   # axes 2 and 6: an emulator at all?
rg -n -g '*protocol*' 'Data|payload|chunk'              # axis 2: bytes or string on the live path?
rg -n 'socket|pipe_name|SOCKET_NAME|_HOME'              # axis 3: what is the default name made of?
rg -n 'tmux'                                            # axis 7: is tmux a prerequisite?
# axis 8: the five transport greps above
# axis 9: the kill-the-parent ritual above
rg -n 'AttachConsole|CreatePseudoConsole|forkpty'       # axis 10: whose PID goes into the attach call?
```

**A trap in step two, and it is an easy one to fall into:** a file sitting in a `tests/` directory is not a test. oly's `tests/output-copilot.log` reads as evidence of live agent-CLI end-to-end tests; it is a 17,718-byte recorded ANSI dump consumed by `src/session/logs.rs`, the log-rendering *unit* tests, and by nothing that attaches to a live agent. **Before citing a test artifact, find the code that opens it.**

### Seven traps that will misclassify a tool

Each of the following is a mistake a competent engineer makes independently, and most of them quietly disqualify a viable tool or promote a broken one. They are stated as standing traps because they will still be traps when this census is stale.

**Trap 1 — reading "it uses a Unix socket" as "it cannot run on Windows".** The intuition is that a `UnixListener`, a `net.Listen("unix", …)`, or an `#[cfg(unix)]` module means the tool is POSIX-only. **That has been false since Windows 10 1803**, when AF_UNIX became a real Windows transport; the sockets work on Windows 10 17063 and later. WezTerm proves it deliberately (`wezterm-uds/src/lib.rs` dispatches to `uds_windows::UnixStream` under `#[cfg(windows)]`) and Codex proves it deliberately (`codex-rs/uds/src/lib.rs:1` opens with "Cross-platform async Unix domain socket helpers"). quil proves it accidentally, with an unconditional `net.Listen("unix", …)` at `internal/ipc/server.go:311` that works on Windows anyway. **So quil is simultaneously an AF_UNIX tool and a viable native-Windows candidate; both are true.** Keep the *hygiene* question ("does the code know it is on Windows?") separate from the *portability* question ("does it run there?") — that is why the transport axis has four poles instead of two. Two related beliefs die with this trap: quil's own ADR-2 says it uses named pipes on Windows, which was **never implemented** (no build-tag split in `internal/ipc/`, no `go-winio` in `go.mod`, the claim exists only in prose at `docs/architecture.md:20`); and psmux was believed to have migrated to named pipes via PR #13, which was **closed without being merged**, leaving psmux with no named-pipe IPC at all and a bolted-on `AUTH` key over TCP.

**Trap 2 — treating state ownership as a binary, and concluding the double parse is unavoidable.** It is not. `AttachMode::Bytes` in qscreen, the WebSocket `Data` message in oly, `MsgPaneOutput` in quil and `%output` in psmux's `-CC` mode all ship bytes on the live path today while maintaining a VT model for snapshots. Two pieces of evidence commonly cited *for* the old binary are misreadings. **ripple's `HANDOFF_GARBLING.md` shows the opposite of what it is cited for** (`yotsuda/ripple`, a C# MCP-plus-ConPTY session tool): the broken component was `CommandOutputRenderer`, a naive **logical-line** model with `MaxCol=100,000` and no grid, which interpreted `\r\n` as a real logical newline and let a following cursor-position sequence collide with a prompt echo already sitting on that row. The VT-emulating path — the one the double-parse story blames — is the path the document says was fine throughout: its `peek_console` route goes through `VtLiteState`, which maintains a visual grid, "so it was OK from the start". **Two disclosures on that quotation.** The document is written in Japanese, so the English wording here is a *translation*, not a verbatim quote — do not re-quote it as one. And no repository URL was recorded for the file, so treat the pointer as approximate; the finding, that a grid-based model was not the broken component, is the load-bearing part and it is legible in the source either way. And **quil's 0x9C-in-UTF-8 bug is not double-parse corruption**: quil's own tech-debt notes classify it as an upstream `charmbracelet/x/vt` spec-compliance defect with a known correct general fix, already worked around, and found on macOS.

**Trap 3 — treating persistence as a boolean.** "Does it persist?" collapses at least four distinct behaviours, and the collapse always flatters the tool. ttyd is widely recorded as having "partial persistence" and has **none** — `src/protocol.c` kills the per-connection process unconditionally on close. Coder's `reconnectingpty` reconnects, which reads as persistence, but **self-terminates after five minutes with nothing attached**. OpenCode's `/pty` needed a level of its own (L1+) because cursor-resumable replay genuinely is more than L1 and genuinely is not L2. And the blanket claim that every non-multiplexer route gives up persistence or reattach is false in both directions: Windows' own `tscon` gives you both natively, and `codex app-server --listen ws://` is a standing listener the client does not own.

**Trap 4 — believing late attach is a live design pole.** node-pty passes its own child's PID to `AttachConsole`, so the prior art everybody cites proves the opposite of what it is cited for. Covered in full above.

**Trap 5 — checking the header instead of the consumer, and the constant instead of the default.** A `#define`, a literal, or a flag in a header tells you what a value *can* be, never what the running code does with it. This trap fires twice in this guide with opposite signs: the "portable-pty confers a flag advantage over node-pty" claim survived for years on two header reads and dies on one code search over `microsoft/terminal` for who actually reads `dwFlags`; and oly gets placed at the bottom of the namespace axis by anyone who reads its default socket-name literal without reading the `std::env::var` call two lines up.

**Trap 6 — treating a file in `tests/` as a test.** oly's `tests/output-copilot.log` reads as evidence of live agent-CLI end-to-end tests. It is a 17,718-byte recorded ANSI dump consumed by `src/session/logs.rs`, the log-rendering *unit* tests, and by nothing that attaches to a live agent. **Before citing a test artifact, find the code that opens it.**

**Trap 7 — treating "a Windows release artifact exists" as proof of a working Windows daemon.** ttyd is the counterexample and it is exact: real ConPTY-capable source, an MSVC fix merged 2026-03-19, and the only shipped Windows binary — `ttyd.win32.exe`, MinGW, 1.7.7, 2024-03-30 — cannot spawn a child on Windows 11 build 26200. **Check that the *released* artifact is recent enough to contain the fixes in master**, and check what your package manager actually pins; WinGet and Scoop both still serve the broken 1.7.7.

**And one more that is about metadata rather than design, because it flipped a verdict here.** `updated_at` on a GitHub repository ticks on stars and watches. **Read `pushed_at`.** A project can look updated three weeks ago and have had no code pushed for nineteen months.

## The seven standalone daemons

Ten projects on native Windows satisfy the structural predicate — **they own a ConPTY, they survive the *client* that spawned them dying, and they expose an interface that is not a GUI.** Read "the client" precisely: it is what lets OpenCode's `/pty` into the set at L1+ even though its sessions die with the `opencode serve` host process. Surviving the *host* is L2, and that is a stronger property that most but not all of the ten have. Seven of them are standalone daemons you can install or build and point an ADE at today. Three more exist only inside a larger product and are covered after these.

Every one of them is **own-from-birth**: the daemon spawns the agent and holds the `HPCON` from the first instruction, for the reasons set out under [Who owns the session](#who-owns-the-session-whoever-called-the-pty-spawn-api). None reaches into a console it did not create.

Star counts and last-activity dates below are a **2026-08-02 snapshot** and churn weekly. Read them as a rough liveness signal, not a number.

**Before the individual entries, the one procedure that decides the category.** Every daemon here claims to survive its parent. Start a detached session, kill the parent terminal window outright, open a new terminal and run the tool's `ls` verb: **still listed and re-attachable is level 2**, and level 2 is the whole point. A tool printing "session created" proves nothing about it, and neither does a daemon still visible in Task Manager — a live child with no re-attach path is a supervisor, not a middle layer, and both questions have to answer yes. The exact commands, including the kill that measures the design rather than the process tree, are in [The verification ritual](#the-verification-ritual).

**A caveat that applies to every command block from here to the end of the guide.** The install and drive lines come from each project's own install documentation and verb list. **None of them was executed on a Windows machine in any pass of this research.** Treat them as the right shape and verify the exact spelling against the version you download.

---

### psmux — a Windows-only tmux workalike with tmux's control mode

**What it is.** A Rust tmux workalike, MIT, 3,140 stars, pushed 2026-08-02, that speaks the tmux verb set and tmux's machine protocol — and runs on Windows and nowhere else.

**How it works.** psmux owns the ConPTY through a vendored `portable-pty-psmux` 0.9.6 at `crates/portable-pty-psmux`, patched in-tree. Its control listener is loopback TCP — `TcpListener::bind(("127.0.0.1",0))` at `src/server/mod.rs:839` — with an application-layer `AUTH <key>` handshake at `src/server/connection.rs:304-315`. A client speaks either ordinary tmux CLI verbs or **tmux `-C` / `-CC` control mode**: you send tmux commands, it replies with `%begin` / `%end` / `%output` / `%layout-change` lines, and the outer program owns rendering while psmux owns sessions. The control-mode implementation is `src/control.rs` (554 lines) plus `docs/control-mode.md` (432 lines) — this is a documented surface, not an accident. Sessions are level 2: they survive the parent.

Note what the two modes do to your bytes. The TUI path is a **full VT owner** — it parses everything into a grid and re-emits rendered ANSI. The `-CC` path ships the pane's output ring octal-escaped through `%output` (`src/server/mod.rs:1222-1227`), which keeps the ADE's own xterm.js closer to being the only renderer in the chain.

**Install and drive it.**

```powershell
winget install psmux.psmux        # or: scoop install psmux
psmux new-session -d -s probe     # detached session
psmux ls                          # then kill the parent window and run this again
```

**What it is genuinely good at.** Two things nothing else in the census matches. First, **the contract is tmux's**, which is the most-cloned terminal contract in existence — at least five independent implementers of `-CC` exist (iTerm2, WezTerm, psmux, Tomiyou/ivyterm, paulrobello/par-term), so a client you write against it is not client to one project's whims. Second, **its CI runs `cargo audit --deny warnings`** against both the workspace and the test-monitor lockfile, a supply-chain gate no other small candidate has. It also answers ConPTY's startup handshake, with a dedicated `tests-rs/test_cpr_responder.rs`, and its pipe mode negotiates terminal size in band rather than guessing — the mechanism, and the 120x30 fallback that makes it a hazard if nothing answers, are under the four things a middle layer must get right on Windows.

**And psmux carries the only external field report in this entire research, which is worth more than its tier suggests.** Almost nothing in this guide has been run by anybody other than a project's own author. The one exception is a [multi-week writeup by an independent developer](https://laurentkempe.com/2026/03/31/from-3-worktrees-to-n-ai-powered-parallel-development-on-windows/) running psmux with Copilot CLI across git worktrees **on native Windows**: "I can detach from a session, close my terminal, come back hours later, and reattach to find everything exactly where I left it — agents still running, output still visible… **No WSL required. No dependencies.**" That is a personal blog, not a project's own documentation, and it should be read at that tier — but it is **the strongest available evidence that somebody other than the author runs any candidate in this guide in anger, and that L2 persistence works in real use on native Windows**, which is the exact property you are shopping for. (One correction on provenance: this report has circulated with its author described as "a .NET MVP". The string "MVP" does not appear on the cited page and that descriptor is withdrawn.) Where this guide says "almost nothing here has been run", this is the qualification.

**The unauthenticated cross-session port — output exfiltration and input injection through one socket.** This is the defect to read twice. Alongside the authenticated control listener, `src/cross_session_server.rs` opens a **second, completely unauthenticated** channel. Line 98 binds `TcpListener::bind("127.0.0.1:0")`. Line 127 accepts **the first connection with no handshake at all**. Lines 131-132 push that socket into `crate::types::PIPE_WRITERS` as a **tee writer**, so the connecting process receives a copy of every byte the pane's ConPTY emits. Line 149 writes everything it reads back into `pty_writer.write_all()`. That is full-duplex — exfiltration *and* injection — unauthenticated, on a loopback port any local process can scan, gated only on the user performing a cross-session pane move. Whether that gate is reachable in normal operation has not been traced (Q6, about three hours: trace every call site of `cross_session_server`, or attempt a proof-of-concept connect during a pane move). Until someone does, treat psmux as unsafe on a shared or multi-user machine, and pin the version you audit.

**The `from_utf8_lossy` that corrupts Unicode permanently.** `src/server/mod.rs:1225` calls `String::from_utf8_lossy(&bytes)` on each ring drain before escaping, so **a multi-byte character split across two drains becomes U+FFFD and never recovers** — the replacement character is what gets stored and re-emitted, not merely what gets displayed. This is a bytes-to-string bug rather than a double-parse bug, and it is a property of string-typed terminal transports generally rather than one project's defect; the general case, and OpenCode's instance of it, are under [Nesting](#nesting-your-middle-layer-runs-inside-the-ades-conpty).

**Two smaller things that will bite you.** The control-mode auth key is generated from `std::collections::hash_map::RandomState` over a nanosecond timestamp plus PID, truncated to 64 bits (`src/server/mod.rs:852-860`) — explicitly non-cryptographic per Rust's own documentation — and the key file gets no explicit ACL, with the source comment at `:864` conceding that "user-only visibility on Windows comes from the profile directory ACLs". And the nesting guard **names the wrong environment variable in its own error message**: the check at `:954` and `:4056` reads `PSMUX_ALLOW_NESTING`, while the text printed at `:958`/`:4060` says *"psmux: sessions should be nested with care, unset PSMUX_SESSION to force"*. A scripted wrapper that obeys the message will not clear the guard.

**Orphaned processes on Windows teardown — an operational defect, unevenly distributed.** A blanket claim that all four small candidates leak orphaned processes when a session is torn down on Windows does not survive checking, but what does survive is uneven and worth knowing before you run any of them at one-agent-per-worktree scale: issue-tracker evidence **supports it for psmux**, **partially for quil**, shows **zero evidence for oly**, and is **necessarily zero for qscreen** — which has no external users to file reports, so its silence means nothing either way. Treat orphan cleanup as something you verify yourself (start ten sessions, kill the daemon, count what is left in Task Manager) rather than something any of these projects has demonstrated.

**And the platform, stated plainly.** psmux is **Windows-only**. Its CI builds only `x86_64/i686/aarch64-pc-windows-msvc`; release v3.3.7 ships six Windows-only assets; the `ubuntu-latest`/`macos-latest` job is called `posix-helper-tests` and runs two shell scripts, **not a build**. Language statistics that say "mostly PowerShell" are misleading — the installer and test suite are the byte count, the product is the Rust binary.

**One more, if you plan to use `-CC` from inside an ADE.** The maintainer's own warning at `src/main.rs:4188-4193` scopes ConPTY's DCS-eating corruption to the SSH case, and whether it generalises to a node-pty ConPTY is an inference rather than psmux's claim — the quote, the corroborating Microsoft issue and the remedy are under [Nesting](#nesting-your-middle-layer-runs-inside-the-ades-conpty). The order to test in matters more than the test: ask whether ORCA's `agentCmdOverrides` can produce a raw-pipe child at all (Q1a) before measuring whether the corruption happens (Q1), because if the cure is unreachable the disease is moot and psmux drops to its plain CLI verbs.

---

### Zellij — best-verified Windows claim and an explicit nesting policy, at the cost of an unverifiable detached-start path

**What it is.** A Rust multiplexer, MIT, 34,647 stars, pushed 2026-08-01, whose Windows port shipped in 0.44.0 — and the candidate whose Windows support claim is **best** verified in this census, from source through to release artifacts. Not the only one so verified: rmux is source-verified (`stream_windows.rs`, `server_identity_windows.rs`, `rmux-pty/.../io.rs`) *and* ships winget, scoop and choco packages, and psmux is source-verified with six Windows assets on v3.3.7. Zellij's advantage over both is breadth, not uniqueness.

**How it works.** ConPTY directly: `zellij-server/src/os_input_output_windows.rs` calls `CreatePseudoConsole` / `ResizePseudoConsole` and holds the `HPCON`. IPC is **Windows named pipes** through the `interprocess` crate (`zellij-utils/src/ipc.rs:8`). The client is the `zellij` CLI plus a WASM plugin runtime that has been protobuf-schema'd since 0.38.0. Zellij is a **full VT owner** — it parses into a grid and re-emits. Resize is handled by polling `crossterm::terminal::size()` every 50 ms on the VT-reader path (`os_input_output_windows.rs:95` doc-comment, `:176` sleep), with a second 100 ms poller at `:38`/`:52`.

Persistence is level 2. **Be careful about what the usual citation for that proves, because the source says something different from what it is quoted for.** `zellij-client/src/lib.rs:463-480` spawns with `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`, and those flags are frequently quoted as "the mechanism" for surviving the parent. They are not. `CREATE_NO_WINDOW` suppresses a console window; `CREATE_NEW_PROCESS_GROUP` detaches Ctrl+C group delivery; **neither implements parent-death survival**, and on Windows a child does not die with its parent by default anyway — which is what actually makes L2 nearly free here. The doc-comment above that spawn says so in as many words, and it is worth reading because it also warns you off the flag you might otherwise reach for:

> On Windows there is no daemonize — we launch the server as a background process with a hidden console. We use `CREATE_NO_WINDOW` (**not** `DETACHED_PROCESS`) so the server gets valid standard handles; `DETACHED_PROCESS` leaves stdin/stdout/stderr as NULL, which breaks PTY creation, WASM plugin loading, and logging.

So Zellij's L2 is real, the flags are hygiene rather than the load-bearing part, and there is a design lesson in there for anyone copying `ao pty-host`'s `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` pattern: **`DETACHED_PROCESS` nulls your standard handles**, and Zellij hit that and backed out of it.

**Install and drive it.**

```powershell
winget install zellij-org.zellij   # or the v0.44.3 x86_64-pc-windows-msvc .msi / .zip
zellij list-sessions
```

**One honest gap in the drive line, and it is in the verb you need most.** Zellij has **no documented flag equivalent to `psmux new-session -d`** — no `-d`, no `--detached`. The invocation `zellij --session probe options --help` that circulates as a "create a session" line does nothing of the sort: it prints help and creates no session. **This guide has no verified detached-start invocation for Zellij**, and that is a real hole, because step 1 of the verification ritual cannot be run against Zellij with anything here. The interim path is the interactive one — `zellij attach --create probe` to make or join a session named `probe`, then detach with the `Ctrl-o` `d` chord — which works but needs a human at the keyboard, which is exactly the property under test. Settle it by reading `zellij --help` and `zellij options --help` on the version you install, and do that before you conclude anything from a failed step 1.

**What it is genuinely good at.** Maturity and packaging: v0.44.3 ships `zellij-x86_64-pc-windows-msvc.zip` and an MSI, and Linux and macOS were the original targets, so you get uniform behaviour across the platforms you run. It is also the **only candidate with an explicit nesting policy**: `nested_session_handling` takes `ask` / `fullscreen` / `descend` / `never` at `zellij-utils/assets/config/default.kdl:268-275`. Every other multiplexer either refuses nesting or lets you force it with an environment variable; Zellij lets you declare what should happen.

**The `TERM`/`WT_SESSION` gate — do this first, then read why.** Set `TERM` in your override command and compare:

```powershell
$env:TERM = 'xterm-256color'   # forces the VT input path; re-run and compare behaviour
```

Now the reason. `zellij-client/src/os_input_output_windows.rs:32` decides between a VT-byte input path and a native-console `INPUT_RECORD` path with `use_vt_path() { env::var("TERM").is_ok() || env::var("WT_SESSION").is_ok() }`. Inside an ADE's node-pty ConPTY, **neither variable is necessarily set**, so Zellij takes the `else` branch. Be precise about what that means: the `else` branch is the native-console `INPUT_RECORD` path, it **is implemented**, it is the conservative choice under a real console, and ConPTY *does* give the child a real console. Calling it the wrong path is unevidenced. What is genuinely unknown is **what the symptom would even be** if the native-console path misbehaved under a nested ConPTY — dead keyboard, garbled input, or silently fine — so there is no pass/fail criterion until someone runs it. This is a **configuration check, not a hazard**; the test costs about an hour (Q3) and settles the objection most often raised against Zellij on Windows.

**Known Windows rough edges**, from the project's Windows tracking issue [#4745](https://github.com/zellij-org/zellij/issues/4745) — opened by `imsnif`, the project lead, with `divens` (a contributor, and the author of the Windows port) as its heaviest commenter: no sixel, unreliable OSC 7 and live-cwd under PowerShell, focus-report sequences not reaching subpanes, and scroll-mode stickiness. (If you go looking for the config file, note the path is `zellij-utils/assets/config/default.kdl` — the bare `assets/config/default.kdl` path that circulates elsewhere 404s.)

---

### rmux — identity-scoped named pipes and typed SDKs, against a single-author bus factor

**What it is.** A Rust daemon with 90-plus tmux-compatible verbs, 2,533 stars across 12 crates and 21 MB, pushed 2026-07-26.

**How it works.** Named pipes — but the pipe **name is computed, not chosen**. `crates/rmux-ipc/src/endpoint.rs` builds `\\.\pipe\{prefix}-{sid}-il-{integrity}-{label}` from the caller's SID and integrity level, so the namespace **cannot be entered by a process that merely guesses a string**. It is the only identity-scoped namespace found anywhere, and it is the pole every other candidate falls short of. On top of that it sets `FILE_FLAG_FIRST_PIPE_INSTANCE` (`crates/rmux-pty/src/backend/windows/io.rs`) so a hostile process cannot pre-create the pipe, and it validates the connected peer with `ImpersonateNamedPipeClient` (`crates/rmux-ipc/src/stream_windows.rs`). The PTY layer uses `PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE` and Job Objects with `CREATE_BREAKAWAY_FROM_JOB`, and has an explicit refusal path rather than a silent degrade — the error string is *"breakaway process creation denied; refusing to run unguarded ConPTY child"*. That string is quoted from a source read once; **its exact file and line were never recorded and could not be recovered**, so take the string as reported and the behaviour as verified.

A client speaks tmux verbs, or **typed SDKs in Rust, Python and TypeScript** exposing `session` / `pane` / `snapshot` / `wait_for_text`. There is also a Ratatui widget and an end-to-end-encrypted web share. Persistence is level 2; the tool is a full VT owner.

**Install and drive it.**

```powershell
winget install Helvesec.rmux      # or: scoop install rmux / choco install rmux
rmux new -d -s probe
rmux ls                           # after killing the parent window
```

**What it is genuinely good at.** Security posture and the agent-facing surface. `wait_for_text` and `snapshot` as first-class typed SDK calls are exactly the primitives a headless driver needs — you are not scraping a screen, you are asking a typed question. Combined with the identity-scoped namespace, it is the one candidate here whose security model has three independent layers rather than one, and if you are writing a middle layer yourself it is the shape worth copying — the namespace derivation in particular, which costs almost nothing to implement and removes a whole class of problem.

**The failure here is procurement, not code.** Two exposures, both human. **936 of roughly 1,000 commits come from a single author** — a figure recorded once and **never re-verified**, so treat the exact ratio as approximate and the concentration as real. And the project is dual-licensed **with the pair unstated in repository metadata**; GitHub reports `NOASSERTION`. If you intend to vendor rmux, **read the `LICENSE-*` files at the exact tag you would vendor before relying on it** — you cannot answer the licensing question from the repo page. Nesting behaviour was never tested, on any pass.

---

### herdr — a large project whose Windows build is on the preview channel

**What it is.** A Rust multiplexer/ADE hybrid, Apache-2.0, 23,466 stars, pushed 2026-08-01, with a CLI, an HTTP API (`src/api/server.rs`) and third-party TypeScript and Python SDKs.

**How it works.** Named pipes via the `interprocess` crate, same family as Zellij and oly. Full VT owner, level 2 persistence — but on Windows every one of those properties carries a `beta` label, from the project's own documentation.

**Install and drive it.**

```powershell
# There is no winget/scoop path. Download the dated preview asset from the releases page:
#   https://github.com/herdrdev/herdr/releases
# The tag is a dated preview with a commit suffix - `preview-2026-07-29-44b3adb12552`, not
# the bare `preview-2026-07-29` that circulates - and the Windows asset in it is
# herdr-windows-x86_64.zip.  Confirm the exact tag on the releases page before scripting it:
$tag = 'preview-2026-07-29-44b3adb12552'
Invoke-WebRequest -Uri "https://github.com/herdrdev/herdr/releases/download/$tag/herdr-windows-x86_64.zip" `
                  -OutFile "$env:TEMP\herdr-windows-x86_64.zip"
# NOT stable v0.7.5 - that release ships linux and macos assets and NO Windows asset.
herdr list
```

**What it is genuinely good at.** It has the maintenance base — 23k stars and daily activity — that the small candidates lack, and an HTTP API plus SDKs means the drive surface does not depend on a terminal being attached. Its Windows-beta page lists **"Nested launch override | beta"** under Supported, which is as close as any project comes to documenting the topology you need.

**"Direct terminal attach — unsupported": the reading first, then the evidence.** The reading is that "Direct terminal attach" almost certainly means the **Unix file-descriptor handoff path, not the ADE-spawn path** — which would leave herdr a live candidate. **That reading is an inference, not something herdr states**, and it needs confirming: read `src/api/`, `src/ipc.rs` and the surrounding doc sections, and file one question on the repo if it stays ambiguous. Budget two hours (Q2). If it is the Unix mechanism, herdr is live; if it is the ADE path, herdr is out on Windows until the beta lands.

Here is what the inference rests on, and it is the shape of the page rather than any one row. The Windows-beta document (`website/src/content/docs/windows-beta.mdx`) has **two** tables, and reading only one of them is how this became the biggest open risk in earlier drafts of this research. The **Supported** table lists "Local persistent sessions | beta", "Native panes through ConPTY | beta", "**Windows Terminal / PowerShell app attach | beta**", "Pane screen history | beta" and "Nested launch override | beta". The **Not supported** table lists "Direct terminal attach | unsupported", "Live server handoff | unsupported", "Unix file-descriptor handoff | unsupported", "Unix foreground process groups | unsupported" and "Prefix input-source switching | unsupported". Read together: "Direct terminal attach" sits in a cluster of Unix-specific mechanisms — fd handoff, live server handoff, foreground process groups — while the ADE-spawn path is separately listed as *supported in beta* on the table above it. **When a page is a capability matrix, the negative half is not the page.**

**The failure you will actually hit is the channel.** There is **no stable Windows release to pin**. You install a dated preview build (`preview-2026-07-29-44b3adb12552` at the time of writing — dated tag plus commit suffix), and the next preview replaces it. For a layer whose entire purpose is to be more durable than the ADE above it, depending on a preview channel is the wrong direction. Note also that "**Prefix input-source switching | unsupported**" is the **only primary-source statement about prefix keys on Windows found anywhere in this research** — every other candidate's rebindability is an inference from "it has a config file."

---

### oly: real Windows PTY tests, no pipe ACL

**What it is.** `slaveOftime/open-relay` — a Rust session daemon, MIT (verified two ways: `gh api` reports `spdx_id MIT` and there is a `LICENSE` at the repo root), 89 stars, `main` HEAD 2026-07-01 with `pushed_at` 2026-07-30 across four side branches.

**How it works.** Named-pipe IPC through `interprocess` `GenericNamespaced`, plus an HTTP/WebSocket surface and push notifications. Its live path is **raw bytes** — `ServerMessage::Data { data: Vec<u8> }` at `src/http/ws.rs:36-46` — so it maintains a VT model for snapshots and scrollback while shipping the child's actual bytes to the client. That matters: it means **the ADE's own xterm.js can be the only VT parser in the chain**, and the "unavoidable double parse" story is false. Level 2 persistence. The socket name comes from `OLY_SOCKET_NAME` and falls back to `open-relay.oly.sock` (`src/config.rs:123-126`).

**oly is widely credited with answering ConPTY's startup handshake. Read the function before you rely on that, because it answers a different set of queries than the credit implies.** `extract_query_responses_no_client`, in `src/session/pty.rs`, answers **CPR, DSR and the OSC 10/11 colour probes** when no client is attached, and its own comment states what it deliberately refuses: "Do NOT respond to: **PrimaryDeviceAttributes (DA1)**, SecondaryDeviceAttributes (DA2), XtVersion (XTVERSION), DecPrivateModeReport (DECRPM), KittyKeyboard… Answering them in detached mode can cause interference with user input and corrupt the output stream." A unit test in the same file asserts that DA1, DA2 and XTVERSION go unanswered in detached mode. The DA1 reply string exists in the response generator (`\x1b[?62;c`) for the attached case; it is not emitted on the detached path. **Since DA1 is the query behind the three-second startup stall, oly's detached mode does not eliminate that stall.** Whether that costs you anything depends on whether something upstream answers DA1 — which is what the DA1 probe above tells you, and it is the first thing to check if oly-hosted spawns take seconds.

**Install and drive it.** There is **no package-manager install line for oly** — the winget/scoop/choco paths in this guide cover psmux, Zellij, rmux, herdr, `wezterm-mux-server` and OpenCode only. You clone and build, and **the result is not on your PATH**:

```powershell
git clone https://github.com/slaveOftime/open-relay
Set-Location open-relay
cargo build --release              # generic Rust build; not a documented install path
# The binary lands in .\target\release\ and is NOT added to PATH. Invoke it by path,
# or add that directory to $env:PATH for the session:
$env:PATH = "$PWD\target\release;$env:PATH"
$env:OLY_SOCKET_NAME = 'oly-orca'  # per-instance namespace; the default has no user component
```

**What it is genuinely good at.** One thing, and it is not nothing: **a real `windows-latest` PTY test matrix**. `tests/e2e_daemon.rs` and `tests/e2e_pty.rs` run under a CI matrix that includes `windows-latest` (`.github/workflows/ci.yml`) and actually exercise ConPTY. No other small candidate has that. Add the raw-byte live path and MIT licensing and there is a real design here.

**The unauthenticated named pipe with no ACL — the disqualifying-adjacent one.** `src/ipc.rs` is 296 lines and contains **no ACL, SID or security-descriptor keyword at all**; `FILE_FLAG_FIRST_PIPE_INSTANCE`, `security_descriptor` and `SECURITY_ATTRIBUTES` are **zero hits repo-wide**. Microsoft's own `CreateNamedPipe` documentation states that a NULL security descriptor grants "read access to members of the Everyone group and the anonymous account." For a pipe carrying **agent terminal I/O**, that is an API-key disclosure path — whatever the agent prints, and whatever you type into it. And with no `FILE_FLAG_FIRST_PIPE_INSTANCE`, a hostile local process can **pre-create the pipe and harvest client connections**. The project knows: `milestones/M4_security_hardening.md` lists "Windows: enforce named-pipe ACL (current-user SID only)" with status "⏳ Not started", **untouched since 2026-03-12**. A later security audit (PR #83) fixed the web layer — 3 High findings including command injection in notification hooks, permissive CORS and no rate limiting on node-join, plus 14 Medium and 4 Low — and Unix socket modes, but **no Windows pipe-ACL item appears in that findings table**. Checking whether the gap was closed without updating the roadmap is a one-hour diff of `src/ipc.rs` across the commit history (Q13).

**The nested-agent tests do not exist.** This is worth stating because oly is the candidate most often credited with having them. `tests/e2e_pty.rs` is 895 lines and contains **zero occurrences of `copilot` or `opencode`**. It spawns **shells** — `cmd.exe`, `bash --noprofile --norc`, `pwsh`. The `tests/output-copilot.log` file that makes it look otherwise is a 17,718-byte **recorded ANSI dump** consumed by `src/session/logs.rs`, the log-rendering unit tests — not by the PTY end-to-end tests, and not by anything that attaches to a live agent. oly tests shells under ConPTY on Windows. It does not test nesting and it does not test agent CLIs.

**And a fixture that cuts against cross-platform uniformity.** oly ships `tests/output-copilot.expected.windows` **alongside** `tests/output-copilot.expected` — a Windows-specific expected output for the *same* input log. That is direct evidence that its VT and log-rendering layer **produces different output on Windows than on Unix**. If you value one behaviour across both platforms, that fixture is the finding to weigh.

Two more sizing facts: the **default socket name has no user component**, so two users on one host collide unless one of them sets `OLY_SOCKET_NAME` (the name is env-selectable, which a one-file read misses — the isolation knob exists; the access control does not). And `main` has been still since 2026-07-01 while four side branches move, which is either a plateau or a departed maintainer; four to six weeks of watching issue-response latency settles it.

---

### qscreen — anti-squatting and per-user namespacing, never run by anyone but its author

**What it is.** A Rust **single-pane** session daemon, MIT, 6 stars, pushed 2026-07-21 (the last default-branch commit is "docs(readme): add feature boundaries and quick start").

**How it works.** Named pipes — `crates/qscreen-daemon/Cargo.toml` carries the comment "Windows平台仅需tokio的named_pipe实现" ("on Windows only tokio's named_pipe implementation is needed"). The pipe is `\\.\pipe\qscreen-<user>` (`crates/qscreen-shared/src/lib.rs:6-11`), one instance per user by construction with no per-project knob, and the initial listener sets `.first_pipe_instance(true)` (`crates/qscreen-daemon/src/lib.rs:162`) so it cannot be squatted. The client is a `qscn` CLI speaking a structured `ScreenFrame`/`ScreenRun` protocol with `FRAME_FLAG_*`, `FrameColor` and `FrameMouseMode` — **and** an `AttachMode::Bytes` raw-byte attach mode (`crates/qscreen-protocol/src/lib.rs:56-61`). Level 2 persistence. It is deliberately session-only: no `split`, no `new-window`, no `select-pane` verb exists.

**Install and drive it.** No packaged Windows install path was recorded. Build it:

```powershell
git clone https://github.com/dualface/qscreen
Set-Location qscreen
cargo build --release              # generic Rust build; not a documented install path
# The client binary lands in .\target\release\ and is NOT on PATH:
.\target\release\qscn.exe --help   # verb spellings unverified - read them off the binary
```

**What it is genuinely good at.** Its protocol arrived independently at the same idea as tmux control mode — **parse once, let the last hop render** — and it offers both a structured frame path and a raw-byte path from the same daemon. Its two security choices are correct: anti-squatting on the listener and per-user pipe namespacing. It is not unique in that (rmux does both as well), but it is the sharp contrast with oly, which does neither.

**Zero CI, zero issues, zero external users — nobody but the author has ever run it.** `contents/.github` returns **404**: there has never been CI on any platform. There are zero issues and zero pull requests in the project's history. This is not a claim that qscreen is broken — its design is sound and source-verified, and the honest reading is **unvalidated on evidence, not refuted on design**. But every property in the paragraphs above is "the source says so," with no second party ever having exercised it. There is one concrete aging tell to weigh with that: its `portable-pty` is **0.8, a full minor behind** oly's 0.9 and psmux's patched 0.9.6, in a crate **whose Windows backend changes between minors**. (Its VT crate `crates/vt100-psmux` is a clean `cargo vendor` of the published `vt100-psmux` 0.16.2 — Jesse Luehrs' vt100-rust, patched and republished by `marlocarlo` — the same crate psmux vendors, arrived at independently rather than copied.)

---

### quil — an 18-tool MCP surface, on ubuntu-only CI and a socket path that deletes live daemons

**What it is.** A Go session daemon, MIT (verified two ways), 11 stars, pushed 2026-08-01, shipping roughly one release a day, whose primary interface is an **MCP server with 18 tools**.

**How it works.** ConPTY through `charmbracelet/x/conpty v0.2.0`, with Microsoft's redistributable ConPTY bundled via `scripts/fetch-conpty.sh` and SHA256-pinned — and loaded by **absolute path**, `filepath.Join(filepath.Dir(exe), "conpty.dll")`, which is the safe way to do it. Live output is raw bytes: `PaneOutputPayload { Data []byte }` at `internal/ipc/protocol.go:204-208`. Screen state is typed: `MsgScreenshotPaneResp{Text, CursorX, CursorY}`. There is mouse-mode forwarding for nested alt-screen applications (`internal/daemon/mousemode.go`) — the only such accommodation this survey noticed, in an area it covered only glancingly, so read that as "nobody else advertises one" rather than as "nobody else has one". `QUIL_HOME` relocates the entire state root, which is the per-workspace isolation analogue of `CLAUDE_CONFIG_DIR`. Persistence is level 2. Clients: MCP, the `quild` CLI, and a TUI.

**The transport is not what its own architecture decision record says it is.** `internal/ipc/server.go:311` is `net.Listen("unix", …)`, **unconditional on every platform**. `go.mod` has no `go-winio`; the `ipc/` directory has no `_windows.go` split. quil's own ADR-2 claims Named Pipes on Windows; **that was never implemented**. This is not a portability failure — AF_UNIX is a real Windows transport since Windows 10 1803, so the daemon does work — it is a **security-semantics** failure, covered below.

**Install and drive it.**

```powershell
git clone https://github.com/artyomsv/quil
Set-Location quil
go build ./...                     # generic Go build; not a documented install path
# `go build ./...` writes the executables into the current directory and does NOT
# install them onto PATH (`go install ./...` would put them in $env:GOPATH\bin).
# Invoke quild by path, or add the build directory to PATH for the session:
$env:PATH = "$PWD;$env:PATH"
$env:QUIL_HOME = "$env:USERPROFILE\.quil-orca"   # isolate this instance - see the os.Remove problem
```

**What it is genuinely good at.** **MCP is what an agent already speaks.** Eighteen tools is the richest agent-facing surface in the census, and it means the middle layer's control plane needs no new client library — an agent can drive sessions with the same mechanism it uses for everything else. Add the raw-byte live path, typed screenshots and mouse-mode forwarding and the interface design is the best in the small-candidate field.

**The unconditional `os.Remove` that bricks a live daemon.** `internal/ipc/server.go:309` is one line: `os.Remove(s.path) // Clean up stale socket`. It runs **unconditionally at the top of `Start()`, before `net.Listen`, with no liveness check on the existing socket.** A second `quild` started against the same `QUIL_HOME` therefore **deletes a live daemon's endpoint by design**. This is not a hypothetical: PR #51 documents a dated production incident on 2026-06-10 in which exactly that happened and "brick[ed] the original for new clients" — in the very instance-isolation mechanism that was previously reported as a strength. The same audit fixed a VT-emulator-disposal race that leaked a goroutine **plus a 10,000-line scrollback grid per closed pane**, an unbounded PTY-coalescer debounce buffer, and a Windows `WaitExit` handle leak per destroyed pane. If you run quil, give every instance its own `QUIL_HOME` and treat a second daemon on the same home as a destructive operation.

**AF_UNIX on Windows with a no-op `chmod`.** `os.Chmod(path, 0600)` **does nothing on Windows**, and there is no `SO_PEERCRED`, so the socket carries no kernel-enforced permission of any kind. Its only protection is **the ACL on the parent directory**. A properly-ACL'd named pipe — what the ADR promised — is strictly stronger; a loopback TCP port would be strictly weaker. The code sits in the middle and reads, to anyone who knows POSIX, as though the `chmod` did something.

**And the validation gap.** CI is **`ubuntu-latest` only**, across 25-plus Windows-specific source files. **Zero external issues have ever been filed.** Running its test suite on Windows — adding a `windows-latest` job locally and seeing what breaks — costs half a day (Q7) and is the difference between "richest agent-facing surface in the census" and "design reference". Separately: the `✳` in Claude Code's own window title **already broke quil's emulator**, which is the concrete instance of the Unicode failure class described under psmux.

---

## Three that live inside a larger product

These three work, are source-verified, and are not shipped as the thing you want. You either run a host binary that a bigger product installs, or you vendor a package out of its tree. Licensing decides how comfortable the second option is.

### wezterm-mux-server — a version-skew-tolerant codec, reachable on Windows only from a rolling nightly

**What it is.** The headless multiplexer inside WezTerm (28,101 stars, pushed 2026-07-31) — a separate executable, not a mode of the GUI. The RPM spec describes it in exactly those words: "Multiplexer server (headless)". **On the licence, apply the same rule this guide applies to rmux, because the same signal is present:** WezTerm is MIT in substance, but GitHub's licence API reports `NOASSERTION` for the repository (the file is `LICENSE.md`), which is exactly the condition that makes the rmux entry say "read `LICENSE-*` at the tag you would vendor". WezTerm's codec is the one thing in this guide the build-it-yourself path tells you to vendor, so **read `LICENSE.md` at the commit you would vendor from** rather than trusting a summary — including this one.

**How it works.** It daemonizes (`--daemonize`, handled explicitly on Windows) and owns the PTY. Transport is an **AF_UNIX shim** — `wezterm-uds/src/lib.rs` does `#[cfg(windows)] use uds_windows::UnixStream`, and the project documents it: "Unix domains are supported on all systems, even Windows." The wire is a **versioned binary codec** with variable-length integer encoding of length, ident and serial (`codec/src/lib.rs`), and the reason is stated in the source: "so client and server can more gracefully manage unknown enum variants." **That is the ADE-churn insulation you are shopping for, written down by someone who needed it for a different reason.** It also ships a tmux `-CC` client (`wezterm-escape-parser/src/tmux_cc/tmux.pest`, `mux/src/tmux.rs`, `tmux_pty.rs:90-91` with a `#[cfg(windows)] fn as_raw_handle`), and the changelog records a **Windows-specific `tmux -CC` bug being fixed** — so that path has real Windows users. A client speaks 15 CLI verbs: `list`, `spawn`, `split-pane`, `send-text`, `get-text`, `kill-pane`, `proxy` and more. Attach and detach are first-class (`docs/config/lua/MuxDomain/attach.md`). Level 2 persistence. Full VT owner. The binary is copied into the Windows zip and the Inno installer by `ci/deploy.sh:115-124`.

**Install and drive it.**

```powershell
# Download WezTerm-windows-nightly.zip  -  there is no current tagged release for Windows.
wezterm-mux-server --daemonize
wezterm cli list
wezterm cli spawn -- pwsh -NoLogo
wezterm cli send-text --no-paste "claude`n"
wezterm cli get-text
```

**What it is genuinely good at.** Everything about the contract. It is the only wire format in the census **explicitly designed for version-skewed client/server pairs**, it was headless from the first design rather than retrofitted, `get-text` and `send-text` are exactly the two verbs a headless driver needs, and it runs on Windows, Linux and macOS from one codebase.

**No tagged release since 2024-02-03 — you cannot pin a version and be on Windows at the same time.** The newest tagged release is `20240203-110809-5046fc22`, published **2024-02-03, two and a half years old**. The **rolling `nightly` tag** that ships `WezTerm-windows-nightly.zip` is the only current Windows path. So the project with the most stability-conscious wire format in the census forces you onto the least stable distribution channel, and "pin the version you audited" and "run on Windows" are in direct tension. Decide which one you are willing to give up before you build on it. (One navigation note: the repository moved — `wez/wezterm` now 301-redirects to `wezterm/wezterm`.)

**One unverified thing you should check first.** Nobody has driven it headlessly end to end on Windows — `spawn`, `send-text`, `get-text`, `list`, with a client attaching later. Half a day settles it (Q8). **If attach turns out to need the GUI, the codec is a design reference and not a product you can use.** A related hazard if you run it inside another terminal: WezTerm's `portable-pty` loads `conpty.dll` by **bare relative name**, so the DLL search order can pick up a *different* terminal's bundled copy — a known cause of blank panes and broken I/O.

### OpenCode's `/pty` API — a resumable attach cursor, on an undocumented contract and a string-typed wire

**What it is.** An HTTP plus WebSocket PTY API inside OpenCode (TypeScript/Bun, MIT, 192,203 stars, pushed 2026-08-02) that **is documented nowhere on opencode.ai** — the published server documentation has zero occurrences of `/pty`.

**How it works.** The endpoints are `GET`/`POST /pty`, `GET`/`PUT`/`DELETE /pty/:id`, `POST /pty/:id/connect-token` and `GET /pty/:id/connect` (WebSocket), in `packages/opencode/src/server/routes/instance/httpapi/groups/pty.ts`. The wire is raw UTF-8 chunks plus **one control frame — a `0x00` byte followed by UTF-8 JSON — carrying the absolute output cursor after replay, so clients can resume later** (`packages/core/src/pty/protocol.ts`). On Windows it sets `useConptyDll: true` (`pty.node.ts`); the Node path uses `@lydell/node-pty`, the Bun path uses `bun-pty` over WezTerm's `portable-pty`.

**Persistence is level 1-plus, not level 2, and the distinction decides everything.** The session survives a *client* disconnecting and a reconnecting client resumes from an absolute cursor rather than replaying from zero — that is a real property and the only instance of it found anywhere. But **the session dies with `opencode serve`**. It does not survive the host process, so it does not survive an ADE that launched the host.

**Install and drive it.**

```powershell
winget install anomalyco.opencode
opencode serve --port 4096
# then, from any client:
#   POST /pty                        -> create a session
#   POST /pty/:id/connect-token      -> get a ticket
#   GET  /pty/:id/connect            -> WebSocket attach, replay, resume by cursor
```

**What it is genuinely good at.** The shape. Ticket auth, a replay cursor, REST plus WebSocket, and it ships in the Windows binary (`opencode-windows-x64.zip`). Because the transport is a network socket, **console-independence is free** — a network client needs no console at all, which is the one column where almost every multiplexer candidate is untested.

**The UTF-8 text wire with a fatal decoder — it is not byte-exact.** Two defects live in a 38-line file. `chunks(data: string)` slices at `REPLAY_CHUNK = 64 * 1024` using `String.slice`, i.e. in **UTF-16 code units**, so a surrogate pair straddling a replay-chunk boundary is split into lone surrogates. And `decodeInput` uses `new TextDecoder("utf-8", { fatal: true })` inside a bare `try { … } catch { return undefined }`, so **invalid UTF-8 on the input path is silently dropped** — the file's own comment says as much. Applied consistently, the same criterion that condemns psmux's `from_utf8_lossy` demotes OpenCode's wire: describing frames as "raw UTF-8 terminal chunks" does not make the payload type a byte slice, and here the payload type is a JavaScript `string`.

**And there is no contract.** Undocumented means it can change in any release, without notice, with no deprecation path — inside a project shipping at 192k-star velocity. Also unverified: **nobody has confirmed the endpoints work on native Windows with the shipped binary.** That is a one-hour test (Q12) — `opencode serve`, then `POST /pty` and a WebSocket connect from PowerShell. If it works you have a resumable attach surface today; if it fails, the protocol is still worth copying.

### `ao pty-host` — detached survival, scrollback replay, resize arbitration and orphan recovery, inside a `Hidden: true` subcommand

**What it is.** A `Hidden: true` cobra subcommand inside Agent Orchestrator (Untrivial-ai/agent-orchestrator, Go, Apache-2.0, 8,742 stars, pushed 2026-08-02). It is a detached ConPTY host, and it is the closest thing in the census to the layer described in this guide.

**How it works.** `conpty/spawn_windows.go` spawns with `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` — the source comment says "so the host survives daemon exit," which is level-2 persistence stated as an intention rather than inferred. The wire is an 8-message binary protocol, `[1-byte type][BE32 len][payload]`, over loopback TCP (`conpty/proto.go`, `MsgTerminalData 0x01` through `MsgKillReq 0x08`); the payload is raw bytes. `conpty/host.go` "replays scrollback to new clients, fans output to all connected clients," and "on PTY exit it broadcasts a status update but stays alive (keep-alive, mirroring tmux behavior)." `applyLargestLocked` sizes the shared PTY to the **largest attached client** — resize arbitration that no other candidate has. And `conpty/ptyregistry/registry.go` persists `~/.ao/windows-pty-hosts.json` with `{sessionId, ptyHostPid, pipePath}` **so orphans are findable after metadata loss** — a recovery story the other candidates simply do not have. Verbs are `GetOutput(lines)`, `Status`, `Kill`, `SendMessage`. The PTY library is `aymanbagabas/go-pty v0.2.3`.

**Install and drive it.** There is no standalone `pty-host` to install and **no install line for Agent Orchestrator was ever recorded in this research** — the project ships Windows npm binary packages, so `npm i -g` against its published package name is the likely path, but that name was not captured and you should read it off the repository rather than off this page. **The realistic route for a middle layer is not to install AO at all: it is to vendor the package** (Q10), which Apache-2.0 makes legally clean. The verb surface below is what the `ao` CLI exposes over its loopback HTTP REST API, and it is included because it shows the shape the AO team converged on, not because it is a drive line you can paste today:

```powershell
ao spawn                                  # -> POST /api/v1/sessions
ao send --session $sessionId --text 'ls'  # argument shape read off the CLI docs, not executed
ao session ls
ao session get
ao session restore
ao status --json
ao doctor --json
ao completion powershell
# Inside a spawned agent, AO_SESSION_ID / AO_PROJECT_ID let it resolve itself.
```

**What it is genuinely good at.** It is the only candidate that treats **detached survival, scrollback replay, multi-client fan-out, resize arbitration and orphan recovery** as one coherent design rather than four separate features. Apache-2.0 makes vendoring legally clean, which the AGPL candidates in the wider census do not.

**It is not a product — `Hidden: true` is an internal contract, and the source says so about its security too.** `host_main.go` carries its own caveat verbatim: "loopback bind only; **any local process on this host can connect to the assigned port.** A per-session random token handshake is the upgrade path." A hidden subcommand has no compatibility promise; it can be renamed or restructured in any refactor of the surrounding ADE, and the surrounding ADE offers **no agent-command override** (30 compiled Go packages under `backend/internal/adapters/agent/`), so you are not adopting the product, you are extracting a package from it. Whether that extraction is clean is untested: run `go build ./backend/internal/adapters/runtime/conpty/...` outside the AO tree and see what it drags in. Three hours (Q10). **Clean and you have a working detached-ConPTY host to build on instead of writing one; entangled and it is a design reference.**

**One disambiguation, because the names collide.** `Untrivial-ai/agent-orchestrator` — the project described here — and `awslabs/cli-agent-orchestrator` are **different, unrelated projects**.

---

## The PTY-as-a-service lineage: terminal over HTTP, WebSocket or SSH

This is the older family: expose a PTY over a network protocol and let any client attach. The shape is right and the ancestry is instructive. Almost none of it survives contact with native Windows plus a survive-the-parent requirement.

**terminado and `jupyter_server_terminals` — the design template.** Python, BSD-3, 373 and 20 stars; terminado's last code commit was 2024-04-30 (its 2025-08-02 activity is documentation), `jupyter_server_terminals` moved 2026-01-14. It **does run on Windows**, via `pywinpty`. The interface is exactly the shape you would draw on a whiteboard: `GET`/`POST /api/terminals` over REST, and a WebSocket speaking `["stdout", text]`, `["stdin", text]` and `["set_size", rows, cols]`. Persistence depends on which manager you configure — `NamedTermManager` is level 1 (plus a `cull_inactive_timeout`), `UniqueTermManager` is level 0. Read it as a **design template, not an interop standard**, and read two defects with it. `terminado/management.py:23-34` is a **nested `try`/`except ImportError` chain, not a platform conditional**: if both imports fail it binds `PtyProcessUnicode = object` and the failure surfaces much later as an obscure `AttributeError`. And `pywinpty` (`winpty/ptyprocess.py`) bridges ConPTY's non-selectable output by **binding a per-PTY ephemeral 127.0.0.1 TCP listener pumped from a daemon thread** — one loopback port and one polling thread per terminal, an `accept()` race any local process can win, output round-tripped through `str`, and a literal `'0011Ignore'` sentinel injected on empty reads. `pywinpty` is also Windows-only, so it is a component that costs you cross-platform uniformity, and its maintainer has stated publicly that it has >30M downloads, is "maintained by a single person," and has features "delayed… due to this lack of resources." (That statement comes from a 2025 Jupyter Discourse post whose URL was never recorded and which was not re-retrieved, so it is reported rather than verified.)

**ttyd — source builds on Windows, the shipped binary does not run.** C, MIT, 12,113 stars, code activity 2026-03-20. Two independent disqualifiers. Architecturally it is **level 0**: `src/protocol.c:154,353,377-383` creates a **new process per WebSocket** and kills it unconditionally on close, so there is no session to survive anything. And practically, **the only Windows release — `ttyd.win32.exe`, MinGW, 1.7.7, 2024-03-30 — fails to spawn any child on Windows 11 build 26200**, which is this machine's exact build, per [`tsl0922/ttyd` issue #1501](https://github.com/tsl0922/ttyd/issues/1501) (whose body names "Windows 11 25H2 (build 26200)" and which closed 2026-03-19). An MSVC fix was merged 2026-03-19 and **no release has been cut since**; WinGet and Scoop both still pin the broken 1.7.7. If you install ttyd from a package manager today you get a binary that does not work on your OS. This is the concrete instance of trap 7 above: a Windows release artifact exists and proves nothing.

**upterm — public-key authentication, and no detach.** Go, Apache-2.0, 1,270 stars, pushed 2026-07-25. Everything about its Windows engineering is real: ConPTY via `charmbracelet/x/conpty` with Job Objects (`host/internal/pty_windows.go`), release artifacts for `windows_{386,amd64,arm64}` at v0.24.0, and a genuine nested-ConPTY lesson worth stealing — `host/host_windows.go` **deliberately ignores `os.Interrupt`** "to prevent upterm from dying when SSH clients send Ctrl+C to child processes via ConPTY." Its transport is SSH with **public-key authentication** (`--authorized-keys`, `--github-user`, `--gitlab-user`), which is the only real auth model anywhere in this census — every other candidate authenticates with a guessable name, a non-cryptographic token, or nothing at all.

**It has no detach and no reattach, and that is the disqualifier.** upterm is **level 1 only**: the session lives exactly as long as the `upterm host` process. Kill the parent and the session is gone; there is no `ls` verb that would list it and no path to attach a new client to an old session. It fails the single requirement that defines this whole category — surviving the process that spawned it — whatever else it is good at. (Its relay, `uptermd`, is also Linux-only, though the host is not.) **So if you are building your own layer, upterm's auth model is the one to copy; if you are shopping for something to deploy, this is not it** — and if you find yourself wanting it anyway, what you actually want is upterm's key handling bolted onto something with L2 persistence.

**The rest of the lineage, and why each is off the board.** `gotty` cannot build a PTY on Windows at all — its dependency `creack/pty` has `start_windows.go` that literally reads `return nil, ErrUnsupported`, and the maintained fork's release matrix ships FreeBSD, NetBSD, OpenBSD and Solaris while deliberately omitting Windows. `wetty` spawns every PTY, including `--command`, as `pty.spawn('/usr/bin/env', cmd, xterm)` and gates local mode on `process.getuid?.() === 0`, which is `undefined` on Windows. [`sshx`](https://github.com/ekzhang/sshx) does use ConPTY, but its author's own comment in `crates/sshx/src/terminal/windows.rs` reads "I can't get `powershell.exe` to work with ConPTY, since it returns error 8009001d," it takes no arbitrary command argument (only `--shell`), it has no detach, its README says "Self-hosted deployments are not supported at the moment", and **every one of its releases has an empty assets array**. `tmate` is a tmux fork and inherits tmux's POSIX dependency. [`code-server`](https://github.com/coder/code-server) states plainly, in `docs/install.md`: "We currently do not publish Windows releases."

**Two more entries belong in this family and are usually missed.** [**Eclipse Theia**](https://github.com/eclipse-theia/theia) (TypeScript, EPL-2.0, 21,617 stars, pushed 2026-08-01) has a **Windows-capable attach-by-id implementation inside a 21k-star project**: `packages/terminal/src/node/shell-process.ts:90-91` is `if (isWindows) { return 'cmd.exe'; }`, and `base-terminal-server.ts:49` is `async attach(id: number)` against a backend terminal registry. That is the same primitive VS Code's `ptyHost` provides, in a second independent implementation — so it is at minimum a peer of the prior art below. What is unvalidated is its **server-mode packaging**: nobody checked whether Theia's backend can be run headlessly on Windows as a standalone process, which is the only thing that would make it usable here rather than merely instructive. And [**ghostel**](https://github.com/dakra/ghostel) (816 stars, `v0.48.0` 2026-07-29) is a shipped existence proof of this guide's whole architecture in a different host application — covered in its own right below.

**Two entries in this family are worth reading even though you cannot run them.** **VS Code's `ptyHost`** (`src/vs/platform/terminal/node/ptyService.ts`) is the strongest prior art in the census: `PersistentTerminalProcess` with `detachFromProcess(id, forcePersist)` at `:403`, a `shouldPersistTerminal` check at `:416`, an orphan-question protocol, and `serializeTerminalState(ids)` at `:230` — and critically, **replay is not a raw byte dump**: it runs `@xterm/headless` and `@xterm/addon-serialize` to serialize real terminal state, and `terminalRecorder.ts` records **resize events too**, with a 10 MB `MaxRecorderDataSize`. Contrast **Coder's `agent/reconnectingpty`**, whose buffered backend is a **64 KiB ring dumped raw** (`buffered.go:52,222-223`) and self-labelled "(buggy)", with its screen backend gated on `runtime.GOOS == "linux"`. Ten megabytes of state-aware replay with resize events, versus 64 KiB of raw bytes, is the clearest illustration in this whole survey of what "replay scrollback on reattach" can mean at either end. VS Code's is level 1 across window reloads, and its open-source server packaging (openvscode-server) is Linux-only, so neither is a tool you deploy — they are the two reference points for how good or how thin a replay implementation can be.

### ghostel — somebody already shipped this architecture, for a different host application

**Read this one even if you never touch Emacs, because it is the closest thing in the census to an existence proof of the shape this whole guide describes.** [`dakra/ghostel`](https://github.com/dakra/ghostel) is a terminal for Emacs built on libghostty-vt with a Zig native module — 816 stars, `v0.48.0` shipped 2026-07-29 — and its Windows support is not aspirational. Its own `CHANGELOG.md` records at `[0.43.0] 2026-07-11`: **"Native Windows support for x86_64 and ARM64 Emacs through a ConPTY backend"**, and, in the same entry, "Windows releases now bundle the native module and Microsoft's redistributable ConPTY runtime… with the system ConPTY as a fallback." The backend is `src/ConPtyProcess.zig`, and **every release ships `ghostel-conpty-*.dll` plus `ghostel-openconsole-*.exe`** — which is bundling done exactly the way item 3 of the build spec says to do it, by a project that had to make it work.

**Architecturally it is your shape, with the names changed:** the native module owns ConPTY and the host application is a swappable frontend. Emacs is the disposable client; the module is the durable connection-owning layer. That is the same split as Evennia's Portal/Server and the same split you are trying to insert under ORCA — and unlike almost everything else in this guide, somebody has already built it, versioned it, and shipped Windows binaries of it. It is not a middle layer you can spawn from an ADE, so it is not a candidate; it is the proof that the load-bearing part is buildable on native Windows, plus a working reference for the ConPTY-plus-bundled-runtime pattern. It is also the subject of Q21 — whether that ConPTY backend means libghostty-vt works on Windows or means ghostel routed around it, which is one hour of reading `src/ConPtyProcess.zig` and decides whether you have three VT-parser options on Windows or two.

## Interface shapes: the eight ways a middle layer can be driven

Once you have decided that something must own the PTY, the next decision is **how anything talks to it**. Every shape below answers the same three questions differently: **what does a caller need in order to speak it** (a shell? a generated client? a socket and a framing library?), **who owns the lifetime of the connection** (the caller, the callee, or neither), and **what happens to the terminal bytes on the way through** (passed verbatim, re-encoded as text, or never produced at all). Get those three right for your caller — which, for a headless-first middle layer, is a script, a hook or an agent, not a human — and the shape picks itself.

They are not mutually exclusive. The best-shaped candidates offer two or three, and the strongest single design decision in the whole census (WezTerm's versioned codec) is about tolerating change in one of them.

The eight below are seven distinct machine interfaces plus SSH, which is a transport rather than a framing but has real candidates behind it and so is treated as a shape of its own.

The install-and-drive lines in this section carry the same caveat as those in the candidate sections above: they are assembled from each project's own docs and were **not executed on a Windows machine in any pass of this research**. Treat them as the shape of the invocation, not as a transcript.

### CLI verbs

**What it is.** The tool ships an executable with subcommands, and you drive it by spawning processes: `psmux ls`, `wezterm cli list`, `rmux new -d -s probe`.

**What it buys.** Trivially scriptable from anything, with no client library. The same verb string survives being called by a shell, a hook, an agent or a human, and it composes with `--json` — [Pane](https://github.com/dcouple/Pane)'s `runpane` emits `--json` on every verb and ships a machine-readable `contracts/runpane/contract.json` plus a first-party Python client, documented in `docs/RUNPANE_CLI_CONTRACT.md`, and Agent Orchestrator's `ao status --json` / `ao doctor --json` do the same over a loopback HTTP API with `ao completion powershell` for the shell. **This is the only shape where a script, a hook and a human all speak one language**, which is the property that matters when the human leaves the loop: nothing has to be re-learned. tmux, psmux and rmux sit in that pole by construction (rmux ships 90+ tmux-compatible verbs); Zellij deliberately does not, its README committing to "must not sacrifice simplicity for power" with an on-screen hint bar as the primary interface and CLI verbs secondary.

**What it costs.** Process-spawn latency per call, no push and no streaming, and state you must re-fetch rather than be told about.

**Who offers it.** tmux, psmux, rmux (90+ verbs), `wezterm cli` (15 verbs), `ao` (a thin client over HTTP), Pane's `runpane`, qscreen's `qscn`, herdr, Zellij. All of them run on Windows.

```powershell
# Drive the verb surface — one detached session, then prove it is listed
psmux new-session -d -s probe ; psmux ls
rmux  new -d -s probe         ; rmux ls
wezterm-mux-server --daemonize ; wezterm cli list
zellij list-sessions          # NOTE: no verified detached-start invocation exists for Zellij -
                              # see the Zellij entry. `zellij --session X options --help` only
                              # prints help; the interactive path is `zellij attach --create X`.
```

**What it implies for an ADE-agnostic layer.** Verbs are the lowest-friction interface an ADE-independent layer can expose, and they are also the shape whose headless behaviour is least established — see the no-console column below, which is the one thing that would disqualify all of them at once.

### tmux control mode (`-C` / `-CC`)

**What it is.** A line-based machine protocol, documented in `tmux.1` under CONTROL MODE: you send tmux commands on stdin, and it replies with `%begin` / `%end` / `%output` / `%window-add` / `%layout-change` lines on stdout. The outer program owns rendering; tmux owns sessions.

**What it buys.** A real, decade-hardened contract with **at least five implementers, not one** — iTerm2, WezTerm (verified in source at `wezterm-escape-parser/src/tmux_cc/tmux.pest`, `mux/src/tmux.rs` and `tmux_pty.rs:90-91` with a `#[cfg(windows)] fn as_raw_handle`, and a changelog entry recording a **Windows-specific `tmux -CC` bug being fixed**), psmux (`src/main.rs:4194`, `src/control.rs` at 554 lines, `docs/control-mode.md` at 432 lines, three PowerShell tests), Tomiyou/ivyterm and paulrobello/par-term. Critically, `%output` carries **raw pane bytes**, so the "parse once, let the last hop render" property is available: your ADE's own xterm.js can be the only VT parser in the chain.

**What it costs, and this is the characteristic failure.** A line-based text protocol is fragile to interleaving, and **ConPTY corrupts it when nested**: it silently consumes the DCS escape sequences the protocol is detected with, and interleaves its own cursor-positioning sequences into the output. The verbatim source quote, its SSH antecedent, Microsoft's independent corroboration in `microsoft/terminal#19621`, and the disclosure that generalising the hazard beyond SSH is inference rather than the source's claim are all under [Nesting](#nesting-your-middle-layer-runs-inside-the-ades-conpty). The remedy the source gives is SSH-specific and worth quoting because it names the shape of the cure: "the SSH client must disable PTY allocation so that stdin/stdout are raw pipes: `ssh -T user@host tmux -CC`."

Two further costs are documented rather than inferred. `docs/control-mode.md:391` states "ConPTY may normalize line endings and process certain cursor movement sequences internally. `%output` data may look slightly different from what a Unix tmux session would produce" — a straight Windows/Linux behavioural divergence in the interface you would be standardising on. And psmux's `src/server/mod.rs:1225` runs `String::from_utf8_lossy(&bytes)` on each ring drain, so a multi-byte character split across two drains becomes U+FFFD **permanently** — the same string-typed-wire failure class described under Nesting.

**The order to test in.** Before asking whether corruption happens, ask whether the cure is reachable: ORCA spawns through node-pty, which is always a ConPTY, and the documented `-CC` remedy is "give the child raw pipes." **If `agentCmdOverrides` cannot produce a raw-pipe child, the corruption question is moot** and this interface is unavailable in this topology regardless. That is two hours of reading ORCA's spawn path from `src/shared/tui-agent-launch-command.ts:30` through to the node-pty call (Q1a), and it can make the afternoon-long corruption experiment (Q1) unnecessary.

```powershell
# A genuine raw-pipe parent — the topology -CC actually wants.
$psi = [Diagnostics.ProcessStartInfo]::new('psmux', '-CC new-session -s probe')
$psi.RedirectStandardInput  = $true
$psi.RedirectStandardOutput = $true
$psi.UseShellExecute        = $false
$p = [Diagnostics.Process]::Start($psi)
$p.StandardInput.WriteLine('list-panes')   # commands in

# A single ReadLine() returns ONE line and cannot show you a %begin/%end block.
# Drain with a deadline instead, and keep the transcript to diff later.
$deadline = (Get-Date).AddSeconds(5)
$lines = while ((Get-Date) -lt $deadline -and -not $p.StandardOutput.EndOfStream) {
    $p.StandardOutput.ReadLine()
}
$lines | Tee-Object -FilePath "$env:TEMP\cc-rawpipe.txt"
# You should see a %begin line, one or more %output lines, and a matching %end.
# Now run the SAME command as an agentCmdOverrides target inside the ADE, capture to a
# second file, and diff them — the difference is the corruption Q1 is asking about.
```

### Binary wire protocols

**What it is.** A framed binary channel with an explicit message catalogue, spoken over a pipe or a socket, with no text layer to corrupt.

**What it buys.** Exact byte fidelity, low overhead, and — in the one case that was designed for it — **tolerance of version skew between client and server**. WezTerm's codec is the standout: `codec/src/lib.rs` encodes "length, ident and serial number… using a variable length integer encoding… client and server can more gracefully manage unknown enum variants." That is precisely the ADE-churn insulation this whole project exists to buy, written down and shipped by somebody else.

**What it costs.** You write and maintain the client. There is no ecosystem, no generated bindings, no curl equivalent, and nobody else's tooling speaks it.

**Who offers it.** The WezTerm mux codec (MIT, inside a 28.1k-star project, Windows-capable, L2). `ao pty-host`'s `conpty/proto.go` — `[1-byte type][BE32 len][payload]`, eight messages from `MsgTerminalData 0x01` to `MsgKillReq 0x08`, Apache-2.0, which makes vendoring legally clean. qscreen's `ScreenFrame` / `ScreenRun`, structured runs with `FRAME_FLAG_*`, `FrameColor` and `FrameMouseMode` — the same "parse once, render at the last hop" idea as tmux control mode, arrived at independently. And asciinema's ALiS: four negotiated WebSocket sub-protocols (`v1.alis` binary with the 5-byte magic `ALiS\x01` = `[0x41,0x4C,0x69,0x53,0x01]` plus LEB128 framing, `v2.asciicast`, `v3.asciicast`, `raw`), where the relay "maintains comprehensive state for each active stream by running the whole stream through asciinema's own virtual terminal emulator" — late-joiner screen sync for free from an existing open-source relay. The asciinema *CLI* is out on Windows (v3.2.1 release assets are darwin and linux only, even in the from-scratch Rust rewrite); the ecosystem is not. How much code a native-Windows ALiS producer would take is genuinely unknown — no estimate here survives scrutiny, so do not plan against one.

**A twenty-year-old warning that lands directly on an Electron ADE.** The BBS-era DOOR32.SYS convention handed a child process an **already-open Winsock socket handle number** rather than emulating a serial device — the "pass a handle, don't emulate" precedent. [ENiGMA½ issue #175](https://github.com/NuSkooler/enigma-bbs/issues/175) — **closed since 2018-12-09**, so this is history rather than an open defect — records what happened when a Node host tried it: "socket descriptors cannot be shared" in Node.js, and the project's own documented workaround is `bivrost!`, **a Rust sidecar between the Node host and the handle**. ORCA is Electron and Node. The BBS world hit this exact wall eight years ago and solved it with the Rust-daemon shape that psmux, oly and qscreen already occupy.

### HTTP and WebSocket

**What it is.** A local HTTP server for control plus a WebSocket (or SSE) for the byte stream.

**What it buys.** Every language has a client. Auth, TLS and proxying are solved problems with existing answers. Push comes free with WS or SSE, and OpenAPI gives you a generated client — `opencode serve` publishes OpenAPI 3.1. The console-independence is inherent: **a network client needs no console at all**, which is the one column where the PTY-owning CLI candidates are all untested.

**What it costs.** Port management, bind address and authentication become your problem, and **a stray `0.0.0.0` is a real leak**. Loopback binding is not an authentication boundary either — `ao pty-host` carries its own caveat in `host_main.go`: "loopback bind only; any local process on this host can connect to the assigned port. A per-session random token handshake is the upgrade path."

**Who offers it.** OpenCode's `/pty` is the best-shaped of them — `GET/POST /pty`, `GET|PUT|DELETE /pty/:id`, `POST /pty/:id/connect-token`, `GET /pty/:id/connect` (WebSocket), with ticket auth and a replay cursor, shipped in the Windows binary. Also oly (named-pipe IPC plus HTTP/WS plus push notifications); [kandev](https://github.com/kdlbs/kandev), whose `ws://localhost:38429/ws` endpoint is documented in its own `docs/public/websocket-api.md`; Jupyter's terminado (`GET/POST /api/terminals` plus a WS carrying `["stdout",text]` / `["stdin",text]` / `["set_size",r,c]`); Agent Orchestrator's `/api/v1/*`; and the [x3270](https://github.com/pmattes/x3270) family's `-httpd` REST control plane, worth a glance because it is a **headless scriptable emulator with a three-transport control plane** that already works on Windows. The evidence for that last one is a set of counts from a GitHub code search over the x3270 source tree — 179 hits for `httpd`, 69 for `scriptport`, and **zero for `CreateNamedPipe`** — so on Windows its control plane is loopback TCP plus HTTP REST. Those are snapshot counts from one search with no query string recorded; the zero is the load-bearing part and it is the one you can re-run in a minute.

**The characteristic failure of this shape is the undocumented contract.** OpenCode's `/pty` API appears nowhere on opencode.ai — the published server doc has zero `/pty` occurrences — so the whole surface can change without notice, in a project shipping at 192k-star velocity. And its wire is **UTF-8 text, not raw bytes**, with the surrogate-splitting and silent-drop consequences set out in the OpenCode entry above: describing frames as "raw UTF-8 terminal chunks" does not make the payload type a byte slice.

**A second characteristic failure: a rich HTTP catalogue that does not include the verb you need.** Warp's `crates/local_control` — in [`warpdotdev/warp`](https://github.com/warpdotdev/warp), the AGPL-3.0 client, branch `master` — is the closest open-source analogue to tmux control mode found anywhere: a versioned action catalog (`crates/local_control/src/catalog.rs:4`, `PROTOCOL_VERSION: u32 = 1`) over authenticated loopback HTTP at `/v1/control`, with **84 entries carrying `status: Implemented`** covering `pane.list/split/resize/focus/navigate/close`, `session.list/activate`, `input.insert/replace` and more. Reading the whole catalogue confirms the negative: **no output-read, no send-keys-to-PTY, no attach.** It is a window-management control plane, not a PTY-attach protocol. Its auth also leans on a kernel-reported peer-UID check, which is POSIX-only. (Note which Warp this is: the *client* is open source and this crate was read at source. Warp's commercial product and its Oz cloud API are closed and nothing about those was verified anywhere in this guide.)

```powershell
# Control plane: ordinary REST, so PowerShell alone is enough.
opencode serve --port 4096                       # then, from another shell:
$pty   = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:4096/pty'
$id    = $pty.id                                 # field name unverified - inspect $pty
$ticket = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:4096/pty/$id/connect-token"
$ticket
```

**The attach is the part that actually tests anything, and PowerShell has no built-in WebSocket client**, so it needs `System.Net.WebSockets.ClientWebSocket` directly. This is the step that exercises the replay cursor — the property the whole entry is about — and it is what Q12 means by "a WS connect from PowerShell":

```powershell
Add-Type -AssemblyName System.Net.WebSockets.Client -ErrorAction SilentlyContinue
$ws  = [System.Net.WebSockets.ClientWebSocket]::new()
$uri = [Uri]"ws://127.0.0.1:4096/pty/$id/connect?token=$($ticket.token)"   # param name unverified
$ws.ConnectAsync($uri, [Threading.CancellationToken]::None).Wait()
"state: $($ws.State)"                            # you should see: Open

$buf = [ArraySegment[byte]]::new([byte[]]::new(64KB))
$r   = $ws.ReceiveAsync($buf, [Threading.CancellationToken]::None).Result
"first frame: $($r.Count) bytes, type $($r.MessageType)"
# The control frame is a 0x00 byte followed by UTF-8 JSON carrying the absolute output
# cursor after replay. If $buf.Array[0] is 0, you are looking at it - decode the rest as
# JSON and that number is what a later client resumes from.
$ws.Dispose()
```

**Both blocks are written against an undocumented API and neither has been run.** The endpoint paths are verified in source; the request and response *bodies*, the field names and the token parameter are not documented anywhere and are guesses from the route handlers. Read `packages/opencode/src/server/routes/instance/httpapi/groups/pty.ts` for the current schema before trusting either block — and if you would rather not fight PowerShell's WebSocket API, this step is three lines in Node or Python and there is no reason to be precious about it.

### MCP

**What it is.** The agent-facing shape: the middle layer registers as an MCP server and the coding agent calls its tools directly.

**What it buys.** The agent can drive the middle layer *itself*, with no glue code, and the tools are discoverable. quil exposes 18 MCP tools — the richest agent-facing surface in the census.

**What it costs, and it is a lifetime problem, not a protocol one.** **A stdio MCP server cannot own persistent sessions, because the client spawns it** — the sessions die with the client that was supposed to be swappable. Only a server the middle layer runs independently works. [kandev](https://github.com/kdlbs/kandev) is the one candidate that names this distinction in its own docs (`docs/public/automation-and-mcp.md`), offering four MCP modes including an **External MCP** mode explicitly "for a client outside a task." [dagger/container-use](https://github.com/dagger/container-use) is the counterexample that proves the rule: it registers as `container-use stdio`, a stdio MCP server, which cannot own persistent sessions at all.

**Who offers it.** quil (18 tools), kandev (External MCP), the paseo daemon, ripple, and vibe-kanban (dead — sunset 2026-04-24).

**What it implies for an ADE-agnostic layer.** MCP is a good *additional* surface and a bad *only* surface. The test to apply to any MCP-shaped candidate is one question: does the client spawn this server, or does it connect to one that was already running? If the former, the persistence you are shopping for is not there.

### JSON-RPC over stdio or a pipe

**What it is.** Line-framed JSON-RPC between a host and a spawned process. ACP (Agent Client Protocol) is the ecosystem's convergence point; Codex's `app-server` is OpenAI's variant, self-described as "JSON-RPC lite" with Thread / Turn / Item primitives.

**What it buys.** The agent-CLI ecosystem is converging here — ACP has 3,840 stars and implementations across Zed, JetBrains, Copilot CLI, Gemini CLI, Claude Code, Neovim and Toad — and the spec is transport-agnostic by its own text.

**What it costs.** Subprocess-bound lifetime, unless you add a network transport. Codex has one: `--listen ws://IP:PORT` is a standing listener the client does **not** own, and its `app-server-transport/src/transport/mod.rs:27-32` registers `remote_control`, `stdio`, `unix_socket` and `websocket` **unconditionally**. But `app-server/README.md` labels websocket "**experimental / unsupported**. Do not rely on it for production workloads," and `codex-rs/app-server-daemon/README.md` states "The current daemon implementation is **Unix-only**… does not yet support Windows lifecycle management." The transport is there on Windows; the daemon lifecycle is not. Release `rust-v0.147.0-alpha.4` does ship `codex-app-server-x86_64-pc-windows-msvc.exe`, and the server ships `/readyz`, `/healthz`, backpressure returning `-32001`, and `generate-ts` / `generate-json-schema` for a version-pinned schema.

**What it implies for an ADE-agnostic layer.** ACP's own draft transports chapter states "The protocol is transport-agnostic… can be implemented over any communication channel that supports bidirectional message exchange," and names Streamable HTTP as transport 2, formally sanctioning custom transports. **So ACP over a Windows named pipe is spec-conformant.** Whether it builds and passes on Windows is a different question — see the negative-space section below.

### SSH

**What it is.** The session is reached by SSH, and the middle layer is the SSH server.

**What it buys.** The only interface in the census with a **real authentication model rather than a local-trust assumption**. upterm's host takes `--authorized-keys`, `--github-user`, `--gitlab-user` — public-key auth, verified in its flag set, and nothing else in the census matches it. The client side is universal and already installed on Windows 11.

**What it costs.** Everything else, in the two candidates that offer it. upterm is **L1 only**: the session lives exactly as long as the `upterm host` process, with no detach and no reattach, which is the single requirement that defines a middle layer — so it fails on the one axis that matters most, whatever else it does well. Its ConPTY engineering is genuinely good and its nested-ConPTY lesson is worth stealing whatever you pick; both are in the upterm entry above. Its relay, `uptermd`, is Linux-only. tmate is a tmux fork and inherits tmux's POSIX dependency outright.

**And the in-box option does not fill the gap.** Windows OpenSSH Server has **no tmux equivalent** — that is stated by a Microsoft member (SteveL-MSFT) in [`Win32-OpenSSH#2291`](https://github.com/PowerShell/Win32-OpenSSH/issues/2291), still open: "On Linux, you can use something like tmux to keep a long lived session, but the equivalent doesn't exist on Windows." The mechanism usually given for *why* — that sshd puts children in a Job Object and disconnect tears it down, so **there is no SIGHUP to trap** — rests on **one maintainer sentence with zero code-search corroboration**: searches for `CreateJobObject` and `KILL_ON_JOB_CLOSE` in openssh-portable return no hits. The absence of a tmux equivalent is established; the Job-Object explanation for it is not, and should not be repeated as though it were.

```powershell
# No angle brackets: `<` is a reserved redirection operator in PowerShell.
$githubUser = 'your-github-username'
upterm host --github-user $githubUser -- pwsh    # public-key auth; session dies with this process
```

### The no-PTY NDJSON channel

**What it is.** Not a way to talk to a PTY owner — **a way to have no PTY at all.** `claude -p --input-format stream-json --output-format stream-json --verbose` is a full-duplex NDJSON channel over ordinary pipes, with `--include-hook-events`, `--forward-subagent-text` (carrying `parent_tool_use_id`), `--include-partial-messages` and `--replay-user-messages` as companions.

**What it buys.** **Console-independence by construction** — ordinary pipes, no console needed anywhere, which makes it the only option in this document that passes the headless test without anyone having to run an experiment. Three channels stack on top of it, all set out with their sources in [When you need a session daemon](#when-you-need-a-session-daemon-and-when-you-do-not) above: Claude Code **hooks** as the write path, five types rather than the three that get repeated in blog posts, where `PreToolUse` returns a `permissionDecision` plus an `updatedInput` that replaces the tool's arguments, and where the `http` type means **your middle layer can BE the endpoint** — a long-lived process you own, which sidesteps the stdio-MCP lifetime problem entirely; **OpenTelemetry** as the read path, including `claude_code.tool.blocked_on_user`, the "is the agent stuck waiting on a human" signal, with no PTY anywhere; and the **JSONL transcript tree**, from which subagent fan-out topology is readable on the filesystem alone.

**What it costs.** It buys everything except the two things PTY ownership uniquely provides: **the byte stream of a program that insists on a terminal, and a human typing into a live session.** Five narrower limits are load-bearing, and all five are quoted from the documentation in the opening section: `http` hooks are unavailable on `SessionStart` and `Setup`, the two bootstrap events a middle layer most wants to own; `mcp_tool` hooks on those same two events "should expect the 'not connected' error on first run", which leaves `command` as the only dependable bootstrap hook type; as of v2.1.199 a tool marked `_meta["anthropic/requiresUserInteraction"]` can refuse to have its approval prompt skipped by a hook; Claude Code strips `OTEL_*` exporter variables from every subprocess it spawns, so telemetry config does not reach grandchildren; and the JSONL tree is undocumented, version-fragile internals that `cleanupPeriodDays` garbage-collects.

**And one cost that is architectural rather than a limit in the documentation: this route is per-vendor plumbing.** Every channel named above — `claude -p` stream-json, hooks, the `claude_code.*` telemetry, the JSONL tree — is Claude Code's. Codex's equivalents (`exec --json`, rollout JSONL, `resume --last`) are a *second* implementation, not the same one. **You do not install a no-PTY middle layer; you implement one per agent vendor**, and each vendor's config surface changes under you on its own schedule. That is the direct trade against the PTY-owning route, which is agent-agnostic by construction because it does not care what runs inside it. If "any ADE, any agent CLI" is a requirement rather than a preference, this is where the no-PTY route charges you for its console-independence.

**And the cross-platform claim is inference, not measurement.** The flags are documented without platform qualification and the transport is ordinary pipes, but **nobody has run this on both Windows and Linux and compared output**. That is the load-bearing cross-platform claim of the whole no-PTY architecture and it rests on an inference.

**One more channel, narrow but real.** `terminalSequence` (v2.1.141+) lets a hook push escape sequences out through Claude Code's own terminal write path: "Hooks run without a controlling terminal, so writing escape sequences directly to /dev/tty fails… This is race-free, works inside tmux and GNU screen, and **works on Windows where there is no /dev/tty**." The allowlist is OSC 0/1/2 (titles), OSC 9 (including **9;4 taskbar progress**), OSC 99, OSC 777 and a bare BEL, restricted "to sequences that can't move the cursor or alter colors" — **so OSC 133 is not available** — but it is enough to push out-of-band structured signals into the PTY byte stream that a nested middle layer parses natively.

**Cross-vendor convergence is itself evidence.** Codex ships the same shape independently: `exec --json` plus rollout JSONL at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` with `resume --last`. Two vendors landing on the identical design says this is a real architectural pattern, not one company's idiosyncrasy.

```powershell
# The channel itself: NDJSON in, NDJSON out, ordinary pipes, no console anywhere.
#
# Set the outbound encoding FIRST. Piping a string to a native executable goes through
# [Console]::OutputEncoding, which is not UTF-8 by default in Windows PowerShell 5.1 - so
# the one document whose central warning is "string-typed wires destroy Unicode" can lose
# bytes in its own example. Use pwsh, and set it anyway:
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

'{"type":"user","message":{"role":"user","content":"list the files"}}' |
  claude -p --input-format stream-json --output-format stream-json --verbose --include-hook-events

# The read-only observation channel — note the master switch is not an OTEL_* var:
$env:CLAUDE_CODE_ENABLE_TELEMETRY = '1'
# traces additionally need CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1;
# the claude_code.hook span needs ENABLE_BETA_TRACING_DETAILED=1 + BETA_TRACING_ENDPOINT + org allowlisting.
# Content is redacted by default: opt in per-field via OTEL_LOG_USER_PROMPTS, OTEL_LOG_TOOL_DETAILS,
# OTEL_LOG_TOOL_CONTENT, OTEL_LOG_ASSISTANT_RESPONSES, OTEL_LOG_RAW_API_BODIES (=file:<dir> writes
# untruncated bodies to disk with a body_ref path).
```

**Honest scoping.** This is print/headless mode. It **does not attach to an existing interactive TUI**. It is a way to build a middle layer that spawns the agent with no PTY at all — a different architecture, not a different transport.

---

## The verb set an ADE-agnostic middle layer has to expose

Whatever shape you pick, the same primitives keep showing up. The list below is **derived from the union of every candidate's verb set** — `runtimeselect.Runtime` in Agent Orchestrator, `wezterm cli`, the tmux/psmux/rmux verbs, OpenCode's `/pty`, and quil's MCP tools. It is a synthesis and a judgement, not any one project's API.

| Verb | Why it is non-negotiable |
|---|---|
| `spawn(cmd, cwd, env, cols, rows) → session_id` | The ADE hook point. ORCA's `agentCmdOverrides` is exactly this |
| `list() → [{id, alive, pid, exit_code, cwd, title}]` | Discovery without state in the ADE |
| `attach(id, {cursor}) → {replay, cursor, stream}` | The one primitive nothing else substitutes for. **Must carry a resumable cursor.** OpenCode's `protocol.ts` is the model **for the cursor semantics only** — copy its absolute-output-cursor control frame, not its wire type, because its payloads are JS strings that split surrogate pairs at 64 KiB and drop invalid UTF-8 input. Carry `bytes`, not `string` |
| `detach(id)` | Distinct from kill; the thing dtach and abduco exist for |
| `send(id, bytes)` and `send_keys(id, keys)` | Raw bytes for fidelity, named keys for scripts |
| `get_output(id, lines)` / `snapshot(id) → {text, cursor_x, cursor_y}` | Headless read without attaching. quil's `MsgScreenshotPaneResp` is the shape |
| `resize(id, cols, rows)` | Must be explicit on Windows — there is no SIGWINCH. Multi-client needs an arbitration rule, and Agent Orchestrator's `applyLargestLocked` is the only one found |
| `status(id) → {alive, pid, exit_code, blocked_on_user?}` | Headless liveness. The `blocked_on_user` bit is what OTel gives you free |
| `kill(id, signal)` | With a process-tree story: Job Objects on Windows (upterm, rmux, kandev's `cmd/winjob/`), not a bare `TerminateProcess` |
| `wait(id, {idle\|text\|exit}, timeout)` | The primitive that makes it scriptable. boo, rmux and andyk/ht all shipped this independently |

**Two properties beyond the verb set, both learned the hard way, and both stated here as build requirements rather than as findings — the evidence behind them is in [Unauthenticated local IPC](#unauthenticated-local-ipc-the-shared-security-problem) below.**

**Namespacing must be identity-scoped, not merely selectable.** rmux's `\\.\pipe\{prefix}-{sid}-il-{integrity}-{label}` is the only correct implementation found, because the name is *computed from the token* rather than picked from a string, so it cannot be entered by a process that merely guesses. A configurable name is not access control: oly has the knob (`OLY_SOCKET_NAME`, `src/config.rs:123-126`) and still has no ACL on the pipe. **Namespacing prevents accidents; ACLs prevent attacks. You need both, and only rmux has both.**

**A local transport is not an auth boundary.** Rank the transports before you pick one: **a properly ACL'd named pipe with `FILE_FLAG_FIRST_PIPE_INSTANCE` is strictly stronger than an AF_UNIX socket on Windows** — where `chmod` is a no-op, `SO_PEERCRED` does not exist, and the only protection is the ACL on the parent directory — **which is in turn stronger than a loopback TCP port**, reachable by any local process including other users and low-integrity ones. And note the ceiling on all of them: authentication in this category is per-*user*, not per-*process*, so ORCA, every agent CLI, every MCP server and every npm postinstall script run as the same Windows user and can all reach the same endpoint. That is the same trust model as tmux's 0700 socket — a property of the category, not a scandal about any one project.

## The convergence: three ecosystems, one shape

Three unrelated projects, solving unrelated problems, independently arrived at the same architecture.

- OpenCode, in [its own server documentation](https://opencode.ai/docs/server): "When you run opencode it starts a TUI and a server. Where the TUI is the client that talks to the server… This architecture lets opencode support multiple clients and allows you to interact with opencode programmatically."
- Evennia, a MUD engine, splits **Portal** from **Server** over a Twisted AMP socket: "you can fully reload the Server and have players still connected to the game. One [sic — upstream typo for 'Once'] the server comes back up, it will re-connect to the Portal and re-sync all players as if nothing happened." Portal owns every protocol and every persistent connection; Server owns all logic and can crash or reload freely. That passage is on Evennia's *Portal-And-Server* documentation page, not on the docs landing page — search the docs for "Portal And Server"; the exact page URL was not recorded here and the landing page does not contain the quote.
- nREPL, from the Clojure world, "solves the 'narrow waist' problem… shares a lot with the Language Server Protocol, though it **predates LSP by several years**… Writing an nREPL server… can be done in a couple hundred lines." Self-describing, session-oriented, no PTY. That passage is in the [nREPL specification](https://nrepl.org/nrepl/index.html) rather than on the site root, which redirects.

A coding agent, a text-game engine and a Lisp REPL. **Read this convergence as a stronger signal than any individual tool finding in this guide** — three unrelated ecosystems, none of which had heard of your problem, all splitting the disposable frontend from the durable connection-owning process. Evennia already has the name for the thing you are building: *Portal*. SLIME/swank states the same idea in one sentence: the frontend is disposable, the real long-running state lives behind a socket. That is the ADE-swap requirement, named and shipped, three times over.

---

## What does not exist

This is the part that saves you a week. Each item below was searched for and not found, and the reason each absence matters is stated with it.

**No terminal-control standard has emerged.** MCP has **zero terminal or PTY SEPs among the 41 Final ones** at [modelcontextprotocol.io/seps](https://modelcontextprotocol.io/seps) — that count is verified. Alongside it sits an unquantified observation from GitHub search rather than a measured figure: there are *many* independently-named `mcp-terminal-server` repositories with no shared schema between them, and no count was recorded, so re-run the search rather than quoting a number. One correction is worth carrying because the opposite is widely believed: [OpenAI's Codex-harness post](https://openai.com/index/unlocking-the-codex-harness) is *not* evidence that MCP was tried for terminals and abandoned — it never mentions terminals or PTYs. What it says is that "maintaining MCP semantics in a way that made sense for VS Code proved difficult," i.e. MCP was abandoned as a **VS Code integration** protocol. That is weaker evidence, and only suggestive of the terminal case.

**tmux control mode is a contract, not a specification.** It standardises the framing — commands in, `%begin` / `%end` / `%output` / `%window-add` / `%layout-change` out — and it has at least five implementers, so it is a genuinely reusable contract rather than one project's internal API. An earlier belief that no second production consumer existed was wrong: WezTerm, ivyterm and par-term all implement it, and WezTerm exercises it on Windows. **Where it stops: there is still no specification independent of tmux's implementation.** The definition is whatever `tmux.1` and the tmux source do, which means version skew is a diff against a moving implementation rather than against a document — the exact problem WezTerm's varint codec was built to solve for its own protocol.

**ACP standardises the conversation, not the process.** Its session verbs are `session/load` (which replays history), `session/resume`, `session/list`, `session/fork` and `session/close`. Read those carefully: that is **conversation-state continuity, not live-process attach**. There is no primitive in ACP today that attaches to a running PTY. Two further limits: **every job in `.github/workflows/ci.yml` is `ubuntu-latest`**, so there is no Windows CI at all, and its terminal work is in flight rather than shipped (`schema/src/v2/terminal.rs`, `docs/rfds/v2/terminal-output.mdx`). The spec does formally sanction custom transports, so ACP over a Windows named pipe is conformant — but conformant and tested are different words, and a two-day prototype against the reference implementation is what would settle whether it builds and passes on Windows.

**No Windows analogue of reptyr, after 10+ years.** reptyr is the POSIX solution to the structurally identical problem — grab the I/O of a process you did not spawn — via `ptrace`. No attempted port was located, which is an absence-of-evidence finding from repository and issue searches rather than an exhaustive proof. Read it as evidence that the platform makes this hard, not that the niche is unfilled: the mature Windows implementations all pick one half of late-attach, NVDA reading without writing and winpty/wexpect reading and writing but owning the console from birth, and **the halves never combine**.

**No native network-attach for Claude Code, and it has been declined twice** — the two `not_planned` closures are in the opening section. Betting on native network-attachable Claude Code sessions is a weak hypothesis, which is itself an argument for an external layer.

**No compatibility matrix** — from Microsoft or anyone — for running a newer bundled `conpty.dll` / `OpenConsole.exe` against an older or locked-down Windows Server Core or LTSC host. This matters because bundling the ConPTY NuGet package is the recommended path, and the recommendation is a **refusal to backport** rather than an endorsement; the quote is under [The four things a middle layer must get right on Windows](#the-four-things-a-middle-layer-must-get-right-on-windows).

**No primary Microsoft source pins the build thresholds** for `WIN32_INPUT_MODE` (its spec was authored 2020-05-07) or for VT passthrough — `build >= 22621` is corroborated only by two independent Rust implementations, psmux and rmux, converging on the same magic number.

**The xterm.js attach-addon convention went unexamined**, and it is the single largest known gap in this guide's protocol coverage. It is easy to describe it as the most widely deployed de-facto terminal wire convention in existence — ttyd, code-server and VS Code all use it — but that superlative is unsourced and untested here, and it survives only as a lead.

**No open-source SCADA or industrial session manager** with a persistent-session-plus-attach design was located (Q20). That area is genuinely under-researched, not confirmed absent — recorded so the gap is not mistaken for a finding.

---

## The column that can disqualify every PTY candidate at once

Before the tables, read this, because one column in them is different from all the others.

**"Verbs with no console attached" is the headless-first requirement stated as a testable property, and the honest answer is *untested* for every single PTY-owning candidate.** `zellij action`, `tmux send-keys`, `wezterm cli` and the rest are normally invoked *from inside a terminal*. Whether they still function when a Windows Service, a Scheduled Task or a Claude Code hook invokes them with no console attached and no TTY on stdin or stdout is a completely different question, and **nobody has run it.**

It matters more than its size suggests, for two reasons. It is **disqualifying if it fails** — a middle layer you can only drive from inside a terminal is not headless-first, it is just a multiplexer. And it is **cheap**: roughly two hours (Q23) to settle for the entire field at once. Those two facts together are why it is the **first** thing to run, ahead of the week-long Q9 that has more leverage — see [The running order, with wall-clock](#the-running-order-with-wall-clock). If those verbs work, the whole "headless verbs" column becomes trustworthy. If they fail, those candidates are terminal tools rather than middle layers, and the no-PTY architecture wins by default — because **it is the only row that passes this column by construction**, over ordinary pipes, with no console needed anywhere.

The test is step 3 of [The verification ritual](#the-verification-ritual), and two things about reading its result are worth stating here. **A task result of `0x0` proves nothing** — the task can report success while the verb wrote an error to a stream nobody captured, or exited early because it could not open a console. What proves it is the output file: it must exist, and it must contain the session list you created from an interactive shell beforehand. And **same-principal matters**: run the probe as the same user that owns the daemon, or you are testing namespacing rather than console-independence.

---

## Comparison table: candidates that own a PTY

**How to read this.** Star counts and last-activity dates churn weekly; every number is a snapshot taken 2026-08-02. "Last activity" is the repository's `pushed_at` unless the cell says otherwise. "Survives client death" uses the persistence levels from [Persistence scope](#persistence-scope-what-exactly-survives-what): **L0** dies with the connection, **L1** survives client disconnect but dies with the host process, **L1+** is L1 plus cursor-resumable replay, **L2** survives the ADE that spawned it, **L3** survives a reboot. Only one L3 claim exists anywhere in the census, and it is macOS-only. The table scrolls horizontally; the two columns that decide most cases are **Survives client death** and **Verbs, no console**.

| Candidate | Language | Licence | Stars | Last activity | Transport | Native Windows | Survives client death | Interface shapes offered | Nesting behaviour | Headless verbs | Verbs, no console | Installable standalone |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **psmux** | Rust (a PowerShell installer/test suite inflates the language stats; the product is the Rust binary) | MIT | 3,140 | 2026-08-02 | Loopback TCP, app-layer `AUTH <key>` handshake | **Yes** | **L2** | CLI verbs + tmux `-C`/`-CC` control mode | Own guard plus `PSMUX_ALLOW_NESTING=1` — **but the error text names `PSMUX_SESSION`, the wrong variable**, so a scripted wrapper that follows the message will not clear the guard. Pipe mode negotiates size in band via `CSI 18 t` | Full tmux verb set + `-CC` | **Untested** | Yes — **Windows only** (CI builds only `*-pc-windows-msvc`; the ubuntu/macos job runs two shell scripts, not a build) |
| **Zellij** | Rust | MIT | 34,647 | 2026-08-01 | Named pipes (`interprocess`) | **Yes** (`CreatePseudoConsole`/`ResizePseudoConsole`/HPCON in `zellij-server/src/os_input_output_windows.rs`) | **L2** — spawns with `CREATE_NO_WINDOW \| CREATE_NEW_PROCESS_GROUP`, but note neither flag *implements* parent-death survival; on Windows a child does not die with its parent by default | CLI verbs + protobuf-schema'd WASM plugins. **No verified detached-start invocation** — `zellij --session X options --help` only prints help | **The only candidate with a policy knob**: `nested_session_handling` = ask/fullscreen/descend/never | CLI + plugins | **Untested** | Yes — msvc zip + MSI, plus Linux and macOS |
| **rmux** | Rust, 12 crates, 21 MB | Dual-licensed; **the pair is not stated in repo metadata** (GitHub reports NOASSERTION) — read `LICENSE-*` at the tag you would vendor | 2,533 | 2026-07-26 | Named pipes, **namespaced by SID + integrity level**, `FILE_FLAG_FIRST_PIPE_INSTANCE`, `ImpersonateNamedPipeClient` | **Yes** | **L2** | 90+ tmux-compatible verbs + typed Rust/Python/TS SDKs + Ratatui widget + E2E-encrypted web share | **Untested** | 90+ verbs + typed SDKs | **Untested** | Yes — winget, scoop, choco |
| **herdr** | Rust | Apache-2.0 | 23,466 | 2026-08-01 | Named pipes (`interprocess`) | **Beta only** — preview channel | **L2 (beta)** — "Local persistent sessions \| beta" is listed under *Supported* | CLI + HTTP API (`src/api/server.rs`) + third-party TS/Python SDKs | "Nested launch override \| beta", listed *Supported*. Separately, "Prefix input-source switching \| unsupported" is the only primary-source statement about prefixes on Windows found anywhere | CLI + HTTP | **Untested** | **Preview channel only on Windows** — the tag `preview-2026-07-29-44b3adb12552` (dated preview plus commit suffix; the bare `preview-2026-07-29` does not resolve) ships `herdr-windows-x86_64.zip`; stable v0.7.5 has **no** Windows asset |
| **oly** (slaveOftime/open-relay) | Rust | MIT | 89 | `main` HEAD 2026-07-01; `pushed_at` 2026-07-30 (four side branches) | Named pipes — **no ACL, no `FILE_FLAG_FIRST_PIPE_INSTANCE`** — plus HTTP/WS | **Yes** | **L2** | Named-pipe IPC + HTTP/WS + push notifications | **No nesting evidence.** What exists is a windows-latest PTY test matrix over **shells** (`cmd.exe`, `bash --noprofile --norc`, `pwsh`), not agents | HTTP/WS + IPC | **Untested** | Yes |
| **qscreen** | Rust | MIT | 6 | 2026-07-21 | Named pipes, `.first_pipe_instance(true)`, per-user namespacing | **Yes** | **L2** | `qscn` CLI + `ScreenFrame`/`ScreenRun` structured protocol + `AttachMode::Bytes` raw attach | **Untested** | `qscn` verbs | **Untested** | Yes |
| **quil** | Go | MIT | 11 | 2026-08-01 | **Naked AF_UNIX on all platforms** — `os.Chmod(path, 0600)` is a **no-op on Windows**, no `SO_PEERCRED`; protection is the parent directory ACL only | ConPTY yes; **CI is ubuntu-latest only**, 25+ Windows source files, zero Windows CI, zero external issues ever | **L2** | **MCP (18 tools)** + `quild` CLI + TUI | Mouse-mode forwarding for nested alt-screen apps (`internal/daemon/mousemode.go`) | MCP, 18 tools — the richest agent-facing surface | **Untested** | Yes |
| **`wezterm-mux-server`** | Rust | MIT | 28,101 (WezTerm) | 2026-07-31 | AF_UNIX via the `uds_windows` shim | **Yes** | **L2** (`--daemonize`, handled explicitly on Windows) | 15 CLI verbs (`list`, `spawn`, `split-pane`, `send-text`, `get-text`, `kill-pane`, `proxy`…) + **versioned varint binary codec** + a tmux `-CC` client | **Untested nested**; attach/detach is first-class | 15 verbs, headless by design | **Untested** | Ships in the Windows zip and Inno installer — but **the newest tagged release is 2024-02-03**; the rolling `nightly` tag is the only current Windows path, so "pin a version" and "run on Windows" are in direct tension |
| **OpenCode `/pty`** | TS/Bun | MIT | 192,203 | 2026-08-02 | HTTP + WebSocket | **Yes** (`useConptyDll: true` on win32) | **L1+** — cursor-resumable replay, but it dies with `opencode serve`. **Not L2** | REST + WS + replay cursor + ticket auth | N/A — network client | REST + WS | **N/A — the transport *is* the console-independence** | Yes (`opencode-windows-x64.zip`), but **the `/pty` API is documented nowhere on opencode.ai** and can change without notice |
| **`ao pty-host`** | Go | Apache-2.0 | 8,742 | 2026-08-02 | Loopback TCP, 8-message binary protocol `[type][BE32 len][payload]` | **Yes** | **L2, explicitly** — `CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS` "so the host survives daemon exit"; replays scrollback to new clients; stays alive on PTY exit, mirroring tmux. Resize arbitration: `applyLargestLocked` sizes the shared PTY to the largest attached client, the only such rule found | Binary wire protocol: `GetOutput(lines)`, `Status`, `Kill`, `SendMessage` | **Untested nested** — it is a network-attached design, so the prefix and alt-screen questions do not arise, but nothing has been run inside a second ConPTY | Those four verbs | **N/A** — network client | **No.** Vendor the package or run the AO binary; Apache-2.0 makes that legally clean. It is a `Hidden: true` cobra subcommand — an internal contract |
| **upterm** | Go | Apache-2.0 | 1,270 | 2026-07-25 | SSH, public-key auth (`--authorized-keys`, `--github-user`, `--gitlab-user`) | Host yes (`charmbracelet/x/conpty` + Job Objects); **relay `uptermd` is Linux-only** | **No — L1 only.** The session lives exactly as long as `upterm host`. No detach, no reattach | SSH | Deliberately ignores `os.Interrupt` "to prevent upterm from dying when SSH clients send Ctrl+C to child processes via ConPTY" | SSH | **N/A** — SSH is the transport | Yes (scoop) |
| **No-PTY architecture** (`claude -p` stream-json + hooks + OTel) | Vendor CLI | Vendor-controlled, publicly documented | — | Continuous | Ordinary pipes; HTTP for hooks and OTel | **Yes** — but "identical on Windows and Linux" is **inference, never measured on both** | **N/A — you own the process** | Bidirectional NDJSON + 5 hook types (incl. `http` and `mcp_tool`) + 34 typed OTel identifiers + JSONL transcript tree. **Per agent vendor** — this is an architecture you implement once per CLI, not a binary you install, so it forfeits agent-agnosticism | **No PTY, so no nesting problem at all** | Near-complete: NDJSON, `permissionDecision`, `updatedInput`, typed telemetry | **Yes, by construction — the only row that passes this column outright** | N/A — it is the agent CLI's own flag surface |

## Comparison table: the PTY-as-a-service lineage

These expose a terminal over HTTP, WebSocket or SSH. Most are refuted, and each is refuted by a **single identifiable cell** — which is what makes them worth reading: the failure modes repeat.

| Name | Language | Licence | Stars | Last activity | Interface | Native Windows | Persistence | The deciding cell |
|---|---|---|---|---|---|---|---|---|
| **OpenCode `/pty`** | TS/Bun | MIT | 192,203 | 2026-08-02 | REST + WS + replay cursor + ticket auth | **Yes** | **L1+** | Best-shaped attach API in the census — **undocumented contract**, and a UTF-8-string wire with a fatal decoder and 64 KiB UTF-16 chunking, so it is not byte-exact |
| ttyd | C | MIT | 12,113 | code 2026-03-20 | HTTP + raw WS | Source yes, **shipped binary broken** | **L0** | `src/protocol.c:377-383` — **a new process per WebSocket, unconditionally killed on close**. The only Windows release (MinGW 1.7.7, 2024-03-30) fails to spawn any child on Windows 11 build 26200, **your exact build**. MSVC fix merged 2026-03-19; no release cut. WinGet and Scoop both pin the broken 1.7.7 |
| gotty (yudai / sorenisanerd) | Go | MIT | 19,531 / 2,523 | 2024-08-01 / 2026-08-01 | HTTP + WS | **No** | L0 | `creack/pty start_windows.go` is literally `return nil, ErrUnsupported`; the active fork ships freebsd/netbsd/openbsd/solaris and **deliberately omits windows** |
| wetty | Node | MIT | 5,362 | 2026-07-31 | HTTP + socket.io | **No** | L0 | Every PTY, including `--command`, is `pty.spawn('/usr/bin/env', …)`; it parses GNU coreutils version strings and gates local mode on `process.getuid?.() === 0`, undefined on Windows |
| terminado / jupyter_server_terminals | Python | BSD-3 | 373 / 20 | 2025-08-02 (docs; last code 2024-04-30) / 2026-01-14 | REST + WS `["stdout",text]` | Yes, via pywinpty | L1 (`NamedTermManager`), L0 (`UniqueTermManager`) | A **design template**, not a product. Its platform selection is a nested `try/except ImportError` chain, not a platform conditional — if both imports fail it binds `PtyProcessUnicode = object` and fails later with an obscure AttributeError. pywinpty underneath binds **a per-PTY ephemeral 127.0.0.1 TCP listener** with an `accept()` race, a `str` round-trip and a literal `'0011Ignore'` sentinel |
| sshx | Rust | MIT | 7,567 | **2025-06-19 (13.5 months)** | gRPC client↔relay + custom canvas UI | Yes (zhiburt `conpty`) | L1 | The author's own source comment: "I can't get `powershell.exe` to work with ConPTY, since it returns error 8009001d." No arbitrary-command argument, no detach, self-hosting "not supported at the moment", and **every release has zero assets** |
| tmate | C (tmux fork) | BSD | 6,092 | 2026-07-29 | SSH | **No** | L2 | A tmux fork, so it inherits tmux's POSIX dependency. The project is alive — the "shutting down" claim traces to a downstream README rather than tmate itself and was not re-verified; the `pushed_at` date is the actual evidence |
| Coder `agent/reconnectingpty` | Go | AGPL-3.0 + proprietary `enterprise/` | 14,004 | 2026-08-02 | Coordinator mesh → WS/SSH | Yes | L1, **self-terminating** | Prior art only. Its screen backend is gated `runtime.GOOS == "linux"`; its buffered backend is a **64 KiB** ring dumped raw and self-labelled "(buggy)"; it closes itself after `Options.Timeout` (default 5 min) and needs a coderd control plane plus Postgres |
| **VS Code `ptyHost`** | TS | MIT | — | Active | VS Code internal IPC | Yes | **L1 across window reloads** | **The most complete prior art in the census, and not the only implementation of the primitive** — Eclipse Theia has an independent `attach(id)` with a Windows-handling shell process. `PersistentTerminalProcess` with `detachFromProcess(id, forcePersist)`, `shouldPersistTerminal`, an orphan-question protocol and `serializeTerminalState(ids)`. Replay is **not a raw byte dump** — it runs `@xterm/headless` plus `@xterm/addon-serialize` and records **resize events too**, up to a 10 MB `MaxRecorderDataSize`. Contrast Coder's 64 KiB raw ring. Open-source server packaging (openvscode-server) is Linux-only |
| **Eclipse Theia** | TS | EPL-2.0 | 21,617 | 2026-08-01 | HTTP/WS or Electron IPC | Partial | attach-by-id exists | A second, independent implementation of the same primitive: `base-terminal-server.ts:49` `async attach(id: number)` against a backend terminal registry, and `packages/terminal/src/node/shell-process.ts:90-91` is `if (isWindows) { return 'cmd.exe'; }`. **Unvalidated on server-mode packaging** — nobody checked whether the backend runs headlessly on native Windows, which is Q25 and the only thing between "reference" and "option" |
| andyk/ht | Rust | Apache-2.0 | 902 | 2025-07-25 | HTTP + WS + NDJSON over stdio | **No** | — | Its own description is nearly the brief verbatim — "wrap any binary with a terminal interface for easy programmatic access" — and it embeds `avt` so callers query the **rendered screen**, not the byte stream. `src/pty.rs` uses `forkpty` + `nix` + `tokio::io::unix::AsyncFd`. **Refuted on the native-Windows constraint, decided by that one file** — so if its description is what you wanted, what you want is a Windows reimplementation of it, not a port |

## Comparison table: ancestors and POSIX-only tools

Kept short deliberately. Each row is here so nobody re-searches it, and each one is out on the native-Windows constraint, decided by a single cell.

| Name | Language | Licence | Stars | Last activity | The deciding cell |
|---|---|---|---|---|---|
| GNU screen | C | GPL | — | 4.9.1 (2023) | Ancestor. Its own original beta-test README: "Since 'screen' uses pseudo-ttys, the select system call, and UNIX-domain sockets, it will not run under a system that does not include these features of 4.2 and 4.3 BSD UNIX" |
| tmux | C | ISC | — | 3.7b (2026-07-01) | Ancestor, and the contract everyone clones. POSIX-only; `cmd-attach-session.c:74-76` holds the nested-session refusal string |
| dtach | C | public-domain-ish | 732 | 2025-06-20 | README: "assumes that the host system uses POSIX termios, and has a working forkpty function available." Also the purest **opaque relay** in the census — no terminal emulation layer at all |
| abduco + dvtm | C | ISC | 969 / 956 | **last commit** 2020-04-30 / 2021-03-06 (not `pushed_at`, which is later for both) | POSIX **and** dormant. Still the closest precedent for the split you want — abduco's author: "these are two distinct features: window and session management shouldn't be intermingled" |
| coder/boo | Zig | MIT | 748 | 2026 (bare year, not re-pulled) | POSIX — `std.posix` in 11 files, zero AF_UNIX hits. Notable for swapping screen's ancient emulator for libghostty-vt and shipping `peek --json` / `wait --idle` as first-class verbs |
| tuios | Go | — | — | — | Unix-socket-only daemon, zero Windows build tags, procfs dependency |
| claude-squad | Go | AGPL-3.0 | 8,222 | 2026-07-30 | `go.mod` has `creack/pty v1.1.24` **and no ConPTY library of any kind**, despite active maintenance; hard tmux prerequisite |
| uzi | Go | MIT | 580 | 2025-06-04 | Hard tmux prerequisite; dormant; zero Windows issues ever filed — neglect, not confirmed non-support |
| reptyr | C | MIT | 6,309 | **2025-11-20** — 8+ months dormant | The POSIX answer to the structurally identical problem, via `ptrace`. **No Windows analogue exists**, after 10+ years |
| Roost | Swift+AppKit / Rust+gtk4 | unstated | — | 2026 (bare year) | Its own docs: "Not a Windows app — macOS and Linux only" |
| wtmux; amux; pymux; conmux; atch; diss; retach; monomux; kip | mixed | mixed | small | mixed | One cell each: detach/attach "planned"; darwin+linux release artifacts only; unmaintained since 2023; abandoned 2019 with no session support; POSIX sockets (four of them); an in-process TUI rather than a daemon |

**How to re-check any cell yourself.** The placement procedure is mechanical, and the transport row is usually the one that decides. Grep the source for `std::os::unix::net`, `std.posix`, `forkpty` or `nix` with term features (POSIX-gated); for `\\.\pipe\`, `CreateNamedPipeW`, `interprocess::GenericNamespaced` or `tokio::net::windows::named_pipe` (named pipes); for `TcpListener::bind("127.0.0.1:0")` (loopback TCP); or for an unconditional `net.Listen("unix", …)` (naked AF_UNIX). One caveat that invalidates the obvious shortcut: **AF_UNIX is a real Windows transport since Windows 10 1803**, so a `UnixListener` in source proves nothing about platform support either way. And for Go projects, `creack/pty` alone is not a disqualifier — quil depends on it *and* on `charmbracelet/x/conpty` and works on Windows. The correct test is the compound one: `creack/pty` present **and no ConPTY library of any kind**.

## What this does not solve

This is the section to read twice. Every option above shares a set of limits, and most of them are not properties of the tool you pick — they are properties of the platform, the topology, or the machine you are sitting at.

### Containers relocate the problem; they never replace the middle layer

The tempting move is "put the agent in a container and let the container be the persistence boundary." It does not work, and the reason is structural: **containerising an agent session relocates PTY ownership, it does not eliminate it.** Every viable container path still needs something *inside* the boundary to own the session — tmux-in-pod, or a proprietary attach layer — and it adds one more VT-parsing and resize boundary on top of the ADE's own PTY. Containers are an optional outer isolation shell around the middle layer, never a substitute for it.

**The WSL question resolves more narrowly than the folklore, and to exactly two surviving paths.** Hyper-V-the-hypervisor and WSL2-the-compatibility-layer are different code paths over the same primitives, so "containers on Windows means WSL" is false. But after applying the open-source constraint, **exactly two open-source non-WSL container paths survive on native Windows: [Podman with `--provider hyperv`](https://github.com/podman-container-tools/podman/blob/main/docs/tutorials/podman-for-windows.md), and [minikube `--driver=hyperv`](https://minikube.sigs.k8s.io/docs/drivers/).** Podman's own Windows tutorial states the constraints plainly: "Because Podman uses WSLv2 or Hyper-V recent features, you need Windows 11 or later", Hyper-V Administrators membership is required (mitigable once via `podman system hyperv-prep`), and "WSL and Hyper-V machines cannot run simultaneously". minikube's driver page lists "Hyper-V — VM (preferred)" for Windows — first-class, not a fallback — though note the same list also marks the Docker driver preferred, so the honest reading is that Hyper-V is not a second-class option, not that it is uniquely blessed.

Everything else fails on one of four grounds.

**Closed source.** [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) is proprietary and paid above 250 employees or $10M, and its own docs say `docker-users` membership "is equivalent to granting administrative privileges on the host" — while the widely-repeated "Hyper-V backend is deprecated" claim is false per that same page. [Docker Sandboxes `sbx`](https://docs.docker.com/ai/sandboxes/get-started/) is architecturally the closest existing thing to what you want and is binaries-only (`docker/sbx-releases` publishes no source). Two things on that page are verbatim and load-bearing: **"Sandboxes persist after the agent exits"** and **"Docker Desktop is not required to use sbx"**. Two things often quoted alongside them are *not* on it and are withdrawn here: there is no `sbx create` command on the get-started page — the invocation shown is `sbx run --name my-sandbox claude`, with the agent as an argument to `run` — and the phrase "re-attaches from anywhere" does not appear. The absence of a Windows edition gate is likewise not evidenced there. Also closed: Daytona, which closed-sourced in June 2026 — its repository root now contains only `README.md` and an assets folder, `GET /license` returns 404, and its README states "As of June 2026, Daytona's core development has moved to a private codebase", leaving 72k stars on an empty repo.

**Hard WSL.** Rancher Desktop requires WSL unconditionally — that requirement is on its **Windows installation prerequisites** page rather than on the [docs root](https://docs.rancherdesktop.io/), which is an introduction page that does not mention WSL at all; cite the prerequisites page, not the root, and re-read it before planning around it, because this guide's own record of the exact sentence traces only to the root. [k3s](https://docs.k3s.io/installation/requirements) is Linux-only by its own requirements page. [Claude Code's own Bash sandbox](https://code.claude.com/docs/en/sandbox-environments) says verbatim: "This option does not support native Windows. On Windows hosts, use WSL2 or one of the container or VM approaches below". And [OpenHands](https://docs.all-hands.dev/) states in its local-setup documentation that "OpenHands only supports Windows via WSL… Native Windows is not officially supported", superseding an older non-WSL guide.

**Dead.** [DevPod](https://github.com/loft-sh/devpod/issues/1946)'s last release is `v0.7.0-alpha.34` from 2025-06-23, and issue #1946 is where the abandonment is usually sourced. **Be careful with that citation, because it is the one place in this guide where the evidence tier inverts if you are sloppy:** the sentences "their attention is focused on vcluster" and "they do not have plans at this moment to allocate resources to maintaining this project" are from the *issue body*, written by `skevetter` — a third party with no repository association, proposing his own fork — and his own framing is explicitly hedged: "based on the lack of engagement from the original developers…, **it is fairly safe to say** they do not have plans at this moment…". That is a community member's declared guess, not a maintainer statement, and it should never be quoted as the project's own words. The unhedged evidence is the release date. Also dead: [dagger/container-use](https://github.com/dagger/container-use/pull/252), whose own open PR says "#242 added Windows compilation but no installation method", whose Windows terminal path discards caller arguments, and which registers as a stdio MCP server — a shape that cannot own persistent sessions at all.

**Wrong kernel.** [Windows Containers](https://learn.microsoft.com/en-us/virtualization/windowscontainers/about/), in both process and Hyper-V isolation, run a **Windows** guest and cannot run Linux binaries. Hyper-V isolation gives you a real VM boundary and the guest inside it is still Windows, which is the whole problem.

**And two container-adjacent notes worth keeping, because both save time.** `kubectl attach` is **L0** — a fresh process every time — and the community's own fix for that is *tmux inside the pod*, via tools like `predatorray/kubectl-tmux-exec`, which need bash and tmux **on the client** and therefore cannot run on native Windows at all. That is this section's thesis in miniature: the container did not remove the need for a session layer, it moved the session layer inside the container and then required a POSIX client to reach it. Separately, do not count `kind` and Docker Desktop's "bundled Kubernetes" as two options — [Docker Desktop's own documentation](https://docs.docker.com/desktop/features/kubernetes/) says the bundled cluster **is** kind (or kubeadm), so they are one candidate wearing two names, and `kind` inherits whatever backend you point it at rather than providing one.

One container-adjacent tool deserves a specific warning because it looks like a fit and is architecturally hostile. [anthropic-experimental/sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) launches the sandboxed process via `CreateProcessWithLogonW` **under a different local user account**, "not as the calling user". Its README states the consequence without any inference needed: "Per-user tool installs are not reachable… tools installed under your profile (nvm/fnm-managed Node, per-user winget/Scoop packages, `pip install --user`, `%LOCALAPPDATA%\Programs\…`) resolve on the inherited PATH but cannot be opened by the sandbox account." **Claude Code's default Windows install lands exactly there.** The second consequence — that a console owned by a foreign user SID is not `AttachConsole`-able by your process — is an inference from documented per-session console semantics and has never been tested.

### Late attach cannot be made into a foundation

If you were hoping to reach *into* an agent process that is already running under someone else's PTY, that door does not open. The full evidence is under [AttachConsole](#attachconsole-and-what-multi-client-object-buys-you) and [Who owns the session](#who-owns-the-session-whoever-called-the-pty-spawn-api) above; what belongs in a limits section is the shape of it, in four lines.

- **Microsoft has told developers not to build on the write half.** `WriteConsoleInput` carries an **Important** banner calling it functionality "no longer a part of our ecosystem roadmap" and a separate **Tip** calling it "the wrong-way verb for this buffer"; the classic-vs-VT page names input injection and output scraping as "a vector to cross security and privilege-levels or domains".
- **The read half is gated by integrity level, directionally.** A lower-integrity process cannot read a higher-integrity console. Same-user, same-integrity siblings — which ORCA's children are — are unaffected; it bites for elevated agents, cross-user, and session 0.
- **Nobody has built a general late-attach library**, and the reason is that every mature implementation ships exactly one half: NVDA reads and never writes, winpty and wexpect read and write but own the console from birth. The halves never combine.
- **It is not a nested topology at all**, so it is not an alternative to anything else in this guide. It is an out-of-band, sideways-reaching daemon — a different shape, worth naming rather than silently conflating with the others.

Whether `AttachConsole` even reaches an ORCA-spawned agent in the exact Electron-plus-node-pty topology is untested (Q5). A success there buys you a read-only out-of-band inspection path and nothing more.

### The node-pty defects that live in your stack today

These are not risks you might take on. If you run ORCA, they are already in your process. All of them are [microsoft/node-pty](https://github.com/microsoft/node-pty) issues.

| Defect | State | Consequence |
|---|---|---|
| `AttachConsole failed` crash when killing an already-exited shell | [PR #886](https://github.com/microsoft/node-pty/pull/886) open since 2026-02-06, unmerged; [PR #901](https://github.com/microsoft/node-pty/pull/901) (Node 22 resize-after-exit) open, unmerged | Surfaced as user-visible crash dialogs in shipping Electron products — [openai/codex#25415](https://github.com/openai/codex/issues/25415) and [microsoft/vscode#201029](https://github.com/microsoft/vscode/issues/201029) |
| The partial mitigation that *did* land | Commit `2b25c761`, "Don't get process list on kill if not yet connected", in v1.2.0-beta.11, 2026-02-03. **This is not PR #886's try/catch guard** — it predates #886 by three days and does something different; do not read it as "#886 landed" | Codex and VS Code shipped **stale bundled copies** and crashed for want of this one commit. The fix on your side is one line of dependency hygiene: pin node-pty ≥ 1.2.0-beta.11 |
| Root cause still open | [vscode#201029](https://github.com/microsoft/vscode/issues/201029) final comment: "kill() unconditionally tries to enumerate console processes for a shell whose exit has already been handled" — `resize()` has an `_exitCode` guard, `kill()` does not | Triggered by short-lived diagnostic shells (`cmd.exe /c "exit /b 0"`) racing the kill path |
| Data race in `ptyHandles` | [issue #921](https://github.com/microsoft/node-pty/issues/921), fixed 2026-05-13 | A process-global vector mutated from per-PTY watcher threads; concurrent `std::remove_if` dereferenced a moved-from `unique_ptr`. A real hazard at moderate session counts — which is exactly what one-agent-per-worktree produces |
| Conout worker deadlock | [PR #943](https://github.com/microsoft/node-pty/pull/943), merged 2026-07-31 | A **regression of a bug already fixed once** (#763 → PR #885 → regression → #943). Triggered when the Node inspector pauses the conout worker thread |
| ORCA's own instance | [stablyai/orca#9586](https://github.com/stablyai/orca/issues/9586), closed with zero comments and no maintainer reply | Read the "root cause / fixed in v1.2.0-beta.11" text there as the **reporter's own unreviewed self-diagnosis**, not an established finding |

There is a second, quieter hazard in the same library, set out under [The four things a middle layer must get right on Windows](#the-four-things-a-middle-layer-must-get-right-on-windows): node-pty's bundled ConPTY prototypes have **drifted from the current ConPTY ABI**, in both directions, on the `useConptyDll` path. The symptom of a mismatch like that is a clear or a resize that silently does nothing, which is the worst class of bug to debug, and it lands on you rather than on the library.

**And one supply-chain note for anyone reaching for a Go PTY library to escape all this.** `creack/pty` has no Windows backend, so Go projects that need ConPTY have to route around it. Wave Terminal's route is a `go.mod` line: `replace github.com/creack/pty => github.com/photostorm/pty`. That fork has **15 stars and was last pushed 2024-04-14**. It works, and it is a named supply-chain risk sitting in the dependency graph of a 21k-star product. If you find yourself about to add the same `replace` directive, know what you are adding. The better-supported answers are `charmbracelet/x/conpty` (used by upterm and quil), `aymanbagabas/go-pty` (used by Agent Orchestrator) and `UserExistsError/conpty` (used by kandev).

### What each non-multiplexer route gives up

If you decide against a PTY-owning daemon, know precisely what you are trading. Each row below is a real route somebody ships; each forfeits something specific.

| Route | Persistence | Reattach | What it costs you |
|---|---|---|---|
| Windows OpenSSH Server | **No** | No | [Win32-OpenSSH#2291](https://github.com/PowerShell/Win32-OpenSSH/issues/2291), filed by a Microsoft member and still open: no tmux equivalent exists. sshd puts children in a Job Object and disconnect tears it down — **not SIGHUP, so there is no signal to trap**. Caveat worth carrying: the Job-Object mechanism rests on one maintainer sentence, and code searches for `CreateJobObject`/`KILL_ON_JOB_CLOSE` in openssh-portable return zero hits. Treat it as absence of evidence, not as established |
| Windows Service | Yes | **No** | Plus a session-0 problem in two halves. The established half: a SYSTEM account has no user-profile agent credentials, and agent CLIs authenticate from the profile (`~/.codex/auth.json`, `~/.claude/`). The inferred half: console objects are per-session and `AttachConsole` takes a PID, so it should not cross the session-0 boundary — **an inference from two documented facts, never observed to fail** |
| Scheduled Task | Yes | **No** | Same, except it avoids the credentials half if you run it as the user rather than as SYSTEM |
| Hooks + file/JSONL IPC | Structured replay | Not live | Resumed sessions **replay saved hook output** rather than re-running it, so timestamps and commit SHAs go stale |
| LangChain agent-inbox | Yes, as a queue | **No** — a queue of pending decisions, not a session | The pattern is transferable and the implementation is not: it requires `from langgraph.types import interrupt` and a running LangGraph deployment, so you adopt a framework rather than a component. (Its response discriminator was recorded as `'response'` rather than `'respond'`, with the config flags using `allow_respond` — an API detail carried from one pass with no file or doc URL, never re-verified) |
| Job-queue fleets (Actions runner, Buildkite, OpenHands) | Yes, at scale | **No** — a streamed log, not a shell | A deliberate trade, and the right one if you never attach |
| RDP / `tscon` | **Yes** | **Yes** | The in-box counterexample that breaks "every route gives up one" — a disconnected RDP session keeps every process running with a live console and you reattach by reconnecting. The cost is **whole-session granularity**: no per-worktree agent tabs, [you can't connect to the console session](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tscon), and client SKUs allow one interactive session |
| `codex app-server --listen ws://` | **Yes** | A standing listener the client does not own | The other counterexample — but its own README labels websocket "experimental / unsupported. Do not rely on it for production workloads", the daemon lifecycle manager is explicitly Unix-only, and it owns no PTY |

The cleanest evidence that file-based IPC *narrows* PTY dependency without eliminating it comes from a harness author in [openai/codex#11750](https://github.com/openai/codex/issues/11750) (still **open**), who describes the workaround as "spawning `codex fork` inside a pseudo-TTY, polling the filesystem for new rollout files to discover the forked session ID, killing the TUI, and then using `codex exec resume --json <forked_id>` for the actual query. **This works but is fragile and slow (~6s overhead for TUI startup)**." Further down the same issue he adds that it "requires PTY bindings (e.g. Python's `pty` module or `node-pty`), and is tightly coupled to the rollout file format" — **two separate sentences from two places in the issue**, which is worth knowing because they are usually spliced into one quotation that appears nowhere in the source. Read the substance carefully before generalising from it: `thread/fork` already exists on app-server, so the PTY fallback exists because `codex exec` lacks a fork verb, not because the capability is intrinsically PTY-bound. (Also note the project that filed it, bearlyai/OpenADE, has **no LICENSE file and `license: null`** — all-rights-reserved by default, so it is usable as evidence and not as a component.)

### Unauthenticated local IPC: the shared security problem

Several of the strongest candidates share one defect, and it matters more the more you share the machine. The transport ranking — ACL'd named pipe, then AF_UNIX, then loopback TCP — and the per-user rather than per-process ceiling on all of them are stated as build requirements under [the verb set](#the-verb-set-an-ade-agnostic-middle-layer-has-to-expose). Here is the evidence, in descending order of how much it should worry you:

- **psmux's cross-session port is unauthenticated and full-duplex.** `src/cross_session_server.rs` binds a loopback port, accepts the first connection with no handshake, registers it as a **tee writer** so it receives every byte the pane's ConPTY emits, and writes everything it reads back into the PTY — exfiltration *and* injection, gated only on the user performing a cross-session pane move, and reachable in practice or not is Q6. The line numbers are in the psmux entry above, along with the separate weakness in the *main* control listener's `AUTH` key: a 64-bit non-cryptographic secret in a file with no explicit ACL.
- **oly's named pipe has no ACL at all**, and no `FILE_FLAG_FIRST_PIPE_INSTANCE`, so a hostile local process can pre-create it and harvest client connections. [Microsoft's `CreateNamedPipe` documentation](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea) states that a NULL security descriptor grants "read access to members of the Everyone group and the anonymous account" — for a pipe carrying agent terminal I/O, that is an API-key disclosure path, covering whatever the agent prints and whatever you type into it. The project's own roadmap has listed the fix as not started since 2026-03-12; the evidence, and the later audit that fixed the web layer without touching this, are in the oly entry above (Q13).
- **`ao pty-host` says so itself.** `host_main.go` carries the caveat in the source: "loopback bind only; any local process on this host can connect to the assigned port. A per-session random token handshake is the upgrade path."

The counterexample, and the design to copy: **rmux is the only candidate that gets both halves right** — a pipe name computed from the caller's SID and integrity level rather than picked from a string, plus `FILE_FLAG_FIRST_PIPE_INSTANCE` and an `ImpersonateNamedPipeClient` peer check. **Namespacing prevents accidents; ACLs prevent attacks. You need both.**

If you homegrow a shared-secret scheme instead, read [Erlang's own distribution security section](https://www.erlang.org/doc/system/distributed.html) first: cookie authentication is "not cryptographically secure" and communication is cleartext by default. Do not build something weaker than a scheme whose own documentation disclaims it.

### Limits that live in the platform, not in any candidate

The mechanics of these are under [Nesting](#nesting-your-middle-layer-runs-inside-the-ades-conpty); collected here so a limits-only reader still meets them, with the consequence rather than the argument.

- **ConPTY reflow/resize desync is unfixable from outside** — [microsoft/terminal#15976](https://github.com/microsoft/terminal/issues/15976), a megathread, with the in-process ConPTY spec calling it **unsolvable** in the current architecture. Consequence: a nested middle layer that keeps its own screen model becomes a **third independent representation** of the same screen. Whether the in-process redesign has shipped, partly shipped or stalled is Q17.
- **Passthrough fixed double VT parsing and made one thing worse.** ConPTY has passed application VT output through unmodified by default since [PR #17510](https://github.com/microsoft/terminal/pull/17510) merged 2024-08-01, so "double VT parsing is unsolved at the OS level" is wrong today. But passthrough injects VT sequences into stdout regardless of parser state, which is the mechanism behind [microsoft/terminal#19621](https://github.com/microsoft/terminal/issues/19621) — still open, filed by a Microsoft member. **If your interface is tmux control mode, that issue is your issue.**
- **Pasting more than 5 KiB into a slow-reading app deadlocks the whole terminal**, and Ctrl-C stops working — [microsoft/terminal#17384](https://github.com/microsoft/terminal/issues/17384), open since 2024-06-06.
- **Residual VT-passthrough issues remain open** in [microsoft/terminal#17643](https://github.com/microsoft/terminal/issues/17643). Cooked-read reflow, `ScrollConsoleScreenBuffer`, the DA3 truncation and the PSReadLine SGR issue are all **fixed** — do not carry those forward as hazards.
- **OSC 133 cannot be forwarded through a nested layer.** tmux's maintainer `nicm` gives the reason across two separate comments in [tmux#5237](https://github.com/tmux/tmux/issues/5237) (open) — quoted here as two, because they are usually run together under an ellipsis that implies one utterance. First: "If tmux writes a prompt at 10,10 and you drag the pane so it is now at 15,15, how does tmux tell the terminal it has moved?" And later: "The sequences are not powerful enough… they are meant for shells, not full screen programs." A nested layer must parse-and-re-expose, not forward. And Claude Code does not emit OSC 133 anyway — at least five duplicate requests since May 2025, all bot-closed. (If you want OSC 133 from a shell rather than from an agent, note that **even `cmd.exe` has a path**: oh-my-posh's `shell_integration` documentation states it "Works in bash, **cmd (Clink v1.14.25+)**, fish, powershell and zsh", so "no cmd.exe OSC 133" is false. tmux's own OSC 133 *events* — `pane-command-started` and friends — are in unreleased master only; the latest release is 3.7b.)

The standards and guarantees that do not exist at all — no MCP terminal convention, no specification of tmux control mode independent of tmux, no Windows reptyr, no ConPTY compatibility matrix, no primary source for the build thresholds — are collected under [What does not exist](#what-does-not-exist), so that a weekend is not spent searching for any of them.

---

## The playbook: what to pick and how to verify

### The decision that matters most, first

Before you compare daemons, answer this: **do you need the byte stream of a program that insists on a terminal, or a human typing into a live session — or neither?**

Everything downstream turns on it, because **those are the only two things PTY ownership buys that no other channel provides.** (Not "exact on-screen state" — screen state is derivable from any byte stream plus a VT emulator, as asciinema's relay demonstrates without ever touching a PTY. It is the *byte stream* that needs the PTY.) If you need neither, you do not need any of the candidates in this guide, and every hard problem in it disappears at once: no ConPTY, no nesting, no prefix keys, no resize propagation, no double parse. The channel that replaces them — `claude -p` stream-json, hooks as the write path, OpenTelemetry as the read path — is set out in full in [When you need a session daemon](#when-you-need-a-session-daemon-and-when-you-do-not).

**Answer it by measurement, not by intuition.** Instrument one week of real work and count the sessions where you actually attached and typed mid-run against the sessions you only observed. That is Q9 below and it costs nothing but a week of passive logging — a "sufficient" answer moots most of the candidate comparison, and a "not sufficient" answer gives you a *number* for how often you need attach, which is the input to every remaining trade-off.

### The running order, with wall-clock

Q9 is the highest-*leverage* question and it is not the first thing to do, because it takes a week and two other tests take two hours each and can kill whole branches before the week is out. Start all three on day one:

| When | What | Cost | What it can kill |
|---|---|---|---|
| Day 1, morning | **Q23 — do any candidate's verbs work with no console attached?** Step 3 of the verification ritual, run once against every candidate at the same time | 2 hours | **The entire PTY branch, in one afternoon.** If the verbs need a terminal, every candidate here is a multiplexer rather than a middle layer, and the no-PTY route wins by default. This is the cheapest disqualifier in this document |
| Day 1, afternoon | **Q1a — can `agentCmdOverrides` produce a raw-pipe child at all?** Read ORCA's spawn path end to end | 2 hours | tmux `-CC` as an interface, which moots the whole `-CC` corruption question (Q1) and drops psmux to its plain verb surface |
| Day 1, and then leave it running | **Q9 — is the no-PTY architecture sufficient for your actual sessions?** Passive logging, nothing to babysit | 1 week elapsed, ~0 attention | Most of the candidate comparison, if the answer is "sufficient" |
| Week 2, once Q23 and Q1a are in | Q3 (Zellij input path, 1 hour), Q4 (xterm.js `CSI 18 t`, 1 hour), Q12 (OpenCode `/pty` on Windows, 1 hour), then Q18 (nesting, 1 day) | ~1.5 days | Individual candidates, not branches |

The logic is simply cost-versus-blast-radius: **two hours that can eliminate eleven candidates beats a week that can eliminate eleven candidates**, and you can have both because the week is passive.

<a id="run-your-own-constraints-as-a-filter-first"></a>

### Run your own constraints as a filter first

Before any of the situational sections below, run this ladder. Each rung is a yes/no about *you*, not about a tool, and each one names what it removes. It takes about five minutes and it is the thing that turns "here is the whole space" into a shortlist.

1. **Native Windows, no WSL?** → the entire POSIX table goes: dtach, abduco+dvtm, boo, ht, tuios, reptyr, tmate, gotty, wetty, claude-squad, uzi, `mobydeck/atch` and the rest. Also out: every hard-WSL container path. **Survivors:** psmux, Zellij, rmux, herdr, oly, qscreen, quil, `wezterm-mux-server`, OpenCode `/pty`, `ao pty-host`, upterm, plus the no-PTY route.
2. **Must it survive the ADE, not just the client?** → **upterm goes** (L1 only, no detach, no reattach) and **OpenCode `/pty` goes as a middle layer** (L1+, dies with `opencode serve`) — though OpenCode's cursor protocol stays as a design to copy. **Survivors:** psmux, Zellij, rmux, herdr, oly, qscreen, quil, `wezterm-mux-server`, `ao pty-host`.
3. **Do the verbs work with no console attached?** → this is Q23 and it is not a preference, it is a measurement you have not made yet. **Either nothing goes or everything PTY-owning goes**, which is why it is first in the running order above. The no-PTY route and the two network-attached candidates (`ao pty-host`, OpenCode `/pty`) pass by construction.
4. **Do you need a pinned stable release?** → **herdr goes** (Windows ships preview-channel only; stable v0.7.5 has no Windows asset) and **`wezterm-mux-server` goes** (newest tagged release 2024-02-03; the rolling `nightly` is the only current Windows path). **Survivors:** psmux, Zellij, rmux, oly, qscreen, quil.
5. **Do you share the machine, or run anything you do not trust as your own user?** → **psmux goes** until Q6 is answered (unauthenticated full-duplex cross-session port) and **oly goes** until Q13 is answered (named pipe with no ACL). **Survivors:** Zellij, rmux, qscreen, quil.
6. **Does it have to behave identically on Linux?** → **psmux goes** outright (Windows-only CI and Windows-only release assets) and **oly's parity is disproven** by its Windows-specific expected-output fixture. **Survivors:** Zellij, rmux, and — if you relax rung 4 — `wezterm-mux-server` and herdr.
7. **Are you willing to vendor and build source rather than install a binary?** → if yes, **`ao pty-host` re-enters** (Apache-2.0, the closest architectural match found) and so does **WezTerm's varint codec** as a protocol to implement. If no, both stay out.

**Where the ladder typically lands.** All rungs applied strictly, with rung 3 passing: **Zellij or rmux**, and the tiebreak is in the Linux-parity section below. Rung 6 relaxed: **psmux** re-enters with the strongest interface and the worst platform breadth. Rung 3 failing: **nothing PTY-owning survives** and you are on the no-PTY route whether you wanted to be or not. That is a decision procedure rather than a verdict — the ranking is yours, produced by your own answers.

### If you only need to observe an agent

Take the no-PTY route and stop reading the candidate list. It is the only option in this guide that passes the console-independence test **by construction** — ordinary pipes, no console needed anywhere — rather than "probably, untested".

**Two sentences of honesty about what that costs, because they are the reason this is not simply the answer for everyone.** This is an architecture you **implement per agent vendor**, not a binary you install: `claude -p` stream-json, Claude Code hooks and the `claude_code.*` telemetry are Claude Code's, and Codex's `exec --json` plus rollout JSONL is a separate implementation of the same shape rather than the same one. **You buy console-independence and forfeit agent-agnosticism** — which is precisely the property "a layer any ADE can spawn with any agent CLI inside it" was asking for. If your agent roster is one CLI, the trade is excellent. If it is three, you are writing three integrations and tracking three config surfaces that "change under you", as the agent-state axis puts it.

Build it out of four vendor-maintained channels. **`claude -p` stream-json** for the duplex channel, with `--include-hook-events`, `--forward-subagent-text` (which carries `parent_tool_use_id`), `--include-partial-messages` and `--replay-user-messages` as companions — being honest that this is print/headless mode and **it does not attach to an existing interactive TUI**; it is a way to *spawn* the agent with no PTY at all. **HTTP hooks** for the write path, so the middle layer is the endpoint rather than a spawned child. **OpenTelemetry** for liveness, remembering that the master switch is `CLAUDE_CODE_ENABLE_TELEMETRY=1` and not an `OTEL_*` variable, that content is redacted until you opt in per field, and that Claude Code strips `OTEL_*` from every subprocess it spawns so the config does not reach grandchildren. And **the JSONL transcripts** for replay — a tree rather than a file, with subagent fan-out readable from the filesystem alone, and undocumented enough that anything treating it as durable needs its own retention policy. Each of those four, with its flags, environment variables and documented limits, is in the opening section.

**One load-bearing claim here is inference, not observation.** That `claude -p --output-format stream-json` behaves identically on Windows and Linux is inferred from unqualified flag documentation over ordinary pipes. **Nobody has run it on both platforms and compared the output.** If cross-platform parity is what sold you on this route, spend an afternoon proving it before you build on it.

If you want a second, vendor-native instance of the same architecture, Codex's `exec --json` plus rollout JSONL under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` with `resume --last` is the same shape from a different company. The cross-vendor convergence on that shape is itself evidence that this is a real architectural pattern rather than one company's idiosyncrasy.

### If the session must survive a reboot

**Then nothing in this guide gives you what you want, and you should design for reconstruction instead of persistence.** The persistence ceiling on Windows among everything surveyed is L2 — a detached daemon that outlives whoever spawned it. The only L3 claim found anywhere is [cmux](https://github.com/manaflow-ai/cmux) (Swift + AppKit, GPL-3.0-or-later, 25,483 stars), whose FAQ says "the state survives a full computer restart… Agent sessions like Claude Code, Codex, and OpenCode come back too". It is **macOS only**, so it is not a fallback and not something you can even evaluate on your platform — and the quote comes from a FAQ read once with no URL recorded, so treat it as reported rather than verified. It is here as the one existence proof that somebody built L3 at all.

So build the restart path explicitly out of three pieces. **A session registry on disk**, so orphans are findable after a metadata loss — `ao pty-host` is the model, persisting `~/.ao/windows-pty-hosts.json` with `{sessionId, ptyHostPid, pipePath}`. **A conversation-state source that is not the PTY** — the JSONL transcripts and `codex resume --last` both survive a reboot, subject to the retention caveat above. And **a respawn step** that re-creates the process and replays state into it, because the process itself is gone.

Do not reach for a Windows Service or a Scheduled Task to close the gap. They give you persistence and take away reattach, and the Service path additionally lands you in session 0, where a SYSTEM account has no user-profile agent credentials — which is the half of the session-0 problem that is documented rather than inferred. A Scheduled Task running *as the user* avoids the credentials problem, and still gives you no reattach.

### If you need a real PTY owner

You are here if either of the two things PTY ownership buys is on your list — **the byte stream of a program that insists on a terminal**, or **a human typing into a live session**. **Read this whole section even if you want only the first one and no human is ever going to attach**, because the criteria below apply to both cases and the human-attach material is a sub-case at the end, not the frame.

**Attach must be first-class, not an afterthought, and it must carry a resumable cursor.** This is the criterion that matters most for a *headless* consumer, not just a human one: the middle layer's whole value is that a new client — your supervisor process, restarted after the ADE was upgraded — can pick up an existing session, and a replay that starts from zero every time is not that. The one primitive nothing else substitutes for is `attach(id, {cursor}) → {replay, cursor, stream}`. OpenCode's `/pty` protocol is the model **for the cursor semantics only** — copy its absolute-output-cursor control frame, not its wire type, because the payloads are JavaScript strings that split surrogate pairs at the 64 KiB replay boundary and silently drop invalid UTF-8 on the way in. It is also L1+, not L2: it dies with `opencode serve`.

**Watch out for string-typed wires generally, not just that one.** Agent CLIs emit heavy Unicode — the `✳` in Claude Code's own window title already broke quil's emulator — and a `from_utf8_lossy` or a `String.slice` in the middle of the live path corrupts it **permanently**, not cosmetically. On the strict test — what is the declared type of the message the server sends on every output tick? — **three candidates carry bytes end to end**: qscreen's `AttachMode::Bytes`, oly's `ServerMessage::Data { data: Vec<u8> }`, and quil's `PaneOutputPayload { Data []byte }`. **psmux's `-CC` `%output` does not qualify on the strict test**, despite being octal-escaped and byte-oriented in intent, because the ring drain runs `String::from_utf8_lossy` at `src/server/mod.rs:1225` *before* the escaping — the escape faithfully encodes bytes that have already been damaged. Where the axes section places psmux `-CC` in the raw-live-path pole, that is design intent; here, where you are choosing something to run, take the strict reading.

**The prefix key is the thinnest-evidenced part of this whole area, and it is a daily-annoyance problem rather than a correctness one — but for a headless consumer it is a correctness one.** Every multiplexer candidate's rebindability is inferred from "it has a config file"; the only *documented* remapping mechanism found in the entire census belongs to [`docker attach --detach-keys`](https://docs.docker.com/reference/cli/docker/container/attach/), which is not a candidate. The one primary-source statement about prefixes on Windows is herdr's own beta page listing "Prefix input-source switching | unsupported". What you actually want is stronger than rebinding — **no prefix at all on the headless path, with the prefix existing only when a human attaches** — and no candidate is known to offer it. That is Q24, it costs three hours, and if the answer is no you inherit a keybinding negotiation with every ADE you ever swap to, which is the exact thing this project exists to avoid.

**Sub-case: if a human genuinely has to be able to sit down at it.** Everything above still applies, plus two more considerations. Keep one in-box option on the table: **RDP with `tscon` gives both persistence and reattach natively, with no third-party code at all.** It is whole-session granularity, so it cannot give you per-worktree agent tabs, but if what you need is "walk away and come back to a live desktop", it is already installed. And in the candidate list, first-class attach/detach verbs stop being a nice-to-have — `wezterm-mux-server` documents attach and detach as first-class operations, psmux and rmux inherit tmux's, and qscreen's raw-byte attach mode is the cleanest of the small designs.

### If you need it to work identically on Linux

**psmux is out.** Its CI builds only `x86_64/i686/aarch64-pc-windows-msvc`; the `ubuntu-latest`/`macos-latest` job runs two POSIX shell scripts and is **not a build**, and release v3.3.7 ships six Windows-only assets. It has the strongest interface in the census and the worst platform breadth, and those are the same fact seen twice.

**Treat oly's platform parity as disproven, not unknown.** It ships `tests/output-copilot.expected.windows` alongside `tests/output-copilot.expected` — a Windows-specific expected output for the *same* input log. That is direct evidence its VT/log-rendering layer produces different output on Windows than on Unix.

Survivors: **Zellij** (original target platforms, plus a `zellij-x86_64-pc-windows-msvc.zip` and an MSI at v0.44.3), **rmux**, **`wezterm-mux-server`**, and **herdr**. Among those, the tiebreak is usually posed as maturity against transport design: Zellij has 34.6k stars, an MSI, and the best-verified Windows claim of anything surveyed; rmux has the only identity-scoped namespace and the only three-layer Windows security model, against a single-author bus factor (roughly 936 of ~1000 commits from one author, a figure recorded once and never re-verified) and a dual-licence pair that is unstated in repo metadata — **read `LICENSE-*` at the tag you would vendor before relying on it.**

**But check whether that tiebreak is even live for you, because for a lot of readers it is not.** rmux's identity-scoped pipe is protection against *another local principal* — a second account, a low-integrity process, something you did not start. **If you are the only account on the box and your threat model does not include a hostile local process, the entire security column collapses to a tie**, rmux's main claimed advantage over Zellij stops discriminating, and the choice reduces to maturity against transport-design taste plus whatever the nesting tests (Q18) turn up. Say which of those two situations you are in before you spend an afternoon comparing pipe ACLs — and note the ceiling that applies either way: authentication in this whole category is per-*user*, not per-*process*, so ORCA, every agent CLI, every MCP server and every npm postinstall script already run as you and can already reach any of these endpoints.

Two more filters land on top of that set. If you **need a pinned stable release**, herdr is out (Windows ships preview-channel only; stable `v0.7.5` has no Windows asset) and `wezterm-mux-server` is out — its newest tagged release is `20240203-110809-5046fc22`, published 2024-02-03, so "pin a version" and "run on Windows" are in direct tension; the rolling `nightly` tag is the only current Windows path. That leaves Zellij (msvc zip plus MSI) and rmux (winget/scoop/choco). If you are **willing to vendor source**, `ao pty-host` opens up — Apache-2.0, the closest architectural match found, detached ConPTY with scrollback replay and largest-client resize arbitration — and so does WezTerm's varint codec as a protocol to implement rather than a binary to run. That codec is the only wire format surveyed that was **explicitly designed for version-skewed client/server pairs**, which is the ADE-churn insulation you are shopping for, expressed in wire form.

### If you are wrapping under ORCA specifically

**Start with the hook itself, because everything in this section and step 4 of the ritual runs through it.** `agentCmdOverrides` is declared in `src/shared/types.ts` and consumed at `src/shared/tui-agent-launch-command.ts:30`, where the lookup is `const override = args.cmdOverrides[args.agent]` — an object keyed by agent identifier, whose value replaces the launch command for that agent. So an override that puts psmux underneath Claude Code looks like this:

```jsonc
// ORCA settings — shape inferred from the consuming code, NOT from ORCA documentation.
// Verify the key spelling and the value's shape against your installed version before
// relying on it; the one thing verified at source is the lookup at
// src/shared/tui-agent-launch-command.ts:30.
{
  "agentCmdOverrides": {
    "claude": "psmux new-session -A -s orca-${worktree} claude"
  }
}
```

Three things to get right when you write your own. **The agent key must match whatever ORCA calls that agent internally** — read it off the same file rather than guessing. **The override replaces the whole command**, so anything ORCA would have appended (model flags, working directory arguments) is now yours to reproduce. And **the middle layer must exec the agent, not fork-and-exit**, or ORCA's pane will see its child terminate immediately. Whether your override string can produce a *raw-pipe* child rather than a ConPTY child is exactly Q1a, below.

**Answer Q1a before you do anything else, because it can moot the question you were about to ask.** ORCA spawns through node-pty, which means **always a ConPTY**. The documented remedy for tmux control mode corruption is "give the child raw pipes" (`ssh -T user@host tmux -CC`). So the question is not "does ConPTY corrupt `-CC` in my topology" — it is **"can `agentCmdOverrides` produce a raw-pipe child at all?"** Read ORCA's spawn path from `src/shared/tui-agent-launch-command.ts:30` through to the node-pty call and check whether any override shape bypasses the PTY. Two hours. If the answer is no, `-CC` is unreachable in this topology whatever the corruption test would have shown, psmux drops to its plain CLI verbs, and the case for psmux drops to what its plain verb surface is worth. This is the general rule stated under [Nesting](#test-the-cure-before-the-disease): test whether the cure is reachable before testing whether the disease exists.

Be precise about what the corruption claim actually says, because it is easy to over-state. psmux's maintainer scopes it to running over SSH with a ConPTY console; **the generalisation to a node-pty ConPTY is inference, not the source's claim**, and Q1 tests it in an afternoon. A related divergence is documented rather than inferred and is worth knowing regardless of how Q1 turns out: `%output` data on Windows may differ from what a Unix tmux session produces, because ConPTY normalises line endings and processes some cursor movement internally.

**Pin node-pty ≥ 1.2.0-beta.11** on ORCA's side. Commit `2b25c761` ("Don't get process list on kill if not yet connected") landed upstream on 2026-02-03 and is what stops the `AttachConsole failed` crash dialogs; the products that still crash are shipping stale bundled copies. Note this is a mitigation rather than the full fix — PR #886's try/catch guard is still open and unmerged, and the root cause in `kill()` is still open at vscode#201029. This is the cheapest thing on this entire list.

**Check Zellij's input-path gate before concluding anything from a bad first run.** Inside ORCA's node-pty ConPTY, neither `TERM` nor `WT_SESSION` is necessarily set, so Zellij takes its native-console `INPUT_RECORD` input path rather than the VT one. This is a **config check, not a hazard** — the details are in the Zellij entry above — and one environment variable in the override command (`TERM=xterm-256color`) forces the other path. What is genuinely unknown is what the *symptom* would be if the native-console path misbehaves under a nested ConPTY, which is why Q3 currently has no pass/fail criterion.

**Assume nesting is untested, because it is.** Double-ConPTY nesting has not been verified for *any* candidate, including oly, whose supposed nested-agent tests turn out to spawn shells rather than agents. Q18 is the test; budget a day for all four candidates and run it with a resize, an alt-screen app and a mouse-mode app.

**If you use psmux's nesting guard, read the code and not the error message.** The check at `src/main.rs:954` and `:4056` reads `PSMUX_ALLOW_NESTING`, but the error printed at `:958`/`:4060` says "psmux: sessions should be nested with care, unset PSMUX_SESSION to force". A scripted wrapper that follows the message will not clear the guard.

### If you share the machine with anyone

Then re-read the unauthenticated-IPC subsection above and treat it as a filter, not a footnote. Prefer a named pipe with a real ACL over AF_UNIX over loopback TCP, in that order. Ask Q13 (does oly's ACL gap still exist?) and Q6 (is psmux's cross-session path reachable?) *before* adoption, not after. And run Q22 — a single NVD/GHSA sweep for the four small candidates, one hour — because only their own issue trackers were ever checked.

### If you end up building it yourself

Every candidate got most of it right and each forfeited exactly one of {maturity, Windows-nativeness, standalone packaging, contract stability}. If that trade is unacceptable, the two things that most often go wrong are **not** in the verb list, and both are cheap to get right at the start and expensive to retrofit: **answering ConPTY's startup handshake**, and **not putting a string type on the wire**. Adopt an existing framing rather than inventing one — tmux `-CC` is decade-hardened with at least five implementers, and WezTerm's varint codec is explicitly built for version skew (read its `LICENSE.md` at the commit you vendor; GitHub's licence API reports NOASSERTION for the repository). Use rmux's identity-scoped pipe shape for the namespace, and `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` plus an on-disk session registry for persistence.

**And pick your VT parser deliberately, because the choice is narrower on Windows than it looks and the census made it five times.** Every candidate needs a screen model for snapshots and scrollback even if the live path ships raw bytes, and here is what the field actually chose:

| Parser | Language | Who uses it | What you should know |
|---|---|---|---|
| **`vt100-psmux` 0.16.2** | Rust | psmux and qscreen, **independently** — qscreen's copy is a clean `cargo vendor` of the published crate, not a fork of psmux's directory | A screen model over Alacritty's `vte` 0.15; originally Jesse Luehrs' `vt100-rust`, patched and republished by `marlocarlo`. Two independent adoptions is the strongest track record in this table |
| **`vt100`** (upstream) | Rust | oly | The unpatched ancestor of the above |
| **`charmbracelet/x/vt`** | Go | quil | Carries a known upstream spec-compliance defect around 0x9C in UTF-8, already worked around downstream — see trap 2 |
| **`libghostty-vt`** | Zig | boo, Roost, **ghostel** | The only one with a shipped native-Windows consumer (ghostel's `src/ConPtyProcess.zig`), and whether that means libghostty-vt itself builds on Windows or that ghostel routed around it is Q21, one hour of reading |
| **`asciinema/avt`** | Rust | asciinema's own relay | Apache-2.0, 229 stars, and its **only** dependencies are `rgb` and `unicode-width` — no libc, no platform-conditional code anywhere. **It should therefore compile on native Windows. That is an inference from the dependency list and nobody has built it**, which makes it either the cleanest option here or an afternoon you lose finding out why not |

---

## The verification ritual

**A success message from the tool proves nothing.** "Session created", "daemon started", "attached" — none of these tells you whether the session survives the thing you care about surviving, whether the verbs work when no human is present, or whether the daemon is even a separate process. This is the same fallacy as trusting that a secret store is encrypted because its API returned success. The following is the minimum proof, and it applies to every candidate.

Start from a running daemon. These install lines come from each project's own documentation and **were not executed on a Windows machine in any pass** — verify them against current docs before pasting.

```powershell
# psmux        — winget install psmux.psmux            (or: scoop install psmux)
# Zellij       — winget install zellij-org.zellij      (or the v0.44.3 msvc .msi)
# rmux         — winget install Helvesec.rmux          (or: scoop install rmux / choco install rmux)
# herdr        — download the dated preview asset: tag preview-2026-07-29-44b3adb12552,
#                asset herdr-windows-x86_64.zip   (NOT stable v0.7.5 — it has no Windows asset,
#                and the bare tag `preview-2026-07-29` does not resolve)
# wezterm-mux  — download WezTerm-windows-nightly.zip  (no current tagged release)
# OpenCode     — winget install anomalyco.opencode
```

**Step 1 — start a session, then kill the parent terminal outright.** Not "close the window", not Ctrl-C: kill it the way a crash kills it, because a graceful close lets a well-behaved child clean up and tells you nothing about detachment.

**Read this before you run it, or you will kill the terminal you are typing in.** `(Get-CimInstance …).ParentProcessId` from a pane inside Windows Terminal or ORCA returns the **host** process, and killing that host closes *every tab in that window* — including terminal B, from which you were about to run the kill. Launch terminal A as its own console host so the two are genuinely separate processes:

```powershell
# Terminal B (the one you keep) — launch terminal A as a SEPARATE console host:
$tool   = 'psmux'
$parent = Start-Process pwsh -PassThru -ArgumentList '-NoExit','-Command',"$tool new-session -d -s probe"
# NOTE for Zellij: there is no verified detached-start invocation. See the Zellij entry —
# `zellij --session X options --help` only prints help and creates nothing.

# Confirm the daemon exists BEFORE you kill anything — it is the thing under test:
Get-Process | Where-Object { $_.ProcessName -like "*$tool*" } | Select-Object Id, ProcessName, StartTime

# Now kill terminal A the way a crash would. No /T, no politeness:
Stop-Process -Id $parent.Id -Force
```

Do not use `taskkill /T`, which walks `ParentProcessId` and will kill a correctly-detached daemon anyway — that measures the process tree, not the design.

**The harsher variant is worth testing separately and knowingly, and worth describing accurately, because the usual description of it contains a claim this guide cannot support.** A parent that puts its children in a **Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`** tears everything down when the job handle closes — *unless* the child was created with `CREATE_BREAKAWAY_FROM_JOB` and the job permits it via `JOB_OBJECT_LIMIT_BREAKAWAY_OK`. So "regardless of how the child was created" is wrong: breakaway is exactly how a child escapes, and it is why **rmux spawns with `CREATE_BREAKAWAY_FROM_JOB`** and has an explicit refusal path rather than a silent degrade. (Note the constant's real name: `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. The bare `KILL_ON_JOB_CLOSE` that circulates is a grep string, not an API symbol.) And the frequent addendum — that this Job-Object teardown "is why Windows OpenSSH cannot host persistent sessions" — is **not established**: it rests on one maintainer sentence, and code searches for `CreateJobObject` and `KILL_ON_JOB_CLOSE` in openssh-portable return zero hits. What is established is that Windows sshd has no tmux equivalent. Why is not.

**Step 2 — open a fresh terminal, list, and reattach.**

```powershell
psmux ls          # or: zellij list-sessions / rmux ls / herdr list / wezterm cli list
psmux attach -t probe
```

If the session is still listed **and** re-attachable, it is L2 and it will survive the ADE. If it is listed but you cannot get back into it, the tool is a supervisor, not a session host. If it is gone, it is L1 — which is precisely what disqualified upterm, an otherwise excellent project with real ConPTY, Job Objects and the only public-key auth model in the census.

**Step 3 — drive a verb with no console attached at all.** This is the headless-first constraint stated as a test, and it is the step everyone skips. `zellij action`, `tmux send-keys` and `wezterm cli` are normally invoked from inside a terminal; whether they still function when a Scheduled Task, a Windows Service or a Claude Code hook invokes them with no console and no TTY on stdin/stdout is a different question, and **nobody has run it for any candidate.** It is disqualifying if it fails, because a middle layer you can only drive from a terminal is not a middle layer — it is a multiplexer. Two hours settles it for the whole field at once (Q23), which is why it is the cheapest disqualifier in this document.

**Run this PowerShell elevated.** `New-ScheduledTaskPrincipal -LogonType S4U` needs an administrative token to register, and the account needs the "Log on as a batch job" right. Getting either wrong produces an error at `Register-ScheduledTask`, which is at least loud.

```powershell
# Run every candidate's list verb from a console-less caller, as the SAME principal that
# owns the daemons, capturing both streams to a file.  ELEVATED PowerShell required (S4U).

New-Item -ItemType Directory -Force C:\probe | Out-Null

# 1. Resolve ABSOLUTE paths first. A Scheduled Task does not reliably inherit the *user*
#    PATH, and winget/scoop put all four of these under %LOCALAPPDATA%. Without this the
#    task reports CommandNotFound for everything and you conclude the whole field fails a
#    column it was never given a chance at. This guide documents the same class of failure
#    for sandbox-runtime: per-user installs "resolve on the inherited PATH but cannot be
#    opened by the sandbox account".
$bins = 'zellij','psmux','wezterm','rmux' | ForEach-Object {
    $c = Get-Command $_ -ErrorAction SilentlyContinue
    if ($c) { $c.Source } else { Write-Warning "not on PATH here either: $_"; $null }
} | Where-Object { $_ }
$bins   # sanity-check these are real absolute paths before continuing

$verbs = @(
    "& '$(($bins | Where-Object { $_ -match 'zellij'  }))' list-sessions"
    "& '$(($bins | Where-Object { $_ -match 'psmux'   }))' ls"
    "& '$(($bins | Where-Object { $_ -match 'wezterm' }))' cli list"
    "& '$(($bins | Where-Object { $_ -match 'rmux'    }))' ls"
) -join '; '
$cmd = "& { $verbs } *> C:\probe\out.txt"

# 2. Register as the same principal, domain-qualified so it is unambiguous on a
#    domain-joined machine.
$act = New-ScheduledTaskAction -Execute 'powershell.exe' `
       -Argument "-NoProfile -NonInteractive -Command `"$cmd`""
$pri = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U
Register-ScheduledTask -TaskName ProbeNoConsole -Action $act -Principal $pri -Force
Start-ScheduledTask  -TaskName ProbeNoConsole

# 3. WAIT for it to finish. A fixed Start-Sleep races the task, and a partial or empty
#    file reads as a failure under this test's own pass rule.
$deadline = (Get-Date).AddSeconds(60)
while ((Get-ScheduledTask -TaskName ProbeNoConsole).State -eq 'Running' -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
}
"final state: $((Get-ScheduledTask -TaskName ProbeNoConsole).State)"

Get-Content C:\probe\out.txt
(Get-ScheduledTaskInfo -TaskName ProbeNoConsole).LastTaskResult   # 0 does NOT mean it worked
Unregister-ScheduledTask -TaskName ProbeNoConsole -Confirm:$false
```

**Four rules for reading the result, and three of them are ways to avoid a false disqualification.**

- **An empty output file with a zero exit code is a failure, not a pass.** Read the file, never the return code: it must contain the session list you created from an interactive shell in step 1.
- **A `CommandNotFoundException` in `out.txt` is a PATH failure, not a console failure.** That is the single most likely wrong answer this test produces, and step 1 of the block exists to prevent it. If you see one, fix the path and re-run; do not record a disqualification.
- **Run it as the same principal *and* at the same integrity level.** Same user is not sufficient: rmux computes its pipe name from **SID *and integrity level***, so an elevated task probing daemons started from a non-elevated shell — or the reverse — is a guaranteed false negative **for rmux specifically**, and it will look exactly like a console-independence failure. Start the daemons and run the probe at the same elevation, or test rmux separately.
- **Be precise about what this proves.** A console-subsystem process launched by Task Scheduler is normally still given a console object unless it is created with `CREATE_NO_WINDOW`. What this test definitely establishes is **no TTY, no interactive window, non-interactive session** — which is the realistic shape of a hook or a service caller and is what the headless-first constraint is actually about. If you want the unambiguous version, wrap the verbs in a script that calls `FreeConsole()` first — the P/Invoke for it is in the [attach probe](#how-to-check-any-of-this-yourself) above — and compare the two results.

Those three steps are the minimum. Two more are worth the time if the candidate survives them:

**Step 4 — nest it, and time the spawn.** Run the candidate as an `agentCmdOverrides` target inside an ORCA pane — the shape of that override entry, and the three things to get right in it, are in [If you are wrapping under ORCA specifically](#if-you-are-wrapping-under-orca-specifically) — then resize the pane, run an alt-screen app and a mouse-mode app inside it (Q18). Then time the spawn, which is one line:

```powershell
Measure-Command { & psmux new-session -d -s timing ; & psmux kill-session -t timing }
```

**If that reports seconds rather than milliseconds, you have found the startup handshake problem** — ConPTY's DA1 query and its 3-second wait, which one measured data point took from 2121 ms to 142 ms by answering instantly. The quotes, the attribution (a third-party developer, not Microsoft) and the state of the thread they live in are under [The four things a middle layer must get right on Windows](#the-four-things-a-middle-layer-must-get-right-on-windows). A related failure is worse than slow: with `PSEUDOCONSOLE_INHERIT_CURSOR` set, the child can wedge inside process initialisation waiting for a CPR reply that never comes — hung **indefinitely**, with nothing in its logs and nothing to attach a debugger to.

**Step 5 — prove the resize path.** Resize the ORCA pane and check the size the session **actually reports**, from inside it. That is the same loop the mechanism section uses, run in the nested position rather than the outer one:

```powershell
# Run this INSIDE the nested session, then drag the ORCA pane border.
while ($true) { '{0}x{1}' -f [Console]::WindowWidth, [Console]::WindowHeight; Start-Sleep 1 }
```

There is no SIGWINCH on Windows; `ResizePseudoConsole(HPCON, COORD)` is an explicit call by whoever owns the handle, at every hop, so this loop is testing whether the call is being made on the inner hop at all. The specific thing to watch for is psmux's in-band sizing: it asks the outer terminal `CSI 18 t`, waits 500 ms, and **falls back to 120x30** if nothing answers — and whether Electron/xterm.js answers by default is unknown, because xterm.js gates `windowOptions` behind opt-in flags. **Numbers frozen at `120x30` are that fallback; numbers frozen at anything else are a missing `ResizePseudoConsole` call.** Either way every TUI inside then wraps against a size nothing on screen agrees with, which is a silent-corruption-class bug rather than a cosmetic one. It is Q4, it costs an hour, and it is the fastest way to turn an unknown into a fact.

---

## Open questions

Twenty-six questions, each with a concrete next step, a cost, and what the answer changes. The first tier can each eliminate whole branches; the last tier is due diligence you pass before shipping, not a discriminator between candidates.

**On the order.** The table below is grouped by *what an answer eliminates*, which is not the same as the order to run them in. The order to run them in is in [The running order, with wall-clock](#the-running-order-with-wall-clock) above, and it differs in one way worth stating here: **Q23 goes first, then Q1a, and Q9 starts in parallel on day one.** Q9 has the highest leverage of anything in this document and takes a week; Q23 takes two hours and can kill the entire PTY branch; Q1a takes two hours and can moot Q1 entirely. Two hours that eliminate eleven candidates beat a week that eliminates eleven candidates, and because Q9 is passive logging you do not have to choose.

**Tier 1 — answers that eliminate branches.**

| # | Question | Next step | Cost | What the answer changes |
|---|---|---|---|---|
| **1a** | **Can ORCA's `agentCmdOverrides` produce a raw-pipe child at all?** ORCA spawns through node-pty, i.e. always a ConPTY, and the documented `-CC` remedy is "give the child raw pipes". Ask whether the cure exists before measuring the disease | Read ORCA's spawn path from `tui-agent-launch-command.ts` through to the node-pty call; check whether any override shape bypasses the PTY | 2 hours | **Yes →** Q1 is worth running and `-CC` stays in play. **No →** `-CC` control mode is unreachable in this topology whatever Q1 finds; psmux drops to its plain CLI verbs and the "strongest interface" claim does not apply to you |
| 1 | Does ORCA's node-pty ConPTY actually corrupt `-CC` control mode, as psmux's source warns for the SSH case? | Run `psmux -CC` as an `agentCmdOverrides` target in ORCA and diff the `%output` stream against the same command run from a raw-pipe parent | One afternoon | **Corrupted →** apply 1a's remedy or drop `-CC` for CLI verbs plus polling. **Clean →** the SSH-scoping in the source was literal, the hazard does not generalise, and psmux's control mode is the best interface available to you |
| 9 | **Is the no-PTY architecture sufficient for your actual sessions?** `claude -p --input-format stream-json` plus HTTP hooks plus OTel covers everything except live screen fidelity and a human typing mid-run. **This is the highest-leverage item here** | Instrument one week of real work: count sessions where you actually attached and typed mid-run against sessions you only observed | One week, passive | **Sufficient →** stop evaluating multiplexers; build on pipes and hooks, and the PTY-ownership problem disappears entirely. **Not sufficient →** you have a measured number for how often you need attach, which is the input to every remaining trade-off |
| 3 | Does Zellij's `use_vt_path()` gate hurt inside an ADE PTY? It selects the native-console path when neither `TERM` nor `WT_SESSION` is set. **There is currently no pass/fail criterion** — nobody knows what the failure would even look like | Launch Zellij under an ORCA pane, record the observable behaviour (keyboard responsive? input garbled? fine?), then re-test with `TERM=xterm-256color` forced | 1 hour | **Broken →** one env var in the override command fixes it, and Zellij stays the most mature candidate. **Fine →** the most-cited hazard in three editions of this research was never real |
| 23 | **Do any candidate's verbs work with no console attached?** Every headless-verbs claim is untested against a genuinely console-less caller — a service, a Scheduled Task, or a hook. This is the headless-first constraint stated as a test | Invoke `zellij list-sessions`, `psmux ls`, `wezterm cli list` and `rmux ls` from a Scheduled Task running with no console, capturing stdout/stderr to a file | 2 hours | **Work →** the whole headless-verbs column becomes trustworthy. **Fail →** those candidates are terminal tools, not middle layers, and the no-PTY architecture wins by default |

**Tier 2 — answers that pick between surviving candidates.**

| # | Question | Next step | Cost | What the answer changes |
|---|---|---|---|---|
| 2 | What does herdr's "Direct terminal attach \| unsupported" mean, given the **same page** lists "Local persistent sessions" and "Windows Terminal / PowerShell app attach" as **Supported (beta)**? Demoted from top priority because the two tables together suggest it is the Unix fd-passing path, not the ADE-spawn path | Read `src/api/`, `src/ipc.rs` and the Windows-beta doc's surrounding sections; if ambiguous, file one question on the repo | 2 hours | **Unix-only mechanism →** herdr is a live candidate with a 23k-star maintenance base. **The ADE path →** herdr is out on Windows until the beta lands |
| 8 | Can `wezterm-mux-server` be driven headlessly end to end on Windows — `spawn`, `send-text`, `get-text`, `list`, with a client attaching later? | Install the nightly Windows zip, run `wezterm-mux-server --daemonize`, drive it with `wezterm cli` only | Half a day | **Yes →** you get the only version-skew-tolerant codec available, at the price of tracking a nightly. **No (attach needs the GUI) →** the codec remains a design reference only |
| 4 | Does Electron/xterm.js answer XTWINOPS `CSI 18 t`? | Read xterm.js `windowOptions` defaults; then empirically resize an ORCA pane and check the reported size inside psmux | 1 hour | **Answers →** psmux's in-band sizing works and resize is solved. **Does not →** psmux silently runs at 120x30 forever, which is a silent-corruption-class bug, not a cosmetic one |
| 10 | Is `ao pty-host` extractable as a standalone package? Apache-2.0 makes vendoring clean and it is the closest architectural match found | Try `go build ./backend/internal/adapters/runtime/conpty/...` outside the AO tree and see what it drags in | 3 hours | **Clean →** you have a working detached-ConPTY host to build on rather than write. **Entangled →** it is a design reference and you write your own |
| 12 | Do OpenCode's `/pty` endpoints work on native Windows with the shipped binary? | `opencode serve`, then `POST /pty` plus a WS connect from PowerShell | 1 hour | **Work →** a REST+WS attach surface with a resumable cursor exists today — but note it is L1+, not L2, and the wire is UTF-8 text. **Fail →** the protocol is still worth copying |
| 18 | Do any candidates run correctly nested inside a second ConPTY? **Nobody has tested this, including oly** — whose "nested agent tests" turned out not to exist | Run each under an ORCA pane with a resize, an alt-screen app, and a mouse-mode app | One day for all four | Whichever survives is your candidate. This is the single largest untested area |
| 24 | Can any candidate's prefix key be **disabled entirely** on a headless path, not merely rebound? Only docker documents remapping; every multiplexer's rebindability is an inference | For each of psmux, Zellij, rmux: find the config key, set it to none, and verify no chord is intercepted | 3 hours | **Yes →** prefix collision with the ADE stops being a concern. **No →** you inherit a keybinding negotiation with every ADE you ever swap to, which is exactly what this project exists to avoid |

**Tier 3 — soundness and due diligence before adoption.**

| # | Question | Next step | Cost | What the answer changes |
|---|---|---|---|---|
| 6 | Is psmux's `cross_session_server.rs` path reachable in practice? It accepts the first connection with no handshake, **registers it as a tee writer so it receives all pane output**, and writes everything it reads into the ConPTY — full-duplex exfiltration plus injection on a loopback port | Trace every call site of `cross_session_server`, or attempt a proof-of-concept connect during a cross-session pane move | 3 hours | **Reachable →** psmux is unsafe on a shared or multi-user machine until patched; report upstream. **Unreachable →** it is latent, and still a reason to pin and watch |
| 7 | Does quil's Windows ConPTY stack actually work? 25+ Windows source files, ubuntu-only CI, zero external issues ever filed | Run its test suite on Windows; add a `windows-latest` job locally and see what breaks | Half a day | **Works →** you get the richest agent-facing surface available (18 MCP tools). **Breaks →** the MCP surface is a design reference only |
| 13 | Does oly's named-pipe ACL gap still exist, or was it closed without updating the roadmap doc (untouched since 2026-03-12)? | Diff `src/ipc.rs` across the full commit history for any ACL or security-descriptor change; or ask the maintainer | 1 hour | **Closed →** oly's main disqualifier is gone. **Still open →** oly is unusable on any machine with another local account or a low-integrity process |
| 22 | Do the four small candidates have CVE/GHSA records? Only their own issue trackers were checked | One NVD/GHSA sweep before adoption sign-off | 1 hour | Either way this is a gate you pass before shipping, not a discriminator |
| 5 | Is `AttachConsole` reliable in the exact topology that matters — a process spawned inside a headless ConPTY created by node-pty inside Electron? | Write a 30-line helper that attaches to a `claude.exe` spawned by ORCA and calls `GetConsoleProcessList` | 2 hours | **Works →** you gain a read-only out-of-band inspection path. **Fails →** the late-attach refutation is complete and that door is closed permanently |
| 11 | Does `codex app-server --listen unix://` actually bind on Windows? The `uds` crate is cross-platform and the transport is registered unconditionally, but the daemon lifecycle manager is explicitly Unix-only | `codex app-server --listen unix://%TEMP%\test.sock` on Windows 11 and see | 30 minutes | **Binds →** a second vendor-native no-PTY architecture is available. **Fails →** Codex stays stdio-only on Windows |
| 14 | Is oly's `main`-branch stall (no commits since 2026-07-01, though four side branches are active) a stable plateau or a departed maintainer? | Watch for 4-6 weeks; check issue response latency | Passive | Affects only whether oly is worth adopting versus reading |
| 19 | Should the middle layer's control plane carry ACP over a Windows named pipe? The spec formally permits it and agent CLIs are converging on it — but ACP has no Windows CI and no live-process attach primitive | Prototype the transport shim against the reference implementation and see whether it builds and passes on Windows | Two days | **Builds →** the wrapper becomes protocol-native to the ecosystem it serves. **Fails →** use your own framing and revisit when ACP v2's terminal work lands |
| 17 | Has microsoft/terminal's in-process ConPTY redesign shipped, partially shipped, or stalled? | Cross-check against Windows Terminal changelogs and the ConPTY NuGet release notes | 1 hour | **Shipped →** the reflow/resize desync may be fixable rather than permanent. **Stalled →** plan around it |
| 15 | Would `kind` or a Hyper-V-backend Podman work end to end on Windows without WSL? Architecturally plausible from both projects' docs; **zero real-world confirmations located** | One hands-on spike: `podman machine init --provider hyperv` then `kind create cluster` | Half a day | Only matters if you want container isolation *around* the middle layer; it never replaces it |
| 21 | Does any libghostty consumer have a working Windows build today? ghostel says yes for its own ConPTY module — is that libghostty on Windows, or ghostel routing around it? | Read `src/ConPtyProcess.zig` in [`dakra/ghostel`](https://github.com/dakra/ghostel) and check what it imports | 1 hour | **libghostty →** a fourth VT-parser option opens up on Windows. **Routing around →** `avt` and `vt100-psmux` remain the only two |
| 25 | Can Eclipse Theia's backend be packaged and run headlessly on Windows? Its `base-terminal-server.ts:49` `async attach(id: number)` against a backend terminal registry is a second independent implementation of VS Code's `ptyHost` primitive, in a 21.6k-star EPL-2.0 project, and its shell process explicitly handles Windows (`shell-process.ts:90-91`) | Try to build and start Theia in server mode on native Windows and drive the terminal REST/WS surface with no browser attached | Half a day | **Works →** a second, better-licensed prior-art implementation becomes an actual option rather than a reference. **Fails →** it joins VS Code's `ptyHost` as prior art you read rather than run |
| 20 | Is there anything transferable in SCADA/industrial session tooling? Genuinely under-researched, not confirmed absent | One dedicated search round before writing the area off | 2 hours | Low expected value; recorded so the gap is not mistaken for a finding |
| 16 | Does the Windows Hypervisor Platform feature work on Windows 11 Home? No Microsoft doc states an edition requirement either way | Only resolvable empirically or by a Microsoft support statement | — | Low priority — the tool that needs it (`sbx`) is closed-source and already out on the open-source constraint |

---

## Coverage gaps

Stated plainly so nothing here is mistaken for verified, and **ordered by how much damage a wrong assumption does.** Inferences lead, because they are the items most likely to be read as facts. Declared unknowns beat silent ones.

**1. Inference presented as reasoning, never observed.** Each of these is a conclusion reached from verified premises. Each could be wrong without any of its premises being wrong.

- That a **foreign-SID console is not `AttachConsole`-able** (the `sandbox-runtime` incompatibility) — inferred from documented per-session console semantics, never tested.
- That the **session-0 boundary blocks `AttachConsole`** — same class, same status. It is commonly stated as established fact. It is not.
- That the **psmux `-CC` / ConPTY DCS hazard generalises beyond SSH**. The source scopes it to "when running over SSH with a ConPTY console"; the generalisation to a node-pty ConPTY is this document's, and Q1 exists to test it.
- That **`claude -p --output-format stream-json` behaves identically on Windows and Linux** — inferred from unqualified flag documentation over ordinary pipes. **This is the no-PTY route's load-bearing cross-platform claim and nobody has run it on both platforms.**
- That **`asciinema/avt` compiles on native Windows** — inferred from a two-crate dependency list (`rgb` and `unicode-width`) with no platform-conditional code. Nobody has built it.
- That **`eat` inherits Emacs core's Windows-pty gap.**
- That **Windows Job Objects are what kill sshd's children on disconnect** — asserted in one maintainer sentence, with **zero** code-search corroboration in openssh-portable.
- That the multiplexer candidates' **prefix keys are rebindable** — inferred from "they have config files". Only docker's `--detach-keys` is documented.

**2. Not tested empirically anywhere.** This is a source-and-docs map. Almost nothing in it has been run.

- **Double-ConPTY nesting**, by any candidate — including oly, whose supposed nested-agent tests were found not to exist.
- **Any candidate actually spawned by ORCA.**
- Whether `AttachConsole` reaches an ORCA-spawned agent.
- Whether **any candidate's CLI verbs work with no console attached** — the headless-first constraint has never been tested against a genuinely console-less caller.
- What the **observable symptom** would be if Zellij takes the native-console input path inside an ADE PTY — so Q3 currently has no pass/fail criterion.
- **The install commands** in this guide were assembled from each project's own docs; none was executed on a Windows machine.
- **The PowerShell probes** in [How to check any of this yourself](#how-to-check-any-of-this-yourself) are new code written for this guide. The Win32 semantics behind them are cited; the scripts themselves have never been run. The same is true of the `System.Net.WebSockets.ClientWebSocket` block for OpenCode's `/pty`, which is additionally written against an undocumented API whose request bodies and parameter names are guesses from the route handlers.
- **Zellij has no verified detached-start invocation anywhere in this guide.** `zellij --session X options --help` prints help and creates nothing, and no `-d` equivalent was located. This blocks step 1 of the verification ritual for the most mature candidate in the census.

**3. Not re-verified in any pass.** Believed, sourced once or not at all, never re-checked. Pruned to the items this guide actually leans on — a caveat you cannot attach to a sentence is noise.

- Zed's `agent_servers` ACP-shaped override — one of the four native-Windows ADE override hooks named in the opening section, and the only one of the four never re-verified.
- The closed-source ADE entries were never verified at source, by definition. Note what this does *not* cover: Warp's `crates/local_control` is in the AGPL-3.0 open-source client and **was** read at source; it is Warp's commercial product and its Oz cloud API that are unverified.
- **rmux's "936 of ~1000 commits" single-author statistic** — recorded once, never re-verified, and it is the load-bearing number behind the bus-factor argument in the Linux-parity tiebreak.
- **The rmux breakaway error string's file and line** ("breakaway process creation denied…") — the string is quoted from a source read once; the behaviour is verified, the pointer is not.
- **PowerSession-rs's missing-`ResizePseudoConsole` finding** — verified at source, but the file and line were not recorded and could not be recovered.
- ~~oly's `extract_query_responses_no_client`~~ — **resolved during this revision, and the claim it supported was wrong.** The symbol is in `src/session/pty.rs`; the function answers CPR, DSR and OSC 10/11 in detached mode and **explicitly refuses DA1**, which is the query behind the startup stall. "oly answers ConPTY's startup handshake" is corrected wherever it appeared.
- **cmux's L3 FAQ quote** and **ripple's `HANDOFF_GARBLING.md`** — both read once with no URL recorded. The ripple document is additionally **in Japanese**, so any English sentence attributed to it in this guide or elsewhere is a translation rather than a quotation.
- **The `build >= 22621` passthrough threshold** — corroborated by psmux and rmux converging on the same constant, but neither constant's file path was recorded, so the corroboration is not locatable from here.
- **The pywinpty maintainer's Jupyter Discourse post** (>30M downloads, "maintained by a single person") — quoted in the terminado entry, URL never recorded, never re-retrieved.
- **The LangChain agent-inbox `'response'` discriminator** — an API detail from one pass with no source, kept only because that route is in the non-multiplexer table.
- Several citations record a *method* (`gh api`, "README") rather than a retrievable object, and a handful resolve only to a repository rather than a line. The instances that matter are the ones enumerated above; the rest support claims nothing in this guide depends on.

**4. Never examined at all.**

- The **xterm.js `attach-addon` raw-bytes-over-WebSocket convention**, shared by ttyd, code-server and VS Code. This is the largest single hole in the protocol coverage — and the superlative usually attached to it ("arguably the most widely deployed…") is itself unverified.
- `chadbyte/claude-relay` and `myrialabs/ptykit` ("PTY sessions over WebSocket — collaborative rooms, resilient client, Node & Bun", 1 star, pushed 2026-07-30).
- ACP v2's terminal work; Codex's `stdio-to-uds` crate and its third `remote_control` transport.
- Whether any candidate other than herdr documents Windows prefix-key behaviour.

**5. Evidence that could not be retrieved.** Both blocked cases are the **same mechanism** — an Anubis-style proof-of-work interstitial that returns HTTP 200 with a "Making sure you're not a bot!" body, so a naive status check passes it.

- developer.valvesoftware.com — the Source RCON spec was not independently verifiable.
- gitlab.freedesktop.org — the canonical OSC 133 spec; triangulated from three implementer docs instead.
- The abduco/dvtm COSIN'18 slides did not extract.

**6. Coverage bounds worth stating.** The candidate pool came from GitHub topic and code search plus targeted follow-up. Anything not indexed by GitHub code search — self-hosted forges, unreleased internal tools, and non-English project descriptions beyond the handful encountered — is outside this survey's reach **by construction, not absent from the world**. Star counts and last-activity dates are a 2026-08-02 snapshot and churn weekly.

---

## Primary sources by category

**Microsoft ConPTY and console documentation.** [CreatePseudoConsole](https://learn.microsoft.com/en-us/windows/console/createpseudoconsole) · [ResizePseudoConsole](https://learn.microsoft.com/en-us/windows/console/resizepseudoconsole) · [AttachConsole](https://learn.microsoft.com/en-us/windows/console/attachconsole) · [WriteConsoleInput — the "no longer part of our ecosystem roadmap" banner and the separate wrong-way-verb tip](https://learn.microsoft.com/en-us/windows/console/writeconsoleinput) · [ReadConsoleOutput](https://learn.microsoft.com/en-us/windows/console/readconsoleoutput) · [Classic console vs virtual terminal — the "cross security and privilege-levels" framing](https://learn.microsoft.com/en-us/windows/console/classic-vs-vt) · [conpty-static.h — the current public ConPTY flag list](https://github.com/microsoft/terminal/blob/main/src/inc/conpty-static.h) · [winconpty.cpp — the only three `dwFlags` consumers in the implementation](https://github.com/microsoft/terminal/blob/main/src/winconpty/winconpty.cpp) · [microsoft/terminal doc/specs — home of #4999 improved keyboard handling and #13000 in-process ConPTY](https://github.com/microsoft/terminal/tree/main/doc/specs) · [CreateNamedPipe — a NULL security descriptor grants Everyone read access](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea) · [tscon — "You can't connect to the console session"](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tscon)

**Candidate source repositories.** [psmux](https://github.com/psmux/psmux) · [Zellij](https://github.com/zellij-org/zellij) · [rmux](https://github.com/Helvesec/rmux) · [herdr](https://github.com/herdrdev/herdr) · [oly / open-relay](https://github.com/slaveOftime/open-relay) · [qscreen](https://github.com/dualface/qscreen) · [quil](https://github.com/artyomsv/quil) · [WezTerm — `wezterm-mux-server` and the varint codec](https://github.com/wezterm/wezterm) (note the repository moved: `wez/wezterm` 301-redirects here; GitHub's licence API reports `NOASSERTION` and the file is `LICENSE.md`) · [OpenCode — `/pty` and `opencode serve`](https://github.com/anomalyco/opencode) · [Agent Orchestrator — `ao pty-host`](https://github.com/Untrivial-ai/agent-orchestrator) · [upterm](https://github.com/owenthereal/upterm) · [microsoft/node-pty — what ORCA uses](https://github.com/microsoft/node-pty) · [rprichard/winpty — the pre-ConPTY scraper, superseded](https://github.com/rprichard/winpty) · [NVDA — production late-attach reader](https://github.com/nvaccess/nvda) · [cc-discord-remote — the only working late-attach loop found](https://github.com/reubenlavin08/cc-discord-remote) · [anthropic-experimental/sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) · [PowerSession-rs](https://github.com/Watfaq/PowerSession-rs) · [dakra/ghostel — ConPTY under a swappable frontend, `src/ConPtyProcess.zig`](https://github.com/dakra/ghostel) (the repository is `ghostel`, not `ghostel.el`; the latter 404s) · [asciinema/avt — the VT parser with no platform code](https://github.com/asciinema/avt) · [Podman](https://github.com/podman-container-tools/podman) (`containers/podman` redirects here) · [Eclipse Theia — a second attach-by-id implementation](https://github.com/eclipse-theia/theia) · [ttyd](https://github.com/tsl0922/ttyd) · [sshx](https://github.com/ekzhang/sshx) · [code-server](https://github.com/coder/code-server) · [mobydeck/atch — the worked example](https://github.com/mobydeck/atch) · [Orc/screen — the preserved GNU screen beta-test README](https://github.com/Orc/screen) · [dtach](https://github.com/crigler/dtach) · [x3270 — headless scriptable emulator with `-httpd`](https://github.com/pmattes/x3270) · [warpdotdev/warp — `crates/local_control` in the AGPL-3.0 client](https://github.com/warpdotdev/warp)

**ADEs with a documented free-form command override** (the hook a middle layer needs). [ORCA — `agentCmdOverrides`](https://github.com/stablyai/orca) · [kandev](https://github.com/kdlbs/kandev) · [Pane](https://github.com/dcouple/Pane) · [Zed — `agent_servers`, ACP-shaped, never re-verified](https://github.com/zed-industries/zed) · [cmux — macOS only, and the census's only L3 claim](https://github.com/manaflow-ai/cmux)

**Field reports and third-party writeups** (weaker tier than a project's own documentation, and labelled as such wherever cited). [Laurent Kempe — multi-week psmux plus Copilot CLI on native Windows, the only external empirical corroboration in this research](https://laurentkempe.com/2026/03/31/from-3-worktrees-to-n-ai-powered-parallel-development-on-windows/) · [Galen Guan — when a multiplexer is essential infrastructure and when it is an unnecessary layer](https://guancyxx.cn/en/blog/tmux-skills-ai-agents) · [abduco/dvtm — "window and session management shouldn't be intermingled"](https://brain-dump.org/blog/abduco-dvtm-a-lightweight-alternative-to-tmux-and-screen/) · [OpenAI — "maintaining MCP semantics in a way that made sense for VS Code proved difficult"](https://openai.com/index/unlocking-the-codex-harness)

**Protocol and interface specifications.** [tmux(1) — CONTROL MODE](https://man.openbsd.org/tmux.1) · [WezTerm mux codec — varint framing built for version-skewed client/server pairs](https://github.com/wezterm/wezterm/blob/main/codec/src/lib.rs) · [WezTerm multiplexing — "Unix domains are supported on all systems, even Windows"](https://wezterm.org/multiplexing.html) · [Agent Client Protocol — transport-agnostic by spec, so ACP over a named pipe is conformant](https://github.com/agentclientprotocol/agent-client-protocol) (`zed-industries/agent-client-protocol` redirects here) · [Codex app-server README — websocket labelled experimental/unsupported](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md) · [MCP SEPs — zero terminal SEPs among 41 Final](https://modelcontextprotocol.io/seps) · [asciinema ALiS streaming protocol — relay holds full VT state for late joiners](https://docs.asciinema.org/manual/server/streaming/) · [nREPL — the narrow-waist design precedent that predates LSP](https://nrepl.org/nrepl/index.html) (the bare `nrepl.org` redirects here; the quoted passage is on this page, not the site root) · [Evennia documentation — the Portal/Server passage is on the *Portal-And-Server* page, not the docs landing page, whose URL was never recorded here](https://www.evennia.com/docs/latest/) · [Erlang distribution security — cookie auth is "not cryptographically secure"](https://www.erlang.org/doc/system/distributed.html) · [Claude Code hooks — five hook types, the SessionStart/Setup exclusion, `terminalSequence`](https://code.claude.com/docs/en/hooks) · [Claude Code CLI reference — `--input-format stream-json` and companions](https://code.claude.com/docs/en/cli-reference) · [Claude Code monitoring — the 34 `claude_code.*` identifiers](https://code.claude.com/docs/en/monitoring-usage) · [OpenCode server — "the TUI is the client that talks to the server"](https://opencode.ai/docs/server) · [docker attach `--detach-keys` — the only documented prefix remapping in the census](https://docs.docker.com/reference/cli/docker/container/attach/) · [Podman for Windows — the Hyper-V provider](https://github.com/podman-container-tools/podman/blob/main/docs/tutorials/podman-for-windows.md) · [minikube drivers — Hyper-V listed preferred (so is Docker; both carry the label)](https://minikube.sigs.k8s.io/docs/drivers/) · [Docker Desktop Kubernetes — the bundled cluster *is* kind or kubeadm](https://docs.docker.com/desktop/features/kubernetes/) · [oh-my-posh `shell_integration` — OSC 133 in cmd.exe via Clink v1.14.25+](https://ohmyposh.dev/docs/configuration/general)

**Issue-tracker threads, with their state disclosed.** [microsoft/terminal#7019 — DA1 3-second wait, "answer them", the ConPTY NuGet refusal-to-backport; **closed `not_planned` 2023-09-29**, maintainer comments continue after closure](https://github.com/microsoft/terminal/issues/7019) · [microsoft/terminal PR #17510 — "Goodbye VtEngine Edition", VT output now passed through unmodified; **merged 2024-08-01**](https://github.com/microsoft/terminal/pull/17510) · [microsoft/terminal#1173 — **closed `completed` two seconds after that merge**](https://github.com/microsoft/terminal/issues/1173) · [microsoft/terminal#19621 — passthrough breaks tmux control mode; filed by a Microsoft member, **open**](https://github.com/microsoft/terminal/issues/19621) · [microsoft/terminal#15976 — reflow/resize desync megathread, "this is a Hard problem"; **open**](https://github.com/microsoft/terminal/issues/15976) · [microsoft/terminal#17384 — >5 KiB paste deadlocks the terminal; **open since 2024-06-06**](https://github.com/microsoft/terminal/issues/17384) · [microsoft/terminal#17643 — residual VT-passthrough issues; **open** (cooked-read reflow, `ScrollConsoleScreenBuffer`, DA3 truncation and the PSReadLine SGR issue are **fixed**)](https://github.com/microsoft/terminal/issues/17643) · [microsoft/terminal#5468 — "no reason to ever use ReadConsoleOutput"; **closed `Resolution-By-Design` seven minutes after filing**](https://github.com/microsoft/terminal/issues/5468) · [PowerShell/Win32-OpenSSH#2291 — no tmux equivalent on Windows sshd; filed by a Microsoft member, **open**](https://github.com/PowerShell/Win32-OpenSSH/issues/2291) · [pywinauto#492 — the 2022 empirical late-attach attempt; **open since 2018**](https://github.com/pywinauto/pywinauto/issues/492) · [node-pty PR #886 — `AttachConsole failed` fix; **open, unmerged**](https://github.com/microsoft/node-pty/pull/886) · [node-pty PR #901 — Node 22 resize-after-exit; **open, unmerged**](https://github.com/microsoft/node-pty/pull/901) · [node-pty#921 — `ptyHandles` data race; **fixed 2026-05-13**](https://github.com/microsoft/node-pty/issues/921) · [node-pty PR #943 — conout worker deadlock, a regression of an already-fixed bug; **merged 2026-07-31**](https://github.com/microsoft/node-pty/pull/943) · [microsoft/vscode#201029 — the `kill()` root cause, still open](https://github.com/microsoft/vscode/issues/201029) · [openai/codex#25415 — the same crash in a shipping product; **open**](https://github.com/openai/codex/issues/25415) · [stablyai/orca#9586 — ORCA's own instance; **closed with zero comments, the diagnosis is the reporter's own**](https://github.com/stablyai/orca/issues/9586) · [openai/codex#11750 — the fragility of file-based IPC; **open**. Two separate sentences are usually spliced into one quotation here — see the non-multiplexer routes section](https://github.com/openai/codex/issues/11750) · [tsl0922/ttyd#1501 — the shipped Windows binary cannot spawn a child on build 26200; **closed 2026-03-19**](https://github.com/tsl0922/ttyd/issues/1501) · [anthropics/claude-code#24365 — `claude serve` request; **closed `not_planned`, stale-bot 2026-03-14, locked 2026-03-21**](https://github.com/anthropics/claude-code/issues/24365) · [anthropics/claude-code#6686 — ACP-over-network request, 551 reactions; **closed `not_planned` 2026-02-09**](https://github.com/anthropics/claude-code/issues/6686) · [awslabs/cli-agent-orchestrator#182 — the in-place TUI redraw that makes screen-scraping go stale; **closed as `completed` 2026-04-20**, so it proves the failure mode is real, not that any tool is broken today](https://github.com/awslabs/cli-agent-orchestrator/issues/182) · [zellij-org/zellij#4745 — the Windows rough-edges tracking issue; **open**, opened by `imsnif` (project lead), with `divens` (contributor) as its heaviest commenter](https://github.com/zellij-org/zellij/issues/4745) · [dagger/container-use PR #252 — "#242 added Windows compilation but no installation method"; **open since 2025-07-24**](https://github.com/dagger/container-use/pull/252) · [loft-sh/devpod#1946 — **open**, and the quoted sentences are the issue *body*, written by a third party (`skevetter`, no repository association) proposing his own fork, with his own hedge "it is fairly safe to say". **Not a maintainer statement** — the unhedged evidence of abandonment is the release date](https://github.com/loft-sh/devpod/issues/1946) · [tmux#5237 — why a nested layer cannot forward OSC 133; **open**, both quotes from maintainer `nicm` but from two separate comments](https://github.com/tmux/tmux/issues/5237) · [ENiGMA½#175 — "socket descriptors cannot be shared" in Node.js, solved with a Rust sidecar; **closed since 2018-12-09**](https://github.com/NuSkooler/enigma-bbs/issues/175) · [GNU Emacs bug#71472 — the ConPTY patch de-tagged 2025-02-12, dormant at wishlist severity](https://debbugs.gnu.org/cgi/bugreport.cgi?bug=71472)
