# Platform services cluster: identity, secrets, memory, git, tasks, evidence

**Scope.** The AgentCulture services that would sit *around* a mesh: identity, secrets,
memory, task tracking, evidence/coherence scoring, git/repo bootstrapping, and the
cite-don't-copy vendoring discipline. Read for the fleet design
(`docs/design/fleet-vision.md`) after `docs/.research/fleet/agentculture.md` (the mesh/wire
survey) — this file does not repeat that survey's presence-protocol findings, only extends
its identity/secrets/steward section and adds the repos the brief named that survey didn't
cover in depth.

**Method.** All `agentculture` org repos enumerated via `gh api orgs/agentculture/repos
--paginate` (78 repos) and `OriNachum`'s personal repos via `gh api users/OriNachum/repos
--paginate`. Shallow-cloned `eidetic-cli agenda evidence-cli coherence-cli headspace-cli
code-lens-cli refactor-cli qodo-cli gitculture-cli` (org) and `agex citation-cli` (personal)
into `/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/ac/`;
`zehut`, `shushu`, `gitculture-cli`, `agentfront` were already cloned there by the earlier
survey pass and are reused, not re-fetched. Maturity cross-checked against
`https://pypi.org/pypi/<name>/json` (version, release count, project URL — to catch
namesquats) and `gh api repos/<org>/<repo> --jq .pushed_at`. **[OBSERVED]** = read in
source/docs; **[INFERRED]** = reasoning on top.

