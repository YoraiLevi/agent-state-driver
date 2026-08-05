#!/usr/bin/env python3
"""Prototype B — hook-sentinel: EVENT channel (hooks) + process channel.

Implements prototypes/common/SPEC.md against Claude Code over tmux (macOS/Linux).
Same subcommands and JSON shapes as prototype A (scrape-driver), so the comparative
harness cannot tell which driver it is driving.

Channel split, deliberately strict (this is the point of the prototype):
  * STATE decisions come from hook events (push, written to disk by tiny shell hooks)
    fused with process liveness. Never from the screen.
  * The screen is used ONLY to DRIVE: the unconditional launch trust dialog (Q7,
    SPEC rule 4) and the `answer` verb, plus the SPEC rule 6 self-test cross-check.

Hook install follows the Q1 protocol: project `.claude/settings.json` is
read-modify-written (other scopes' hooks exist and must not be clobbered) BEFORE the
process starts, and the channel is not trusted until an event has provably arrived
("hook liveness"); if it never does, the driver reports `conflict` with evidence and
never guesses.

Stdlib only, Python 3.9 floor (no PEP 604 unions). State per session lives under
<workdir>/.hook-sentinel/<id>/.

COVERAGE DECLARATION
  Verified live (claude 2.1.222, macOS): starting (trust dialog), idle (SessionStart and
  Stop paths), busy (UserPromptSubmit and PreToolUse paths), waiting:permission
  (PermissionRequest), dead (SIGKILL via process channel, 27 ms), conflict (permission
  latch unresolved by the event channel), and send-refusal outside idle.
  Verified by offline selftest.py only (NOT live): presumed_hung, the 90 s idle
  no-false-busy property, compaction suppression + re-arm, idle.background_work,
  waiting:input, and the hooks-never-fired conflict path.
  NOT verified at all: a real AskUserQuestion/Elicitation dialog, a real compaction,
  --safe-mode, cold attach to a session this driver did not launch, Linux, Windows.
  KNOWN LIMIT (structural, verified twice): denying a permission dialog emits NO hook
  event, so this channel alone can never clear the latch. It reports `conflict` rather
  than guessing; a production fusion layer needs the sidecar or the screen to close it.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patterns import (  # noqa: E402
    COMPAT_RANGE, HOOK_EVENTS, PERMISSION_CLEARING,
    classify_notification, screen_has,
)

POLL_S = 1.0            # harness parity with A; the hook channel itself is push
STALE_AFTER_S = 120     # SPEC rule 3: presumed_hung threshold (> poll interval)
CAPTURE_TIMEOUT_S = 5   # FMA 6.4: a hanging capture is an event, not a crash
HOOK_PAYLOAD_CAP = 1500  # keep one appended line < PIPE_BUF so appends stay atomic
LIVENESS_GRACE_S = 25   # after first send, how long before "hooks never fired" = conflict
PERM_LATCH_STALE_S = 10  # permission latch with no clearing event -> conflict

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")

# SPEC rule 3: config assertion at startup, fail-fast (cultureagent's shape).
assert STALE_AFTER_S > POLL_S, "stale_after must exceed the poll interval"


def die(msg, code=1):
    print(json.dumps({"error": msg}), flush=True)
    sys.exit(code)


# -- hook installation --------------------------------------------------------

def hook_command(events_path, event):
    """Tiny portable shell, no jq: one line per event, one write syscall.

    Line format is TSV, NOT JSON-wrapping-JSON, deliberately: if the vendor payload
    is ever larger than the cap, truncation costs us the payload only — the epoch
    and the event name (which carry the state decision) stay parseable. Wrapping the
    payload inside our own JSON object would make a truncated line unparseable and
    lose the event itself.
    """
    return (
        "L=$(head -c %d | tr -d '\\n'); "
        "printf '%%s\\t%s\\t%%s\\n' \"$(date +%%s)\" \"$L\" >> '%s'"
        % (HOOK_PAYLOAD_CAP, event, events_path)
    )


def install_hooks(workdir, events_path, tag):
    """Q1 protocol: read-modify-write project settings. Returns the pre-existing
    hook block so `kill` can restore it (retrofit must be reversible)."""
    sfile = workdir / ".claude" / "settings.json"
    sfile.parent.mkdir(parents=True, exist_ok=True)
    settings = {}
    if sfile.exists():
        try:
            settings = json.loads(sfile.read_text() or "{}")
        except ValueError:
            settings = {}
    prior = json.loads(json.dumps(settings.get("hooks", {})))  # deep copy
    hooks = settings.setdefault("hooks", {})
    for ev in HOOK_EVENTS:
        entry = {"hooks": [{"type": "command",
                            "command": hook_command(events_path, ev),
                            "timeout": 10}]}
        if ev in ("PreToolUse", "PostToolUse", "PostToolUseFailure",
                  "PermissionRequest", "PermissionDenied"):
            entry["matcher"] = "*"
        hooks.setdefault(ev, [])
        hooks[ev] = [e for e in hooks[ev] if tag not in json.dumps(e)]
        hooks[ev].append(entry)
    sfile.write_text(json.dumps(settings, indent=2))
    return prior


def uninstall_hooks(workdir, prior):
    sfile = workdir / ".claude" / "settings.json"
    if not sfile.exists():
        return
    try:
        settings = json.loads(sfile.read_text() or "{}")
    except ValueError:
        return
    if prior:
        settings["hooks"] = prior
    else:
        settings.pop("hooks", None)
    sfile.write_text(json.dumps(settings, indent=2))


# -- session ------------------------------------------------------------------

class Session:
    def __init__(self, workdir, sid):
        self.id = sid
        self.workdir = workdir
        self.dir = workdir / ".hook-sentinel" / sid
        self.events = self.dir / "events.jsonl"
        self.sock = "hook-%s" % sid[:8]

    # -- tmux plumbing (driving + trust dialog only) -------------------------
    def tmux(self, *args, **kw):
        timeout = kw.pop("timeout", CAPTURE_TIMEOUT_S)
        cmd = ["tmux", "-L", self.sock, "-f", "/dev/null"] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def capture(self):
        try:
            r = self.tmux("capture-pane", "-p", "-t", self.id[:8], "-S", "-60")
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0:
            return None
        return ANSI_RE.sub("", r.stdout)

    # -- persistence ----------------------------------------------------------
    def save(self, meta):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=2))

    def load(self):
        return json.loads((self.dir / "meta.json").read_text())

    def mark_sent(self):
        (self.dir / "first_send_at").write_text(str(time.time()))

    def first_send_at(self):
        try:
            return float((self.dir / "first_send_at").read_text())
        except (IOError, OSError, ValueError):
            return None

    # -- event channel --------------------------------------------------------
    def read_events(self):
        """-> (list_of_events, last_write_mtime_or_None). Malformed payloads are
        kept with payload=None; a bad payload must never drop an event."""
        out = []
        try:
            raw = self.events.read_text(errors="replace")
            mtime = os.stat(str(self.events)).st_mtime
        except (IOError, OSError):
            return [], None
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                ts = float(parts[0])
            except ValueError:
                continue
            payload = None
            if len(parts) > 2 and parts[2]:
                try:
                    payload = json.loads(parts[2])
                except ValueError:
                    payload = None
            out.append({"at": ts, "event": parts[1], "payload": payload,
                        "payload_raw": parts[2] if len(parts) > 2 else ""})
        return out, mtime

    # -- process channel ------------------------------------------------------
    def pane_pid(self):
        try:
            r = self.tmux("list-panes", "-t", self.id[:8], "-F", "#{pane_pid}")
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return int(r.stdout.strip().splitlines()[0])

    def claude_pid(self):
        """The real agent pid, resolved from the tmux pane's descendants. Cached in
        meta.json: after SIGKILL the pane is gone, so discovery must not be the only
        path to the pid (existence != liveness, SYNTHESIS 1.8, cuts both ways)."""
        meta = self.load()
        cached = meta.get("claude_pid")
        if cached and pid_alive(cached) and is_agent_cmd(pid_cmd(cached)):
            return cached
        ppid = self.pane_pid()
        if ppid is None:
            return cached
        found = descendant_claude(ppid)
        if found:
            meta["claude_pid"] = found
            self.save(meta)
        return found or cached


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # a zombie answers signal 0 but is not liveness
    try:
        r = subprocess.run(["ps", "-p", str(pid), "-o", "stat="],
                           capture_output=True, text=True, timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return True
    st = r.stdout.strip()
    return bool(st) and not st.startswith("Z")


def pid_cmd(pid):
    try:
        r = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def is_agent_cmd(cmd):
    """The AGENT process, not merely a process with 'claude' somewhere in its
    argv. Discovered live: claude spawns `/bin/zsh -c source ~/.claude/
    shell-snapshots/...` children whose command line contains 'claude' — a
    substring match latches onto a transient child and the process channel then
    reports `dead` the moment that child exits. Anchor on argv[0]'s basename."""
    argv0 = (cmd.split() or [""])[0]
    base = argv0.rsplit("/", 1)[-1].lower()
    return base in ("claude", "claude.exe")


