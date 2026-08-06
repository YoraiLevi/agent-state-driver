# Fleet mesh — synthesis and recommended architecture

Synthesis of five research passes in this directory (`own-prior-art.md`, `agentculture.md`,
`distributed-patterns.md`, `transport-and-membership.md`, `roles-and-topology.md`,
`security-and-cost.md`) against the shipped primitive in this repo.

**Provenance.** **OBSERVED** = read first-hand in a repo file (path:line) or quoted from a
researcher file that cites a primary source. **INFERRED** = design judgment added by this
synthesis, not present in any input. Where two researchers disagree the disagreement is
named, not averaged — see *Where the researchers conflict*, which you should read before
the architecture.

---

## Verdict

- **The fleet has exactly one structural advantage and every decision below traces to it.**
  Every mature scheduler surveyed detects a dead worker by *timeout on a self-report* —
  Temporal's own doc says it verbatim ("The Temporal Server doesn't detect failures when a
  Worker loses communication… relies on the Start-To-Close Timeout", `distributed-patterns.md`
  verdict 1), Kubernetes' kubelet self-registers and self-reports, cultureagent ships
  `STATE_WORKING` that no backend emits, and the owner's own `agent-mesh` names class BB
  ("heartbeat fresh, dispatch wedged") with the mitigation *"heartbeat gated on loop
  liveness"* — still self-report. This repo reads state from **outside the reporter**:
  vendor sidecar + rendered screen + PID, fused, evidence-carrying, for sessions it did not
  spawn, on three OSes (`functional-design.md:95,99-116`). Frame the fleet as closing BB and
  AF, not as "a better presence system".

- **Ship one keystone primitive and the rest is ordinary distributed systems: the dispatch
  lease.** Three researchers converged on it independently from three directions —
  bind-time re-verification at the host supervisor (`distributed-patterns.md` verdict 4,
  from kubelet admission + Nomad `plan_rejection_tracker`), a short-TTL lease issued by the
  node observer that `send` refuses to honour when expired (`roles-and-topology.md`
  verdict 4), and cache-plus-confirm-before-dispatch (`own-prior-art.md` open question 2).
  It is the fleet-scale generalisation of a rule already shipped: `send` refuses unless idle,
  exit 4 (`README.md:49,94,101`). Nothing else in this document is novel; this is.

- **There are five liveness tiers and collapsing any two is the failure mode of every
  system surveyed.** `registry entry` < `reachability` (Tailscale handshake / broker
  connection) < `presence claim` (self-report) < `verified state` (fused evidence) <
  `lease` (verified state + a freshness bound + a signature). The mailbox KEYSTONE RULE
  (`own-prior-art.md`, `PROTOCOL.md:70-94`) is the first two tiers; cultureagent stops at
  the third; this repo owns the fourth; the fleet must add the fifth. **Never let a lower
  tier answer a question the higher tier is for.**

- **One writer of state per machine, and it is co-resident with the process.** Adopt
  agentirc's rule *"a peer may never overwrite a locally-hosted nick"*
  (`agentculture.md`, `presence.py:484-498`) as a hard mesh invariant: the **Warden** —
  one node agent per machine — is the sole author of every state row for agents on that
  machine, signs it, and no other party may write that row. This makes state a
  single-writer register per agent and removes an entire class of race.

- **Adopt the owner's existing vocabulary wholesale rather than inventing one.**
  `dgx-fleet` supplies roles-as-directories with `meta/argument_specs.yml` validated at
  load, `drained: true` as a declarative flag the play refuses to touch, `baseline` vs
  `dangerous` risk tags where the unattended path runs *only* `baseline`, `serial: 1`
  canary with pre-check/smoke/human-pause, one end-of-play evaluator for disruptive
  actions, and a designated primary instead of n=2 quorum. `agent-mesh` supplies the
  envelope (ULID, `{v,id,from,to,ts,kind,reply_to,sig}`), process-**then**-ack, `(from,id)`
  dedup and quarantine-on-bad-sig. **Do not design a third message layer**
  (`own-prior-art.md` verdict 1).

- **`waiting:permission` is a schedulable resource, not a fault — and nobody else models
  it.** cultureagent *deleted* the state at source (`bypassPermissions`, `approve_all`,
  SYNTHESIS C9); agentirc's six-value enum has no waiting state at all, so a
  blocked-on-a-human agent is reported as `thinking` and then mis-escalated to
  `presumed_hung` (`agentculture.md` verdict 2). Ours becomes a queue a human role
  subscribes to, and a backpressure signal that throttles dispatch of prompt-generating
  task classes.

- **The permanent-latch failure is the most likely production outage and it is a
  *placement* bug.** An `attached-noscreen` agent can *detect* a dialog and never *answer*
  one (`README.md:112-114`, SPEC rule 8). Dispatching dialog-generating work there creates
  a `waiting:permission` latch nothing in the mesh can clear. `posture_required` must be a
  hard placement predicate, re-evaluated during execution — the deliberate divergence from
  Kubernetes' `IgnoredDuringExecution` (`roles-and-topology.md` finding 2).

- **The biggest unclosed hole is that nothing authenticates the Warden's report.** Three
  researchers flag it and none resolves it (`roles-and-topology.md` open q6;
  `security-and-cost.md` open q1; `own-prior-art.md` open q3). A compromised or buggy node
  claiming `idle` for a dead agent reintroduces self-report one layer up. **Recommended
  resolution (INFERRED):** the driver stays stdlib-only and emits *unsigned* local JSON over
  a pipe; the Warden — a separate binary that already holds a transport identity (NATS
  NKey / tsnet node key) — signs the row. That preserves `README.md:53` and puts the
  signature at the machine boundary where it belongs. Second-observer sampling and a
  dead-man's switch cover the residual.

---

## Where the researchers conflict

Read this first; it changes how the architecture reads.

