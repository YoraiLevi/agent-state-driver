# Distributed schedulers and orchestrators: what transfers to an agent fleet

Research pass for the multi-machine, role-based agent mesh. Scope: Kubernetes, HashiCorp
Nomad, Ray, Temporal, Celery/Kombu, SLURM, Erlang/OTP supervision, SWIM/memberlist.

**Method.** Every mechanism claim below is grounded in a primary vendor doc, scraped
2026-08-06 and archived under `.research/prior-art-search/` (filenames cited inline so a
reviewer can re-read the exact text without re-fetching). Claims are labelled:

- **OBSERVED** — quoted or paraphrased from the cited primary doc, or from a file in this repo.
- **INFERRED** — this researcher's design judgment. Not sourced. Argue with it freely.

The project-side facts (seven states, sidecar, fusion, conflict) are cited to
`docs/design/functional-design.md`, `docs/discovery-session-sidecar.md`,
`prototypes/common/SPEC.md`, and `docs/.research/prior-art/SYNTHESIS.md`.

---

## Verdict

1. **Every mature scheduler surveyed detects a dead worker the same way: a timeout on a
   self-report. Not one can distinguish "working" from "wedged."** Kubernetes expires a
   Lease; Nomad expires a heartbeat TTL; Temporal's own doc states outright that "The
   Temporal Server doesn't detect failures when a Worker loses communication with the Server
   or crashes. Therefore, the Temporal Server relies on the Start-To-Close Timeout to force
   Activity retries" (OBSERVED, `…docs.temporal.io_encyclopedia_detecting-activity-failures…`);
   Celery re-delivers on a visibility timeout; SWIM pings and gives up. This is the same
   finding SYNTHESIS reached inside the agent world (SYNTHESIS.md:41-45, C5) — it holds one
   layer up too. Our verified state is not "a better heartbeat"; it is a **different
   epistemic class**, and the design should say so in exactly those terms.