def descendant_claude(root):
    """Breadth-first (shallowest wins): the agent is a direct child of the tmux
    pane, its helpers are deeper."""
    try:
        r = subprocess.run(["ps", "-Ao", "pid=,ppid=,command="],
                           capture_output=True, text=True, timeout=8)
    except (subprocess.TimeoutExpired, OSError):
        return None
    kids = {}
    cmds = {}
    for line in r.stdout.splitlines():
        f = line.split(None, 2)
        if len(f) < 3:
            continue
        try:
            pid, ppid = int(f[0]), int(f[1])
        except ValueError:
            continue
        kids.setdefault(ppid, []).append(pid)
        cmds[pid] = f[2]
    if is_agent_cmd(cmds.get(root, "")):
        return root
    queue = [root]
    seen = set()
    while queue:
        p = queue.pop(0)
        if p in seen:
            continue
        seen.add(p)
        if p != root and is_agent_cmd(cmds.get(p, "")):
            return p
        queue.extend(kids.get(p, []))
    return None


def find_session(workdir, sid):
    s = Session(workdir, sid)
    if not (s.dir / "meta.json").exists():
        die("unknown session id %s" % sid, 2)
    return s


# -- state engine (hooks authoritative, process for dead) ---------------------

def derive_from_events(events):
    """Replay the event log into a state. Pure function of the log — no clocks,
    no screen. Returns (state, attrs, notes)."""
    state = "starting"
    attrs = {}
    in_compaction = False
    session_end = False
    perm_latch = False
    for e in events:
        name = e["event"]
        pl = e["payload"] or {}
        if name in PERMISSION_CLEARING and perm_latch:
            perm_latch = False
        if name == "SessionStart":
            state = "idle"
        elif name == "UserPromptSubmit":
            state = "busy"
            attrs.pop("background_work", None)
        elif name in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
            state = "busy"
        elif name == "StopFailure":
            state = "idle"   # turn ended abnormally (interrupt / denied tool)
        elif name == "PermissionRequest":
            perm_latch = True
            state = "waiting:permission"
        elif name == "PermissionDenied":
            state = "busy"
        elif name == "Notification":
            kind = classify_notification(e["payload_raw"])
            if kind == "permission":
                perm_latch = True
                state = "waiting:permission"
            elif kind == "input":
                state = "waiting:input"
        elif name == "Stop":
            bg = pl.get("background_tasks") or []
            attrs["background_work"] = bool(bg)
            state = "idle"
        elif name == "PreCompact":
            in_compaction = True
            state = "busy"
        elif name == "PostCompact":
            in_compaction = False
            state = "busy"
        elif name == "SessionEnd":
            # NOT death: SessionEnd fires on /clear too (design 6.4). Recorded only.
            session_end = True
    if perm_latch:
        state = "waiting:permission"
    return state, attrs, {"in_compaction": in_compaction,
                          "session_end_seen": session_end}


