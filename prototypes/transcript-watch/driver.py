#!/usr/bin/env python3
"""Prototype C — transcript-watch: session-JSONL (disk) + process channels.

Implements prototypes/common/SPEC.md against Claude Code over tmux (macOS/Linux).
Channels: the session transcript under ~/.claude/projects/<mangled-cwd>/<sid>.jsonl
(design section 3, "Transcript JSONL") + process liveness. Screen (tmux capture)
is used ONLY for the three things the disk channel provably cannot do:
the trust dialog at launch (SPEC rule 4), the `answer` verb (keystrokes), and
post-send verification. No STATE decision reads the screen.

Deliberately NO hooks and no settings writes — this prototype measures what the
always-on-disk channel alone can prove, including its declared blind spots.

Stdlib only, Python 3.9 floor. State per session: <workdir>/.transcript-watch/<id>/.
"""

import argparse
import glob
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
from records import (  # noqa: E402
    COMPAT_RANGE, INPUT_TOOLS, SchemaSelfTest, classify,
)

POLL_S = 1.0
STABLE_N = 3            # SPEC rule 1: >=3 confirming observations for idle
STALE_AFTER_S = 120     # SPEC rule 3: presumed_hung threshold
PERMISSION_SUSPECT_S = 8.0   # unresolved tool_use silence => suspect a dialog
TMUX_TIMEOUT_S = 5
TRANSCRIPT_WAIT_S = 60  # the file can appear late; poll for it

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")
TRUST_RE = re.compile(r"Quick safety check: Is this a project you created"
                      r"|Yes, I trust this folder"
                      r"|Do you trust the files in this folder")


def die(msg: str, code: int = 1):
    print(json.dumps({"error": msg}), flush=True)
    sys.exit(code)


def mangle(cwd: str) -> str:
    """~/.claude/projects dir name. Verified: '/'->'-' (and '.'->'-'), e.g.
    /private/tmp/.../protoA -> -private-tmp-...-protoA"""
    return re.sub(r"[/.]", "-", str(cwd))


def transcript_path(workdir: Path, sid: str):
    """Primary: mangled-cwd guess. Fallback: glob every project dir for
    <sid>.jsonl (cheap, and immune to mangling-rule drift)."""
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    guess = root / "projects" / mangle(str(workdir)) / (sid + ".jsonl")
    if guess.exists():
        return guess
    hits = glob.glob(str(root / "projects" / "*" / (sid + ".jsonl")))
    if hits:
        return Path(hits[0])
    return guess  # nonexistent path; caller treats absence as `starting`


# -- transcript reader --------------------------------------------------------