2. **Do not put per-agent liveness on the control plane. Copy Kubernetes' two-tier split.**
   K8s separates a cheap node-level Lease (`nodeLeaseDurationSeconds` default 40, "renewed
   every 10s, per KEP-0009", OBSERVED, `…kubelet-config.v1beta1…`) from rich per-pod status.
   Nomad shows the cost of not splitting: heartbeat TTL is computed as
   `<number of Clients> / <max_heartbeats_per_second>` (default 50.0), so at 10 000 clients
   the client TTL is **200-400 s** and the doc marks "safe after elections: NO" (OBSERVED,
   `…nomad_docs_configuration_server…`). A fleet-scale heartbeat is structurally too slow to
   be an agent-liveness signal. Architecture: **verified agent state is read locally by a
   per-host supervisor at ~1 s, and only state *edges* leave the machine.** Edge-triggered
   propagation is already the validated shape twice over — cultureagent's presence emitter
   (SYNTHESIS.md:471-474, C11) and the sidecar itself, which is explicitly edge-triggered and
   not a heartbeat (`docs/discovery-session-sidecar.md:53-56`).

3. **The unit of work is a durable workflow whose activities are turns, executed against a
   pinned actor — never a queue job.** Three properties kill the job model: agent work is
   non-idempotent (it mutates a worktree), expensive (dollars per turn), and *can block on a
   human for hours*. Temporal supplies durability and the human-wait primitive; Ray supplies
   the right dispatch default — actor tasks are **at-most-once by default**
   (`max_task_retries=0`) precisely because actor state makes blind retry unsafe (OBSERVED,
   `…ray-core_fault_tolerance_actors…`). Celery's own FAQ makes the counter-case for us:
   `acks_late` is only safe "if your task is idempotent" (OBSERVED, `…celeryq…faq…`). Steal
   Temporal's shape, Ray's default, and reject Celery's redelivery model outright.

4. **Replace `ack` with `evidence` at the dispatch boundary.** Every queue has the same hole:
   an ack proves a message was received, never that work happened, and its absence is
   ambiguous between "lost" and "slow." We can close it. Bind-time protocol: the scheduler
   assigns optimistically from a possibly-stale cache (k8s informer shape), and the host
   supervisor **must re-verify `state == idle` with evidence and reject the assignment
   otherwise** — Nomad already has the rejection half of this as leader `plan_rejection_tracker`
   (OBSERVED, `…nomad_docs_configuration_server…`), and k8s has it as kubelet admission.
   Neither can *prove* readiness at bind time. We can (`README.md:49`, `send` refuses unless
   idle; `prototypes/common/SPEC.md:36-37`). (INFERRED: this is the single highest-value
   transfer in this document.)

5. **Invert Kubernetes' unreachable-node default. Quarantine, do not reschedule.** K8s taints
   an unreachable node (`node.kubernetes.io/unreachable: NoExecute`) and "waits 5 minutes
   between marking the node as `Unknown` and submitting the first eviction request"
   (OBSERVED, `…architecture_nodes…`). That default is correct when pods are cheap and
   fungible. Our agents are neither: rescheduling an agent whose machine merely went
   unreachable produces **two live agents spending money into the same worktree**. Default
   must be: unreachable host → `unknown`, stop dispatching, do **not** re-dispatch its work
   until a positive fencing action succeeds. K8s's own defensive brakes are the pattern to
   copy instead — eviction rate reduced above `--unhealthy-zone-threshold` (0.55), evictions
   *stopped entirely* for clusters ≤ `--large-cluster-size-threshold` (50), and no evictions
   at all when every zone is unhealthy because the control plane assumes the fault is its own
   connectivity (OBSERVED, same file).

6. **`waiting:permission` is a backpressure signal on a human queue — a resource no surveyed
   scheduler models.** Temporal's equivalent is a *pathology*: Schedule-To-Start latency
   means "workers can't keep up" (OBSERVED, Temporal doc). For us, a rising count of agents
   in `waiting:permission` means the fleet is saturating a *human*, and the scheduler should
   throttle dispatch of task classes that generate prompts. (INFERRED, but it follows
   directly from having the state at all — and cultureagent, the only system that got close,
   **deleted** the state at the source via `bypassPermissions` / `approve_all` rather than
   scheduling on it, SYNTHESIS.md:390, C9.)

7. **Gossip for membership; a single-writer/raft registry for anything that must not be
   double-granted.** memberlist is "eventually consistent but converges quickly on average"
   and its Lifeguard extension exists specifically to survive "slow message processing (due
   to factors such as CPU starvation…)" (OBSERVED, `…github.com_hashicorp_memberlist…`) —
   which is the literal operating condition of a host running twenty agents. Use SWIM for
   *which machines exist*. Never gossip a worktree lease or a task assignment; eventual
   consistency there means two agents in one checkout.

8. **Steal OTP's supervision-tree *topology* for the role mesh, and its restart-intensity
   circuit breaker; discard its restart economics.** `one_for_one` / `rest_for_one` /
   `one_for_all` map exactly onto "restart just this worker" / "restart it and everything
   downstream" / "restart the whole squad," and when more than `intensity` restarts occur in
   `period` seconds "the supervisor terminates all the child processes and then itself"
   (OBSERVED, `…erlang.org_doc_system_sup_princ…`) — escalation that propagates *upward* is
   exactly the missing safety valve in every agent orchestrator surveyed. But OTP assumes
   restart is nearly free; an agent restart costs a fresh context window in dollars and lost
   working knowledge. (INFERRED: set intensity to 1-2, not OTP-typical values, and treat
   "restart" as a last resort below "checkpoint and hand off.")

---

## Findings

### 1. How each system detects a dead or hung worker — and what verified state adds

