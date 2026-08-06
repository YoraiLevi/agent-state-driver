"""F3 — durable identities: node_id, agent slugs, tombstoning, session binding.

The acceptance test for F3 (issue #13) is `test_node_id_survives_identity_churn`
plus `test_tombstoned_slug_is_permanently_unallocatable`.

Why tombstoning gets three tests: it is a security property, not bookkeeping.
Work, capabilities and budgets are addressed to a slug, so a reallocated slug
would let a new agent silently inherit a retired one's authority and queued work
— an identity-confusion attack that needs no attacker, only a coincidence of
naming.
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
ROSTER = ROOT / "fleet" / "roster.py"
WARDEN = ROOT / "fleet" / "warden.py"
MOCK = ROOT / "prototypes" / "mockagent" / "mock_claude.py"

pytestmark = pytest.mark.slow


def have_tmux():
    return subprocess.run(["which", "tmux"], capture_output=True).returncode == 0


requires_tmux = pytest.mark.skipif(not have_tmux(), reason="tmux not installed")


@pytest.fixture
def env(tmp_path):
    cfg = tmp_path / "claude"
    (cfg / "sessions").mkdir(parents=True)
    return {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg),
            "FLEET_STATE_DIR": str(tmp_path / "fleet")}


def run(env, script, *args):
    r = subprocess.run([sys.executable, str(script), *args],
                       capture_output=True, text=True, timeout=60, env=env)
    line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "{}"
    return json.loads(line), r.returncode


@pytest.fixture
def named_session(env, tmp_path):
    """A live agent whose name was set by the OPERATOR (nameSource null)."""
    sock = "rtest-" + uuid.uuid4().hex[:6]
    sid = str(uuid.uuid4())
    sessions = Path(env["CLAUDE_CONFIG_DIR"]) / "sessions"

    def tmux(*a):
        return subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", *a],
                              capture_output=True, text=True, timeout=15)

    cmd = "%s %s --session-id %s --sessions-dir %s --name reviewer-01" % (
        sys.executable, MOCK, sid, sessions)
    tmux("new-session", "-d", "-s", "m", "-x", "180", "-y", "45",
         "-c", str(tmp_path), cmd)
    time.sleep(2)
    try:
        yield {"sid": sid, "tmux": tmux, "slug": "reviewer-01"}
    finally:
        tmux("kill-server")


class TestSlugLifecycle:
    def test_claim_allocates(self, env):
        out, rc = run(env, ROSTER, "claim", "--slug", "reviewer-01", "--role", "reviewer")
        assert rc == 0 and out["claimed"] == "reviewer-01"
        assert out["roles"] == ["reviewer"]

    def test_claim_is_idempotent_on_the_same_node(self, env):
        run(env, ROSTER, "claim", "--slug", "worker-a")
        out, rc = run(env, ROSTER, "claim", "--slug", "worker-a")
        assert rc == 0 and out.get("already") is True

    def test_invalid_slugs_are_refused(self, env):
        for bad in ["Reviewer-01", "a", "has spaces", "-leading", "x" * 64]:
            _, rc = run(env, ROSTER, "claim", "--slug", bad)
            assert rc == 2, "expected %r to be refused" % bad

    def test_tombstoned_slug_is_permanently_unallocatable(self, env):
        """F3 ACCEPTANCE. Retiring an agent must make its slug unallocatable
        forever — otherwise a new agent inherits the old one's authority."""
        run(env, ROSTER, "claim", "--slug", "reviewer-01")
        out, rc = run(env, ROSTER, "retire", "--slug", "reviewer-01", "--reason", "done")
        assert rc == 0 and out["reallocatable"] is False
        out, rc = run(env, ROSTER, "claim", "--slug", "reviewer-01")
        assert rc == 3, "a tombstoned slug must never be reallocatable"
        assert "tombstoned" in out["error"]

    def test_retire_is_idempotent(self, env):
        run(env, ROSTER, "claim", "--slug", "gone")
        run(env, ROSTER, "retire", "--slug", "gone")
        out, rc = run(env, ROSTER, "retire", "--slug", "gone")
        assert rc == 0 and out.get("already_tombstoned") == "gone"

    def test_tombstone_survives_a_restart(self, env):
        """The refusal is only a security property if it is durable."""
        run(env, ROSTER, "claim", "--slug", "reviewer-01")
        run(env, ROSTER, "retire", "--slug", "reviewer-01")
        out, _ = run(env, ROSTER, "list")
        assert "reviewer-01" in out["tombstones"]


@requires_tmux
class TestBinding:
    def test_operator_named_session_binds_to_its_slug(self, env, named_session):
        run(env, ROSTER, "claim", "--slug", "reviewer-01")
        out, rc = run(env, ROSTER, "bind")
        assert rc == 0
        assert any(b["slug"] == "reviewer-01" and b["session_id"] == named_session["sid"]
                   for b in out["bound"])

    def test_vendor_derived_names_are_never_identity_claims(self, env, tmp_path):
        """A `derived` name is the vendor's guess from the conversation. Treating
        it as an identity claim would let an unrelated session adopt a
        role-holder's authority by coincidence."""
        sock = "rtest2-" + uuid.uuid4().hex[:6]
        sessions = Path(env["CLAUDE_CONFIG_DIR"]) / "sessions"
        cmd = "%s %s --session-id %s --sessions-dir %s" % (
            sys.executable, MOCK, uuid.uuid4(), sessions)   # NO --name
        subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", "new-session", "-d",
                        "-s", "m", "-c", str(tmp_path), cmd], capture_output=True,
                       timeout=15)
        time.sleep(2)
        try:
            out, _ = run(env, ROSTER, "bind", "--autoclaim")
            assert out["bound"] == []
            assert any(i["why"] == "not an operator-set name" for i in out["ignored"])
        finally:
            subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", "kill-server"],
                           capture_output=True, timeout=15)

    def test_bind_refuses_a_tombstoned_slug(self, env, named_session):
        run(env, ROSTER, "claim", "--slug", "reviewer-01")
        run(env, ROSTER, "retire", "--slug", "reviewer-01")
        out, _ = run(env, ROSTER, "bind", "--autoclaim")
        assert out["bound"] == []
        assert any("tombstoned" in u["why"] for u in out["unbound"])

    def test_unclaimed_slug_needs_autoclaim(self, env, named_session):
        out, _ = run(env, ROSTER, "bind")
        assert out["bound"] == []
        assert any("not claimed" in u["why"] for u in out["unbound"])
        out, _ = run(env, ROSTER, "bind", "--autoclaim")
        assert out["bound"][0]["slug"] == "reviewer-01"


class TestNodeIdentity:
    def test_node_id_survives_identity_churn(self, env):
        """F3 ACCEPTANCE. node_id must not derive from anything that changes when
        Tailscale is reinstalled or the machine is re-IP'd — so we assert it is
        stable across invocations AND that it contains no hostname/IP material."""
        import socket
        a, _ = run(env, WARDEN, "id")
        b, _ = run(env, WARDEN, "id")
        assert a["node"] == b["node"]
        host = socket.gethostname().lower().split(".")[0]
        assert host not in a["node"].lower(), \
            "node_id must not embed the hostname — hostnames change"
        assert a["node"].startswith("nod_")

    def test_two_nodes_get_distinct_ids(self, env, tmp_path):
        other = {**env, "FLEET_STATE_DIR": str(tmp_path / "fleet2")}
        a, _ = run(env, WARDEN, "id")
        b, _ = run(other, WARDEN, "id")
        assert a["node"] != b["node"]
