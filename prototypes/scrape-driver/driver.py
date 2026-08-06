#!/usr/bin/env python3
"""Prototype A — scrape-driver: screen-composite + process channels only.

Implements prototypes/common/SPEC.md against Claude Code over tmux (macOS/Linux).
Channels: tmux capture-pane (screen composite gate, Q7) + process liveness.
Deliberately NO hooks, NO transcript — this prototype measures how far the
always-available floor gets us (design section 3, fusion rule 2).

Stdlib only. State per session lives under <workdir>/.scrape-driver/<id>/.

COVERAGE DECLARATION
  Verified live (claude 2.1.222, macOS): starting (incl. unconditional trust dialog),
  idle, busy, waiting:permission (+ denial verified causally by file absence), dead.
  Verified by fixture (macOS + Linux): the screen predicates via patterns.classify_screen.
  NOT verified: waiting:input against a real question dialog, presumed_hung live,
  compaction, attached posture (no `attach` verb exists), Windows (this backend is tmux).
  KNOWN LIMIT: single-channel, so motion-without-busy-regex is treated as busy and a
  statusline wall-clock produces a false-busy this prototype cannot resolve. Declared,
  not hidden — the fused prototype defers to the sidecar instead.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patterns import classify_screen, COMPAT_RANGE  # noqa: E402

POLL_S = 1.0
STABLE_N = 3          # SPEC rule 1: >=3 identical captures for idle
STALE_AFTER_S = 120   # SPEC rule 3: presumed_hung threshold
CAPTURE_TIMEOUT_S = 5  # FMA 6.4: a hanging capture is an event, not a crash

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")



def sessions_dir():
    """Where the vendor writes session sidecars.

    Follows CLAUDE_CONFIG_DIR when set — hardcoding ~/.claude made the sidecar
    channel silently disappear (pid: null, liveness degraded to the terminal
    proxy) for any session with a custom config dir. Found on WSL2, 2026-08-06.
    """
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "sessions"

def die(msg: str, code: int = 1):
    print(json.dumps({"error": msg}), flush=True)
    sys.exit(code)


class Session:
    def __init__(self, workdir: Path, sid: str):
        self.id = sid
        self.workdir = workdir
        self.dir = workdir / ".scrape-driver" / sid
        self.sock = f"scrape-{sid[:8]}"

    # -- tmux plumbing -------------------------------------------------------
    def tmux(self, *args, timeout=CAPTURE_TIMEOUT_S):
        cmd = ["tmux", "-L", self.sock, "-f", "/dev/null", *args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def capture(self):  # -> Optional[str]; PEP 604 unions need py3.10, floor is 3.9
        """ANSI-stripped visible screen + scrollback tail. None = capture failed
        (surfaced as evidence, never raised — FMA 6.4)."""
        try:
            # VISIBLE PANE ONLY (no -S): scrollback carries spinner lines from
            # earlier frames, and matching liveness over history reports `busy`
            # on a long-idle session. The present is what is on screen now.
            r = self.tmux("capture-pane", "-p", "-t", self.id[:8])
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0:
            return None
        return ANSI_RE.sub("", r.stdout)

    def agent_pid(self):
        """claude's PID.

        Resolved from the vendor session sidecar (keyed by sessionId, not by PID
        — docs/discovery-session-sidecar.md) and then CACHED to disk, because the
        sidecar is DELETED on clean shutdown. Without the cache, liveness lookup
        fails exactly when it matters — at death — and the driver silently falls
        back to the terminal proxy it is trying to avoid (harness S6b, 2026-08-05).
        """
        cache = self.dir / "agent_pid"
        if cache.exists():
            try:
                return int(cache.read_text().strip())
            except ValueError:
                pass
        d = sessions_dir()
        if not d.is_dir():
            return None
        for f in d.glob("*.json"):
            try:
                if json.loads(f.read_text()).get("sessionId") == self.id:
                    pid = int(f.stem)
                    self.dir.mkdir(parents=True, exist_ok=True)
                    cache.write_text(str(pid))
                    return pid
            except (ValueError, OSError):
                continue
        return None

    def pid_alive(self):
        """True/False if we know the pid, None if we don't."""
        pid = self.agent_pid()
        if pid is None:
            return None
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def terminal_alive(self) -> bool:
        try:
            r = self.tmux("has-session", "-t", self.id[:8])
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def alive(self) -> bool:
        """Liveness = the AGENT PROCESS, not its terminal.

        Measured 2026-08-05: the claude process outlives its killed terminal by
        ~1 s (SIGHUP propagation), and a detached agent can outlive it
        indefinitely. Gating on `has-session` alone made this driver report
        `dead` while the process was provably alive — a silent misdetection
        caught by harness scenario S6b. Terminal-gone is now only a fallback for
        when no sidecar exists to name the pid.
        """
        p = self.pid_alive()
        if p is not None:
            return p
        return self.terminal_alive()

    # -- persistence ---------------------------------------------------------
    def save(self, meta: dict):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "meta.json").write_text(json.dumps(meta))

    def load(self) -> dict:
        return json.loads((self.dir / "meta.json").read_text())

    def touch_evidence(self):
        (self.dir / "last_evidence").write_text(str(time.time()))

    def last_evidence(self) -> float:
        try:
            return float((self.dir / "last_evidence").read_text())
        except FileNotFoundError:
            return time.time()


