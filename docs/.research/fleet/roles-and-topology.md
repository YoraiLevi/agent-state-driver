# Roles and configurable mesh topology — research and proposal

Date: 2026-08-06. Scope: what a *role* is concretely, and 3 topology models for a
multi-machine, self-orchestrating fleet of CLI agents built on **verified** state.

Provenance convention: **OBSERVED** = read from a primary source at the cited path/URL in
this pass. **INFERRED** = my reasoning on top of it. **UNVERIFIED** = a claim I could not
close and which must not be built on without a probe.

Sources read in this pass are listed at the bottom; local artifacts are cited by
`path:line`, external ones by URL plus the line of the scraped copy under
`scratchpad/scrape/` (retrievable by re-scraping the URL).

---

## Verdict

- **"Role" is not one thing and the failure of every agent framework surveyed is that they
  ship it as one thing.** It decomposes into **six orthogonal facets**: *capability*
  (what the agent can do), *permission scope* (what it may do), *persona* (how it behaves),
  *work subscription* (what it accepts), *placement constraint* (where it may live), and
  *supervision policy* (what happens when it fails). Infrastructure systems separate at
  least four of these (K8s: labels ≠ RBAC ≠ taints; Ansible: `defaults` ≠ `argument_specs`
  ≠ tags); agent frameworks collapse all six into a prompt (ChatDev `RoleConfig.json` is
  literally a dict of role-name → list of prompt strings; CrewAI's required fields are
  `role`, `goal`, `backstory`). Collapse them and you cannot route work by evidence,
  because a prose `backstory` is not a checkable predicate.

- **Add a seventh facet nobody else has: observation posture.** This project's own
  `SPEC.md:8` already proves observability is not uniform — an attached session with no
  reachable terminal reports `screen_available: false` and *can detect a dialog but never
  answer one* (`prototypes/common/SPEC.md`, rule 8; README.md:112-114). So
  `can_answer_dialog` is a **capability of the observer, not of the agent**, and it must be
  schedulable. A role whose work generates permission dialogs must not be placed on an
  agent the fleet can only watch. No surveyed system models this because no surveyed system
  can observe an agent it did not spawn.

- **Every distributed system surveyed degrades unreachability to "Unknown" and then guesses
  with a timer — and says so out loud.** Akka: *"the state of an unreachable node is
  unknown and the cluster cannot know if the node has crashed or is only temporarily
  unreachable because of network issues or GC pauses"* (akka cluster-membership.md:81-82).
  Kubernetes: the kubelet **self-registers** and self-reports via two heartbeat forms
  (`.status` updates and `Lease` objects); when a node is unreachable the node controller
  can only set the `Ready` condition to `Unknown` and then wait a default **5 minutes**
  before the first eviction. That is the exact hole this project fills: our node-local
  observer reads the vendor sidecar, the screen, and the PID — it does not ask the agent how
  it is doing. **Roles are declared; state is proved.** The mesh's routing table is
  `(role: declared, verified at admission) × (state: observed, evidence-carrying)`, and an
  agent must never be able to write into the second column.

- **Dispatch must be gated on a lease, not on a state reading.** Verified state is a fact
  about a past instant; the RACE results give per-channel latency but not zero. Proposal: the
  node observer issues a short-TTL **dispatch lease** (`{agent, state:idle, evidence[],
  issued_at, ttl_ms}`) and `send` refuses if the lease expired — which is the fleet-scale
  generalisation of the driver's existing rule that `send` refuses unless idle
  (`README.md:94`, exit code 4). This is the primitive that makes "orchestrate agents you did
  not spawn" safe, and it has no analogue in prior art.