| System | Death detection mechanism (OBSERVED) | Can it see "hung but alive"? | What verified state adds |
|---|---|---|---|
| **Kubernetes** | Two heartbeats: `.status` updates and a Lease per node in `kube-node-lease`. `nodeLeaseDurationSeconds` default **40**, "lease is currently renewed every 10s, per KEP-0009"; `--node-monitor-period` default **5s**, `--node-monitor-grace-period` default **50s**. On expiry the node controller sets `Ready=Unknown` and adds `node.kubernetes.io/unreachable:NoExecute` | **No.** The kubelet renews the lease as long as *the kubelet process* is healthy. Every container on the node can be wedged and the node stays `Ready` | We can renew a lease *conditional on evidence about the workload*, not about the supervisor. A lease you cannot renew without proving agent state is strictly stronger than any node lease |
| **Nomad** | Client heartbeats forwarded to the leader; missed heartbeat → node `down`, allocations `lost` (or `disconnected` if `disconnect.lost_after` set) and replaced. TTL = `clients / max_heartbeats_per_second` (50.0) × up to 2× jitter, floored by `min_heartbeat_ttl` (10s), plus `heartbeat_grace` (10s); `failover_heartbeat_ttl` 5m after an election | No — same class | The heartbeat's own doc states the tradeoff: "The longer the heartbeat period, the longer Nomad takes to replace a down Client's workload. The shorter… the more likely transient network issues… could cause a perfectly functional Client… to be marked as down." Verified state removes the tradeoff at the agent tier by not inferring from silence |
| **Temporal** | Start-To-Close timeout (per Activity Task attempt) is the primary crash detector; Heartbeat + Heartbeat Timeout for long activities. Heartbeats are throttled at `min(heartbeatTimeout*0.8, maxHeartbeatThrottleInterval)`, defaults `defaultHeartbeatThrottleInterval` 30s / `maxHeartbeatThrottleInterval` 60s | No, and the doc says so verbatim (quoted in Verdict 1) | An agent turn's legitimate duration ranges minutes to hours, so a Start-To-Close timeout tuned not to false-fire is useless as a hang detector. Our `presumed_hung` is computed from *positive* busy-assertion plus staleness (functional-design.md:63, SPEC.md:59-60), not from an unbounded duration guess |
| **Celery / Kombu** | Broker-level: Redis transport emulates ack (`ack_emulation = True`) with a `visibility_timeout` — unacked messages are restored (`restore_unacked`, `restore_visible`) after it elapses. `task_acks_late` default **Disabled**; `task_reject_on_worker_lost` default **Disabled** | No. "the worker isn't known to crash" (FAQ, verbatim) | Nothing about a redelivery timer can tell whether the prior execution half-happened. We can read the transcript and the live state instead of guessing |
| **Ray** | Actor process failure → optional restart via `max_restarts` (default **0**, `-1` = infinite); after the limit "subsequent actor methods will raise a `RayActorError`". Dispatch is at-most-once by default; at-least-once opt-in via `max_task_retries` | Partially — it detects process death, not application wedge | Same gap; Ray's honesty is useful though: "this exception may be thrown even though the task did indeed execute successfully" — the ambiguity is *documented* |
| **SLURM** | Node health via slurmd contact + configurable health-check; job death via exit status and time limits | No | — |
| **Erlang/OTP** | Process link/monitor: exit signals are synchronous and reliable *within a node*; between nodes, `net_ticktime` heartbeats | No — a `gen_server` in an infinite loop is alive forever | This is the classic result: liveness ≠ progress. Our channels (screen motion + sidecar status + process) are precisely a progress oracle |
| **SWIM / memberlist** | Direct probe → indirect probe through k peers → suspect → confirm. "Node failures are detected and network partitions are partially tolerated by attempting to communicate to potentially dead nodes through multiple routes" | No — process-level only | Correct tool for *machine* membership; wrong tool for agent state |

**The pattern (INFERRED).** Every one of these detects death by *absence of a signal a healthy
worker would have sent*. That makes the false-positive rate a direct function of how long you
are willing to wait, and the false-negative rate a function of how honest the reporter is.
Our channel set is *presence of positive evidence from outside the reporter* — vendor-written
sidecar status, rendered screen, and OS process liveness, fused, with disagreement surfaced as
`conflict` rather than resolved (SPEC.md:14-20). That is the only structural advantage the
fleet has, and every fleet-level design decision should be traced back to it.

### 2. The right unit of work

**Not a job.** The queue-job model (Celery, k8s `Job`, SLURM batch) assumes: idempotent
retry, cheap re-execution, no mid-execution human dependency, and fungible workers. Agent
work violates all four.

**Not a bare actor either.** Ray actors give identity and state affinity, but Ray has no
durable history: if the driver dies, the computation is gone.

**The composite (INFERRED):**

