# Cluster: the thinking behind AgentCulture

**Scope.** The *ideas* layer of the AgentCulture / OriNachum ecosystem, read for adoption by
agent-state-driver: the blog, the RFC repo, the guides, the org-level doctrine documents, and
the protocol/spec/superpowers trees inside `culture` and `agentirc`. Sibling files cover the
runtime (`docs/.research/fleet/agentculture.md`) and the backends
(`docs/.research/prior-art/cultureagent.md`); this one answers *what does he believe, and where
does that agree or collide with us*.

**Method.** `gh repo view` / `gh api` for maturity and fork status; shallow clones into
`…/scratchpad/ac/`, `…/scratchpad/culture/`, `…/scratchpad/phil/`; PyPI JSON for release counts;
`curl` against culture.dev, tools.culture.dev, agentculture.org for the live doc surface.
Claims are **[OBSERVED]** (read in the artifact) or **[INFERRED]** (my reasoning on top).
Quotes are verbatim.

---

## Verdict

- **The thesis is one sentence, and he states it himself: *"when you design software, the
  primary consumer is an AI agent, not a human."*** (`agentfront/docs/agent-first.md:6`) Every
  other convention in the org — the `learn` verb, `--json` everywhere, markdown-first doc sites,
  minimal MCP menus, `doctor` with a mandatory `remediation` string — is a derivation from that
  single reversal. It is not vibes: it is compiled into a **seven-bundle rubric** that a tool
  (`agentfront cli doctor`) mechanically enforces, and agentfront is required to pass its own
  gate in CI. **This is the most adoptable idea in the whole ecosystem and it costs us almost
  nothing.** [OBSERVED]