def find_session(workdir: Path, sid: str) -> Session:
    s = Session(workdir, sid)
    if not (s.dir / "meta.json").exists():
        die(f"unknown session id {sid}", 2)
    return s


# -- state engine ------------------------------------------------------------

def observe(s: Session, history: list) -> dict:
    """One observation tick. Appends to history (list of (hash, signals))."""
    if not s.alive():
        return {"state": "dead", "attrs": {}, "evidence": [
            {"channel": "process", "signal": "tmux session gone", "at": time.time()}]}

    text = s.capture()
    if text is None:
        return {"state": "conflict", "attrs": {"conflict": True}, "evidence": [
            {"channel": "screen", "signal": "capture failed/timeout", "at": time.time()}]}

    sig = classify_screen(text)
    h = hashlib.sha256(text.encode()).hexdigest()[:12]
    history.append((h, sig))
    if len(history) > 10:
        history.pop(0)

    now = time.time()
    ev = [{"channel": "screen", "signal": k, "at": now} for k, v in sig.items() if v]

    # ordered decision — dialogs outrank busy (a dialog IS a paused turn)
    if sig["trust_dialog"] or sig["starting_screen"]:
        s.touch_evidence()
        return {"state": "starting", "attrs": {}, "evidence": ev}
    if sig["permission_dialog"]:
        s.touch_evidence()
        return {"state": "waiting:permission", "attrs": {}, "evidence": ev}
    if sig["input_dialog_rows"] and not sig["spinner_busy"]:
        s.touch_evidence()
        return {"state": "waiting:input", "attrs": {}, "evidence": ev}

    busy_regex = sig["spinner_busy"] or sig["tool_running"]
    recent = [hh for hh, _ in history[-(STABLE_N + 1):]]
    hash_motion = len(set(recent)) > 1 if len(recent) >= 2 else True
    stable = len(recent) >= STABLE_N and len(set(recent[-STABLE_N:])) == 1

    # NOTE (2026-08-05): motion is necessary but NOT sufficient for busy — a
    # statusline with a live wall-clock moves the hash while idle (found by the
    # fused prototype as `conflict: sidecar=idle screen=busy`). This screen-only
    # prototype has no second channel to defer to, so it keeps motion in the busy
    # predicate and accepts the false-busy; that is the measured cost of a
    # single-channel design and is declared, not hidden. The fused driver treats
    # motion-without-regex as inconclusive instead.
    if busy_regex or (hash_motion and not stable):
        s.touch_evidence()
        # staleness check: busy asserted with no fresh evidence for too long
        if now - s.last_evidence() > STALE_AFTER_S:
            return {"state": "presumed_hung", "attrs": {}, "evidence": ev + [
                {"channel": "watchdog", "signal": f"stale>{STALE_AFTER_S}s", "at": now}]}
        return {"state": "busy", "attrs": {}, "evidence": ev + [
            {"channel": "screen", "signal": f"hash_motion={hash_motion}", "at": now}]}

    if stable and not busy_regex:
        attrs = {"background_work": sig["background_work"]}
        return {"state": "idle", "attrs": attrs, "evidence": ev + [
            {"channel": "screen", "signal": f"stable x{STABLE_N}", "at": now}]}

    # not enough history yet — keep observing, report busy-leaning unknown
    return {"state": "busy", "attrs": {"settling": True}, "evidence": ev}


def observe_settled(s: Session, ticks: int = STABLE_N + 1) -> dict:
    """SPEC rule 1: never decide from a single capture."""
    hist: list = []
    rep = {}
    for _ in range(ticks):
        rep = observe(s, hist)
        if rep["state"] in ("dead", "waiting:permission", "waiting:input", "starting"):
            return rep  # these are single-capture-decidable (dialog/process proof)
        time.sleep(POLL_S)
    return rep