- **Loop control must be declarative and budgeted per edge, not emergent.** ChatDev is the
  only agent system surveyed that bounds its cycles in config
  (`ChatChainConfig.json`: `CodeCompleteAll` `cycleNum: 10`, `CodeReview` `cycleNum: 3`,
  `Test` `cycleNum: 3`, plus per-phase `max_turn_step`). AutoGen's Swarm has no bound at all
  — its own worked example ping-pongs planner→analyst→planner→analyst→planner and is stopped
  only by the model emitting the magic string `TERMINATE`. Steal OTP's shape instead:
  `intensity`/`period` restart budgets with OTP's explicit warning that nested budgets
  *multiply* ("if the top level allows 10 restarts, and the next level also allows 10, a
  crashing child below that level will be restarted 100 times").

- **Verified state converts livelock detection from a heuristic into a measurement.** A
  handoff ping-pong and productive delegation look identical in a self-reported mesh — both
  are just messages. With verified state you can compute, per work-item, *aggregate
  busy-seconds actually spent* vs *number of role transitions*, and cut a cycle that is
  churning edges while nobody was ever provably `busy`. Conversely it stops the opposite
  error: killing a chain that looks stalled but is provably `busy` (or is in compaction, the
  documented hang-lookalike, functional-design.md:74-76). **INFERRED — this metric is a
  proposal, not something any surveyed system implements.**

- **Recommended shape: supervisor tree as the control plane, capability routing as the data
  plane, market only where ownership is genuinely ambiguous.** Not a fixed hierarchy — the
  tree carries *lifecycle, safety and escalation*, while work finds agents by selector.
  Akka is the precedent that this hybrid is what mature systems actually do: node roles pick
  placement (`akka.cluster.roles`) but a single `ShardCoordinator` is still involved in
  routing the first message per shard.

- **Adopt the owner's existing dgx-fleet vocabulary rather than inventing one.** `roles/<name>/`
  with `defaults/` + `meta/argument_specs.yml` + generated READMEs; risk tags `baseline` vs
  `dangerous` (`playbooks/site.yml:45-58`) where the unattended pull path runs **only**
  `--tags baseline` (`WHY.md:30`); explicit ordering in the play, never `meta` dependencies
  (`WHY.md:54`); strict variable precedence with the rule *"extra-vars never carry policy"*
  (`WHY.md:74`); and INVENTORY.md's framing that *"the infrastructure does not enforce a
  specific topology; you compose one from these knobs."* That last sentence is the design
  brief for this whole document.

---

## Findings

### 1. What each system actually means by "role"

| System | Role is… | Machine-checkable? | Carries permissions? | Carries placement? | Carries failure policy? |
|---|---|---|---|---|---|
| **K8s RBAC** | a named rule set: `apiGroups`/`resources`/`verbs`/`resourceNames` bound by `RoleBinding`/`ClusterRoleBinding` | yes | **yes, and only that** | no | no |
| **K8s node labels** | arbitrary k/v on a Node, selected via `nodeSelector` or `nodeAffinity` | yes | no | **yes, and only that** | no (see `IgnoredDuringExecution`) |
| **K8s taints** | the *node's* refusal, `NoSchedule`/`PreferNoSchedule`/`NoExecute` + `tolerationSeconds` | yes | no | yes (inverse direction) | partly (`NoExecute` evicts) |
| **Ansible role** (`dgx-fleet/roles/*`) | a directory: `tasks/` + `defaults/` + `meta/argument_specs.yml` + `handlers/` + tags | yes (argspec-validated) | implicitly, via tag class | via inventory groups/`host_vars` | no (ordering is in the play) |
| **Akka cluster role** | a string in `akka.cluster.roles`, part of `MemberEvent` membership gossip | yes | no | **yes** — sharding `init` creates a `ShardRegion` or a proxy depending on role match | no (that is the supervisor's job) |
| **OTP supervisor** | not a role at all — a *strategy* + child spec (`restart => permanent\|transient\|temporary`, `significant`) | yes | no | no | **yes, and only that** |
| **AutoGen** | an agent `name` + `description` fed to a model-based `selector_prompt`; or a `handoffs=[...]` edge list | no (prose) | no | no | no |
| **CrewAI** | required `role` + `goal` + `backstory` strings, plus `tools`, `allow_delegation`, `max_iter`, `max_rpm` | partly (`tools` yes, the rest prose) | no | no | partly (`max_iter`, `max_retry_limit`) |
| **LangGraph supervisor/swarm** | an agent node name reachable via a generated `transfer_to_<name>` handoff tool | no | no | no | no |
| **MetaGPT** | a role class inside a fixed SOP — *"`Code = SOP(Team)` is the core philosophy"* | no | no | no | no |
| **ChatDev 1.0** | a key in `RoleConfig.json` mapping to a **list of prompt strings** | no | no | no | no (bounds live in the chain config) |
| **cultureagent** | a *resident* on an IRC-shaped bus, addressed by mention/DM past an accept-gate | no | eliminated by design (all backends auto-approve) | no | yes (crash window + stale-busy watchdog) |

OBSERVED. Read across: **infrastructure systems make role a set of separately-checkable
declarations; agent frameworks make role a paragraph.** The gap is not sophistication, it is
that agent frameworks never needed to schedule against scarce, heterogeneous, individually
failing machines.

### 2. Selection: two directions, hard and soft — and the gap K8s never closed

- `nodeSelector` is the simplest constraint: exact label match. `nodeAffinity` adds
  `requiredDuringSchedulingIgnoredDuringExecution` (hard) and
  `preferredDuringSchedulingIgnoredDuringExecution` (soft, `weight` 1-100, summed into the
  node score). Multiple `nodeSelectorTerms` are OR'd; multiple `matchExpressions` within a
  term are AND'd. OBSERVED.
- Taints run the other way: the *node* repels work unless the pod tolerates it. K8s ships
  well-known ones — `node.kubernetes.io/not-ready` (`Ready=False`) and
  `node.kubernetes.io/unreachable` (`Ready=Unknown`) — added automatically by the node
  controller, with a default `tolerationSeconds=300` injected into pods that do not set it.
  OBSERVED.
- **The gap:** `IgnoredDuringExecution` means *"if the node labels change after the Pod is
  scheduled, the Pod keeps running"*. K8s has never shipped
  `RequiredDuringSchedulingRequiredDuringExecution`. For a fleet of long-lived agents whose
  observable state changes every few seconds, ignoring placement predicates after dispatch is
  exactly wrong: a machine whose human sits down at the keyboard, or an agent that flips to
  `waiting:permission`, must be able to *revoke* an in-flight assignment. INFERRED, but it is
  the direct consequence of the OBSERVED semantics.

### 3. Membership, liveness and the self-report ceiling

- **Akka** membership states: `joining · weakly up · up · preparing for shutdown · ready for
  shutdown · leaving · exiting · down · removed`, moved by a `leader` only on gossip
  convergence, with `UnreachableMember`/`ReachableMember` events from a
  `PhiAccrualFailureDetector` (`akka.cluster.failure-detector.threshold`,
  `acceptable-heartbeat-pause`). Critically: *"If a node is `unreachable` then gossip
  convergence is not possible and therefore most `leader` actions are impossible"* — a single
  unreachable member freezes cluster-wide decisions until it is downed. OBSERVED.
- **Akka gating on role**: `akka.cluster.min-nr-of-members` and per-role
  `akka.cluster.role.<name>.min-nr-of-members` hold new members in `Joining` until the fleet
  has enough of a given role. OBSERVED. This is a directly stealable admission gate: *do not
  start dispatching until N verified-idle agents of role R exist.*
- **Kubernetes** is the honest counter-example: node health is **self-reported** (kubelet
  self-registers; heartbeats are `.status` updates plus `Lease` objects in
  `kube-node-lease`), the node controller polls every 5 s, degrades to `Ready=Unknown`, and
  waits 5 minutes before evicting, rate-limited to `--node-eviction-rate 0.1`/s. OBSERVED.
- **cultureagent** is the agent-world instance of the same ceiling: `presumed_hung = state in
  BUSY_STATES and (now - last_refresh) > stale_after_seconds` (90 s vs a 30 s heartbeat),
  computed **server-side at read time**, with a fail-fast config assertion that stale must
  exceed the heartbeat. Its own stated principle is the correction that matters:
  *"transitions are driven only by observable code boundaries — never by model self-report"*
  (`presence_emitter.py:9-10`) — and yet `STATE_WORKING` is in the enum and *no backend emits
  it* (SYNTHESIS.md, Verdict). OBSERVED via `docs/.research/prior-art/cultureagent.md:41-58`.

**What this buys us, precisely.** Every system above must answer "is this worker ready?" with
either (a) the worker's own claim, or (b) silence plus a timer. This project answers it with
a third thing: a node-local observer fusing a vendor-written sidecar
(`~/.claude/sessions/<pid>.json`, `status` + `waitingFor`), the rendered screen, and
`kill -0 <pid>` — for sessions it did not spawn, on macOS/Linux/Windows
(`docs/discovery-session-sidecar.md`; `docs/design/functional-design.md:95,155-162`). A
scheduler with that input does not need a 5-minute eviction grace period to distinguish
"dead" from "thinking".

### 4. Failure policy as a first-class, declarable thing (OTP)

`SupFlags = #{strategy => …, intensity => …, period => …, auto_shutdown => …}` where
`strategy() = one_for_all | one_for_one | rest_for_one | simple_one_for_one` and
`restart() = permanent | transient | temporary`. If more than `intensity` restarts occur in
`period` seconds the supervisor terminates all children and itself, escalating to *its*
supervisor. `auto_shutdown => any_significant | all_significant` lets a supervisor represent a
*work unit of cooperating children* that shuts down when its significant children finish.
OBSERVED.

Three pieces of OTP's tuning guidance transfer verbatim and are worth quoting into the design:

1. Burst vs sustained rate are different knobs — `1/6` and `5/30` have the same sustained
   rate but `1/6` forbids two quick retries.
2. Do not set a very long `period` to tolerate bursts (`5/3600` gives up on a single restart
   an hour later; "you probably want to regard those crashes as separate incidents").
3. **"If your application has multiple levels of supervision, do not set the restart
   intensities to the same values on all levels"** — the total is the *product* across the
   tree. For an LLM fleet where each restart costs money and tokens, this is the difference
   between a bounded incident and an unbounded bill.

`rest_for_one` (restart the failed child and everything started *after* it) is the strategy
with no analogue in any agent framework surveyed, and it is the right one for a pipeline role
chain: if the reviewer dies, the integrator downstream of it must be restarted too, but the
planner upstream need not be. INFERRED.

### 5. How agent frameworks route, and how they (fail to) stop

- **AutoGen `RoundRobinGroupChat`**: fixed turn order, *"all agents share the same context"*,
  each broadcasts to all. Stops on a `termination_condition` such as
  `TextMentionTermination("APPROVE")`, composable with `|`. OBSERVED.
- **AutoGen `SelectorGroupChat`**: an LLM picks the next speaker from participants' `name` and
  `description` via a `selector_prompt`. *"By default, the team will not select the same
  speaker consecutively unless it is the only agent available"* (`allow_repeated_speaker`), and
  you can override with a deterministic `selector_func`, or narrow the field per turn with
  `candidate_func` (valid only if `selector_func` is unset). OBSERVED. Read as: the framework's
  own escape hatch from LLM routing is a Python function — i.e. its authors agree deterministic
  routing is sometimes required.
- **AutoGen `Swarm`**: agents declare `handoffs=["flights_refunder", "user"]`; emitting a
  `HandoffMessage` transfers the task *with the same message context*, and `target="user"`
  is how a human is pulled in. OBSERVED. Its published worked trace is a five-hop
  planner↔specialist ping-pong ending in `stop_reason="Text 'TERMINATE' mentioned"` — **loop
  control is a magic string produced by a model.**
- **LangGraph `create_supervisor` / `create_swarm`**: handoffs are generated tools
  (`transfer_to_<agent>`); by default a handoff passes the **full** message history; supervisor
  offers `output_mode="full_history" | "last_message"`; multi-level hierarchies are built by
  nesting supervisors. Swarm requires a checkpointer or *"the swarm would 'forget' which agent
  was last active"*. OBSERVED. Two consequences: context grows superlinearly with hop count,
  and "who is active" is durable state living in a checkpointer — i.e. a routing table by
  another name.
- **CrewAI**: `Process.sequential` (output of one task is context for the next) vs
  `Process.hierarchical`, which **requires** `manager_llm` or `manager_agent`; *"Tasks are not
  pre-assigned; the manager allocates tasks to agents based on their capabilities"* — where
  "capabilities" are the prose `role`/`goal`/`backstory`. Bounds are per-agent (`max_iter`
  = "maximum attempts before giving best answer", `max_rpm`, `max_retry_limit`) and
  `allow_delegation` gates agent-to-agent handoff. OBSERVED.
- **ChatDev 1.0**: the only surveyed system whose loop bounds are **data**. `ChatChainConfig.json`
  declares a chain of phases, each `SimplePhase` (with `max_turn_step`, `need_reflect`) or
  `ComposedPhase` (with `cycleNum` — 10 for `CodeCompleteAll`, 3 for `CodeReview`, 3 for
  `Test`). Roles are `RoleConfig.json` prompt lists. OBSERVED. **Steal the split** (workflow
  bounds are config, separate from role definitions); **reject the coupling** (a linear chain
  is a fixed hierarchy).
- **MetaGPT**: *"`Code = SOP(Team)` is the core philosophy. We materialize SOP and apply it to
  teams composed of LLMs"* — product manager / architect / project manager / engineer, fixed.
  OBSERVED. This is precisely the fixed hierarchy the owner has ruled out; its transferable
  idea is only that the *procedure* is a first-class artifact independent of the agents.
- **cultureagent / AgentCulture**: residents on an IRC-shaped bus; work arrives as a mention or
  DM that must pass an **accept-gate**; presence is a `PRESENCE :<json>` verb carrying
  `{state, since, task?, tokens_in?, tokens_out?}`, truncated to fit IRC's 512-byte line cap by
  dropping `task` first. Crash policy: `MAX_CRASH_COUNT=3` within `CRASH_WINDOW_SECONDS=300`
  opens a circuit breaker, else `_delayed_restart` after `CRASH_RESTART_DELAY=5`s. `draining`
  is **sticky** so a late in-flight LLM call cannot undo a shutdown signal. OBSERVED via
  `cultureagent.md:66,193-222`.

### 6. The market option: FIPA Contract Net, and why its failure mode is our home turf

The Contract Net Interaction Protocol (FIPA SC00029H): an Initiator issues a `cfp` (call for
proposals) to *m* participants; *j* respond with `propose`, *i=n-j* with `refuse`; the
Initiator sends `accept-proposal` to the winners and `reject-proposal` to the rest; the winner
returns `inform-done`/`inform-result` or `failure`. OBSERVED.

Two clauses matter:

- *"In the case that a Participant fails to reply with either a propose or a refuse act, the
  Initiator may potentially be left waiting indefinitely. To guard against this, the `cfp` act
  includes a deadline by which replies should be received"* — the `reply-by` parameter; late
  proposals are auto-rejected. **This is a 1996-vintage admission that a bidding market's core
  failure mode is a silently-dead bidder** — the exact failure verified state removes.
- A `cancel` meta-protocol exists as a separate interaction with the same `conversation-id`,
  answered with `inform-done` or `failure`. Cancellation is a protocol, not a kill.

---

## Proposal: what a role is, concretely

**A role is a named, version-pinned bundle of six declarations plus one derived posture, all
independently checkable. It contains no state.**

```yaml
# roles/reviewer/role.yml   (shape follows dgx-fleet: defaults + argument_specs + generated README)
role: reviewer
version: 1                        # pinned; a mesh may run two versions side by side

capabilities:                     # 1. DECLARED, then PROBED at admission — never trusted as prose
  - tool:git                      #    probe: `git --version` on the node
  - tool:pytest
  - lang:python
  - model:claude-opus             #    probe: sidecar `version` field + launch flags

permissions:                      # 2. SCOPE. Deliberately NOT k8s-shaped (see "what to avoid")
  allow: ["Read", "Edit", "Bash(pytest:*)"]
  deny:  ["Bash(git push:*)", "Bash(rm:*)"]
  risk_class: baseline            #    baseline | dangerous  (dgx-fleet playbooks/site.yml:45-58)
  unattended: true                #    false => may only be dispatched with a human subscriber live

persona:                          # 3. The only free-text facet. Never load-bearing for routing.
  prompt_ref: prompts/reviewer.md

subscribes:                       # 4. WORK SUBSCRIPTION — the agent's selector over work
  - queue: review
    match: {label.lang: python}
    concurrency: 1

placement:                        # 5. PLACEMENT — k8s nodeAffinity shape, both hard and soft
  required:                       #    ALL must hold at dispatch AND during execution (see below)
    - {key: os, operator: In, values: [linux, darwin]}
    - {key: repo.checkout, operator: Exists}
  preferred:
    - {weight: 50, key: machine.class, operator: In, values: [workstation]}
  tolerations:                    #    which node taints this role accepts
    - {key: agent.fleet/human-attended, operator: Exists, effect: PreferNoSchedule}

supervision:                      # 6. FAILURE POLICY — OTP shape, budgets declared not emergent
  strategy: rest_for_one
  intensity: 3
  period_s: 300
  escalate_to: role:integrator
  turn_deadline_s: 900            #    FIPA reply-by, applied to a dispatch
  hung_after_s: 300               #    observer-computed; must exceed compaction p99 (OPEN)

posture_required: attached+screen  # 7. DERIVED/REQUIRED OBSERVATION POSTURE
                                   #    spawned | attached+screen | attached-noscreen
                                   #    implies can_answer_dialog: true
```

Four rules bind the model:

1. **Roles are declared; state is proved.** No field of a role may be written by the agent
   at runtime, and no state field may be written by anything but the node observer. Enforced
   the same way `prototypes/common/SPEC.md` rule 2 enforces evidence: every state row carries
   `evidence: [{channel, signal, at}]`, and disagreement surfaces as `conflict`, never a
   silent winner (rule 9).
2. **Capabilities are declared then probed.** Admission runs the probes and *rejects the
   agent from the role* on mismatch — the fleet analogue of `meta/argument_specs.yml`
   validating at play start (`WHY.md:74`). A capability that cannot be probed is not a
   capability; it belongs in `persona`.
3. **`posture_required` is a hard placement predicate.** Dispatching dialog-generating work
   to an `attached-noscreen` agent produces a permanent `waiting:permission` latch that
   nothing in the mesh can clear — a guaranteed stuck work-item, and the single most likely
   way this system fails in production. OBSERVED basis: README.md:112-114, SPEC rule 8.
4. **Required-during-execution, not ignored.** Unlike K8s, `placement.required` and the state
   predicate are re-evaluated for the life of the assignment; violation revokes the lease and
   returns the work-item to its queue with a `revoked` reason. This is the deliberate
   divergence from `IgnoredDuringExecution`.

**Dispatch predicate** (the one line the whole system turns on):

```
dispatch(work, agent) is legal  iff
      role.subscribes matches work.labels
  AND role.placement.required holds on agent.node          (evaluated now, re-evaluated during)
  AND agent.verified_state == idle                          (observer-computed, not claimed)
  AND agent.evidence.max_age_ms <= lease.ttl_ms
  AND kill_0(agent.pid) is true                             (PITFALLS: liveness is the PID)
  AND work.risk_class <= role.permissions.risk_class
  AND (role.permissions.unattended OR a human subscriber is live)
```

`send` then carries the lease id and **refuses on an expired lease**, exactly as the driver's
`send` already refuses unless idle (`README.md:94`, exit 4). INFERRED design; the underlying
refusal mechanism is OBSERVED and shipped.

---

## Three topology models

All three assume the same substrate: one **node observer** per machine (the existing driver's
`list`/`state`/`attach` verbs, `README.md:106-114`) publishing edge-triggered, evidence-carrying
state upward. The topologies differ only in who decides what runs where.

### A. Supervisor tree (OTP-shaped)

```
                 root supervisor  (one_for_one, intensity 3 / 300s)
                   ├── domain sup: build      (rest_for_one)   → agents on linux nodes
                   ├── domain sup: review     (one_for_one)    → agents with posture attached+screen
                   └── domain sup: human-gate (one_for_all)    → permission/question broker
```

- **Work discovery**: push-down. A parent holds the work queue and assigns to a named child.
  Children never search.
- **Loops/livelock**: OTP restart budgets, per level, deliberately *not* equal across levels
  (the compounding warning). `turn_deadline_s` converts a stall into a death so one recovery
  path handles both — cultureagent's deliberate `.terminate()` pattern (SYNTHESIS 1.8).
  `auto_shutdown: all_significant` retires a completed work-unit subtree.
- **Human control**: strongest of the three. Every escalation has exactly one destination;
  `risk_class: dangerous` work can be made to require an explicit human `accept` at the domain
  supervisor, mirroring dgx-fleet's rule that the unattended pull path runs only
  `--tags baseline` (`WHY.md:30`).
- **Verified state buys**: the supervisor restarts on *proved* death (`kill -0` + EOF) rather
  than on silence, so compaction and long silent tool calls stop triggering restart storms —
  the failure this project's own `presumed_hung` threshold exists to prevent
  (functional-design.md:74-76).
- **Cost**: it *is* a hierarchy. The owner has ruled out a fixed one; use it for lifecycle and
  safety only, not for work assignment.

### B. Peer mesh with capability routing (K8s/Akka-shaped) — recommended default for the data plane

```
work-item{labels} ──▶ scheduler(s) ──▶ selector match ──▶ lease ──▶ agent.send
        ▲                                  │
        └────────── revoked / requeued ◀────┘  (state left idle, node tainted, deadline blown)
```

- **Work discovery**: label-and-selector, symmetric. Work carries labels; roles carry
  `subscribes.match`; nodes carry labels and **taints**. Agents do not talk to each other to
  find work — they talk to a queue. Peer-to-peer *messages* (handoff) are allowed but are
  modelled as **creating a new work-item**, not as transferring a context blob. That single
  change removes LangGraph/AutoGen's full-history-per-hop growth.
- **Loops/livelock**: a work-item carries `hops`, `budget_tokens`, `deadline`, and a
  `lineage[]` of role transitions. A hard `max_hops` (ChatDev's `cycleNum` in a general
  form) plus the busy-seconds-per-transition ratio (see Verdict) cuts churning cycles. A role
  may not re-enter its own lineage more than `k` times — a checkable generalisation of
  AutoGen's `allow_repeated_speaker=False` default.
- **Human control**: `cordon` a node (`agent.fleet/human-attended:NoSchedule`) when someone
  sits at the keyboard; `drain` with a `tolerationSeconds` grace; a `human` role that
  subscribes to the `waiting:permission` and `waiting:input` queues — this project's
  detect-don't-bypass stance (functional-design.md:124-128) means blocked agents become
  *routable work* rather than dead ends. AutoGen's `ExternalTermination` is the right shape
  for the stop button: it *"allows the current agent to finish its turn"* rather than killing
  mid-generation.
- **Verified state buys**: the entire model. Selector matching answers *may* this agent take
  the work; only verified state answers *can it right now*. Without it you are K8s scheduling
  onto `Ready` conditions the worker wrote itself — and you get the two failures named in the
  brief: dispatch to a not-actually-ready agent, and work lost to an agent that silently died.
- **Cost**: needs a scheduler component and a durable queue; needs the capability probe suite;
  admission control is real work.

### C. Blackboard / market (FIPA Contract Net-shaped)

```
poster ──cfp{spec, reply_by}──▶ all agents matching a coarse selector
       ◀──propose{cost, eta, evidence:[state=idle, capabilities probed]}── / ──refuse──
       ──accept-proposal──▶ winner    ──reject-proposal──▶ rest
       ◀── inform-done | inform-result | failure ──
```

- **Work discovery**: pull, by bidding. Best where the right owner is genuinely unknown
  (triage, "who has this repo checked out and warm", cross-machine cost differences).
- **Loops/livelock**: `reply_by` on every `cfp` (FIPA's own guard against waiting
  indefinitely); auto-reject of late proposals; a bid budget per work-item; a `cancel`
  meta-protocol distinct from a kill.
- **Human control**: weakest — the human is a bidder among peers unless you special-case them.
  Mitigate by making high-`risk_class` work non-auctionable (routes to B or A instead).
- **Verified state buys**: the thing that makes bidding honest. A bid can carry *evidence*
  (`state=idle` at `t`, sidecar + screen + pid) rather than a promise, and the auctioneer can
  independently re-verify the winner before `accept-proposal` — closing the classic CNP hole
  where the winner was already dead when it bid. **This is the strongest demonstration of the
  project's differentiator and the weakest candidate for v1.**
- **Cost**: N model calls per auction (real money), non-determinism, hardest to audit.

### Recommendation

`A ⊕ B` composed, `C` behind a flag for a named subset of queues. Precedent: Akka does
exactly this — roles pick placement, a `ShardCoordinator` is still consulted for the first
message of each shard, and `LeastShardAllocationStrategy` rebalances automatically (with
`ExternalShardAllocationStrategy` as the manual override). OBSERVED, cluster-sharding.md:101-102,
176-213.

| | A supervisor tree | B peer mesh + capability routing | C market |
|---|---|---|---|
| Work discovery | pushed down by parent | selector match on a queue | bidding on a `cfp` |
| Determinism | high | high | low |
| Loop control | restart intensity/period, per level | max_hops + lineage + busy-seconds ratio | reply_by + bid budget |
| Human control | strongest (one escalation path) | strong (cordon/drain + human role) | weakest |
| Fixed hierarchy? | yes | no | no |
| Cost per decision | ~0 | ~0 | one model call per bidder |
| Best for | lifecycle, safety, escalation | routine dispatch | ambiguous ownership |

---

## What to steal

1. **Ansible role directory + `meta/argument_specs.yml` + generated README** (dgx-fleet). A
   role that validates its own inputs at load time and whose docs cannot drift. Same argument
   as `WHY.md:74`.
2. **`baseline` vs `dangerous` tag classes, and an unattended path that runs only `baseline`**
   (`playbooks/site.yml:45-58`, `WHY.md:30`). Maps 1:1 onto `permissions.risk_class` +
   `unattended`.
3. **Explicit ordering in the composition, never `meta` dependencies** (`WHY.md:54`). Fleet
   translation: topology lives in one readable mesh file, not scattered across role metadata.
4. **K8s `nodeAffinity` grammar** — `required`/`preferred`, `weight` 1-100, OR across terms,
   AND within a term. Well-understood, expressible, already familiar to the owner.
5. **K8s taints as the operator's lever** — `NoSchedule` for cordon, `NoExecute` +
   `tolerationSeconds` for drain, and *auto-applied* condition taints as the way node health
   feeds the scheduler without special-casing.
6. **Akka `akka.cluster.role.<r>.min-nr-of-members`** as an admission gate before dispatch
   starts, and node roles gating whether a machine hosts a real worker or a proxy.
7. **OTP `SupFlags`** verbatim: `strategy` (esp. `rest_for_one`), `intensity`/`period`,
   `permanent|transient|temporary`, `auto_shutdown: all_significant`, and the three tuning
   rules — especially "do not set the same intensities on all levels".
8. **FIPA `reply-by` + auto-reject-late + a `cancel` meta-protocol** for every dispatch, not
   just auctions.
9. **ChatDev's config-declared loop bounds** (`cycleNum`, `max_turn_step`) as the shape for
   `max_hops`/`max_cycles`, kept in the topology file, not in prompts.
10. **cultureagent's sticky `draining`** (a late in-flight call cannot undo a shutdown signal),
    its crash circuit-breaker (3 in 300 s), and its read-time server-side hung computation.
11. **AutoGen's `ExternalTermination`** semantics for the human stop button: stop the team, let
    the current turn finish and broadcast.
12. **AutoGen's `selector_func`/`candidate_func` escape hatch** as the *default*, inverted: our
    router is deterministic, and a model may only *narrow candidates*, never pick.

## What to avoid, and why

- **LLM-as-router for dispatch** (AutoGen `selector_prompt`, CrewAI `manager_llm`). Costs a
  model call per hop, is non-deterministic, produces no evidence, and cannot be replayed in an
  incident review. Keep model judgement for *decomposition*, not *placement*.
- **Capability as prose** (CrewAI `role`/`goal`/`backstory`; ChatDev `RoleConfig.json`). CrewAI's
  hierarchical manager allocates "based on their capabilities" where capabilities are a
  paragraph. Unprobeable, so unenforceable, so the scheduler is guessing — the failure class
  this project exists to eliminate.
- **Handoff-as-tool-call carrying full history** (AutoGen `Swarm`, `langgraph_supervisor`'s
  `create_handoff_tool` which passes **full** message history by default). Three problems: the
  agent unilaterally reassigns with no admission control; context grows superlinearly in hops;
  and the routing state ends up hidden in a checkpointer. Model a handoff as *emitting a new
  work-item with a reference*, and let the scheduler decide.
- **Termination by magic string.** `TextMentionTermination("TERMINATE")` makes loop exit a
  model output. Bounds must be data the scheduler enforces.
- **K8s's "permissions are purely additive (there are no 'deny' rules)".** Correct for an API
  server, wrong here: the agent CLI's own settings support deny rules, and `deny` is how you
  express "never `git push`" without enumerating the allow-universe. **Deliberate divergence —
  record it as a decision.**
- **`IgnoredDuringExecution`.** See finding 2. Long-lived agents change state constantly;
  placement predicates must be re-evaluated and leases revocable.
- **Fixed SOP as the topology** (MetaGPT `Code = SOP(Team)`; ChatDev's linear chain). Directly
  contrary to "configurable mesh, not a fixed hierarchy". Keep the *procedure-as-artifact*
  idea, drop the fixed graph.
- **Any state field an agent can write about itself.** cultureagent states the principle and
  still ships an unemitted `STATE_WORKING`; K8s is forced into it by architecture. We are not.
- **Building a watchdog on the sidecar's timestamp.** It is edge-triggered, not a heartbeat
  (`PITFALLS.md:121-128`: a live busy session showed a 23-minute-old `updatedAt`). Fleet-wide
  this becomes a mass-eviction bug. Staleness of *our own observation* is the watchdog input;
  staleness of the vendor's timestamp is not.
- **Quorum with two machines.** dgx-fleet's answer is a documented **designated primary**
  ("avoids n=2 split-brain by fiat", `INVENTORY.md`). Do the same per work-domain rather than
  shipping a consensus protocol.
- **Cluster-wide gossip for agent state** (Akka's model). An unreachable member blocks leader
  actions cluster-wide. Our state is node-local and cheap to observe; push it up edge-triggered
  and compute `presumed_hung` centrally at read time (cultureagent's shape) instead.

## Open questions for the design

1. **Can a role label be carried in the vendor sidecar?** It has `"name":"protoc-c5"` with
   `"nameSource":"derived"` (`docs/discovery-session-sidecar.md:16-17`). If `name` can be set
   at launch, `driver.py list` becomes a zero-cost fleet-wide role directory for sessions we
   did not spawn. **UNVERIFIED — one probe.** If it cannot, the node observer needs its own
   sidecar-adjacent registry, and role↔session binding for adopted sessions becomes a real
   design problem.
2. **What is the correct dispatch-lease TTL?** It must exceed worst-case observation latency
   per channel. `docs/results/RACE-macos.md` has the per-channel numbers; nobody has turned
   them into a scheduler budget. Also unmeasured: latency under N concurrent sessions on one
   machine (HANDOFF.md lists concurrent sessions as unverified).
3. **Compaction duration distribution.** Open in functional-design.md:257 and it now gates
   *two* fleet numbers: `hung_after_s` and the "do not reassign yet" threshold. Reassigning
   during compaction duplicates work and spends money twice.
4. **Where does `waiting:input` route?** To a human queue or to a policy agent? Depends on the
   `waitingFor` vocabulary, whose size is unknown (functional-design.md:95) — and an
   unrecognised literal must yield `conflict`, which the scheduler must have a rule for.
   Proposal: `conflict` makes an agent **unschedulable but not evicted** (K8s's
   `Ready=Unknown` posture, minus the 5-minute blind wait since we can re-probe immediately).
5. **Can the fleet dispatch to read-only members?** `attach` is unbuilt (HANDOFF.md "Open
   work"), and `attached-noscreen` agents can be observed but not driven. Is a detect-only
   member a first-class role ("observed, never dispatched") or excluded from the mesh?
6. **What authenticates a node observer's report?** Nothing in the current design stops a
   compromised or buggy node from claiming `idle` for a dead agent — which would reintroduce
   self-report at the machine level. Evidence needs to be *verifiable*, not merely *carried*
   (signed reports? auditor re-probe? sampled second-observer?). **Unaddressed; the biggest
   hole in the differentiator at fleet scale.**
7. **Transport and heterogeneity.** macOS/Linux/Windows nodes with no shared filesystem
   assumption; the driver's cross-platform work stops at the machine boundary. Push (node →
   scheduler, edge-triggered, cultureagent's shape) vs pull (scheduler polls `list`) is
   undecided; push needs an outbound-only path from laptops behind NAT.
8. **Do OTP restart budgets translate to spend budgets?** Restarting an LLM agent costs tokens.
   The design should probably carry *both* an `intensity/period` and a token budget per subtree,
   with the compounding warning applied to both. **INFERRED, unmodelled anywhere in prior art.**

---

## Sources

Local (this repo and the owner's):
`README.md`, `docs/design/functional-design.md`, `docs/discovery-session-sidecar.md`,
`docs/.research/prior-art/SYNTHESIS.md`, `docs/.research/prior-art/cultureagent.md`,
`prototypes/common/SPEC.md`, `PITFALLS.md`, `HANDOFF.md`;
`~/source/dgx-fleet/{INVENTORY.md, WHY.md, playbooks/site.yml, roles/*/meta/main.yml,
inventories/production/host_vars/dgx-01.yml.example}`.

External, scraped 2026-08-06 (copies under the session scratchpad):
- https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/
- https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/
- https://kubernetes.io/docs/concepts/architecture/nodes/
- https://www.erlang.org/doc/system/sup_princ.html
- https://raw.githubusercontent.com/akka/akka/main/akka-docs/src/main/paradox/typed/{cluster,cluster-membership,cluster-sharding}.md
- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/{tutorial/teams,selector-group-chat,swarm}.html
- https://docs.crewai.com/en/concepts/{agents,processes}
- https://raw.githubusercontent.com/langchain-ai/langgraph-supervisor-py/main/README.md
- https://raw.githubusercontent.com/langchain-ai/langgraph-swarm-py/main/README.md
- https://raw.githubusercontent.com/FoundationAgents/MetaGPT/main/README.md
- https://raw.githubusercontent.com/OpenBMB/ChatDev/chatdev1.0/CompanyConfig/Default/{RoleConfig,ChatChainConfig}.json
- http://www.fipa.org/specs/fipa00029/SC00029H.html (FIPA Contract Net Interaction Protocol)

Not fetched in this pass and therefore not relied on: Akka Scala/Java API pages (roles read
from the paradox docs, not `Member.hasRole` source); `langgraph` concepts/multi_agent doc
(404 at both raw paths tried — the two prebuilt-library READMEs were used instead); AutoGen
v0.2 `GroupChat` (superseded by the v0.4 AgentChat pages read here); agentirc server source
(cultureagent's presence semantics taken from the prior-art file, itself second-hand on the
server side).