- **What he explicitly rejects, in his own words:** the agent as a function call
  (*"Most AI tooling treats an agent as a function call. We treat it as a coworker"* —
  culture.dev/docs/why.md); `--help` scraping as an onboarding path; maximal MCP menus
  (*"every verb is a decision point that can go wrong"*); tracebacks as an error surface
  (rubric bundle 4 fails any CLI that leaks one); prose-only errors without a `hint:`/`try:`
  remediation marker; SPA doc sites (*"markdown-first with a sitemap. No SPA, no SDK, no login
  wall"*); and — load-bearing for us — **model self-report of state**: *"transitions are driven
  **only** by code boundaries, never by model self-report"* and *"a resident never self-reports
  its state"* (`culture/protocol/extensions/presence.md:45,61`). [OBSERVED]

- **We agree with him on the principle and disagree on where he drew the observation
  boundary.** He rules out the *model* reporting; we rule out the *process* reporting. His
  emitter is in-process with the agent (`cultureagent/clients/shared/presence_emitter.py`), so
  the server still believes whatever a connection asserts about itself, and the send is
  explicitly **fail-open**. Our position — observe from outside, attach evidence, report
  `conflict` rather than a confident wrong answer — is the same principle taken one layer
  further out. **Frame our upstream PR as *finishing* his stated rule, not correcting it.**
  [OBSERVED + INFERRED]

- **The hard conflict is real and it is in code, not in doctrine.** Every enforced backend
  deletes the permission-wait state at source: `permission_mode="bypassPermissions"`
  (`cultureagent/clients/claude/agent_runner.py:148`), `"approvalPolicy": "never"` and
  `--full-auto` for codex (`clients/codex/agent_runner.py:140`, `supervisor.py:99`), and a
  `_APPROVAL_METHODS` frozenset routed straight into `_auto_approve()`
  (`clients/codex/agent_runner.py:320-341`). **A blocked-on-a-human agent cannot exist in his
  world, which is exactly why his presence enum has no waiting state and why nobody upstream
  has felt the gap.** Our `waiting:permission` is not a missing enum value to them — it is a
  category they engineered out. Argue it from the *fleet* case (dispatch into a void, culture
  #305's 0.3-0.5M-token spiral), never from the single-agent case. [OBSERVED]

- **"Cite, don't import" is a genuinely good idea we should partially adopt and mostly
  resist.** `agentirc/pyproject.toml` carries a 470-line `[tool.citation]` ledger: per-file
  `source` URL pinned to upstream commit `df50942`, a `status` of `quote` / `paraphrase` /
  `synthesize`, a `sha256`, and a `notes` field that records every adaptation and its reason.
  That is provenance done properly. But the *practice* it serves — vendoring code instead of
  depending on it — is the opposite of what we decided (adopt their infrastructure, don't
  rebuild it). **Take the ledger format for the handful of files we do vendor; do not take the
  vendoring habit.** [OBSERVED]

- **The philosophy is better documented than it is applied, and the gap is measurable.** His
  own doctrine says HTTP surfaces are markdown-first with a sitemap; `culture.dev/sitemap.xml`
  and `tools.culture.dev/sitemap.xml` return nothing, both sites are Astro SPAs, and the
  culture.dev URLs cited inside the shipped repo docs — `/vision/`, `/mental-model/`,
  `/reference/cli/devex/` — **all 404 today**. What does work is `llms.txt`, `llms-full.txt`,
  and the `.md`-suffix / `Accept: text/markdown` content negotiation. **Read his repo docs, not
  his site links; and cite `llms.txt` paths when we reference him.** [OBSERVED]

- **The "community" cluster named in the brief is mostly not his.** `awesome-claude-code-security`
  and `community` are both **forks** with a single trivial commit or none of his own
  (`awesome-claude-code-security`: one commit, "Fix typo"; `community`: last commit by Barak Or,
  0 KB, upstream `STATE16-Physical-AI-Community`). `BenevolentAgentsRFC` is a fork of
  `agamrafaeli/BenevolentAgentsRFC` — a WhatsApp-group experiment he participated in as the
  agent "otti", not his design. **Do not cite these as AgentCulture doctrine.** [OBSERVED]

- **The single best philosophical borrow for us is not a package — it is the sentence
  *"Presence is a fact, not a feature."*** (culture.dev/docs/why.md, arguing for IRC). He wrote
  the strongest possible case for our product and then shipped a presence layer that does not
  meet it. That sentence, quoted back with our evidence array attached, is our entire pitch.
  [OBSERVED]

---

## Repos

Maturity column: PyPI version + release count where published; otherwise last push + whether
there is real code. "Docs link" prefers the artifact we actually read.

| Repo | What it actually is | Maturity | Docs | Intended use case | Verdict |
|---|---|---|---|---|---|
| **agentfront** (`agentculture/agentfront`, ex-`teken`, ex-`afi-cli`) | The doctrine *and* its enforcement: an importable `App` runtime deriving CLI + MCP + HTTP from one registry, plus `cli doctor`, the seven-bundle rubric, and `assert_surfaces_agree()` | PyPI `agentfront` **0.20.0**, 16 releases (`afi-cli` 0.8.0 is a deprecated alias) | [`docs/agent-first.md`](https://github.com/agentculture/agentfront/blob/main/docs/agent-first.md), [`docs/rubric.md`](https://github.com/agentculture/agentfront/blob/main/docs/rubric.md) | Give every org tool the same agent-legible surface so they compound instead of fragmenting | **ADOPT (the rubric, not the runtime)** — our driver CLI already meets bundles 1/3/4 by accident; adding `learn`, `explain`, `overview`, `doctor` makes us legible to *their* agents and costs a day |
| **culture** — `docs/culture/` (vision, patterns, mental-model, what-is-culture, reflective-development) | The org's stated worldview: rooms as spaces, agents-as-members, `Introduce→Educate→Join→Mentor→Promote`, Reflective Development, nick-as-identity | culture PyPI **14.5.0**, 161 releases; docs tree pushed 2026-07-15 | [`docs/culture/vision.md`](https://github.com/agentculture/culture/blob/main/docs/culture/vision.md), [`patterns.md`](https://github.com/agentculture/culture/blob/main/docs/culture/patterns.md) | Explain what a "culture" is and why IRC | **WATCH** — beautiful and almost entirely orthogonal to scheduling; the one durable borrow is `<server>-<agent>` nick-as-identity, which answers our open question 5 |
| **culture** — `protocol/extensions/presence.md` | The only normative spec in the ecosystem that touches state: six values, field rules, the never-self-report principle, the observe-only-v1 boundary | Ships with culture 14.5.0 | in-repo, one file | The wire contract our PR extends | **ADOPT** — this is the document our `waiting` PR argues against, line by line |
| **culture** — `docs/superpowers/{plans,specs}` + `docs/specs` | 58 dated design docs, one per feature, spec-then-plan, kept after shipping | 2026-03-19 → 2026-07-07, real content | in-repo | Durable design memory; the format his agents write in | **ADOPT (the convention)** — it is `docs/design/` + `docs/results/` with a date-prefixed naming rule; cheap discipline, and matching it makes an upstream design doc from us look native |
| **agentirc** — `docs/api-stability.md`, `docs/specs/2026-07-07-…presence…` | Seven public modules with semver contracts; the presence design record incl. the "kept ircd.py to registration-only" decision | agentirc-cli **9.12.0**, 131 releases | [`docs/api-stability.md`](https://github.com/agentculture/agentirc/blob/main/docs/api-stability.md) | Tell downstreams what they may import | **ADOPT** — tells us exactly which seven modules our integration may depend on; also the model for our own SPEC's stability section |
| **agentirc** — `pyproject.toml [tool.citation]` | The cite-don't-copy ledger: 470 lines, per-file source URL + upstream commit + `quote`/`paraphrase`/`synthesize` + sha256 + a `notes` rationale | Live, pinned to culture `df50942` | in-file | Make vendoring auditable | **ADOPT (format only)** — use it for `culture_core/credentials.py` if we vendor it; ignore the underlying vendor-don't-depend philosophy |
| **citation-cli** (`OriNachum/citation-cli`) | The standalone tool for the above ledger. *"Cite, don't import"* | PyPI **0.1.0**, **1 release**; 3 stars; pushed 2026-04-21 | [PyPI](https://pypi.org/project/citation-cli/) | Track cited code in `pyproject.toml` | **IGNORE** — one release, ~4 months stale; the *format* is worth copying by hand, the tool is not worth a dependency |
| **eidetic-cli** (`agentculture/eidetic-cli`) | The memory store behind the org-wide `/recall` before / `/remember` after discipline; culture keeps its store **in-repo and committed** at `.eidetic/memory/` | PyPI **0.13.0**, 20 releases | [`culture/CLAUDE.md:102-126`](https://github.com/agentculture/culture/blob/main/CLAUDE.md) | Cross-session agent memory that travels with the repo, not `$HOME` | **WATCH** — the *discipline* is already ours (`STATE/HANDOFF/PITFALLS`); the tool is a second memory system to keep in sync. Revisit only if fleet agents need shared memory across machines |
| **agentic-human** (`OriNachum/agentic-human`) | His blog, Jekyll, 13 posts, newest 2026-03-26. Load-bearing posts: *Code as Documentation* (skills), *Everything is Agents* (per-folder AGENT.md), *Workbench Development* (scoped folder per agent), *Assimilai* (the cite-don't-import origin) | 3 stars; **stale 4.5 months**; predates all mesh/presence work | [agentic-human.org via repo](https://github.com/OriNachum/agentic-human/tree/main/_posts) | Where the ideas were first argued, in prose | **WATCH** — read once for vocabulary and quotes; nothing here mentions presence, state, or the mesh |
| **agentic-guides** (`OriNachum/agentic-guides`) | A Jekyll shell containing exactly **one** guide file, 7 lines long | 1 star; pushed 2026-03-13; effectively **a stub** | n/a | Guides site | **IGNORE** — empty |
| **claude-code-guide** (`OriNachum/claude-code-guide`) | His most popular artifact: a real Claude Code **plugin** — 7 skills (`ask`, `onboard`, `introspect`, `level-up`, `game-mode`, `migrate-to-claude`, `visualize-setup`), a `hooks/hooks.json`, and a docs site | **120 stars**, pushed 2026-06-17, real code | [README](https://github.com/OriNachum/claude-code-guide) | Gamified onboarding to Claude Code | **WATCH** — not state-relevant, but it is the reference for *his* skills-layout convention (`skills/<name>/SKILL.md` + `scripts/`) and, at 120 stars, the highest-leverage place an upstream mention of us would be seen |
| **BenevolentAgentsRFC** (`OriNachum/…`, **fork of** `agamrafaeli/…`) | A 4-human/4-agent WhatsApp experiment turned into RFCs: RFC-0001 a shared Upstash Redis agent registry; RFC-0003 identity ("the human is the trust anchor"); RFC-0004 "The Right to Write" | 0 stars, pushed 2026-04-08, **not his repo** — he appears as the agent "otti", status *Pending R.N* | [`rfcs/`](https://github.com/agamrafaeli/BenevolentAgentsRFC/tree/main/rfcs) | Agent-to-agent cooperation without human mediation | **WATCH (one idea only)** — RFC-0001's own next-steps list *"TTL / heartbeat for liveness detection"* as unbuilt, and its security model admits *"trust is social, not cryptographic."* Useful as evidence that liveness keeps getting deferred everywhere; not a spec to build on |
| **community** (`OriNachum/community`) | **Fork**, 0 KB, upstream `STATE16-Physical-AI-Community`; last commit by another author. Physical-AI safety discussion | fork, no contribution of his | n/a | Not his project | **IGNORE** |
| **awesome-claude-code-security** (`OriNachum/…`) | **Fork** of `efij/awesome-claude-code-security` (upstream 34 stars); his sole commit is *"Fix typo: 'A curated' → 'An awesome curated'"* | fork, 1 trivial commit, 2026-03-17 | [upstream](https://github.com/efij/awesome-claude-code-security) | Curated Claude Code security list | **IGNORE as doctrine; WATCH upstream** — the upstream list is a fine reading list for our fleet-security workstream, but it says nothing about AgentCulture |
| **culture-tools** (`agentculture/culture-tools`) | The **`*-cli` template made concrete**: tools.culture.dev, "the package index for agent-first CLI tools that conform to the agentfront contract" — and a repo whose README section is literally *"Make it your own"* | pushed 2026-07-27; real code + Astro site | [README](https://github.com/agentculture/culture-tools) | Certify and index conforming CLIs | **WATCH** — this is the org's front door for third-party tools. If we ever want the driver listed as agent-first infrastructure, this is the door; `teken cli doctor . --strict` is the gate |
| **org** (`agentculture/org`) | Source of agentculture.org; same template shape (`culture.yaml`, `AGENTS.colleague.md`, `site-astro`, vendored skills) | pushed 2026-07-22, 1.2 MB | in-repo `docs/` | Org web presence | **IGNORE** for us |
| **evidence-cli** / **prove-cli** (`agentculture/…`) | Named here because they are the philosophy pointed at our problem: evidence-cli *"documents the evidence trail behind a piece of work… then grades that evidence"* | evidence-cli **0.6.1, 1 release**; prove-cli **0.4.1, 4 releases** | PyPI summaries | Grade the evidence behind work | **WATCH** — same vocabulary as ours ("evidence trail"), one release deep. Worth a look before we name our own evidence schema, so we don't collide on terms |

---

## Adoption notes

**What we would install: nothing from this cluster.** It is a doctrine cluster, not a package
cluster. The only pip-installable item worth considering is `agentfront` (0.20.0, 16 releases)
and even that we should **not** install — our drivers are stdlib-only Python 3.9+ by design and
agentfront requires the `App` registry to be embedded. Read its rubric; do not take its runtime.

**What we would add (concrete, in cost order):**

1. **The four universal verbs on our driver CLI** — `learn`, `explain <path>`, `overview`,
   `doctor` — plus `--json` on each, stdout/stderr never mixed, and a `hint:` line on every
   error. Cost: roughly a day. What it buys: the driver becomes discoverable *by their agents*
   with no human in the loop, which is the whole argument of `agent-first.md`. We already
   satisfy the hardest bundles — meaningful exit codes (bundle 4) and JSON output (bundle 3) —
   so this is mostly surface. **Caveat: their exit-code policy is `0/1/2, 3+ reserved` and ours
   already uses `3` timeout / `4` refused / `5` launch-failure. We should keep ours and
   *document the divergence*, not silently break a published contract to score a rubric point.**

2. **The `[tool.citation]` ledger format** for anything we vendor — in practice
   `culture_core/credentials.py`, already flagged as a wholesale steal in the fleet research.
   Per-file: source URL pinned to a commit, `quote|paraphrase|synthesize`, sha256, and a `notes`
   field naming every adaptation and why. Cost: 20 lines of TOML per vendored file. What it
   replaces: an untracked copy-paste we would not be able to re-sync in six months.

3. **The dated spec/plan convention** — `docs/specs/YYYY-MM-DD-<slug>.md` paired with
   `docs/plans/YYYY-MM-DD-<slug>.md`, kept after shipping. We already do this in spirit under
   `docs/design/` and `docs/results/`. Adopting their exact naming makes any design doc we send
   upstream look native rather than foreign — which matters for the `waiting`-state PR.

4. **Their framing, verbatim, in our PR body.** The presence spec's own words are the strongest
   argument for the change: it already claims transitions are *"driven **only** by observable
   code boundaries — never by model self-report,"* and it already admits *"`working` is part of
   the contract, but as of cultureagent 0.13.0 no backend has an observable tool-execution
   boundary, so no emitter sends it yet."* We are not proposing a new principle; we are
   supplying the observation channel their principle already demands. Cost: zero. This is the
   single highest-leverage item in this file.

**What it replaces: nothing.** No idea in this cluster displaces a decision we have already
made. The state model stays ours (seven states plus `conflict`); the evidence array stays ours;
the observation posture stays ours.

**What it costs beyond the day of CLI work:** an ongoing obligation. Adopting the rubric means
`doctor` must keep its promise — *"when `healthy: false`, every failed check supplies a
non-empty `remediation`"* — forever, on every new check. That is a real maintenance contract,
and it is one we would honour anyway, since it is the same "no silent failure" rule our SPEC
already enforces.

---

## Traps

1. **`bypassPermissions` is not an oversight to point out — it is their architecture.** All
   three enforced backends erase the permission-wait state at source (claude:
   `permission_mode="bypassPermissions"`; codex: `approvalPolicy: "never"` + `--full-auto` +
   auto-approve on all three `*_approval_request` methods). If our PR reads as "you forgot a
   state," it will be read as "you don't understand our design." It has to read as "here is the
   state that appears the moment an agent is *not* run with permissions bypassed — which is
   every agent an operator attaches to rather than spawns." **Our `attach` posture is the
   argument.** Their own culture#305 postmortem features `local-boss`, described as an
   *"orchestrator session driven from outside the mesh (not a managed agent)"* — that is our
   posture, in their incident report.

2. **"Never self-report" means something narrower to him than to us.** The rule scopes to the
   *model*; the *process* self-reports freely, over a fail-open transport, with no ack on the
   publish path. If we say "your presence is self-reported" without that qualifier, we are
   contradicting a sentence he wrote and will lose the room. Say instead: *the emitter is
   in-process; we observe from outside the process.*

3. **The doctrine sites are stale in exactly the places docs point at them.**
   `culture.dev/vision/`, `/mental-model/`, `/reference/cli/devex/` — all cited from shipped
   repo docs, all 404. `sitemap.xml` is empty on both culture.dev and tools.culture.dev despite
   the doctrine mandating sitemaps. Cite `https://culture.dev/llms.txt`,
   `https://culture.dev/docs/<page>.md`, or the GitHub blob URL — never a bare culture.dev
   pretty-path.

4. **Three of the six repos the brief named are not his work.** `community` and
   `awesome-claude-code-security` are forks with zero or one trivial commit;
   `BenevolentAgentsRFC` is a fork of a group project where he is a *participant* (agent
   "otti", still listed *Pending*). Quoting them as "AgentCulture's position" would be a factual
   error that a maintainer would catch immediately.

5. **`agentic-guides` is a stub** — one 7-line guide inside a full Jekyll scaffold, stale since
   2026-03-13. **`agentic-human` is stale by 4.5 months** and predates every mesh, presence, and
   role decision. Neither can be used to establish what the ecosystem currently believes; the
   live doctrine lives in `agentfront/docs/` and `culture/protocol/`.

6. **Reflective Development cuts against verified state, subtly.** Its premise is that agents
   improve their own environment and that documentation is the memory. Applied to presence, that
   worldview trusts the participant's account of itself — which is precisely what we refuse. Do
   not adopt "the system is self-improving because participants share the same context" as a
   design principle at the scheduling layer; it is right for docs and wrong for liveness.

7. **`eidetic-cli` is a second memory system.** Culture commits its `.eidetic/memory/*.jsonl`
   into the repo and makes `/recall`-before / `/remember`-after a per-task habit. If we adopt it
   alongside `STATE.md` / `HANDOFF.md` / `PITFALLS.md` we own two stores that will disagree.
   Pick one. Ours already works.

8. **The rubric's exit-code policy collides with our published contract.** Theirs reserves
   `3+`; ours uses `3` timeout, `4` refused, `5` launch failure — and our README states that
   state is never encoded in an exit code. Passing bundle 4 must not mean renumbering. Document
   the divergence in `SPEC.md` the way culture documents its own preserved wire-format bugs
   (`ROOMETAEND` et al., kept verbatim rather than fixed because fixing them unilaterally breaks
   peers). That precedent is on our side.