```
Task              = durable workflow            (Temporal-shaped)
                    · event-history-backed, survives orchestrator restart
                    · owns the human-wait: parks on a signal, not a timeout
                    · owns retry policy at operator-declared safe boundaries only
   │
   ├─ Turn        = activity                    (Temporal-shaped, heartbeat REPLACED)
   │                · liveness = verified state from the host supervisor,
   │                  not a self-reported activity heartbeat
   │                · Start-To-Close set to a cost ceiling, not a hang detector
   │
   └─ Agent       = pinned actor                (Ray/StatefulSet-shaped)
                    · identity + location affinity: its state IS the worktree
                      + the session transcript, both on one machine
                    · at-most-once dispatch (Ray default)
                    · max_restarts small; restart escalates to the squad
                      supervisor (OTP intensity/period)
```

Two consequences worth stating explicitly:

- **A `waiting:permission` agent must not free its slot.** In Temporal an activity that blocks
  should ideally release the worker; here the agent *is* the slot and its context window is
  the state. Model it as a distinct scheduler condition (`blocked-on-human`) that is neither
  runnable nor reclaimable. (INFERRED.)
- **Gang scheduling has a real analogue.** Ray placement groups "atomically reserve groups of
  resources across multiple nodes… If a bundle can't fit in any of the current nodes, Ray
  reserves no resources" with `PACK`/`SPREAD`/`STRICT_PACK`/`STRICT_SPREAD` (OBSERVED,
  `…placement-group…`). A role squad (lead + reviewers + implementers) that only functions
  complete is exactly a `STRICT_PACK`-or-fail bundle. Partial squad admission is a money
  leak: idle members burn nothing but hold worktrees and quota reservations.

### 3. Partition, split-brain, fencing

**What they do (OBSERVED):**

- K8s: per-availability-zone eviction policy exactly so "one availability zone might become
  partitioned from the control plane while the others remain connected"; and the corner case —
  when *all* zones are unhealthy, "the node controller assumes that there is some problem with
  connectivity between the control plane and the nodes, and doesn't perform any evictions."
- Nomad: `failover_heartbeat_ttl` (5m) grants every client a long grace after a leader
  election, "in case they were directly connected to a leader that crashed"; and a documented
  correction formula for >5000 clients.
- memberlist: indirect probes route around single-path partitions; Lifeguard adds "situational
  awareness" for self-diagnosed slowness.

**What we must add (INFERRED).** None of these fence. K8s evicts a pod on an unreachable node
without proving the container stopped — safe because the pod is stateless and its storage is
usually externally fenced. Our shared resource is a **git worktree**, and the failure is not
data loss but *two agents committing conflicting work and both charging money*.

Design consequence — three tiers, only one of them strongly consistent:

```
tier            mechanism                      consistency     what breaks if wrong
──────────────  ─────────────────────────────  ──────────────  ────────────────────────
machines        SWIM/memberlist gossip         eventual        slow discovery (tolerable)
agent state     local verified read, edge-push evidence-backed a stale view (bind-time
                to control plane                               re-verify catches it)
leases/assign   raft or single-writer          linearizable    DOUBLE-SPEND — never gossip
```

The lease itself should be the novel part: **a worktree lease renewable only on presentation
of fresh evidence about the agent that holds it.** A k8s node lease renews on kubelet
liveness; ours renews on `state ∈ {busy, idle, waiting:*}` with an evidence timestamp. Loss
of evidence ⇒ lease expires ⇒ the worktree is reclaimable *after* a fencing action (host
supervisor confirms kill, or the branch is force-reserved). (INFERRED.)

### 4. At-least-once vs at-most-once

**OBSERVED, the two poles:**

- Celery default is early-ack (at-most-once; task lost if the worker dies mid-execution).
  `task_acks_late` flips it to at-least-once; the FAQ's own worked example is a task that
  increments a counter, writes metadata, and copies a file — "If this crashed in the middle
  of copying the file to its destination the world would contain incomplete state." The
  guidance is: "use retry for Python errors, and if your task is idempotent combine that
  with `acks_late`."
- Ray: at-most-once by default for actor tasks; at-least-once opt-in, with the explicit
  warning that "Retried methods may execute twice, once on the failed actor and a second
  time on the restarted actor."

