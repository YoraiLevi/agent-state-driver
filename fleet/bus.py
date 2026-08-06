#!/usr/bin/env python3
"""Bus — signed state edges, and the replay that reconstructs history from them.

    uv run fleet/bus.py keygen                 # mint this node's signing key
    uv run fleet/bus.py replay [--strict]      # rebuild every agent's history
    uv run fleet/bus.py verify                 # signatures only

WHAT AN EDGE IS FOR
-------------------
A consumer that joins late, or restarts, or was partitioned, must be able to
reconstruct exactly what each agent did — without asking the agent, and without
trusting whoever hands it the stream. Two fields carry that weight:

    seq   monotone per (node, agent). The transport cannot give us ordering:
          NATS' consumer distribution across subscribers on one subject is
          explicitly "partition-less and non-deterministic".
    prev  the state this edge moved AWAY from. A dropped edge is therefore
          DETECTABLE — `prev` will not chain — rather than silently absorbed
          into a plausible-looking history.

`prev` is the difference between "I have a history" and "I have the history I
was given". Every surveyed presence system has the former.

SIGNING HAPPENS HERE, NOT IN THE DRIVER
---------------------------------------
The driver stays stdlib-only and unsigned by design — that is what makes it
droppable onto a strange machine. The Warden already holds a node identity, so
the attestation belongs exactly at the machine boundary: local pipe unsigned,
anything crossing the network signed.

If the signing dependency is absent, edges are emitted with `sig: null` and
`sig_alg: "none"` — and `replay --strict` REFUSES them. Silently degrading
crypto is worse than not having it, because it looks like it worked.

THE SINK IS PLUGGABLE ON PURPOSE
--------------------------------
Default is an append-only local journal, which needs no infrastructure and is
enough to develop and test the whole spine. A NATS/JetStream adapter is the
intended production sink (durable, replayable, subject-per-node). The SHAPE of
an edge is the contract; the destination is a deployment choice, and keeping it
swappable means the broker decision stays reversible.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import warden  # noqa: E402

try:                                        # optional: fleet extra
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey)
    from cryptography.hazmat.primitives import serialization
    HAVE_CRYPTO = True
except ImportError:                         # degrade LOUDLY, never silently
    HAVE_CRYPTO = False


# --------------------------------------------------------------------------
# keys
# --------------------------------------------------------------------------

def key_path() -> Path:
    return warden.state_root() / "node.key"


def pub_path() -> Path:
    return warden.state_root() / "node.pub"


def ensure_key():
    """-> (private_or_None, public_hex_or_None). Idempotent."""
    if not HAVE_CRYPTO:
        return None, None
    if key_path().exists():
        priv = serialization.load_pem_private_key(key_path().read_bytes(), password=None)
    else:
        priv = Ed25519PrivateKey.generate()
        key_path().parent.mkdir(parents=True, exist_ok=True)
        key_path().write_bytes(priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()))
        os.chmod(key_path(), 0o600)
    raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    pub_path().write_text(raw.hex())
    return priv, raw.hex()


def signing_payload(edge: dict) -> bytes:
    """Exactly the fields that are signed, in a canonical order.

    `sig` and `sig_alg` are excluded (they are the signature), and so is
    `published_at` (set by the sink after signing). Everything a consumer makes a
    decision on must be inside this payload — otherwise it is not attested.
    """
    signed = {k: edge[k] for k in sorted(edge)
              if k not in ("sig", "sig_alg", "published_at", "pubkey")}
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()


def sign(edge: dict) -> dict:
    priv, pub = ensure_key()
    if priv is None:
        edge["sig"], edge["sig_alg"] = None, "none"
        return edge
    edge["sig"] = priv.sign(signing_payload(edge)).hex()
    edge["sig_alg"] = "ed25519"
    edge["pubkey"] = pub
    return edge


def verify_edge(edge: dict):
    """-> (ok: bool, why: str)."""
    alg = edge.get("sig_alg")
    if alg in (None, "none"):
        return False, "unsigned"
    if not HAVE_CRYPTO:
        return False, "signed edge but no verifier available (install the fleet extra)"
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(edge["pubkey"]))
        pub.verify(bytes.fromhex(edge["sig"]), signing_payload(edge))
        return True, "ok"
    except Exception as e:                  # any failure is a rejection
        return False, "bad signature: %s" % type(e).__name__


# --------------------------------------------------------------------------
# sinks
# --------------------------------------------------------------------------

class JournalSink:
    """Append-only local file. No infrastructure; enough to develop the spine."""

    name = "journal"

    def __init__(self, path=None):
        self.path = Path(path) if path else warden.state_root() / "edges.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, edge: dict):
        edge = sign(edge)
        edge["published_at"] = time.time()
        with open(self.path, "a") as fh:
            fh.write(json.dumps(edge) + "\n")
        return edge

    def read(self):
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"__corrupt__": line[:120]})
        return out


def get_sink(url=None):
    """Sink factory. `nats://…` is the intended production sink; it is not
    implemented here on purpose — the decision to take an infrastructure
    dependency is the operator's, and the edge shape does not change."""
    url = url or os.environ.get("FLEET_BUS", "journal")
    if url.startswith("nats://"):
        raise SystemExit(json.dumps({
            "error": "NATS sink not implemented yet",
            "note": "the edge shape is unchanged; see docs/design/fleet-architecture.md",
            "url": url}))
    return JournalSink()