`steward` and `guildmaster` — named in the brief — return 404 under both `agentculture` and
`OriNachum` (confirmed again this pass). They are referenced throughout the ecosystem as
private infrastructure repos (`devague/docs/skill-sources.md`: *"the supplier role moved
from `steward` to `guildmaster` at the 2026-05-24 handover"*). Treat both as unverifiable;
they are covered here only by what other repos say about them.

---

## Verdict

- **Most of this cluster is one code-generation template, not nine services.** `eidetic-cli`,
  `agenda`, `evidence-cli`, `coherence-cli`, `headspace-cli`, `refactor-cli`, `qodo-cli`,
  `code-lens-cli` all carry the identical `afi-cli`/`teken`-cited scaffold: `whoami`, `learn`,
  `explain`, `overview`, `doctor`, a `culture.yaml` mesh identity, and an 11-skill
  `guildmaster` vendor kit. **Three of them never got past that scaffold** — `agenda`,
  `evidence-cli`, `refactor-cli` ship *zero* domain verbs beyond the template's own five
  (confirmed by reading `agenda/cli/_commands/`, `evidence-cli/evidence/cli/_commands/`,
  `refactor-cli/refactor/cli/_commands/` — all three trees are byte-identical in shape). A
  repo existing and a repo doing its stated job are different facts here; check the command
  tree, not the README's problem statement. [OBSERVED]
- **Identity and secrets are still vapor**, confirming the prior mesh survey: `zehut` is a
  4-file README with no code, `shushu` a 52-line `--version` scaffold. Nothing changed since
  the last pass. Do not plan to consume either. [OBSERVED, re-verified]
- **`eidetic-cli` is the one real, mature service in this cluster** — 20 PyPI releases,
  genuine `remember`/`recall`/`sweep` verbs, pluggable backends (files/mongo/neo4j via
  `data-refinery-cli[store]`), scope-aware retrieval with four search modes, lifecycle
  management that never hard-deletes. It is the closest thing here to a memory component our
  fleet design would want — but it is memory *for a single mesh-resident agent's own
  recall*, not fleet-wide task/evidence state, and it inherits the `culture.yaml`
  mesh-identity assumption our fleet does not share. WATCH, do not adopt the package as-is.
- **`agenda-cli` does not solve our work layer.** It is the pure template — no dependency
  graph, no wave/completion signal, no persistence beyond `whoami`. This matches what the
  mesh survey already found in `devague`'s `assign-to-workforce` skill: the ecosystem's
  actual task-fanout logic lives in a *skill document*, not in any of these CLIs, and even
  that skill has no completion signal. Nothing here closes the gap our fleet's admission
  control needs to close.
- **`citation-cli` is real, documented, and worth adopting as *practice*** — a genuine
  successor to a predecessor tool (`assimilai`, with a `cite migrate` path), formal
  Quote/Paraphrase/Synthesize semantics, sha256 integrity checks (`cite check`), and both
  Python (`pyproject.toml [tool.citation]`) and Node (`package.json`) surfaces. It is what
  our own PITFALLS.md-style "paid for once" discipline would look like formalized and
  automated with a verifiable manifest instead of a prose convention.
- **`coherence-cli` (18.6k lines) and `headspace-cli` (34.8k lines) are the most
  substantively-built repos in this cluster** but solve adjacent problems, not ours:
  coherence scores whether an artifact should be trusted/refreshed/repaired (a memory-hygiene
  problem), headspace is a sandboxed ephemeral-execution workspace with result compression (a
  context-budget problem). Neither touches liveness, scheduling, or state verification. WATCH
  for later (headspace's provider-abstraction and digest-pinning patterns are reusable
  engineering even if the product isn't), IGNORE for the current phase.
- **`code-lens-cli`, `qodo-cli`, `gitculture-cli`, `agex` are narrow dev-tooling utilities**
  (repo introspection, an unofficial Qodo PR-review wrapper, GitHub repo bootstrapping,
  agent-facing dev-experience briefings) with no bearing on identity, secrets, memory,
  scheduling, or state. IGNORE for the fleet.
- **`steward`/`guildmaster` remain unverifiable** — both 404 publicly, referenced only as the
  private source other repos vendor skills from. Nothing to adopt because there is nothing to
  read.

---

## Repos

| Repo | What it actually is | Maturity | Docs | Intended use case | Verdict |
|---|---|---|---|---|---|
| `zehut` (OriNachum) | Named "agents-first secrets manager" identity component. 4 files, README is 2 lines, zero code. | No PyPI package. Last push 2026-04ish (unchanged since prior survey). Pure stub. | Repo README only | Mesh identity graph (`reports_to`/`member_of`/etc. per culture#269) | **IGNORE** — nothing exists to adopt; build our own identity if/when needed |
| `shushu` (OriNachum) | Named secrets manager. `cli.py` is 30 lines, `--version` only. README: "Early scaffold — details to come." | PyPI `shushu` 0.1.0 in pyproject but scaffold-only code; effectively pre-alpha | Repo README only | Scoped secret access per identity/role (culture#270) | **IGNORE** — `culture_core/credentials.py` (already surveyed in the mesh pass) is the actual reusable secrets code in this ecosystem, not `shushu` |
| `eidetic-cli` | Agent memory CLI: `remember`/`recall`/`sweep`/`migrate` over a shared `~/.eidetic/memory` store; four recall modes (exact/approximate/keyword/hybrid), scope-aware (no private→public leak), lifecycle shadow/archive (never deletes), pluggable file/mongo/neo4j backends. | PyPI `eidetic-cli` **0.13.0, 20 releases**. Last push 2026-07-26. Real, actively maintained. | `README.md` (thorough CLI table), `docs/skill-sources.md` | Perfect-recall memory for one mesh-resident agent | **WATCH** — most mature "real" service in this cluster; matches our fleet's memory need in concept, but is single-agent recall bound to `culture.yaml` identity, not fleet-wide task/evidence state we'd write from many machines |
| `agenda` | Named "tasks analogue of guildmaster." README promises GitHub issue/priority/blocker tracking; **actual CLI ships only the template's five verbs** (`whoami`/`learn`/`explain`/`overview`/`doctor`) — no task-domain code exists in `agenda/cli/_commands/`. | PyPI `agenda-cli` 0.2.0, 3 releases (confirmed correct package via project URL — plain `agenda` on PyPI is an unrelated squat). Last push 2026-07-15. Template-stage. | `README.md`, `CLAUDE.md` | Work-state tracking (issues/priorities/blockers/next-actions) | **IGNORE** — the README's claim and the shipped code disagree; nothing here to adopt for our work layer |
| `evidence-cli` | Named "documents the evidence trail... grades it and issues a score." Same template-only pattern as `agenda` — `evidence/cli/_commands/` is the identical five-verb scaffold, no scoring/grading code present. | PyPI `evidence-cli` 0.6.1, 1 release. Last push 2026-07-23. Template-stage. | `README.md`, `AGENTS.colleague.md` | Evidence-trail scoring for a piece of work | **IGNORE** — same gap as `agenda`: README describes a product, repo ships a template |
| `coherence-cli` | Real, substantial service: five "coherence domains" (quality/meaning/signal/investiture/frames) turning artifact trust/freshness/provenance into inspectable scores; `quality` domain is fully offline rule-based, others use embeddings. Domain-real code, not template. | PyPI `coherence-cli` 0.6.1, **9 releases**. Last push 2026-07-15. 18.6k lines. Actively built. | `README.md`, `docs/domains.md` | Should an agent trust/refresh/repair/route/remember an artifact | **WATCH** — genuinely built, but scores artifact trust, not agent liveness/scheduling; adjacent to memory hygiene, not our fleet's core problem |
| `headspace-cli` | Real, substantial service: ephemeral sandboxed execution workspace ("headspace") with a 9-state lifecycle, closed-by-default policy, digest-pinned runtime profiles, Provider protocol (docker + in-memory fake), compact result-package return so raw execution logs don't flood model context. | PyPI `headspace-cli` 0.11.0, 5 releases. Last push 2026-07-30 (most recently active repo in this cluster). 34.8k lines, largest in this cluster. | `README.md` (detailed), `docs/headspace_cli_issue_requirements.docx` | Offload computation out of agent context without losing provenance | **WATCH** — engineering patterns (provider abstraction, digest pinning, intent journal + crash reconciliation) are worth studying for our own container/sandbox needs later; not a fleet-scheduling component |
| `code-lens-cli` | Four inspection verbs (`classify`/`grep`/`recent`/`profile`) for "what kind of repo is this / where's this symbol / what changed / how does it plug into neighbors." Real, narrow tool; split off from `antoine` (kata-cli). | PyPI `code-lens-cli` 0.11.0, 7 releases. Last push 2026-07-15. 7.2k lines. | `README.md` | Fast 1-call repo/codebase introspection for agent skills | **IGNORE** — useful dev-tooling, zero overlap with state/scheduling/identity |
| `refactor-cli` | README claims "atomic in-repo transformation engine" but ships only the template's five verbs, same as `agenda`/`evidence-cli` — no refactor-domain code in `refactor/cli/_commands/`. | **PyPI `refactor-cli` is a namesquat** — unrelated package "CLI tool to organize files using AI," no project URL, not AgentCulture's. AgentCulture's own repo has never actually published under that name. Last push 2026-07-15. Template-stage. | `README.md`, `CLAUDE.md` | Behavior-preserving code refactors | **IGNORE** — doubly unusable: the repo is unbuilt and the PyPI name it would want is squatted by someone else |
| `qodo-cli` | Real tool: unofficial community wrapper for Qodo (AI code reviewer) — `rules get`, `review`/`pr` (list/reply/ack/resolve PR comments via `gh`/`glab`), `config` (repo-level `.pr_agent.toml`). Zero third-party runtime deps. | PyPI `qodo-cli` 0.11.0, 8 releases. Last push 2026-07-15. 5.6k lines. | `README.md`, `docs/qodo-skills-sources.md` | Manage Qodo's review bot from the terminal | **IGNORE** — a specific SaaS integration, no relevance to a fleet's identity/state/scheduling layer |
| `gitculture-cli` | Real tool: bootstraps/maintains AgentCulture sibling repos on GitHub — create repos, scaffold the `afi-cli` python-cli template into them, create `pypi`/`testpypi` GitHub Environments for Trusted Publishing. Formerly `ghafi` (still works, not a shim). | PyPI `gitculture-cli` 1.0.0, 1 release. Last push 2026-07-15. 3.5k lines. Every GitHub-mutating verb defaults to dry-run. | `README.md` | Bootstrap new AgentCulture-pattern repos | **IGNORE** — repo scaffolding tool for *their* org's template convention, not something our project would run |
| `agex` (OriNachum, `agex-cli` on PyPI) | "Agent-operated developer-experience CLI" — non-agentic, deterministic, markdown-first briefings per backend (`agex overview --agent claude-code`, `agex learn`). | PyPI `agex-cli` **0.32.0, 33 releases** — the most actively released package in this whole cluster, but the *cloned repo's* `pyproject.toml` lags at 0.13.1, meaning the shallow clone is stale relative to what's shipped; treat the PyPI number as ground truth. Docs at culture.dev/agex. | `README.md`, `culture.dev/agex` | Deterministic per-backend developer briefings for agents | **IGNORE** — a docs/briefing generator for AgentCulture's own onboarding convention, orthogonal to our fleet |
| `citation-cli` (OriNachum) | Formal "cite, don't import" distribution pattern: Quote/Paraphrase/Synthesize semantics, sha256 integrity (`cite check`), Python (`[tool.citation]`) and Node (`"citation"` key) surfaces, `cite migrate` from predecessor `assimilai`. Docs-heavy repo (Jekyll site source), light CLI code (661 lines). | No PyPI check run (not confirmed published under this name at time of survey — docs describe `pip install citation-cli`/`npm install -g citation-cli` but repo is a docs/spec site, not the implementation). Last push ~2026-04-21. | `README.md`, `concept.md`, `python.md`, `npm.md`, `migration.md`, `when-not-to-use.md`, culture.dev/citation-cli | Formalize cite-don't-copy vendoring with tracked integrity across diverging consumers | **ADOPT the practice, WATCH the tool** — see Adoption notes |
| `steward` / `guildmaster` | Referenced throughout the ecosystem as the private supplier of vendored skills (`cicd`, `communicate`, the 11-skill guildmaster kit). Not public under either org. | Unverifiable — 404 on `agentculture` and `OriNachum` both. | None accessible | Skill-kit supplier for the whole org | **IGNORE** — cannot evaluate what we cannot read; do not plan around it |

---

## Adoption notes

**What we would install:** nothing from this cluster as a running dependency. The only
concrete adoption candidate is a *practice*, not a package: the citation-cli discipline
(Quote/Paraphrase/Synthesize + `cite check` integrity manifest) applied to our own
PITFALLS.md-driven vendoring habit — e.g. when we lift `culture_core/credentials.py`
wholesale (already flagged in the mesh survey's "what to steal" list), we'd record it as a
tracked citation with a sha256 and a source pin, not a silent copy-paste. That costs: reading
`citation-cli`'s actual CLI implementation (not yet done this pass — the survey read the docs
site, not the 661-line implementation) before deciding whether to install the tool itself or
just imitate the manifest shape by hand in our own `pyproject.toml`.

**What it would replace:** nothing existing in our project — we have no vendoring tool today,
only a prose convention (PITFALLS.md, "paid for once"). Adopting citation-cli's manifest
format would formalize that convention with a verifiable integrity check; it would not
replace PITFALLS.md's role of recording *why* a trap was paid for.

**What we would explicitly NOT install:** `eidetic-cli`, `coherence-cli`, and `headspace-cli`
are the three genuinely-built services here, and all three are tempting because they're
real. Resist installing any of them now — each one assumes the `culture.yaml` mesh-identity
model (`suffix`+`backend`) our fleet design has not adopted (per the mesh survey: "roles are
not modelled" in their ecosystem, and our fleet's R3 wants roles as configuration). Installing
one early would import that identity assumption by the back door before we've decided our
own. Revisit `eidetic-cli` specifically once the fleet has a concrete need for cross-machine
agent memory, not single-resident recall.

**Cost of the "watch" list, if later adopted:** `headspace-cli`'s provider abstraction
(`capabilities/create/run/inspect/read/write/stop/remove`, digest-pinned profiles, fake
provider for dependency-free testing) is the one piece of engineering in this cluster most
directly reusable for our own future sandboxing needs — but it is a 34.8k-line dependency
with its own lifecycle and policy model to absorb, not a drop-in library.

---

## Traps

- **README claims and shipped code diverge in this cluster more than in the mesh-core repos
  surveyed earlier.** `agenda`, `evidence-cli`, and `refactor-cli` all describe a real domain
  product in prose and ship only the identical five-verb scaffold. Always read the actual
  command tree (`<pkg>/cli/_commands/`), not just the README's opening paragraph, before
  scoring maturity in this ecosystem.
- **PyPI package names can be squatted by unrelated projects.** `refactor-cli` on PyPI is "CLI
  tool to organize files using AI" with no project URL — nothing to do with AgentCulture. Cross-check `project_urls`/`author` in the PyPI JSON against the repo's own `pyproject.toml`
  before citing a PyPI version as evidence of *this* project's maturity. The plain `agenda`
  package (vs. the correct `agenda-cli`) is the same trap.
- **A shallow clone's `pyproject.toml` version can lag the actually-published PyPI version.**
  `agex`'s clone read 0.13.1 while PyPI serves 0.32.0 (33 releases) — the clone was simply
  behind main at the moment it was made. Treat PyPI's JSON as the maturity source of truth,
  the clone as the code-reading source of truth, and don't average them.
- **"Cited from teken (afi-cli)" is a boilerplate marker, not a maturity signal.** Nearly
  every repo in this cluster (and the wider org) carries that same sentence in its README.
  It tells you the repo used a code generator; it tells you nothing about whether the
  generated stub was ever filled in.
- **`steward`/`guildmaster` 404s are consistent across two separate survey passes** (this one
  and the earlier mesh survey) — this is not a transient access issue, they are genuinely
  private. Don't re-attempt `gh api repos/agentculture/steward` expecting a different result
  without a specific reason to believe access changed.