**Position (INFERRED).** Take **at-most-once by default**, per turn. An agent turn is the
Celery `process_upload` example with a credit card attached. Then use the differentiator to
do what neither can: on a suspected loss, **do not choose between redeliver and drop —
investigate.** The host supervisor can read the sidecar, the transcript, and the process, and
answer "did this turn run, and is it still running?" with evidence. Retry becomes a decision
made on observation rather than a policy applied on a timer.

Operator-declared safe-retry boundaries (the only place at-least-once is allowed): a task
that begins from a *fresh* worktree at a known commit and whose side effects are confined to
that worktree. Everything else is manual. (INFERRED.)

### 5. Backpressure

**OBSERVED.** Temporal's Schedule-To-Start timeout has "two primary use cases: detect whether
an individual Worker has crashed. Detect whether the fleet of Workers polling the Task Queue
is not able to keep up," and the doc recommends monitoring
`temporal_activity_schedule_to_start_latency` *instead of* setting the timeout — because the
timeout "is non-retryable by design… as a retry would place the Activity Task back into the
same Task Queue." Nomad rate-limits heartbeat processing via `max_heartbeats_per_second`. K8s
rate-limits evictions (`--node-eviction-rate` 0.1/s, `--secondary-node-eviction-rate` 0.01/s).

**Transfer (INFERRED).** The scarce resources in an agent fleet are not CPU and memory:

| Scarce resource | Observable today? | Backpressure action |
|---|---|---|
| API rate limit / token budget per account | Partially — transcript has turn durations; OTel has cost metrics but with 37.9 s measured lag (functional-design.md:94) | Admission control per account; a `quota-exhausted:NoSchedule` host/account taint |
| **Human attention for permission dialogs** | **Yes, directly — this is ours alone** | Throttle dispatch of prompt-generating task classes when `count(waiting:permission)` exceeds the roster of available approvers |
| Worktree / branch locks | Yes (lease registry) | Queue on the lease, do not spin up an agent that will block |
| Host CPU (a machine with N agents starves) | Yes (OS) | Cap agents per host; note memberlist's Lifeguard exists for exactly this failure |

Copy k8s's *rate-limited* actuation shape everywhere: never take a fleet-wide corrective
action at full speed, and stop entirely when the observation itself looks suspect.

### 6. Cost and quota fairness

SLURM is the only surveyed system with a real fairness model, and it transfers almost
unchanged (OBSERVED, `…priority_multifactor…`):

```
Job_priority = site_factor
             + PriorityWeightAge       * age_factor
             + PriorityWeightAssoc     * assoc_factor
             + PriorityWeightFairshare * fair-share_factor
             + PriorityWeightJobSize   * job_size_factor
             + PriorityWeightPartition * priority_job_factor
             + PriorityWeightQOS       * QOS_factor
             + SUM(TRES_weight_<t> * TRES_factor_<t>, …)
             - nice_factor
```

All factors normalize to 0.0-1.0; weights are unsigned 32-bit; the doc warns to start weights
"around 1000 or so for those factors you want to make predominant" so significant digits
survive. Fair-share does not cap: "jobs charging accounts that are under-serviced are
scheduled first, while jobs charging accounts that are over-serviced are scheduled when the
machine would otherwise go idle." `TRESBillingWeights` lets you bill non-CPU resources
(memory, licenses, GRES) at distinct weights.

**Transfer (INFERRED).** `TRESBillingWeights` is a direct fit for **per-model billing weights**
(an Opus turn and a Haiku turn are not the same unit) and for token-vs-wallclock blending.
The weighted-sum-of-normalized-factors formula is a good **policy language for a configurable
mesh** — roles become QOS/partition analogues, and squad membership becomes an association.
The half-life decay behind fair-share is what stops one long-running project from permanently
owning the fleet.

### 7. Preemption

**OBSERVED (SLURM).** Modes: cancel, requeue, suspend/resume, or share via gang scheduling —
selectable per partition or per QOS. `GraceTime` (default 0) sets a preemption delay: "Once a
job has been selected for preemption, its end time is set to the current time plus GraceTime.
The job is immediately sent SIGCONT and SIGTERM signals in order to provide notification of
its imminent termination. This is followed by the SIGCONT, SIGTERM and SIGKILL signal
sequence upon reaching its new end time."

**Transfer (INFERRED).** Of the four modes:

