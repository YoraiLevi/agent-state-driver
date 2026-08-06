# Transport and membership: how mesh nodes find and talk to each other

Status: research pass, 2026-08-06. Written for the fleet-mesh design (README.md, functional-design.md,
discovery-session-sidecar.md — cited as FD, README, SIDECAR below). Grounds every transport claim in a
primary source or a repo file. OBSERVED = verified against docs/changelogs/issues with dates; INFERRED =
this document's reasoning from those facts, not independently tested against the owner's tailnet.

The owner's environment (given, not researched): a live Tailscale tailnet, heterogeneous OSes (macOS
laptop, Windows desktops, Linux boxes), Tailscale SSH already in use. Every option below is evaluated
*as a layer on top of that tailnet*, not as a replacement for it — Tailscale supplies the private network;
the question is what rides on it for a) discovering peers, b) exchanging state/evidence, c) driving.

---

## Verdict

- **Tailscale is the identity and reachability layer, not the message bus.** It gives every node a stable
  private IP and a name for free, but its native pub/sub-shaped primitives (Taildrop, Funnel) are the
  wrong fit for continuous state fusion. Layer NATS (or, at smaller scale, plain HTTP+SSE) *on top of*
  Tailscale addressing — do not try to make Tailscale itself carry the mesh protocol.
- **`tailscale status --json` is a membership *hint*, never a liveness proof, for exactly the reason the
  sidecar taught us: it is state Tailscale believes, refreshed on its own schedule, not a heartbeat you
  control** — the JSON exposes `Online` per peer but that reflects the *coordination server's* view of
  the WireGuard handshake, not whether the agent process on that peer is alive. Fuse it with an
  application-level heartbeat exactly as FD section 3 fuses the sidecar with screen and process — never
  alone.
- **A node's Tailscale IP and hostname are NOT a stable identity across reinstall.** A reinstalled/
  re-authed node gets a **new node key and (observed on macOS standalone/macsys installs) a new Tailscale
  IP**, registering as a *second* device unless machine-name reuse is explicitly configured
  [github.com/tailscale/tailscale#20568]. The mesh must mint and persist its **own** node identity
  (UUID, written to local disk) independent of the tailnet's idea of the device — Tailscale's identity is
  a *credential*, not a *primary key* for our purposes.
- **tsnet (embedding Tailscale directly into the Go/Rust/Dart process) is the strongest single finding
  here**: it gives every mesh node its own tailnet identity, its own ACL tag, and its own MagicDNS name —
  with no `tailscaled` daemon, no admin rights, and no system-level config
  [tailscale.com/docs/features/tsnet; github.com/tailscale/tailscale tsnet/tsnet.go]. This is the shape
  that matches "agents coordinating themselves" — an agent process can BE a tailnet node, not merely sit
  behind one.
- **Key expiry is a fleet-lethal default, not an edge case.** Tailscale node keys expire (default policy)
  and an expired key silently drops the node's connectivity until re-authenticated
  [tailscale.com/docs/features/access-control/key-expiry]. A fleet-mesh design that doesn't either disable
  expiry for fleet nodes or build an expiry-refresh watchdog will eventually present `dead` for nodes that
  are merely locked out — a false-death class the state model in FD section 6.4 doesn't yet cover.
- **No transport surveyed gives "verified state" for free — that is still this project's job.** Every
  broker (NATS, Redis, MQTT) can tell you a connection dropped; none of them can tell you an agent is
  *busy* vs *hung* vs *waiting on a human*. The transport's contract with the state-fusion core must be:
  carry evidence-with-timestamp reliably and in order per node, and expose its OWN failure (partition,
  broker down) as a distinguishable `conflict`-class signal — never let transport silence masquerade as
  agent death, the same trap the sidecar's `statusUpdatedAt` staleness already warned against (SIDECAR
  section "How it lies," point 1).
- **SSH-as-transport (Tailscale SSH) is real but architecturally a control channel, not a bus.** It is the
  right tool for *driving* (launch/kill/one-shot command) and for bootstrap (push the mesh agent binary to
  a new node), never for the many-to-many, low-latency, ordered evidence stream the state-fusion core
  needs — one SSH exec per state-check does not scale past a handful of nodes and carries connection-setup
  latency the design's own latency table (FD section 3, hooks ~5-20ms) would never accept for a
  local channel.
- **File-based transport over a synced directory is worth exactly one role: durable audit log / cold
  handoff, not live coordination.** Taildrop is peer-to-peer, user-initiated, and has no daemon-mode
  push API for continuous small messages [see Findings 7] — it is not a channel a supervisor polls at
  sub-second latency.