def observe(s):
    """One state report. Hook events authoritative; process channel for dead;
    observer-side staleness watchdog; loud conflict when the channel is silent."""
    now = time.time()
    meta = s.load()
    events, mtime = s.read_events()
    ev_out = []
    if events:
        tail = events[-3:]
        ev_out = [{"channel": "hook", "signal": e["event"], "at": e["at"]}
                  for e in tail]

    pid = s.claude_pid()
    alive = bool(pid) and pid_alive(pid)
    if not alive:
        return {"state": "dead", "attrs": {},
                "evidence": ev_out + [
                    {"channel": "process",
                     "signal": "claude pid %s not alive" % pid, "at": now}]}

    state, attrs, notes = derive_from_events(events)

    # -- hook liveness (Q1): never trust a channel that has not proven itself ---
    fired = set(e["event"] for e in events)
    live = bool(fired & set(["SessionStart", "UserPromptSubmit", "Stop",
                             "PreToolUse", "PostToolUse", "Notification"]))
    sent_at = s.first_send_at()
    if not live:
        if sent_at and now - sent_at > LIVENESS_GRACE_S:
            return {"state": "conflict",
                    "attrs": {"conflict": True, "reason": "hooks_never_fired"},
                    "evidence": [
                        {"channel": "process", "signal": "pid %s alive" % pid,
                         "at": now},
                        {"channel": "hook",
                         "signal": "no event in %s after send at %.0f"
                                   % (s.events, sent_at), "at": now},
                        {"channel": "config",
                         "signal": "hooks installed in %s"
                                   % (s.workdir / ".claude" / "settings.json"),
                         "at": now}]}
        return {"state": "starting", "attrs": {"hooks_confirmed": False},
                "evidence": ev_out + [
                    {"channel": "process", "signal": "pid %s alive" % pid,
                     "at": now},
                    {"channel": "hook", "signal": "awaiting first event",
                     "at": now}]}
    attrs["hooks_confirmed"] = True

    # -- staleness watchdog (observer-side, SPEC rule 3) -----------------------
    last = mtime or meta.get("created", now)
    if state == "busy":
        if notes["in_compaction"]:
            attrs["compaction"] = True   # watchdog suppressed (design 2 / C7)
        elif now - last > STALE_AFTER_S:
            return {"state": "presumed_hung", "attrs": attrs,
                    "evidence": ev_out + [
                        {"channel": "watchdog",
                         "signal": "busy asserted, no hook event for %.0fs "
                                   "(>%ss)" % (now - last, STALE_AFTER_S),
                         "at": now},
                        {"channel": "process", "signal": "pid %s alive" % pid,
                         "at": now}]}
    if notes["session_end_seen"] and state != "busy":
        attrs["session_end_seen"] = True

    ev_out.append({"channel": "process", "signal": "pid %s alive" % pid, "at": now})
    ev_out.append({"channel": "hook",
                   "signal": "last event %.1fs ago" % (now - last), "at": now})

    # -- SPEC rule 6 self-test: hook channel PROVES the dialog; if the screen
    # literal set matches nothing, the literal set is stale -> fail loudly.
    if state == "waiting:permission":
        text = s.capture() or ""
        if not screen_has("permission", text):
            attrs["literal_selftest"] = "MISS"
            attrs["conflict"] = True
            ev_out.append({"channel": "selftest",
                           "signal": "PermissionRequest fired but no permission "
                                     "literal matched the screen (patterns stale "
                                     "OR the dialog was resolved with no event)",
                           "at": now})
            # LIVE FINDING: answering "No" emits no hook event at all, so the latch
            # cannot be cleared from the event channel. Two channels now disagree —
            # surface it as `conflict` (SPEC rule 2) rather than guess either way.
            if now - last > PERM_LATCH_STALE_S:
                attrs["reason"] = "permission_latch_unresolved_by_event_channel"
                return {"state": "conflict", "attrs": attrs, "evidence": ev_out}
        else:
            attrs["literal_selftest"] = "ok"
    return {"state": state, "attrs": attrs, "evidence": ev_out}


