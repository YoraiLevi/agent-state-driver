# Fleet: vision and problem statement

Draft v0 (2026-08-06). Written before the architecture research landed, deliberately —
this is the "what is it for" that the architecture must serve, not a summary of what the
architecture turned out to be.

---

## 1. The bet

**Everyone building agent fleets is scheduling on a lie.**

Every multi-agent system surveyed reports presence by asking the agent. cultureagent ships
a `STATE_WORKING` enum value and its own wire-contract document says no backend emits it —
*"no backend has an observable tool-execution boundary."* Screen-scrapers report "pixels
changed." Heartbeat systems report "the wrapper is still alive," which is not the same as
"the agent is working." Every one of them, asked *"is agent 7 ready for work right now?"*,
answers with a guess.

At one agent, a guess is an annoyance. At a hundred agents across five machines, a guess is
a system that:

- **dispatches into a void** — sends work to an agent sitting on an unanswered permission
  dialog, where it waits forever;
- **loses work silently** — an agent is SIGKILLed, its wrapper's last heartbeat still looks
  fresh, and the task is never retried;
- **cannot tell slow from stuck** — so it either kills healthy long-running work, or waits
  hours on a wedge;
- **burns money invisibly** — because nobody can see which agents are actually doing
  something versus blocked.

This project already solved that primitive. It can prove an agent's state from fused
channels — a vendor status file, the rendered screen, process liveness — with the evidence
attached, cross-platform, **including for agents it did not spawn**. It reports `conflict`
rather than guessing when channels disagree.

**The bet: verified state is what makes a large agent fleet schedulable rather than
merely hopeful.** Everything below is downstream of that one capability.

---

## 2. What this is not

Naming the neighbours honestly, because building beside them is a choice.

| System | What it is | Why this is not that |
|---|---|---|
| **AgentCulture / AgentIRC** | A workspace and chat runtime for agents — rooms, presence, history, roles | It is a *social* layer: agents talk. This is a *scheduling* layer: work is placed on agents whose readiness is proven. The clean seam is that our verified state could **feed** AgentIRC's presence instead of self-report |
| **Kubernetes / Nomad** | Schedulers for cheap, fast, idempotent, stateless-ish workloads | Agents are slow, expensive, non-idempotent, and **can ask questions**. No container asks its scheduler for permission mid-run |
| **Temporal** | Durable execution of deterministic workflows | The right idea for the *work* layer; wrong assumption at the *worker* layer, where our worker is a stochastic process that may block on a human |
| **CrewAI / AutoGen / LangGraph** | In-process multi-agent frameworks | Single machine, single process, agents-as-function-calls. This orchestrates *real CLI agents* on *real machines*, which is what you actually pay for and what actually edits your repos |

The unclaimed ground: **a multi-machine scheduler whose placement decisions are made on
observed agent state rather than self-report.**

---

## 3. Where this gets used

Five concrete scenarios, ordered by how soon they pay for themselves. Each is something
this repo's own construction either did by hand or could not do at all.

### 3.1 The cross-platform verification matrix
*(this project did this by hand, over hours)*

A change lands. The fleet dispatches the same verification to a macOS agent, a Linux agent
and a Windows agent **simultaneously**, each on real hardware with a real CLI, and returns
a matrix. Phase 4 of this project was exactly that, executed manually via SSH with
hand-written base64 script plumbing. The fleet makes it one command.

**Why verified state matters here:** the Windows agent has no tmux and a different hosting
layer entirely. The scheduler must know it is *ready*, not merely *reachable*.

### 3.2 The overnight autonomous project
*(this project, again — but the coordination was all human-in-the-middle)*

A goal is decomposed into tasks with dependencies; specialists take the pieces matching
their role; results feed back; the human reads a report in the morning. This session did
that with subagents — but they could not see each other. When prototype B discovered
prototype A's permission literals were stale, **that finding routed through the orchestrator
by hand.** A fleet closes that loop.

