#!/usr/bin/env python3
"""Warden — one node agent per machine, sole author of state for its agents.

    uv run fleet/warden.py run          # sweep, own, and publish state edges
    uv run fleet/warden.py status       # what this machine holds, right now
    uv run fleet/warden.py id           # this node's durable identity

WHY ONE WRITER PER MACHINE
--------------------------
Borrowed as a hard invariant from agentirc's "a peer may never overwrite a
locally-hosted nick". With two writers, a stale peer can overwrite a fresh local
observation — and the fleet's only structural advantage (state read from OUTSIDE
the reporter) evaporates the moment a second party is allowed to guess.

So: exactly one Warden owns any given session, enforced by an on-disk lock keyed
by sessionId. A second Warden must REFUSE, loudly, and say who holds it.

WHY EDGES, NOT HEARTBEATS
-------------------------
Verified state is read at ~1s next to the process; only TRANSITIONS cross the
machine boundary. A fleet-scaled heartbeat is structurally too slow to be an
agent-liveness signal — Nomad needs a 200-400s client TTL at 10k clients, which
is useless for "is this agent ready for work right now".

Each edge carries `seq` (monotone per agent — ordering the transport cannot give
us) and `prev` (so a MISSED edge is detectable rather than silently absorbed).

WHAT THIS IS NOT, YET
---------------------
F2 publishes edges to a local append-only journal. The bus (F4) replaces the
sink, not the shape. Signing (F3/F4) happens at this boundary — the driver stays
stdlib-only and unsigned by design, so the attestation belongs exactly here.

Stdlib only, Python 3.9+.
"""

import argparse
import errno
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes" / "fused"))
import driver as fused  # noqa: E402

POLL_S = 2.0
LOCK_STALE_AFTER_S = 30.0   # a holder that has not renewed for this long is presumed gone


def state_root() -> Path:
    """Where this Warden keeps its identity, locks and journal.

    Honours FLEET_STATE_DIR so tests (and several Wardens on one machine, which
    is exactly the acceptance test) can be isolated without touching the real one.
    """
    base = os.environ.get("FLEET_STATE_DIR")
    return Path(base) if base else Path.home() / ".fleet"


# --------------------------------------------------------------------------
# identity (the durable part of F3 that F2 cannot do without)
# --------------------------------------------------------------------------

def node_id() -> str:
    """A self-minted node identity that survives reinstalls and re-IPs.

    Deliberately NOT derived from a Tailscale node key, hostname or MAC:
    Tailscale is reachability, not identity, and a node key changes when the
    client is reinstalled. The id is minted once and persisted.
    """
    p = state_root() / "node_id"
    if p.exists():
        return p.read_text().strip()
    nid = "nod_" + uuid.uuid4().hex[:16]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(nid)
    return nid


def warden_instance_id() -> str:
    """Distinguishes THIS running Warden process from a previous one that died
    holding locks. The node is durable; a Warden instance is not."""
    return "wdn_" + uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------
# ownership locks
# --------------------------------------------------------------------------

