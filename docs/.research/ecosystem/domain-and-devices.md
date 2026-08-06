# Domain and device agents — the long tail, and the pattern behind it

**Scope.** 34 repos named in the brief (`jetson*`, `dgx-spark-cli`, `rtx-spark-cli`,
`reachy*`, `fleet-cli`, `sensibo-cli`, `webcam-cli`, `media-cli`, `face-cli`,
`face-recognition-cli`, `harmonics-cli`, `shell-cli`, `webglass-cli`, `storybook-cli`,
`arxivist`, `learn-cli`, `spanish-cli`, `french-cli`, `telegram-agent`, `office-agent`,
`tipalti`, `knowledgebase-cli`, `data-refinery-cli`, `unsloth-cli`, `tensor-cli`,
`reduce-cli`, `prove-cli`, `autonomous-intelligence`), plus `teken` (the generator, found
by following citations — not in the original list). `reachy-nova` **404s** — does not
exist under `agentculture` (renamed, deleted, or never public; not investigated further).

**Method.** Metadata for all 33 org repos pulled via `gh api repos/agentculture/<name>`.
PyPI JSON pulled for every plausible package name. Five repos shallow-cloned and
tree-diffed to find the template boundary: `jetson-orin-cli` (stub-shaped per tree),
`dgx-spark-cli` (domain-shaped per tree), `reduce-cli` + `tensor-cli` (generic-named,
suspected stubs), `telegram-agent` (integration-shaped). Once the template was confirmed,
five more were cloned to test the boundary against repos the brief flagged as
structurally different: `shell-cli`, `webglass-cli`, `sensibo-cli`, `webcam-cli`,
`jetson-thor-cli`. `OriNachum/autonomous-intelligence` cloned separately — it predates the
org and is not built on the template. Citations below are `repo/path` relative to
`…/scratchpad/ac/`. **[OBSERVED]** = read in source; **[INFERRED]** = reasoning on top.

---

## Verdict

- **There is one template, and it is a real code generator, not a copy-paste habit.**
  Every repo in this cluster (`autonomous-intelligence` excepted) ships identical
  boilerplate: `.claude/skills/` (the same 18 skill names), `culture.yaml`, `CLAUDE.md`,
  `pyproject.toml`, `docs/skill-sources.md`, `sonar-project.properties`, and a Python
  package with `cli/_commands/{whoami,learn,explain,overview,doctor,cli}.py` plus
  `tests/{test_cli.py,test_cli_introspection.py}` — down to identical file names. Every
  README states the same sentence: *"An agent-first CLI cited from
  [teken](https://github.com/agentculture/teken) (`afi-cli`)."* **`teken` (PyPI, v0.20.0,
  17 releases) is the generator** — "Create Agent First products." This is a cookiecutter
  for agent-fronted device/domain CLIs, actively maintained, more mature by release count
  than most of what it generates. [OBSERVED: repo trees, READMEs, `teken` PyPI]
- **The template has two states, and most repos in this list are in the empty one.**
  Six boilerplate commands (`whoami/learn/explain/overview/doctor/cli overview`) ship in
  *every* repo regardless of domain. Domain-specific verbs are a separate, optional layer
  added by hand afterward. `reduce-cli`, `tensor-cli`, and (surprisingly, given its name)
  **`jetson-orin-cli` itself** have zero domain commands — only the six boilerplate ones.
  `dgx-spark-cli` and `jetson-thor-cli` have real domain modules (`monitor.py` 467 lines,
  `swap.py` 471 lines, reading `/proc` and `statvfs` directly). **The repo existing, and
  even being on PyPI with several releases, says nothing about whether there is a product
  behind the name — check for files beyond the six.** [OBSERVED: file trees + line counts]
- **`shell-cli` and `webglass-cli` are the two repos worth reading past the table, and
  they are at opposite ends of the same idea.** Both are a "guarded operation plane": a
  policy gate + evidence contract sitting between an agent's intent and a real side
  effect (local shell/fs vs. web/browser). `shell-cli` has a working `Operation` model,
  a policy evaluator, and real `fs.*`/`process.*` execution with mandatory `--apply` for
  mutations — but its own README opens with **"A guard, not a sandbox"**: the gate reads
  the command string and is bypassable by `sh -c`, pipelines, and any interpreter that
  takes code as an argument; there is no namespace/container isolation.
  `webglass-cli`'s README states outright: **"Status: pre-implementation… none of these
  verbs exist yet."** It is a spec (issue #1) and an introspection shell, nothing more.
  [OBSERVED: `shell-cli/README.md`, `webglass-cli/README.md`]
