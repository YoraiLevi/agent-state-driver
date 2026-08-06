# Fleet architecture — decisions

Status: settled design v1 (2026-08-06). The reasoning, citations and rejected alternatives
live in `docs/.research/fleet/SYNTHESIS.md` (688 lines) and the six researcher files beside
it. This document is the **decisions** and the **build order**; read the synthesis when you
want to know why, or to argue with it.

Vision and use cases: [fleet-vision.md](fleet-vision.md).

---

## 1. The one structural advantage

Every mature scheduler surveyed detects a dead worker by **timeout on a self-report**.
Temporal's own documentation says it outright: *"The Temporal Server doesn't detect failures
when a Worker loses communication… relies on the Start-To-Close Timeout."* Kubernetes'
kubelet self-registers and self-reports. cultureagent ships a `STATE_WORKING` no backend
emits. Even the owner's own `agent-mesh` research names failure class BB — *"heartbeat fresh,
dispatch wedged"* — and proposes gating the heartbeat on loop liveness, which is still the
agent talking about itself.

**This project reads state from outside the reporter.** That is the whole advantage, and
every decision below traces to it. The fleet is not "a better presence system" — it is the
system that closes the heartbeat-fresh-but-wedged class.

### The five liveness tiers

Collapsing any two of these is the failure mode of every surveyed system.

```
registry entry     "it is in the config"          — a file said so
   ↑
reachability       "the network answers"          — Tailscale/ping. NOT liveness
   ↑
presence claim     "it says it is idle"           — cultureagent, agentirc stop here
   ↑
verified state     "I observed it idle, evidence" — THIS REPO owns this tier
   ↑
lease              verified state + freshness bound + signature   — the fleet adds this
```

---

## 2. The keystone: the dispatch lease

Three researchers converged on this independently. It is the only genuinely novel mechanism
in the design; everything else is ordinary distributed systems.

**The problem it solves.** Verified state is a fact about the *past*. Between "the broker
saw agent A idle" and "the prompt arrives at agent A", A may have gone busy, hit a permission
dialog, or died. Dispatching on a stale observation is how every fleet loses work.

**The mechanism.** The Warden — not the broker — mints a short-TTL signed lease at bind
time, and `send` refuses without a valid one:

```json
{"kind":"lease","lease_id":"01JZ…","agent":"agt_01JZ…","work_item":"wi_01JZ…",
 "granted_state":"idle","evidence":[…],"evidence_max_age_ms":740,
 "pid_liveness":"kill0:ok@2026-08-06T09:14:03.001Z",
 "ttl_ms":15000,"sig":"ed25519:…"}
```

This is the fleet-scale generalisation of a rule this repo already ships: `send` refuses
unless the agent is idle, exit 4. The lease makes that refusal work *across a network*, with
a bounded staleness (`evidence_max_age_ms`) and an attestation of who observed it.

**Two invariants, unanimous across researchers:**
1. **Never gossip a lease.** Leases are requested and granted point-to-point, recorded in a
   linearizable store. Gossip is eventually consistent; two agents in one worktree spending
   money is not an eventual-consistency-tolerant outcome.
2. **Never resolve a channel disagreement by picking a winner** — the SPEC rule that already
   governs a single driver, promoted to the fleet.

---

## 3. Layers

```
L6 PROJECTION   agentirc presence export · console · OTel/SIEM       egress only
L5 WORK         work-items · envelopes (ULID, capability, budget)    durable
L4 BROKER       predicates → priorities → bind → lease → revoke      stateless
L3 LEDGER       roster · role bindings · leases (CAS per entry)      linearizable
L2 BUS          NATS core + JetStream (evidence stream, KV)          1–5 servers
─────────────────────────── machine boundary ───────────────────────────
L1 WARDEN       ONE per machine. Sole author of state for its agents. every host
                  ├─ state driver (stdlib-only, unsigned local JSON)
                  ├─ lease mint + signature
                  └─ local ownership lock, keyed by sessionId
L0 FABRIC       Tailscale: addressing + tag ACLs. NOT identity,      every host
                NOT liveness
```

### Load-bearing decisions

**One writer of state per machine.** The Warden is the sole author of every state row for
its agents, and no peer may overwrite it. Borrowed from agentirc's *"a peer may never
overwrite a locally-hosted nick"*, promoted to a hard invariant.

**The driver stays stdlib-only and unsigned.** Signing happens at the Warden, which already
holds a transport identity. This preserves the property that makes the driver droppable onto
a strange machine, and puts the attestation exactly at the machine boundary.

**Edges, not heartbeats, cross the network.** Verified state is read at ~1s *next to the
process*; only transitions are published. A fleet-scaled heartbeat is structurally too slow
to be an agent-liveness signal — Nomad needs 200–400s client TTL at 10 000 clients.

**`seq` and `prev` on every edge.** `seq` gives per-agent ordering the transport cannot;
`prev` makes a *missed* edge detectable rather than silently absorbed.

**Tailscale is reachability, not identity and not liveness.** Node identity is a self-minted
`node_id` on disk that survives a Tailscale reinstall, re-IP, and new node key.

---

## 4. Topology: peer mesh with capability routing