# -- commands -----------------------------------------------------------------

def cmd_launch(a):
    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    s = Session(workdir, sid)
    s.dir.mkdir(parents=True, exist_ok=True)
    s.events.touch()
    claude = shutil.which("claude")
    if not claude:
        die("claude not found on PATH", 5)

    # Q1: install BEFORE the process starts (spawned posture), read-modify-write.
    prior = install_hooks(workdir, str(s.events), tag=str(s.events))
    s.save({"id": sid, "workdir": str(workdir), "created": time.time(),
            "compat": COMPAT_RANGE, "prior_hooks": prior,
            "settings_file": str(workdir / ".claude" / "settings.json")})

    r = s.tmux("new-session", "-d", "-s", sid[:8], "-x", "220", "-y", "50",
               "-c", str(workdir), "%s --session-id %s" % (claude, sid), timeout=10)
    if r.returncode != 0:
        die("tmux launch failed: %s" % r.stderr.strip(), 5)

    # SPEC rule 4: trust dialog unconditionally (Q7). This is the ONE place the
    # screen drives state progress, and it is a driving action, not a state decision.
    deadline = time.time() + 60
    trusted = False
    while time.time() < deadline:
        text = s.capture() or ""
        if not trusted and (screen_has("trust", text) or screen_has("starting", text)):
            time.sleep(0.8)
            s.tmux("send-keys", "-t", sid[:8], "Enter")
            trusted = True
            time.sleep(2.0)
            continue
        events, _ = s.read_events()
        if events or (trusted and time.time() > deadline - 45):
            break
        time.sleep(POLL_S)
    meta = s.load()
    meta["claude_pid"] = s.claude_pid()
    meta["trust_dialog_answered"] = trusted
    s.save(meta)
    rep = observe(s)
    print(json.dumps({"id": sid, "state": "starting", "settled": rep["state"],
                      "trust_dialog_answered": trusted,
                      "claude_pid": meta.get("claude_pid")}), flush=True)