- **`reachy-mini-cli` is the maturity outlier by an order of magnitude** — 0.47.0, 37 PyPI
  releases, 5207 KB repo, updated 2026-08-03 (two days before this survey). Everything
  else in the cluster tops out in the single digits or low teens of releases. If AgentCulture
  has a flagship device product, it's this one, not the NVIDIA workstation family.
  [OBSERVED: PyPI JSON, `gh api`]
- **`autonomous-intelligence` (234 stars, OriNachum personal) is not part of this pattern
  at all.** It predates the org, is not built on `teken`, has no `culture.yaml`/mesh
  identity, and its README is a hand-maintained checklist for a physical Raspberry
  Pi + Jetson voice-and-vision companion robot ("Tau"). It is OriNachum's biggest project
  by stars for reasons unrelated to fleet orchestration — it is a robotics hobby project,
  not infrastructure. [OBSERVED: `autonomous-intelligence/README.md`]
- **None of the 33 org repos in this cluster touch agent *state* or *fleet scheduling*.**
  They are device/domain operation surfaces (CLI verbs an agent calls) or guarded
  execution planes (policy + evidence around a side effect). The closest thing to our
  concern — presence, waiting states, fleet dispatch — lives in `agentirc`/`culture`,
  already covered in `docs/.research/fleet/agentculture.md`, not here. [INFERRED from
  scope of every README read]
- **Practical read for us: nothing here is a dependency candidate.** We don't run Jetson
  hardware, Reachy robots, Sensibo ACs, or drones, and we don't need a language tutor or
  an arXiv indexer. The one transferable *idea*, not code, is `shell-cli`'s
  guard-not-sandbox operation model — worth a glance if agent-state-driver ever needs to
  mediate a `send` payload rather than just report state, but it is pre-1.0 and explicitly
  disclaims being a security boundary.

---

## Repos

