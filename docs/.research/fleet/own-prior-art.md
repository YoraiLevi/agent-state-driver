# The owner's own prior art — what the orchestration mesh must honour or supersede

**Scope.** Five of the owner's repos, read this session: `~/source/agent-mesh` (design + research only,
no code), `~/source/agent-to-agent-communication-file-mailbox` (a shipped protocol), `~/source/living-agents`
(a shipped multi-agent system with a PTY supervisor), `~/source/dgx-fleet` (a real multi-machine Ansible
fleet), plus skims of `~/source/swarm-test`, `~/source/meta-harness-pi-like`, `~/source/agent-native`.

**Evidence legend.** **OBSERVED** = I read it in a file this session (path + line where useful).
**INFERRED** = my reasoning on top of what I read, not stated by the source.

---

## Verdict

- **The owner has already written the mesh's message layer twice, and the second time an adversarial
  round broke the first.** `agent-to-agent-communication-file-mailbox/PROTOCOL.md` is the shipped
  minimal version; `agent-mesh/research/redesign-issue.md` is the hardened one, with a stated envelope,
  a process-THEN-ack state machine, ULID idempotency keys, and a signed directory. **Do not design a
  third message layer.** Adopt the agent-mesh envelope + ack semantics and make the file mailbox one
  transport binding of it. (OBSERVED: `redesign-issue.md` "1.1 Message envelope", `proposal-minimal.md`
  lines ~55-90.)
- **The differentiator is already named as an unsolved residual in the owner's own work.** agent-mesh
  class **BB — "Zombie / half-dead agent (heartbeat fresh, dispatch wedged)"** and class **AF —
  "ACK-gaming (ack-without-processing)"** are exactly the holes verified state fills
  (`agent-mesh/research/anticipated-failures.md`, Family LC and Family BZ). Its stated mitigation is
  "heartbeat gated on loop liveness" — i.e. *still self-reported*. **The state driver's evidence-fused
  state is the first mechanism the owner has that can externally refute a lying heartbeat.** Frame the
  fleet design as closing BB/AF, and cite the owner's own taxonomy, not just cultureagent.
- **Liveness must never be judged by the existence of a file, a pane, or a registry row — only by a
  live announcement, and now, by verified state.** This is the mailbox protocol's KEYSTONE RULE, learned
  the hard way (`PROTOCOL.md:70-94`: an ejected manager leaves `to-manager.md` behind; a worker's own
  announcement creates it). Generalise it: **registry entry ≠ presence; presence claim ≠ readiness;
  only fused evidence proves readiness.** Three tiers, named separately, never collapsed.
- **"Between tasks, absent is normal" must be a first-class state, or the watchdog will false-alarm the
  whole fleet.** `agent-team-kit/watchdog.sh:5-7` says it outright: beat staleness alone is *wrong* —
  DOWN fires only when `state=RUNNING` **and** the beat is stale. The kit's six-state machine
  (`RUNNING · WAITING_POKE · STOOD_DOWN · BLOCKED · DOWN · POKE_HUNG`,
  `agent-team-kit/README.md:16-23`) is orthogonal to the driver's seven agent states: one is
  *scheduler intent*, the other is *observed reality*. **Keep both axes; a conflict between them is
  the most valuable signal the fleet has.**
- **dgx-fleet already supplies the whole inventory/role vocabulary — do not invent one.** Hosts in
  `inventories/<env>/{group_vars,host_vars}/`, a group per machine class (`dgx_spark`), a per-host
  `workload_tier`, a `drained: true` host flag that the play *refuses to touch*
  (`playbooks/site.yml:41-46`), roles tagged `baseline` (safe for unattended pull) vs `dangerous`
  (push-only), explicit play ordering instead of hidden dependencies, `serial: 1` canary with a
  human gate between hosts (`playbooks/canary.yml`), a flock mutex so push and pull cannot race, and a
  single end-of-play reboot evaluator. **Map agent roles onto this, verbatim where possible.**
- **Every capability an agent has must be declared in a schema, and the fleet must refuse an
  undeclared one.** dgx-fleet's "parameterize everything" rule ships `meta/argument_specs.yml` per role
  and lints for its absence (`WHY.md`, "Parameterize everything"). The fleet equivalent is a per-role
  capability spec (which CLI, which OS, which tools, which permission posture) validated at join —
  otherwise role assignment becomes an `if agent == 'claude'` ladder, the exact failure `WHY.md`
  ("Inference platform role, not vLLM role") warns about.
- **The human is a participant with an inbox, not an escape hatch — and is the checker of last
  resort.** agent-mesh imports the fraud-proof "≥1 honest party suffices" model explicitly
  (`monitoring-prior-art.md` 2.2) and requires that a checker publish **evidence citations, not
  verdicts**, so a lying auditor is catchable. The state driver already emits evidence per answer —
  that property must survive aggregation: **the fleet-level view must carry per-channel evidence
  upward, never a summarised boolean.**