### 3.3 Swarm audit at scale
Point N agents at one large codebase with different lenses — security, correctness,
performance, dead code — let them work in isolated worktrees, then dedupe and
adversarially verify each other's findings. The pattern is proven (this repo's own
adversarial review caught real overclaiming); the fleet makes it routine and parallel.

### 3.4 Long-horizon research with specialists
A scout finds sources, readers digest in parallel, a librarian dedupes and indexes, a
synthesizer writes, a critic tries to refute. Roles are the natural unit, and the work is
naturally parallel and naturally long — the case where losing an agent silently is most
expensive.

### 3.5 On-call triage
An alert fires. The mesh wakes the agent nearest the affected machine — the one that can
actually reach it — collects evidence, proposes a fix, and **stops at the permission
dialog for a human**. That last part is the point: `waiting:permission` is a first-class
state, so "blocked on a human" is a schedulable condition rather than a hang.

---

## 4. What it must be

Requirements the vision imposes, before any architecture is chosen.

**R1 — Heterogeneous by default.** macOS, Linux, and Windows are peers. Windows has no
tmux and uses a different hosting layer; the fleet must not treat it as a second-class
citizen or the fleet becomes a Linux fleet with excuses.

**R2 — No agent is trusted to report its own state.** State is observed and carries
evidence. A node may *offer* state; the mesh records how it was proven.

**R3 — Roles are configuration, not code.** Adding a "reviewer" role must not require a
release. Roles declare capabilities and constraints; work declares requirements; the
scheduler matches.

**R4 — The topology is configurable.** Supervisor tree, peer mesh, and market-style bidding
are all legitimate for different jobs. The mesh must not hardcode one.

**R5 — A human is always able to stop it.** Not a promise — a mechanism. Kill switch,
budget ceiling, and a permission model that fails closed.

**R6 — Money is a first-class resource.** Agents cost real money. Spend must be
attributable per task, per role, per node — and predictable *before* it happens, not
discovered afterwards.

**R7 — Partition tolerance without lying.** When a node is unreachable, the mesh must not
report its agents as healthy, and must not double-dispatch their work. Unknown must be
representable, and `conflict` must survive to the fleet layer.

**R8 — Every fleet decision is auditable.** Why was this task placed on that agent? The
answer must be reconstructible from a log, including the evidence the placement rested on.

---

## 5. The thing that makes it hard

Agents are unlike every workload orchestrators were built for:

| Property | Consequence for the design |
|---|---|
| **Slow** (minutes to hours) | Scheduling latency is irrelevant; *wrong* placement is very expensive |
| **Expensive** (real money per turn) | Retries are not free; at-least-once dispatch can double a bill |
| **Non-idempotent** (they edit repos, open PRs, send messages) | At-most-once matters more than at-least-once; worktrees isolate blast radius |
| **Non-deterministic** | Two agents given the same task produce different work — sometimes valuably (panels, adversarial verify) |
| **They ask questions** | `waiting:permission` is a normal state, not a fault. No container does this |
| **They can be wrong confidently** | Verification must be structural, not trusting — the adversarial pattern generalises |
| **They can be manipulated** | A malicious file read by one agent can try to enqueue work for the fleet. Prompt injection becomes a *distributed systems* threat |

That last row is the one that scares me most, and it is why security is being researched
as a first-class workstream rather than bolted on.

---

## 6. Success criteria

The fleet is real when it can do this unattended, and prove it did:

1. Run the cross-platform verification matrix (3.1) on three real machines from one
   command, and produce a result table with per-agent evidence.
2. Survive a node being unplugged mid-task: no double-dispatch, no silent loss, no agent
   reported healthy while unreachable.
3. Survive an agent being SIGKILLed mid-task: detected from the process channel, work
   re-placed under an at-most-once policy the operator chose.
4. Stop cleanly when a budget ceiling is hit, mid-task, without corrupting state.
5. Answer "why did task T run on agent A?" from the log, with the evidence.
6. Add a new role and a new machine **by editing configuration only**.

Anything that cannot be demonstrated on real machines does not count. That standard is
what the state driver was built to.
