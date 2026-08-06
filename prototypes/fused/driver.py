#!/usr/bin/env python3
"""Prototype D — fused: the design's fusion rules, implemented.

Channels, in the precedence of docs/design/functional-design.md section 3:

  0. session sidecar  ~/.claude/sessions/<pid>.json  (vendor-emitted status)
  1. screen composite (busy regex OR hash-motion; dialogs; the always-available floor)
  2. process liveness (the only channel that survives the agent's death)

Why fusion rather than the best single channel — each has a hole the others cover:
  * sidecar cannot see pre-session dialogs (trust/theme/login) and carries no option
    text, so it can detect a dialog but never drive one; its staleness means nothing.
  * screen is version-volatile (vendor UI copy) and poll-bound.
  * process alone knows only alive/dead.
Disagreement is reported, never silently resolved (SPEC rule 8).

Stdlib only, Python 3.9+.

COVERAGE DECLARATION
  Verified live (claude 2.1.222, macOS): starting, idle, busy, waiting:permission
  (+ causal denial), dead, and `conflict` — emitted live as sidecar=idle vs screen=busy
  (record: docs/results/conflict/).
  NOT verified: waiting:input against a real question dialog, presumed_hung live,
  compaction suppression, an unrecognised sidecar literal (the conflict path for it is
  written but never exercised), attached posture (no `attach` verb), Windows.
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrape-driver"))
from patterns import classify_screen, COMPAT_RANGE  # noqa: E402

POLL_S = 1.0
STABLE_N = 3
STALE_AFTER_S = 120
CAPTURE_TIMEOUT_S = 5
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")

# Sidecar status vocabulary observed on 2.1.222. An UNRECOGNISED value must
# produce `conflict`, never a guess (docs/discovery-session-sidecar.md).
SIDECAR_STATUS = {"idle": "idle", "busy": "busy", "waiting": "waiting"}
SIDECAR_WAITING_FOR = {"permission prompt": "waiting:permission"}



def sessions_dir():
    """Where the vendor writes session sidecars.

    Follows CLAUDE_CONFIG_DIR when set — hardcoding ~/.claude made the sidecar
    channel silently disappear (pid: null, liveness degraded to the terminal
    proxy) for any session with a custom config dir. Found on WSL2, 2026-08-06.
    """
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "sessions"

def die(msg, code=1):
    print(json.dumps({"error": msg}), flush=True)
    sys.exit(code)


class Session:
    def __init__(self, workdir, sid):
        self.id = sid
        self.workdir = workdir
        self.dir = workdir / ".fused" / sid
        self.sock = "fused-" + sid[:8]

    # ---- plumbing ----
    def tmux(self, *args, timeout=CAPTURE_TIMEOUT_S):
        return subprocess.run(["tmux", "-L", self.sock, "-f", "/dev/null", *args],
                              capture_output=True, text=True, timeout=timeout)

    def capture(self):
        try:
            # VISIBLE PANE ONLY — see scrape-driver: scrollback would carry
            # stale busy frames into a liveness decision.
            r = self.tmux("capture-pane", "-p", "-t", self.id[:8])
        except subprocess.TimeoutExpired:
            return None
        return ANSI_RE.sub("", r.stdout) if r.returncode == 0 else None

    # ---- channel 0: sidecar ----
    def agent_pid(self):
        cache = self.dir / "agent_pid"
        if cache.exists():
            try:
                return int(cache.read_text().strip())
            except ValueError:
                pass
        p = self._sidecar_path()
        if p:
            self.dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(p.stem)
            return int(p.stem)
        return None

    def _sidecar_path(self):
        d = sessions_dir()
        if not d.is_dir():
            return None
        for f in d.glob("*.json"):
            try:
                if json.loads(f.read_text()).get("sessionId") == self.id:
                    return f
            except (ValueError, OSError):
                continue
        return None

    def sidecar(self):
        """(status, waitingFor, unknown_literal) — None status if unavailable.
        Absence is NOT death: a clean exit deletes the file, but so does a session
        that never wrote one yet."""
        p = self._sidecar_path()
        if p is None:
            pid = self.agent_pid()
            if pid is not None:
                p = sessions_dir() / ("%d.json" % pid)
                if not p.exists():
                    return None, None, None
            else:
                return None, None, None
        try:
            d = json.loads(p.read_text())
        except (ValueError, OSError):
            return None, None, None
        raw = d.get("status")
        wf = d.get("waitingFor")
        unknown = None
        if raw is not None and raw not in SIDECAR_STATUS:
            unknown = "status=%s" % raw
        if raw == "waiting" and wf is not None and wf not in SIDECAR_WAITING_FOR:
            unknown = "waitingFor=%s" % wf
        return raw, wf, unknown

    # ---- channel 2: process ----
    def pid_alive(self):
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

    def terminal_alive(self):
        try:
            return self.tmux("has-session", "-t", self.id[:8]).returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def alive(self):
        p = self.pid_alive()
        return self.terminal_alive() if p is None else p

    # ---- persistence ----
    def save(self, meta):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "meta.json").write_text(json.dumps(meta))


def find_session(workdir, sid):
    s = Session(workdir, sid)
    if not (s.dir / "meta.json").exists():
        die("unknown session id %s" % sid, 2)
    return s


def ev(channel, signal):
    return {"channel": channel, "signal": signal, "at": time.time()}


def observe(s, history):
    """One fused tick. history: list of (screen_hash, signals)."""
    evidence = []

    # -- channel 2 first: dead outranks everything (fusion rule 3) --
    if not s.alive():
        return {"state": "dead", "attrs": {},
                "evidence": [ev("process", "agent pid not alive")]}

    # -- channel 0: sidecar --
    sc_status, sc_waiting, sc_unknown = s.sidecar()
    sc_state = None
    if sc_status is not None:
        evidence.append(ev("sidecar", "status=%s%s" % (
            sc_status, (" waitingFor=%s" % sc_waiting) if sc_waiting else "")))
        if sc_unknown:
            return {"state": "conflict",
                    "attrs": {"conflict": True,
                              "reason": "unrecognised sidecar literal: " + sc_unknown},
                    "evidence": evidence}
        if sc_status == "waiting":
            sc_state = SIDECAR_WAITING_FOR.get(sc_waiting, "waiting:input")
        else:
            sc_state = SIDECAR_STATUS[sc_status]

    # -- channel 1: screen --
    text = s.capture()
    if text is None:
        evidence.append(ev("screen", "capture failed/timeout"))
        if sc_state:  # sidecar carries us through a capture failure
            return {"state": sc_state, "attrs": {"degraded": "screen unavailable"},
                    "evidence": evidence}
        return {"state": "conflict",
                "attrs": {"conflict": True, "reason": "no channel available"},
                "evidence": evidence}

    sig = classify_screen(text)
    h = hashlib.sha256(text.encode()).hexdigest()[:12]
    history.append((h, sig))
    if len(history) > 10:
        history.pop(0)
    for k, v in sig.items():
        if v:
            evidence.append(ev("screen", k))

    # pre-session dialogs: sidecar is structurally blind here, screen wins
    if sig["trust_dialog"] or sig["starting_screen"]:
        return {"state": "starting", "attrs": {}, "evidence": evidence}

    screen_state = None
    if sig["permission_dialog"]:
        screen_state = "waiting:permission"
    elif sig["input_dialog_rows"] and not sig["spinner_busy"]:
        screen_state = "waiting:input"
    else:
        # MOTION IS NECESSARY BUT NOT SUFFICIENT FOR BUSY.
        # Q7 established that a busy screen always moves (two per-second tickers).
        # The converse does not hold: a custom statusline containing a live clock
        # (observed here: "wall 11s") moves the hash while the agent is idle. Read
        # as busy, that is a false-busy — exactly the FMA 6.2 class the prior-art
        # survey predicted from other projects and which this fusion caught live
        # on 2026-08-05 as `conflict: sidecar=idle screen=busy`.
        # So: regex => busy (strong). stable => idle (strong).
        # motion without regex => INCONCLUSIVE; defer to the sidecar rather than
        # invent a state.
        busy_regex = sig["spinner_busy"] or sig["tool_running"]
        recent = [hh for hh, _ in history[-(STABLE_N + 1):]]
        stable = len(recent) >= STABLE_N and len(set(recent[-STABLE_N:])) == 1
        if busy_regex:
            screen_state = "busy"
            evidence.append(ev("screen", "busy_regex"))
        elif stable:
            screen_state = "idle"
            evidence.append(ev("screen", "stable x%d" % STABLE_N))
        else:
            evidence.append(ev("screen", "motion without busy-regex: inconclusive"))

    # -- fuse --
    attrs = {"background_work": sig["background_work"]}
    if sc_state and screen_state:
        if sc_state == screen_state:
            return {"state": sc_state, "attrs": attrs, "evidence": evidence}
        # Disagreement. Two are RECONCILABLE by construction, not by preference:
        #  * screen sees a dialog the sidecar reports as busy/idle -> the dialog is
        #    real and drivable; screen wins for waiting:* because only it has the
        #    option rows we would need to answer.
        #  * sidecar says waiting while the screen has not yet rendered the dialog
        #    -> sidecar leads by design (measured 18 ms vs the transcript record).
        if screen_state.startswith("waiting:"):
            attrs["corroboration"] = "screen-led; sidecar=%s" % sc_state
            return {"state": screen_state, "attrs": attrs, "evidence": evidence}
        if sc_state.startswith("waiting:"):
            attrs["corroboration"] = "sidecar-led; screen=%s" % screen_state
            return {"state": sc_state, "attrs": attrs, "evidence": evidence}
        # busy/idle disagreement is NOT reconcilable: one of them is wrong and we
        # cannot tell which. Report it (SPEC rule 8) rather than pick a winner.
        attrs.update({"conflict": True,
                      "reason": "sidecar=%s screen=%s" % (sc_state, screen_state)})
        return {"state": "conflict", "attrs": attrs, "evidence": evidence}

    state = sc_state or screen_state
    if state is None:
        return {"state": "busy", "attrs": {"settling": True}, "evidence": evidence}
    if state == "busy":
        last = s.dir / "last_busy"
        now = time.time()
        prev = float(last.read_text()) if last.exists() else now
        if now - prev > STALE_AFTER_S:
            return {"state": "presumed_hung",
                    "attrs": {"stale_s": round(now - prev)},
                    "evidence": evidence + [ev("watchdog", "busy > %ds" % STALE_AFTER_S)]}
        if not last.exists():
            s.dir.mkdir(parents=True, exist_ok=True)
            last.write_text(str(now))
    else:
        (s.dir / "last_busy").unlink(missing_ok=True)
    return {"state": state, "attrs": attrs, "evidence": evidence}


def observe_settled(s, ticks=STABLE_N + 1):
    hist = []
    rep = {}
    for _ in range(ticks):
        rep = observe(s, hist)
        if rep["state"] in ("dead", "starting", "conflict") or \
           rep["state"].startswith("waiting:"):
            return rep
        time.sleep(POLL_S)
    return rep


# ---------------- commands ----------------

def cmd_launch(a):
    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    s = Session(workdir, sid)
    claude = shutil.which("claude") or die("claude not found on PATH", 5)
    r = s.tmux("new-session", "-d", "-s", sid[:8], "-x", "220", "-y", "50",
               "-c", str(workdir), "%s --session-id %s" % (claude, sid), timeout=10)
    if r.returncode != 0:
        die("tmux launch failed: %s" % r.stderr.strip(), 5)
    s.save({"id": sid, "workdir": str(workdir), "created": time.time(),
            "compat": COMPAT_RANGE, "socket": s.sock})
    for _ in range(20):          # cache pid while the sidecar exists
        if s.agent_pid() is not None:
            break
        time.sleep(0.5)
    rep = {"state": "starting"}
    deadline = time.time() + 60
    hist = []
    while time.time() < deadline:
        rep = observe(s, hist)
        if rep["state"] == "starting":
            time.sleep(1.0)
            s.tmux("send-keys", "-t", sid[:8], "Enter")
            time.sleep(2.0)
            hist = []
            continue
        if rep["state"] in ("idle", "dead"):
            break
        time.sleep(POLL_S)
    print(json.dumps({"id": sid, "state": rep["state"], "settled": rep["state"]}),
          flush=True)


def cmd_list(a):
    """Every live agent on this machine, from the vendor sidecars alone.

    No tmux, no settings, no spawn ownership — this is what makes `attach`
    possible at all: the sidecar names every interactive session, including ones
    started by a human in a terminal we have never seen.
    """
    out = []
    d = sessions_dir()
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            try:
                doc = json.loads(f.read_text())
            except (ValueError, OSError):
                continue
            pid = doc.get("pid")
            try:
                os.kill(int(pid), 0)
                alive = True
            except (OSError, TypeError, ValueError):
                alive = False
            out.append({"sessionId": doc.get("sessionId"), "pid": pid,
                        # name/nameSource matter: role binding treats only an
                        # OPERATOR-set name as an identity claim (F3)
                        "name": doc.get("name"), "nameSource": doc.get("nameSource"),
                        "cwd": doc.get("cwd"), "status": doc.get("status"),
                        "waitingFor": doc.get("waitingFor"),
                        "kind": doc.get("kind"), "version": doc.get("version"),
                        # absence is not death and staleness is not liveness, so the
                        # pid is checked here rather than inferred from the file
                        "alive": alive})
    print(json.dumps({"sessions": out}), flush=True)


def cmd_attach(a):
    """Adopt a session this driver did not launch.

    The prior-art survey concluded that observing a human-launched agent was
    screen-scraping only. Two findings killed that: the vendor sidecar needs no
    spawn ownership, and hooks can be retrofitted mid-session (Q1). This verb is
    the capability those findings implied.

    What attach can and cannot do is a straight consequence of which channels
    are reachable, and it is recorded in the session meta so `state` never
    over-claims:
      * sidecar + process  — always available; gives busy/idle/waiting/dead.
      * screen             — ONLY if the session is in a tmux server we can name
                             (--socket/--target). Without it there is no way to
                             read dialog option rows, so dialogs can be DETECTED
                             (sidecar) but not ANSWERED.
    """
    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    sid = a.session_id

    # Resolve the target from the sidecar — the session must exist and be alive.
    match = None
    d = sessions_dir()
    if d.is_dir():
        for f in d.glob("*.json"):
            try:
                doc = json.loads(f.read_text())
            except (ValueError, OSError):
                continue
            if doc.get("sessionId") == sid:
                match = (f, doc)
                break
    if match is None:
        die("no live session with sessionId %s (run `list`)" % sid, 2)
    f, doc = match
    pid = doc.get("pid")
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        die("session %s has a sidecar but pid %s is not alive" % (sid, pid), 2)

    s = Session(workdir, sid)
    if a.socket:
        s.sock = a.socket
    screen = bool(a.socket) and s.terminal_alive()
    s.save({"id": sid, "workdir": str(workdir), "created": time.time(),
            "compat": COMPAT_RANGE, "socket": s.sock if a.socket else None,
            "attached": True, "screen_available": screen,
            "cwd": doc.get("cwd")})
    s.dir.mkdir(parents=True, exist_ok=True)
    (s.dir / "agent_pid").write_text(str(pid))

    rep = observe_settled(s)
    rep.setdefault("attrs", {})["attached"] = True
    if not screen:
        rep["attrs"]["screen_available"] = False
        rep["attrs"]["cannot"] = "answer dialogs (no terminal); detection only"
    print(json.dumps({"id": sid, "pid": pid, "cwd": doc.get("cwd"),
                      "screen_available": screen, "report": rep}), flush=True)


def cmd_state(a):
    print(json.dumps(observe_settled(find_session(Path(a.workdir).resolve(), a.id))),
          flush=True)


def cmd_wait(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    targets = set(a.until.split(","))
    deadline = time.time() + a.timeout
    hist = []
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
            print(json.dumps({"error": "refusing send in state %s" % rep["state"],
                              "report": rep}), flush=True)
            sys.exit(4)
    s.tmux("send-keys", "-t", s.id[:8], "-l", "--", a.text)
    time.sleep(0.3)
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    time.sleep(1.0)
    print(json.dumps({"sent": True,
                      "verified_on_screen": a.text[:40] in (s.capture() or "")}),
          flush=True)


def cmd_answer(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    rep = observe_settled(s)
    if not (rep["state"].startswith("waiting:") or rep["state"] == "starting"):
        print(json.dumps({"error": "no dialog; state %s" % rep["state"]}), flush=True)
        sys.exit(4)
    for _ in range(a.option - 1):
        s.tmux("send-keys", "-t", s.id[:8], "Down")
        time.sleep(0.2)
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    print(json.dumps({"answered": a.option, "from_state": rep["state"]}), flush=True)


def cmd_screen(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    lines = [ln for ln in (s.capture() or "").splitlines() if ln.strip()]
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
    p.add_argument("--workdir", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("launch").set_defaults(f=cmd_launch)
    sub.add_parser("list").set_defaults(f=cmd_list)
    ap_at = sub.add_parser("attach")
    ap_at.add_argument("--session-id", required=True,
                       help="sessionId of a live session (see `list`)")
    ap_at.add_argument("--socket", default=None,
                       help="tmux socket hosting it, if any; without this, dialogs "
                            "can be detected but not answered")
    ap_at.set_defaults(f=cmd_attach)
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