---

## Findings

### 1. Tailscale as substrate: what's real, what's marketing

**MagicDNS.** Every device gets `hostname.tailnet-name.ts.net`, resolved by an in-tailnet DNS server built
into the client; no separate nameserver required since v1.20
[tailscale.com/docs/features/magicdns]. The tailnet name itself is either a random
`word-word.ts.net` (default for personal accounts, generated once and shown in the admin console) or an
org-controlled name (`tailscale.com/docs/concepts/tailnet-name`). **Stability**: the name is stable *per
tailnet*, not per device across a device's lifecycle — see Finding 3 on node identity for why the device
side is the weaker link.

**Tags and grants/ACLs.** Tags (`tag:fleet-worker`) attach to a *device*, not a user, and are the unit
ACLs/grants select on [tailscale.com/docs/features/tags]. Grants are the current (GA since 2025) syntax,
replacing raw ACL rules, deny-by-default: `{"src": ["autogroup:member"], "dst": ["tag:golink"], "ip":
["*"]}` [tailscale.com/blog/grants-ga]. **For the fleet**: tag every mesh node at provisioning
(`tag:mesh-worker`, `tag:mesh-coordinator`) and write grants keyed on those tags — this is a real,
enforced-at-the-network-layer authorization boundary the mesh gets without writing any auth code itself,
which is a meaningfully different security posture than any of the message brokers below (all of which
need their own auth layered on top).

