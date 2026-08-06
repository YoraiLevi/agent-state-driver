# Cluster: delegation daemons + coding agents

**Scope.** The closest cluster in the AgentCulture ecosystem to our fleet ambitions:
`codexd`, `antigravityd`, `kirod`, `lecodeur`, `colleague`, `lobes-cli`, `devague`,
`antoine`, `league-of-agents`, `league-of-agents-platform`, `intern-cli`, and
`OriNachum/dev-agents`. One repo not in the brief is added because the cluster is
unreadable without it: **`agent-lifecycle`** (PyPI-only; its GitHub repo is private/404),
which is the process-supervision core `colleague` embeds.

**Method.** `gh api` for metadata, shallow clones into
`…/scratchpad/daemons/`, PyPI JSON for maturity, sdist extraction for
`agent-lifecycle`. READMEs and `docs/` read directly. Claims are **[OBSERVED]** unless
marked **[INFERRED]**.

**Headline correction to the prior survey.** `docs/.research/fleet/agentculture.md`
concluded *"the three named daemons are empty… do not model delegated repo work on
them."* That remains true. But it also filed `colleague` as a minor row. That was wrong:
**`colleague` is 60,390 lines of Python across 404 test files at PyPI 1.53.0 (117
releases), pushed today**, and it independently built roughly the run-control half of
what our fleet vision calls for. This file corrects that.

---

## Verdict

- **The `*d` daemons never became daemons.** `codexd` / `antigravityd` / `kirod` are
  25 / 34 / 14-line `--version` CLIs, last pushed 2026-05-22. There is no task queue, no
  dispatch, no lease, no completion signal. Delegated repo work in them = *a nick, a
  backend, a set of vendored shell skills, and a chat channel*. `codexd`'s own README
  says *"daemon task orchestration is not implemented yet."* **The question "how does a
  `*d` daemon accept and execute delegated repo work" has no answer, because none of them
  does.** [OBSERVED]
- **The real answer to that question is `colleague`, and it is substantial.** Task shape
  is a typed `Task` → `TaskResult`; it runs in a **throwaway git worktree** at operator
  HEAD on branch `colleague/<id>`; it reports back through a JSON artifact
  (`.colleague/<task-id>.json`) plus an append-only **flight feed**; and PR review is
  `git branch → commit → push → gh pr create`, gated so `--no-pr`/no-remote stays local
  and CI never pushes. There is no reviewer agent — the PR is the review surface, and a
  human is the reviewer. [OBSERVED]
- **`colleague` has built a mid-run control plane that we have not, and it is
  file-based, cooperative, and daemon-free.** `.colleague/flight/<id>.feed.jsonl` +
  `.control.json`, verbs `flight status|guide|stop|list`, a `colleague talk <id>` attach
  REPL from a second terminal, a liveness **heartbeat** record so a long silent
  completion does not read as death, and SIGTERM caught to commit WIP before exit. **This
  is our `attach` + `wait` + `send` surface, for their harness, already shipped.**
  [OBSERVED]
- **But it observes only its own loop — it cannot see a foreign CLI agent, and that is
  the seam.** Every signal above is written *by colleague's own tool loop from inside*.
  Codex/Claude/Gemini adapters are on its explicit **out-of-scope** list. Point it at a
  running Claude Code session and it knows nothing. Our three-channel observation
  (sidecar / screen / process) answers exactly the question colleague's flight plane
  answers only for processes it authored. [OBSERVED + INFERRED]
- **`agent-lifecycle` (PyPI 0.11.0, 22 releases, stdlib-only) is the ecosystem's real
  supervision core — and its health probe is a hole shaped like us.** It ships
  `ProcessSupervisor` (asyncio spawn / classify exit / SIGTERM→SIGKILL escalation),
  `RestartPolicy`, `ReadinessTracker` (one-way latch), and `HealthThreshold`
  (consecutive-failure counter). The probe itself is a **caller-supplied
  `HealthProbe = Callable[[], Awaitable[object]]`** — they define the tracker and leave
  the probe to the consumer. Nobody in the ecosystem has written a real one for a CLI
  agent. **We are that probe.** Also: *"Windows is an explicit non-goal."* [OBSERVED]
- **A live `colleague` resident on the mesh emits no presence at all.** `colleague
  promote --serve` opens a real IRC connection to agentirc (`resident/connection.py`,
  `transport.py`, 2,854 lines under `resident/`), joins channels, and serves mesh work
  requests — and `grep -rn "PRESENCE" colleague/` returns **zero wire references**; every
  hit is their unrelated conversational `COLLEAGUE_PRESENCE` knob. A colleague resident is
  a working, invisible mesh agent. That is a concrete, demonstrable gap our `waiting`-state
  PR sits directly beside. [OBSERVED]