Chosen over a supervisor tree (too rigid for R4), a pure market (livelock risk, unbounded
cost), and the owner's star-with-one-manager (single point of failure at fleet scale).
Supervision is retained *within* a node; the mesh between nodes is peer.

**Work reaches an agent by capability match, not by address.** Work declares requirements;
roles declare capabilities; the broker matches. Adding a machine or a role is configuration.

---

## 5. Roles

Directory-shaped, following the owner's existing `dgx-fleet` vocabulary rather than
inventing a third one: `roles/<name>/` with `defaults/`, `meta/argument_specs.yml`, and a
generated README. **A role with no argspec fails lint.** Capabilities are *probed at
admission*, not declared on trust — a role claiming `tool:pytest` on a node without pytest
is rejected with the failing probe named.

`drained: true`, `baseline` vs `dangerous`, and `serial: 1` canary rollout are adopted
wholesale from dgx-fleet.

**Session naming is free** (probed 2026-08-06): `claude --name fleet-reviewer-01` lands in
the vendor sidecar as `name`, and `nameSource` is `null` for operator-set names versus
`"derived"` for auto-generated ones. So a fleet can enumerate *and distinguish* its own
labelled sessions across a machine with no registry at all — including sessions it did not
spawn.

---

## 6. Failure semantics

The table the advantage buys. Every row's detection channel is observed, not reported.

| Failure | Detected by | Mesh response |
|---|---|---|
| Agent SIGKILLed | process channel (pid liveness) | lease void; work re-placed per policy |
| Agent wedged, terminal alive | verified state stale + `presumed_hung` watchdog | escalate; **never** silently reassign |
| Agent blocked on a human | `waiting:permission` — a **schedulable resource** | route to human queue; agent excluded from dispatch; backpressure signal |
| Compaction (long silent gap) | compaction suppression in the watchdog | **no** `presumed_hung`, no reassignment |
| Warden SIGSTOPed | node lease not renewed (renewal gated on a completed sweep) | its agents go **`unknown`**, not `dead` |
| Node partitioned | bus unreachable | agents `unknown`; **no re-dispatch without a positive fence** |
| Channels disagree | fusion layer | `conflict` propagates to the fleet; never averaged |
| Budget exhausted | meter channel | `budget_exhausted` state; refuse next send at idle — distinct from `dead` |

**`unknown` is a first-class state.** Unreachable must never be reported as healthy *or* as
dead, and this is where most fleets lie.

---

## 7. Non-negotiable invariants

**Security.** A mesh that dispatches work to other machines is remote code execution as a
feature. Therefore: signed envelopes; a `hop` ceiling and a `taint` marking agent-derived
work; capability attenuation before agents may enqueue for other agents; human-gated node
join confirmed by read-back; bad signature ⇒ quarantine and nack, never silent skip.
**Prompt injection is a distributed-systems threat here** — an agent that reads a malicious
file must not be able to enqueue fleet work with authority it never held.

The existing refusals scale up unchanged: no `--dangerously-skip-permissions`, no global
config writes, no binary patching.

**Cost.** Budgets are per-node, per-role, per-task, with a deadline. Spend must be
attributable and visible *before* it is incurred. Budget exhaustion mid-task stops cleanly
rather than corrupting state.

**Human control.** The human plane is a role with an inbox, not an escape hatch. Escalations
carry the full `evidence[]` array **unmodified** — never a summarised boolean, because the
per-answer evidence property must survive aggregation upward.

---

## 8. Build order

Fourteen features. Tier 1 is strictly ordered (each is the next one's precondition); Tier 2
parallelises; Tier 3 is deliberate deferral. Acceptance tests are in the GitHub issues.

| Tier | Features | Note |
|---|---|---|
| **1 — spine** | F1 `attach` (done) · F2 Warden · F3 identities · F4 Bus+StateEdge · F5 Ledger · **F6 dispatch lease** | F6 is the point at which the system does something no prior art can |
| **2 — parallel** | F7 roles · F8 broker · F9 work envelope · F10 budget · F11 watchdogs · F12 quarantine/fencing | independent of each other; ideal for worktrees |
| **3 — later** | F13 capability attenuation · F14 supervision tree + agentirc projection | attenuation matters once *agents* enqueue work; projection buys interop, not correctness |

**Process rule, borrowed from dgx-fleet:** any fleet-wide change to agent config, prompts or
CLI version ships as a `serial: 1` canary — one machine at a time, pre-apply health gate,
post-apply smoke test, and a lock so push and pull cannot race. *"If dgx-01 fails, dgx-02 is
never touched."*

---

## 9. Where the researchers disagreed

Recorded rather than averaged, with the resolution taken: transport (NATS vs MQTT); whether
to speak agentirc's wire protocol or export to it; OTP restart budget (1–2 vs 3); Temporal
as engine vs Temporal as shape; where the state cache lives; and whether a detect-only
member belongs in the mesh at all. Full arguments in `SYNTHESIS.md` section "Where the
researchers conflict".

Two points of **unanimous** agreement are recorded as evidence in their own right: never
gossip a lease, and never resolve a channel disagreement by picking a winner.
