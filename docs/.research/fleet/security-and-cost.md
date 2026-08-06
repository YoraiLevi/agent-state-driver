# Fleet research: trust and money

Scope: the two properties that make a multi-machine, role-based orchestration mesh of CLI AI
agents dangerous at scale — **who is allowed to make an agent run code**, and **what stops the
fleet spending unbounded money**. Written for the design of a *new* system layered on this
repo's verified-state primitive.

Provenance rules used here: **OBSERVED** = read first-hand in a file in this repo or in a page
fetched during this pass (cited by `file:line` or URL). **INFERRED** = my reasoning on top of
those facts, marked inline. Vendor docs were fetched 2026-08-06 and are saved under
`.research/prior-art-search/` in the session scratchpad (not committed — some carry PII-shaped
example payloads).

---

## Verdict

- **The mesh's dispatch edge is a remote-code-execution API, and this repo already ships the
  exploit primitive.** Q1 proved hooks can be retrofitted onto a *running* session by writing
  the project `.claude/settings.json` mid-session (`docs/design/functional-design.md:23-26`),
  and the vendor confirms settings hot-reload including `hooks` with a `ConfigChange` hook per
  change (monitoring/settings docs, "Claude Code watches your settings files and reloads them
  when they change… This includes `permissions`, `hooks`"). So **filesystem write access to a
  repo == arbitrary command execution inside every agent attached to it.** Any fleet design
  that lets a remote node deliver a workspace, a settings fragment, or a plugin is granting
  RCE. Treat "who may write settings on a node" as a *higher* privilege than "who may enqueue
  a task".
- **Make the task envelope a capability that can only be attenuated, never widened.** Biscuit
  (and Macaroons before it) give exactly this: a public-key-signed bearer token where
  "the other blocks can be freely added by intermediate parties (offline attenuation)… The
  token can only be restricted, it will never gain more rights"
  (https://www.biscuitsec.org/docs/getting-started/introduction/). An agent that enqueues work
  must derive the child envelope from its own, offline, with no call to the scheduler. A
  prompt-injected node then cannot mint authority it did not already hold — the blast radius
  of a compromise becomes exactly the compromised role's own grant, which is the only
  containment story that survives agent-to-agent propagation.
- **Agent-to-agent prompt-injection propagation is demonstrated prior art, not a hypothetical,
  and it decays with hop count.** Morris-II (arXiv:2403.02817, v2 2025-01-30) shows an
  "adversarial self-replicating prompt that triggers a cascade of indirect prompt injections
  within the ecosystem and forces each affected application to… compromise the RAG of
  additional applications", with worm performance measured *as a function of the number of
  hops*. Design consequence: every envelope carries `hop_count` and a **provenance taint**
  (human-authored / agent-derived / derived-from-untrusted-content); tainted envelopes get a
  strictly smaller capability set and a low hop ceiling, and hop 0 is only reachable from a
  human-signed root.
- **Verified state is a security control, not only a scheduling one.** Prior art's presence is
  self-reported (`SYNTHESIS.md:365-372`: "Self-report is only as good as the reporter"), which
  means a compromised node can lie about being idle to attract work. This repo's evidence
  array (`{state, attrs, evidence:[{channel,signal,at}]}`,
  `docs/design/functional-design.md:136-137`) is the fleet's *attestation* format: the
  scheduler should require fused-channel evidence for readiness, and treat a node whose
  channels disagree (`conflict`, SPEC rule 9, `prototypes/common/SPEC.md:78-80`) as
  quarantined rather than merely unknown.
- **Sandboxing is not uniform across the fleet, and the gap lands exactly on the OS this repo
  went to the most trouble to support.** Claude Code's built-in Bash sandbox "runs on macOS,
  Linux, and WSL2. **Native Windows is not supported**" — Seatbelt on macOS, bubblewrap+socat
  (+optional seccomp via `@anthropic-ai/sandbox-runtime`) on Linux/WSL2
  (https://code.claude.com/docs/en/sandboxing). The Windows leg of this project is a native
  ConPTY host on `windesk` (`docs/design/functional-design.md:139-150`), i.e. **an unsandboxed
  execution class**. Roles must be capability-typed: any role that may ingest untrusted content
  must be schedulable only onto nodes that can prove an isolation boundary.
- **Cost cannot be enforced from telemetry, only audited by it — this repo already measured
  why.** Q4 found the block window is telemetry-silent and the one precise identifier exports
  only *after* the state ends (`docs/.research/empirical/q4-telemetry.md:169-186`); the vendor
  defaults are 60 s metrics / 5 s logs export and the docs state outright that "Cost metrics
  are approximations" (monitoring-usage). Budgets must therefore be enforced **at the dispatch
  boundary, before a turn starts**, with telemetry used for reconciliation and drift alarms.
- **The fleet budget is dual-currency and most designs get this wrong.** API-key nodes spend
  USD (org monthly spend caps: Start $500, Build $1,000, Scale $200,000; per-workspace spend and
  rate limits configurable — https://docs.claude.com/en/api/rate-limits). Subscription nodes
  spend *plan window percentage*, and Anthropic states plainly that "Usage inside the seat
  allowance isn't metered in dollars" (code.claude.com/docs/en/costs). A single USD ledger over
  a mixed fleet is a fiction. Carry both, and make `rate_limits.five_hour.used_percentage` /
  `seven_day` (available on statusline stdin for Pro/Max) a first-class scheduling input.
- **Budget exhaustion has exactly one safe stopping point, and this project owns it.** You
  cannot kill mid-turn without losing the turn's work and paying for it anyway. The state
  machine's `idle` is the only clean seam. Enforce budgets as a **refusal to `send`** — the
  verb this repo already refuses when the state is wrong (`prototypes/fused/driver.py:471`) —
  and add a terminal `budget_exhausted` distinct from `dead` so recovery does not look like a
  crash.

---

## Findings

### 1. Trust boundaries in a dispatch mesh

There are four distinct boundaries; conflating any two is the classic failure.

| # | Boundary | Question it answers | Weakest prior-art answer |
|---|---|---|---|
| B1 | Node admission | may this machine join the mesh at all? | Tailscale tags; but see the key-expiry trap below |
| B2 | Enqueue authority | may this principal put work on a queue? | usually "anyone on the network" |
| B3 | Task authorisation | may *this task* run with *these* capabilities on *this* node? | usually implicit in B2 |
| B4 | Execution confinement | what can the task touch once running? | OS sandbox — absent on native Windows |

**B1 — node identity.** Tailscale's tag model is the closest fit found: "Tags are essentially
service accounts", defined in `tagOwners`, applied with
`tailscale login --advertise-tags=tag:server`, and "A tagged device's identity is the
combination of all its tags (not the intersection)"
(https://tailscale.com/kb/1068/acl-tags). Two operational facts matter for a fleet:

- Tags **do not AND** in policy: "you cannot define a rule that permits access to devices with
  both `tag:prod` and `tag:database`. Instead, you can use a composite tag such as
  `tag:prod-database`". A role mesh expressed as orthogonal tags will silently over-grant;
  composite role tags (`tag:fleet-worker-untrusted-linux`) are the documented workaround.
- **"When you apply a tag to a device for the first time and authenticate it, the tagged
  device's key expiry is disabled by default."** A tagged fleet node therefore holds a
  credential that never expires unless you re-enable expiry from the admin console or API.
  For a large fleet of ephemeral workers that is a permanent-credential accumulation problem.
  (This repo's own infra already runs over Tailscale — `PITFALLS.md:156-158`.)

**B2/B3 — task authentication.** The MCP security spec's rules generalise directly and are
written in RFC-2119 language worth copying verbatim into the mesh spec
(https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices):

- "MCP servers **MUST NOT** use sessions for authentication." → A `session_id` from this
  repo's driver is a *name*, never a bearer credential. Do not let a node act on a task because
  it knows the session UUID.
- "MCP servers **MUST NOT** accept any tokens that were not explicitly issued for the MCP
  server." (token passthrough) → A node must reject an envelope whose audience is another node
  or another role, even if the signature verifies.
- The **confused deputy** section describes a proxy with a static client ID that hands
  attacker-controlled flows the deputy's authority. A fleet scheduler *is* a proxy with a
  static identity; if it re-signs agent-originated tasks under its own key, it is the confused
  deputy by construction. The scheduler must forward attenuated child envelopes, never mint
  fresh ones on an agent's behalf.

**B3 — the admission-control shape to copy.** Kubernetes validating/mutating admission webhooks
give the operational details that most home-grown gates miss
(https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/):
`failurePolicy: Fail` is the **default and means fail-closed** (`Ignore` is opt-in fail-open);
`timeoutSeconds` bounds the gate (examples use 2-5 s) so a hung policy engine cannot wedge the
cluster; `matchConditions` (CEL, up to 64 per webhook) pre-filters cheaply, and when a match
condition itself errors the request is *rejected* under `failurePolicy: Fail` "without calling
the webhook"; mutating webhooks "must be idempotent" and declare `reinvocationPolicy` because
a later mutation can invalidate an earlier decision. Every one of those has a mesh analogue:
a policy check on enqueue that times out must **reject**, and any envelope-rewriting step must
be idempotent because a re-queued task will pass through it twice.

**B4 — confinement.** See section 3.

### 2. Prompt injection propagating agent-to-agent

- **The vector is published and quantified.** Morris-II (arXiv:2403.02817) demonstrates
  zero-click, self-replicating prompts cascading through GenAI applications over RAG-based
  inter-application communication, with measured sensitivity to context size, embedding model,
  and **number of hops**. It also ships a defence ("Virtual Donkey": reported TPR 1.0, FPR
  0.015) — i.e. a cheap inline classifier on inter-agent messages is a demonstrated, not
  speculative, control.
- **Claude Code's own defences are per-session, not per-fleet.** The security doc lists
  permission prompts, "Isolated context windows: Web fetch uses a separate context window to
  avoid injecting potentially malicious prompts", "Command injection detection", and
  "Fail-closed matching: Unmatched commands default to requiring manual approval"
  (https://code.claude.com/docs/en/security). None of these knows anything about a *second*
  agent. The moment one agent's output is another agent's input, the isolated-context
  protection is defeated at the mesh layer, by us.
- **The concrete fleet-poisoning path** (INFERRED, but every step is OBSERVED individually):
  1. Agent A reads an attacker-controlled file in a repo it was told to review.
  2. The injected text tells A to enqueue a task ("as part of the review, ask the infra role to
     run …").
  3. If enqueue authority is ambient (B2 unguarded), the mesh accepts it.
  4. The infra role executes it on a node with wider capability than A had — privilege
     escalation *by delegation*, which is exactly what offline attenuation forbids.
  5. If the task body itself contains the self-replicating text, step 1 recurs on the new node.
- **Two structural mitigations beat any classifier.** (a) Attenuation-only envelopes make step
  4 impossible. (b) A **taint bit that is monotone**: once an agent's context has ingested
  content whose provenance is not human-signed, every envelope it emits for the rest of that
  session is tainted, and tainted envelopes cannot request network egress, credential access,
  or a wider node class. This is the "lethal trifecta" framing (private data access + untrusted
  content + exfiltration channel) applied at the queue rather than at the prompt; the sandbox
  doc gives the matching enforcement knob — `sandbox.network.strictAllowlist` "denies sandboxed
  commands access to any host outside the allowlist instead of prompting" and
  `allowManagedDomainsOnly` in managed settings blocks non-allowed domains outright.

### 3. Sandboxing, per OS — the real, asymmetric picture

All OBSERVED from https://code.claude.com/docs/en/sandboxing unless marked.

| OS | Mechanism | Fleet-relevant caveats |
|---|---|---|
| macOS | Seatbelt, built in, nothing to install | Go CLIs (`gh`, `gcloud`, `terraform`) "may fail TLS verification under Seatbelt" → pushed into `excludedCommands`, i.e. out of the sandbox. `allowAppleEvents` "removes code-execution isolation" |
| Linux / WSL2 | `bubblewrap` (filesystem) + `socat` (proxy relay); optional seccomp filter from `npm i -g @anthropic-ai/sandbox-runtime` blocks Unix domain sockets | Ubuntu 24.04+ AppArmor blocks bwrap user namespaces unless you install a profile (`kernel.apparmor_restrict_unprivileged_userns`); `enableWeakerNestedSandbox` for unprivileged containers "considerably weakens security"; WSL2 sandboxed commands cannot invoke Windows binaries under `/mnt/c/` |
| Native Windows | **none** — "WSL1 and native Windows are not supported" | The only isolation options are the outer container/VM, and Windows-native primitives (AppContainer, Job Objects, WDAC) that Claude Code does not use (INFERRED: this is a gap the mesh must fill itself or refuse to schedule into) |

Sandbox properties that change fleet policy design:

- **Network default is deny-with-prompt, not deny.** "no domains are pre-allowed by default…
  the first time a command needs a new domain, Claude Code prompts for approval", and since
  v2.1.191 a Yes allows the host for the rest of the session. Unattended fleet nodes have no
  human to answer that prompt — so an unattended role **must** ship `allowedDomains` +
  `strictAllowlist: true`, or every new domain becomes a `waiting:permission` stall (which is
  precisely the state this repo detects, so the mesh can at least *see* it).
- **TLS is not inspected by default**: "the built-in proxy does not terminate or inspect TLS on
  outbound traffic". Domain allowlisting is the whole control; exfiltration to an allowed
  domain is unimpeded.
- **`allowUnixSockets` is a host-escape switch**: "allowing access to `/var/run/docker.sock`
  effectively grants access to the host system through the Docker socket."
- **Policy-file self-protection exists and is worth mirroring**: the sandbox "automatically
  denies write access to the files a sandboxed command could otherwise edit its own policy
  through" — `settings.json` at every scope, the managed settings directory, `.mcp.json` at the
  project root and each `--add-dir` root, and (since v2.1.210) symlink targets that appear at
  those paths. A mesh agent must likewise be unable to write the fleet's own policy artefacts.
- **A documented hole to plan around**: "`excludedCommands` has no equivalent managed-only
  lockdown, so a developer can always append entries that run additional commands outside the
  sandbox. Keep the managed list narrow." On a fleet node, "a developer" is "anyone who can
  write user settings on that box".

### 4. The org policy plane already exists — treat managed settings as the fleet's admission controller

OBSERVED, https://code.claude.com/docs/en/settings:

- Precedence: **Managed (highest, and within the managed tier only ONE source is used, not
  merged)** → CLI `--settings` → local → project → user. Delivery: server-managed at sign-in,
  MDM plist (`com.anthropic.claudecodemanaged`), Windows registry (HKLM/HKCU),
  `managed-settings.json` at `/Library/Application Support/ClaudeCode/`, `/etc/claude-code/`,
  `C:\Program Files\ClaudeCode\`, plus a systemd-style `managed-settings.d/` drop-in dir
  (alphabetical merge, arrays concatenated+deduped, objects deep-merged).
- **`policyHelper`**: an executable that computes managed settings at startup from device
  posture/identity/remote service; it is ignored anywhere except MDM or a system
  `managed-settings.json`; when configured it becomes the *only* managed source; and **"When
  the helper exits non-zero at startup, Claude Code prints the error and refuses to start"** —
  a native fail-closed node-attestation hook. This is the single most useful primitive found
  for a fleet: node posture can gate whether the agent boots at all.
- Lockdown keys with no user override: `allowManagedHooksOnly`, `allowManagedPermissionRulesOnly`,
  `allowManagedDomainsOnly`, `allowManagedReadPathsOnly`, `strictKnownMarketplaces`,
  `disallowNonPluginCustomizations` ("blocks skills, agents, hooks, and MCP servers from user
  and project sources"), `allowedMcpServers`, `forceLoginOrgUUID`, `allowedHttpHookUrls`.
- Robustness detail worth copying: **managed settings parse tolerantly** — an invalid entry is
  stripped with a warning and "A single typo cannot disable the rest of your organization's
  policy" — while user/project settings are strict and rejected whole. A fleet policy
  distributor should behave the same way: never let one bad fragment disarm the policy.
- `ConfigChange` hooks are the audit tap the vendor itself recommends: "Audit or block settings
  changes during sessions with `ConfigChange` hooks" (security doc).

### 5. What this repo already refuses — and how each refusal scales to a fleet

| Refusal (OBSERVED) | Where | Fleet form |
|---|---|---|
| No `--dangerously-skip-permissions` | `prototypes/common/SPEC.md:63`; `PITFALLS.md:141` | No bypass flag may be set by a *task*; only by managed settings on a node explicitly typed as disposable. Note the vendor also blocks the flag "as root or via sudo… The check is skipped automatically inside a recognized sandbox" — so on a native-Windows node (no sandbox) there is no such backstop |
| No user-global config writes (`claude config set --global` banned; `config get` needs a timeout) | `functional-design.md:129-130`; `PITFALLS.md:30-31` | The mesh agent may write **project-scoped** settings only, and only inside a workspace it owns. Global writes are how one tenant poisons every session on a shared node |
| Never patch the target binary | C10, `SYNTHESIS.md:459-465` (VibeTunnel `claude-patcher.ts`, three regex variants from prior breakage) | No node image may ship a patched CLI; node attestation should hash the binary (INFERRED) |
| Refuse to send unless idle | `prototypes/fused/driver.py:471`, `scrape-driver/driver.py:317`, `hook-sentinel/driver.py:532`, `transcript-watch/driver.py:614` | The same refusal is the budget gate and the quarantine gate — one chokepoint, three policies |
| Never resolve a channel disagreement by picking a winner; report `conflict` | SPEC rule 9, `prototypes/common/SPEC.md:78-80` | A node in `conflict` is not dispatchable. "Guessing is the failure this project exists to eliminate" applies verbatim to trust decisions |
| Degrade loudly: `attach` without a terminal reports `screen_available: false` and names what it cannot do | SPEC rule 8, `prototypes/common/SPEC.md:71-76` | A node advertises a **capability vector** (channels available, sandbox present, OS, isolation class), and the scheduler matches roles to it instead of assuming parity |
| Bounded workflows, no unbounded agent loops, no bypass on spend-capable sessions | `STATE.md:37` | This is already the fleet cost policy in embryo; section 6 makes it enforceable |

### 6. Money: what the signals actually are, and what they cannot do

**Signal inventory (OBSERVED).**

| Signal | Shape | Latency | Fit |
|---|---|---|---|
| `claude_code.cost.usage` (counter, USD) | attributes: `model`, `query_source` (`main`/`subagent`/`auxiliary`), `speed`, `effort`, `agent.name`, `skill.name`, `plugin.name`, `marketplace.name`, `mcp_server.name`, `mcp_tool.name` + standard attrs (`session.id`, `user.email`, `organization.id`, `user.account_uuid`) | default metrics export **60 s** | Post-hoc attribution, per-role and per-skill. Best available *ledger*, worst possible *gate* |
| `claude_code.token.usage` | `type` ∈ input/output/cacheRead/cacheCreation, same attribution set | 60 s | Needed because cache reads bill at ~10% and don't count to ITPM |
| `claude_code.api_request` event | `cost_usd`, **`cost_usd_micros` (integer)**, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `duration_ms`, `request_id`, `query_source`, `effort`, `speed` | default logs export **5 s** | Per-request truth; the integer micros field is the one to ledger on (no float drift) |
| `claude_code.api_error` event | emitted **only after retries are exhausted**; `attempt` = 11 by default (`CLAUDE_CODE_MAX_RETRIES` default 10, cap 15) | terminal only | A rate-limited fleet looks like *slowness* for a long time before any error event appears |
| `claude_code.tool.blocked_on_user` span | `duration_ms`, `decision`, `source`; gated behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` | **span ends at the human's decision** — measured 37.9 s observation lag for a 32.9 s block (`q4-telemetry.md:144-157`) | Audit only. Already ruled out as a live channel by this repo |
| statusline stdin JSON | `cost.total_cost_usd`, `cost.total_duration_ms`, `cost.total_api_duration_ms`, `context_window.used_percentage` + `current_usage.{input,output,cache_creation,cache_read}_tokens`, `rate_limits.five_hour.{used_percentage,resets_at}`, `rate_limits.seven_day.…`, `session_id`, `model`, `effort` | re-runs at session start, **on every new assistant message**, on `/compact` finish, on permission-mode change, and on `refreshInterval` (min 1 s) | **The best local, near-real-time cost meter available.** "The status line runs locally and does not consume API tokens" |
| `subagentStatusLine` | per-task rows with `tokenCount`, `contextWindowSize`, `model`, `effort`, `cwd` | same triggers | Per-subagent spend visibility — the fan-out this repo already tracks via the `subagents/` transcript tree |
| Admin Usage & Cost API (`/v1/organizations/usage_report/messages`, `bucket_width` 1m/1h/1d) | authoritative, groupable by API key / workspace / model / service tier | "typically appears within **5 minutes** of API request completion" | Reconciliation and the only number finance may use |

**Hard limits on those signals (OBSERVED, and they kill the naive design).**

1. "Cost metrics are approximations. For official billing data, refer to your API provider"
   (monitoring-usage). `/usage` "computes the dollar figure locally from token counts priced at
   standard list rates, so it doesn't reflect promotional pricing or contracted discounts"
   (costs doc). A budget enforced on these numbers is enforced on an estimate — say so in the
   API, and reconcile against the Admin API.
2. Telemetry goes **completely silent while blocked on a human** — Q4 run 2 observed 88 s with
   zero batches (`q4-telemetry.md:120-132`). A spend watchdog built on export cadence will
   read "cheap" precisely when an agent is stalled and expensive in wall-clock.
3. Console exporters emit nothing observable under the TUI; an OTLP sink is mandatory
   (`q4-telemetry.md:99-115`).
4. Raw OTLP dumps carry `user.email`, `user.account_uuid`, `organization.id` — PII, never
   commit (`q4-telemetry.md:205-207`; the vendor confirms `user.email` is included under OAuth).
5. `rate_limits` appears "only for Claude.ai subscribers (Pro/Max) **after the first API
   response**" — so a freshly launched subscription node has no quota reading at all for its
   first turn (INFERRED consequence: the scheduler must treat first-dispatch to a cold node as
   uninstrumented and cap it conservatively).

**Enforcement primitives that actually stop spend (OBSERVED).**

- Org monthly spend cap by tier: Start **$500**, Build **$1,000**, Scale **$200,000**; Custom
  has none. Self-set spend limit below the tier cap in Console → Settings → Limits.
- **Per-workspace spend and rate limits** — "you can set custom spend and rate limits per
  Workspace… Organization-wide limits always apply, even if Workspace limits add up to more",
  and Claude Code authentication auto-creates a dedicated "Claude Code" workspace whose Limits
  page can "cap Claude Code's share and protect other production workloads". **This is the
  strongest real quota boundary available and it maps cleanly onto fleet roles** (INFERRED:
  one workspace per role class, not per node).
- Rate-limit response headers give live remaining budget without any telemetry pipeline:
  `anthropic-ratelimit-{requests,tokens,input-tokens,output-tokens}-{limit,remaining,reset}`
  and `retry-after` on 429. Headers reflect "the most restrictive limit currently in effect".
- Knobs that reduce per-turn cost: `MAX_THINKING_TOKENS` (e.g. `=8000`), `/effort` levels
  (`low`…`max`, and `effort` is an attribute on both cost and token metrics so you can prove
  the policy took effect), model choice (`model: haiku` for simple subagents), and context
  hygiene (`/clear` costs nothing; `/compact` "is itself a large request").
- Documented multiplier to plan capacity against: "Agent teams use approximately **7x** more
  tokens than standard sessions when teammates run in plan mode, because each teammate
  maintains its own context window and runs as a separate Claude instance" (costs doc). A
  fleet's cost model must be superlinear in fan-out by default.

---

## What to steal

1. **Biscuit-style offline attenuation for the task envelope.** Root envelope is human-signed;
   every agent-to-agent enqueue is a *derived* token with added checks (expiry, node class,
   tool allowlist, hop ceiling, budget ceiling). Verification needs only the root public key —
   no scheduler round-trip, which is what makes it survive partition. Carry the policy as
   Datalog-style checks so the envelope can constrain itself ("check if operation('read')").
2. **Kubernetes admission-webhook ergonomics** for the enqueue gate: `failurePolicy: Fail` as
   the default, an explicit `timeoutSeconds` (2-5 s), cheap CEL-ish `matchConditions` before the
   expensive check, an error in the match condition = reject, and idempotent mutation with an
   explicit reinvocation policy.
3. **`policyHelper` as node attestation.** It already exists, it is MDM/system-scoped only, and
   a non-zero exit **refuses to start the agent**. Ship a fleet `policyHelper` that checks node
   posture (sandbox deps present, binary hash, tags, clock skew) and refuses to boot an agent
   on a node that cannot host its role.
4. **The `allowManaged*Only` lockdown family + `disallowNonPluginCustomizations`** as the
   supply-chain control for skills/agents/hooks/MCP across the fleet, plus
   `strictKnownMarketplaces` so a node cannot install from an arbitrary marketplace.
5. **Tolerant policy parsing** (strip the bad entry, keep enforcing the rest) for fleet policy
   distribution, and **strict** parsing for node-local config.
6. **Tailscale composite role tags** rather than orthogonal tags (because tags don't AND), with
   key expiry explicitly re-enabled for worker nodes.
7. **MCP's RFC-2119 rules verbatim**: sessions are not authentication; reject tokens not issued
   for you; per-client consent to avoid the confused deputy.
8. **A Morris-II-style inline guardrail on inter-agent message bodies** — the paper reports
   TPR 1.0 / FPR 0.015, which is good enough to be a cheap second layer behind attenuation.
9. **statusline stdin as the local cost meter.** It is push-driven on every assistant message,
   costs no tokens, and carries both USD and plan-window percentage. Wire it as a *fourth
   channel* alongside sidecar/screen/process — call it the **meter channel** — with the same
   evidence discipline.
10. **`cost_usd_micros`** (integer) as the ledger unit, and `query_source` + `agent.name` +
    `skill.name` as the attribution key, so per-role budgets are computable from the same data
    the SIEM gets.
11. **Sandbox policy self-protection**: deny the agent write access to the artefacts that
    define its own policy, including symlink targets that appear at those paths after startup.

## What to avoid, and why

- **Do not enforce budgets from OTel.** 60 s metric batching, silence while blocked
  (`q4-telemetry.md:120-132`), vendor-declared approximation, and a pre-v2.1.214 inflation bug
  for multi-frame usage streams behind `ANTHROPIC_BASE_URL`. Ledger, don't gate.
- **Do not let the scheduler re-sign agent-originated tasks under its own identity.** That is
  the confused deputy, written down (MCP spec). Forward attenuated envelopes only.
- **Do not treat a node's self-reported state or self-reported budget as authority.**
  `SYNTHESIS.md:365-372` — primeline's workers report on themselves, so one that crashes before
  its first self-report is never flagged at all. Require evidence-carrying state.
- **Do not use session IDs (or tmux socket paths) as credentials.** MCP spec: "MUST NOT use
  sessions for authentication"; also this repo's sidecar is world-readable under `~/.claude`.
- **Do not schedule untrusted-content roles onto native Windows nodes** until the mesh supplies
  its own boundary — the built-in sandbox does not exist there.
- **Do not lean on `excludedCommands` or `allowUnixSockets` as if they were locked down.**
  `excludedCommands` has no managed-only lockdown by design; `/var/run/docker.sock` is a host
  escape.
- **Do not enable `--dangerously-skip-permissions` fleet-wide** (`SPEC.md:63`,
  `PITFALLS.md:141`; blocked as root, and that block is skipped inside a recognised sandbox —
  so the flag is *most* available exactly where it is least safe to combine with weak isolation).
- **Do not patch the target binary or write user-global config** to make fleet features work
  (C10; `functional-design.md:129-130`). VibeTunnel's `claude-patcher.ts` needed three regex
  variants from prior breakage.
- **Do not commit raw telemetry dumps** — PII (`q4-telemetry.md:205-207`).
- **Do not assume a USD ledger covers subscription nodes** — seat-allowance usage "isn't
  metered in dollars".
- **Do not kill a session to enforce a budget.** You pay for the turn either way and lose the
  work; refuse at `idle` instead.
- **Do not fail open on a policy-engine timeout.** K8s makes `Fail` the default for a reason.

## Open questions for the design

1. **Where does the envelope verifier run?** In the driver (so a compromised orchestrator
   cannot dispatch), or in the orchestrator (simpler, but the driver then trusts its caller)?
   The repo's philosophy — verify locally, never trust a report — argues for the driver, which
   means the driver grows a crypto dependency and the stdlib-only property
   (`README.md:53`) is at risk. **Decide explicitly; it is a stated selling point.**
2. **What is the taint propagation rule, exactly?** Does reading *any* file in a workspace taint
   the session, or only content fetched from outside the workspace? A rule that is too broad
   taints everything by turn 2 and the control becomes a no-op.
3. **Can `policyHelper` be driven from the mesh** without violating the no-global-config-writes
   rule? It must live in MDM or a system `managed-settings.json` — both outside a project. Is
   node provisioning a separate, human-authorised plane (probably yes)?
4. **Is the statusline channel usable without stealing the user's statusline?** `statusLine` is
   a single command per session and configuring it in user settings is close to a global config
   write. Options: project-scoped `statusLine`, a wrapper that chains to the user's existing
   script, or reading cost from the transcript instead. Needs an empirical probe.
5. **What is the cost of a `conflict`?** If a node in `conflict` is quarantined, an adversary
   who can induce conflicts (e.g. by forcing UI copy drift) can drain the fleet. Is there a
   rate limit or a quarantine budget?
6. **Compaction is still an unmeasured hang window** (`functional-design.md:257`) — and it is
   also an unmeasured *spend* window, since `/compact` "reads the conversation it summarizes".
   The same probe answers both; run it once.
7. **What happens to an in-flight envelope when a node's Tailscale key is revoked?** Does the
   task finish, or is there a heartbeat-bound lease? (Leases interact badly with the sidecar's
   edge-triggered timestamps — `PITFALLS.md:123-125`: staleness proves nothing.)
8. **Per-workspace quota granularity vs role count.** Workspaces are an Anthropic-side object
   with admin-console lifecycle; how many roles can the fleet have before workspace management
   becomes the bottleneck? Is there an API to create/limit them programmatically?
9. **Native-Windows confinement**: is a Job Object + AppContainer + WDAC story worth building,
   or is "Windows nodes run trusted roles only, or run inside WSL2" the honest answer?
   (The repo's Windows leg is native ConPTY precisely because WSL/tmux was avoided.)
10. **Is `hop_count` enough, or does the mesh need a per-root spend/fan-out budget** that all
    descendants draw from? The 7x agent-team multiplier suggests fan-out, not depth, is the
    cost driver.

---

## Sources

Repo (first-hand): `README.md`, `STATE.md:37`, `PITFALLS.md`, `prototypes/common/SPEC.md`,
`prototypes/{fused,scrape-driver,hook-sentinel,transcript-watch}/driver.py`,
`docs/design/functional-design.md`, `docs/discovery-session-sidecar.md`,
`docs/.research/empirical/q4-telemetry.md`, `docs/.research/prior-art/SYNTHESIS.md`.

External (fetched 2026-08-06):
- https://code.claude.com/docs/en/monitoring-usage — metric/event/span inventory, cardinality,
  identity attributes, SIEM guidance
- https://code.claude.com/docs/en/sandboxing — Seatbelt/bubblewrap/socat/seccomp, network proxy,
  `strictAllowlist`, credential mask/deny, documented security limitations
- https://code.claude.com/docs/en/settings — precedence, managed delivery, `policyHelper`,
  `allowManaged*Only`, tolerant managed parsing
- https://code.claude.com/docs/en/security — prompt-injection safeguards, `ConfigChange` audit
- https://code.claude.com/docs/en/statusline — stdin JSON schema, refresh triggers, `rate_limits`
- https://code.claude.com/docs/en/costs — `/usage`, seat allowances, workspace controls, 7x
  agent-team multiplier
- https://docs.claude.com/en/api/rate-limits — spend caps, workspace limits, ratelimit headers
- https://docs.claude.com/en/api/usage-cost-api — Admin API, ~5-minute data latency
- https://tailscale.com/kb/1068/acl-tags — tags as service accounts, composite tags, key expiry
- https://www.biscuitsec.org/docs/getting-started/introduction/ — offline attenuation
- https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/ —
  `failurePolicy`, `timeoutSeconds`, `matchConditions`, idempotent mutation
- https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices —
  confused deputy, token passthrough, session-hijack prompt injection
- https://arxiv.org/abs/2403.02817 — Morris-II self-replicating prompts, hop-count sensitivity,
  Virtual Donkey guardrail
- https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/ — workload identity (read for
  node-identity framing; not load-bearing above)