| Repo | What it actually is | Maturity | Docs | Intended use | Verdict |
|---|---|---|---|---|---|
| `jetson` | Agent+CLI for Jetson Thor/AGX Orin device ops (setup, container builds, deploy) | not on PyPI checked; pushed 2026-07-15; Shell, 193 KB | repo README | Jetson fleet device ops | IGNORE — no hardware overlap |
| `jetson-orin-cli` | Named for Jetson Orin, but **is the bare `teken` stub** — only whoami/learn/explain/overview/doctor, no domain verbs, README still says "Make it your own" | PyPI 0.5.0, 2 releases | repo README | Orin Nano/NX/AGX provisioning (unbuilt) | IGNORE — unbuilt stub |
| `jetson-thor-cli` | Jetson Thor device ops — **has real domain code**: `monitor.py`, `swap.py`, `machine.py`, `_probe.py` reading `/proc` directly | PyPI 0.5.0, 3 releases | repo README | Thor provisioning/inference/ops | IGNORE — no hardware overlap |
| `jetson-arena` | Benchmarks a Jetson device against a full model stack (VAD+STT+LLM+TTS), publishes results + Docker recipes; also runs the public arena site | PyPI 0.6.2, 4 releases | repo README | Jetson model-stack benchmarking | IGNORE |
| `jetson-ai-lab-cli` | Discord bot: fetches/indexes Jetson AI Lab docs, answers community questions | not on PyPI | repo README | Community support bot | IGNORE |
| `dgx-spark-cli` | DGX Spark (Grace-Blackwell) workstation ops — real domain code: GPU/memory/thermal/disk/container/network/process telemetry, swap management | PyPI 0.7.1, 13 releases | repo README | Workstation health/ops | IGNORE — no hardware overlap |
| `rtx-spark-cli` | Same shape as dgx-spark-cli for RTX workstations | PyPI 0.3.0, 4 releases | repo README | Workstation ops | IGNORE |
| `reachy-mini-cli` | Reachy Mini robot device/app/runtime ops. **Maturity outlier**: 5.2 MB repo, most recently pushed (2026-08-03) | PyPI 0.47.0, **37 releases** | repo README | Robot device ops, flagship product | IGNORE — no hardware overlap, but note as their most mature CLI |
| `reachy-mini-mcp` | MCP server to control a Reachy Mini (server or sim) | PyPI 0.3.0, 3 releases | repo README | MCP-based robot control | IGNORE |
| `reachy-lobes` | Fuses reachy-mini-cli with a locally-served vLLM model ("lobes-cli") for a fully local robot brain | PyPI 0.5.0, 1 release | repo README | Local-inference robot cognition | IGNORE |
| `reachy-nova` | **404 — does not exist** under agentculture | n/a | n/a | n/a | n/a |
| `fleet-cli` | Multi-drone (UAV) coordination CLI, built on `drone-cli` | PyPI 0.4.1, 2 releases | repo README | Drone swarm ops | IGNORE — name collision with our "fleet" concept only, no relation |
| `sensibo-cli` | Sensibo smart-AC control: device discovery, sensor collection, automation rules. **Heavily built out** — 27 command files incl. schedule/rule/automation/mcp/service | PyPI 0.7.1, 4 releases | repo README | Home AC automation | IGNORE |
| `webcam-cli` | USB webcam/mic capture: enumerate, stream, record | PyPI 0.9.0, 4 releases | repo README | Local media capture | IGNORE |
| `media-cli` | Local media I/O device plane composing webcam-cli, owns routing/playback | PyPI 0.6.2, 2 releases | repo README | Media device orchestration | IGNORE |
| `face-cli` | Browser-rendered pseudo-3D face for robot/kiosk gaze+expression | PyPI 0.7.1, 3 releases | repo README | Robot expression surface | IGNORE |
| `face-recognition-cli` | Face recognition/enrollment, extracted out of reachy-mini-cli's OpenCV engine | PyPI 0.8.0, 3 releases | repo README | Identity from camera | IGNORE |
| `harmonics-cli` | Non-speech audio signals (chimes/tones) mapped to agent intent/confidence/urgency | PyPI 0.8.0, 6 releases | repo README | Non-verbal agent-to-human signaling | IGNORE |
| `shell-cli` | **Guarded local-ops plane**: policy gate + evidence + execution for fs/process ops, `--apply` required for mutation. Explicitly "a guard, not a sandbox" — bypassable, no isolation | PyPI 0.14.0, 7 releases; real `Operation`/`HostRunner` code, `git`/container runner not yet built | repo README + `docs/threat-model.md` | Safe local execution substrate under a harness | WATCH — closest conceptual neighbor if we ever mediate `send` payloads, but pre-1.0 and self-disclaimed as non-adversarial-safe |
| `webglass-cli` | **Guarded web-ops plane** — spec only. README: "pre-implementation… none of these verbs exist yet" | PyPI 0.5.0, 4 releases; ships only introspection CLI | repo README + issue #1 | Safe web/browser execution substrate | IGNORE for now — nothing built; revisit if it ships |
| `storybook-cli` | Helps an agent build a shareable site/artifact recapping its work, styled after the AgentCulture site | PyPI 0.6.1, 2 releases | repo README | Agent work-summary publishing | IGNORE |
| `arxivist` | Fetches arXiv papers, maintains a KB, implements and benchmarks paper solutions | PyPI 0.2.0, 3 releases | repo README | Research-paper agent | IGNORE |
| `learn-cli` | CLI/MCP/web front for stepwise learning; fronts spanish-cli and french-cli, generalizes to other learnable domains | PyPI 0.7.0, 10 releases | repo README | Learning-domain front-end | IGNORE |
| `spanish-cli` | Claude-driven private Spanish tutor: progress tracking, stories, practice | PyPI 0.7.0, 4 releases | repo README | Language tutoring | IGNORE |
| `french-cli` | Same shape as spanish-cli, for French | PyPI 0.6.0, 4 releases | repo README | Language tutoring | IGNORE |
| `telegram-agent` | Agent-first Telegram community management | PyPI 0.3.1, 1 release | repo README | Telegram community ops | IGNORE |
| `office-agent` | Manages office desk/meeting-room bookings | **not on PyPI** | repo README | Office facility management | IGNORE |
| `tipalti` | CLI for the Tipalti payments platform | PyPI 0.5.0, 7 releases | repo README | Payments-platform ops | IGNORE |
| `knowledgebase-cli` | Manages Amazon Bedrock Knowledge Bases (data sources, ingestion, RAG retrieval) | PyPI 0.5.0, 4 releases | repo README | Managed-RAG ops | IGNORE |
| `data-refinery-cli` | Data quality (validation, dedup, freshness) for storage/retrieval; split out of `eidetic-cli` | PyPI 0.12.0, 13 releases | repo README | Data pipeline hygiene | IGNORE |
| `unsloth-cli` | Wraps Unsloth for easier LLM fine-tuning | PyPI 0.6.0, 9 releases | repo README | Fine-tuning ops | IGNORE |
| `tensor-cli` | **Bare `teken` stub** — description says "tensor operations" but only the six boilerplate commands exist | PyPI 0.3.0, 3 releases | repo README | Unbuilt | IGNORE |
| `reduce-cli` | **Bare `teken` stub** — description says "data reduction/aggregation" but only the six boilerplate commands exist | PyPI 0.3.0, 2 releases | repo README | Unbuilt | IGNORE |
| `prove-cli` | Theorem proving / formal verification CLI (not deep-read; description-only) | PyPI 0.4.1, 4 releases | repo README | Formal verification | IGNORE |
| `teken` | **The generator itself.** "Create Agent First products" — the `afi-cli`/`python-cli` scaffold every repo above cites | PyPI 0.20.0, **17 releases**, most-released package found in this survey pass | repo README | Scaffolds new agent-fronted CLIs | WATCH — not for us to adopt code from, but explains *why* everything above looks identical; useful if we ever want to understand how fast AgentCulture can mint a new domain agent |
| `autonomous-intelligence` (OriNachum personal) | "Tau" — a hand-built Raspberry Pi + Jetson voice/vision companion robot; predates the org, not built on `teken`, no mesh identity | not packaged; last push 2026-04-08; 234 stars (his biggest by far) | repo README (checklist-style) | Personal robotics hobby project | IGNORE — no fleet/orchestration content, unrelated domain |

