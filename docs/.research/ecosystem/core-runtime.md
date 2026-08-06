# Cluster: the core runtime

**Scope.** The eight repos we have already decided to adopt or sit next to: `culture`,
`agentirc`, `irc-lens`, `cultureagent` (PyPI-only), `agentfront`, `cultureflare`,
`culture-tools`, `org`. Read for **adoption**, not survey.

**Method.** `gh api` for repo metadata; PyPI JSON for maturity; shallow clones under
`/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/ac/`;
`culture` 14.5.0 installed from PyPI into `…/scratchpad/culture-venv` and **actually run**
against an isolated `HOME` (`…/scratchpad/fakehome`); the `PRESENCE` wire exercised with a
raw TCP socket (`…/scratchpad/p3.py`, `p4.py`, `p5.py`); doc sites scraped and every README
link status-checked.

Claims are **[OBSERVED]** (read in source, or produced by a live run recorded here) or
**[INFERRED]**. Where I ran something, the command and its output are quoted so the result
is reproducible rather than trusted.

This file assumes `docs/.research/fleet/agentculture.md` (the protocol read) and does not
repeat it. Where a live run **confirms or corrects** that file, it is called out.

---

## Verdict

- **The seam is smaller than we thought, and we proved it.** A 30-line stdlib TCP client
  that speaks `NICK` / `USER` / `PRESENCE :<json>` is a fully functional presence emitter.
  No SDK, no CAP negotiation, no auth, no bot capability, no `cultureagent`, no
  `agentirc-cli` import. **Our state driver's only hard dependency on this ecosystem is a
  socket.** [OBSERVED — `p3.py` produced a row visible in `culture residents --json`]
- **The wrong-answer failure our project exists to prevent reproduced on a stock install in
  under six minutes.** Client `culture-obs1` published `thinking`, then its process exited
  cleanly (kernel FIN, no `QUIT`). 90 s later: `{"nick":"culture-obs1","state":"thinking",
  "presumed_hung":true}`. The agent was **dead**; the mesh said **hung**. That is agentirc#55
  live, and it is our marketing case with a timestamp on our own machine. [OBSERVED]
- **The fix is one IRC verb, and it is the single most important operational fact in this
  file.** A controlled A/B on the same server: client `culture-modeA` sent
  `MODE <nick> +A` after registration, published `thinking`, then died identically → row
  flipped to `offline`. Without `+A`, `_emit_disconnect_events` never fires
  (`agentirc/ircd.py:769-771`). **Any connection we open must negotiate `+A` or it lies about
  its own death.** [OBSERVED]
- **`working` is accepted from any client — the hole is in the emitters, not the server.**
  Prior research said no backend emits it. Live: I published `{"state":"working"}` from a
  plain socket and it appeared in `PRESENCELIST` and in `residents.json`. Confirmed in
  `cultureagent`: `STATE_WORKING` is defined in `presence_emitter.py:35` and appears in **no**
  transition call across all five backends. **We can occupy `working` today, unilaterally,
  with nobody to collide with.** [OBSERVED]
- **Invalid states are dropped silently and the *stale row survives*.** Publishing
  `{"state":"waiting:permission"}` produced **zero bytes** of reply, and the prior `thinking`
  row remained with its original `since`. So a naive "just emit our seven states" integration
  doesn't degrade to unknown — it **freezes the dashboard on a stale truth**. The projection
  is not optional. [OBSERVED — corrects nothing in the prior read, but makes it concrete]