- **Cross-platform hostility is empirical here, not theoretical.** The owner's PTY traps are already
  written down: `\r` bundled with prompt text = paste, turn never submits; raw PTY bytes are not lines
  (spinner chrome fuses onto the reply); `statSync().size` is bytes while `String.slice` is chars, which
  silently hides appended bus lines; `printf '- …'` parses the dash as an option; a 4xx honest refusal
  trips a "zero console errors" oracle (`living-agents/PITFALLS.md`). **These are acceptance tests for
  the fleet's transport and injection layer, not folklore.**

---

## Findings

### 1. `agent-to-agent-communication-file-mailbox` — the shipped protocol, and its stated limits

**Shape (OBSERVED, `PROTOCOL.md:8-20`).** A folder (`~/.agent-mail/` global, `<cwd>/.agent-mail/` local,
or custom) containing `PROTOCOL.md`, `to-manager.md` (shared inbound funnel), `to-<worker>.md` (one
private inbox per worker), `log.md` (shared ledger), `state/<name>.md` (per-worker checkpoint that
survives restart). Topology is a **star**: one manager owns routing, N workers are spokes
(`README.md:26-38`).

**Line grammar (OBSERVED, `PROTOCOL.md:21-39`).** One physical line per message:
`- [HH:MM] (from-id) <message>`, with a small verb set — `alive` (heartbeat / "still working on X"),
`done` (names artifact + how to verify), `blocked` (names exactly what unblocks), `stopping` (names
resume-from), and `PING <nonce>` / `PONG <nonce>` as a liveness probe.

**Four semantics worth reusing verbatim:**

1. **KEYSTONE RULE — role from live state, not a flag** (`PROTOCOL.md:70-94`). A manager is alive only
   if `to-manager.md` holds a `(manager) … alive` line not cancelled by a later `stopping`/`ejected`.
   *"The mere existence of the `to-manager.md` file proves nothing."* Election: no live manager → you
   self-elect; tie-break by earliest timestamp, later manager demotes itself.
2. **Orphan discipline** (`PROTOCOL.md:88-91`). A worker with no live manager must **not** fabricate one
   by announcing into `to-manager.md`. It reports an initialization failure to its human, watches, and
   **self-heals** the moment a real manager appears. This is a refusal-to-guess rule of exactly the same
   family as the state driver's `conflict` state.
3. **Arm the watcher BEFORE announcing** (`PROTOCOL.md:51-56`). Observed in practice: a manager PINGed a
   worker that had announced but not yet armed its `tail -f`, so the PONG came back late. Order is
   **create inbox → arm watcher → announce**.
4. **Evidence, not claims** (`PROTOCOL.md:65-67, 101-105`). A `done` must name the artifact plus an
   oracle to check it; *"the manager ticks nothing on a say-so"*. Work products live in the repo; the
   mailbox carries coordination + evidence pointers only.

**Its own stated limits — the exact gap the new system exists to close** (`PROTOCOL.md:107-117`):
no delivery confirmation, no de-duplication, no ordering guarantees beyond append order, no isolation
(every agent can read/append every file), **single machine** (shared filesystem required). The README
closes with "when to graduate to something bigger" (`README.md:81-87`).

**Eject is a protocol step, not a kill** (`prompts/eject.md`): announce `stopping — resume-from: …`,
stop the watcher, optional checkpoint to `state/<id>.md`, delete your own inbox, confirm `ejected`.
Manager-side: stop routing, remove the leftover inbox, **reassign the unfinished work named in
`resume-from`**.

### 2. `agent-mesh` — the hardened redesign (design only; no code shipped)

This repo is design + research (`README.md`: "Design in progress"), migrated from an
`ai-voice-reminders-bridge` issue. It is the owner's most rigorous multi-agent thinking and the
new system should treat it as the spec to inherit.

**The bug that motivated it (OBSERVED, `redesign-issue.md` 1).** The poller marked a message COMPLETED
at *poller-read*, before the manager processed it — a transport ack mistaken for an application ack.
Cited to `pyicloud_bridge.poll_inbox:368-385` and `reminder_bridge.poll_inbox:268-283`, where the
CalDAV path completes the source *before the mailbox line is even written*, and the seen-file is written
first, so a crash loses the message permanently.

**Reliability core, cited to primary sources** (`redesign-issue.md` 2): end-to-end argument
(Saltzer/Reed/Clark 1984) → only the application endpoint can confirm work happened; Two Generals →
confirmation is probabilistic, so retry-until-timeout then escalate to a human; Helland idempotence →
at-least-once + idempotent consumer, dedup by stable id; transactional outbox + inbox idempotency key;
CouchDB-style durable cursor; backoff + jitter; DLQ scaled down to a per-message fail counter.

**Envelope (PROPOSED, `proposal-minimal.md` 1.1).** One item per message; machine header as a single
JSON line: `{v, id, from, to, ts, kind, reply_to, sig}` + `---` + body.
`id` = **ULID** (sortable, sender-minted, doubles as idempotency and ordering key).
`kind` ∈ `msg | ack | nack | hb`. `sig` = detached ed25519 over the canonical field set + body hash.

