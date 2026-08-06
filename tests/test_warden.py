"""F2 — Warden: single-writer ownership, edge-triggered publication, durable cursor.

Deterministic: drives the mock agent, so state transitions are forced rather than
waited for. No credentials, no API cost.

The acceptance test for F2 (issue #12) is `test_second_warden_refuses` plus
`test_lock_reclaimed_when_holder_dies`; the rest guard the invariants those two
would otherwise let slide.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WARDEN = ROOT / "fleet" / "warden.py"
MOCK = ROOT / "prototypes" / "mockagent" / "mock_claude.py"

pytestmark = pytest.mark.slow


def have_tmux():
    return subprocess.run(["which", "tmux"], capture_output=True).returncode == 0


requires_tmux = pytest.mark.skipif(not have_tmux(), reason="tmux not installed")


@pytest.fixture
def fleet(tmp_path):
    """An isolated machine: its own agent-config dir (so the Warden sees only our
    mock) and its own fleet state dir (so locks/cursors never touch the real one)."""
    cfg = tmp_path / "claude"
    (cfg / "sessions").mkdir(parents=True)
    state = tmp_path / "fleet"
    env = {**os.environ,
           "CLAUDE_CONFIG_DIR": str(cfg),
           "FLEET_STATE_DIR": str(state)}
    sock = "wtest-" + uuid.uuid4().hex[:6]
    sid = str(uuid.uuid4())

    def tmux(*a, timeout=15):
        return subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", *a],
                              capture_output=True, text=True, timeout=timeout)

    cmd = "%s %s --session-id %s --sessions-dir %s" % (
        sys.executable, MOCK, sid, cfg / "sessions")
    tmux("new-session", "-d", "-s", "m", "-x", "200", "-y", "50",
         "-c", str(tmp_path), cmd)
    time.sleep(2)
    tmux("send-keys", "-t", "m", "Enter")     # trust dialog
    time.sleep(2)
    try:
        yield {"env": env, "sid": sid, "state": state, "tmux": tmux}
    finally:
        tmux("kill-server")


def warden(fleet, *args, timeout=90):
    r = subprocess.run([sys.executable, str(WARDEN), *args],
                       capture_output=True, text=True, timeout=timeout,
                       env=fleet["env"])
    lines = [l for l in r.stdout.strip().splitlines() if l.startswith("{")]
    return [json.loads(l) for l in lines], r.returncode


def edges(fleet):
    p = fleet["state"] / "edges.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


@requires_tmux
class TestOwnership:
    def test_warden_adopts_a_session_it_did_not_spawn(self, fleet):
        out, rc = warden(fleet, "run", "--duration", "5")
        assert rc == 0
        assert any(fleet["sid"] in r.get("owned", []) for r in out)

    def test_second_warden_refuses_and_names_the_holder(self, fleet, tmp_path):
        """F2 ACCEPTANCE (first half). Two Wardens on one machine: the second
        must refuse the sessions the first holds, and say who holds them."""
        proc = subprocess.Popen([sys.executable, str(WARDEN), "run", "--duration", "20"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, env=fleet["env"])
        try:
            time.sleep(6)
            out, _ = warden(fleet, "run", "--duration", "3")
            last = out[-1]
            assert last.get("owned") == [], "second warden must own nothing"
            refused = last.get("refused") or []
            assert any(r["session_id"] == fleet["sid"] for r in refused)
            assert refused[0]["holder"], "refusal must name the holder"
        finally:
            proc.kill()
            proc.wait(timeout=10)

    def test_lock_reclaimed_when_holder_dies(self, fleet):
        """F2 ACCEPTANCE (second half). A SIGKILLed Warden never releases
        cleanly; the next one must reclaim, because a lock held by a dead
        process is not ownership."""
        proc = subprocess.Popen([sys.executable, str(WARDEN), "run", "--duration", "60"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, env=fleet["env"])
        time.sleep(6)
        proc.kill()
        proc.wait(timeout=10)
        lock = fleet["state"] / "locks" / (fleet["sid"] + ".lock")
        assert lock.exists(), "expected a stale lock left by the killed warden"
        out, _ = warden(fleet, "run", "--duration", "4")
        assert fleet["sid"] in out[-1].get("owned", [])


@requires_tmux
class TestEdges:
    def test_publication_is_edge_triggered_not_a_heartbeat(self, fleet):
        """Many polls, one state: exactly one edge. A heartbeat would emit per
        poll and drown the bus at fleet scale."""
        warden(fleet, "run", "--duration", "8")
        es = [e for e in edges(fleet) if e["session_id"] == fleet["sid"]]
        assert len(es) == 1, "expected one edge for one unchanged state, got %d" % len(es)

    def test_edge_carries_seq_prev_and_evidence(self, fleet):
        warden(fleet, "run", "--duration", "5")
        e = edges(fleet)[0]
        assert e["seq"] == 1 and e["prev"] is None
        assert e["state"]
        assert e["evidence"], "an edge without evidence is a presence claim, not verified state"
        assert e["node"].startswith("nod_") and e["warden"].startswith("wdn_")

    def test_seq_continues_across_a_warden_handover(self, fleet):
        """REGRESSION (found by the F2 acceptance run, 2026-08-06): seq restarted
        at 1 and prev came back null after a Warden restart, so a transition
        during the handover would have been invisible — defeating the entire
        point of `prev`. The cursor belongs to the (node, agent) pair, not to a
        Warden instance."""
        warden(fleet, "run", "--duration", "5")
        # force a transition while no warden is running
        fleet["tmux"]("send-keys", "-t", "m", "-l", "touch probe.txt")
        fleet["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        warden(fleet, "run", "--duration", "5")
        es = [e for e in edges(fleet) if e["session_id"] == fleet["sid"]]
        assert len(es) >= 2, "expected the post-handover transition to be published"
        assert [e["seq"] for e in es] == list(range(1, len(es) + 1)), \
            "seq must be monotone across the handover: %s" % [e["seq"] for e in es]
        assert es[1]["prev"] == es[0]["state"], \
            "prev must chain to the previous state, not reset to null"

    def test_cursor_survives_on_disk(self, fleet):
        warden(fleet, "run", "--duration", "5")
        cur = json.loads((fleet["state"] / "cursors.json").read_text())
        assert fleet["sid"] in cur and cur[fleet["sid"]]["seq"] >= 1


@requires_tmux
class TestIdentity:
    def test_node_id_is_durable(self, fleet):
        a, _ = warden(fleet, "id")
        b, _ = warden(fleet, "id")
        assert a[0]["node"] == b[0]["node"], "node identity must persist"
        assert a[0]["node"].startswith("nod_")

    def test_status_reports_holder_liveness(self, fleet):
        warden(fleet, "run", "--duration", "4")
        out, _ = warden(fleet, "status")
        assert fleet["sid"] in out[0]["sessions_seen"]