- **Nicks are server-namespaced and the server enforces it**: `:culture 432 * obs1
  :Nickname must start with culture-`. Open question 5 in the fleet research ("how does an
  agent we did not spawn get a stable mesh nick?") has a hard constraint: whatever we mint
  **must** be `<server-name>-<suffix>`. `<host>-<pid>` only works if the server is named
  `<host>`. [OBSERVED]
- **Two consumption surfaces, not one.** Besides the IRC wire there is `GET
  /residents.json` — served by `culture mesh overview --serve`, port discovered from
  `~/.culture/pids/overview-<name>.port`, adding three fields the wire does not carry
  (`token_budget`, `budget_used_pct`, `budget_warning`). `irc-lens` consumes exactly this.
  **A read-only fleet dashboard needs no IRC client at all.** [OBSERVED]
- **`culture` is a real, dense, working product; its documentation is not.** 161 PyPI
  releases, 112 stars, a 13-verb CLI that started an IRCd, a SQLite history DB and an audit
  JSONL on first run with zero config. But **five of the seven culture.dev links in its own
  README 404** (`/vision/`, `/ecosystem-map/`, `/choose-a-harness/`,
  `/agentirc/architecture-overview/`, `/reference/cli/devex/`). Trust the code; do not plan
  around the docs. [OBSERVED]
- **Windows is a hard stop at the daemon layer, not a soft one.** `culture server start` and
  `agentirc start` both `sys.exit(1)` with *"Daemon mode not supported on Windows. Use
  --foreground."* (`agentirc/cli.py:569-572`, `culture_core/cli/server.py:579`). This is worse
  than culture#262 implied — it is an explicit refusal, which is at least honest. Our ConPTY
  host + `schtasks` detach is genuinely ahead here, and **R1 (heterogeneous by default)
  cannot be satisfied by adopting their server process as-is on Windows.** [OBSERVED]

---

## Repos

| Name | What it actually is | Maturity | Docs | Intended use case | Verdict |
|---|---|---|---|---|---|
| **agentirc** (`agentirc-cli`) | The IRCd itself: RFC-2812 core + five server-side skills (history, icon, **presence**, rooms, threads) + S2S federation + a bot event bus. Extracted out of `culture` under a cite-don't-copy ledger. Ships an `agentirc` CLI with 12 verbs — `serve/start/stop/restart/status/link/logs/version/send/read/watch/join/bot`. **No presence verb on the CLI**; presence is wire-only. | PyPI **9.12.0**, **131 releases**, py≥3.11, Apache-2.0. Repo pushed 2026-07-15, 2 stars. 28 packages / 51 MB installed. | [README](https://github.com/agentculture/agentirc), [PyPI](https://pypi.org/project/agentirc-cli/), [layers doc](https://culture.dev/docs/architecture/layers/) | Run one IRCd per machine; federate them; agents connect as clients. | **ADOPT** — this is the wire and the daemon we build on; it is the smallest thing that gives us rooms, presence, history and federation for free. |
| **culture** | The integrated workspace CLI + the operator layer around agentirc. 13 top-level verbs (`agents server mesh channel bot skills devex afi console explain overview learn doctor residents`); several forward to other packages (`server restart/link/logs/serve` → agentirc, `agents doctor/show/overview` → steward, `devex` → agex, `afi` → agentfront, `console` → irc-lens). `culture server start` forks a daemon on 0.0.0.0:6667, creates `~/.culture/{pids,logs,data/history.db,audit}`. `culture residents [--json]` is the presence read surface. | PyPI **14.5.0**, **161 releases**, py≥3.12, Apache-2.0. 112 stars — the org's flagship. Repo HEAD `4a898b8` (2026-07-07) = the presence release. 71 packages / 97 MB installed. | [README](https://github.com/agentculture/culture), [culture.dev](https://culture.dev/), [quickstart](https://culture.dev/quickstart/) | Human/operator front door: create agents, start the mesh, read rooms, inspect residents. | **ADOPT (selectively)** — take `culture residents`, `mesh overview --serve` and `credentials.py`; do **not** take `culture agents start`, which is the self-reporting harness we are replacing. |
| **cultureagent** | The per-backend agent harness — five daemons (`claude`, `codex`, `colleague`, `copilot`, `acp`) over one shared `base_daemon` that owns the IRC transport, a supervisor, webhooks and the `PresenceEmitter`. Presence transitions live in `base_daemon.py` (`idle`/`listening` on dispatch, `draining` on shutdown) and in per-backend wrappers (`presence_thinking` around the LLM call). **`STATE_WORKING` is defined and never transitioned to, in any of the five.** | PyPI **0.13.0**, **30 releases**, py≥3.12. No public GitHub repo (`gh api repos/agentculture/cultureagent` → 404) — **PyPI-only, source unavailable except from the wheel**. | [PyPI](https://pypi.org/project/cultureagent/) only | Run a model backend as a resident IRC agent. | **WATCH** — it is the incumbent we out-measure, and the only place to read what their emitters actually do; but it is a competing answer to our question, and unauditable (no repo). |
| **irc-lens** | The web console: localhost aiohttp + HTMX + SSE, server-rendered fragments, Playwright-driveable. Its CLI/MCP/HTTP/TUI surfaces are all rendered from one `agentfront` registry so they can't drift (`irc-lens serve/join/mcp/tui/learn`). `web/residents.py` fetches culture's `/residents.json` and **classifies the outcome** — supported / unsupported / error — never raising. | PyPI **0.10.0**, **16 releases**, py≥3.12. Repo pushed 2026-07-15, 1 star. HEAD = *"residents presence page behind CF Access"*. | [README](https://github.com/agentculture/irc-lens), [PyPI](https://pypi.org/project/irc-lens/) | Look at the mesh in a browser; let an agent drive the console via Playwright/MCP. | **ADOPT (as a free UI)** — a fleet dashboard we do not have to write. `resolve_residents_url` + `fetch_residents` is also the exact degrade taxonomy we want to copy. |
| **agentfront** | An **importable runtime** (not a scaffolder): declare docs + tools once into an `App`, derive a CLI (with a `learn` verb), a minimal MCP server, and an HTTP markdown site with `/llms.txt` + sitemap. **Zero third-party deps** except the optional `mcp` extra. `agentfront cli doctor --strict` is a published rubric gate. | PyPI **0.20.0**, **16 releases**, py≥3.12. Repo pushed 2026-07-15, 1 star. Renamed twice (`afi-cli` → `teken` → `agentfront`). | [README](https://github.com/agentculture/agentfront), [PyPI](https://pypi.org/project/agentfront/) | Give any CLI tool a coherent agent-facing surface. | **WATCH** — the org's best reusable idea and a zero-dep way to give our driver an MCP surface later; but it is a presentation layer, and our JSON CLI contract already works. Not on the critical path. |
| **culture-tools** | Two things in one repo: (a) a tiny `culture-tools` CLI that is the *template* for an agent-first tool (`whoami/learn/explain/overview/doctor/cli overview`, all `--json`, exit codes 0/1/2), and (b) the Astro source for **tools.culture.dev**, a certification index gated on `agentfront cli doctor --strict`. | PyPI **0.6.0**, **5 releases**. Repo pushed 2026-07-27. Live index lists **3 certified tools** — `agentfront`, `colleague`, `culture-tools` — and 4 "roadmap" entries (`agtag`, `auntiepypi`, `cultureflare`, `devex`) with the rubric bundles they still fail. **Neither `culture`, `agentirc-cli` nor `irc-lens` is certified.** | [tools.culture.dev](https://tools.culture.dev/), [README](https://github.com/agentculture/culture-tools) | An index so an agent can discover conforming CLIs. | **IGNORE** — a three-entry index that does not list the org's own flagship. There is nothing here to consume. |
| **org** | The Astro source for **agentculture.org**, plus the same repo-local agent-first CLI template as `culture-tools` (literally the same verb table). Explicitly **not published to PyPI** — the deliverable is the site. Most recent HEAD in the cluster (2026-07-22) and the commit is *"real robot photographs replace all three placeholder slates"*. | Not on PyPI. Repo pushed 2026-07-22, 2 stars, Astro. | [agentculture.org](https://agentculture.org/) (200), [README](https://github.com/agentculture/org) | Marketing site. | **IGNORE** — a website. Useful only as evidence of where the org's attention is going (marketing, not the mesh). |
| **cultureflare** | An agent-first CLI for managing the org's **own Cloudflare** state — action-oriented verbs, dry-run by default, `--json` on every verb. Renamed from `cfafi`; ships a back-compat shim. Language is Shell/Python. | Repo pushed 2026-07-15, 2 stars. On the tools.culture.dev roadmap as **failing** four rubric bundles (`doctor, explain, json, overview`). | [README](https://github.com/agentculture/cultureflare) | Deploy and gate the org's own web properties (this is what puts irc-lens behind CF Access). | **IGNORE** — it is their infra-ops tool for their DNS. It has nothing to do with agent state, and we do not share their Cloudflare account. |

**Named-but-absent, since the brief listed the cluster by name:** `cultureagent` has **no
public repo** — only a PyPI distribution. Everything known about it comes from the installed
wheel. Treat its internals as unversioned-by-git and unauditable. [OBSERVED — 404]

---

## Adoption notes

### What we would install, per machine

Two options, and the cheap one is much cheaper:

| | `uv tool install agentirc-cli` | `uv tool install culture` |
|---|---|---|
| Packages / size | **28 / 51 MB** | **71 / 97 MB** |
| Gets you | the IRCd, federation, history, bots, `agentirc` CLI | the above **plus** `cultureagent` (5 backends), `irc-lens`, `agentfront`, `agex-cli`, `agtag`, `steward-cli`, and `culture residents` |
| Python | ≥3.11 | ≥3.12 |

Our drivers are stdlib-only Python 3.9+; **neither of these goes near them.** The IRCd is a
separate process, and our emitter is a socket. That separation is worth protecting: the
moment we `import agentirc`, we inherit a 3.12 floor and 27 transitive packages (grpcio and
protobuf among them) into a repo whose whole pitch is "drop it on a strange machine and it
works."

**Recommendation: install `agentirc-cli` only, per machine, and never import it.**
`culture` goes on *one* box as the operator/dashboard front-end.

### What we would run, per machine

```bash
# once per machine — the mesh node
uv tool install agentirc-cli
agentirc start --name $(hostname -s) --port 6667        # macOS/Linux
agentirc serve --name $(hostname -s) --port 6667        # Windows: --foreground only,
                                                        # detach with our schtasks path
```

Note `--name $(hostname -s)`: the nick namespace is derived from the server name, so naming
the server after the host is what makes `<host>-<suffix>` nicks legal.

### What our state detector plugs into

The whole integration, as proven:

```
prototypes/fused/driver.py state --id <id>
        │   {"state":"waiting:permission","evidence":[…]}
        ▼
  projection  (ours, declared, lossy — see Traps 1)
        │
        ▼
  TCP 127.0.0.1:6667
        NICK <server>-<suffix>
        USER <suffix> 0 * :<suffix>
        MODE <server>-<suffix> +A        ← REQUIRED. without it our death is invisible.
        PRESENCE :{"state":…,"since":…,"task":…}     every ≤30 s while busy
        ▼
  agentirc PresenceSkill  →  PRESENCE LIST / SEVENT presence.update to peers
        ▼
  culture residents --json  ·  GET /residents.json  ·  irc-lens /residents
```

Concretely, the observer is a new component in our repo — call it a **presence bridge** —
that: (1) polls `driver.py state` (or subscribes to it) per session; (2) applies the
projection; (3) holds one `+A` socket per observed agent; (4) re-emits every ≤30 s while in a
busy state; (5) sends `QUIT` on clean shutdown. Everything on that list is stdlib `socket`
and `json`.

### What it replaces vs. adds

**Replaces:** nothing of ours. Our seven states, evidence array, `conflict`, and JSON CLI
stay canonical. The bridge is an *export*.

**Replaces of theirs:** the `cultureagent` `PresenceEmitter`. Their emitter is in-process
with the agent and reports what the harness believes; ours is outside it and reports what
three fused channels prove. Notably we can emit `working` — which their contract defines and
none of their five backends has ever sent.

**Adds, for free:** rooms, message history (SQLite WAL, resumable `BACKFILL` cursors),
threads, a bot event bus with bounded queues, S2S federation, OTLP traces/metrics, a per-day
audit JSONL, and a browser console. That is a very large amount of fleet plumbing we do not
have to write, and it is the reason the adopt decision was right.

### What it costs

1. **A projection with declared coverage loss.** Seven states onto six, with two that have no
   honest target. Non-negotiable, because the alternative is a frozen stale row (Traps 1).
2. **A second transport for evidence.** `task` is 128 chars, the line is 512 bytes, and the
   emitter drops `task` entirely on overflow. `EVENTPUB` is the natural carrier but requires
   `CAP REQ agentirc.io/bot` — a plain client gets `EVENTERR e1 :bot-capability-required`
   [OBSERVED]. So the evidence path is a *second, differently-capability'd* connection, or
   an HTTP side-channel of our own.
3. **A heartbeat obligation.** ≤30 s per busy agent, forever, or their watchdog calls us hung.
   At 100 agents that is ~3.3 publishes/second of pure keepalive, and it is fail-open on our
   side (a network blip reads as a hang).
4. **A nick-minting policy** constrained to `<server-name>-*`, for agents we did not name.
5. **A Python floor if we ever import.** Don't. Keep the socket.
6. **A version floor.** Pre-9.12 servers answer `421 … PRESENCE :Unknown command` — which is
   exactly what I got before registration completed, so **`421` is ambiguous between
   "unsupported server" and "your client isn't registered."** Probe `VERBS` first and check
   `server_version` / the presence of `"PRESENCE"` in the verb list.

---

## Traps

1. **A rejected state does not clear the old one — it freezes it.** `PRESENCE
   :{"state":"waiting:permission",…}` returned zero bytes and the prior `thinking` row kept
   its original `since`. An emitter with a typo is not silent; it is a **liar with a
   plausible timestamp**. Whatever we emit must be in their six-value enum, and our bridge
   must assert that locally before sending. [OBSERVED]

2. **`MODE +A` or your row outlives you.** The A/B is unambiguous: same server, same clean
   exit, one row went `offline` and one stayed `thinking` → `presumed_hung: true` 90 s later.
   `_emit_disconnect_events` is gated on `"A" in modes` (`ircd.py:769-771`). This is
   agentirc#55, still open, and it will bite anyone who writes the obvious three-line client.
   [OBSERVED]

3. **`presumed_hung` is not a liveness signal and we must never re-import it.** It is
   `state ∈ BUSY and now − last_refresh > 90s`, computed at read time. On this run it fired
   for a process that had been *dead* for 90 seconds — the diagnosis was wrong, not late.
   Our `dead` stays grounded in process exit.

4. **`421 :Unknown command` is overloaded.** It is the pre-9.12 "unsupported" reply *and*
   the reply to any skill verb from an unregistered connection (skill dispatch is gated on
   `self._registered`, `client.py:390`). Culture's client maps `421` → `PresenceUnsupportedError`
   → `supported: false`, which means **a client with a registration bug silently reports the
   whole server as too old.** Probe `VERBS` before concluding anything.

5. **Nick rejection is a 432, and it happens before anything else works.** `:culture 432 *
   obs1 :Nickname must start with culture-`. If the server is named `culture` (the default!)
   and you name it after the host on machine 2, your nicks are not portable. Name servers
   deliberately and once.

6. **`task` is truncated server-side, not rejected.** I sent 400 `x`s; the row came back with
   exactly 128. So an oversized field fails *quietly and lossily* — the worst mode for
   anything carrying evidence.

7. **Windows: `culture server start` / `agentirc start` exit(1).** Literally *"Daemon mode not
   supported on Windows. Use --foreground."* An honest refusal, but it means the mesh node on
   a Windows box is **our** problem — foreground process plus our own `schtasks` detach.
   Do not let a fleet design assume `agentirc start` exists everywhere.

8. **The docs site is aspirational; 5 of 7 README links 404.** `/vision/`,
   `/ecosystem-map/`, `/choose-a-harness/`, `/agentirc/architecture-overview/`,
   `/reference/cli/devex/` all return 404. The two that resolve
   (`/quickstart/`, `/docs/architecture/layers/`) are themselves stale — `layers` documents
   `culture agent start` (the CLI verb is `agents`) and describes history as *"10,000 messages
   per channel, in-memory"* when the code ships SQLite WAL at `~/.culture/data/history.db`.
   **Read source, run the CLI, do not cite the site.**

9. **`residents.json` is not always there.** It exists only while `culture mesh overview
   --serve` is running, on an **ephemeral port** rediscovered from
   `~/.culture/pids/overview-<name>.port`. And each request opens a fresh IRC connection to
   answer. Fine for a dashboard; do not put it in a scheduling hot path.

10. **`cultureagent` has no repository.** PyPI-only, 404 on GitHub. Any behavior we depend on
    there is unversioned from our side and can change under us with no diff to read.

11. **Their supervisor is the thing we are replacing, and it is LLM-based.** Per the layers
    doc: *"A sub-agent watches the agent's activity and whispers corrections when it detects
    spiraling, drift, stalling, or shallow reasoning."* That is a model guessing about a
    model. culture#305 is what it costs. Do not mistake it for an observation layer.

---

## Reproduction

Everything above re-runs from the scratchpad:

```bash
S=/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad
export HOME=$S/fakehome
$S/culture-venv/bin/culture server start
$S/culture-venv/bin/python $S/p3.py    # register, VERBS, publish, bad publish, LIST
$S/culture-venv/bin/python $S/p4.py    # EVENTPUB gating, 400-char task truncation
$S/culture-venv/bin/python $S/p5.py    # MODE +A, publish, hard close
$S/culture-venv/bin/culture residents --json
```

The scratchpad is session-scoped. If these matter beyond this session, the three probe
scripts should be promoted into `docs/.research/empirical/` as a presence-wire conformance
harness — they are ~30 lines each and they are the only executable evidence we have that the
integration seam behaves as documented.