**State machine, retire only at `acked`** (`proposal-minimal.md` 1.2):
sender `queued → sent → acked`, with `sent --no ack within T_ack--> stalled → escalate`;
receiver `unseen → seen → processed → acked`, with duplicate → **re-send ack, do not reprocess**, and
sig/parse failure → **quarantine + nack, never silent-skip**.

**Isolation findings that broke two of the four proposals** (`critique-isolation.md` 0,
`redesign-issue.md` 3):
- There is exactly **one item-write permission letter** in Radicale (`w`), and it grants PUT +
  overwrite + **DELETE**. There is no append-only item permission. Therefore a shared inbox everyone
  can write to lets sender A delete sender C's pending message to B. Only **sender-partitioning**
  (`mesh/<B>-inbox/<A>/`, one collection per ordered pair) closes it at the server.
- `R` ≠ `r`: a rule granting `R` where it meant "let the auditor read messages" is silently a no-op.
  This broke `proposal-substrate`.
- The directory must be **per-entry write-locked** (`collection: mesh/directory/{user}`), or an attacker
  rewrites a victim's row to swap the pubkey. This broke `proposal-minimal`.
- **Named residual, honestly scoped:** all agents on one box run as one OS user, so a malicious
  co-located agent can `open()` another inbox off disk and bypass any server ACL. The ACL binds a
  *remote/leaked-credential* agent and an *honest-but-buggy* agent, **not** a malicious co-located one.

**Addressing + directory** (`redesign-issue.md` 3). Address = `agent_id`, a stable lowercase slug
(`manager`, `w3`, `human`, `auditor`) that doubles as auth username, path segment and directory key —
one identity, no mapping table to drift. Resolution is by **explicit directory URL, never display-name
discovery**. Directory entry: `{agent_id, inbox_url, pubkey, transport, last_seen, joined, sig}`,
CAS-guarded per entry, join is idempotent, **human-gated** (an unknown party cannot self-join) and
confirmed by read-back.

**The anticipated-failure taxonomy** (`anticipated-failures.md`) is the single most reusable artifact
here — 40+ classes lettered Y..BQ, each with severity and an invariant. The ones that bear directly on
a many-machine agent fleet:

| Class | Mode | Why it matters here |
|---|---|---|
| **Y / AB** | Asymmetric hub reachability; gray outage (PUT ok, REPORT times out) | Reachability is **per-agent, not global**; the canary must measure latency vs an SLO, not just reachability. A heterogeneous mac/Windows/Linux mesh fails asymmetrically. |
| **BB** | Zombie: heartbeat fresh, dispatcher wedged | The differentiator. Their fix is "gate the heartbeat on loop liveness" — still self-report. Verified state refutes it externally. |
| **AF / AE** | Ack-gaming; equivocation (different body to different peers) | "PTA is receipt-proof, not correctness-proof" — no finite protocol closes a lying acker. Backstop = human observe-all + auditor comparing content, not existence. |
| **AK / AL / AM** | No key revocation path; rotation gap; signature-downgrade oracle | Named as the **#1 genuine new gap**. Directory entry needs `key_version` + valid-from/until; verify against the key valid at message `ts`; `enforce_sig` is one-way per agent. |
| **AY / AZ** | Unbounded durable-store growth; GC vs replay-safety coupling | Every durable store needs a stated GC policy; never prune a dedup ledger id while its source could still replay. |
| **AP** | Key the dedup ledger on `(from, id)`, not `id` alone | Cheap, and prevents cross-namespace id forgery. |
| **AW** | Clock skew across mac/Windows/Proxmox | `ts` is **evidence, not authority**; timing decisions computed on one observer's clock. |
| **AV / AT** | Backpressure, slow consumer, broadcast storm | Sender backs off when unacked-depth exceeds a bound; keep the mesh unicast. |
| **BC** | Deregister race — retire an entry with mail in flight; slug reuse | Drain before retire; **tombstone the identity, never reuse a slug**. |
| **BH / BI / BJ** | Container crash-loop loses ledger; missing secret → default cred; one compromised image → all agents | Durable stores on named volumes; **fail closed** on a missing secret; image = TCB, pin by digest. |
| **BM / BP / BQ** | Alert fatigue; silent degradation no alert catches; failure of the checking layer itself | Severity-tiered alerting; a **continuous synthetic end-to-end canary**; a **dead-man's switch** — absence of a periodic signed all-clear is itself the alarm. |

**Monitoring prior art already surveyed** (`monitoring-prior-art.md`) — do not re-survey:
Chandra–Toueg (no detector distinguishes dead from slow — so escalate, never declare); **φ-accrual**
(adaptive timeout that learns jitter — directly applicable to hang thresholds instead of a fixed
number); **SWIM's indirect probe** (ask a third party to double-check a suspect before declaring it
dead — cheap and reusable even though full SWIM is overkill); Kubernetes liveness probes (with the
docs' own warning that a bad liveness probe causes cascading failures — the source of "heartbeat must
reflect real work"); Prometheus **Watchdog dead-man's-switch**; **blackbox_exporter** synthetic probing;
Lightning **watchtowers** (a checker need not be trusted if its output is independently verifiable —
hence *publish evidence, not verdicts*); Arbitrum BoLD's "one honest party suffices" (the formal
justification for human observe-all). Explicitly named overkill: BFT/slashing, interactive dispute games.