- **CANCEL** — throws away paid-for work and leaves a dirty worktree. Last resort.
- **REQUEUE** — actively dangerous: non-idempotent re-execution (see 4).
- **SUSPEND** — tempting (SIGSTOP preserves the context window) and PITFALLS already uses
  SIGSTOP as a deterministic test tool (`HANDOFF.md:45-46`). Risk: an in-flight API request
  and any server-side session timeout. Unverified.
- **The right one is a fifth mode SLURM does not have: cooperative checkpoint.** Send the
  agent "commit what you have and write a handoff," then **wait for verified `idle`**, then
  reclaim. `GraceTime` becomes "grace turns" plus a hard wall-clock ceiling. This is only
  implementable because we can prove the checkpoint landed — a screen-scraper cannot
  distinguish "wrote the handoff" from "is still typing it." (INFERRED, and it is the second
  clearest payoff of the differentiator after bind-time verification.)

### 8. Scheduling mechanics worth copying verbatim

- **Predicates then priorities** (k8s filter/score): hard constraints first (OS, credentials
  for org X, worktree locality, model availability), then soft scoring. Trivially portable.
- **Taints/tolerations** (OBSERVED: node controller "adds taints corresponding to node
  problems like node unreachable or not ready. This means that the scheduler won't place Pods
  onto unhealthy nodes"): the right vocabulary for a heterogeneous mesh —
  `os=windows:NoSchedule`, `no-docker:NoSchedule`, `quota-exhausted:NoSchedule`,
  `unreachable:NoExecute`. Note we gain a taint source nobody else has: taints derived from
  *observed agent evidence* rather than node self-report.
- **Informer/watch cache + optimistic bind + admission rejection** (k8s), and Nomad's
  `plan_rejection_tracker` for when the optimism is wrong repeatedly. Our version adds a
  bind-time evidence check (Verdict 4).
- **Drivers as an abstraction** (Nomad): one scheduler, N execution backends. Maps onto the
  existing adapter interface (functional-design.md:29-30, C11) — tmux backend, ConPTY
  backend, and later non-Claude agent backends.

---

## What to steal

1. **Two-tier liveness** — k8s node Lease (cheap, machine-level, fleet-scale) + rich local
   per-agent verified state, edge-pushed. Never a per-agent heartbeat to the control plane.
2. **Bind-time verification** — kubelet-admission / Nomad-plan-rejection, upgraded: the host
   supervisor rejects an assignment unless it can *prove* the agent is idle, with evidence.
3. **Durable-workflow task, pinned-actor agent, turn-as-activity** (Temporal + Ray composite).
4. **Ray's at-most-once default** (`max_task_retries=0`) as the dispatch default, with
   at-least-once only at operator-declared fresh-worktree boundaries.
5. **OTP supervision topology + restart intensity/period** for the role mesh, with upward
   escalation — a crash-looping agent takes down its squad rather than burning money forever.
   (cultureagent's `MAX_CRASH_COUNT=3`/`CRASH_WINDOW_SECONDS=300` is the same idea
   independently derived, SYNTHESIS.md:337-338.)
6. **SLURM's multifactor priority formula and `TRESBillingWeights`** as the fairness/quota
   policy language; bill per-model, decay over a window.
7. **Ray placement groups (`STRICT_PACK`, atomic-or-nothing)** for role squads.
8. **K8s's defensive brakes**: rate-limited actuation, zone-aware thresholds, and the
   "if everything looks broken, assume *we* are broken and do nothing" rule.
9. **Taints/tolerations vocabulary** for heterogeneous hosts, extended with evidence-derived
   taints.
10. **SWIM/memberlist (with Lifeguard) for machine membership only.**
11. **SLURM `GraceTime`'s shape** for preemption notification — reinterpreted as cooperative
    checkpoint with a verified-idle completion check.
12. **Temporal's advice to monitor schedule-to-start latency rather than set the timeout** —
    generally: prefer a metric that reveals saturation over a timeout that punishes it.

## What to avoid and why

| Pattern | Source | Why it is wrong for agents |
|---|---|---|
| Timeout-only crash detection | Temporal Start-To-Close (doc admits it) | Agent turns legitimately run minutes-to-hours and compaction produces silent gaps (functional-design.md:74-76). A timeout long enough to avoid false fire cannot detect a hang |
| Visibility-timeout redelivery | Celery/Kombu Redis `ack_emulation` + `visibility_timeout` | Redelivers a non-idempotent, expensive, side-effecting prompt. Celery's own FAQ restricts `acks_late` to idempotent tasks |
| `task_reject_on_worker_lost` style re-queue | Celery | The doc itself warns "Enabling this can cause message loops" |
| Evict-on-unreachable after a grace period | K8s (5 min `Unknown` → eviction) | Produces two live agents in one worktree. The machine is probably fine; the *network* is not |
| Fleet-size-scaled heartbeat as the agent liveness path | Nomad (200-400 s TTL at 10k clients) | A hung agent would burn ≥3 minutes of nothing before anyone noticed |
| At-least-once actor retries | Ray `max_task_retries=-1` | Ray's doc: "Retried methods may execute twice" — for us that is double spend plus conflicting commits |
| Gossip-carried assignment or leases | memberlist (eventual by design) | Double-grant of a worktree. Membership only |
| Aggressive OTP-style restart | OTP defaults assume cheap restarts | An agent restart loses a context window; restarts must be rare, budgeted, and escalate |
| SLURM `REQUEUE` / blind `SUSPEND` preemption | SLURM `PreemptMode` | Requeue is non-idempotent re-execution; suspend's interaction with in-flight API calls and session timeouts is unverified |
| Modelling a human wait as a failure or timeout | Temporal Schedule-To-Start, Celery visibility timeout | A `waiting:permission` can last hours and is a *correct* state, not a fault |
| Eliminating the permission state to simplify scheduling | cultureagent (`bypassPermissions`, `approve_all`), SYNTHESIS.md:390 | Destroys the signal we uniquely have, and PITFALLS/functional-design.md:124-128 already rejected bypass on safety grounds |
| Central polling of N agents' state | naive | Poll locally at the host, push edges. The sidecar is edge-triggered anyway (`discovery-session-sidecar.md:53-56`) |
| Renewing a lease on supervisor liveness | K8s node lease | A healthy kubelet with every container wedged still holds the lease. Bind lease renewal to workload evidence |

## Open questions for the design

1. **What is the compaction duration distribution?** It sets the `presumed_hung` threshold,
   and at fleet scale it also sets how long the scheduler must tolerate an agent looking
   silent before quarantining it. Still open in `functional-design.md:257`.
2. **What is the fencing primitive for a worktree across machines?** A raft-backed lease is
   the registry side; the *enforcement* side (what stops a partitioned host's agent from
   committing) is unspecified. Options: branch reservation server-side, a pre-commit hook
   that checks the lease, filesystem-level lock. None verified.
3. **Does the sidecar (or any equivalent) exist for non-Claude agents?** "Claude Code and
   friends" implies backend heterogeneity, but verified state is proven for exactly one
   vendor. If Codex/Gemini have no equivalent, the mesh degrades to self-report for those
   hosts and the scheduler needs a per-agent *confidence class*, not just a state.
4. **What is the observable, low-latency source for quota/cost accounting?** Fair-share needs
   a billing ledger. OTel carries cost but at 37.9 s measured lag (functional-design.md:94) —
   fine for billing, useless for admission control. Is there a faster source (transcript
   `turn_duration` plus token counts)?
5. **Can two supervisors on one machine both drive one session?** The sidecar is read-only and
   carries no ownership. Local ownership arbitration (a lock file keyed by `sessionId`) is
   unspecified and is a split-brain path *inside* a host, below the level any surveyed system
   models.
6. **What is the per-agent state-change event rate, and at what fleet size does edge-push
   saturate the control plane?** Nomad published a heartbeat-cost table; we have no equivalent
   number and cannot size the mesh without it.
7. **Does SIGSTOP-based suspend survive an in-flight API request and a session timeout?**
   Determines whether SUSPEND-class preemption exists at all.
8. **Is `waiting:input` decomposable by question kind?** Routing "which approach do you want"
   to a tech lead and "approve this rm -rf" to an operator requires more than one waiting
   slot — SYNTHESIS C8 already flagged that there are at least three waiting states and v1
   merged two deliberately (functional-design.md:62).
9. **What is the correct behavior when the control plane cannot reach a host but the host's
   agents are provably fine?** K8s's answer is "do nothing." Ours could be better: a host
   supervisor that can *prove* its agents' states could be allowed to continue autonomously
   under a pre-granted budget until the partition heals. Untested, potentially the most
   interesting mesh property. (INFERRED.)

---

## Sources

Primary docs scraped 2026-08-06; archived copies in `.research/prior-art-search/`
(filename prefixes given for exact re-read).

- Kubernetes, Nodes — heartbeats, node controller, eviction rates, taints —
  https://kubernetes.io/docs/concepts/architecture/nodes/ · `20260806_055620_365330_…`
- Kubernetes, kubelet config v1beta1 — `nodeLeaseDurationSeconds`, `nodeStatusUpdateFrequency`,
  `nodeStatusReportFrequency` — https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/ ·
  `20260806_055639_835079_…`
- Kubernetes, kube-controller-manager flags — `--node-monitor-grace-period` (50s),
  `--node-monitor-period` (5s) —
  https://kubernetes.io/docs/reference/command-line-tools-reference/kube-controller-manager/ ·
  `20260806_055640_489441_…`
- Kubernetes, labels/annotations/taints — `node.kubernetes.io/unreachable` —
  https://kubernetes.io/docs/reference/labels-annotations-taints/ · `20260806_055621_094984_…`
- Nomad, server block + Client Heartbeats section — `heartbeat_grace`, `min_heartbeat_ttl`,
  `failover_heartbeat_ttl`, `max_heartbeats_per_second`, TTL-vs-cluster-size table,
  `plan_rejection_tracker` — https://developer.hashicorp.com/nomad/docs/configuration/server ·
  `20260806_055735_358588_…`
- Nomad, architecture — https://developer.hashicorp.com/nomad/docs/architecture ·
  `20260806_055621_754372_…`
- Temporal, Detecting Activity failures — Schedule-To-Start / Start-To-Close /
  Schedule-To-Close, Activity Heartbeat + throttling defaults —
  https://docs.temporal.io/encyclopedia/detecting-activity-failures · `20260806_055643_199457_…`
- Celery, configuration — `task_acks_late`, `task_reject_on_worker_lost`,
  `broker_transport_options.visibility_timeout` —
  https://docs.celeryq.dev/en/stable/userguide/configuration.html · `20260806_055703_696276_…`
- Celery, FAQ — "Should I use retry or acks_late?" —
  https://docs.celeryq.dev/en/stable/faq.html · `20260806_055704_830280_…`
- Kombu, Redis transport — `ack_emulation`, `visibility_timeout`, `restore_unacked` —
  https://docs.celeryq.dev/projects/kombu/en/stable/reference/kombu.transport.redis.html ·
  `20260806_055702_457907_…`
- Ray, actor fault tolerance — `max_restarts`, `max_task_retries`, at-most-once default —
  https://docs.ray.io/en/latest/ray-core/fault_tolerance/actors.html · `20260806_055706_720147_…`
- Ray, placement groups — atomic gang reservation, PACK/SPREAD/STRICT_* —
  https://docs.ray.io/en/latest/ray-core/scheduling/placement-group.html · `20260806_055708_129985_…`
- SLURM, preemption — `PreemptMode`, `GraceTime` signal sequence —
  https://slurm.schedmd.com/preempt.html · `20260806_055729_226508_…`
- SLURM, multifactor priority — priority formula, fair-share, `TRESBillingWeights` —
  https://slurm.schedmd.com/priority_multifactor.html · `20260806_055730_547200_…`
- Erlang/OTP, Supervisor Behaviour — strategies, restart types, maximum restart intensity —
  https://www.erlang.org/doc/system/sup_princ.html · `20260806_055733_173387_…`
- hashicorp/memberlist — SWIM + Lifeguard, eventual consistency, indirect probes —
  https://github.com/hashicorp/memberlist · `20260806_055734_265665_…`

Repo-internal: `README.md`, `HANDOFF.md`, `PITFALLS.md`,
`docs/design/functional-design.md`, `docs/discovery-session-sidecar.md`,
`prototypes/common/SPEC.md`, `docs/.research/prior-art/SYNTHESIS.md`.