class Lock:
    """An on-disk ownership claim over one session, keyed by sessionId.

    Acquisition is atomic (O_CREAT|O_EXCL). A lock whose holder is provably gone
    is reclaimable — "provably" meaning the holder PID is not alive, or it has
    not renewed within LOCK_STALE_AFTER_S. Both checks matter: a Warden killed
    with SIGKILL never releases cleanly, and one that is SIGSTOPed is alive but
    not observing, which is not ownership in any useful sense.
    """

    def __init__(self, session_id: str, holder: str):
        self.session_id = session_id
        self.holder = holder
        self.path = state_root() / "locks" / (session_id + ".lock")

    def _read(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None

    def _write(self, fd=None):
        doc = {"session_id": self.session_id, "warden": self.holder,
               "pid": os.getpid(), "host": socket.gethostname(),
               "node": node_id(), "acquired_at": time.time(),
               "renewed_at": time.time()}
        blob = json.dumps(doc)
        if fd is not None:
            os.write(fd, blob.encode())
        else:
            self.path.write_text(blob)
        return doc

    @staticmethod
    def _pid_alive(pid) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def acquire(self):
        """-> (ok: bool, info: dict). Never raises on contention; the refusal is
        the product, and it must say WHO holds it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            cur = self._read()
            if cur is None:
                # corrupt or half-written; treat as stale
                self.path.unlink(missing_ok=True)
                return self.acquire()
            if cur.get("warden") == self.holder:
                return True, cur                       # already ours: idempotent
            alive = self._pid_alive(cur.get("pid"))
            fresh = (time.time() - cur.get("renewed_at", 0)) < LOCK_STALE_AFTER_S
            if alive and fresh:
                return False, {"refused": "held by another warden", **cur}
            # reclaimable: the holder is gone, or alive-but-not-observing
            self.path.unlink(missing_ok=True)
            ok, info = self.acquire()
            if ok:
                info["reclaimed_from"] = {"warden": cur.get("warden"),
                                          "pid": cur.get("pid"),
                                          "pid_alive": alive, "renewal_fresh": fresh}
            return ok, info
        try:
            return True, self._write(fd)
        finally:
            os.close(fd)

    def renew(self):
        cur = self._read()
        if not cur or cur.get("warden") != self.holder:
            return False
        cur["renewed_at"] = time.time()
        self.path.write_text(json.dumps(cur))
        return True

    def release(self):
        cur = self._read()
        if cur and cur.get("warden") == self.holder:
            self.path.unlink(missing_ok=True)
            return True
        return False


# --------------------------------------------------------------------------
# the sweep
# --------------------------------------------------------------------------

def local_sessions():
    """Every live agent on this machine, from the vendor sidecars.

    No tmux, no settings, no spawn ownership — this is what makes a Warden able
    to adopt sessions a human started by hand.
    """
    out = []
    d = fused.sessions_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        pid = doc.get("pid")
        try:
            os.kill(int(pid), 0)
            alive = True
        except (OSError, TypeError, ValueError):
            alive = False
        if not alive:
            continue          # a sidecar survives SIGKILL; absence of pid is the truth
        out.append(doc)
    return out


class Cursor:
    """Per-agent `seq` and last-known state, PERSISTED.

    Found by the F2 acceptance test: when a Warden was killed and a second one
    reclaimed the lock, `seq` restarted at 1 and `prev` came back null — so a
    state change that happened during the handover would have been invisible,
    which is precisely what `prev` exists to make detectable. The cursor belongs
    to the (node, agent) pair, not to a Warden instance; Wardens are disposable
    and the agent's history is not.
    """

    def __init__(self):
        self.path = state_root() / "cursors.json"
        try:
            self.data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def seq(self, sid):
        return int(self.data.get(sid, {}).get("seq", 0))

    def last(self, sid):
        return self.data.get(sid, {}).get("state")

    def advance(self, sid, state):
        n = self.seq(sid) + 1
        self.data[sid] = {"seq": n, "state": state, "at": time.time()}
        tmp = self.path.with_suffix(".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(self.data))
        os.replace(tmp, self.path)      # atomic: a torn cursor loses the history
        return n

    def forget(self, sid):
        self.data.pop(sid, None)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data))
        os.replace(tmp, self.path)


class Journal:
    """Adapter onto the bus sink (F4). The Warden signs at this boundary — the
    driver stays stdlib-only and unsigned, so the attestation belongs here, where
    a node identity already exists and where the edge crosses the machine."""

    def __init__(self, sink=None):
        import bus
        self.sink = sink or bus.get_sink()
        self.path = getattr(self.sink, "path", None)

    def emit(self, edge: dict):
        return self.sink.publish(edge)


def sweep_once(holder, owned, cursor, journal, workdir):
    """One observation pass. Returns a summary dict.

    `owned` maps session_id -> Lock. `cursor` carries per-agent sequence and
    previous state ACROSS Warden restarts, so an edge is self-describing and a
    handover cannot silently swallow a transition.
    """
    seen, edges, refused = set(), 0, []
    for doc in local_sessions():
        sid = doc.get("sessionId")
        if not sid:
            continue
        seen.add(sid)
        if sid not in owned:
            lk = Lock(sid, holder)
            ok, info = lk.acquire()
            if not ok:
                refused.append({"session_id": sid, "holder": info.get("warden")})
                continue
            owned[sid] = lk
        else:
            owned[sid].renew()

        # Observe with the SHIPPED driver — the Warden adds no detection logic of
        # its own, so there is exactly one implementation of "what state is this".
        s = fused.Session(Path(workdir), sid)
        s.dir.mkdir(parents=True, exist_ok=True)
        (s.dir / "agent_pid").write_text(str(doc.get("pid")))
        if not (s.dir / "meta.json").exists():
            s.save({"id": sid, "workdir": str(workdir), "created": time.time(),
                    "compat": fused.COMPAT_RANGE, "socket": None,
                    "attached": True, "adopted_by": holder})
        rep = fused.observe_settled(s)

        st = rep.get("state")
        prev = cursor.last(sid)
        if prev != st:                              # EDGE-triggered, never a heartbeat
            n = cursor.advance(sid, st)
            journal.emit({
                "v": 1, "kind": "state", "id": "edg_" + uuid.uuid4().hex[:16],
                "node": node_id(), "warden": holder,
                "session_id": sid, "pid": doc.get("pid"),
                "name": doc.get("name"), "name_source": doc.get("nameSource"),
                "seq": n,
                "state": st, "prev": prev,
                "attrs": rep.get("attrs", {}), "evidence": rep.get("evidence", []),
                "backend": "claude-code", "cli_version": doc.get("version"),
                "observed_at": time.time(),
            })
            edges += 1

    # A session that vanished: release the lock, and record the edge. Absence of
    # the sidecar is NOT death on its own (a clean exit deletes it, and so does a
    # process that never wrote one) — but the pid check in local_sessions() is,
    # which is why anything missing here is genuinely gone.
    for sid in [s for s in owned if s not in seen]:
        prev = cursor.last(sid)
        n = cursor.advance(sid, "dead")
        journal.emit({"v": 1, "kind": "state", "id": "edg_" + uuid.uuid4().hex[:16],
                      "node": node_id(), "warden": holder, "session_id": sid,
                      "seq": n, "state": "dead", "prev": prev,
                      "attrs": {}, "evidence": [{"channel": "process",
                                                 "signal": "pid not alive",
                                                 "at": time.time()}],
                      "observed_at": time.time()})
        owned[sid].release()
        del owned[sid]
        edges += 1

    return {"owned": sorted(owned), "edges": edges, "refused": refused}


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_run(a):
    holder = warden_instance_id()
    journal = Journal()
    owned, cursor = {}, Cursor()
    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"warden": holder, "node": node_id(),
                      "state_dir": str(state_root()), "poll_s": POLL_S}), flush=True)
    deadline = time.time() + a.duration if a.duration else None
    try:
        while deadline is None or time.time() < deadline:
            rep = sweep_once(holder, owned, cursor, journal, workdir)
            rep.update({"warden": holder, "at": time.time()})
            print(json.dumps(rep), flush=True)
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        pass
    finally:
        for lk in owned.values():
            lk.release()


def cmd_status(a):
    locks = []
    d = state_root() / "locks"
    if d.is_dir():
        for f in sorted(d.glob("*.lock")):
            try:
                doc = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            doc["holder_alive"] = Lock._pid_alive(doc.get("pid"))
            doc["renewal_age_s"] = round(time.time() - doc.get("renewed_at", 0), 1)
            locks.append(doc)
    # One JSON object per line, like every other command: the Warden's stdout is
    # a machine interface first. Pretty-printing broke line-oriented consumers
    # (caught by the F2 test helper, 2026-08-06) — pipe through `jq` for humans.
    print(json.dumps({"node": node_id(), "state_dir": str(state_root()),
                      "sessions_seen": [s.get("sessionId") for s in local_sessions()],
                      "locks": locks}), flush=True)


def cmd_id(a):
    print(json.dumps({"node": node_id(), "host": socket.gethostname(),
                      "state_dir": str(state_root())}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workdir", default=str(state_root() / "sessions"),
                   help="scratch dir for per-session driver state")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.set_defaults(f=cmd_run)
    r.add_argument("--duration", type=float, default=0,
                   help="seconds to run (0 = forever)")
    sub.add_parser("status").set_defaults(f=cmd_status)
    sub.add_parser("id").set_defaults(f=cmd_id)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