## Adoption notes

**Nothing in this cluster gets installed.** We are not a device-ops shop; none of these
repos address presence, state, scheduling, or multi-machine dispatch — the concerns this
project is built around. The verdict table above is uniformly IGNORE with two WATCH
exceptions, both watched for *idea*, not code:

- **`shell-cli`** — if agent-state-driver's `send`/`answer` surface ever needs to gate
  *what* gets sent (not just detect *when* it's safe to send), `shell-cli`'s
  `Operation → policy + preview → backend → result + evidence` lifecycle and its explicit
  preview/`--apply` split for mutations is a pattern worth re-deriving from, not a
  dependency worth pulling in. It is pre-1.0, Apache-2.0, and its own README disclaims
  adversarial safety — treat it as a design reference, not infrastructure to depend on.
- **`teken`** — worth a five-minute look if we ever want a template for a small CLI/agent
  companion tool of our own (e.g., a `fleet-cli` operator surface), since it is the most
  actively released artifact (17 versions) found anywhere in this cluster and clearly
  works as a generator. Not relevant to the state-detection or scheduling core.

**Cost of doing nothing here: zero.** No repo in this list is upstream of anything we plan
to build; there is no integration seam to design.

## Traps

- **Repo name ≠ built product.** `jetson-orin-cli`, `reduce-cli`, and `tensor-cli` are
  bare `teken` scaffolds with zero domain logic — same six commands as every other
  scaffold, README still carrying the generic "Make it your own" section. A PyPI listing
  and a plausible description are not evidence of a real feature; check for files beyond
  `_commands/{whoami,learn,explain,overview,doctor,cli}.py` before citing capability.
- **`webglass-cli`'s README is honest about being unbuilt ("pre-implementation… none of
  these verbs exist yet") — do not skim past the Status section and assume the "planned
  surface" code block is current.** The same caution applies org-wide: several repos in
  this list likely have similar gaps between description and `_commands/` contents that
  this pass did not clone and verify (only 10 of 33 were tree-inspected).
  `sensibo-cli`, `jetson-thor-cli`, and `dgx-spark-cli` are confirmed built; most of the
  rest are description-only in this report.
- **`fleet-cli` is a false-cognate.** It coordinates drones (UAVs), unrelated to our
  "fleet" of CLI coding agents. Don't let the name search collide with our own
  `docs/design/fleet-vision.md` vocabulary.
- **`reachy-nova` doesn't exist** (404 on `gh api repos/agentculture/reachy-nova`) — the
  brief's repo list included it; flagging so nobody re-checks it as "maybe I typo'd."
