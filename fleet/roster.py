#!/usr/bin/env python3
"""Roster — durable identities for nodes and agents.

    uv run fleet/roster.py claim  --slug reviewer-01 [--role reviewer]
    uv run fleet/roster.py list
    uv run fleet/roster.py retire --slug reviewer-01 --reason "project ended"
    uv run fleet/roster.py bind                       # map live sessions -> slugs

THE PROBLEM IDENTITY SOLVES
---------------------------
A `sessionId` identifies a *conversation*; it changes every time the agent is
restarted. An `agent_id` must identify the *role-holder* — the thing work is
addressed to, budgets are charged to, and history accumulates against — and must
survive a restart, a reinstall, and a change of IP.

Three identities, three lifetimes:

    node_id     per machine, minted once, survives Tailscale reinstall + re-IP
    agent slug  per role-holder, operator-chosen, survives session restarts
    sessionId   per conversation, vendor-minted, dies with the process

WHY SLUGS ARE TOMBSTONED, NEVER REUSED
--------------------------------------
This is a security property, not bookkeeping. Work, capabilities and budgets are
addressed to a slug. If `reviewer-01` could be retired and later reallocated, a
new agent would silently inherit whatever authority, queued work and trust the
old one had accumulated — an identity-confusion attack that needs no attacker,
only a coincidence of naming. So a retired slug is permanently unallocatable.

HOW A SESSION BINDS TO A SLUG (free, thanks to the vendor)
----------------------------------------------------------
Probed 2026-08-06: `claude --name reviewer-01` lands in the vendor sidecar as
`name`, and `nameSource` is `null` for operator-set names versus `"derived"` for
auto-generated ones. So the fleet can enumerate *and distinguish* the sessions it
labelled from ones it did not — with no registry, and including sessions it did
not spawn. `bind` exploits exactly that.

Stdlib only, Python 3.9+.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import warden  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def roster_path() -> Path:
    return warden.state_root() / "roster.json"


def load() -> dict:
    try:
        return json.loads(roster_path().read_text())
    except (OSError, ValueError):
        return {"v": 1, "agents": {}, "tombstones": {}}


def save(doc: dict):
    p = roster_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, p)          # atomic: a torn roster is an identity crisis


def die(msg, code=1, **extra):
    print(json.dumps({"error": msg, **extra}), flush=True)
    sys.exit(code)


# --------------------------------------------------------------------------

def cmd_claim(a):
    """Allocate a slug. Refuses a tombstoned one — that refusal is the feature."""
    if not SLUG_RE.match(a.slug):
        die("invalid slug (lowercase alphanumeric and dashes, 2-63 chars)", 2,
            slug=a.slug)
    doc = load()
    if a.slug in doc["tombstones"]:
        die("slug is tombstoned and can never be reallocated", 3,
            slug=a.slug, tombstone=doc["tombstones"][a.slug])
    if a.slug in doc["agents"]:
        cur = doc["agents"][a.slug]
        if cur.get("node") != warden.node_id():
            die("slug already claimed on another node", 4, slug=a.slug,
                held_by=cur.get("node"))
        print(json.dumps({"claimed": a.slug, "already": True, **cur}), flush=True)
        return
    rec = {"slug": a.slug, "node": warden.node_id(),
           "roles": ([a.role] if a.role else []),
           "claimed_at": time.time(), "session_id": None, "pid": None}
    doc["agents"][a.slug] = rec
    save(doc)
    print(json.dumps({"claimed": a.slug, **rec}), flush=True)


def cmd_retire(a):
    """Tombstone a slug. Irreversible by design."""
    doc = load()
    if a.slug in doc["tombstones"]:
        print(json.dumps({"already_tombstoned": a.slug,
                          **doc["tombstones"][a.slug]}), flush=True)
        return
    rec = doc["agents"].pop(a.slug, None)
    doc["tombstones"][a.slug] = {"slug": a.slug, "retired_at": time.time(),
                                 "reason": a.reason,
                                 "node": (rec or {}).get("node", warden.node_id()),
                                 "last_session": (rec or {}).get("session_id")}
    save(doc)
    print(json.dumps({"retired": a.slug, "reallocatable": False,
                      **doc["tombstones"][a.slug]}), flush=True)


def cmd_bind(a):
    """Map live sessions to slugs using the vendor sidecar's `name`.

    Only `nameSource: null` (operator-set) counts. A `"derived"` name is the
    vendor's own guess from the conversation and must never be treated as an
    identity claim — that is how an unrelated session would silently adopt a
    role-holder's authority.
    """
    doc = load()
    bound, unbound, ignored = [], [], []
    for s in warden.local_sessions():
        name, src = s.get("name"), s.get("nameSource")
        sid = s.get("sessionId")
        if not name or src is not None:
            ignored.append({"session_id": sid, "name": name, "name_source": src,
                            "why": "not an operator-set name"})
            continue
        if name in doc["tombstones"]:
            unbound.append({"session_id": sid, "slug": name,
                            "why": "slug is tombstoned; refusing to bind"})
            continue
        rec = doc["agents"].get(name)
        if rec is None:
            if not a.autoclaim:
                unbound.append({"session_id": sid, "slug": name,
                                "why": "slug not claimed (use --autoclaim)"})
                continue
            rec = {"slug": name, "node": warden.node_id(), "roles": [],
                   "claimed_at": time.time()}
            doc["agents"][name] = rec
        rec.update({"session_id": sid, "pid": s.get("pid"),
                    "node": warden.node_id(), "bound_at": time.time()})
        bound.append({"slug": name, "session_id": sid, "pid": s.get("pid")})
    save(doc)
    print(json.dumps({"bound": bound, "unbound": unbound, "ignored": ignored}),
          flush=True)


def cmd_list(a):
    doc = load()
    live = {s.get("sessionId") for s in warden.local_sessions()}
    agents = []
    for slug, rec in sorted(doc["agents"].items()):
        agents.append({**rec, "session_live": rec.get("session_id") in live})
    print(json.dumps({"node": warden.node_id(), "agents": agents,
                      "tombstones": sorted(doc["tombstones"])}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("claim"); c.set_defaults(f=cmd_claim)
    c.add_argument("--slug", required=True)
    c.add_argument("--role", default=None)
    r = sub.add_parser("retire"); r.set_defaults(f=cmd_retire)
    r.add_argument("--slug", required=True)
    r.add_argument("--reason", default="")
    b = sub.add_parser("bind"); b.set_defaults(f=cmd_bind)
    b.add_argument("--autoclaim", action="store_true",
                   help="claim an operator-named slug on first sight")
    sub.add_parser("list").set_defaults(f=cmd_list)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