**Failure archaeology** (`failure-archaeology.md`) adds 32 real incidents and nine classes A–I. The ones
that transfer regardless of transport: **Class B** — resolve every channel by a stable id, never by title
or item-count, and refuse ambiguity loudly (they once inferred which list was live from item count and
were wrong); **Class C** — a poll is fault-isolated per item, one bad member never aborts the batch;
**Class E** — at most one authenticating poller per credentialed account (three pollers on one Apple ID
caused a 2FA/503 auth-storm); **Class I** — all shared mutable state updated by compare-and-set (an ETag
If-Match CAS already prevents concurrent-onboard clobber of the routing table). Also: distinct mailbox
directory per channel/project after two channels collided into one `to-manager.md` (row 22).

### 3. `living-agents` — the shipped system, and its hard-won traps

**Thesis (OBSERVED, `CLAUDE.md`).** *"A worker is a persistent CLI REPL living in a PTY"*, managed by a
supervisor (identity, crash-revive, lifecycle), coordinated over a file bus, observed from a browser
room. One-shot `agent -p` invocations were **removed, not deprecated** — `STATE.md` records the mandate
and `.archive/webui-transport-a-era/` holds the corpse.

**Identity is durable; the process is disposable** (OBSERVED, `webui/session-supervisor.mjs:4-10`):
*"Makes a worker a durable IDENTITY (a name) whose body (the claude REPL process)…"* — crash-detect via
the PTY's real `onExit` → auto-restart **under the same name** with backoff, announcing
`♥ alive (revived)` on the bus. A generation counter discards stale exit handlers from an older body of
the same identity (`:353`). On rehydrate, a pid that is alive but un-ownable is **not killed** —
*"only kill pids this supervisor spawned"* (`:290`). That is precisely the ownership boundary the state
driver's `attach` verb has to respect at fleet scale.

**The `agent-team-kit` state machine (the earlier, portable extraction).** Six manager-side states in
`state/<name>.json` (`agent-team-kit/README.md:16-23`): `RUNNING` (poke in flight) · `WAITING_POKE`
(between pokes, work remains — **no beat is normal**) · `STOOD_DOWN` · `BLOCKED` · `DOWN` (stale beat
mid-directive only) · `POKE_HUNG` (poke exceeded wall-clock timeout). The dispatch predicate
`should_poke_worker` (`state-helpers.sh:108-139`) refuses to poke when the lock is held or a
`poke-started` marker is fresh, and refuses outright in `STOOD_DOWN|BLOCKED|RUNNING`; a `PING` in the
inbox forces an immediate poke; otherwise a mission plus a stale-or-absent beat triggers one.
State is **reconciled from durable bus signals** after each poke (`state-helpers.sh:61-79`) — it reads
the `⏹` / `⛔` lines out of `to-manager.md` rather than trusting in-memory state.

**The worker's contract** (`.meta/manager-channel/WORKER-PROTOCOL.md`, Transport-A era): read protocol +
inbox (newest instruction wins), work one step, **checkpoint to disk continuously and append-only**
("the next poke has no chat memory"), report `♥ alive`, write a machine beat file, exit. PING → PONG
before any other work. Blocked → post `⛔`, write the beat, exit, **do not spin**. Stopping → post
`⏹ stopping — resume from: <pointer>` and **delete the beat file**. Respawn → find the last `⏹`/`♥`
line and resume; do not redo checkpointed work.

**SLA honesty** (`agent-team-kit/README.md:35-39`): *"Graceful degradation = no data loss, not continued
execution."* If the manager or the scheduler dies, pokes stop until someone relaunches; files on disk
are the recovery surface. That sentence should be lifted into the new design almost verbatim.

**PTY / transport traps that are acceptance tests** (`living-agents/PITFALLS.md`, all confirmed):
- `prompt + '\r'` in **one** PTY write is treated as a **paste**; the turn never submits and the driver
  waits forever. Fix: write text, wait ~300 ms, then a standalone `\r`. Applies to `cursor-agent` too.
- **Never stream raw PTY bytes into a response file.** The status bar streams digits *after* the answer,
  so "last number in the file" returns `0`/`1`. Scrape the *rendered* screen instead.
- Even a bullet-anchored scrape isn't chrome-safe: the spinner lands on the **same un-newlined raw
  stretch** as the reply (`42✽ Schlepping… (4s · ↓ 1 tokens)`).
- **`statSync().size` is bytes; `String.slice` is chars.** Tailing a bus file full of multibyte glyphs by
  byte offset **silently hides appended lines** — a verifiably-on-disk `♥ alive (revived)` went missing.
- The marker file a consumer requires must **exist from recruit time**, not from the first completed turn
  — otherwise a turn-zero session reads as "no live REPL".
- `cursor-agent`'s input box renders **during** a busy turn, so prompt-shape-present is not readiness;
  the real oracle is the busy-flag transition (appear-then-disappear + screen settled ≥1 s). There are
  **no OSC 133/633** shell-integration sequences to wait for.