| # | Conflict | Position A | Position B | Resolution taken here |
|---|---|---|---|---|
| 1 | **Transport** | `transport-and-membership.md`: NATS+JetStream on top of Tailscale; HTTP+SSE at small scale; MQTT's LWT criticised as reachability-not-liveness | `own-prior-art.md` open q1: agent-mesh's own `transport-fit.md` rated **MQTT strongest** on ack/cursor/persistent-session and rejected it *only* for lacking an iOS surface — a constraint that no longer applies | **NATS+JetStream.** MQTT's win was scored against a phone leg we don't have, and MQTT has no CAS/KV primitive, which the lease tier requires. MQTT is the runner-up (section 3), and its named hazard — a spoofed `CONNECT` with a duplicate `clientId` destroying another client's persistent session — is disqualifying for a fleet whose identity story is the product |
| 2 | **Speak agentirc's wire, or not** | `agentculture.md` verdict 1: AgentIRC 9.12.0 ships a byte-specified presence protocol; *"do not invent a presence wire — emit theirs"*, ideally as an S2S peer | `agentculture.md` itself (avoid 4, 6) + `security-and-cost.md`: agentirc#56 lets **any linked peer assert presence for any nick it does not host, with no trust check**; the 512-byte line drops `task` on overflow so evidence cannot ride it | **Split the layers.** agentirc PRESENCE is an **egress projection only** — lossy, declared, one-way. It is never an ingress path into fleet-authoritative state, and we never federate *in*. Interop is free; trust is not inherited |
| 3 | **Restart budget size** | `distributed-patterns.md` verdict 8: set OTP `intensity` to **1-2**, because an agent restart costs a context window in dollars; rank cooperative checkpoint above restart | `roles-and-topology.md` role schema: `intensity: 3 / period_s: 300` (inherited from cultureagent `MAX_CRASH_COUNT=3` / `CRASH_WINDOW_SECONDS=300`) | **Two budgets, not one.** A *crash* budget (the process died on its own) may be 3/300 s. A *deliberate restart* budget (we chose to kill a wedged agent) is 1/period. They are different events with different costs and must not share a counter. Both compound multiplicatively across supervision levels (OTP's own warning) |
| 4 | **Durable-workflow engine** | `distributed-patterns.md` verdict 3: the unit of work is a Temporal-shaped durable workflow whose activities are turns | Everything else in the corpus is stdlib/single-binary-shaped; `README.md:53` advertises no dependencies; `dgx-fleet` explicitly rejects AWX/Tower as *"overkill for a two-node fleet"* | **Steal the shape, not the engine.** Event-history-backed work-items with a human-wait primitive, implemented on JetStream + KV. Temporal is the named escape hatch if work-item semantics outgrow it — recorded as a decision, not a default |
| 5 | **Where the state cache lives** | `distributed-patterns.md`: informer-style cache at the broker, optimistic bind, host rejects | `own-prior-art.md` open q2: *"decide, not assume"* between a directory document, a cache, and a synchronous pull at dispatch | **Not a conflict once named.** Cache at the broker (fast, stale-tolerable) **plus** synchronous lease grant at the Warden (authoritative, partition-sensitive). The cache's age is carried in the lease's `evidence_max_age_ms`, so staleness is *data*, not an assumption |
| 6 | **Whether a detect-only member is in the mesh** | `roles-and-topology.md` open q5: is `attached-noscreen` a first-class role or excluded? | `security-and-cost.md`: a node advertises a capability vector and the scheduler matches roles to it | **First-class, with a role that cannot be dispatched dialog-generating work.** Exclusion loses the observability that is the whole point; the fix is a placement predicate, not a membership rule |

Two things all six researchers agree on, worth recording because agreement is also evidence:
**never gossip a lease or an assignment**, and **never resolve a channel disagreement by
picking a winner** (`SPEC.md` rule 9).

---

## 1. Recommended architecture

Seven layers. Each row of the diagram names what runs where; the tables below give the data
shape that crosses each boundary and the one-sentence justification.

```
                 ┌──────────────────────────────────────────────────────────┐
  L6 PROJECTION  │ agentirc PRESENCE export · irc-lens console · OTel/SIEM   │  egress only
                 └───────────────▲──────────────────────────────────────────┘
                 ┌───────────────┴──────────────────────────────────────────┐
  L5 WORK        │ work-items · envelopes (ULID, attenuated capability,      │  durable
                 │ hop, taint, budget) · human queues                        │
                 └───────────────▲──────────────────────────────────────────┘
                 ┌───────────────┴──────────────────────────────────────────┐
  L4 BROKER      │ stateless scheduler(s): predicates → priorities →         │  restartable
                 │ optimistic bind → lease request → revoke                  │  any host
                 └──────▲────────────────────────────────────▲──────────────┘
                 ┌──────┴──────────────────┐  ┌──────────────┴──────────────┐
  L3 LEDGER      │ roster · role bindings  │  │ leases · work ownership     │  linearizable
                 │ (CAS per entry)         │  │ (single-writer, R3)         │  never gossiped
                 └──────▲──────────────────┘  └──────────────▲──────────────┘
                 ┌──────┴────────────────────────────────────┴──────────────┐
  L2 BUS         │ NATS core (control, subject-per-node) + JetStream         │  1-3-5 servers
                 │ (evidence stream, durable consumers, KV)                  │
                 └───────────────▲──────────────────────────────────────────┘
   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ machine boundary ─ ─ ─ ─ ─ ─ ─
                 ┌───────────────┴──────────────────────────────────────────┐
  L1 WARDEN      │ ONE per machine. Sole author of state for its agents.     │  every host
                 │  ├── state driver (stdlib-only, unsigned local JSON)      │
                 │  ├── lease mint + signature (NKey)                        │
                 │  ├── node lease renewal (gated on a fresh sweep)          │
                 │  └── local ownership lock, keyed by sessionId             │
                 └───────────────▲──────────────────────────────────────────┘
                 ┌───────────────┴──────────────────────────────────────────┐
  L0 FABRIC      │ Tailscale tailnet: addressing, MagicDNS, tag-based ACL    │  every host
                 │ grants. Reachability credential — NOT identity, NOT       │
                 │ liveness.                                                 │
                 └──────────────────────────────────────────────────────────┘
```

### What runs where, and why

| Layer | Runs on | One-sentence justification |
|---|---|---|
| **L0 Fabric** — Tailscale | every machine (system `tailscaled`; `tsnet` in-process if the Warden is Go/Rust) | It supplies private addressing and a network-layer authorization boundary (tags + grants) that every broker option would otherwise force us to rebuild in application code (`transport-and-membership.md` finding 1). |
| **L1 Warden** — node agent | exactly one per machine, long-lived, restart-supervised by the OS | Verified state must be read at ~1 s next to the process; only *edges* may cross the machine boundary, because a fleet-scaled heartbeat is structurally too slow to be an agent-liveness signal (Nomad: 200-400 s client TTL at 10 000 clients, `distributed-patterns.md` verdict 2). |
| **L2 Bus** — NATS + JetStream | 1 server to start, 3 or 5 for JetStream quorum (⌊n/2⌋+1) | One static binary with a documented native-Windows service install, per-node crypto identity via NKeys, subject-per-node ordering, and a durable replayable evidence stream — the only option scoring on all four (`transport-and-membership.md` finding 3). |
| **L3 Ledger** — JetStream KV | co-located with the Bus servers | Leases and assignments must be linearizable or two agents spend money into one worktree; KV `revision` gives the CAS-per-entry that `agent-mesh/critique-isolation.md` proved is required after a shared-write substrate let one sender delete another's pending message. |
| **L4 Broker** — scheduler | any host; stateless; one *writer* per work-domain | Statelessness means a broker crash costs a dispatch decision, never state — and a designated primary per domain avoids shipping a consensus protocol for a fleet that dgx-fleet's own INVENTORY.md would call n=2 ("avoids split-brain by fiat"). |
| **L5 Work** — items + envelopes | stored in L3, carried on L2 | Retiring a task only on process-**then**-ack is the exact bug the owner already shipped and fixed once (`redesign-issue.md` 1: COMPLETED marked at poller-read, before the manager processed it). |
| **L6 Projection** — export | anywhere, read-only, off the message path | A checker that publishes evidence rather than verdicts is independently verifiable (watchtower model, `agent-mesh/monitoring-prior-art.md` 2.2); one-way export also means agentirc#56's missing trust check can never contaminate us. |
| **Human plane** (cross-cutting) | a role with an inbox, not an escape hatch | *"≥1 honest party suffices"* is the formal justification for human observe-all, and the human is the checker of last resort for the class no protocol closes (ack-gaming, `anticipated-failures.md` AF/AE). |

### Data shapes that cross each boundary

**Driver → Warden** (in-process pipe, local, unsigned — this is the boundary that keeps
`README.md:53` true):

```json
{"state":"waiting:permission",
 "attrs":{"waiting_for":"permission prompt","background_work":false,
          "screen_available":true},
 "evidence":[{"channel":"sidecar","signal":"status=waiting waitingFor=permission prompt","at":"2026-08-06T09:14:02.118Z"},
             {"channel":"screen","signal":"permission_dialog","at":"2026-08-06T09:14:02.640Z"}]}
```

**Warden → Bus — `StateEdge`** (edge-triggered, never a heartbeat; one subject per node,
`fleet.node.<node_id>.state`, because NATS consumer distribution is explicitly
*"partition-less and non-deterministic"* across subscribers on one subject):

```json
{"v":1,"kind":"state","id":"01JZ…ULID",
 "node":"nod_01JZ…","agent":"agt_01JZ…","session_id":"bfaf7ed8-…","pid":40326,
 "seq":4412,
 "state":"waiting:permission","prev":"busy",
 "attrs":{"waiting_for":"permission prompt","screen_available":true},
 "evidence":[{"channel":"sidecar","signal":"…","at":"…Z"},
             {"channel":"screen","signal":"permission_dialog","at":"…Z"}],
 "confidence":"fused-3ch",
 "backend":"claude-code","cli_version":"2.1.222",
 "observed_at":"…Z","published_at":"…Z",
 "sig":"ed25519:…"}
```

Four fields are non-obvious and each closes a named failure:
`seq` (monotone per `(node, agent)`) gives per-agent ordering the broker cannot get from
the transport; `prev` makes a missed edge detectable rather than silently absorbed;
`confidence` is the class a non-Claude backend degrades into (see section 5, and
`distributed-patterns.md` open q3); `sig` is the machine-boundary attestation.

**Warden → Broker — `Lease`** (the keystone; issued only in reply to a dispatch request,
never broadcast):

```json
{"v":1,"kind":"lease","lease_id":"01JZ…",
 "node":"nod_01JZ…","agent":"agt_01JZ…","work_item":"wi_01JZ…",
 "granted_state":"idle","evidence":[…],"evidence_max_age_ms":740,
 "pid_liveness":"kill0:ok@2026-08-06T09:14:03.001Z",
 "issued_at":"…Z","ttl_ms":15000,
 "sig":"ed25519:…"}
```

**Broker → Warden — `Dispatch`** (the `agent-mesh` envelope, extended with the fields
`security-and-cost.md` requires):

```json
{"v":1,"id":"01JZ…ULID","kind":"dispatch","from":"brk_a","to":"nod_01JZ…",
 "ts":"…Z","reply_to":"fleet.brk_a.reply",
 "work_item":"wi_01JZ…","lease_id":"01JZ…","role":"reviewer@3","agent":"agt_01JZ…",
 "payload":{"brief_ref":"wi_01JZ…/brief.md","verbatim":true},
 "capability":"biscuit:…",
 "hop":2,"taint":"agent-derived",
 "budget":{"usd_micros":250000,"plan_pct":2.0,"turns":6,"deadline":"…Z"},
 "sig":"ed25519:…"}
```

`payload.verbatim` is not decoration: *"a reworded brief silently drifts from"* the contract
the human confirmed (`agentculture.md`, `assign-to-workforce/SKILL.md`). The dispatch layer
must forbid paraphrase.

**Warden → Ledger — `AgentRecord`** (CAS per entry; join is human-gated and confirmed by
read-back; slugs are tombstoned, never reused — `anticipated-failures.md` BC):

```json
{"agent_id":"agt_01JZ…","node":"nod_01JZ…","session_id":"…","pid":40326,
 "roles":["reviewer@3"],"posture":"attached+screen",
 "channels":["sidecar","screen","process"],"confidence":"fused-3ch",
 "capabilities_probed":[{"cap":"tool:git","probe":"git --version","result":"2.45.1","at":"…Z"}],
 "backend":"claude-code","cli_version":"2.1.222",
 "sandbox":"seatbelt","isolation_class":"os-sandbox",
 "pubkey":"…","key_version":3,
 "joined":"…Z","drained":false,"tombstoned":false,
 "sig":"ed25519:…"}
```

**Any → Human — `Escalation`**: carries the full `evidence[]` array unmodified. The
per-answer evidence property must survive aggregation upward — **never a summarised
boolean** (`own-prior-art.md` verdict 7).

---

## 2. Topology options and recommendation

| | A. Supervisor tree (OTP) | B. Peer mesh + capability routing (K8s/Akka) | C. Market / Contract Net (FIPA) | D. Star with one manager (owner's mailbox) |
|---|---|---|---|---|
| Work discovery | pushed down by parent | selector match on a queue | bidding on a `cfp` | manager routes everything |
| Determinism | high | high | low | high |
| Loop control | `intensity`/`period` per level | `max_hops` + `lineage[]` + busy-seconds ratio | `reply-by` + bid budget | none defined |
| Human control | strongest (one escalation path) | strong (cordon/drain + human role) | weakest (human is a bidder) | strong but single-point |
| Fixed hierarchy? | yes | no | no | yes |
| Cost per decision | ~0 | ~0 | one model call per bidder | ~0 |
| Failure mode | over-restart cascade | scheduler is a component to run | silently-dead bidder (FIPA's own 1996 admission) | manager death stops the fleet |
| Verified state buys | restart on *proved* death, not silence | the whole model — selector says *may*, state says *can right now* | an honest bid: evidence, not a promise | kills phantom presence |

**Recommendation: A ⊕ B composed. C behind a flag for a named subset of queues. D
rejected as topology, adopted for its discipline.**

- **A carries lifecycle, safety and escalation only** — never work assignment. The owner
  has ruled out a fixed hierarchy; a supervision tree is not a routing hierarchy, and
  conflating them is what makes people reject both.
- **B is the data plane.** Work carries labels, roles carry `subscribes.match`, nodes carry
  labels and taints. A handoff is modelled as **emitting a new work-item with a reference**,
  not as transferring a context blob — which deletes LangGraph/AutoGen's superlinear
  context growth per hop and restores admission control the agent had unilaterally bypassed
  (`roles-and-topology.md`, "what to avoid").
- **Precedent that the hybrid is what mature systems actually do:** Akka uses
  `akka.cluster.roles` for placement yet still routes the first message per shard through a
  single `ShardCoordinator` (`roles-and-topology.md` finding, cluster-sharding.md:101-102).
- **C is the strongest demonstration of the differentiator and the weakest candidate for
  v1**: a bid can carry `evidence[]` rather than a promise, and the auctioneer can
  independently re-verify the winner before `accept-proposal` — closing the classic Contract
  Net hole where the winner was already dead when it bid. Cost: N model calls per auction,
  non-determinism, hardest to audit. Flag it, do not build it first.
- **D's discipline survives even though its shape does not**: earliest-timestamp election
  with self-demotion, orphan self-heal (never fabricate a missing role), and
  arm-the-watcher-before-announcing are all real fixes to observed races
  (`PROTOCOL.md:51-56,70-94,88-91`). Keep all three; drop the single hub.

---

## 3. Transport, membership, identity

### Recommendation

| Concern | Choice | Why |
|---|---|---|
| **Network / reachability** | Tailscale tailnet, composite role tags (`tag:fleet-worker-untrusted-linux`) | Tags do **not** AND in policy — *"you cannot define a rule that permits access to devices with both `tag:prod` and `tag:database`"* — so orthogonal role tags silently over-grant; composite tags are the documented workaround (`security-and-cost.md`, tailscale.com/kb/1068). |
| **Transport** | NATS core, subject `fleet.node.<node_id>.*` | Native Windows service install, one binary, no external coordinator, NKey identity, and per-subject ordering we control by subject design rather than assume from the broker. |
| **Durability / evidence ledger** | JetStream stream + durable consumers | At-least-once with server-tracked position is exactly "prove what we observed and when", replayable for incident review. |
| **Lease / assignment store** | JetStream KV with `revision` CAS, R3 | Linearizable per key; never gossiped; double-granting a worktree is the one failure that costs money twice and produces conflicting commits. |
| **Membership** | three-signal fusion: Tailscale peer `Online` + NATS connection + Warden **node lease** in KV, renewed every 10 s with a 40 s duration | Copies the k8s two-tier split (`nodeLeaseDurationSeconds` 40, renewed every 10 s), with the one improvement k8s cannot make — see below. |
| **Node identity** | self-minted UUID persisted to local disk at first run; Tailscale tag = authorization anchor; NKey = signing identity with `key_version` in the Ledger | A node's Tailscale IP and node key are **not stable across reinstall** (tailscale/tailscale#20568: new node key, new IP, registers as a second device). Tailscale identity is a credential, not a primary key. |
| **Agent identity** | durable slug + ULID, tombstoned on retire, never reused | Deregister races retire an entry with mail in flight (`anticipated-failures.md` BC); a reused slug silently delivers old work to a new agent. |
| **Driving / bootstrap** | Tailscale SSH, a *separate* channel | ~1-3 ms overhead per session is fine for launch/kill/push-the-binary and structurally wrong as a continuous state-poll bus (per-session cost compounds linearly with fleet size × poll rate). |

**The one improvement over Kubernetes, stated precisely.** A k8s node Lease renews on
*kubelet* liveness — a node whose every container is wedged still holds its lease
(`distributed-patterns.md` finding 1). **The Warden's node lease may be renewed only after
a completed observation sweep of every local agent within the last renewal interval.** A
Warden that can no longer observe cannot renew, and its agents become unschedulable
without any timeout guessing. This is the single cheapest place to spend the differentiator.

### Runner-up, and the condition to switch

**Runner-up: HTTP + SSE per node, fronted by Tailscale Serve** (automatic HTTPS for
`*.ts.net`, zero cert management, stdlib-only on every OS, no broker process at all).

Switch to it if **any** of these holds:

1. The fleet stabilises at **≤ 8 machines with ≤ 2 brokers**, where N² connection growth
   never bites and a broker process is pure overhead.
2. The Jepsen analysis of NATS 2.12.1 (jepsen.io/analyses/nats-2.12.1, Dec 2025 — *found but
   not read* by the transport pass) shows JetStream losing acknowledged writes under
   partition in a way the lease tier cannot tolerate. Then leases move to a single
   **designated primary** HTTP service with an fsync'd log, per dgx-fleet's
   "avoids n=2 split-brain by fiat".
3. `nats-server` fails to install natively on the owner's Windows desktop. Probe before
   committing (section 8).

**Second runner-up: MQTT/Mosquitto.** Lightest broker, and the only transport whose core
primitive (Last Will and Testament) was *designed* for "did this node vanish". Rejected
because (a) LWT fires identically for a crashed node and a partitioned-but-healthy one — the
reachability-vs-liveness category error this project exists to correct; (b) no CAS/KV, so
the lease tier needs a second system anyway; (c) the named hazard from the owner's own
transport study: a spoofed `CONNECT` with a duplicate `clientId` destroys another client's
persistent session and its queued QoS 1/2 messages. Keep LWT's *concept* as one more
evidence input, not as an answer.

**Explicitly not the bus:** Taildrop or any synced-directory scheme (no push-on-write daemon
mode found; a stale file is indistinguishable from a dead writer with no liveness gate
available at all) — usable only for cold audit handoff and binary bootstrap.

**Fleet-lethal default to disable on day one:** Tailscale key expiry. An expired key silently
drops connectivity and presents as `dead` for a node that is merely locked out — a
false-death class `functional-design.md` section 6.4 does not yet name. Note the interaction
with tagging: *"When you apply a tag to a device for the first time and authenticate it, the
tagged device's key expiry is disabled by default"* — so tagged fleet nodes hold
never-expiring credentials, which is a permanent-credential accumulation problem in the
opposite direction. Both facts must be in the provisioning runbook.

---

## 4. The role model

**A role is a named, version-pinned bundle of seven independently checkable declarations.
It contains no state.** Roles are declared; state is proved. No field of a role may be
written by the agent at runtime, and no state field may be written by anything but the
Warden.

```yaml
# roles/reviewer/role.yml   (directory shape follows dgx-fleet: defaults/ + meta/argument_specs.yml
#                            + a generated README; a role with no argspec fails lint)
role: reviewer
version: 3                          # pinned; two versions may run side by side

capabilities:                       # 1. DECLARED, then PROBED at admission. Never prose.
  - {cap: "tool:git",        probe: "git --version",     expect: "^git version 2\\."}
  - {cap: "tool:pytest",     probe: "pytest --version"}
  - {cap: "backend:claude-code", probe: "sidecar:version", expect: "^2\\.1\\."}

permissions:                        # 2. SCOPE.
  allow: ["Read", "Edit", "Bash(pytest:*)"]
  deny:  ["Bash(git push:*)", "Bash(rm:*)"]      # deliberate divergence from K8s RBAC
  risk_class: baseline                            # baseline | dangerous
  unattended: true                                # false => needs a live human subscriber
  max_taint: agent-derived                        # human-signed | agent-derived | untrusted-content
  max_hop: 4

persona:                            # 3. The only free-text facet. Never load-bearing for routing.
  prompt_ref: prompts/reviewer.md

subscribes:                         # 4. WORK SUBSCRIPTION — the role's selector over work
  - {queue: review, match: {label.lang: python}, concurrency: 1}

placement:                          # 5. PLACEMENT — K8s nodeAffinity grammar
  required:                         #    re-evaluated DURING execution, not only at bind
    - {key: os,             operator: In,     values: [linux, darwin]}
    - {key: repo.checkout,  operator: Exists}
    - {key: isolation_class, operator: In,    values: [os-sandbox, container]}
  preferred:
    - {weight: 50, key: machine.class, operator: In, values: [workstation]}
  tolerations:
    - {key: agent.fleet/human-attended, operator: Exists, effect: PreferNoSchedule}

supervision:                        # 6. FAILURE POLICY — OTP shape, budgets declared
  strategy: rest_for_one
  crash_intensity: 3                # process died on its own      (cultureagent 3/300s)
  restart_intensity: 1              # we chose to kill a wedge     (see conflict 3)
  period_s: 300
  escalate_to: role:integrator
  turn_deadline_s: 900              # FIPA reply-by applied to a dispatch
  hung_after_s: 300                 # observer-computed; MUST exceed compaction p99 (OPEN)
  token_budget_per_period: 400000   # restarts cost money; budget them like restarts

observation:                        # 7. OBSERVATION POSTURE — the facet nobody else has
  posture_required: attached+screen  # spawned | attached+screen | attached-noscreen
  min_confidence: fused-3ch          # fused-3ch | fused-2ch | self-report
                                     # posture_required implies can_answer_dialog
```

### Matching work to a role

```
dispatch(work, agent) is legal  iff
      role.subscribes.match      ⊇ work.labels
  AND role.placement.required    holds on agent.node     (now AND continuously)
  AND agent.verified_state == idle                        (Warden-computed, never claimed)
  AND agent.confidence          >= role.observation.min_confidence
  AND agent.posture             satisfies role.observation.posture_required
  AND lease.evidence_max_age_ms <= lease.ttl_ms
  AND kill0(agent.pid) is true                            (liveness is the PID, not the terminal)
  AND work.risk_class           <= role.permissions.risk_class
  AND work.taint                <= role.permissions.max_taint
  AND work.hop                  <  role.permissions.max_hop
  AND work.budget               <= remaining(node.budget) ∩ remaining(role.budget)
  AND (role.permissions.unattended OR a human subscriber is live)
  AND NOT node.drained AND NOT node.quarantined
```

Then `send --lease <id>` **refuses on an expired lease**, exit 4 — the same refusal already
shipped (`README.md:94,101`), now carrying a fleet-scale precondition.

Four binding rules:

1. **Capabilities are declared then probed; a capability that cannot be probed is not a
   capability — it belongs in `persona`.** Admission rejects the agent from the role on
   mismatch. This is dgx-fleet's argspec rule and its stated purpose transfers exactly:
   prevent an `if runtime == 'vllm'` ladder — here, an `if cli == 'claude'` ladder.
2. **`posture_required` is a hard predicate.** See Verdict; this is the permanent-latch bug.
3. **Required-during-execution, not ignored.** Violation revokes the lease and returns the
   work-item with a `revoked` reason. Deliberate divergence from K8s
   `IgnoredDuringExecution`, recorded as a decision.
4. **`deny` rules exist.** Deliberate divergence from K8s RBAC's *"permissions are purely
   additive (there are no 'deny' rules)"* — the agent CLI's own settings support deny, and
   `deny` is how you express "never `git push`" without enumerating the allow-universe.

**Two orthogonal state axes, kept orthogonal.** The scheduler's intent machine
(`RUNNING · WAITING_POKE · STOOD_DOWN · BLOCKED · DOWN · POKE_HUNG`, from
`agent-team-kit/README.md:16-23`) is not the observed-state machine (the seven states plus
`conflict`). `WAITING_POKE` encodes *"between tasks, absent is normal"* — the reason
`watchdog.sh:5-7` fires DOWN only when `state=RUNNING` **and** the beat is stale. **The
cross-product is the most valuable signal the fleet has**: `intent=RUNNING ∧
observed=idle for 5 min` is a lost dispatch; `intent=STOOD_DOWN ∧ observed=busy` is
culture#305 (two agents spiralling ~9 minutes *after* declaring stand-down, ~0.3-0.5M
tokens of pure spiral output, force-stopped by hand). Neither is visible on one axis.

---

## 5. Failure semantics

`VS` marks a row where the **verified-state primitive changes the answer** — i.e. prior art
must guess and we do not.

| # | Failure | Detection channel | Mesh response | What prior art does instead |
|---|---|---|---|---|
| 1 | **Agent wedged mid-turn** (heartbeat fresh, dispatch stuck) — `agent-mesh` class BB | **VS** sidecar `busy` unchanged + screen hash frozen + PID alive, past `hung_after_s`, observer-computed at read time | `presumed_hung`; agent becomes unschedulable; lease revoked; cooperative-checkpoint attempted before any restart | Every surveyed system: a timeout on silence. `agent-mesh`'s own mitigation is "heartbeat gated on loop liveness" — still self-report |
| 2 | **Agent SIGKILLed** | process channel only — the sole channel that survives death; overrides everything (`functional-design.md:111`) | `dead` in ~0.03-0.04 s (RACE-macos); work-item requeued **only after** a positive fence | cultureagent reaches `presumed_hung` after 90 s; k8s waits 5 min before the first eviction |
| 3 | **Terminal died, agent alive** | PID cached at launch; sidecar is deleted on clean exit so it cannot name the PID later | Not death. Measured window: terminal death → process death is **0.81-1.31 s** — the silent-misdetection window S6b polices | claude-flow counts `ps \| grep` and divides by a magic constant |
| 4 | **Permanent permission latch** on an `attached-noscreen` agent | **VS** sidecar `waitingFor` present + `screen_available:false` | Prevented at placement (`posture_required`); if it happens anyway, escalate to a human role immediately — the mesh declares it cannot self-clear | Nobody models observation posture; the work-item hangs forever |
| 5 | **Compaction** (looks exactly like a hang) | `PreCompact`/`PostCompact` hooks or the transcript `compact_boundary` record | Suppress the staleness watchdog **and** the reassignment timer for the compaction window | Screen-only observers false-alarm. Threshold still a guess — see section 8 |
| 6 | **Channel disagreement** | fusion rule 5 → `conflict`, `attrs.reason` names the mechanism | Agent is **unschedulable but not evicted** (k8s `Ready=Unknown` posture, minus the 5-minute blind wait, because we can re-probe immediately) | Every scraper picks a winner and reports it confidently |
| 7 | **Unknown `waitingFor` literal** | sidecar vocabulary is small and of unknown size (`discovery-session-sidecar.md:71-73`) | `conflict`, never a guess. Rate-limit the resulting quarantine (see security invariant 8) | agentirc drops a malformed presence payload **silently** — indistinguishable from no heartbeat |
| 8 | **Vendor UI copy drift** (dialog literals stop matching) | self-test: a session that provably showed a dialog with zero literal matches fails loudly (SPEC rule 6) | Fleet-wide alarm, not a per-node one: drift is correlated across every node on that CLI version | Silent misdetection — the observed failure mode across three surveyed projects |
| 9 | **CLI version outside the pin** | version compare at admission | Refuse to admit the agent to any role whose `capabilities` probe pinned that range; loud, not degraded | dgx-fleet's `nvidia_verify` is the precedent: hard-fail on drift, operator inspects, PR bumps the pin |
| 10 | **Warden hung** (who watches the watcher — class BQ) | node lease not renewed (renewal requires a completed sweep) **plus** a dead-man's switch: absence of a periodic signed all-clear is itself the alarm | Every agent on that node → `unknown`; **quarantine, do not reschedule**; page a human | No surveyed system detects a hung observer at all |
| 11 | **Warden lies / node compromised** | second-observer sampling + signature verification + evidence-vs-outcome audit | Quarantine the node, revoke its NKey (`key_version` bump), tombstone its agent slugs | Presence is self-reported everywhere; agentirc#56 lets **any** linked peer assert presence for a nick it does not host |
| 12 | **Host unreachable** (network partition) | Tailscale peer `Online` false + NATS disconnect + node lease expiry — three signals, none sufficient alone | `unknown`; stop dispatching; **do not re-dispatch its work until a positive fence succeeds**. Deliberate inversion of k8s's evict-after-5-min | k8s evicts and reschedules — correct for fungible pods, produces **two live agents in one worktree** here |
| 13 | **Tailscale key expiry** | `tailscale status --json` handshake state + a key-expiry watchdog | A distinct `locked_out` reason on `unknown` — never `dead`. Expiry disabled per fleet node at provisioning | Unmodelled; presents as a false death |
| 14 | **Ack-gaming** (node acks without processing) — class AF | **VS** partially: an ack claiming completion while the agent was never provably `busy` is refutable from the evidence stream | Quarantine + human audit. Honest scope: *"PTA is receipt-proof, not correctness-proof"* — no finite protocol closes a lying acker; the backstop is a human comparing content | Every queue: an ack proves receipt, and nothing else |
| 15 | **Double dispatch into one worktree** | KV CAS on the worktree lease; the lease renews only on **fresh evidence about the agent holding it** | Second dispatch refused at bind. If it somehow lands, `conflict` + human | k8s renews a node lease on kubelet liveness — a fully wedged node still holds it |
| 16 | **Agent dies before writing `resume-from`** | `dead` from the process channel while a work-item lease is live | Recover from the last on-disk checkpoint plus the transcript; the lease timeout returns the item; **never blind-retry** | The mailbox eject protocol assumes a graceful departure that writes `resume-from` |
| 17 | **Livelock / handoff ping-pong** | **VS** per work-item: aggregate *provably-busy seconds* vs count of role transitions | Cut a cycle churning edges where nobody was ever provably `busy`; do **not** cut a chain that is provably busy or compacting | Indistinguishable from productive delegation — both are just messages. AutoGen Swarm stops only when a model emits `TERMINATE` |
| 18 | **Budget exhausted** | meter channel (statusline stdin: `cost.total_cost_usd`, `rate_limits.five_hour.used_percentage`) at the dispatch boundary | Terminal `budget_exhausted`, distinct from `dead`; enforced as a **refusal to `send` at `idle`** — the only safe stopping point | Kill mid-turn: you pay for the turn anyway and lose the work |
| 19 | **Rate limit (429)** | response headers `anthropic-ratelimit-*`; `api_error` events fire **only after retries are exhausted** (`attempt` = 11 by default) | Account-scoped `quota-exhausted:NoSchedule` taint; back off the whole account, not the node | A rate-limited fleet looks like *slowness* for a long time before any error event appears |
| 20 | **Human saturation** | **VS** count of agents in `waiting:permission` vs live approvers | Throttle dispatch of prompt-generating task classes. Backpressure on a *human queue* — a resource no surveyed scheduler models | cultureagent deleted the state at source rather than scheduling on it |
| 21 | **Non-Claude backend, no sidecar** | channel enumeration at admission → `confidence: self-report` | Admissible, but only to roles whose `min_confidence` allows it; **never** to a role that holds a worktree lease | Unmodelled; the mesh would silently degrade to self-report and keep claiming verification |
| 22 | **Bus / JetStream partition** | NATS connection error is explicit, not silent | Transport failure is a distinguishable `conflict`-class signal, **never** agent death. Wardens continue observing locally and buffer edges | A stale file, an SSE drop and an MQTT LWT all look like death |
| 23 | **Broker crash** | reply timeout on `Dispatch` | Stateless: another broker takes the domain's primary key via KV CAS. In-flight leases expire harmlessly | — |
| 24 | **Restart storm** | OTP `crash_intensity`/`restart_intensity` per level, exceeded | Supervisor terminates its children and itself, escalating **upward** — plus a token budget on the same subtree, because restarts cost money as well as attempts | Escalation upward is missing from every agent orchestrator surveyed |

Two shapes to copy verbatim from k8s for *how* the mesh acts on any of the above:
**rate-limit every fleet-wide corrective action** (`--node-eviction-rate` 0.1/s), and
**stop entirely when the observation itself looks suspect** — when every zone is unhealthy
k8s performs no evictions at all, on the assumption the fault is its own connectivity.

---

## 6. Security and budget invariants

Non-negotiable. Each is one line, each traces to a cited finding.

**Security**

1. **The dispatch edge is an RCE API.** Filesystem write access to a repo equals arbitrary
   command execution inside every agent attached to it — Q1 proved hooks can be retrofitted
   onto a *running* session by writing project `.claude/settings.json`
   (`functional-design.md:23-26`), and the vendor confirms settings hot-reload including
   `hooks`. **"Who may write settings on a node" is a higher privilege than "who may enqueue
   a task"** and must be a separate, human-authorised plane.
2. **Capabilities attenuate only, never widen.** Biscuit/Macaroon shape: *"The token can only
   be restricted, it will never gain more rights"*, with offline attenuation requiring no
   scheduler round-trip. An agent enqueueing work derives the child envelope from its own.
3. **The scheduler never re-signs an agent-originated task under its own identity.** That is
   the confused deputy by construction (MCP security spec). Forward attenuated envelopes;
   never mint fresh ones on an agent's behalf.
4. **Taint is monotone and travels with the envelope.** Once a session ingests content whose
   provenance is not human-signed, every envelope it emits is tainted; tainted envelopes get
   strictly smaller capabilities and a lower hop ceiling. Morris-II (arXiv:2403.02817)
   demonstrates a self-replicating prompt cascading through GenAI apps *measured against hop
   count* — this is published prior art, not a hypothetical.
5. **Session IDs are names, never credentials.** MCP spec: *"MCP servers MUST NOT use
   sessions for authentication"*; and this repo's sidecar is world-readable under `~/.claude`.
   Same for tmux socket paths.
6. **Fail closed on every gate.** K8s admission webhooks make `failurePolicy: Fail` the
   default with a bounded `timeoutSeconds` (2-5 s) — a policy-engine timeout must **reject**.
   Corollary from the same doc: any envelope-rewriting step must be idempotent, because a
   requeued task passes through it twice.
7. **No untrusted-content role may be scheduled onto a node with no isolation boundary.**
   Claude Code's Bash sandbox is Seatbelt (macOS) / bubblewrap+socat (Linux, WSL2) and
   **native Windows is not supported** — which is exactly this project's Windows leg
   (`functional-design.md:139-150`). `isolation_class` is a placement predicate, not a note.
8. **A node in `conflict` is quarantined, not merely unknown — with a quarantine budget.**
   Otherwise an adversary who can induce conflicts (forcing UI copy drift) can drain the
   fleet. Rate-limit quarantine exactly as k8s rate-limits eviction.
9. **Never bypass permissions fleet-wide, never patch the binary, never write user-global
   config.** Already this repo's rules (SPEC rule 5); at fleet scale note the sharp edge:
   `--dangerously-skip-permissions` is blocked as root *and that block is skipped inside a
   recognised sandbox* — so the flag is most available exactly where it is least safe.
10. **Policy distribution parses tolerantly; node-local config parses strictly.** Managed
    settings strip an invalid entry with a warning so *"a single typo cannot disable the rest
    of your organization's policy"*; user/project settings are rejected whole. Mirror both.
11. **Human-gated join, CAS per directory entry, tombstoned slugs, `key_version` with
    valid-from/until.** An unknown party cannot self-join; a rewritten directory row must not
    be able to swap a victim's pubkey (this broke `proposal-minimal` in the owner's own
    adversarial round); signature verification uses the key valid at message `ts`.

**Budget**

12. **The fleet budget is dual-currency and a single USD ledger over a mixed fleet is a
    fiction.** API-key nodes spend USD (org caps: Start $500 / Build $1,000 / Scale
    $200,000); subscription nodes spend plan-window percentage — *"Usage inside the seat
    allowance isn't metered in dollars"*. Carry both.
13. **Enforce at the dispatch boundary; reconcile from telemetry.** OTel batches at 60 s
    (metrics) / 5 s (logs), goes **completely silent for the whole block window** (Q4: 88 s,
    zero batches), and the vendor states *"Cost metrics are approximations"*. Ledger, don't
    gate.
14. **`idle` is the only safe stopping point.** Enforce budgets as a refusal to `send`, and
    add a terminal `budget_exhausted` distinct from `dead` so recovery does not look like a
    crash.
15. **Ledger on `cost_usd_micros` (integer), attribute on `query_source` + `agent.name` +
    `skill.name`.** No float drift; per-role budgets computable from the same rows the SIEM
    gets.
16. **Model the cost as superlinear in fan-out.** The vendor documents ~**7x** token usage
    for agent teams because each teammate maintains its own context window. Fan-out, not
    depth, is the cost driver — so a per-root fan-out budget is required alongside
    `hop_count`.
17. **Bounded workflows, no unbounded agent loops, no bypass on spend-capable sessions.**
    Already a locked decision in `STATE.md`; it is the fleet cost policy in embryo and the
    build order makes it enforceable.
18. **Every durable store has a stated GC policy, and no dedup-ledger id is pruned below the
    replay horizon.** Classes AY/AZ. The evidence stream is a *new* store nobody has sized.

---

## 7. Build order

14 features. **Tier 1** must exist before anything else is meaningful; **Tier 2** items are
parallelisable once Tier 1 lands; **Tier 3** is a later luxury. Each carries one acceptance
test.

### Tier 1 — the spine (strictly ordered)

| # | Feature | Acceptance test |
|---|---|---|
| **F1** | **`attach` verb, evidence-carrying, all three OSes** (currently unbuilt — `HANDOFF.md` "Open work") | On a machine with three live sessions the driver did not spawn, `attach` + `state` returns the correct state for all three with ≥2 evidence channels each, and reports `screen_available:false` with a named list of impossible operations for the one with no reachable terminal. |
| **F2** | **Warden v0** — one node agent per machine; owns every local session; local ownership lock keyed by `sessionId` | Two Wardens started on one machine: the second refuses to adopt sessions the first holds and says so; killing the first releases the lock within one poll. |
| **F3** | **Durable identities** — self-minted `node_id` on disk, `agent_id` slug, tombstoning, sidecar `name` probe | Reinstalling Tailscale on a node (new node key, new IP) leaves `node_id` unchanged and the roster row intact; retiring an agent makes its slug permanently unallocatable. |
| **F4** | **Bus + StateEdge** — NATS subject per node, JetStream evidence stream, `seq`/`prev`, signed | A broker replaying the JetStream stream from offset 0 reconstructs each agent's exact state history; a deliberately dropped edge is detected via `prev` mismatch rather than silently absorbed. |
| **F5** | **Ledger** — JetStream KV, CAS per entry, human-gated join with read-back confirm | Two concurrent writers to one agent record: exactly one succeeds, the loser retries against the new revision; an unapproved node's join is rejected and logged. |
| **F6** | **Dispatch lease + `send --lease`** — the keystone | `send` with an expired lease exits 4 and the prompt is not delivered; `send` against an agent that flipped to `waiting:permission` after the lease was minted is refused, with the evidence that refused it. |

### Tier 2 — parallelisable after F6

| # | Feature | Acceptance test |
|---|---|---|
| **F7** | **Role schema + argspec validation + capability probes at admission** | A role declaring `tool:pytest` on a node without pytest is rejected at admission with the failing probe named; a role directory with no `argument_specs.yml` fails lint. |
| **F8** | **Broker** — predicates → priorities → optimistic bind → lease request → revoke; taints/tolerations incl. evidence-derived taints | Work labelled `lang:python` reaches only agents whose role subscribes to it; cordoning a node (`human-attended:NoSchedule`) stops new dispatch within one scheduling cycle and does not disturb running work. |
| **F9** | **Work-item + envelope** — ULID, process-**then**-ack, `(from,id)` dedup, quarantine-on-bad-sig, at-most-once default | A duplicate envelope is re-acked without re-execution; an envelope with a bad signature is quarantined and nacked, never silently skipped; killing the Warden mid-turn leaves the item un-acked and it is **not** auto-redelivered. |
| **F10** | **Budget gate + meter channel** — statusline stdin as a fourth channel; `budget_exhausted` state | An agent at 100% of its role budget refuses the next `send` at `idle` and reports `budget_exhausted`, not `dead`; the ledger's `cost_usd_micros` total reconciles with the Admin API within its ~5-minute latency. |
| **F11** | **Watchdogs** — adaptive `presumed_hung` (φ-accrual), compaction suppression, Warden node lease gated on a completed sweep, dead-man's switch | A 5-minute compaction produces **no** `presumed_hung` and no reassignment; a `SIGSTOP`ed Warden fails to renew its node lease and its agents go `unknown` (not `dead`) within one lease duration. |
| **F12** | **Quarantine and fencing** — unreachable → `unknown`, no re-dispatch without a positive fence; rate-limited actuation | Partitioning a host from the bus while its agent keeps working produces zero re-dispatch of that agent's work-item and zero second agent in the worktree; healing the partition resumes without duplicate work. |

### Tier 3 — later luxury

| # | Feature | Acceptance test |
|---|---|---|
| **F13** | **Capability attenuation + taint + hop ceiling** (Biscuit-style envelopes) | An agent attempts to enqueue work with a capability it does not hold: the derived envelope fails verification at the receiving Warden with no scheduler round-trip involved. |
| **F14** | **Supervision tree + cooperative-checkpoint preemption + agentirc PRESENCE projection** | Exceeding `restart_intensity` terminates the subtree and escalates upward rather than looping; a preempted agent is told to checkpoint and is reclaimed only after **verified** `idle`; `culture residents` shows our rows with the declared lossy mapping and a written coverage-loss statement. |

**Sequencing rationale.** F1-F6 are strictly ordered because each is the other's
precondition: no Warden without `attach`; no signed edge without an identity; no lease
without a Ledger to CAS against. F6 is the point at which the system does something no prior
art can. F7-F12 are independent of one another and can run in parallel across agents or
sessions. F13-F14 are deferred deliberately: attenuation matters once *agents* enqueue work
(they do not in F1-F12, where a human or a broker does), and the projection layer buys
interop, not correctness.

**One process rule borrowed wholesale from dgx-fleet:** any fleet-wide change to agent
config, prompts, or CLI version ships as a `serial: 1` canary — one machine at a time, a
pre-apply health gate that refuses to proceed, a post-apply smoke test, an optional human
pause, and a flock so push and pull cannot race. *"If dgx-01 fails, dgx-02 is never
touched."*

---

## 8. Open questions needing an empirical probe

Ordered by how much design each can kill. Every one names its probe.

1. **Can the sidecar's `name` be set at launch?** It carries `"name":"protoc-c5"` with
   `"nameSource":"derived"` (`discovery-session-sidecar.md:16-17`). **Probe:** launch with a
   `--name`-style flag / env var and re-read the sidecar. **If yes**, `list` becomes a
   zero-cost fleet-wide role directory for sessions we did not spawn and F3/F7 get much
   cheaper. **If no**, role↔session binding for adopted sessions needs its own registry and
   a stable-nick policy. Two researchers independently asked this (`roles-and-topology.md`
   open q1, `agentculture.md` open q5) — it is the cheapest high-value probe on the list.
2. **Compaction duration distribution.** One probe sets **three** numbers: `hung_after_s`,
   the do-not-reassign threshold, and the unmeasured *spend* window (`/compact` is itself a
   large request). Still open at `functional-design.md:257`. Reassigning during compaction
   duplicates work and pays twice.
3. **Per-channel latency under N concurrent sessions on one host.** RACE-macos is n=1 with
   one session (send→permission 2.1 s, launch→idle 13.3 s for the fused driver). The
   dispatch lease TTL must exceed worst-case observation latency; nobody has turned the
   numbers into a scheduler budget, and concurrent sessions are listed as unverified.
4. **Is a 2-channel lease (sidecar + process, no screen) safe to grant?** Determines whether
   `attached-noscreen` members can hold any lease at all, and therefore whether
   `min_confidence` has two tiers or three.
5. **Does `nats-server` install and run as a native Windows service on the owner's
   desktop?** A direct install attempt on `windesk`. This is the single fact that decides
   between the recommendation and the runner-up in section 3.
6. **Read the Jepsen analysis of NATS 2.12.1 in full** before JetStream becomes the
   durability layer for leases. Found but not read by the transport pass; its
   partition-tolerance findings are the switch condition in section 3.
7. **Does any non-Claude backend have a sidecar equivalent?** Codex/Gemini/Kiro. Determines
   whether `confidence` has real tiers or whether "Claude Code and friends" means the mesh
   silently degrades to self-report on some hosts while still calling itself verified.
8. **Does `SIGSTOP`-based suspend survive an in-flight API request and any server-side
   session timeout?** Determines whether SUSPEND-class preemption exists at all, or whether
   cooperative checkpoint is the only preemption mode.
9. **Can the statusline meter channel be used without stealing the user's statusline?**
   `statusLine` is one command per session and configuring it in user settings is close to a
   banned global-config write. Probe: project-scoped `statusLine`, or a wrapper that chains
   to the user's existing script.
10. **Enumerate the `waitingFor` vocabulary.** Only `"permission prompt"` has ever been
    observed. Probe `AskUserQuestion`, MCP elicitation, and plan-mode dialogs. Every
    unrecognised literal is a `conflict` today, and `conflict` is quarantine — so the
    vocabulary's size is directly a fleet-availability number.
11. **Does `ConfigChange` fire — and can it be made the audit tap — on a session we did not
    spawn?** Q1 proved the retrofit works; the *audit* direction (detecting that someone
    else wrote settings mid-session) is unexercised and is invariant 1's enforcement point.
12. **What is the per-agent state-edge rate, and at what fleet size does edge-push saturate
    the bus?** Nomad published a heartbeat-cost table; we have no equivalent number and
    cannot size the mesh without it.

---

## Sources

Researcher files in this directory, read in full:
`own-prior-art.md` · `agentculture.md` · `distributed-patterns.md` ·
`transport-and-membership.md` · `roles-and-topology.md` · `security-and-cost.md`
(each carries its own primary-source citations, retained above by name).

Repo, first-hand: `README.md:47,49,53,94,101,112-114` ·
`docs/design/functional-design.md:23-26,62,74-76,94,95,99-116,139-150,257` ·
`docs/discovery-session-sidecar.md:16-17,53-56,57-63,64-67,71-73` ·
`prototypes/common/SPEC.md` (rules 1-9, scenario suite) ·
`docs/results/RACE-macos.md` (latency table; terminal-death→process-death 0.81-1.31 s) ·
`docs/.research/prior-art/SYNTHESIS.md` (1.9, 2, 3 — conclusions C1-C11) ·
`STATE.md` (locked decisions) · `HANDOFF.md` (open work).