class Tail:
    """Incremental JSONL reader. Buffers a partial trailing line until its
    newline arrives (fsync lag / mid-append reads are normal, not errors).
    Only OUR session id is consumed; forks/siblings are counted and skipped."""

    def __init__(self, path: Path, sid: str):
        self.path = path
        self.sid = sid
        self.offset = 0
        self.buf = ""
        self.recs = []          # classified records, in order
        self.foreign = 0
        self.bad_json = 0
        self.partial_reads = 0
        self.selftest = SchemaSelfTest()
        self.last_size = -1
        self.last_mtime = 0.0
        self.last_growth_at = 0.0

    def exists(self) -> bool:
        return self.path.exists()

    def poll(self) -> int:
        """Read whatever is new. Returns count of new records parsed."""
        if not self.path.exists():
            return 0
        try:
            st = self.path.stat()
        except OSError:
            return 0
        if st.st_size < self.offset:      # truncated/replaced -> restart
            self.offset, self.buf, self.recs = 0, "", []
        if st.st_size != self.last_size:
            self.last_growth_at = time.time()
        self.last_size, self.last_mtime = st.st_size, st.st_mtime
        n = 0
        with open(self.path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(self.offset)
            chunk = fh.read()
            self.offset = fh.tell()
        self.buf += chunk
        *lines, self.buf = self.buf.split("\n")
        if self.buf.strip():
            self.partial_reads += 1   # incomplete last line held back
        for ln in lines:
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except ValueError:
                self.bad_json += 1
                continue
            cls = classify(rec)
            rsid = cls["session_id"]
            if rsid and rsid != self.sid:
                self.foreign += 1
                continue
            self.selftest.observe(rec, cls)
            self.recs.append(cls)
            n += 1
        return n


# -- state engine -------------------------------------------------------------

def derive(tail: Tail, now: float) -> dict:
    """State from records + file facts alone. Pure w.r.t. the screen."""
    ev = []

    if not tail.exists():
        return {"state": "starting", "attrs": {"transcript": "absent"},
                "evidence": [{"channel": "transcript",
                              "signal": "file not created yet", "at": now}]}
    if not tail.recs:
        return {"state": "starting", "attrs": {"transcript": "empty"},
                "evidence": [{"channel": "transcript",
                              "signal": "no parsable records", "at": now}]}

    # bootstrap: the session is not usable until the mode/bridge records land
    kinds = {r["type"] for r in tail.recs}
    if not (kinds & {"mode", "bridge-session", "user", "assistant"}):
        return {"state": "starting", "attrs": {"transcript": "bootstrap"},
                "evidence": [{"channel": "transcript",
                              "signal": "bootstrap records only", "at": now}]}

    # walk records: pending tool_uses, last turn boundary, compaction
    pending = {}          # tool_use_id -> (name, index)
    last_prompt_i = -1
    last_turn_end_i = -1
    last_compact_i = -1
    last_denial = None
    for i, r in enumerate(tail.recs):
        for tid, name in r["tool_use"]:
            pending[tid] = (name, i)
        for tid, denied, kind in r["tool_results"]:
            pending.pop(tid, None)
            if denied:
                last_denial = (kind, r["ts"], i)
        if r["is_prompt"]:
            last_prompt_i = i
        if r["turn_end"]:
            last_turn_end_i = i
            pending.clear()       # a turn cannot end with live tool calls
        if r["compact"]:
            last_compact_i = i

    last = tail.recs[-1]
    last_i = len(tail.recs) - 1
    quiet_s = now - (tail.last_growth_at or now)
    ev.append({"channel": "transcript",
               "signal": "last_record type=%s subtype=%s" % (last["type"], last["subtype"]),
               "at": now})
    ev.append({"channel": "transcript",
               "signal": "quiet_for=%.1fs records=%d" % (quiet_s, len(tail.recs)),
               "at": now})

    # 1. compaction — busy, watchdog suppressed (design 2, C7)
    if last_compact_i > max(last_turn_end_i, last_prompt_i):
        return {"state": "busy",
                "attrs": {"compacting": True, "watchdog_suppressed": True},
                "evidence": ev + [{"channel": "transcript",
                                   "signal": "system/compact_boundary newest",
                                   "at": now}]}

    # 2. unresolved tool_use — the channel's blind window (see COVERAGE below)
    if pending:
        tid, (name, idx) = sorted(pending.items(), key=lambda kv: kv[1][1])[-1]
        ev.append({"channel": "transcript",
                   "signal": "unresolved tool_use %s (%s) for %.1fs" % (name, tid, quiet_s),
                   "at": now})
        if name in INPUT_TOOLS:
            # the transcript NAMES the tool — a discriminator the screen lacks
            return {"state": "waiting:input",
                    "attrs": {"tool": name, "inferred": True},
                    "evidence": ev + [{"channel": "transcript",
                                       "signal": "pending %s is an input tool" % name,
                                       "at": now}]}
        if quiet_s >= PERMISSION_SUSPECT_S:
            return {"state": "waiting:permission",
                    "attrs": {"tool": name, "inferred": True, "confidence": "low",
                              "discriminator": "none",
                              "ambiguous_with": "long-running foreground tool"},
                    "evidence": ev + [{"channel": "transcript",
                                       "signal": ("no record for %.1fs after tool_use; "
                                                  "transcript writes NOTHING while a "
                                                  "permission dialog is pending" % quiet_s),
                                       "at": now}]}
        return {"state": "busy", "attrs": {"tool": name, "tool_running": True},
                "evidence": ev}

    # 3. turn ended after the last prompt -> idle candidate
    if last_turn_end_i >= 0 and last_turn_end_i >= last_prompt_i and last_turn_end_i == last_i:
        attrs = {}
        if last_denial and last_denial[2] < last_turn_end_i:
            attrs["last_tool_denied"] = last_denial[0]
        return {"state": "idle", "attrs": attrs,
                "evidence": ev + [{"channel": "transcript",
                                   "signal": "system/turn_duration is newest record",
                                   "at": now}]}
    if last_turn_end_i >= 0 and last_turn_end_i > last_prompt_i:
        # trailing bookkeeping records (file-history-snapshot, ai-title...) after
        # the turn end are not work.
        tail_types = {r["type"] for r in tail.recs[last_turn_end_i + 1:]}
        if tail_types <= {"file-history-snapshot", "ai-title", "summary",
                          "last-prompt", "mode", "permission-mode", "bridge-session"}:
            return {"state": "idle", "attrs": {"trailing": sorted(tail_types)},
                    "evidence": ev + [{"channel": "transcript",
                                       "signal": "turn_duration + bookkeeping only",
                                       "at": now}]}

    # 3b. never prompted: session booted, no turn ever started -> idle.
    # DECLARED BLINDNESS: the trust dialog produces no record, so a session
    # sitting on the trust dialog is indistinguishable from a fresh idle one.
    # The launch verb therefore gates this on a screen check (SPEC rule 4).
    if last_prompt_i < 0 and last_turn_end_i < 0:
        return {"state": "idle",
                "attrs": {"never_prompted": True,
                          "blind_to": ["trust dialog", "theme/login picker"]},
                "evidence": ev + [{"channel": "transcript",
                                   "signal": "bootstrap complete, no prompt yet",
                                   "at": now}]}

    # 4. a prompt (or assistant text) with no turn end yet -> busy
    if quiet_s > STALE_AFTER_S:
        return {"state": "presumed_hung",
                "attrs": {"busy_asserted_for": round(quiet_s, 1)},
                "evidence": ev + [{"channel": "watchdog",
                                   "signal": "busy asserted, transcript quiet > %ds"
                                             % STALE_AFTER_S, "at": now}]}
    return {"state": "busy", "attrs": {}, "evidence": ev}


class Session:
    def __init__(self, workdir: Path, sid: str):
        self.id = sid
        self.workdir = workdir
        self.dir = workdir / ".transcript-watch" / sid
        self.sock = "tw-" + sid[:8]

    # -- tmux plumbing (launch/answer/send/screen only; never state) ---------
    def tmux(self, *args, timeout=TMUX_TIMEOUT_S):
        cmd = ["tmux", "-L", self.sock, "-f", "/dev/null", *args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def capture(self):
        try:
            r = self.tmux("capture-pane", "-p", "-t", self.id[:8], "-S", "-60")
        except subprocess.TimeoutExpired:
            return None
        return ANSI_RE.sub("", r.stdout) if r.returncode == 0 else None

    def alive(self) -> bool:
        try:
            return self.tmux("has-session", "-t", self.id[:8]).returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def save(self, meta: dict):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "meta.json").write_text(json.dumps(meta))

    def load(self) -> dict:
        return json.loads((self.dir / "meta.json").read_text())

    def tail(self) -> Tail:
        return Tail(transcript_path(self.workdir, self.id), self.id)


def find_session(workdir: Path, sid: str) -> Session:
    s = Session(workdir, sid)
    if not (s.dir / "meta.json").exists():
        die("unknown session id %s" % sid, 2)
    return s


def observe(s: Session, tail: Tail) -> dict:
    """One tick. Process channel outranks everything for `dead` (fusion rule 3)."""
    now = time.time()
    if not s.alive():
        rep = {"state": "dead", "attrs": {},
               "evidence": [{"channel": "process",
                             "signal": "tmux session gone", "at": now}]}
        tail.poll()
        rep["attrs"]["records_at_death"] = len(tail.recs)
        return rep
    tail.poll()
    return derive(tail, now)


def observe_settled(s: Session, ticks: int = STABLE_N) -> dict:
    """SPEC rule 1: idle is never decided from one observation — it must hold
    across >=STABLE_N polls with no new records."""
    tail = s.tail()
    rep = observe(s, tail)
    if rep["state"] != "idle":
        return rep
    for _ in range(ticks - 1):
        time.sleep(POLL_S)
        before = len(tail.recs)
        rep2 = observe(s, tail)
        if rep2["state"] != "idle" or len(tail.recs) != before:
            return rep2
        rep = rep2
    rep["evidence"].append({"channel": "transcript",
                            "signal": "stable x%d (no new records)" % ticks,
                            "at": time.time()})
    rep["attrs"]["selftest"] = tail.selftest.verdict()
    return rep


# -- commands -----------------------------------------------------------------

def cmd_launch(a):
    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    s = Session(workdir, sid)
    claude = shutil.which("claude")
    if not claude:
        die("claude not found on PATH", 5)
    # --session-id makes the transcript FILENAME known before the file exists.
    r = s.tmux("new-session", "-d", "-s", sid[:8], "-x", "220", "-y", "50",
               "-c", str(workdir), "%s --session-id %s" % (claude, sid), timeout=10)
    if r.returncode != 0:
        die("tmux launch failed: %s" % r.stderr.strip(), 5)
    s.save({"id": sid, "workdir": str(workdir), "created": time.time(),
            "compat": COMPAT_RANGE,
            "transcript": str(transcript_path(workdir, sid))})

    # SPEC rule 4 — trust dialog handled unconditionally, via SCREEN (the only
    # channel that can see it; declared as a coverage gap for this prototype).
    deadline = time.time() + TRANSCRIPT_WAIT_S
    trust_answered = False
    tail = s.tail()
    rep = {"state": "starting", "attrs": {}, "evidence": []}
    while time.time() < deadline:
        text = s.capture() or ""
        if TRUST_RE.search(text):
            time.sleep(0.7)
            s.tmux("send-keys", "-t", sid[:8], "Enter")
            trust_answered = True
            time.sleep(2.0)
            continue
        rep = observe(s, tail)
        if rep["state"] in ("idle", "dead"):
            break
        time.sleep(POLL_S)
    out = {"id": sid, "state": rep["state"], "trust_dialog_answered": trust_answered,
           "transcript": str(transcript_path(workdir, sid)),
           "transcript_exists": transcript_path(workdir, sid).exists()}
    print(json.dumps(out), flush=True)


def cmd_state(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    print(json.dumps(observe_settled(s)), flush=True)


def cmd_wait(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    targets = set(a.until.split(","))
    deadline = time.time() + a.timeout
    tail = s.tail()
    rep = {}
    while time.time() < deadline:
        rep = observe(s, tail)
        if rep["state"] in targets:
            rep["attrs"]["selftest"] = tail.selftest.verdict()
            print(json.dumps(rep), flush=True)
            return
        time.sleep(POLL_S)
    print(json.dumps({"error": "timeout", "last": rep}), flush=True)
    sys.exit(3)


def cmd_send(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    tail = s.tail()
    if not a.force:
        rep = observe_settled(s)
        if rep["state"] != "idle":
            print(json.dumps({"error": "refusing send in state %s" % rep["state"],
                              "report": rep}), flush=True)
            sys.exit(4)
    tail.poll()
    before = len(tail.recs)
    s.tmux("send-keys", "-t", s.id[:8], "-l", "--", a.text)
    time.sleep(0.3)
    t_send = time.time()
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    # dual verification (FMA 6.3): screen echo AND the transcript's own record
    time.sleep(1.0)
    screen_ok = a.text[:40] in (s.capture() or "")
    t_rec = None
    while time.time() - t_send < 15:
        tail.poll()
        if any(r["is_prompt"] and a.text[:30] in (r.get("prompt") or "")
               for r in tail.recs[before:]):
            t_rec = time.time()
            break
        time.sleep(0.2)
    print(json.dumps({
        "sent": True, "verified_on_screen": screen_ok,
        "verified_in_transcript": t_rec is not None,
        "transcript_append_lag_s": round(t_rec - t_send, 3) if t_rec else None,
    }), flush=True)


def cmd_answer(a):
    s = find_session(Path(a.workdir).resolve(), a.id)
    rep = observe(s, s.tail())
    if not (rep["state"].startswith("waiting:") or rep["state"] == "starting"):
        print(json.dumps({"error": "no dialog; state %s" % rep["state"],
                          "report": rep}), flush=True)
        sys.exit(4)
    for _ in range(a.option - 1):
        s.tmux("send-keys", "-t", s.id[:8], "Down")
        time.sleep(0.2)
    s.tmux("send-keys", "-t", s.id[:8], "Enter")
    print(json.dumps({"answered": a.option, "was": rep["state"]}), flush=True)


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


def cmd_dump(a):
    """Debug/evidence verb (not in SPEC): classified record stream + selftest."""
    s = find_session(Path(a.workdir).resolve(), a.id)
    tail = s.tail()
    tail.poll()
    for i, r in enumerate(tail.recs):
        print(json.dumps({"i": i, "type": r["type"], "subtype": r["subtype"],
                          "ts": r["ts"], "tool_use": r["tool_use"],
                          "tool_results": r["tool_results"],
                          "turn_end": r["turn_end"], "compact": r["compact"]}))
    print(json.dumps({"selftest": tail.selftest.verdict(),
                      "foreign_records": tail.foreign,
                      "bad_json": tail.bad_json,
                      "partial_line_reads": tail.partial_reads}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workdir", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("launch"); sp.set_defaults(f=cmd_launch)
    for name, f in [("state", cmd_state), ("wait", cmd_wait), ("send", cmd_send),
                    ("answer", cmd_answer), ("screen", cmd_screen),
                    ("kill", cmd_kill), ("dump", cmd_dump)]:
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
