# AgentCulture ecosystem map — an adoption manual

**Audience:** whoever wires agent-state-driver into AgentCulture. Not a narrative — a lookup
table plus a build order.

**Sources:** the five cluster surveys under `docs/.research/ecosystem/` (`core-runtime.md`,
`agent-daemons.md`, `platform-services.md`, `domain-and-devices.md`, `philosophy-and-docs.md`)
and the earlier protocol read in `docs/.research/fleet/agentculture.md`. Every claim here is
traceable to one of those; where a survey marked something inferred or unverified, this file
carries the mark forward.

**Coverage:** 78 named repos across 77 table rows (`steward`/`guildmaster` share one row), of
which one — `reachy-nova` — turned out not to exist. Plus 4 in-repo doc artifacts. Nothing
appears twice.

---

## 1. Start here

1. **AgentCulture** (github.com/agentculture, ~78 repos) is one person's attempt to build an
   agent-first software ecosystem: an IRC-based mesh where agents are *members* with nicks,
   rooms, presence and history — plus a long tail of `teken`-scaffolded domain CLIs.
2. **`agentirc`** is the wire and the daemon. Our whole dependency on this ecosystem is a TCP
   socket speaking `NICK` / `USER` / `MODE +A` / `PRESENCE :<json>`. Nothing to import.
3. **`culture`** is the operator front-end wrapped around agentirc — take `residents`,
   `mesh overview --serve` and `credentials.py`; leave `culture agents start` (the
   self-reporting harness we replace).
4. **`agent-lifecycle`** is the ecosystem's process-supervision core, and its `HealthProbe` is
   a caller-supplied callable **nobody has written for a CLI agent**. That hole is our shape.
5. Everything else is IGNORE or WATCH. Three-quarters of the org is a code generator's output;
   check the command tree, never the README's problem statement.

---

## 2. The map

Maturity = PyPI version + release count where published; otherwise last push + whether real
code exists. "Docs" prefers the artifact actually read.

### 2.1 The mesh core — the wire, the operator layer, the console