# -- commands ----------------------------------------------------------------

def cmd_launch(a):
    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    s = Session(workdir, sid)
    claude = shutil.which("claude")
    if not claude:
        die("claude not found on PATH", 5)
    r = s.tmux("new-session", "-d", "-s", sid[:8], "-x", "220", "-y", "50",
               "-c", str(workdir), f"{claude} --session-id {sid}", timeout=10)
    if r.returncode != 0:
        die(f"tmux launch failed: {r.stderr.strip()}", 5)
    s.save({"id": sid, "workdir": str(workdir), "created": time.time(),
            "compat": COMPAT_RANGE, "socket": s.sock})
    s.touch_evidence()
    # Resolve+cache the agent PID while the sidecar still exists (it is removed
    # on shutdown). Poll briefly: the sidecar appears shortly after exec.
    for _ in range(20):
        if s.agent_pid() is not None:
            break
        time.sleep(0.5)
    # starting-phase handling (SPEC rule 4): wait for trust dialog or idle
    deadline = time.time() + 60
    hist: list = []
    while time.time() < deadline:
        rep = observe(s, hist)
        if rep["state"] == "starting":
            time.sleep(1.0)
            s.tmux("send-keys", "-t", sid[:8], "Enter")  # accept trust
            time.sleep(2.0)
            hist.clear()
            continue
        if rep["state"] in ("idle", "dead"):
            break
        time.sleep(POLL_S)
    print(json.dumps({"id": sid, "state": rep["state"]}), flush=True)


def cmd_state(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    print(json.dumps(observe_settled(s)), flush=True)


def cmd_wait(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    targets = set(a.until.split(","))
    deadline = time.time() + a.timeout
    hist: list = []
    rep = {}
    while time.time() < deadline:
        rep = observe(s, hist)
        if rep["state"] in targets and not rep["attrs"].get("settling"):
            print(json.dumps(rep), flush=True)
            return
        time.sleep(POLL_S)
    print(json.dumps({"error": "timeout", "last": rep}), flush=True)
    sys.exit(3)


def cmd_send(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    if not a.force:
        rep = observe_settled(s)
        if rep["state"] != "idle":
            print(json.dumps({"error": f"refusing send in state {rep['state']}",
                              "report": rep}), flush=True)
            sys.exit(4)
    s.tmux("send-keys", "-t", s.id[:8], "-l", "--", a.text)
    time.sleep(0.3)
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    # post-send verification (FMA 6.3): prompt text must appear on screen
    time.sleep(1.0)
    text = s.capture() or ""
    landed = a.text[:40] in text
    print(json.dumps({"sent": True, "verified_on_screen": landed}), flush=True)


def cmd_answer(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    rep = observe_settled(s)
    # starting-phase dialogs (trust/theme/login) are answerable too
    if not (rep["state"].startswith("waiting:") or rep["state"] == "starting"):
        print(json.dumps({"error": f"no dialog; state {rep['state']}"}), flush=True)
        sys.exit(4)
    for _ in range(a.option - 1):
        s.tmux("send-keys", "-t", s.id[:8], "Down")
        time.sleep(0.2)
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    print(json.dumps({"answered": a.option}), flush=True)


def cmd_screen(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    text = s.capture() or ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print("\n".join(lines[-a.lines:]))


def cmd_kill(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    try:
        s.tmux("kill-server", timeout=10)
    except subprocess.TimeoutExpired:
        pass
    print(json.dumps({"killed": s.id}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workdir", default=".", help="session workdir root")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("launch"); sp.set_defaults(f=cmd_launch)
    for name, f in [("state", cmd_state), ("wait", cmd_wait), ("send", cmd_send),
                    ("answer", cmd_answer), ("screen", cmd_screen), ("kill", cmd_kill)]:
        sp = sub.add_parser(name)
        sp.add_argument("--id", required=True)
        sp.set_defaults(f=f)
        if name == "wait":
            sp.add_argument("--until", required=True)
            sp.add_argument("--timeout", type=float, default=120)
        if name == "send":
            sp.add_argument("--text", required=True)
            sp.add_argument("--force", action="store_true")
        if name == "answer":
            sp.add_argument("--option", type=int, required=True)
        if name == "screen":
            sp.add_argument("--lines", type=int, default=25)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
