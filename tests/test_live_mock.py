"""End-to-end tests against the mock agent — real tmux, real processes, no credentials.

These drive an actual TUI through an actual terminal and assert the shipped drivers
report the right state. They cost seconds and zero API turns, which is what makes
them runnable in CI and on a stranger's machine.

Marked `slow` so `pytest -m "not slow"` stays instant.
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
MOCK = ROOT / "prototypes" / "mockagent" / "mock_claude.py"
DRIVERS = {
    "scrape": ROOT / "prototypes" / "scrape-driver" / "driver.py",
    "fused": ROOT / "prototypes" / "fused" / "driver.py",
}

pytestmark = pytest.mark.slow


def have_tmux():
    return subprocess.run(["which", "tmux"], capture_output=True).returncode == 0


requires_tmux = pytest.mark.skipif(not have_tmux(), reason="tmux not installed")


@pytest.fixture
def mock_session(tmp_path):
    """A running mock agent in its own tmux server, with an isolated sessions dir
    so we never touch the user's real ~/.claude."""
    sock = "pytest-" + uuid.uuid4().hex[:6]
    sid = str(uuid.uuid4())
    sessions = tmp_path / "sessions"
    sessions.mkdir()

    def tmux(*args, timeout=15):
        return subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", *args],
                              capture_output=True, text=True, timeout=timeout)

    cmd = "%s %s --session-id %s --sessions-dir %s" % (sys.executable, MOCK, sid, sessions)
    tmux("new-session", "-d", "-s", "m", "-x", "200", "-y", "50", "-c", str(tmp_path), cmd)
    time.sleep(2)
    try:
        yield {"tmux": tmux, "sid": sid, "sessions": sessions, "workdir": tmp_path}
    finally:
        tmux("kill-server")


def capture(session):
    r = session["tmux"]("capture-pane", "-p", "-t", "m")
    return r.stdout


def sidecar(session):
    for f in session["sessions"].glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("sessionId") == session["sid"]:
                return d
        except (ValueError, OSError):
            pass
    return {}


@requires_tmux
class TestSidecarLifecycle:
    """The vendor status channel — docs/discovery-session-sidecar.md.
    These assertions are the contract our drivers depend on."""

    def test_sidecar_created_and_idle_after_trust(self, mock_session):
        assert sidecar(mock_session), "no sidecar written at startup"
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        assert sidecar(mock_session)["status"] == "idle"

    def test_busy_then_idle_across_a_turn(self, mock_session):
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        mock_session["tmux"]("send-keys", "-t", "m", "-l", "say hello")
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(1.5)
        assert sidecar(mock_session)["status"] == "busy"
        time.sleep(5)
        assert sidecar(mock_session)["status"] == "idle"

    def test_waiting_carries_waiting_for(self, mock_session):
        """`waitingFor` is the signal that answers the hardest state directly."""
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        mock_session["tmux"]("send-keys", "-t", "m", "-l", "touch probe.txt")
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        sc = sidecar(mock_session)
        assert sc["status"] == "waiting"
        assert sc["waitingFor"] == "permission prompt"

    def test_clean_exit_deletes_the_sidecar(self, mock_session):
        """Absence is not death, and death is not absence — the asymmetry that
        forces a pid liveness gate (PITFALLS)."""
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        mock_session["tmux"]("send-keys", "-t", "m", "-l", "/exit")
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        assert not sidecar(mock_session)


@requires_tmux
class TestScreenPredicatesLive:
    """The detector against a live terminal, not a string fixture."""

    def test_startup_screen_then_prompt(self, mock_session):
        sys.path.insert(0, str(ROOT / "prototypes" / "scrape-driver"))
        from patterns import classify_screen
        assert classify_screen(capture(mock_session))["trust_dialog"] is True
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        assert classify_screen(capture(mock_session))["prompt_mark"] is True

    def test_idle_screen_moves_but_is_not_busy(self, mock_session):
        """The false-busy source: a statusline wall-clock changes the screen hash
        while the agent is idle. Motion is necessary but not sufficient for busy."""
        sys.path.insert(0, str(ROOT / "prototypes" / "scrape-driver"))
        from patterns import classify_screen
        mock_session["tmux"]("send-keys", "-t", "m", "Enter")
        time.sleep(2)
        a = capture(mock_session)
        time.sleep(2)
        b = capture(mock_session)
        assert a != b, "expected the statusline clock to move the screen"
        assert classify_screen(b)["spinner_busy"] is False


@requires_tmux
def test_portability_check_passes(tmp_path):
    """The full cross-platform check, as a test. This is the same script the README
    tells a newcomer to run."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "prototypes" / "mockagent" / "portability_check.py")],
        capture_output=True, text=True, timeout=300,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "checks passed" in r.stdout
