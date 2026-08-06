"""F4 — bus: signed state edges, and replay that detects a broken history.

The acceptance test for F4 (issue #14):
  * `test_replay_reconstructs_exact_history`
  * `test_dropped_edge_is_detected_not_absorbed`

The second is the one that matters. Any system can hand you a history; the
question is whether you can tell that the history you were handed is the one that
happened. `prev` and `seq` are what make that answerable, and these tests break
them on purpose to prove the detection is real rather than decorative.
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
sys.path.insert(0, str(ROOT / "fleet"))

BUS = ROOT / "fleet" / "bus.py"


@pytest.fixture
def fleet_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_STATE_DIR", str(tmp_path / "fleet"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    for m in ("warden", "bus"):
        sys.modules.pop(m, None)
    import bus
    return bus


def edge(sink, sid, seq, state, prev, node="nod_test", **extra):
    return sink.publish({
        "v": 1, "kind": "state", "id": "edg_" + uuid.uuid4().hex[:12],
        "node": node, "warden": "wdn_test", "session_id": sid,
        "seq": seq, "state": state, "prev": prev,
        "attrs": {}, "evidence": [{"channel": "sidecar", "signal": "status=%s" % state,
                                   "at": time.time()}],
        "observed_at": time.time(), **extra})


class TestReplay:
    def test_replay_reconstructs_exact_history(self, fleet_env):
        """F4 ACCEPTANCE. A consumer joining from offset 0 must rebuild exactly
        what happened — without asking the agent."""
        bus = fleet_env
        sink = bus.JournalSink()
        sid = str(uuid.uuid4())
        for i, (st, prev) in enumerate(
                [("idle", None), ("busy", "idle"),
                 ("waiting:permission", "busy"), ("idle", "waiting:permission"),
                 ("dead", "idle")], start=1):
            edge(sink, sid, i, st, prev)
        rep = bus.replay(sink.read())
        assert rep["problems"] == []
        hist = [h["state"] for h in rep["agents"][sid]["history"]]
        assert hist == ["idle", "busy", "waiting:permission", "idle", "dead"]
        assert rep["agents"][sid]["current"] == "dead"

    def test_dropped_edge_is_detected_not_absorbed(self, fleet_env):
        """F4 ACCEPTANCE, the load-bearing half. Drop the middle edge: a history
        that merely looks plausible must NOT be accepted."""
        bus = fleet_env
        sink = bus.JournalSink()
        sid = str(uuid.uuid4())
        edge(sink, sid, 1, "idle", None)
        edge(sink, sid, 2, "busy", "idle")            # this one gets dropped
        edge(sink, sid, 3, "idle", "busy")
        lines = sink.path.read_text().splitlines()
        sink.path.write_text("\n".join([lines[0], lines[2]]) + "\n")   # drop seq 2

        rep = bus.replay(sink.read())
        kinds = {p["kind"] for p in rep["problems"]}
        assert "seq_gap" in kinds, "a missing seq must be reported"
        assert "prev_mismatch" in kinds, "the history must be shown not to chain"
        gap = next(p for p in rep["problems"] if p["kind"] == "seq_gap")
        assert gap["expected"] == 2 and gap["got"] == 3

    def test_duplicate_edge_is_detected(self, fleet_env):
        bus = fleet_env
        sink = bus.JournalSink()
        sid = str(uuid.uuid4())
        edge(sink, sid, 1, "idle", None)
        edge(sink, sid, 1, "idle", None)               # replayed twice
        rep = bus.replay(sink.read())
        assert any(p["kind"] == "seq_gap" for p in rep["problems"])

    def test_out_of_order_delivery_is_detected(self, fleet_env):
        """The transport gives no ordering guarantee across subscribers, which is
        exactly why `seq` exists rather than trusting arrival order."""
        bus = fleet_env
        sink = bus.JournalSink()
        sid = str(uuid.uuid4())
        edge(sink, sid, 2, "busy", "idle")
        edge(sink, sid, 1, "idle", None)
        rep = bus.replay(sink.read())
        assert rep["problems"], "arrival order must not be trusted silently"

    def test_corrupt_line_is_reported(self, fleet_env):
        bus = fleet_env
        sink = bus.JournalSink()
        edge(sink, str(uuid.uuid4()), 1, "idle", None)
        with open(sink.path, "a") as fh:
            fh.write("{not json at all\n")
        rep = bus.replay(sink.read())
        assert any(p["kind"] == "corrupt_line" for p in rep["problems"])

    def test_two_agents_do_not_share_a_sequence(self, fleet_env):
        bus = fleet_env
        sink = bus.JournalSink()
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        edge(sink, a, 1, "idle", None)
        edge(sink, b, 1, "idle", None)
        edge(sink, a, 2, "busy", "idle")
        rep = bus.replay(sink.read())
        assert rep["problems"] == [], "seq is per-agent, not global"
        assert rep["agents"][a]["current"] == "busy"
        assert rep["agents"][b]["current"] == "idle"


class TestSigning:
    def test_edges_are_signed_and_verify(self, fleet_env):
        bus = fleet_env
        if not bus.HAVE_CRYPTO:
            pytest.skip("signing extra not installed")
        sink = bus.JournalSink()
        e = edge(sink, str(uuid.uuid4()), 1, "idle", None)
        assert e["sig_alg"] == "ed25519"
        ok, why = bus.verify_edge(e)
        assert ok, why

    def test_tampering_with_state_breaks_the_signature(self, fleet_env):
        """The point of signing at the machine boundary: a relay cannot rewrite
        what a Warden observed."""
        bus = fleet_env
        if not bus.HAVE_CRYPTO:
            pytest.skip("signing extra not installed")
        sink = bus.JournalSink()
        e = edge(sink, str(uuid.uuid4()), 1, "idle", None)
        e["state"] = "busy"
        ok, why = bus.verify_edge(e)
        assert not ok and "bad signature" in why

    def test_tampering_with_evidence_breaks_the_signature(self, fleet_env):
        """Evidence must be inside the signed payload — otherwise a consumer
        could be shown a state with fabricated justification."""
        bus = fleet_env
        if not bus.HAVE_CRYPTO:
            pytest.skip("signing extra not installed")
        sink = bus.JournalSink()
        e = edge(sink, str(uuid.uuid4()), 1, "idle", None)
        e["evidence"][0]["channel"] = "invented"
        ok, _ = bus.verify_edge(e)
        assert not ok

    def test_strict_replay_refuses_unsigned_edges(self, fleet_env, monkeypatch):
        """Degrading crypto silently is worse than not having it, because it
        looks like it worked. Strict mode must keep unsigned edges OUT of
        history, and say so."""
        bus = fleet_env
        monkeypatch.setattr(bus, "HAVE_CRYPTO", False)
        sink = bus.JournalSink()
        sid = str(uuid.uuid4())
        edge(sink, sid, 1, "idle", None)
        rep = bus.replay(sink.read(), strict=True)
        assert any(p["kind"] == "signature" for p in rep["problems"])
        assert rep["agents"] == {}, "an unsigned edge must not enter strict history"


class TestSinkContract:
    def test_nats_url_fails_loudly_rather_than_pretending(self, fleet_env):
        """The production sink is a deliberate operator decision. Until it
        exists, asking for it must error — not silently fall back to a local
        file while the operator believes they are on a bus."""
        bus = fleet_env
        with pytest.raises(SystemExit) as ex:
            bus.get_sink("nats://localhost:4222")
        assert "not implemented" in str(ex.value)