- **`devague` is genuinely the workforce planner, and genuinely refuses to orchestrate.**
  Vague idea → converged spec → converged plan, deterministic, **zero LLM calls inside the
  tool**, state as plain JSON under `.devague/`. `devague plan waves --json` emits the
  dependency graph in topological batches. Per devague#20 it *"does not spawn agents,
  manage worktrees, mark tasks done, or pick a backend."* The fan-out lives in a
  427-line Claude skill whose wave gate is the prose *"Wait for all tasks in the wave to
  complete"* — **still no completion signal**. [OBSERVED]
- **The cheapest credible proof of our value is unchanged and now doubly available.**
  Either replace devague's undefined wave gate with `wait --until idle` per worktree
  agent, or supply the missing `HealthProbe` to `agent-lifecycle`'s `ProcessSupervisor`.
  Both are small patches to real projects that today guess. [INFERRED]

---

## Repos

Maturity is PyPI `version` + release count where published; otherwise last push + whether
real code exists.

| Repo | What it actually is | Maturity | Docs | Intended use | Verdict |
|---|---|---|---|---|---|
| **colleague** | A swappable coder-agent harness: typed `Task`→`TaskResult`, bounded tool loop, worktree isolation, git/PR handoff, file-based flight control plane, mesh resident appserver. *Not* a wrapper for Claude Code/Codex. | **1.53.0, 117 releases**; 60,390 LOC Python, 404 test files; pushed 2026-08-06 | [README](https://github.com/agentculture/colleague) · `docs/features/` (60 pages) · [PyPI](https://pypi.org/project/colleague/) | Delegate a scoped repo task to a *different mind* (local vLLM / any OpenAI-compatible endpoint) and get an auditable artifact back | **ADOPT (patterns) / WATCH (product)** — steal the flight plane, worktree convention, and rig-slot design; do not adopt it as our agent, since it is a competing harness that cannot observe foreign agents |
| **agent-lifecycle** *(not in brief; GitHub 404, PyPI only)* | Stdlib-only, harness- and transport-agnostic process lifecycle core: `Supervisor`, `ProcessSupervisor`, `RestartPolicy`, `ReadinessTracker`, `HealthThreshold`, `Observer` seam | **0.11.0, 22 releases**; 2,284 LOC in `runtime/`, ~24 test modules | [PyPI](https://pypi.org/project/agent-lifecycle/) · `docs/runtime-seam.md`, `docs/scope-charter.md`, `docs/colleague-embed.md` in the sdist | Spawn/crash-detect/restart/health-probe an agent process independent of brain and transport | **ADOPT** — the closest thing to a fleet worker-supervision contract in the ecosystem, and its `HealthProbe` seam is exactly our output shape |
| **devague** | Deterministic, LLM-free CLI: vague idea → converged spec → converged plan with acyclic task graph and `plan waves --json` | **0.22.0, 32 releases**; pushed 2026-07-29 | [README](https://github.com/agentculture/devague) · `.claude/skills/assign-to-workforce/SKILL.md` | Produce the task graph a workforce executes; deliberately does not execute it | **ADOPT (as input) / WATCH** — consume `plan waves --json` as our dispatcher's task source; its missing wave-completion signal is our demo |
| **league-of-agents** | Deterministic multi-agent strategy arena with two engines, fog of war, and a harness that drives external agents as subprocesses (`command` = stateless per turn; `resident` = one persistent session per seat) | **0.17.0, 28 releases**; pushed 2026-07-15; 2 MB of real code + docs | [README](https://github.com/agentculture/league-of-agents) · `docs/features/harness-and-drivers.md` | Benchmark whether a group of agents can cooperate under constraint; scores a *span-of-control* axis | **WATCH** — the only place anyone measures multi-agent coordination quality, and its `resident` driver blocks on a live session with no readiness check (a consumer for us); but it is a game, not infrastructure |
| **lobes-cli** | Local vLLM model server manager — run, assess, switch the local model; serves cortex/senses/stt/tts roles via a `/capabilities` gateway | **0.55.0, 53 releases**; pushed 2026-08-04 | [README](https://github.com/agentculture/lobes-cli) · [PyPI](https://pypi.org/project/lobes-cli/) | Local inference substrate under colleague | **IGNORE** — inference plumbing; touches no state, presence, or dispatch concern of ours |
| **codexd** | 25-line `--version` CLI + `culture.yaml` (`suffix: codexd, backend: codex`) + vendored `.agents/skills/` shell scripts | 0.1.2, 3 releases; pushed 2026-05-22; **scaffold, self-declared** | [README](https://github.com/agentculture/codexd) | *Intended*: "Codex daemon for delegated repo tasks and reviewable PRs" | **IGNORE** — README states orchestration is not implemented; nothing to model |
| **antigravityd** | 34-line CLI; `culture.yaml` uses `backend: acp` with `acp_command: ["antigravityd","serve"]` — a command that does not exist in the repo | 0.1.0, 1 release; pushed 2026-05-22; **scaffold** | [README](https://github.com/agentculture/antigravityd) (one line) | *Intended*: delegated repository work via Agent Client Protocol | **IGNORE** — only interesting datum is that ACP is their intended foreign-agent seam |
| **kirod** | 14-line CLI; `culture.yaml` `acp_command: ["kiro-cli","--acp"] # placeholder — confirm real Kiro ACP launch command` | **Not on PyPI**; pushed 2026-05-22; **scaffold** | [README](https://github.com/agentculture/kirod) (one line) | *Intended*: Kiro daemon | **IGNORE** — the launch command is an admitted placeholder |
| **lecodeur** | ~766 LOC package exposing `whoami` / `learn` / `explain` only. Despite "a local coding agent", there is no coding agent | 0.2.0, **2 releases**; pushed 2026-07-15 | [README](https://github.com/agentculture/lecodeur) (3 lines) | *Intended*: local coding agent for the Culture mesh | **IGNORE** — an identity stub; colleague supersedes the intent |
| **intern-cli** | Unmodified agent-repo template (`whoami`/`learn`/`explain`/`overview`/`doctor`); the Bonsai 1-bit model wrapper the description promises is absent from the tree | 0.4.1, 2 releases; pushed 2026-07-18 | [README](https://github.com/agentculture/intern-cli) | *Intended*: cheap local ternary-model "intern" as a Small-mode harness component | **IGNORE** — template residue; even its README still says "this template" |
| **antoine** (`kata-cli` / `antoine-cli`) | Codebase lookup/indexing verbs (`antoine` = "N to 1": collapse N tool calls into one) **plus** a real A/B eval harness with LLM-judge scoring. The verbs themselves are still `learn`/`explain`/`whoami` stubs | **2.6, 5 releases**; pushed 2026-07-15 | [README](https://github.com/agentculture/antoine) · `docs/eval-rounds/` | Cheaper repo comprehension for delegated subagents | **IGNORE** (with one note) — not fleet-shaped; its round-2 finding that *subagents build plans from the prompt body before consulting the skills catalog* is worth remembering when we write dispatch briefs |
| **league-of-agents-platform** | Hosted AWS/SAM deployment of the arena (Lambda + DynamoDB + S3, OAuth, agent tokens, BYO-key), `league-site` operator CLI | 0.x; **not separately on PyPI** under that name; pushed 2026-07-15, 3.2 MB | [README](https://github.com/agentculture/league-of-agents-platform) | Public benchmark site at league-of-agents.ai | **IGNORE** — hosting concern, orthogonal to us |
| **OriNachum/dev-agents** (personal) | 5 files: `.gitignore`, `LICENSE`, a 2-line README, and one `python-stack/.agent/` pair | **Dead** — last push 2025-07-11, 13 months stale; effectively empty | [README](https://github.com/OriNachum/dev-agents) (2 lines) | "Workbenches repository of agents and code" | **IGNORE** — abandoned before the mesh work began |

---

## Adoption notes

### 1. `agent-lifecycle` — the one thing to actually install

```bash
uv add agent-lifecycle          # 0.11.0, stdlib-only, no third-party deps
```

**What it adds.** A worker-supervision contract we currently do not have. Concretely:

| Piece | What it gives us |
|---|---|
| `ProcessSupervisor` | `asyncio.create_subprocess_exec` spawn, `classify(returncode) → ExitOutcome`, `terminate()` → 5 s → `kill()` escalation, and `process_exited` emitted **exactly once** whether discovered by `wait` or `stop` (a `_exited` guard) |
| `ReadinessTracker` | A **one-way latch**: `NOT_READY` → `READY` on first successful probe, never reverts. Matches our `starting` → `idle` transition semantics exactly |
| `HealthThreshold` | Consecutive-failure counter, `threshold >= 1` enforced at construction with a stated reason. One success resets |
| `RuntimeObserver` | Instrumentation seam where every call is wrapped in `_notify` — `SystemExit`/`KeyboardInterrupt` propagate, everything else is swallowed *"so a broken observer never corrupts supervision"* |

**What it replaces.** Nothing we have shipped. It sits *above* our driver: our
`state --id` becomes the `HealthProbe` their `ProcessSupervisor` is missing, and their
restart policy becomes the "re-place the work" half of fleet success criterion 3.

**What it costs.**
- **asyncio.** Their seam is asyncio-throughout by declared design. Our drivers are
  stdlib-only synchronous Python 3.9+. Adopting the runtime means an async boundary at the
  fleet layer, or an executor shim — do not let it leak into `prototypes/`.
- **Windows.** `process_supervisor.py`'s own docstring: *"POSIX semantics — SIGTERM via
  `proc.terminate()`, SIGKILL via `proc.kill()`. **Windows is an explicit non-goal**."*
  This collides head-on with fleet requirement **R1**. Adopting it wholesale makes our
  fleet a Linux fleet with excuses. Plan to supply our own Windows supervisor behind the
  same seam.
- **Governance.** The repo is private on GitHub (`gh api repos/agentculture/agent-lifecycle`
  → 404) and reachable only through PyPI. We cannot read issues, file them, or see the
  seam-ratification status their own charter flags as open (issue #10). Pin the version.

### 2. `devague` — consume the plan, do not consume the fan-out

```bash
uv tool install devague         # 0.22.0
devague plan waves --json       # → {"plan", "waves": [["t1"],["t2","t3"]], "tasks": {...}}
```

**What it adds.** A ready-made, deterministic, LLM-free task-graph producer for our
dispatcher — topological batches with per-task `summary`, `instruction`,
`acceptance_criteria`, `covers`. It is authored to be consumed by an orchestrator that
devague deliberately does not contain.

**What it costs.** Nothing at runtime (no LLM calls, plain JSON state under `.devague/`).
The cost is conceptual: their convergence gates are *human-confirmation* gates, so a fully
unattended fleet either drives those gates itself or stops at them. Their anti-fabrication
rule — *"LLM-proposed claims stay `proposed` until **you** confirm them"* — is a rule we
should keep, not route around.

### 3. `colleague` — steal five patterns, install nothing (yet)

Do **not** make colleague our worker: it is a competing harness with its own tool loop and
its own model backends, and Claude/Codex adapters are on its stated out-of-scope list. Do
steal these, all of which are file-based, daemon-free, and stdlib-only:

1. **The flight plane split.** `<id>.feed.jsonl` (append-only, written by the worker) +
   `<id>.control.json` (written by the pilot, read at the next turn boundary). Cooperative,
   ~one-turn latency, no socket. Our `send`/`answer` refusal semantics map straight onto it.
2. **`flight_repo_path` ≠ `repo_path` (their bug #310).** They armed the control plane
   inside the throwaway worktree, so it was destroyed on cleanup and piloting was *silently
   dead* for every `work` and `--background` run. The fix decouples the plane's location
   from the work CWD. **We will hit this the moment we isolate fleet work in worktrees.**
3. **The heartbeat record.** A `{"type": "run-start"|"heartbeat", ...}` marker distinct from
   a step record (a step record has **no** `type` key, so existing readers stay
   byte-identical) so a multi-minute silent completion is visibly *thinking*, not dead.
   This is their answer to the same problem our `presumed_hung` threshold guesses at.
4. **The rig slot (`colleague/rig.py`).** Cross-process concurrency budget via atomic
   `mkdir` on `.colleague/rig-slots/slot-<i>`, PID stamped into `slot-<i>/pid`,
   `os.kill(pid, 0)` stale-slot self-heal, **a live holder is never preempted — even by a
   process that merely cannot confirm it (`PermissionError` counts as alive)**, and
   degrade-open after `max_wait` rather than deadlock. That is a correct, dependency-free
   admission-control primitive we would otherwise design from scratch.
5. **SIGTERM as the graceful signal.** They catch SIGTERM/SIGINT on the isolated path and
   **commit work-in-progress to the branch before exiting**, so `timeout 300 colleague
   work …` no longer strands a near-complete run as uncommitted files in an orphan
   worktree. SIGKILL still orphans, and `colleague clean` reaps it. Our fleet's
   at-most-once story needs exactly this distinction.

Also worth copying verbatim: the worktree convention `../.worktrees.<repo>/agent-<task-id>`
on branch `agent/<task-id>`, and `MAX_SUBAGENT_DEPTH=4` / `MAX_SUBAGENT_FANOUT=4` /
`MAX_SUBAGENT_TOTAL=24` charged **before any child work** so every nesting shape provably
terminates.

### 4. The two shippable demos

Both are small patches to code that today guesses, and both are the argument in
`fleet-vision.md` section 1 made concrete:

- **Wave gate.** `assign-to-workforce` step 4 is prose: *"Wait for all tasks in the wave to
  complete."* Replace with `driver wait --id <agent> --until idle --timeout N` per worktree
  agent. Cost: one skill edit. Payoff: the first defined completion signal in their fleet path.
- **Health probe.** `ProcessSupervisor.monitor_health` takes
  `HealthProbe = Callable[[], Awaitable[object]]` and nobody has written one for a CLI
  agent. Ours returns `state != dead and state != presumed_hung` with the evidence attached.
  Cost: an async shim over `driver.py state`. Payoff: their restart policy stops firing on
  agents that are merely blocked on a permission dialog.

---

## Traps

1. **"Presence" means two unrelated things, and the collision is total.** In agentirc,
   `PRESENCE` is the six-state wire protocol our PR touches. In colleague,
   `COLLEAGUE_PRESENCE` / `presence_engine.py` / `docs/features/presence-default-everywhere.md`
   is a *conversational* feature — a small "senses" model narrating cortex's progress to
   the operator. Their rungs are `loop | beats | off`. **Nothing in colleague publishes a
   `PRESENCE` line.** Any conversation about "colleague presence" will be at cross purposes
   unless the term is disambiguated first.
2. **A live colleague resident is invisible to the mesh's own presence system.**
   `colleague promote --serve` opens a real IRC connection and serves work, and emits no
   presence. Do not assume mesh membership implies a presence row. Conversely: this is our
   opening, not just a defect.
3. **`agent-lifecycle` disclaims Windows in writing.** *"Windows is an explicit non-goal."*
   Adopting it as the fleet worker contract without a parallel Windows path silently
   violates R1. Note this compounds culture#262 (their mesh update *"continues as if
   success"* when it cannot spawn daemons on Windows). The ecosystem's Windows story is
   consistently absent, not merely immature.
4. **`agent-lifecycle`'s GitHub repo is private.** Cited throughout colleague's docs with
   issue links we cannot open. We can install and read the sdist; we cannot track its
   roadmap, file bugs, or verify the seam-ratification status its own charter lists as
   open. Treat its API as pinned-and-frozen, not as a partnership.
5. **Colleague's resident row is honestly marked NOT live-proven, and the docs lag the
   code.** `docs/features/resident.md` says *"a real mesh transport round-trip stays
   PENDING until upstream ships a transport plug."* But `colleague/resident/` now contains
   `connection.py`, `transport.py`, `register.py`, `identity_mint.py` — 2,854 lines, with a
   hand-rolled asyncio IRC client. The doc is stale relative to the tree. **Read the code,
   not the feature page, before citing what is or is not live.** Their own note is
   telling: *"the live network handshake is exercised by manual end-to-end against a
   running mesh (no IRC server in the automated suite)."*
6. **`backend: acp` in `antigravityd`/`kirod` is aspiration, not integration.** Their
   `acp_command` values are an unbuilt binary and an admitted placeholder. Do not read the
   ecosystem as having an Agent Client Protocol seam; it has an intention to have one.
7. **Repo descriptions overstate three repos in this cluster.** `lecodeur` ("a local coding
   agent") has no agent; `intern-cli` ("wraps the Bonsai 1-bit model") has no wrapper;
   `codexd` ("daemon for delegated repo tasks") says so itself. Name-based triage of this
   org produces a wrong map — which is the reason this pass cloned rather than guessed.
8. **Colleague's flight control is cooperative, never preemptive**, by explicit design:
   directives land at the *next turn boundary*, never mid-model-call or mid-tool, and
   *"a runaway process is killed by the OS/harness, not this feature."* If we borrow the
   pattern we inherit the latency floor — which is fine for guidance and wrong for a kill
   switch (**R5**). Our kill switch must not ride the flight plane.
9. **Their concurrency primitives degrade open.** The rig slot proceeds *without* a slot
   after `max_wait` (default 300 s) rather than queueing, and their presence emitter is
   fail-open. Correct for a single operator protecting one GPU; wrong as an admission gate
   for a fleet spending real money (**R6**). Copy the mechanism, not the default.