- Honest operator-facing refusals must be **HTTP 200 + `{ok:false, code}`**; Chrome logs every ≥400
  response as a console error, so "honest failure = 4xx" and "zero console errors" are structurally
  incompatible. Keep real 4xx/5xx for genuine protocol errors.
- `printf` with a format starting `- ` parses the dash as an **option** and dies — every bus line in this
  grammar starts `- [HH:MM]`. Use `printf -- '…'`.
- **Verified-in-proof ≠ visible-to-operator**: a long-running server on `:7788` kept executing pre-fix
  code while proofs passed on fresh ports. Bitten twice. After landing operator-facing changes, check
  what is listening and restart it yourself.

### 4. `dgx-fleet` — the real multi-machine fleet, and the vocabulary to reuse

**Inventory model (OBSERVED).** `inventories/production/` and `inventories/staging/`, each with
`group_vars/` and `host_vars/<host>.yml`. Hosts are grouped by machine class (`hosts: dgx_spark` in
`playbooks/site.yml:19`). Variable precedence is stated and strictly bottom-up
(`WHY.md`, "Parameterize everything"): `defaults/main.yml → group_vars/all.yml → group_vars/<group>.yml
→ host_vars/<host>.yml → extra-vars`, and **extra-vars never carry policy** — only `allow_reboot`,
`break_glass_justification`, ad-hoc overrides.

**Per-host declarations that map straight onto agents** (`inventories/production/host_vars/dgx-01.yml.example`):
`ansible_host` (reachability), `workload_tier` (the role knob: `inference` vs `training`, with
*"No 'dev' tier on production boxes"*), `vault_role_id` (non-secret per-host identity; the matching
secret is delivered out-of-band to a `0400 root` file and is **not in the repo**), and a list of
**self-contained deployment specs** — each with a pinned `image_digest`, a `model.checksum_sha256`,
a `network` block (port, bind, `allow_from`), a `resources` block (GPU UUIDs, cpu quota, memory max/high,
`oom_score_adj`), a `health` block (`readiness_url`, `readiness_timeout_s`, `canary_prompt_id`), a
`rollout` block (`strategy: blue_green`, `drain_timeout_s`) and an `isolation` block (cgroup slice).
The argspec **rejects tag-only image refs in production**.

**The five fleet-control primitives worth copying wholesale:**

1. **`drained: true` as a host flag the play refuses to touch** (`playbooks/site.yml:41-46`): an assert
   in `pre_tasks` fails with *"Host … is drained (reason). Re-add by removing 'drained: true' from
   host_vars."* Drain is declarative, reasoned, and reversible by config — not a runtime side channel.
2. **`baseline` vs `dangerous` tags** (`playbooks/site.yml` header + role list). `baseline` roles are
   safe for the unattended hourly `ansible-pull` cron; `dangerous` roles are push-only. Hard rule from
   `WHY.md`: **`baseline`-tagged tasks must not perform secret lookups** — reusing the AppRole secret
   hourly forever turns it into a permanent attack surface.
3. **Canary = `serial: 1` + gates** (`playbooks/canary.yml`). One host at a time; `any_errors_fatal`;
   a pre-apply healthcheck that **refuses to proceed** if it fails; a post-apply smoke test; an
   optional `pause` for human verification between hosts; and a host-local **flock** on
   `/var/run/ansible-pull.lock` so push and pull cannot race. *"If dgx-01 fails, dgx-02 is never
   touched."*