| Repo | What it is | Maturity | Docs | Use case | Verdict |
|---|---|---|---|---|---|
| **agentirc** (`agentirc-cli`) | The IRCd: RFC-2812 core + 5 server skills (history, icon, **presence**, rooms, threads) + S2S federation + bot event bus. Presence is wire-only — no CLI verb for it. | **9.12.0, 131 releases**, py≥3.11, Apache-2.0; pushed 2026-07-15; 28 pkgs / 51 MB installed | [README](https://github.com/agentculture/agentirc) · [PyPI](https://pypi.org/project/agentirc-cli/) | One IRCd per machine, federated; agents connect as clients | **ADOPT** — the smallest thing that gives us rooms, presence, history and federation |
| **culture** | Integrated workspace CLI around agentirc: 13 verbs, several forwarding to sibling packages. `culture server start` forks a daemon on 0.0.0.0:6667 and creates `~/.culture/{pids,logs,data/history.db,audit}`. | **14.5.0, 161 releases**, py≥3.12; 112 stars (org flagship); 71 pkgs / 97 MB | [README](https://github.com/agentculture/culture) · [quickstart](https://culture.dev/quickstart/) | Operator front door: create agents, start mesh, read rooms, inspect residents | **ADOPT (selectively)** — `residents`, `mesh overview --serve`, `credentials.py`; **not** `agents start` |
| **irc-lens** | Web console: localhost aiohttp + HTMX + SSE, Playwright-driveable. `web/residents.py` fetches culture's `/residents.json` and classifies the outcome (supported / unsupported / error) without raising. | 0.10.0, 16 releases, py≥3.12; pushed 2026-07-15 | [README](https://github.com/agentculture/irc-lens) | Look at the mesh in a browser | **ADOPT (free UI)** — a fleet dashboard we don't write; its degrade taxonomy is worth copying |
| **cultureagent** | The per-backend harness: 5 daemons (claude, codex, colleague, copilot, acp) over one `base_daemon` owning IRC transport + `PresenceEmitter`. `STATE_WORKING` is defined and **transitioned to by none of the five**. | 0.13.0, 30 releases, py≥3.12. **No public GitHub repo** — PyPI-only, unauditable | [PyPI](https://pypi.org/project/cultureagent/) | Run a model backend as a resident IRC agent | **WATCH** — the incumbent we out-measure; the only place to read what their emitters do |
| **agentfront** (ex-`teken`, ex-`afi-cli`) | Importable runtime: declare docs + tools once into an `App`, derive CLI + minimal MCP + markdown HTTP site. Ships the seven-bundle agent-first rubric and `cli doctor --strict` as a gate. | 0.20.0, 16 releases, py≥3.12; zero third-party deps | [`docs/agent-first.md`](https://github.com/agentculture/agentfront/blob/main/docs/agent-first.md) · [`docs/rubric.md`](https://github.com/agentculture/agentfront/blob/main/docs/rubric.md) | Give any CLI a coherent agent-facing surface | **ADOPT the rubric, not the runtime** — our CLI already passes the hard bundles by accident |
| **culture-tools** | Two things: a template agent-first CLI, and the Astro source for tools.culture.dev, a certification index gated on `agentfront cli doctor --strict`. Lists 3 certified tools; **neither `culture`, `agentirc-cli` nor `irc-lens` is one of them.** | 0.6.0, 5 releases; pushed 2026-07-27 | [tools.culture.dev](https://tools.culture.dev/) | Index so agents can discover conforming CLIs | **IGNORE (consume) / WATCH (as a door)** — nothing to consume; it is the front door if we ever want listing |
| **org** | Astro source for agentculture.org + the same repo-local CLI template. Not on PyPI; deliverable is the site. | Pushed 2026-07-22 | [agentculture.org](https://agentculture.org/) | Marketing site | **IGNORE** — evidence of where org attention is going, nothing more |
| **cultureflare** | Agent-first CLI for managing the org's **own Cloudflare** state; dry-run by default. Failing 4 rubric bundles per tools.culture.dev. | Pushed 2026-07-15; Shell/Python | [README](https://github.com/agentculture/cultureflare) | Deploy/gate their own web properties | **IGNORE** — their DNS, not ours |

### 2.2 Supervision, delegation and planning — the fleet-adjacent cluster

| Repo | What it is | Maturity | Docs | Use case | Verdict |
|---|---|---|---|---|---|
| **agent-lifecycle** *(not in the original brief; **GitHub 404 — private**, PyPI only)* | Stdlib-only, harness- and transport-agnostic process lifecycle core: `Supervisor`, `ProcessSupervisor`, `RestartPolicy`, `ReadinessTracker` (one-way latch), `HealthThreshold`, `RuntimeObserver`. The health probe itself is `HealthProbe = Callable[[], Awaitable[object]]` — supplied by the caller. | **0.11.0, 22 releases**; 2,284 LOC in `runtime/`, ~24 test modules | [PyPI](https://pypi.org/project/agent-lifecycle/) · `docs/runtime-seam.md`, `docs/scope-charter.md` in the sdist | Spawn / crash-detect / restart / health-probe an agent process | **ADOPT** — closest thing to a worker-supervision contract in the ecosystem, and its probe seam is our output shape |
| **colleague** | A swappable coder-agent harness: typed `Task`→`TaskResult`, bounded tool loop, throwaway git worktree at operator HEAD on `colleague/<id>`, JSON artifact + append-only flight feed, `gh pr create` handoff (human is the reviewer). Also a real mesh resident (2,854 LOC under `resident/`) — **that emits zero `PRESENCE` lines**. | **1.53.0, 117 releases**; 60,390 LOC Python, 404 test files; pushed 2026-08-06 | [README](https://github.com/agentculture/colleague) · `docs/features/` (60 pages) | Delegate a scoped repo task to a different mind, get an auditable artifact back | **ADOPT (patterns) / WATCH (product)** — steal the flight plane, worktree convention, rig slot; it cannot observe foreign agents |
| **devague** | Deterministic, **zero-LLM-calls** CLI: vague idea → converged spec → converged plan with an acyclic task graph. `plan waves --json` emits topological batches. Per devague#20 it does not spawn agents or mark tasks done. | 0.22.0, 32 releases; pushed 2026-07-29 | [README](https://github.com/agentculture/devague) · `.claude/skills/assign-to-workforce/SKILL.md` | Produce the task graph a workforce executes | **ADOPT (as input)** — consume `plan waves --json`; its missing wave-completion signal is our demo |
| **league-of-agents** | Deterministic multi-agent strategy arena with fog of war; drives external agents as subprocesses (`command` = stateless per turn, `resident` = persistent session per seat). Scores a span-of-control axis. | 0.17.0, 28 releases; pushed 2026-07-15 | [README](https://github.com/agentculture/league-of-agents) · `docs/features/harness-and-drivers.md` | Benchmark whether agents cooperate under constraint | **WATCH** — its `resident` driver blocks on a live session with no readiness check (a consumer for us), but it is a game |
| **lobes-cli** | Local vLLM model server manager (run/assess/switch); serves cortex/senses/stt/tts roles via a `/capabilities` gateway. | 0.55.0, 53 releases; pushed 2026-08-04 | [README](https://github.com/agentculture/lobes-cli) | Local inference substrate under colleague | **IGNORE** — inference plumbing, no state/presence/dispatch concern |
| **codexd** | 25-line `--version` CLI + `culture.yaml` + vendored shell skills. README states *"daemon task orchestration is not implemented yet."* | 0.1.2, 3 releases; pushed 2026-05-22; **scaffold** | [README](https://github.com/agentculture/codexd) | *Intended:* Codex daemon for delegated repo tasks | **IGNORE** — self-declared unbuilt |
| **antigravityd** | 34-line CLI; `culture.yaml` uses `backend: acp` with `acp_command: ["antigravityd","serve"]` — a command absent from the repo. | 0.1.0, 1 release; pushed 2026-05-22; **scaffold** | [README](https://github.com/agentculture/antigravityd) | *Intended:* delegated work via Agent Client Protocol | **IGNORE** — only datum: ACP is their intended foreign-agent seam |
| **kirod** | 14-line CLI; `acp_command: ["kiro-cli","--acp"] # placeholder — confirm real Kiro ACP launch command`. | Not on PyPI; pushed 2026-05-22; **scaffold** | [README](https://github.com/agentculture/kirod) | *Intended:* Kiro daemon | **IGNORE** — admitted placeholder |
| **lecodeur** | ~766 LOC exposing `whoami`/`learn`/`explain` only. Described as "a local coding agent"; there is no coding agent. | 0.2.0, 2 releases; pushed 2026-07-15 | [README](https://github.com/agentculture/lecodeur) | *Intended:* local coding agent for the mesh | **IGNORE** — identity stub, superseded by colleague |
| **intern-cli** | Unmodified agent-repo template; the Bonsai 1-bit model wrapper the description promises is absent from the tree. README still says "this template." | 0.4.1, 2 releases; pushed 2026-07-18 | [README](https://github.com/agentculture/intern-cli) | *Intended:* cheap local ternary-model harness | **IGNORE** — template residue |
| **antoine** (`kata-cli`) | Codebase lookup/indexing (collapse N tool calls into 1) **plus** a real A/B eval harness with LLM-judge scoring. The verbs themselves are still template stubs. | 2.6, 5 releases; pushed 2026-07-15 | [README](https://github.com/agentculture/antoine) · `docs/eval-rounds/` | Cheaper repo comprehension for subagents | **IGNORE (one note)** — its finding that *subagents build plans from the prompt body before consulting the skills catalog* matters when we write dispatch briefs |
| **league-of-agents-platform** | Hosted AWS/SAM deployment of the arena (Lambda + DynamoDB + S3, OAuth, agent tokens, BYO-key). | Not separately on PyPI; pushed 2026-07-15, 3.2 MB | [README](https://github.com/agentculture/league-of-agents-platform) | Public benchmark site | **IGNORE** — hosting concern |
| **OriNachum/dev-agents** | 5 files: `.gitignore`, `LICENSE`, 2-line README, one `python-stack/.agent/` pair. | **Dead** — last push 2025-07-11 | [README](https://github.com/OriNachum/dev-agents) | "Workbenches repository of agents and code" | **IGNORE** — abandoned before the mesh work began |

### 2.3 Platform services — identity, secrets, memory, evidence

| Repo | What it is | Maturity | Docs | Use case | Verdict |
|---|---|---|---|---|---|
| **eidetic-cli** | Agent memory: `remember`/`recall`/`sweep`/`migrate` over `~/.eidetic/memory`; 4 recall modes, scope-aware (no private→public leak), never hard-deletes, pluggable file/mongo/neo4j. Culture commits its store in-repo. | **0.13.0, 20 releases**; pushed 2026-07-26 | [README](https://github.com/agentculture/eidetic-cli) | Perfect recall for one mesh-resident agent | **WATCH** — real and mature, but single-agent recall bound to `culture.yaml` identity, not fleet-wide state |
| **coherence-cli** | Five "coherence domains" (quality/meaning/signal/investiture/frames) scoring artifact trust/freshness/provenance; `quality` fully offline rule-based. | 0.6.1, 9 releases; pushed 2026-07-15; 18.6k lines | [README](https://github.com/agentculture/coherence-cli) · `docs/domains.md` | Should an agent trust / refresh / repair an artifact | **WATCH** — genuinely built, but scores artifacts, not agent liveness |
| **headspace-cli** | Ephemeral sandboxed execution workspace: 9-state lifecycle, closed-by-default policy, digest-pinned runtime profiles, Provider protocol (docker + in-memory fake), compact result packages. | 0.11.0, 5 releases; pushed 2026-07-30; 34.8k lines — largest in cluster | [README](https://github.com/agentculture/headspace-cli) | Offload computation out of agent context with provenance | **WATCH** — provider abstraction + digest pinning + crash reconciliation are reusable if we ever sandbox |
| **citation-cli** (OriNachum) | The "cite, don't import" tool: Quote/Paraphrase/Synthesize semantics, sha256 integrity (`cite check`), Python `[tool.citation]` + Node surfaces, `cite migrate` from `assimilai`. Docs-heavy, 661 LOC of CLI. | **0.1.0, 1 release**; 3 stars; pushed 2026-04-21 (~4 months stale) | [concept.md / python.md in repo](https://github.com/OriNachum/citation-cli) | Track cited code with a verifiable manifest | **ADOPT the format, IGNORE the tool** — 20 lines of TOML per vendored file beats a dependency |
| **agenda** (`agenda-cli`) | README promises GitHub issue/priority/blocker tracking; **`agenda/cli/_commands/` ships only the template's five verbs.** | 0.2.0, 3 releases; pushed 2026-07-15; **template-stage** | [README](https://github.com/agentculture/agenda) | Work-state tracking | **IGNORE** — README and shipped code disagree |
| **evidence-cli** | *"Documents the evidence trail… then grades it."* Same template-only tree as `agenda`; no scoring code present. Named here because it shares our vocabulary. | 0.6.1, 1 release; pushed 2026-07-23; **template-stage** | [README](https://github.com/agentculture/evidence-cli) | Evidence-trail scoring | **IGNORE (check before naming)** — worth a glance before we name our own evidence schema, to avoid a term collision |
| **zehut** (OriNachum) | Named "agents-first secrets manager" identity component. 4 files, 2-line README, **zero code**. | No PyPI package; unchanged across two survey passes | Repo README | Mesh identity graph (`reports_to`/`member_of`, culture#269) | **IGNORE** — nothing exists |
| **shushu** (OriNachum) | Named secrets manager. `cli.py` is ~30–52 lines, `--version` only. README: *"Early scaffold — details to come."* | 0.1.0 in pyproject, scaffold-only | Repo README | Scoped secret access per role (culture#270) | **IGNORE** — `culture_core/credentials.py` is the real secrets code in this ecosystem |
| **steward** / **guildmaster** | Referenced ecosystem-wide as the private supplier of vendored skill kits; the supplier role moved steward→guildmaster at the 2026-05-24 handover. | **404 on both orgs, confirmed across two independent passes** — genuinely private | None accessible | Skill-kit supplier for the org | **IGNORE** — unverifiable; do not plan around it |

### 2.4 Dev tooling and the generator

| Repo | What it is | Maturity | Docs | Use case | Verdict |
|---|---|---|---|---|---|
| **teken** | **The generator.** "Create Agent First products" — the `afi-cli`/python-cli scaffold every org repo cites in its README. | 0.20.0, 17 releases | [README](https://github.com/agentculture/teken) | Scaffold new agent-fronted CLIs | **WATCH** — explains why every repo looks identical; a 5-minute look if we ever want an operator CLI scaffold |
| **code-lens-cli** | Four inspection verbs (`classify`/`grep`/`recent`/`profile`); split off from `antoine`. Real, narrow. | 0.11.0, 7 releases; 7.2k lines | [README](https://github.com/agentculture/code-lens-cli) | One-call repo introspection for agent skills | **IGNORE** — no state/scheduling overlap |
| **qodo-cli** | Unofficial community wrapper for Qodo (AI code reviewer): `rules get`, `review`/`pr` via `gh`/`glab`, repo-level `.pr_agent.toml`. Zero runtime deps. | 0.11.0, 8 releases; 5.6k lines | [README](https://github.com/agentculture/qodo-cli) | Manage a review bot from the terminal | **IGNORE** — SaaS integration |
| **gitculture-cli** (ex-`ghafi`) | Bootstraps org sibling repos: create repo, scaffold the template, create `pypi`/`testpypi` GitHub Environments for Trusted Publishing. Every mutating verb dry-runs by default. | 1.0.0, 1 release; 3.5k lines | [README](https://github.com/agentculture/gitculture-cli) | Bootstrap new AgentCulture-pattern repos | **IGNORE** — their org convention |
| **agex** (`agex-cli`, OriNachum) | Non-agentic, deterministic markdown-first per-backend developer briefings (`agex overview --agent claude-code`). | **0.32.0, 33 releases** on PyPI (cloned repo's pyproject lagged at 0.13.1) | [README](https://github.com/OriNachum/agex) | Per-backend onboarding briefings | **IGNORE** — docs generator for their onboarding convention |
| **refactor-cli** | README claims an "atomic in-repo transformation engine"; ships only the template's five verbs. **And the PyPI name is squatted by an unrelated project.** | Never actually published by them; pushed 2026-07-15; **template-stage** | [README](https://github.com/agentculture/refactor-cli) | Behavior-preserving refactors | **IGNORE** — doubly unusable |

### 2.5 Guarded operation planes

Both are "policy gate + evidence contract between an agent's intent and a real side effect."
The only place in the long tail conceptually near us.

| Repo | What it is | Maturity | Docs | Use case | Verdict |
|---|---|---|---|---|---|
| **shell-cli** | Guarded local-ops plane: `Operation` model, policy evaluator, real `fs.*`/`process.*` execution, `--apply` mandatory for mutations. README opens *"A guard, not a sandbox"* — bypassable by `sh -c`, pipelines, any interpreter taking code as an argument; no namespace isolation. | 0.14.0, 7 releases; real `Operation`/`HostRunner` code; git/container runners unbuilt | [README](https://github.com/agentculture/shell-cli) · `docs/threat-model.md` | Safe local execution substrate under a harness | **WATCH (design reference)** — the `Operation → policy + preview → backend → result + evidence` lifecycle if we ever gate `send` payloads |
| **webglass-cli** | Guarded *web*-ops plane — spec only. README: *"Status: pre-implementation… none of these verbs exist yet."* | 0.5.0, 4 releases; ships only introspection | [README](https://github.com/agentculture/webglass-cli) + issue #1 | Safe web/browser execution substrate | **IGNORE for now** — revisit if it ships |

### 2.6 Device and domain agents — the long tail

All IGNORE. No repo here touches presence, state detection, or fleet scheduling. Listed so
nobody re-surveys them. Bold = confirmed built by tree inspection; *italic* = confirmed bare
`teken` stub; the rest are description + PyPI metadata only (**not tree-verified**).

| Repo | What it is | Maturity | Docs | Use case | Verdict |
|---|---|---|---|---|---|
| `jetson` | Agent+CLI for Jetson Thor/AGX Orin device ops | Not on PyPI; pushed 2026-07-15; Shell, 193 KB | repo README | Jetson device ops | IGNORE |
| *`jetson-orin-cli`* | **Bare stub** despite the name — six boilerplate verbs only, README still says "Make it your own" | 0.5.0, 2 releases | repo README | Orin provisioning (unbuilt) | IGNORE |
| **`jetson-thor-cli`** | Real domain code: `monitor.py`, `swap.py`, `machine.py`, `_probe.py` reading `/proc` | 0.5.0, 3 releases | repo README | Thor provisioning/ops | IGNORE — no hardware overlap |
| `jetson-arena` | Benchmarks a Jetson against a full VAD+STT+LLM+TTS stack; runs the public arena site | 0.6.2, 4 releases | repo README | Model-stack benchmarking | IGNORE |
| `jetson-ai-lab-cli` | Discord bot indexing Jetson AI Lab docs | Not on PyPI | repo README | Community support bot | IGNORE |
| **`dgx-spark-cli`** | DGX Spark workstation ops — real GPU/memory/thermal/disk/container/network telemetry | 0.7.1, 13 releases | repo README | Workstation health | IGNORE |
| `rtx-spark-cli` | Same shape for RTX workstations | 0.3.0, 4 releases | repo README | Workstation ops | IGNORE |
| `reachy-mini-cli` | Reachy Mini robot device/app/runtime ops. **Maturity outlier** — their most-released CLI | 0.47.0, **37 releases**; 5.2 MB; pushed 2026-08-03 | repo README | Robot device ops | IGNORE — but note it as the org's real flagship product |
| `reachy-mini-mcp` | MCP server controlling a Reachy Mini (server or sim) | 0.3.0, 3 releases | repo README | MCP robot control | IGNORE |
| `reachy-lobes` | Fuses `reachy-mini-cli` with a locally served vLLM for a fully local robot brain | 0.5.0, 1 release | repo README | Local robot cognition | IGNORE |
| `reachy-nova` | **404 — does not exist** under `agentculture` | n/a | n/a | n/a | n/a — flagged so nobody re-checks |
| `fleet-cli` | Multi-**drone** (UAV) coordination, built on `drone-cli` | 0.4.1, 2 releases | repo README | Drone swarm ops | IGNORE — **false cognate**, see Traps |
| **`sensibo-cli`** | Sensibo smart-AC control; heavily built (27 command files: schedule/rule/automation/mcp/service) | 0.7.1, 4 releases | repo README | Home AC automation | IGNORE |
| `webcam-cli` | USB webcam/mic capture: enumerate, stream, record | 0.9.0, 4 releases | repo README | Local media capture | IGNORE |
| `media-cli` | Local media I/O plane composing `webcam-cli`; owns routing/playback | 0.6.2, 2 releases | repo README | Media orchestration | IGNORE |
| `face-cli` | Browser-rendered pseudo-3D face for robot/kiosk gaze + expression | 0.7.1, 3 releases | repo README | Robot expression surface | IGNORE |
| `face-recognition-cli` | Face recognition/enrollment, extracted from `reachy-mini-cli`'s OpenCV engine | 0.8.0, 3 releases | repo README | Identity from camera | IGNORE |
| `harmonics-cli` | Non-speech audio (chimes/tones) mapped to agent intent/confidence/urgency | 0.8.0, 6 releases | repo README | Non-verbal agent→human signaling | IGNORE |
| `storybook-cli` | Helps an agent publish a shareable site recapping its work | 0.6.1, 2 releases | repo README | Work-summary publishing | IGNORE |
| `arxivist` | Fetches arXiv papers, maintains a KB, implements and benchmarks paper solutions | 0.2.0, 3 releases | repo README | Research-paper agent | IGNORE |
| `learn-cli` | CLI/MCP/web front for stepwise learning; fronts `spanish-cli`/`french-cli` | 0.7.0, 10 releases | repo README | Learning-domain front end | IGNORE |
| `spanish-cli` | Claude-driven private Spanish tutor with progress tracking | 0.7.0, 4 releases | repo README | Language tutoring | IGNORE |
| `french-cli` | Same shape, French | 0.6.0, 4 releases | repo README | Language tutoring | IGNORE |
| `telegram-agent` | Agent-first Telegram community management | 0.3.1, 1 release | repo README | Telegram community ops | IGNORE |
| `office-agent` | Office desk/meeting-room booking | Not on PyPI | repo README | Facility management | IGNORE |
| `tipalti` | CLI for the Tipalti payments platform | 0.5.0, 7 releases | repo README | Payments ops | IGNORE |
| `knowledgebase-cli` | Manages Amazon Bedrock Knowledge Bases (sources, ingestion, RAG retrieval) | 0.5.0, 4 releases | repo README | Managed-RAG ops | IGNORE |
| `data-refinery-cli` | Data quality (validation, dedup, freshness); split out of `eidetic-cli` | 0.12.0, 13 releases | repo README | Data pipeline hygiene | IGNORE |
| `unsloth-cli` | Wraps Unsloth for easier LLM fine-tuning | 0.6.0, 9 releases | repo README | Fine-tuning ops | IGNORE |
| *`tensor-cli`* | **Bare stub** — description says "tensor operations"; only the six boilerplate verbs exist | 0.3.0, 3 releases | repo README | Unbuilt | IGNORE |
| *`reduce-cli`* | **Bare stub** — description says "data reduction/aggregation"; six boilerplate verbs only | 0.3.0, 2 releases | repo README | Unbuilt | IGNORE |
| `prove-cli` | Theorem proving / formal verification CLI (**description-only, not deep-read**) | 0.4.1, 4 releases | repo README | Formal verification | IGNORE |
| `autonomous-intelligence` (OriNachum) | "Tau" — hand-built Raspberry Pi + Jetson voice/vision companion robot. Predates the org, not built on `teken`, no mesh identity | Not packaged; pushed 2026-04-08; **234 stars — his biggest** | repo README | Personal robotics hobby project | IGNORE — unrelated domain |

### 2.7 Doctrine, blog and community

| Repo | What it is | Maturity | Docs | Use case | Verdict |
|---|---|---|---|---|---|
| **claude-code-guide** (OriNachum) | A real Claude Code **plugin**: 7 skills (`ask`, `onboard`, `introspect`, `level-up`, `game-mode`, `migrate-to-claude`, `visualize-setup`), `hooks/hooks.json`, docs site. | **120 stars**; pushed 2026-06-17; real code | [README](https://github.com/OriNachum/claude-code-guide) | Gamified Claude Code onboarding | **WATCH** — the reference for his skills layout, and the highest-visibility place an upstream mention of us would land |
| **agentic-human** (OriNachum) | His blog. Jekyll, 13 posts, newest 2026-03-26. Load-bearing posts: *Code as Documentation*, *Everything is Agents*, *Workbench Development*, *Assimilai*. | 3 stars; **stale 4.5 months**; predates all mesh/presence work | [`_posts/`](https://github.com/OriNachum/agentic-human/tree/main/_posts) | Where the ideas were first argued in prose | **WATCH** — read once for vocabulary and quotes; mentions no presence or state |
| **BenevolentAgentsRFC** (**fork of** `agamrafaeli/…`) | A 4-human/4-agent WhatsApp experiment turned into RFCs: shared Upstash Redis registry, identity ("the human is the trust anchor"), "The Right to Write". He participates as the agent "otti", status *Pending*. | 0 stars; pushed 2026-04-08; **not his repo** | [`rfcs/`](https://github.com/agamrafaeli/BenevolentAgentsRFC/tree/main/rfcs) | Agent-to-agent cooperation without human mediation | **WATCH (one idea)** — RFC-0001 lists *"TTL / heartbeat for liveness detection"* as unbuilt. Evidence that liveness keeps getting deferred everywhere |
| **agentic-guides** (OriNachum) | A Jekyll shell containing exactly one 7-line guide. | 1 star; pushed 2026-03-13; **stub** | n/a | Guides site | **IGNORE** — empty |
| **community** (OriNachum) | **Fork**, 0 KB, upstream `STATE16-Physical-AI-Community`; last commit by another author. | Fork, no contribution of his | n/a | Not his project | **IGNORE** |
| **awesome-claude-code-security** (OriNachum) | **Fork** of `efij/awesome-claude-code-security`; his sole commit is *"Fix typo."* | Fork, 1 trivial commit, 2026-03-17 | [upstream](https://github.com/efij/awesome-claude-code-security) | Curated security list | **IGNORE as doctrine; WATCH upstream** — a decent reading list for our fleet-security workstream |

**Doc artifacts (not repos) worth reading in full:**

| Artifact | Why it matters | Verdict |
|---|---|---|
| `culture/protocol/extensions/presence.md` | The only normative spec in the ecosystem touching state: six values, field rules, *"transitions are driven only by code boundaries, never by model self-report"* (:45), *"a resident never self-reports its state"* (:61), and the observe-only-v1 boundary | **ADOPT** — the document our `waiting` PR argues against, line by line |
| `agentirc/docs/api-stability.md` | Names the seven public modules with semver contracts | **ADOPT** — tells us exactly what our integration may depend on; model for our own SPEC stability section |
| `agentirc/pyproject.toml [tool.citation]` | 470-line ledger: per-file source URL pinned to culture commit `df50942`, `quote`/`paraphrase`/`synthesize`, sha256, `notes` rationale | **ADOPT (format only)** |
| `culture/docs/superpowers/{plans,specs}` + `docs/specs` | 58 dated design docs, spec-then-plan, kept after shipping (2026-03-19 → 2026-07-07) | **ADOPT (the convention)** |

---

## 3. What we adopt, in order

Each step is independently useful. Stop anywhere.

### Step 1 — one mesh node per machine

```bash
uv tool install agentirc-cli            # 28 pkgs / 51 MB, py>=3.11
agentirc start --name $(hostname -s) --port 6667      # macOS / Linux
```

`--name $(hostname -s)` is load-bearing: the nick namespace derives from the server name, and
the server enforces it (`:culture 432 * obs1 :Nickname must start with culture-`). Naming the
server after the host is what makes `<host>-<suffix>` nicks legal.

**Windows** *(corrected 2026-08-06 — see §9 and windows-persistence-answer.md; `serve` works
natively, only `start` is refused)*: `agentirc start` and `culture server start` both `sys.exit(1)` with *"Daemon mode
not supported on Windows. Use --foreground."* Run `agentirc serve --foreground` under our own
`schtasks` detach. This is our problem, not theirs — see [What we keep building](#4-what-we-keep-building).

**Do not install `culture` per machine** (71 pkgs / 97 MB, py≥3.12) and **never `import`
either one**. Our drivers are stdlib-only Python 3.9+; importing inherits a 3.12 floor and 27
transitive packages including grpcio and protobuf, into a repo whose pitch is "drop it on a
strange machine and it works."

### Step 2 — probe the server before trusting it

```bash
# from any client, after registration completes:
#   VERBS       -> check "PRESENCE" appears and read server_version
```

`421 :Unknown command` is **overloaded**: it is both the pre-9.12 "unsupported" reply and the
reply to any skill verb from an unregistered connection. Culture's own client maps `421` →
`PresenceUnsupportedError` → `supported: false`, so a registration bug silently reports the
whole server as too old. Probe `VERBS` first; never conclude from a `421`.

### Step 3 — build the presence bridge (ours, ~150 lines, stdlib only)

New component in our repo, alongside `fleet/bus.py` / `roster.py` / `warden.py`. It:

1. polls `prototypes/fused/driver.py state --id <id>` per observed session;
2. applies the projection (below) and **asserts the result is in their six-value enum locally
   before sending**;
3. holds one TCP connection per observed agent;
4. sends `MODE <nick> +A` immediately after registration;
5. re-publishes every ≤30 s while in a busy state;
6. sends `QUIT` on clean shutdown, and simply closes on agent death.

```
NICK <server>-<suffix>
USER <suffix> 0 * :<suffix>
MODE <server>-<suffix> +A          <- REQUIRED. Without it our death is invisible.
PRESENCE :{"state":"working","since":<epoch>,"task":"<=128 chars"}
```

**The projection** (ours, declared, lossy — [INFERRED design, not observed upstream]):

| our state | agentirc value | note |
|---|---|---|
| `starting` | `listening` | connected, no work accepted yet |
| `busy` | `working` | the value they define and **no backend of theirs has ever sent** |
| `idle` | `idle` | exact |
| `waiting:permission` | `thinking` + `task` prefix | **no honest target.** `idle` would cause dispatch into a void; `thinking` at least withholds the agent |
| `waiting:input` | `thinking` + `task` prefix | same loss |
| `presumed_hung` | keep publishing `thinking` | their 90 s watchdog reaches the same label independently |
| `dead` | close the `+A` socket → `offline` | server-emitted, not published |
| `conflict` | **publish nothing** | hold the prior row; surface `conflict` on our own surface only |

Two states have no honest target. That is exactly the gap the `waiting` PR closes, and it is
the reason the projection must be declared rather than silent.

### Step 4 — one operator box

```bash
uv tool install culture                 # py>=3.12, 71 pkgs / 97 MB — ONE machine only
culture residents --json                # presence read surface
culture mesh overview --serve           # then GET /residents.json
culture console                         # forwards to irc-lens
```

`residents.json` carries three fields the wire does not: `token_budget`, `budget_used_pct`,
`budget_warning`. Its port is ephemeral, rediscovered from
`~/.culture/pids/overview-<name>.port`. **A read-only fleet dashboard needs no IRC client at
all** — but do not put this in a scheduling hot path (each request opens a fresh IRC
connection).

### Step 5 — supervision under the bridge

```bash
uv add agent-lifecycle                  # 0.11.0, stdlib-only, no third-party deps
```

Wire `driver.py state --id` as the `HealthProbe` their `ProcessSupervisor` is missing. Their
`ReadinessTracker` one-way latch matches our `starting` → `idle` semantics exactly; their
`RestartPolicy` becomes the "re-place the work" half of fleet success criterion 3.

Cost: an async boundary (their seam is asyncio throughout) that must **not** leak into
`prototypes/`; and a Windows supervisor of our own behind the same seam, since their docstring
says *"Windows is an explicit non-goal."* Pin the version — the repo is private.

### Step 6 — task graph in, completion signal out

```bash
uv tool install devague
devague plan waves --json    # -> {"plan", "waves": [["t1"],["t2","t3"]], "tasks": {...}}
```

Consume the topological batches as our dispatcher's task source. Then replace their prose wave
gate with a real one — see [Where we plug in](#5-where-we-plug-in), seam 4.

---

## 4. What we keep building

Seven things nothing in the ecosystem covers. Each row's evidence is the reason we can say
"nothing covers it" rather than "we didn't find it."

| What | Evidence that nothing covers it |
|---|---|
| **Observation of a foreign agent from outside its process** | `cultureagent`'s emitter is in-process and explicitly fail-open; `colleague` writes every signal from inside its own tool loop and lists Claude/Codex/Gemini adapters as **out of scope**; `agent-lifecycle`'s `HealthProbe` is a caller-supplied callable with no implementation anywhere in the org |
| **A waiting-on-a-human state** | All three enforced backends delete the category at source: `permission_mode="bypassPermissions"` (claude `agent_runner.py:148`), `"approvalPolicy":"never"` + `--full-auto` (codex `agent_runner.py:140`, `supervisor.py:99`), `_APPROVAL_METHODS` routed into `_auto_approve()`. Their enum has no waiting value **because a blocked agent cannot exist in their world** |
| **Windows as a peer** | `agentirc start` / `culture server start` → `sys.exit(1)`, *"Daemon mode not supported on Windows"* (`agentirc/cli.py:569-572`, `culture_core/cli/server.py:579`); `agent-lifecycle`: *"Windows is an explicit non-goal"*; culture#262 continues *"as if success"* when it cannot spawn daemons on Windows. The absence is consistent, not incidental |
| **Death distinguished from hang** | `presumed_hung` is `state ∈ BUSY and now − last_refresh > 90s`, computed at read time. On a live run it fired for a process that had been **dead** for 90 s — the diagnosis was wrong, not late. Our `dead` is grounded in process exit |
| **A completion signal for fanned-out work** | `devague`'s `assign-to-workforce` step 4 is the prose *"Wait for all tasks in the wave to complete"*; devague#20 states the tool does not mark tasks done; `codexd`'s README states orchestration is not implemented. There is no completion signal anywhere in their fan-out path |
| **Evidence attached to a state claim** | The wire carries a 128-char `task` field, **silently truncated server-side** (400 chars sent → 128 returned). The natural evidence carrier `EVENTPUB` requires `CAP REQ agentirc.io/bot`; a plain client gets `EVENTERR e1 :bot-capability-required` |
| **Admission control that fails closed** | `colleague`'s rig slot proceeds *without* a slot after `max_wait` (default 300 s) rather than queueing; their presence emitter is fail-open. Correct for one operator protecting one GPU, wrong as a spend gate (**R6**) |

---

## 5. Where we plug in

Ordered by value. Each row names the concrete change.

| # | Seam | Concrete change | Why it is worth it |
|---|---|---|---|
| 1 | **Presence bridge → agentirc wire** | New `fleet/presence_bridge.py`: stdlib socket, `MODE +A`, projection table from step 3, ≤30 s heartbeat, local enum assertion before send | Our state becomes visible to every existing consumer (`culture residents`, `residents.json`, `irc-lens`) with zero upstream change |
| 2 | **`waiting` value in the presence enum** *(draft PR exists)* | Add the value to `culture/protocol/extensions/presence.md` and to agentirc's `PresenceSkill` validation set; argue it from the **fleet** case (dispatch into a void, culture#305's 0.3–0.5M-token spiral) and from our `attach` posture, never from the single-agent case | Removes the only lossy cell in our projection. Frame it as *finishing* his stated rule — he already wrote *"transitions are driven only by code boundaries"* |
| 3 | **`agent-lifecycle` `HealthProbe`** | An async shim over `driver.py state` returning `state not in {dead, presumed_hung}` with the evidence attached | Their restart policy stops firing on agents that are merely blocked on a permission dialog. Smallest possible patch to code that today has no probe at all |
| 4 | **`devague` wave gate** | One skill edit: replace `assign-to-workforce` step 4's prose with `driver wait --id <agent> --until idle --timeout N` per worktree agent | The first defined completion signal in their fleet path. Cost: one file |
| 5 | **`colleague` resident presence** | `colleague promote --serve` opens a real IRC connection (2,854 LOC under `resident/`) and `grep -rn "PRESENCE" colleague/` returns **zero wire references** — a working, invisible mesh agent. Offer the bridge as its emitter | A live demonstration, in their most active repo, of the gap our PR describes |
| 6 | **`irc-lens` dashboard** | None — consume `GET /residents.json` and read it in a browser | A fleet dashboard we do not write |
| 7 | **agentfront rubric verbs** | Add `learn`, `explain <path>`, `overview`, `doctor` with `--json` and a `hint:` line on every error (~1 day) | Makes our driver discoverable *by their agents* with no human in the loop. **Keep our exit codes** (3/4/5) and document the divergence — do not renumber a published contract to score a rubric point |

---

## 6. Conventions to adopt

| Convention | Where it lives | What we do |
|---|---|---|
| **`[tool.citation]` ledger** | `agentirc/pyproject.toml` (470 lines): per-file source URL pinned to upstream commit, `quote`/`paraphrase`/`synthesize`, sha256, `notes` rationale | Use it for anything we vendor — in practice `culture_core/credentials.py`. ~20 lines of TOML per file. **Take the ledger, refuse the vendoring habit** — we decided to adopt their infrastructure, not copy it |
| **Dated spec/plan pairs** | `culture/docs/superpowers/{specs,plans}`, `docs/specs/YYYY-MM-DD-<slug>.md`, kept after shipping | Rename our `docs/design/` + `docs/results/` files to their date-prefixed pattern. Makes an upstream design doc from us look native |
| **`api-stability.md`** | `agentirc/docs/api-stability.md` — seven public modules with semver contracts | Add the same section to `prototypes/common/SPEC.md`: what a downstream may depend on, and what may move |
| **Nick as identity** | `<server>-<agent>`, server-enforced (432 on violation) | Answers our open question 5. Name servers deliberately and once — nicks are not portable across differently-named servers |
| **The four universal verbs** | `agentfront/docs/rubric.md`, seven bundles, enforced by `agentfront cli doctor --strict` | `learn` / `explain` / `overview` / `doctor`, `--json` on each, stdout never mixed with stderr, `hint:`/`try:` on every error, and `doctor` must supply a non-empty `remediation` for every failed check — forever |
| **Degrade taxonomy** | `irc-lens/web/residents.py`: classify the outcome as supported / unsupported / error, never raise | Exactly the shape our `attach --socket`-less path already uses (`screen_available: false`). Copy the naming |
| **Flight-plane split** | `colleague`: `<id>.feed.jsonl` (append-only, worker-written) + `<id>.control.json` (pilot-written, read at turn boundary) | Our `send`/`answer` refusal semantics map straight on. **But:** cooperative only — our kill switch (R5) must not ride it |
| **Heartbeat record** | `colleague`: `{"type":"run-start"\|"heartbeat"}` markers, distinct from step records (which have **no** `type` key, so old readers stay byte-identical) | A multi-minute silent completion reads as thinking, not dead. Copy the backward-compatible discriminator trick too |
| **Rig slot** | `colleague/rig.py`: atomic `mkdir` on `.colleague/rig-slots/slot-<i>`, PID stamped, `os.kill(pid,0)` self-heal, **a live holder is never preempted — `PermissionError` counts as alive** | A correct dependency-free admission-control primitive. **Copy the mechanism, change the default** — theirs degrades open |
| **SIGTERM commits WIP** | `colleague` catches SIGTERM/SIGINT and commits work-in-progress to the branch before exit; SIGKILL still orphans, and `clean` reaps it | Our at-most-once story needs exactly this distinction |
| **Worktree + budget conventions** | `../.worktrees.<repo>/agent-<task-id>` on branch `agent/<task-id>`; `MAX_SUBAGENT_DEPTH=4` / `FANOUT=4` / `TOTAL=24` charged **before any child work** | Every nesting shape provably terminates. Copy verbatim |
| **Memory discipline** | Theirs: `eidetic-cli` + `/recall`-before, `/remember`-after, store committed in-repo at `.eidetic/memory/` | **Keep ours.** `STATE.md` / `HANDOFF.md` / `PITFALLS.md` already works; adopting eidetic means two stores that will disagree |

---

## 7. Traps

**Wire and protocol**

1. **`MODE +A` or your row outlives you.** Controlled A/B, same server, same clean exit: the
   `+A` client flipped to `offline`; the one without it stayed `thinking` → `presumed_hung`
   90 s later. `_emit_disconnect_events` is gated on `"A" in modes` (`agentirc/ircd.py:769-771`).
   This is agentirc#55, still open, and it bites anyone who writes the obvious three-line client.
2. **A rejected state does not clear the old one — it freezes it.** `PRESENCE
   :{"state":"waiting:permission"}` returned **zero bytes** and the prior `thinking` row kept
   its original `since`. An emitter with a typo is a liar with a plausible timestamp. Assert
   locally before sending.
3. **`421 :Unknown command` is overloaded** — pre-9.12 "unsupported" *and* "your client isn't
   registered" (skill dispatch is gated on `self._registered`, `client.py:390`). Probe `VERBS`.
4. **Nick rejection is a `432` and happens before anything works.** If the server is named
   `culture` (the default) on one box and `<host>` on another, your nicks are not portable.
5. **`task` is truncated server-side, not rejected.** 400 chars in → 128 chars back. Quiet and
   lossy — the worst mode for a field carrying evidence.
6. **`presumed_hung` is not a liveness signal.** Computed at read time from
   `state ∈ BUSY and now − last_refresh > 90s`. It fired for an already-dead process. Never
   re-import it as truth.
7. **`residents.json` is not always there** — only while `culture mesh overview --serve` runs,
   on an ephemeral port from `~/.culture/pids/overview-<name>.port`, and each request opens a
   fresh IRC connection. Dashboard yes, scheduler no.

**Versions and platforms**

8. **Python floors:** `agentirc-cli` ≥3.11, `culture` ≥3.12, `agentfront` ≥3.12. **Our drivers
   are stdlib-only 3.9+.** The moment we `import` either, we inherit the floor and 27
   transitive packages (grpcio, protobuf). Keep the socket.
9. **Windows: the refusal is DAEMONIZATION only — corrected 2026-08-06 by testing.**
   This entry previously read *"Windows is an explicit refusal, not an omission."* That
   overstated it. `agentirc start` exits 1 because `_daemonize_server` needs `os.fork`
   (`agentirc/cli.py:570-572`), and its own message says **"Use --foreground."**
   **Verified on Windows 11 build 26200:** `agentirc-cli` 9.12.0 installs under `uv`, serves,
   and completes a full `PRESENCE` publish + `PRESENCELIST` round-trip. The server, the wire
   and the presence protocol all work natively.
   Still true: `agent-lifecycle` declares Windows a non-goal, and culture#262 reports success
   it did not achieve. So do not assume `agentirc start` works everywhere — but **do** assume
   `agentirc serve` does, and supply the lifetime yourself
   (see [windows-persistence-answer.md](windows-persistence-answer.md)).
10. **`agent-lifecycle` is asyncio throughout and its GitHub repo is private (404).** We can
    install and read the sdist; we cannot file issues or track the seam-ratification its own
    charter lists as open (issue #10). Pin the version; treat the API as frozen, not a partnership.
11. **`cultureagent` has no repository at all.** PyPI-only. Anything we depend on there is
    unversioned from our side and can change with no diff to read.
12. **Exit-code collision.** Their rubric reserves `3+`; we publish `3` timeout, `4` refused,
    `5` launch failure. Passing bundle 4 must not mean renumbering — document the divergence,
    the way culture keeps its own wire-format bugs (`ROOMETAEND`) verbatim rather than breaking peers.

**Reading the ecosystem**

13. **Repo name ≠ built product, and README ≠ code.** `agenda`, `evidence-cli`, `refactor-cli`,
    `jetson-orin-cli`, `tensor-cli`, `reduce-cli` all describe real products and ship the
    identical six-verb `teken` scaffold. Read `<pkg>/cli/_commands/` before scoring maturity.
    Only 10 of 33 long-tail repos were tree-verified — the rest are description-only here.
14. **"Cited from teken (afi-cli)" is boilerplate, not a maturity signal.** It tells you a
    generator ran; nothing about whether the stub was filled in.
15. **PyPI names can be squatted.** `refactor-cli` on PyPI is an unrelated "organize files
    using AI" package; plain `agenda` is a squat (correct name: `agenda-cli`). Cross-check
    `project_urls`/author against the repo's own `pyproject.toml`.
16. **A shallow clone's version can lag PyPI.** `agex` cloned at 0.13.1 while PyPI served
    0.32.0. PyPI is the maturity truth; the clone is the code truth; don't average them.
17. **"Presence" means two unrelated things.** agentirc `PRESENCE` = the six-state wire
    protocol. `COLLEAGUE_PRESENCE` / `presence_engine.py` = a *conversational* narration feature
    with rungs `loop | beats | off`. Disambiguate before any conversation with Ori about it.
18. **`fleet-cli` is a false cognate** — it coordinates drones. Do not let it collide with our
    `docs/design/fleet-vision.md` vocabulary.
19. **Three "community" repos are not his work.** `community` and `awesome-claude-code-security`
    are forks with zero or one trivial commit; `BenevolentAgentsRFC` is a fork of a group
    project where he participates as the agent "otti", status *Pending*. Quoting any as
    AgentCulture doctrine is a factual error a maintainer catches instantly.
20. **`steward` / `guildmaster` are genuinely private** — 404 across two independent passes.
    Not a transient access issue; don't re-check without a reason.

**Documentation**

21. **The docs site is aspirational.** Five of seven culture.dev links in `culture`'s own README
    404 (`/vision/`, `/ecosystem-map/`, `/choose-a-harness/`, `/agentirc/architecture-overview/`,
    `/reference/cli/devex/`). The two that resolve are stale — `layers` documents a CLI verb that
    doesn't exist and describes history as in-memory when the code ships SQLite WAL.
    `sitemap.xml` is empty on both culture.dev and tools.culture.dev **despite the doctrine
    mandating sitemaps.** Cite `llms.txt`, `llms-full.txt`, `.md`-suffix paths, or GitHub blob
    URLs — never a bare pretty-path.
22. **`colleague`'s docs lag its code.** `docs/features/resident.md` says a real mesh transport
    round-trip stays PENDING; the tree already contains a hand-rolled asyncio IRC client. Read
    the code, not the feature page, before citing what is live.
23. **Doctrine repos are stale in the places that would matter.** `agentic-human` is 4.5 months
    old and predates all mesh/presence/role work; `agentic-guides` is a one-file stub. Live
    doctrine is in `agentfront/docs/` and `culture/protocol/`.

**Framing**

24. **`bypassPermissions` is their architecture, not their oversight.** If the PR reads as "you
    forgot a state," it reads as "you don't understand our design." It must read as "here is the
    state that appears the moment an agent is *not* run with permissions bypassed — which is
    every agent an operator attaches to rather than spawns." Their own culture#305 postmortem
    features `local-boss`, described as an *"orchestrator session driven from outside the mesh
    (not a managed agent)"* — that is our posture, in their incident report.
25. **"Never self-report" is narrower to him than to us.** His rule scopes to the *model*; the
    *process* self-reports freely over a fail-open transport with no ack. Saying "your presence
    is self-reported" without that qualifier contradicts a sentence he wrote. Say instead: *the
    emitter is in-process; we observe from outside the process.*
26. **Reflective Development cuts against verified state.** Its premise — agents improve their
    own environment, documentation is the memory — trusts the participant's account of itself.
    Right for docs, wrong for liveness. Do not adopt it at the scheduling layer.

---

## 8. Open questions for Ori

| # | Question | Why only he can answer it |
|---|---|---|
| 1 | Would you accept a `waiting` value in the presence enum, or would you prefer a namespaced extension (`x-waiting`)? What is the compatibility story for pre-9.12 peers across S2S? | It is his protocol and his federation-compat policy |
| 2 | Is `working` reserved for a backend with an observable tool-execution boundary, or may an **external observer** occupy it? We can emit it today and nothing collides. | Determines whether our bridge is conforming or squatting |
| 3 | Is `MODE +A` intended to be opt-in? Without it a client's death is invisible (agentirc#55). Should presence-publishing clients get disconnect events automatically? | Design intent behind the gate in `ircd.py:769-771` |
| 4 | Is there an intended path for a presence source that is **not the agent's own connection** — a proxy publishing on behalf of nick X? Today nick == connection. | This is the single structural question our whole integration rests on |
| 5 | Nick minting for agents the mesh did not spawn: is "one server per host, named after the host" the endorsed convention, given the `<server>-*` constraint? | Ours would be a convention others have to live with |
| 6 | Windows: is `--foreground` + an external supervisor the intended path, or is a native daemon planned? Would you take our `schtasks` path upstream? | Determines whether we maintain a fork of the daemon story forever |
| 7 | Will `cultureagent` get a public repo? Today it is PyPI-only, so its emitters cannot be audited or PR'd. | Only he can open it |
| 8 | `agent-lifecycle` is private on GitHub. How do we file against the `HealthProbe` seam, and what is the status of the seam-ratification its charter lists as open (issue #10)? | We cannot see the tracker |
| 9 | Is `GET /residents.json` a stable read API, or an implementation detail of the overview server? | We would build a dashboard on it |
| 10 | Is `EVENTPUB` (bot capability) the intended carrier for payloads over the 128-char `task` limit, or should evidence live off-wire entirely? | Determines whether we open a second capability-gated connection |
| 11 | Would you take a PR replacing `devague`'s prose wave gate with an external readiness check? | It is his skill doc and his stated non-goal boundary |
| 12 | `steward` / `guildmaster` are private — is anything we plan to adopt dependent on them? | Unknowable from outside |

---

*Compiled 2026-08-06 from five cluster surveys. Anything marked "description-only" or
"not tree-verified" was scored from repo metadata and PyPI JSON, not from source.*