def cmd_state(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    print(json.dumps(observe(s)), flush=True)


def cmd_wait(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    targets = set(a.until.split(","))
    deadline = time.time() + a.timeout
    rep = {}
    while time.time() < deadline:
        rep = observe(s)
        if rep["state"] in targets:
            print(json.dumps(rep), flush=True)
            return
        time.sleep(0.2)   # push channel: poll only to notice the file changed
    print(json.dumps({"error": "timeout", "last": rep}), flush=True)
    sys.exit(3)


def cmd_send(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    if not a.force:
        rep = observe(s)
        if rep["state"] != "idle":
            print(json.dumps({"error": "refusing send in state %s" % rep["state"],
                              "report": rep}), flush=True)
            sys.exit(4)
    s.mark_sent()
    s.tmux("send-keys", "-t", s.id[:8], "-l", "--", a.text)
    time.sleep(0.3)
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    # post-send verification (FMA 6.3) — on THIS prototype the oracle is the hook
    # channel: UserPromptSubmit must arrive, otherwise the send did not land.
    verified = False
    t0 = time.time()
    while time.time() - t0 < 10:
        events, _ = s.read_events()
        if any(e["event"] == "UserPromptSubmit" and e["at"] >= int(t0) - 1
               for e in events):
            verified = True
            break
        time.sleep(0.1)
    print(json.dumps({"sent": True, "verified_by_hook": verified,
                      "hook_latency_s": round(time.time() - t0, 2)
                      if verified else None}), flush=True)


def cmd_answer(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    rep = observe(s)
    if not (rep["state"].startswith("waiting:") or rep["state"] == "starting"):
        print(json.dumps({"error": "no dialog; state %s" % rep["state"],
                          "report": rep}), flush=True)
        sys.exit(4)
    for _ in range(a.option - 1):
        s.tmux("send-keys", "-t", s.id[:8], "Down")
        time.sleep(0.2)
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    print(json.dumps({"answered": a.option, "from_state": rep["state"]}), flush=True)


def cmd_screen(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    text = s.capture() or ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print("\n".join(lines[-a.lines:]))


def cmd_kill(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    meta = s.load()
    pid = meta.get("claude_pid")
    if pid and pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        s.tmux("kill-server", timeout=10)
    except subprocess.TimeoutExpired:
        pass
    uninstall_hooks(Path(meta["workdir"]), meta.get("prior_hooks") or {})
    print(json.dumps({"killed": s.id, "hooks_restored": True}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workdir", default=".", help="session workdir root")
    sub = p.add_subparsers(dest="cmd")
    sp = sub.add_parser("launch")
    sp.add_argument("--session-name", default=None)
    sp.set_defaults(f=cmd_launch)
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
    if not getattr(a, "f", None):
        p.error("a subcommand is required")
    a.f(a)


if __name__ == "__main__":
    main()