4. **Explicit ordering, not hidden dependencies** (`WHY.md`, "Explicit play ordering, not role
   meta-deps"): dependencies two directories deep re-apply opaquely; the canonical sequence lives in one
   reviewable list. Same reasoning as "structure resists drift better than prose."
5. **Single end-of-play reboot evaluator** (`playbooks/_reboot-evaluator.yml`): multiple roles may
   *request* a disruptive action by setting a host fact; exactly one aggregator decides and executes,
   gated by `allow_reboot | default(false)`. **The fleet analogue is: many roles may request an agent
   restart; one evaluator performs restarts.**

**Topology is declared, not hardcoded** (`INVENTORY.md`). A per-host state table whose columns are the
contract — *workload tier · deployments · mounts · fabric role · **blast radius if lost***. Four named
topologies (A sharded / B replicated / C active-passive / D mixed), each with a declaration sketch and a
**failure → topology re-statement** section saying what to re-declare when a host dies. Two rules worth
stealing: a **designated primary** for any decision that needs a single answer (*"avoids n=2 split-brain
by fiat"*), and a refusal to adopt Topology C in production **until its failover runbook is authored**.
Also: *"add a third host when you can dedicate a separate inventory group for it — splitting prod and dev
tiers across the same group muddles the workload-tier contract."*

**Idempotency and drift, as engineering practice** (`docs/research/05-testing-idempotency-ci.md`):
the two-pass test (re-run and fail if anything reports changed); `--check --diff` on every PR against a
staging host; `changed_when:` mandatory on any shell-out; banned patterns —
`changed_when: false` used as a silencer ("lying about idempotency, worse than the original problem"),
`ignore_errors` without a follow-up assertion, `state: latest`, `get_url` without a checksum, timestamps
baked into templates (the file changes every run), roles with no argspec. Drift runs nightly against
**production** in check mode and **opens a GitHub Issue** as the operator's drift dashboard
(`.github/workflows/nightly-drift.yml:1-13, 39-50`). *"For a two-node fleet, AWX/Tower is overkill."*

**Hard-fail on version drift** (`WHY.md`): `nvidia_verify` asserts the driver/CUDA major matches the
pin, so an out-of-band upgrade fails the next apply **loudly**; the operator inspects, then a PR bumps
the pin. Direct analogue: **pin the agent CLI version range and fail loudly when the fleet's detectors
meet an unknown version** — which is also SYNTHESIS conclusion C4.

**Process pitfalls with fleet relevance** (`PITFALLS.md`): a comment claimed a substitution happened and
the code did not — caught only by a fresh-agent onboarding review, and the fix added a **defensive
assert that fails loud if any value still contains the placeholder**; `HANDOFF.md` rotted within 24
hours because a completed item wasn't updated in the same commit; a self-tripping test (its own grep
pattern matched itself) plus the discovery that `grep --exclude-dir` matches a **basename**, not a path.

### 5. Skims

- **`swarm-test`** (BridgeSpace artifacts, 2026-06-16). `agents.json` is a flat
  `[{label, role}]` roster (`Coordinator 1`/coordinator, `Builder 1`/builder, …). Coordination is a
  markdown `SWARM_BOARD.md` with a task table whose columns are `ID · Task · Owner · Owned Files ·
  Depends On · Status` and a lifecycle `OPEN → ASSIGNED → PLANNING → BUILDING → REVIEW → DONE`; plan
  state is also an append-only event log (`plan/events/*.json`, e.g. `{id, type: goal_created,
  timestamp, actorLabel, goal{…}}`), and messaging is a CLI (`bs-mail send --to @all|@operator --type
  swarm_complete`). Two things bear on our design: **file ownership is the concurrency primitive**
  ("no two tasks share file ownership; if unavoidable, sequence them with DEPENDS_ON"), and the
  coordinator prompt is riddled with **timing hacks** — *"BridgeSpace launches you FIRST… Builders come
  up roughly 2 seconds later and start polling within 60 seconds… use that head start"*. That is a
  race condition papered over with a prompt, and it is exactly what verified readiness replaces:
  dispatch when the worker is **proven idle**, not 2 seconds after launch.
- **`meta-harness-pi-like`**. `.meta/DECISIONS.md` is a ratification ledger (PROPOSED → LOCKED, with
  reversibility per decision) — a good governance shape for the mesh's own design decisions. Relevant
  content: D1 typed **envelope** between heterogeneous CLI agents (`summary` + optional JSON Schema +
  `artifacts[]`, defaulting to pass-summary-only, never hard-fail); D4 **tiered isolation with a
  `direct` floor** (git→worktree, Dockerfile→docker, else direct+warn — "the only strategy with zero
  preconditions"); D5 **MCP is not an orchestration bus** ("MCP exposes tools *to* an agent"), keep a
  `CliAgentAdapter` as the core contract. Its `PITFALLS.md` adds Windows-specific facts: PSReadLine
  fails to init in a spawned host context (default to `cmd.exe`); **ConPTY cooks and reflows output**,
  so byte-comparing an echo is not a valid oracle; `AttachConsole failed` when spawning multiple ConPTYs
  in one process; chunk PTY writes by **`TextEncoder` byte length ≤4096 on code-point boundaries**, not
  `.length`; and *"don't crown a winner from N=1."*
- **`agent-native`** — an Obsidian/MDX content app. **Nothing bearing on multi-agent coordination.**

---

## What to steal

| # | Steal | From (OBSERVED) | Why |
|---|---|---|---|
| 1 | **Keystone rule**, generalised to three tiers: registry entry ≠ live announcement ≠ verified state | `mailbox/PROTOCOL.md:70-94` | Kills phantom presence at every layer, and slots the driver's evidence in as the strongest tier |
| 2 | **Orphan self-heal**: never fabricate a missing role; report, watch, join when a real one appears | `mailbox/PROTOCOL.md:88-91` | Same refusal-to-guess posture as `conflict` |
| 3 | **Arm the watcher before announcing** | `mailbox/PROTOCOL.md:51-56` | Removes a real, observed join-race |
| 4 | **Message envelope + ULID + kinds + process-THEN-ack + `(from,id)` dedup + quarantine-on-bad-sig** | `agent-mesh/proposal-minimal.md` 1.1-1.2, `anticipated-failures.md` AP | Already designed and adversarially reviewed; do not redo |
| 5 | **Directory entry** `{agent_id, endpoint, pubkey, key_version, transport, capabilities, last_seen, joined, sig}`, CAS per entry, join human-gated + read-back confirmed, **slugs tombstoned never reused** | `redesign-issue.md` 3, `anticipated-failures.md` BC | One identity across auth, path and routing; no mapping table to drift |
| 6 | **Six-state scheduler machine** kept orthogonal to the seven observed agent states, with `WAITING_POKE` meaning "absent is normal" | `agent-team-kit/README.md:16-23`, `watchdog.sh:5-7` | Prevents fleet-wide false DOWN; the cross-product is the interesting signal |
| 7 | **Durable identity, disposable body**: revive under the same name with backoff + generation counter; never kill a pid you did not spawn | `living-agents/session-supervisor.mjs:4-10, 290, 353` | The ownership boundary `attach` needs at fleet scale |
| 8 | **`drained: true` host flag** + a pre-flight assert that refuses drained hosts | `dgx-fleet/playbooks/site.yml:41-46` | Declarative, reasoned, reversible maintenance mode |
| 9 | **`baseline` vs `dangerous` capability tags**, with "unattended paths must not touch secrets" | `dgx-fleet/WHY.md`, `site.yml` header | The autonomy dial for self-orchestrating agents |
| 10 | **`serial: 1` canary with pre-check gate, post-check smoke, optional human pause, and a push/pull mutex** | `dgx-fleet/playbooks/canary.yml` | The correct default for any fleet-wide change to agent config or prompts |
| 11 | **One evaluator for disruptive actions**; roles request via a fact, one aggregator decides | `dgx-fleet/playbooks/_reboot-evaluator.yml` | Stops N roles independently restarting agents |
| 12 | **Per-host state table whose columns include blast radius**, plus named topologies with a failure→re-declaration section and a **designated primary** | `dgx-fleet/INVENTORY.md` | Ready-made topology vocabulary for role meshes; kills n=2 split-brain by fiat |
| 13 | **Argspec-per-role + generated docs + lint failure on a missing spec** | `dgx-fleet/WHY.md` | Role capabilities become a validated contract, not an `if cli == 'claude'` ladder |
| 14 | **Nightly drift in check mode → opens an Issue** | `.github/workflows/nightly-drift.yml` | Drift dashboard with zero new infra |
| 15 | **Dead-man's switch + synthetic end-to-end canary + evidence-citing auditor** | `agent-mesh/anticipated-failures.md` BQ/BP, `monitoring-prior-art.md` 2.2-2.3 | Detects a broken guarantee before real work hits it, and catches a lying checker |
| 16 | **φ-accrual adaptive timeouts and SWIM's indirect probe** | `agent-mesh/monitoring-prior-art.md` 1 | Replaces the admittedly-guessed fixed hang threshold; a second observer confirms a suspect before declaring it dead |
| 17 | **File-ownership as the concurrency primitive** (no two tasks share owned files; else `DEPENDS_ON`) | `swarm-test/SWARM_BOARD.md` | Simple, checkable, and already in the owner's vocabulary |
| 18 | **SLA honesty sentence**: graceful degradation = no data loss, not continued execution | `agent-team-kit/README.md:35-39` | Sets the right expectation for a fleet whose scheduler can die |

## What to avoid, and why

1. **A star topology with one manager.** The mailbox protocol is explicitly a star ("The manager owns
   routing", `README.md:30`), and its own election rules exist only to keep exactly one hub alive. A
   configurable role mesh must not inherit the single hub — but it **must** inherit the election
   discipline (earliest-timestamp wins, demote yourself on discovering an earlier claim).
2. **Any "presence" that is a self-written file with no external check.** Both prior systems do this
   (`heartbeat/<name>.beat`, `last_seen` in the directory), and both name the residual themselves
   (agent-mesh BB; `SYNTHESIS.md` 1.9 on cultureagent). Keep the heartbeat as a *cheap first filter*,
   never as the dispatch gate.
3. **Ack-on-receipt.** The exact shipped bug (`redesign-issue.md` 1, with line numbers). Retire a task
   only on process-then-ack, and treat "the transport accepted it" as delivery evidence, never handling
   evidence.
4. **A shared inbox everyone can write to** on any substrate whose write permission also grants delete.
   Sender-partition, or accept that any peer can silently delete another peer's pending work
   (`critique-isolation.md` 0).
5. **Resolving an endpoint by display name, title, or item count.** Three separate incidents
   (`failure-archaeology.md` rows 4/5/6): a ghost list out-voted the live one because it had more items.
   Resolve by stable id; **refuse ambiguity loudly** rather than picking.
6. **Timing-based coordination.** The BridgeSpace coordinator prompt budgets a "2 second head start" and
   a "60 second" polling window. That is the guess this whole project exists to delete.
7. **One-shot `agent -p` as a worker primitive.** Removed by mandate after being shipped
   (`living-agents/STATE.md`, `CLAUDE.md`: *"Don't reintroduce them."*) — persistent sessions only.
8. **Patching or racing the vendor TUI.** `SYNTHESIS.md` C10 (never patch the binary) plus the owner's
   own scrape traps: raw bytes are not lines, the spinner fuses onto the reply, byte offsets hide lines.
   Anything read off a screen needs a sanitiser and a version-pinned indicator set.
9. **`ignore_errors` / `changed_when: false` as silencers**, in any form — including a fleet
   "best-effort dispatch" that swallows a failed injection. `dgx-fleet` bans the pattern by name.
10. **Assuming multiple pollers can share one credential.** Three pollers on one account produced a
    2FA/503 auth-storm (`failure-archaeology.md` row 7). At most one authenticating client per
    credentialed identity, bounded backoff, never an unattended re-auth.
11. **Docs that drift within a day.** `dgx-fleet/PITFALLS.md`: update the claim in the **same commit** as
    the change. Related: verified-in-proof ≠ visible-to-operator — restart the long-running process
    yourself (`living-agents/PITFALLS.md`).
12. **Merging role and machine into one axis.** `INVENTORY.md`: don't split prod and dev tiers across one
    inventory group; it "muddles the workload-tier contract."

## Open questions for the design

1. **What is the fleet's substrate, given that the file mailbox is single-machine by construction and
   agent-mesh's Radicale/CalDAV choice was driven by an iPhone requirement this project does not have?**
   MQTT was rated the strongest ack/cursor/persistent-session candidate and rejected **only** because it
   had no stock iOS surface — a constraint that does not apply here (`transport-fit.md` 2). Re-run that
   comparison with the real constraint set (many machines, heterogeneous OS, no phone leg). Note the
   named MQTT hazard: a spoofed `CONNECT` with a duplicate `clientId` destroys another client's
   persistent session and its queued QoS 1/2 messages.
2. **How does verified state enter the message layer?** Options: (a) a `kind: "state"` envelope carrying
   the driver's `{state, attrs, evidence[]}` as first-class mesh traffic; (b) a per-agent state document
   in the directory that the scheduler reads before dispatch; (c) a pull-model — the dispatcher asks the
   *machine agent* on the target host at dispatch time. (c) is freshest and immune to stale caches, but
   makes dispatch synchronous and partition-sensitive (agent-mesh class Y: reachability is per-agent).
   **Recommendation to decide, not assume:** (b) as the cache + (c) as the confirm-before-dispatch
   check, with the cache's age carried in the evidence.
3. **Who runs the driver on each machine, and does that node itself need verified state?** dgx-fleet's
   answer for its own agents is an argspec'd role plus a hard-fail assert; agent-mesh's answer for its
   auditor is "off the message path, read-only, publishes evidence." A hung *observer* is undetectable by
   construction unless something else watches it — this is class BQ and the dead-man's switch is the only
   named mitigation. **Decide whether the machine-agent is itself a mesh member with a directory entry.**
4. **What is the hang threshold, and does it stay fixed?** The project's own README lists compaction
   behaviour as unverified and admits *"the hang-watchdog threshold is still a guess"*. agent-mesh
   already surveyed φ-accrual as the adaptive replacement. Do we ship a fixed threshold with a
   config assertion (cultureagent's `stale > heartbeat` fail-fast), an adaptive detector, or both?
5. **Does the mesh need key rotation/revocation on day one?** agent-mesh ranks AK/AL/AM as the **#1
   genuine new gap** and notes that deferred signing is a live downgrade oracle. On a multi-machine
   fleet the blast radius of a leaked key is much larger than on one box. Answer explicitly, including
   whether `enforce_sig` starts on.
6. **What is the fleet's isolation boundary?** agent-mesh's honest scope statement — a server ACL binds
   remote and buggy agents, not a malicious co-located one — was written for one Windows box with one OS
   user. Many machines change the calculus: per-machine OS users, containers (family BF–BK), or an
   accepted trusted-fleet assumption. **Say which, and say what it does not cover.**
7. **What is the role vocabulary, concretely?** dgx-fleet gives the *shape* (`workload_tier` per host,
   groups per class, argspec'd capabilities), not the content. Candidate axes to settle: capability
   (which CLI + version + OS + toolchain), authority (may it dispatch? may it approve permissions?),
   autonomy tag (`baseline` unattended vs `dangerous` human-gated), and residency (which machine, and
   is it pinned). Are roles per-agent, per-machine, or both — and can an agent hold more than one?
8. **What replaces `serial: 1` for agent work?** Canary rollout maps cleanly to *config* changes
   (prompts, hooks, CLI upgrades) but not to task dispatch. Is there a fleet-wide change class that
   must go one machine at a time with a verification gate between, and who is the "human pause"?
9. **What is the GC policy for every durable store** (message ledgers, evidence logs, state history,
   checkpoints), and how does pruning interact with replay-safety? agent-mesh classes AY/AZ say every
   store needs a stated policy and that pruning a ledger id below the replay horizon reopens replay.
   The state driver adds a new store — evidence — that nobody has yet sized.
10. **Does the fleet keep the `resume-from` contract?** The mailbox eject prompt requires a departing
    agent to name where it left off and the manager to reassign that work. With verified `dead` /
    `presumed_hung` states, an agent may die **without** getting to write its `resume-from`. What is the
    recovery surface then — the last checkpoint on disk, a manager-side task lease with a timeout, or
    both? (dgx-fleet's answer for machines is `replace-failed-node.md`; there is no agent equivalent yet.)
