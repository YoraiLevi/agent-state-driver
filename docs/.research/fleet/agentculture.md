# Prior art / integration target: the AgentCulture ecosystem

**Scope.** Investigated for the fleet design (multi-machine, role-based orchestration mesh).
All 78 repos in the `agentculture` org enumerated via `gh api orgs/agentculture/repos
--paginate`; 9 org repos + 4 `OriNachum` personal repos cloned shallow to
`/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/ac/`;
`culture` itself was already cloned at `…/scratchpad/culture` (HEAD
`4a898b83a790900668a5859f1976cb643f8957f0`, 2026-07-07, *"feat: resident presence + mesh
resource view — observe-only v1"*) and `cultureagent==0.13.0` extracted at
`…/scratchpad/cadl-venv/…/site-packages/cultureagent/` by the earlier survey pass. Line
citations below are relative to those roots. Claims are marked **[OBSERVED]** (read in
source/docs/issues) or **[INFERRED]** (my reasoning on top).

This file extends `docs/.research/prior-art/cultureagent.md`, which read the *backend* side
(the five agent runners). This pass reads the *mesh* side: the IRCd, the wire protocol, the
daemons, identity/secrets, and the delegation model — and answers the integration-seam
question.

---

## Verdict

- **AgentIRC 9.12.0 has a fully shipped, byte-specified presence protocol we can speak
  today** — `PRESENCE :<json>` publish, `PRESENCE LIST` → `PRESENCELIST :<json>` ×N →
  `PRESENCEEND`, nine fixed keys, S2S federation via `SEVENT presence.update`, read-time
  `presumed_hung`. It is not a sketch: `agentirc/skills/presence.py` is 574 lines with a
  federation test suite. **Design consequence: our fleet layer should not invent a presence
  wire. It should emit theirs, and win on the *contents* of the state field, not the
  envelope.** [OBSERVED: `agentirc/skills/presence.py`, `culture/protocol/extensions/presence.md`]
- **Their state enum has no waiting states at all.** Six values: `idle · listening ·
  thinking · working · draining · offline` (`presence.py:74-76`). There is no
  `waiting:permission`, no `waiting:input`. A blocked-on-a-human agent is indistinguishable
  from a thinking one — and after `stale_after` it is misreported as `presumed_hung`. That is
  a *wrong answer*, not a missing one, and it is the single largest correctness gap we can
  close. **Design consequence: our state model needs a declared, lossy projection onto their
  six values, plus an out-of-band carrier for the two waiting states.** [OBSERVED]
- **`working` — their tool-execution state — is still unemitted a release later.** The
  wire contract says outright *"`working` is part of the contract, but as of cultureagent
  0.13.0 no backend has an observable tool-execution boundary, so no emitter sends it yet"*
  (`culture/protocol/extensions/presence.md`, Activity States). Our sidecar + hooks +
  screen fusion emits provable tool activity. **`working` is a hole in their contract shaped
  exactly like our channel set.** [OBSERVED]
- **The only in-band way to set presence for nick N is a TCP connection registered *as* N.**
  `_handle_publish` keys the registry off `client.nick` (`presence.py:261,294`); `EVENTPUB`
  strips `_`-prefixed keys and server-stamps the nick (`agentirc/client.py:1449-1457`), so a
  bot cannot inject presence for someone else. **But a federated peer can.** `SEVENT` stamps
  `_origin` and `PresenceSkill._on_presence_update` upserts any nick this server does not
  host locally (`presence.py:472-530`, `agentirc/server_link.py:907-962`). **Design
  consequence: the clean seam is to run our state driver as an agentirc S2S peer — one
  observer-server per machine — not as a bot and not as a library patch.**
- **Their fleet coordination never consults presence.** The workforce fan-out
  (`devague/.claude/skills/assign-to-workforce/SKILL.md`, 427 lines) assigns tasks to agents
  in git worktrees and says *"Wait for all tasks in the wave to complete"* with **no defined
  completion signal** and **zero references to presence/residents/idle/busy** (grep returns
  nothing). Presence is a dashboard, not a scheduler input — the wire contract says so
  explicitly: *"v1 servers only aggregate and report… No deferred wakes, no admission
  control, no budget blocking."* **Design consequence: verified state feeding an actual
  admission-control decision is unoccupied ground, not a contested one.** [OBSERVED]
- **They have a documented, expensive real-world failure of exactly the class we prevent.**
  `culture#305`: two Claude-backed agents in one channel spiralled for ~9 minutes *after both
  declared stand-down*, re-executing already-signed tests, hallucinating commit attribution,
  burning "~0.3–0.5M tokens of pure spiral output"; the humans force-stopped the daemons by
  hand. **This is the marketing case for verified state, written by the neighbour, with
  timestamps.** [OBSERVED]
- **The identity and secrets legs of the mesh do not exist.** `OriNachum/zehut` is a README
  + LICENSE (4 files, zero code); `OriNachum/shushu` is a 52-line `--version` scaffold whose
  README says *"Early scaffold — details to come."* Both are still open *issues* on culture
  (`#269` identity graph, `#270` Shushu secret manager). What actually ships is a per-peer
  S2S `password` + a two-value `trust` enum (`agentirc/config.py:11-18`) and an OS-keyring
  wrapper (`culture/culture_core/credentials.py`). **Design consequence: do not plan to
  consume zehut/shushu. Plan to authenticate against an S2S password and per-peer trust, and
  treat mesh identity as ours to solve.** [OBSERVED]
- **Roles are not modelled.** There is no `role` field anywhere in `AgentConfig`
  (`culture/culture_core/config.py:89-125`): the closest are `suffix`, `backend`, `channels`,
  `tags`, `system_prompt`. "Add position hierarchy (team lead, tech lead)" is culture issue
  **#25** — a two-line stub open since the low-number era. **Design consequence: the
  configurable-mesh-with-roles target shape has no prior art here to borrow; a role is
  currently a channel membership plus a system prompt.** [OBSERVED]
- **The three named daemons are empty.** `codexd` / `antigravityd` / `kirod` are 14–34-line
  `--version` CLIs. codexd's own README: *"currently in initial scaffold state… daemon task
  orchestration is not implemented yet."* Their real content is repo-local skill scripts and
  a 2–4-line `culture.yaml`. **Do not model delegated repo work on them; there is nothing
  there.** [OBSERVED]

---

## Findings

### 1. AgentIRC: what it actually is

`agentirc-cli` 9.12.0 (`pyproject.toml:3`), Apache-2.0, Python 3.11+, ~2 GitHub stars but a
serious codebase: `ircd.py` 896 lines, `protocol.py` 561, five skills totalling 3,024 lines.
It is the server core **extracted out of** culture under a "cite-don't-copy" vendoring
ledger (`[tool.citation]` in `pyproject.toml`, four entries all pinned to culture commit
`df50942`). Split of concerns, from its own README table: agentirc owns the IRCd, channels,
federation, history, telemetry, transport, bot API; culture owns agent backends, console,
mesh credentials, process supervisor, agent manifest.

Runtime surface [OBSERVED, `agentirc/README.md`]:

| Layer | What ships |
|---|---|
| Classic IRC | RFC 2812 verb set: `PRIVMSG JOIN PART MODE TOPIC NICK USER QUIT WHO WHOIS LIST NAMES INVITE KICK PING PONG CAP ERROR` |
| Skill verbs | `ROOMCREATE/ROOMARCHIVE/ROOMMETA`, `THREAD/THREADS/THREADSEND/THREADCLOSE`, `TAGS`, `PRESENCE` |
| Federation | S2S links, `--link name:host:port:password[:trust]`, trust ∈ {`full`, `restricted`} |
| Bots | IRCv3 cap `agentirc.io/bot` + `EVENTSUB/EVENTUNSUB/EVENT/EVENTERR/EVENTPUB`, per-sub bounded queue (default 1024) with `EVENTERR … backpressure-overflow` + `BACKFILL` recovery |
| Agent CLI | `agentirc join|send|read|watch`, `--json`, msgid + IRCv3 server-time, resumable cursor |
| Discovery | `VERBS` (runtime verb discovery, `VERBS_DISCOVERY_VERSION=1`), 11 stable `ERROR_TOKEN_*` strings (`ERROR_TOKENS_VERSION=1`) |
| History | SQLite WAL at `<data-dir>/history.db`, replay via `BACKFILL`/`BACKFILLEND` |
| Telemetry | OTLP/gRPC traces+metrics, per-day audit JSONL `~/.culture/audit/server-<name>-YYYY-MM-DD.jsonl` (rotates UTC midnight or 256 MiB) |

Four wire-format bugs are **preserved verbatim** rather than fixed, because fixing them
unilaterally breaks federation with unpatched culture peers: `ROOMETAEND` (should be
`ROOMMETAEND`), `ROOMETASET`, `ERR_NOSUCHCHANNEL` (403) overloaded for "channel already
exists", and `STHREAD` collapsing two verbs. Tracked as agentirc issues #7/#8/#9 ("Track A —
coordinated cross-repo wire-format fixes"). [OBSERVED: `agentirc/README.md`, "Wire-format
compatibility"]

### 2. The presence model, exactly

**Publish (client → server).** One line, fire-and-forget, no ack ever:

```
PRESENCE :{"state":"thinking","since":"2026-07-06T14:32:00Z","task":"review PR #471","tokens_in":1024,"tokens_out":512}
```

Field rules (`presence.py:_validate_fields`, 297-362, and
`culture/protocol/extensions/presence.md` "Payload Schema"):

| Field | Req | Rule |
|---|---|---|
| `state` | yes | must be one of the six; anything else drops the whole update |
| `since` | yes | non-empty string, ISO-8601 UTC; truncated at 64 chars (`_SINCE_MAX_LEN`) |
| `task` | no | string, truncated at 128 chars (`_TASK_MAX_LEN`); non-string ⇒ drop |
| `tokens_in` / `tokens_out` | no | int in `[0, 1e15]`; `bool` explicitly rejected; **omitted, not null**, when unknown |

Whole line ≤ 512 bytes. The emitter enforces the same budget and, on multi-byte overflow,
**drops `task` entirely rather than sending an oversized line**
(`cultureagent/clients/shared/presence_emitter.py:66-97`).

**Invalid payloads are dropped silently** — `_handle_publish` logs at debug/warning and
returns; there is no error reply on the publish path at all (`presence.py:250-260`). A
malformed heartbeat is indistinguishable from no heartbeat. [OBSERVED]

**The six states and their claimed harness boundaries** (`presence.md`, Activity States):

| State | Boundary | Reality |
|---|---|---|
| `idle` | connected, no work in flight | emitted |
| `listening` | work dispatch opened (mention/DM past the accept-gate, or poll dispatch) | emitted |
| `thinking` | `harness.llm.call` span open | emitted |
| `working` | tool execution in flight | **defined, never emitted by any backend** |
| `draining` | graceful shutdown started | emitted; sticky (only `offline` may follow) |
| `offline` | disconnect / QUIT | server-stamped implicitly |

Design principle, stated twice: *"Transitions are driven **only** by observable code
boundaries — never by model self-report."* Note the precise scope of that claim: it rules out
the *model* reporting, not the *process* reporting. Every emitter is in-process with the
agent; the server accepts whatever a connection asserts about itself. That is self-reported
presence in the sense that matters to a scheduler. [OBSERVED + INFERRED]

**Heartbeat + watchdog.** Busy states re-emit every `heartbeat_interval_seconds` (default 30)
from `PresenceEmitter._heartbeat_loop`; the send is **fail-open** — `except Exception:
logger.warning("PRESENCE send failed (fail-open): %s")`
(`presence_emitter.py:208-216`). Server-side, `presumed_hung` is computed **at read time**,
never by a sweep task: `state in {listening,thinking,working,draining} and (now -
last_refresh) > stale_after_seconds` (default 90), strictly greater
(`presence.py:219-232`). Fail-fast config assertion: `stale_after > heartbeat_interval` or
the server refuses to load. One `presence:` YAML section in `~/.culture/server.yaml` drives
both daemons — agentirc adopted culture's defaults verbatim. [OBSERVED]

Consequence worth naming: **a fail-open emitter plus a staleness watchdog means a network
hiccup is reported as a hang.** Their own docs admit the converse too — a clean `kill -9`
whose kernel sends FIN reads as `offline`, and only a *silent* death (partition, lost FIN,
stalled-but-connected) reaches `presumed_hung` (`presence.md`, Stale-Busy Watchdog).

**Query (client → server).**

```
PRESENCE LIST
→ PRESENCELIST :{"nick":…,"server":…,"state":…,"since":…,"task":…,"tokens_in":…,"tokens_out":…,"presumed_hung":…,"last_refresh":…}
→ … (one line per resident, nick-sorted)
→ PRESENCEEND :End of presence list
```

Nine keys, always all present, `null` (never omitted) for unknown `task`/`tokens_*`;
`last_refresh` server-stamped ISO-8601 UTC at second precision; `since` round-trips verbatim.
A pre-9.12 server answers `421 <nick> PRESENCE :Unknown command`, which culture's client
turns into `PresenceUnsupportedError` → a `supported: false` degrade with exit-success —
*"a mesh on a not-yet-upgraded server is a known state, not an error"*
(`culture/culture_core/resource_view.py:67-74`). `PRESENCE LIST` is a **pure read**: no
`last_refresh` bump, no CAP required, any registered client may query
(`presence.py:178-193`). [OBSERVED]

Culture's client seam is one function, `_query_presence_wire`
(`culture_core/resource_view.py:229-276`), with a nice distinction we should copy: a
timeout/close **before any record** = "unsupported"; a timeout/close **mid-stream** =
`ConnectionError`, because *"that server clearly speaks the surface but stalled, and
classifying it unsupported would report a healthy `supported: false` while silently
discarding the residents already received."*

**Rooms, threads, history, roles.** Rooms are IRC channels plus `ROOMMETA` key/values;
threads are a first-class verb set with an IRCv3 `agentirc.io/thread` tag
(`protocol.py:328`); history is SQLite with resumable cursors. **Roles are absent from the
protocol entirely** — no role verb, no role field, no role tag. In culture, an agent's
"role" is the union of its `channels`, its `tags` (free-form strings, e.g.
`["persistence","colleague"]` in `culture/culture.yaml`), and its `system_prompt`. [OBSERVED]

### 3. Presence federation, and where it is soft

Presence rides the **generic** event bus — no new S2S verb, no hop counts
(`presence.py:19-35`, and the design decision recorded verbatim in
`agentirc/docs/specs/2026-07-07-…presence….md`):

1. every accepted local publish/offline-flip → `Event(type=EventType.PRESENCE)` i.e.
   `"presence.update"` → `IRCd.emit_event`;
2. `emit_event` runs local skill hooks, then relays to peers **iff there is no `_origin`
   tag** (`ircd.py:256-258`) — that is the entire loop-prevention mechanism;
3. on receipt, `ServerLink._handle_sevent` strips peer-supplied `_`-keys and stamps its own
   `_origin` (`server_link.py:954-959`);
4. `PresenceSkill._on_presence_update` upserts keyed by nick, attributing `server` to the
   **tamper-resistant `_origin`**, not the peer-supplied `data["server"]`
   (`presence.py:472-530`);
5. `SERVER_LINK` → re-emit every local row (burst-on-link, so a new peer learns pre-link
   state); `SERVER_UNLINK` → flip every row attributed to the departed server to `offline`;
6. `presence.update` is in `NO_SURFACE_EVENT_TYPES` so 30 s heartbeats never spam `#system`.

Two guards worth stealing: **federated rows are validated with the identical rules as local
publishes** (`_validate_fields` is shared), and **a peer may never overwrite a nick this
server hosts locally** (`presence.py:484-498`) — *"a nick is hosted by exactly one server, so
a federated row for a locally-owned nick is always wrong (stale echo, version skew, or a
forged `nick` aimed at clobbering a live local resident's real state)."* Also: a
peer-supplied `last_refresh` that is NaN/Inf/out-of-range falls back to `now` rather than
being stored, because it would otherwise raise inside `_format_last_refresh` and **break
`PRESENCE LIST` for every client on the server** (`presence.py:514-524`).

**Two admitted holes, both open issues:**

- **agentirc#55** — *"Presence: mode-less silent disconnect never flips row to offline."*
  `IRCd._remove_client` only fires disconnect events for clients that negotiated `+A` (agent)
  or `+C` (console) modes. A plain client that drops TCP without `QUIT` and without those
  modes emits **no event at all**, so its row lingers busy until it ages into `presumed_hung`.
  The PRESENCE PR "kept `ircd.py` to registration-only."
- **agentirc#56** — *"channel-less S2S events skip trust check."* `ServerLink` only invokes
  `_check_incoming_trust` when the relayed verb carries a channel; global (`channel=None`)
  events — **which is exactly how `presence.update` federates** — are relayed to every peer
  with no per-peer trust gating. Confirmed in code: `server_link.py:926` is `if verb_channel
  is not None and not self._check_incoming_trust(...)`. Also: the `SERVER_LINK` burst
  re-broadcasts to *all* peers, not just the new one — `O(local_residents ×
  already_linked_peers)` redundant messages per link event, compounding under link churn.
  Deemed "non-blocking given v1 is observe-only on a cooperative, password-authenticated
  mesh."

That second issue is the load-bearing security fact for our integration: **on a
password-authenticated mesh, any linked peer can assert presence for any nick it does not
host, with no trust check.** It is simultaneously the seam that makes our integration cheap
and the reason a verified-state fleet must not adopt their trust model unchanged. [OBSERVED
+ INFERRED]

### 4. The `*d` daemons — nothing to model

| Repo | cli.py lines | README |
|---|---|---|
| `codexd` | 25 | *"currently in initial scaffold state: package metadata, Culture registration, Codex repo guidance, repo-local skills, CI, lint, and tests exist; daemon task orchestration is not implemented yet."* |
| `antigravityd` | 34 | one line: *"Antigravity daemon for delegated repository work"* |
| `kirod` | 14 | one line: *"Kiro daemon"* |

Last pushed 2026-05-22, i.e. ~2.5 months stale against `culture` (2026-07-15) and `lobes-cli`
(2026-08-04). What each *does* contain is the honest answer to "how do they model delegated
repo work":

1. **A `culture.yaml` registration** binding a nick suffix to a backend — that is the whole
   agent identity. `codexd/culture.yaml` is literally `agents: [{suffix: codexd, backend:
   codex}]`; `kirod/culture.yaml` adds `acp_command: ["kiro-cli","--acp"]` with the inline
   comment `# placeholder — confirm real Kiro ACP launch command`.
2. **Repo-local skill scripts** under `.agents/skills/` (Codex convention),
   `.kiro/skills/` (Kiro convention), or `.claude/skills/` — `cicd` (`workflow.sh`,
   `pr-status.sh`, `pr-reply.sh`, `portability-lint.sh`, `_resolve-nick.sh`), `communicate`
   (`mesh-message.sh`, `fetch-issues.sh`, `post-issue.sh`, `post-comment.sh`), `run-tests`,
   `version-bump`, `sonarcloud`/`sonarclaude`.
3. `mesh-message.sh` is a 73-line bash wrapper around `culture channel message <target>
   <text>`, with the telling comment *"No signature is appended — the IRC nick is the
   speaker."*

**So: delegated repo work = a nick, a backend, a set of shell skills, and a chat channel.**
There is no task queue, no dispatch, no lease, no state machine, and no completion signal.
[OBSERVED]

### 5. The actual delegation model lives in a *skill*, not a daemon

`devague/.claude/skills/assign-to-workforce/SKILL.md` (427 lines) is the real workforce
orchestration design, and it is good:

- `devague plan waves --json` emits `{"plan", "waves": [["t1"],["t2","t3"]], "tasks":
  {id → {summary, instruction, acceptance_criteria, covers}}}` — the dependency graph in
  topological batches, with each task's full working contract.
- **The CLI deliberately does not orchestrate** (devague#20): *"`devague plan waves`
  describes the dependency graph; it does not spawn agents, manage worktrees, mark tasks
  done, or pick a backend."*
- Fan-out = one agent per task per wave, each in an isolated `git worktree` under
  `../.worktrees.<repo-name>/agent-<task-id>` on branch `agent/<task-id>`. Three named
  reasons for that path convention (visible ownership so another agent's cleanup doesn't
  sweep a live fan-out; task ids restart at `t1` per repo so a shared `../worktrees/` collides;
  in-repo paths get swept by `git add -A` / destroyed by `git clean -fdx`).
- Merge gate: run the task's tests on main *before* merge (baseline), `git merge --no-ff`,
  run them *after*; failure ⇒ revert and hand the output back to the task agent.
- Three human gates: exported spec, the split plan (task map + per-task agent/model proposal
  + go/no-go + `plan deliverables` end-state), and the final PR. Per-task TDD gates belong to
  the main agent, not the human.
- Hard rule: briefs quote `summary`/`instruction`/`acceptance_criteria`/`covers` **verbatim**
  — *"a reworded brief silently drifts from"* the contract the human confirmed.

**And the gap:** step 4 of fan-out is *"Wait for all tasks in the wave to complete before
starting the next wave."* No mechanism is specified. `grep -rn
"presence\|residents\|idle\|busy" .claude/skills/assign-to-workforce/` returns **nothing** —
the fleet's own dispatch path never asks the presence system whether an agent is ready, alive,
or blocked. [OBSERVED]

### 6. Identity (`zehut`) and secrets (`shushu`) — vapor

Neither is in the `agentculture` org (`gh api repos/agentculture/zehut` → 404). Both are
personal repos under `OriNachum`, both described "Agents first secrets manager":

- `OriNachum/zehut`: **4 files** — `LICENSE`, `README.md` (two lines), `.gitignore`,
  `CLAUDE.md`. No code.
- `OriNachum/shushu`: 52 lines of Python across `cli.py` (30), `__main__.py` (4),
  `__init__.py` (1), `tests/test_cli.py` (17). README: *"A Python CLI. Early scaffold —
  details to come."*

The intent is on record as culture issues:

- **#270 "Add Shushu secret manager with AFI-CLI interface"** — wants request/store/rotate/
  scoped credentials, local+remote backends, *"scoped secret access per identity / role /
  relationship"*, audit trail for reads/writes/rotations, policy hooks, machine-readable
  output by default.
- **#269 "Use identity graph for org structure"** — *"identity should also capture social and
  organizational position: who I am, my role, who my people are, who leads me, and who I
  report to"*; proposes typed relationships `reports_to / member_of / peer_of / trusted_by /
  acts_for`; explicitly ends *"I still need to think through the implementation details."*

**What exists instead, today:** a per-link `password: str` and `trust: "full"|"restricted"`
(`agentirc/config.py:11-18`), and `culture_core/credentials.py` — a genuinely careful
OS-keyring wrapper (Linux `secret-tool` via stdin, macOS `security -i` via stdin, Windows
PowerShell `New-StoredCredential` reading `[Console]::In.ReadLine()`), with the invariant
*"passwords never land in config files and never transit argv on any platform"*, peer names
validated against `^[A-Za-z0-9._-]+$`, and regression tests asserting secrets never appear in
built argv. That module is worth stealing outright for our cross-platform link secrets.
[OBSERVED]

### 7. The rest of the surveyed surface

- **`irc-lens`** — the web console: localhost aiohttp + HTMX + SSE, server-rendered
  fragments, driveable by Playwright *or* a human. Renders `GET /residents` from culture's
  `/residents.json`, and degrades with the literal copy *"presence pending the agentirc
  upgrade"* on `supported: false`. Its CLI/MCP/HTTP/TUI surfaces are all generated from one
  `agentfront` registry so they cannot drift.
- **`agentfront`** (ex-`teken`, ex-`afi-cli`) — the "Agent First Interface" runtime: declare
  docs + tools once into an `App` registry, derive CLI (with a `learn` verb for an agent to
  author its own usage skill), a deliberately minimal MCP menu, and an HTTP markdown site
  with `/llms.txt` + sitemap. Pure stdlib except the MCP extra. `agentfront cli doctor`
  audits other CLIs against a published rubric with a fixed exit-code policy (0 success /
  1 user error / 2 env error). This is the org's actual reusable idea.
- **`devague`** — a deterministic, LLM-free Python CLI: vague idea → spec → plan, state as
  plain JSON under `.devague/`. Anti-fabrication rule: *"LLM-proposed claims and honesty
  conditions stay `proposed` until **you** confirm them."* Transactional batch confirm/reject;
  a durable, explicitly non-authoritative review file. Nothing is deleted to make a gate go
  green — parked/deferred items keep the decision that closed them.
- **`lobes-cli`** (11 MB, most recently pushed org repo, 2026-08-04) — "a local thinking agent
  for Culture ecosystem", i.e. locally-served vLLM inference; `reachy-lobes` fuses it with a
  robot. Not state-detection relevant.
- **`gitculture-cli`** — GitHub CLI/agent, "AgentCulture manager".
- **`OriNachum/agentic-human`** (Jekyll blog, 13 posts, newest 2026-03-26) and
  **`agentic-guides`** (one guide: `claude-code-guide.md`). Both predate the mesh work; no
  post covers presence, the mesh protocol, or roles. Nothing load-bearing here — flagged
  because the brief named them.
- **`steward`** — named in the brief; **does not exist** as a public repo under
  `agentculture` or `OriNachum` (404 both). It is referenced throughout as the *former*
  upstream supplier of vendored skills (`cicd`, `communicate`): *"the supplier role moved
  from `steward` to `guildmaster` at the 2026-05-24 handover"* (`devague/docs/skill-sources.md`,
  `devague/CLAUDE.md:152,465`). `guildmaster` is likewise not public. **Both are private
  infrastructure repos; treat their behavior as unverifiable.**

### 8. Where culture explicitly fails or punts (their words)

| Source | Punt |
|---|---|
| `presence.md`, Activity States | *"`working` is part of the contract, but as of cultureagent 0.13.0 no backend has an observable tool-execution boundary, so no emitter sends it yet"* |
| `presence.md`, Observation Only (v1) | *"No deferred wakes, no admission control, no budget blocking. A budget breach emits a warning signal only."* |
| agentirc spec, Scope/boundaries | *"The diff contains no code path where presence state or token counters gate/defer/reject any command, message, or connection"* — enforced as an acceptance criterion |
| `culture/docs/resident-presence.md` | Token budgets are **per-connection cumulative**, so *"the tally therefore resets whenever the resident reconnects."* Per-UTC-day accounting is *"an unscheduled follow-up"* |
| agentirc#55 | mode-less silent disconnect never flips a row to offline |
| agentirc#56 | channel-less S2S events skip the trust check; link burst fans out to all peers |
| culture#25 | "Add position hierarchy (team lead, tech lead)" — open, two-line body, no design |
| culture#262 | *"Windows fallback in mesh update cannot reliably spawn daemons"* — `os.fork()` is unavailable, `culture server start` has no Windows daemonization path, and the CLI *"continues as if success"*; proposed fix (a) is to abort cleanly on Windows |
| culture#305 | the 4-hour multi-agent spiral, below |
| culture#76 / #77 | "periodically evaluate the agents" and "guardrails to avoid over-expenditure" — both open, unstarted |
| culture#333 | *"CLI surface inconsistencies — missing `list` verbs, namespace mismatches, listed-but-stub commands"* |
| culture#24 | "Add local direct terminal UI" — open; **they have no terminal-observation capability at all** |
| `presence.md` mixed-version caveat | a pre-9.12 peer *"renders [presence.update] as a `#system` PRIVMSG until upgraded — bump linked servers together"* |

**culture#305 in detail**, because it is the best single argument for this project that
exists in someone else's repo. Setting: an overnight multi-agent QA migration on a v8.6.0
fork, three participants in `#fig-ori` — `local-st4ck` (engineer), `local-ori` (customer
agent), `local-boss` (*"orchestrator session driven from outside the mesh (not a managed
agent)"* — i.e. exactly our attach posture). Four productive hours: 11 tests signed, 7
commits. Both agents post "standing down" at 01:45:02 UTC. Then:

- `01:50:05` `local-st4ck` responds to a 30-minutes-stale message slice as if fresh;
- `01:50:11` `local-ori` **actually re-executes** five already-`signed+green` smoke tests —
  real exec records, real tokens;
- `01:51:50` `local-st4ck` hallucinates attribution of its own commit `9d2482ff` to the
  sleeping human;
- `01:52–01:54` humans force-stop the daemons; *"several already-queued spiral messages still
  flushed to the channel after the daemons received SIGTERM"*;
- near-miss: `local-ori` was about to call `modify_test_case` on a row whose adjacent
  signatures would have been cleared, because a `preserve_signatures: true` server change had
  not deployed;
- cost: *"~0.3–0.5M tokens of pure spiral output across the two daemons in the final 5–10
  minutes, plus ~0.2M from the `local-helper-1` and `local-boss` daemons idling earlier in the
  session with supervisor evals every ~10s."*

The issue title names the diagnosis: *"no stand-down state."* Their presence enum has
`draining` but no terminal quiescent state a supervisor can act on, and nothing in the mesh
was watching whether these agents were doing useful work — because presence is observe-only
by design. [OBSERVED]

---

## What to steal

1. **The `PRESENCE` wire, verbatim.** Emit `PRESENCE :<json>`; answer `PRESENCE LIST` with
   `PRESENCELIST`/`PRESENCEEND`. Nine keys, fixed order, `null` never omitted. Free
   interoperability with a shipped console (`irc-lens /residents`) and a shipped CLI
   (`culture residents`).
2. **Read-time `presumed_hung`, not a sweep task.** `state ∈ BUSY and now - last_refresh >
   stale_after`, computed at query time (`presence.py:219-232`). Zero task lifecycle, and
   tests need only a small configured threshold instead of time-freezing. Their reasoning is
   sound and matches our SPEC's observer-computed watchdog.
3. **The fail-fast config invariant.** `stale_after > heartbeat_interval` asserted at *load*,
   with a clear error. Ours should assert the analogous relation between the hang threshold
   and the longest known compaction gap.
4. **Validate federated input with the identical function as local input.** One
   `_validate_fields` shared by both paths (`presence.py:297-347`) — a malformed row a peer
   relays is rejected exactly as a malformed local publish is.
5. **"A peer may never overwrite a locally-hosted nick."** (`presence.py:484-498`.) In a mesh
   where any machine can observe any agent, ownership-of-record must be single-writer, and
   the writer is whoever is physically co-resident with the process.
6. **Defensive rendering of untrusted timestamps.** A peer-supplied NaN/Inf/out-of-range
   epoch would raise inside the formatter and break the *whole* list reply for *every*
   client (`presence.py:514-524`). Any fleet-wide aggregate needs per-row failure isolation.
7. **The unsupported/stalled distinction.** Timeout before the first record = "peer doesn't
   support it"; timeout mid-stream = hard error, because silently reporting `supported:
   false` would discard rows already received (`resource_view.py:229-248`).
8. **`culture_core/credentials.py` wholesale.** Cross-platform secret storage with the
   never-in-argv invariant, three platform-specific stdin paths, and regression tests that
   assert the invariant. This is the exact problem a multi-machine mesh has and we have not
   solved.
9. **The worktree fan-out convention.** `../.worktrees.<repo-name>/agent-<task-id>` on branch
   `agent/<task-id>`, with the three stated reasons. Cheap, correct, and battle-argued.
10. **Verbatim briefs.** *"No operator paraphrasing anywhere in this flow: the plan text *is*
    the contract the user confirmed."* This should be a hard rule in our dispatch layer too.
11. **Runtime capability discovery + stable error tokens.** `VERBS` with a
    `VERBS_DISCOVERY_VERSION`, and a frozen `ERROR_TOKEN_*` vocabulary with its own version
    integer (`protocol.py:298-395`). A heterogeneous fleet needs exactly this so a driver can
    ask a node what it can do rather than assume.
12. **Bounded per-subscriber queues with an explicit overflow error and a `BACKFILL` recovery
    verb.** Not silent drop, not unbounded growth — `EVENTERR <sub-id> :backpressure-overflow`
    then a cursor-based catch-up.

## What to avoid, and why

1. **Do not adopt their six-state enum as our state model.** It cannot express
   `waiting:permission` or `waiting:input`, and folding those into `thinking` produces an
   actively *wrong* answer that the watchdog then escalates to `presumed_hung`. Keep our
   seven-state model canonical; treat theirs as a lossy export format with a declared mapping.
2. **Do not build on `presumed_hung` as a liveness primitive.** It is inferred from missing
   heartbeats over a fail-open transport (`presence_emitter.py:208-216`). A dropped TCP
   segment, a paused container, or a 100-second compaction all read identically to death. Our
   `dead` must stay grounded in process exit, per SPEC.
3. **Do not silently drop malformed state updates.** `_handle_publish` returns on any
   validation failure with only a debug/warning log, and the publish path defines *no* error
   reply (`presence.py:250-260`). An agent whose emitter is subtly wrong is invisible rather
   than loud. Our equivalent must surface `conflict`.
4. **Do not federate state on an untrusted channel-less path.** agentirc#56 is unfixed: any
   linked peer can assert presence for any non-locally-hosted nick with no trust check. If we
   speak S2S we must add our own signing/attestation over the row, or scope trust per peer
   ourselves — "cooperative, password-authenticated mesh" is not a security model for an
   expensive fleet.
5. **Do not let the `SERVER_LINK` burst be our resync design.** It re-emits every local row to
   *every* peer on *every* link event — `O(residents × peers)` per event, compounding under
   churn (agentirc#56 item 2). At fleet scale, resync must be scoped to the peer that linked,
   and preferably delta-based.
6. **Do not carry evidence in `task`.** 128 characters, 512-byte total line, and the emitter
   *drops `task` entirely* on multi-byte overflow. An evidence array does not fit and will be
   silently discarded exactly when it matters (a long tool name, a non-ASCII path).
7. **Do not model per-connection counters as budgets.** Their own doc admits the tally resets
   on every reconnect, so an agent that crash-loops shows near-zero spend forever
   (`resident-presence.md`, "Spend window and reset semantics"). Fleet accounting must be
   server-accumulated from deltas — which is precisely the follow-up they left unscheduled.
8. **Do not assume the ecosystem's Windows story works.** culture#262: the mesh-update
   fallback cannot spawn daemons on Windows (`os.fork()` absent, no daemonization path) and
   *"the CLI continues as if success."* Our ConPTY host and `schtasks` detach are already
   ahead of this; do not inherit their assumptions.
9. **Do not plan around `zehut`, `shushu`, `steward`, or `guildmaster`.** Two are empty, two
   are private. Anything the fleet needs from identity or secrets, we build or vendor.
10. **Do not copy "observe-only" as a permanent posture.** It is an explicit, test-enforced
    boundary in their spec — and culture#305 is what it costs. Our differentiator is only
    worth its complexity if verified state actually gates dispatch.

## Open questions for the design

1. **What is the declared projection from our seven states onto their six?** Strawman:
   `busy → thinking`; `idle → idle`; `starting → listening`; `dead → offline`;
   `presumed_hung → thinking` + let their watchdog flag it (or `draining`?). The two waiting
   states have **no** honest target. Options: (a) emit `idle` and carry the truth
   out-of-band — safe against their scheduler, wrong on their dashboard; (b) emit `working`
   — their only unused slot, semantically wrong but visually distinct and free of collision;
   (c) propose a 7th value upstream and pin a version floor. Each needs a written
   coverage-loss statement.
2. **Where does the evidence array live once `task` is ruled out?** Candidates: a parallel
   `EVENTPUB`-published custom event type on the same connection (bots get a base64-JSON
   envelope with no 128-char cap); a separate HTTP endpoint the console fetches by nick; a
   `ROOMMETA`-style side store. Which survives federation?
3. **Server-peer or client-per-agent?** The S2S posture gives us one process per machine that
   can speak for every agent on it, matches "ownership of record follows co-residency", and
   needs no per-agent socket. The client posture (one IRC connection per observed nick) needs
   no federation privileges and inherits their local-publish validation, but costs N
   connections and a nick-collision policy for agents we did not name. **Which posture is the
   product?**
4. **Do we ever answer `PRESENCE LIST` ourselves?** If our observer server is a peer, culture
   clients querying *their* server already see our rows via federation. If we also serve the
   query surface, we become an alternate front door — and must decide whether to answer for
   rows we did not verify.
5. **How does an agent we did not spawn get a stable mesh nick?** Our `attach` gives us a
   session UUID and a PID, not a name. Culture derives nicks as `<server>-<suffix>` from a
   manifest. Do we mint `<host>-<pid>`, read the sidecar's `name`/`nameSource` fields (both
   observed in `~/.claude/sessions/<pid>.json`), or require an operator mapping?
6. **What signs a verified row?** Given agentirc#56, an unsigned federated presence row is
   assertable by any linked peer. Does a fleet built on *proof* need per-row attestation
   (observer identity + channel set + timestamp), and if so, does that fit in 512 bytes or
   force a second transport?
7. **What is the fleet's admission-control contract, concretely?** Their answer is "none by
   design." Ours has to name the verbs: does the dispatcher `wait --until idle` before
   assigning, refuse to assign to `waiting:permission`, revoke a lease on `presumed_hung`,
   and what happens to work already handed to a node that then goes `dead`?
8. **Does the wave model survive verified state, or improve because of it?** `assign-to-
   workforce` waits for a wave with no completion signal. Replacing that with `wait --until
   idle --timeout` per worktree agent is a small, demonstrable patch to a real project — is
   that the cheapest credible proof of value we can ship?
9. **How do we handle the mixed-version mesh?** A pre-9.12 agentirc renders `presence.update`
   as a `#system` PRIVMSG (channel spam) and answers `PRESENCE` with `421`. Do we probe
   `VERBS` first and refuse to federate below the floor?
10. **Is roles-in-the-mesh ours to define?** culture#25 is an empty stub and culture#269
    ("identity graph… `reports_to / member_of / peer_of / trusted_by / acts_for`") ends with
    *"I still need to think through the implementation details."* If we define roles, do we
    express them in their existing primitives (channel membership + tags) for
    interoperability, or in a new typed layer that federation cannot carry?