**tsnet — embedding a node in-process.** `tailscale.com/tsnet` is a Go package: "embeds a Tailscale node
directly into a Go program, allowing it to join a tailnet and accept or dial connections without running a
separate tailscaled daemon or requiring any system-level configuration"
[github.com/tailscale/tailscale/blob/main/tsnet/tsnet.go, package doc]. It runs a **userspace TCP/IP
stack (gVisor)**, not the OS TUN/TAP driver [pkg.go.dev/tailscale.com/tsnet], which is exactly why it
needs no admin/root: the "device" is the process, and it dials/accepts directly on the tailnet without
touching the host network stack [jnsgr.uk/2024/08/tailscale-on-the-rocks — corroborating, independent
source]. There is a Rust binding via `libtailscale`/the `tsnet` crate [docs.rs/crate/tsnet] and a
Dart/Flutter binding exposing the same primitives (HTTP/TCP/UDP/TLS/Serve/Funnel/prefs/exit-nodes)
[pub.dev/packages/tailscale] — so this is not Go-only. **Design implication**: a Python-based agent driver
(this project's language) does not get tsnet natively; embedding would require either shelling to a small
Go/Rust sidecar tsnet binary or FFI into `libtailscale`. That's a real cost the design must price in, not
assume away.

**`tailscale status --json`.** Documented as suited for automation specifically *because* the table form
isn't: "gives a detailed list of peers and users in your tailnet" [tailscale.com/docs/reference/tailscale-cli].
The changelog records the JSON schema is still evolving: "tailscale status --json now shows Tags and
PrimaryRoutes for Peers" (a dated addition, not always-present fields)
[tailscale.com/changelog]. Fields include per-peer `Online` (bool), `TailscaleIPs`, `Tags`,
`LastSeen`/handshake-derived data (schema defined in `tailcfg.go`/`ipnstate` packages
[github.com/tailscale/tailscale tailcfg/tailcfg.go; pkg.go.dev/tailscale.com/ipn/ipnstate]). **What this
proves**: whether the *coordination plane* believes a WireGuard handshake with that peer is current.
**What it does not prove**: whether the agent process on that peer is running, busy, or dead — the same
gap this project already solved once for the Claude Code sidecar (SIDECAR: "edge-triggered, NOT a
heartbeat"). Treat `tailscale status --json` exactly the way FD's fusion rule treats the sidecar: a fast,
free, *corroborating* membership signal, never sufficient alone, and re-poll it (it's a local CLI call
against the running `tailscaled`, so it's cheap — no network round-trip per query).

**Funnel and Serve.** Serve exposes a local port to the tailnet only; Funnel exposes it to the public
internet, gated on `tailscale.com/blog/reintroducing-serve-funnel`. Funnel is **capped by a non-configurable
bandwidth limit**, works only on **ports 443/8443/10000 over TLS**, requires MagicDNS + HTTPS enabled +
Tailscale v1.38.3+ [tailscale.com/docs/features/tailscale-funnel; docs.openclaw.ai/gateway/tailscale
independently confirming the three-port restriction]. **On macOS specifically Funnel requires an
open-source client variant**, not the App Store build [tailscale.com/docs/features/tailscale-funnel]. Serve
and Funnel cannot both bind the same port simultaneously. **Relevance to this design**: Funnel is
irrelevant (the fleet is private, tailnet-only by design) but Serve is a legitimate way to expose one
node's HTTP+SSE state-fusion endpoint to the rest of the tailnet without hand-managing certs — Tailscale
issues the HTTPS cert automatically for `*.ts.net` names.

**Taildrop.** Peer-to-peer file transfer, user- or CLI-triggered (`tailscale file cp`), not a persistent
push channel — no researcher source in this pass found a daemon-mode "watch and auto-receive small
messages" primitive; it is designed for discrete file handoffs, not a message bus. Rule it out for live
state exchange; it's a candidate only for the "ship the driver binary to a newly-joined node" bootstrap
step (Finding 8 revisits this).

### 2. Node/agent identity — what survives restart, re-IP, reinstall

Tailscale's own identity primitive is the **node key**, generated at `tailscale up`/re-auth and rotated
automatically by default; disconnecting/expiring invalidates it
[tailscale.com/docs/features/access-control/key-expiry]. Two failure classes matter for a fleet that must
name things durably:

- **Key expiry (routine).** Default tailnets expire keys on a policy interval; an expired key stops that
  device from establishing new connections until re-authenticated — existing sessions may persist briefly
  but new ones fail [tailscale.com/docs/features/access-control/key-expiry]. Ephemeral/pre-auth keys have
  their own separate short-lived semantics for CI-style nodes [tailscale.com/docs/features/ephemeral-nodes].
  **This is disableable per-device** ("Disable key expiry" in the admin console, referenced across setup
  guides) — the fleet MUST do this for every mesh node, or build a key-refresh watchdog, or the mesh will
  intermittently and silently lose nodes to an unrelated auth mechanism, not to any state the driver
  detects.
- **Reinstall/re-auth (structural).** A live, filed bug documents a macOS standalone/macsys install
  **re-registering as a brand-new device — new node key, new Tailscale IP, no interactive re-login required
  in the reported case** [github.com/tailscale/tailscale/issues/20568, opened 2026-07-21, open at time of
  writing]. A second, separate report on Linux/Raspbian shows manual reinstall-plus-authkey producing an
  "unable to re-authenticate" state requiring the old device be manually removed from the tailnet first
  [github.com/tailscale/tailscale/issues/9382]. **Neither the IP nor the device's Tailscale-assigned
  identity is a safe long-term primary key.** The stable anchor Tailscale does offer is the **machine
  name** users can pin in the admin console independent of the underlying node key
  [tailscale.com/docs/concepts/machine-names] — but that still requires the operator (or an
  API-driving script) to reconcile "new node key, same intended machine" by hand or via the Tailscale
  admin API; it is not automatic.

**Design consequence.** Mint a mesh-level identity (a UUID or a `hostname+first-boot-timestamp` composite,
written once to local disk at first run, analogous to how Claude Code's sidecar is looked up by
`sessionId` and never by PID per SIDECAR's guard 3) and persist it independent of Tailscale. Use the
Tailscale **tag** as the authorization anchor (tags survive reinstall if the admin/API re-applies them at
enrollment) and the mesh's own identity file as the addressing/state anchor. Never key durable fleet state
(the roster, evidence history) off `TailscaleIPs` or the node key — both are observed to churn.

### 3. Message transports, evaluated

For each: what it is, cross-platform reality, operational weight, partition/failure semantics, join/leave.

**NATS + JetStream.**
- *What.* Lightweight pub/sub broker (`nats-server`), single static binary; JetStream is its built-in
  persistence layer, opt-in per stream (`-js` flag), giving at-least-once delivery, replay, and durable
  consumers that track per-client progress server-side [docs.nats.io/concepts/jetstream;
  docs.nats.io/reference/jetstream]. Auth is decentralized via NKeys (Ed25519 keypairs, no shared secret)
  and JWTs signed in an operator→account→user chain [docs.nats.io/learn/security/decentralized-auth;
  docs.nats.io/running-a-nats-service/nats_admin/jwt] — this maps cleanly onto per-agent identity if the
  mesh wants cryptographic node identity independent of Tailscale.
- *Cross-platform.* `nats-server` ships and documents a native Windows service install path (`nats-server
  service create`, no WSL) [github.com/nats-io/nats.docs windows_srv.md]. Genuinely first-class on all
  three target OSes; this is the strongest cross-platform story of any broker surveyed here.
- *Operational weight.* One binary, no external dependency (no Zookeeper-class coordinator); JetStream
  clustering wants 3 or 5 nodes for fault tolerance against 1-2 simultaneous server failures (quorum = ⌊n/2⌋+1)
  [docs.nats.io/running-a-nats-service/configuration/clustering/jetstream_clustering]. A single-server
  JetStream instance (no clustering) is a **single point of failure** for persistence — acceptable for a
  first fleet build, a declared limitation for GA.
  A third-party Jepsen analysis of NATS 2.12.1 exists and specifically exercised network partitions against
  JetStream's at-least-once guarantee [jepsen.io/analyses/nats-2.12.1, Dec 2025] — worth reading in full
  before committing to JetStream's consistency claims under partition; this document did not extract its
  verdict, only confirms the analysis exists and is recent.
- *Partition semantics.* Core NATS (no JetStream) is fire-and-forget: a subscriber that's down when a
  message publishes simply never sees it [james-carr.org, corroborating the docs' framing]. JetStream adds
  durability but core NATS queue-groups/JetStream consumer distribution is explicitly **"partition-less and
  non-deterministic"** for ordering across multiple subscribers on the same subject
  [docs.nats.io/nats-concepts/subject_mapping] — if the mesh needs strict per-node ordering of evidence
  events, that must be enforced by subject design (one subject per node) rather than assumed from the
  broker.
- *Join/leave.* A new node just connects and subscribes/publishes on its own subject namespace
  (`fleet.node.<id>.state`) — no broker-side registration step beyond auth. Leaving is implicit
  (connection drop); JetStream durable consumers remember position so a reconnecting node resumes cleanly.

**Redis Streams.**
- *What.* An append-only log data type inside Redis with consumer-group semantics: `XREADGROUP` delivers
  to one consumer in a group, tracked in a per-consumer Pending Entries List (PEL); `XACK` clears it;
  `XCLAIM`/`XAUTOCLAIM` let a live consumer take over another consumer's un-acked, timed-out entries
  [redis.io/docs streams docs; redis.io/docs/commands/xclaim]. This consumer-failure-recovery shape is a
  near-exact structural match for this project's own `presumed_hung`→reassignment pattern (FD section 2)
  — a busy worker that goes silent leaves its pending work claimable by a healthy peer.
- *Cross-platform.* Redis itself is a server process; native Windows support is via Microsoft's WSL-based
  or community ports, not a first-party Windows binary from Redis Ltd — this is a real asterisk (not
  independently confirmed in this pass beyond general knowledge; flagged as a gap, see Open Questions).
  Client libraries are cross-platform (stackexchange.Redis, redis-py, ioredis) regardless of server
  hosting.
- *Operational weight.* Requires a running Redis instance; single-instance Redis is again an SPOF for
  stream data unless Sentinel/Cluster is added, which is meaningfully more operational surface.
- *Partition semantics.* No native multi-node partitioning of a single stream (`XADD`/`XREAD` targets one
  key on one instance); horizontal scale is achieved by the application sharding streams across keys/
  instances, not by Redis Streams itself [several sources above note "Redis doesn't handle partition
  management the way Kafka does"].
- *Join/leave.* A consumer group is created once (`XGROUP CREATE`); a new node names itself a new
  consumer in that group and starts reading — cheap, no broker restart needed.

**MQTT (e.g. Mosquitto).**
- *What.* Lightweight pub/sub over a broker, purpose-built for presence: **Last Will and Testament (LWT)**
  — a client registers a message-on-death at CONNECT time; if it disconnects **ungracefully**, the broker
  publishes that message on its behalf [hivemq.com LWT explainer; vernemq.com LWT primer explicitly calling
  out "track...presence status of participating devices" as the intended use]. QoS 0/1/2 tunes
  delivery guarantees per message. This is the one transport surveyed whose core primitive is *designed*
  for the "did this node vanish" question the fleet cares about.
- *Cross-platform.* Mosquitto ships native Windows binaries; it is a small, dependency-light C broker
  (~120KB, ~3MB RAM for 1000 clients per one source [devopedia.org/mqtt]) — light enough to run on any
  fleet node itself if a central broker host is undesired.
- *Operational weight.* Lowest of the broker options — a single small binary, minimal config
  (`mosquitto.conf`).
- *Partition semantics.* **LWT's failure mode is exactly the false-positive class this project has already
  fought once**: LWT fires on ungraceful TCP disconnect (broker-observed), which is a *reachability*
  signal, not a *liveness* signal — a node that's alive but network-partitioned from the broker triggers
  the same "died" message as a node that actually crashed. This is architecturally identical to the
  sidecar's SIGKILL-vs-clean-exit ambiguity (SIDECAR point 2) except MQTT's LWT can't even distinguish the
  two — it fires the same will either way. A design leaning on LWT for `dead` detection must still gate on
  an out-of-band liveness check (Tailscale peer `Online` + process check) exactly as FD's process channel
  is mandated to override every other signal for `dead` (FD section 3, fusion rule 3).
- *Join/leave.* Trivial — connect, subscribe/publish on a topic; QoS 1/2 with a persistent session lets a
  reconnecting client resume without re-subscribing.

**HTTP + Server-Sent Events (SSE).**
- *What.* No broker: each node runs a small HTTP server; a coordinator (or any peer) opens a long-lived
  GET and receives a stream of state events. This is the shape closest to the OTel/stream-json channels
  already characterized in FD (push, ordered, per-connection).
- *Cross-platform.* Trivially cross-platform — stdlib HTTP servers exist in every language on every OS;
  this project's own drivers are explicitly "stdlib-only Python 3.9+" (README) and SSE needs nothing
  beyond that.
- *Operational weight.* Lowest of any option in this document — no broker process, no cluster, one port
  per node. Combine with Tailscale Serve (Finding 1) to get automatic HTTPS with zero cert management.
- *Partition semantics.* Point-to-point: if the connection drops, the coordinator's *only* signal is "my
  connection to node X is gone" — which is the same reachability-vs-liveness ambiguity as MQTT's LWT, but
  now without even a will message; the consumer must reconnect and re-poll `state`. No fan-out: N
  coordinators watching one node means N independent HTTP connections to that node, which doesn't scale
  past a small coordinator count without an intermediary.
- *Join/leave.* A new node just needs coordinators to know its `hostname.tailnet.ts.net:port` — which is
  exactly the membership-discovery problem `tailscale status --json` (Finding 1) or a lightweight registry
  service can answer.

**gRPC.**
- *What.* HTTP/2-based typed RPC with built-in bidirectional streaming and keepalive pings that detect a
  dead peer connection by timing out unacknowledged HTTP/2 PING frames
  [grpc.io/docs/guides/keepalive; github.com/grpc/grpc/blob/master/doc/keepalive.md].
- *Cross-platform reality — the sharpest finding in this section.* **`Grpc.Net.Client` (the modern .NET
  gRPC client) does not support HTTP/2 on Windows 10 with .NET Framework; only Windows 11 is supported for
  that path** [github.com/dotnet/core/issues/8094, and independently confirmed by
  learn.microsoft.com/aspnet/core/grpc/netstandard: "gRPC requires extra configuration to make RPC calls
  on .NET implementations that don't have support for gRPC over HTTP/2"]. This is specific to the .NET
  ecosystem's HTTP/2 stack, not gRPC-the-protocol — Go, Python, and Node gRPC implementations carry their
  own HTTP/2 stacks and don't inherit this limitation — but it is a concrete trap if any Windows tooling in
  this fleet ends up written in C#/.NET Framework (a real possibility given the owner's Windows desktops).
  gRPC-core itself **does build on Windows via CMake/Bazel** across all three OSes
  [github.com/grpc/grpc/blob/master/BUILDING.md] — so native Go/Python/Rust gRPC on Windows is fine; the
  landmine is specifically the older .NET Framework HTTP/2 story.
- *Operational weight.* No broker — direct connections, like HTTP+SSE, but with generated typed stubs
  (protobuf), which buys strong contracts at the cost of a build step per language/platform.
- *Partition semantics.* Keepalive pings detect a half-open connection faster than TCP's own timeouts, and
  a failed streaming RPC surfaces as an explicit `Unavailable` error rather than silent hang — a genuinely
  better story than plain HTTP+SSE for surfacing "the transport itself broke" as a distinguishable signal,
  which is exactly the `conflict`-vs-silent-misdetection distinction this project's fusion rules already
  insist on (FD section 3, fusion rule 5).
- *Join/leave.* Same discovery problem as HTTP+SSE — needs an address book, not solved by gRPC itself.
  No native fan-out; a full mesh of N nodes wanting each other's state needs N² connections or a hub.

**SSH-as-transport (Tailscale SSH specifically).**
- *What.* Tailscale SSH replaces key management with WireGuard-authenticated, ACL-gated SSH — "Tailscale
  uses netstack port interception and just-in-time...configuration of the client known_hosts file to make
  `ssh myhost` work without any new binary or configuration file"
  [tailscale.com/docs/features/tailscale-ssh]. Independent latency data: **direct peer-to-peer SSH over
  Tailscale adds roughly 1-3ms WireGuard overhead**, versus 5-15ms for a proxy-based system like Teleport
  [onidel.com/zero-trust-ssh-vps-2025] — genuinely low latency for a single exec.
  Access is governed by a **separate authorization layer** — the tailnet policy's `ssh` rules — layered on
  top of network-level grants [agentpedia.codes remote-coding-agents guide, corroborating the two-layer
  model: network ACL decides reachability, SSH policy decides login].
- *Cross-platform.* Works wherever the Tailscale client and an SSH-capable shell exist — native on all
  three target OSes (Windows via the Tailscale Windows client + its built-in SSH server support,
  documented across setup guides though not independently deep-verified in this pass).
- *Operational weight.* Zero extra infrastructure beyond what's already running (README already states the
  owner uses Tailscale SSH) — the cheapest possible channel to add for *driving*, not for continuous
  telemetry.
- *Partition semantics.* Each command is a fresh (or multiplexed) session; a network partition simply
  fails the connection attempt — clean, unambiguous failure, no silent staleness trap. But it is
  fundamentally request/response, not a subscribable stream: polling agent state over SSH means opening a
  session (or keeping one multiplexed pty open) per poll interval per node, which is exactly the
  1-second-poll-per-node cost this project's screen channel already pays locally (FD section 3, "poll-bound,
  1s") — multiplied across a fleet, that's N SSH round-trips per tick, a cost none of the broker/HTTP
  options carry.
- *Join/leave.* A new node needs no registration with an SSH-transport scheme beyond being on the tailnet
  and covered by the `ssh` ACL rule — arguably the lowest-friction join of any option here, precisely
  because Tailscale already solved it.

**File-based transport over a synced directory (Taildrop or otherwise).**
- *What.* Nodes write/read state files in a shared location, relying on a sync mechanism (Taildrop,
  Dropbox-class tool, or a network filesystem) to propagate them. Taildrop specifically is peer-to-peer,
  user- or CLI-triggered file transfer [general Tailscale docs, corroborated by every setup guide
  surveyed] — no evidence found in this pass of a Taildrop daemon mode that watches a directory and
  auto-pushes on every write, the behavior continuous state-sharing would need.
- *Cross-platform.* File I/O is universally available; the weak link is the *sync* mechanism, which is
  transport-specific (Taildrop transfers are discrete, one-shot; a real synced-folder tool like Syncthing
  would need its own evaluation, out of scope here since it wasn't in the brief's option list).
- *Operational weight.* Conceptually the lightest — "just files" — but this project's own transcript-
  watching channel (FD section 3, TR row) already demonstrates the failure mode: file-based signals are
  **FS-watch-bound, not push**, and every field is reverse-engineered/undocumented when the format isn't
  owned by this project.
- *Partition semantics.* Worst of any option surveyed: a sync failure is invisible at the file layer — a
  stale file looks identical to a file that was never updated because the writer is dead, precisely the
  ambiguity the sidecar's "stale ≠ dead, gate on `kill -0`" rule exists to prevent (SIDECAR point 2), except
  here there is no equivalent liveness gate available at all without an independent channel.
- *Join/leave.* Trivial in principle (a new node just starts writing to the shared location) but silent
  in practice — nothing tells existing readers a new file appeared except their own poll.

### 4. What the transport owes the state-fusion core

This project's hardest-won principle (FD sections 3 and 6, README's "It refuses to guess") is that a
consumer must be able to distinguish "the signal says X" from "the signal went silent," and must never let
silence be read as a state. Every transport surveyed above reproduces some version of this trap at the
network layer: Tailscale's peer `Online` bit, MQTT's LWT, gRPC's keepalive timeout, and a stale file all
answer "is the connection to this node currently up," which is a **reachability** claim, not the
**liveness** claim the fleet needs. The design must treat transport-level connectivity exactly as FD
treats the screen channel: an always-available floor that corroborates, never a sole source of truth for
`dead`. The process/PID channel's supremacy rule (FD fusion rule 3: "Process channel overrides everything
for `dead`") does not have an equivalent at fleet scale yet — cross-machine, there is no local PID to
check, and this is the load-bearing open question this document surfaces (Open questions, below).

---

## What to steal

- **tsnet's shape**: an agent process that IS a tailnet node, with its own tag, own MagicDNS name, no
  daemon. If the driver language can embed it (directly in Go/Rust, or via a slim sidecar for Python),
  this collapses "join the mesh" and "get a private, ACL'd address" into one step with zero admin
  privilege required.
- **MQTT's LWT concept, reframed**: not as the liveness answer, but as a cheap, standard, broker-enforced
  "this connection just dropped" event to feed into the fusion layer as one more piece of *evidence* — same
  epistemic status as the sidecar's `waitingFor` literal: useful, never sufficient alone.
- **Redis Streams' consumer-group PEL/XCLAIM pattern** as a literal design for work reassignment when a
  fleet worker goes `presumed_hung`: a healthy peer claiming another's stalled work item is precisely the
  shape a role-based mesh needs for self-healing, and it is a shipped, well-understood primitive rather
  than something to invent.
- **Tags + grants as the authorization boundary**, done once at the network layer, instead of building a
  parallel auth system inside whichever message transport is chosen. Every broker surveyed needs its own
  auth (NKeys/JWT for NATS, ACLs for MQTT, ACLs for Redis) — Tailscale's grants can gate *reachability*
  before any of that even runs, a defense-in-depth layer none of the brokers give by themselves.
- **JetStream's durable-consumer model** for the audit/evidence trail specifically: at-least-once,
  replayable, server-tracked position — a good match for "prove what state we observed and when," which is
  this project's entire differentiator, extended to fleet scale.

## What to avoid and why

- **Do not build fleet membership on `tailscale status --json` alone.** It's free and fast, but it answers
  "does the coordination server think a handshake happened," not "is the agent process alive" — the exact
  category error this project already spent an entire discovery doc correcting for the sidecar
  (SIDECAR "How it lies," point 1). Treat it as one evidence channel among several.
- **Do not use Taildrop, or any bare synced-directory scheme, for continuous state.** Neither has a
  push-on-write daemon mode confirmed in this pass; both degrade to slow polling with no liveness signal
  at all, worse than every broker option surveyed.
- **Do not let SSH-as-transport become the state-polling loop.** It's the right tool for driving
  (launch/kill/bootstrap) and for one-shot commands, wrong for a many-node, sub-second-latency stream — the
  per-session overhead compounds linearly with fleet size and poll frequency.
- **Do not assume gRPC's Windows story is uniform across languages.** The .NET Framework HTTP/2 gap
  (github.com/dotnet/core#8094) is real and specific; if any part of the fleet tooling targets Windows via
  .NET rather than Go/Python/Rust, this is a concrete blocker to test before committing to gRPC.
  Node/Python/Go gRPC clients on native Windows do not carry this specific limitation.
- **Do not treat a single JetStream or Redis instance as fleet-durable without clustering.** Both are
  single points of failure for the evidence history in their default single-node configuration; the
  quorum math for JetStream clustering (⌊n/2⌋+1 of 3 or 5) is documented and should be the baseline for
  any deployment the owner intends to trust.
- **Do not leave Tailscale key expiry enabled on fleet nodes without a refresh mechanism.** It is a
  routine, dated, self-inflicted `dead`-looking failure mode this project's own state model doesn't yet
  name (Open questions, below) — indistinguishable from a real hang unless the design accounts for it
  explicitly.

## Open questions for the design

- **What is the fleet-scale equivalent of "process channel overrides everything for `dead`" (FD fusion
  rule 3)?** Locally, `kill -0 <pid>` is unambiguous. Across machines there is no local PID to check —
  candidates are (a) SSH-exec a liveness probe on demand (costs latency, see Findings), (b) trust the
  target node's own transport-layer heartbeat (re-introduces the reachability-vs-liveness ambiguity this
  document flags repeatedly), or (c) a lightweight always-on companion process per node whose sole job is
  answering "is the agent process alive" over the chosen transport — effectively porting the sidecar
  pattern to fleet scale. This wants its own design pass, not a default answer here.
- **Does the mesh need one transport or two?** A plausible split: NATS/JetStream (or MQTT) for the
  continuous evidence stream + roster, and Tailscale SSH for driving/bootstrap/emergency access — never
  merging the two roles onto one channel. Worth deciding explicitly rather than defaulting into it.
- **Redis on native Windows** — this document flagged a gap (no first-party Windows server binary
  confirmed) rather than verifying it; settle with a direct install attempt on one of the owner's Windows
  desktops before any Redis-Streams commitment.
- **Should node identity be self-minted (UUID at first boot) or derived from something Tailscale-stable
  like the machine name?** Machine names can be pinned in the admin console independent of node-key churn
  [tailscale.com/docs/concepts/machine-names] but that pinning is a manual/admin-API step, not automatic on
  reinstall — decide whether the mesh's bootstrap flow re-applies the pin itself or requires an operator to.
- **What does "role" mean at the transport layer?** The brief specifies a configurable mesh with roles, not
  a fixed hierarchy — none of the transports surveyed have a native concept of role beyond pub/sub topic
  naming conventions (`fleet.role.coordinator.*`) or NATS subject hierarchies. Whether roles are enforced
  by tag+grant (network layer), by subject-naming convention (transport layer), or by the application
  logic reading evidence is an open architectural choice this document did not resolve.
- **Jepsen's NATS 2.12.1 report** [jepsen.io/analyses/nats-2.12.1] was found but not read in full for this
  pass — its specific partition-tolerance findings for JetStream should be read before JetStream is
  adopted as the durability layer for fleet evidence.

---

## Sources

- tsnet: https://tailscale.com/docs/features/tsnet ·
  https://github.com/tailscale/tailscale/blob/main/tsnet/tsnet.go ·
  https://pkg.go.dev/tailscale.com/tsnet · https://docs.rs/crate/tsnet/latest ·
  https://pub.dev/packages/tailscale · https://jnsgr.uk/2024/08/tailscale-on-the-rocks/
- MagicDNS / tailnet names: https://tailscale.com/docs/features/magicdns ·
  https://tailscale.com/docs/concepts/tailnet-name · https://tailscale.com/blog/magicdns
- Tags / grants / ACLs: https://tailscale.com/docs/features/tags ·
  https://tailscale.com/docs/reference/syntax/grants · https://tailscale.com/blog/grants-ga ·
  https://tailscale.com/docs/reference/syntax/policy-file
- `tailscale status --json`: https://tailscale.com/docs/reference/tailscale-cli ·
  https://tailscale.com/changelog · https://github.com/tailscale/tailscale/blob/main/tailcfg/tailcfg.go ·
  https://pkg.go.dev/tailscale.com/ipn/ipnstate
- Funnel / Serve: https://tailscale.com/docs/features/tailscale-funnel ·
  https://tailscale.com/docs/features/tailscale-serve ·
  https://tailscale.com/blog/reintroducing-serve-funnel · https://docs.openclaw.ai/gateway/tailscale
- Identity/key churn: https://github.com/tailscale/tailscale/issues/20568 ·
  https://github.com/tailscale/tailscale/issues/9382 ·
  https://tailscale.com/docs/features/access-control/key-expiry ·
  https://tailscale.com/docs/features/ephemeral-nodes · https://tailscale.com/docs/concepts/machine-names
- Tailscale SSH: https://tailscale.com/docs/features/tailscale-ssh ·
  https://onidel.com/zero-trust-ssh-vps-2025/ · https://agentpedia.codes/blog/remote-coding-agents-termius-tailscale-tmux-guide
- NATS/JetStream: https://docs.nats.io/concepts/jetstream · https://docs.nats.io/reference/jetstream/ ·
  https://github.com/nats-io/nats.docs/blob/master/running-a-nats-service/running/windows_srv.md ·
  https://docs.nats.io/running-a-nats-service/configuration/clustering/jetstream_clustering ·
  https://docs.nats.io/nats-concepts/subject_mapping · https://jepsen.io/analyses/nats-2.12.1 ·
  https://docs.nats.io/learn/security/decentralized-auth ·
  https://docs.nats.io/running-a-nats-service/nats_admin/jwt
- Redis Streams: https://redis.io/docs/latest/develop/data-types/streams/ ·
  https://redis.io/docs/latest/commands/xclaim/ · https://redis.io/docs/latest/commands/xack/ ·
  https://redis.antirez.com/fundamental/streams-consumer-patterns.html
- MQTT: https://www.hivemq.com/blog/mqtt-essentials-part-9-last-will-and-testament/ ·
  https://vernemq.com/intro/mqtt-primer/last_will_testament.html · https://devopedia.org/mqtt
- gRPC: https://grpc.io/docs/guides/keepalive/ · https://github.com/grpc/grpc/blob/master/doc/keepalive.md ·
  https://github.com/dotnet/core/issues/8094 ·
  https://learn.microsoft.com/en-us/aspnet/core/grpc/netstandard?view=aspnetcore-8.0 ·
  https://github.com/grpc/grpc/blob/master/BUILDING.md
- Repo context: README.md, docs/design/functional-design.md,
  docs/discovery-session-sidecar.md, docs/.research/prior-art/SYNTHESIS.md (all in this repo)