# --------------------------------------------------------------------------
# replay — the acceptance test's subject
# --------------------------------------------------------------------------

def replay(edges, strict=False):
    """Reconstruct per-agent history and report every integrity failure.

    Returns {agents: {sid: {history, current, ...}}, problems: [...]}.
    A problem is never silently repaired: the whole point of `prev` and `seq` is
    that a gap is visible.
    """
    agents, problems = {}, []
    for i, e in enumerate(edges):
        if "__corrupt__" in e:
            problems.append({"i": i, "kind": "corrupt_line", "detail": e["__corrupt__"]})
            continue
        ok, why = verify_edge(e)
        if not ok:
            problems.append({"i": i, "kind": "signature", "detail": why,
                             "session_id": e.get("session_id")})
            if strict:
                continue                    # a rejected edge must not enter history
        sid = e.get("session_id")
        a = agents.setdefault(sid, {"session_id": sid, "node": e.get("node"),
                                    "name": e.get("name"), "history": [],
                                    "current": None, "last_seq": 0})
        seq, prev, st = e.get("seq"), e.get("prev"), e.get("state")
        if seq != a["last_seq"] + 1:
            problems.append({"i": i, "kind": "seq_gap", "session_id": sid,
                             "expected": a["last_seq"] + 1, "got": seq,
                             "detail": "an edge is missing or duplicated"})
        if prev != a["current"]:
            problems.append({"i": i, "kind": "prev_mismatch", "session_id": sid,
                             "expected_prev": a["current"], "got_prev": prev,
                             "detail": "history does not chain — an edge was dropped"})
        a["history"].append({"seq": seq, "state": st,
                             "at": e.get("observed_at"),
                             "evidence": [ev.get("channel")
                                          for ev in e.get("evidence", [])]})
        a["current"] = st
        a["last_seq"] = seq if isinstance(seq, int) else a["last_seq"]
    return {"agents": agents, "problems": problems}


# --------------------------------------------------------------------------

def cmd_keygen(a):
    if not HAVE_CRYPTO:
        print(json.dumps({"error": "signing unavailable",
                          "fix": "uv sync --extra fleet (adds cryptography)",
                          "effect": "edges are emitted with sig_alg='none' and "
                                    "replay --strict refuses them"}), flush=True)
        sys.exit(2)
    _, pub = ensure_key()
    print(json.dumps({"node": warden.node_id(), "pubkey": pub,
                      "key_file": str(key_path())}), flush=True)


def cmd_replay(a):
    rep = replay(get_sink().read(), strict=a.strict)
    out = {"node": warden.node_id(), "strict": a.strict,
           "agents": {k: {"session_id": v["session_id"], "name": v["name"],
                          "current": v["current"], "edges": len(v["history"]),
                          "history": [(h["seq"], h["state"]) for h in v["history"]]}
                      for k, v in rep["agents"].items()},
           "problems": rep["problems"],
           "integrity": "ok" if not rep["problems"] else "FAILED"}
    print(json.dumps(out), flush=True)
    sys.exit(0 if not rep["problems"] else 1)


def cmd_verify(a):
    edges = get_sink().read()
    bad = []
    for i, e in enumerate(edges):
        ok, why = verify_edge(e)
        if not ok:
            bad.append({"i": i, "why": why})
    print(json.dumps({"edges": len(edges), "unverified": len(bad),
                      "detail": bad[:10],
                      "signing_available": HAVE_CRYPTO}), flush=True)
    sys.exit(0 if not bad else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen").set_defaults(f=cmd_keygen)
    r = sub.add_parser("replay"); r.set_defaults(f=cmd_replay)
    r.add_argument("--strict", action="store_true",
                   help="refuse unsigned or badly-signed edges into history")
    sub.add_parser("verify").set_defaults(f=cmd_verify)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
