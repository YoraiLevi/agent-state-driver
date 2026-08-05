#!/usr/bin/env python3
"""Comparative harness — races SPEC-conformant drivers through scripted scenarios.

The harness is the referee: it derives ground truth from its OWN observation
channels (direct tmux captures on the driver's socket + wall clock + the session
transcript), never from the driver under test. A driver is scored on:
  correctness  — did it report the expected state sequence
  latency      — t_detect - t_truth per transition
  honesty      — zero confident wrong states (silent misdetection)

Usage:
  python3 run.py --driver ../scrape-driver/driver.py [--driver ...] \
                 --scenarios S1,S2,S4,S6,S7 --out results/

Python 3.9+, stdlib only. Each (driver, scenario) runs in a fresh workdir.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

POLL = 0.5


def jrun(driver, workdir, *args, timeout=180):
    """Run a driver subcommand, return (parsed-last-json-line, exit code)."""
    cmd = [sys.executable, str(driver), "--workdir", str(workdir), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "{}"
    try:
        return json.loads(line), r.returncode
    except json.JSONDecodeError:
        return {"error": "unparseable", "raw": line}, r.returncode


class Truth:
    """Ground-truth observer: independent captures of the driver's tmux socket."""

    def __init__(self, sid):
        self.sock = f"scrape-{sid[:8]}"  # overridden per driver via meta
        self.sid = sid

    def find_socket(self, workdir):
        # driver-agnostic: find the newest meta.json under workdir and read conventions
        metas = sorted(Path(workdir).glob(".*/*/meta.json"))
        return metas

    @staticmethod
    def capture(sock, target):
        try:
            r = subprocess.run(["tmux", "-L", sock, "-f", "/dev/null",
                                "capture-pane", "-p", "-t", target, "-S", "-40"],
                               capture_output=True, text=True, timeout=5)
            return r.stdout if r.returncode == 0 else None
        except subprocess.TimeoutExpired:
            return None


def _socket_dir():
    # tmux default socket dir: $TMUX_TMPDIR or /tmp, subdir tmux-<uid>
    base = os.environ.get("TMUX_TMPDIR") or "/tmp"
    return Path(base) / f"tmux-{os.getuid()}"


def discover_session(workdir):
    """Find the driver's session id + tmux socket from its state dir.

    Prototype-agnostic by construction: a driver MAY record its socket in
    meta.json, otherwise we enumerate every socket in the tmux socket dir and
    ask which one owns the session. Hardcoding prefixes silently misjudged
    prototypes using an unlisted prefix (found 2026-08-05: C uses 'tw-').
    """
    for meta in sorted(Path(workdir).glob(".*/*/meta.json")):
        m = json.loads(meta.read_text())
        sid = m["id"]
        target = sid[:8]
        candidates = []
        if m.get("socket"):
            candidates.append(m["socket"])
        sd = _socket_dir()
        if sd.is_dir():
            # newest first: the live one is usually the most recent
            candidates += [p.name for p in
                           sorted(sd.iterdir(), key=lambda p: -p.stat().st_mtime)]
        for sock in candidates:
            try:
                probe = subprocess.run(["tmux", "-L", sock, "-f", "/dev/null",
                                        "has-session", "-t", target],
                                       capture_output=True, timeout=5)
            except subprocess.TimeoutExpired:
                continue
            if probe.returncode == 0:
                return sid, sock
        return sid, m.get("socket")
    return None, None


def snap(workdir, sid, lines=14):
    """Harness's own screen snapshot — evidence attached to any failed check.
    Independent of the driver under test (FMA: never trust the subject's report)."""
    _, sock = discover_session(workdir)
    if not sock:
        return None
    cap = Truth.capture(sock, sid[:8]) or ""
    return [ln for ln in cap.splitlines() if ln.strip()][-lines:]


def record(results, **kw):
    kw["at"] = time.time()
    results.append(kw)
    print(json.dumps(kw), flush=True)


# ---------------- scenarios ----------------

def s1_launch_to_idle(driver, workdir, results):
    t0 = time.time()
    rep, rc = jrun(driver, workdir, "launch")
    if rc != 0 or "id" not in rep:
        record(results, scenario="S1", event="launch_failed", detail=rep)
        return None
    sid = rep["id"]
    rep2, rc = jrun(driver, workdir, "wait", "--id", sid, "--until", "idle",
                    "--timeout", "90")
    record(results, scenario="S1", event="first_idle", ok=(rc == 0),
           t_truth=t0, t_detect=time.time(),
           delta_s=round(time.time() - t0, 1), state=rep2.get("state"))
    return sid


def s2_trivial_turn(driver, workdir, sid, results):
    _, sock = discover_session(workdir)
    t_send = time.time()
    rep, rc = jrun(driver, workdir, "send", "--id", sid,
                   "--text", "Reply with exactly: pong")
    if rc != 0:
        record(results, scenario="S2", event="send_refused", detail=rep)
        return
    # ground truth for busy: harness's own capture shows spinner-ish motion;
    # ground truth for done: two identical consecutive harness captures with pong
    rep_busy, _ = jrun(driver, workdir, "state", "--id", sid)
    record(results, scenario="S2", event="busy_report", state=rep_busy.get("state"),
           expected="busy", ok=rep_busy.get("state") == "busy")
    rep2, rc = jrun(driver, workdir, "wait", "--id", sid, "--until", "idle",
                    "--timeout", "90")
    t_idle_detect = time.time()
    truth_pong = False
    if sock:
        cap = Truth.capture(sock, sid[:8]) or ""
        truth_pong = "pong" in cap
    record(results, scenario="S2", event="turn_complete", ok=(rc == 0 and truth_pong),
           truth_pong_on_screen=truth_pong, t_truth=t_send,
           t_detect=t_idle_detect, delta_s=round(t_idle_detect - t_send, 1))


def s4_permission_deny(driver, workdir, sid, results):
    marker = f"probe-{uuid.uuid4().hex[:6]}.txt"
    # Never discard the send result: a refused send makes the subsequent wait
    # time out, and without this record the failure is indistinguishable from a
    # detection miss. (Found by this harness failing S4 on 2026-08-05.)
    sent, sent_rc = jrun(driver, workdir, "send", "--id", sid,
                         "--text", f"Run exactly this bash command: touch {marker}")
    record(results, scenario="S4", event="send", ok=(sent_rc == 0), detail=sent)
    if sent_rc != 0:
        record(results, scenario="S4", event="perm_detected", ok=False,
               skipped="send refused", screen=snap(workdir, sid))
        return
    rep, rc = jrun(driver, workdir, "wait", "--id", sid,
                   "--until", "waiting:permission", "--timeout", "60")
    t_detect = time.time()
    # ground truth: harness's own capture contains the dialog
    _, sock = discover_session(workdir)
    truth_dialog = False
    if sock:
        cap = Truth.capture(sock, sid[:8]) or ""
        truth_dialog = "Do you want to proceed" in cap or "No, and tell Claude" in cap
    ok = (rc == 0 and truth_dialog)
    record(results, scenario="S4", event="perm_detected", ok=ok,
           truth_dialog=truth_dialog, state=rep.get("state"), t_detect=t_detect,
           screen=None if ok else snap(workdir, sid))
    # deny = last numbered option; 3 on current build (harness knows the layout)
    jrun(driver, workdir, "answer", "--id", sid, "--option", "3")
    rep2, rc = jrun(driver, workdir, "wait", "--id", sid, "--until", "idle",
                    "--timeout", "60")
    denied = not (Path(workdir) / marker).exists()
    record(results, scenario="S4", event="deny_verified", ok=(rc == 0 and denied),
           file_absent=denied)


def agent_pid(sid):
    """The claude PID for a session, via the vendor session sidecar
    (docs/discovery-session-sidecar.md). None if no sidecar exists."""
    d = Path.home() / ".claude" / "sessions"
    if not d.is_dir():
        return None
    for f in d.glob("*.json"):
        try:
            if json.loads(f.read_text()).get("sessionId") == sid:
                return int(f.stem)
        except (ValueError, OSError):
            continue
    return None


def pid_alive(pid):
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def s6_kill_dead(driver, workdir, sid, results):
    jrun(driver, workdir, "send", "--id", sid,
         "--text", "Count from 1 to 100, one number per line.", "--force")
    time.sleep(3)
    _, sock = discover_session(workdir)
    pid = agent_pid(sid)
    t_kill = time.time()
    if sock:
        subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", "kill-server"],
                       capture_output=True, timeout=10)

    # GROUND TRUTH IS PROCESS DEATH, NOT THE KILL COMMAND RETURNING.
    # Measured 2026-08-05: the claude process outlives its terminal by ~1 s
    # (SIGHUP propagation). Scoring against t_kill made a *correct* driver look
    # wrong and rewarded one that reports "terminal gone" as "agent dead" — a
    # proxy that is outright false for a detached-but-live agent.
    t_truth = None
    if pid is not None:
        while time.time() - t_kill < 15:
            if pid_alive(pid) is False:
                t_truth = time.time()
                break
            time.sleep(0.05)
    if t_truth is None:
        t_truth = t_kill  # no sidecar: fall back, and say so in the record

    rep, _ = jrun(driver, workdir, "state", "--id", sid)
    t_detect = time.time()
    record(results, scenario="S6", event="dead_detected",
           ok=rep.get("state") == "dead", state=rep.get("state"),
           pid=pid, truth_source="pid_exit" if pid else "kill_return",
           t_truth=t_truth, t_detect=t_detect,
           term_to_proc_death_s=round(t_truth - t_kill, 2),
           delta_s=round(t_detect - t_truth, 2))


def s6b_premature_death(driver, workdir, sid, results):
    """Silent-misdetection probe: kill the terminal, then ask the driver for
    state IMMEDIATELY, while the agent process is provably still alive.
    A driver that answers 'dead' here is reporting a proxy as proof."""
    pid = agent_pid(sid)
    _, sock = discover_session(workdir)
    if pid is None or sock is None:
        record(results, scenario="S6b", event="skipped", ok=None,
               reason="no sidecar/socket")
        return
    # Make the window DETERMINISTIC instead of racing a ~1 s SIGHUP.
    # SIGSTOP the agent first: a stopped process cannot act on the terminal's
    # death, so it stays provably alive while its terminal is gone. This is not
    # an artificial case — it is exactly the shape of a detached or wedged agent,
    # which is the state a terminal-only liveness check misreports as `dead`.
    # (Two consecutive runs came back INCONCLUSIVE without this; a test that
    # cannot fail the defect it targets is not evidence.)
    os.kill(pid, signal.SIGSTOP)
    try:
        subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", "kill-server"],
                       capture_output=True, timeout=10)
        alive_before = pid_alive(pid)
        rep, _ = jrun(driver, workdir, "state", "--id", sid)
        alive_after = pid_alive(pid)
    finally:
        # never leak a stopped process
        try:
            os.kill(pid, signal.SIGCONT)
            time.sleep(0.5)
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    claimed_dead = rep.get("state") == "dead"
    if alive_before is not True:
        record(results, scenario="S6b", event="premature_death_claim", ok=None,
               inconclusive="process already dead before driver was asked",
               state=rep.get("state"))
        return
    if claimed_dead and alive_after is False:
        record(results, scenario="S6b", event="premature_death_claim", ok=None,
               inconclusive="process died during the driver call; window closed",
               state=rep.get("state"))
        return
    premature = claimed_dead and alive_after is True
    record(results, scenario="S6b", event="premature_death_claim",
           ok=not premature, premature=premature,
           pid_alive_before=alive_before, pid_alive_after=alive_after,
           state=rep.get("state"))


def s7_idle_no_false_busy(driver, workdir, sid, results, hold_s=60):
    t0 = time.time()
    bad = []
    while time.time() - t0 < hold_s:
        rep, _ = jrun(driver, workdir, "state", "--id", sid)
        if rep.get("state") not in ("idle",):
            bad.append({"at": round(time.time() - t0, 1), "state": rep.get("state")})
        time.sleep(5)
    record(results, scenario="S7", event="idle_hold", ok=not bad,
           false_transitions=bad, held_s=hold_s)


SCENARIOS = {"S1": None, "S2": s2_trivial_turn, "S4": s4_permission_deny,
             "S6": s6_kill_dead, "S6b": s6b_premature_death,
             "S7": s7_idle_no_false_busy}


def run_driver(driver: Path, scenarios, outdir: Path):
    results = []
    name = driver.parent.name
    workdir = outdir / f"run-{name}-{uuid.uuid4().hex[:6]}"
    workdir.mkdir(parents=True)
    print(f"=== {name} → {workdir}", flush=True)
    sid = s1_launch_to_idle(driver, workdir, results)
    if sid:
        # S7 before destructive scenarios; S6 always last
        # S6b and S6 are both terminal-destructive; S6b must run alone (it kills
        # the terminal to probe the premature-death claim). Prefer S6b when both
        # are requested only if S6 is absent.
        order = [s for s in ["S2", "S4", "S7", "S6b", "S6"] if s in scenarios]
        for s in order:
            try:
                SCENARIOS[s](driver, workdir, sid, results)
            except Exception as e:  # a scenario crash is data, not a harness abort
                record(results, scenario=s, event="scenario_exception", error=str(e))
        if "S6" not in scenarios:
            jrun(driver, workdir, "kill", "--id", sid)
    out = outdir / f"{name}.results.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in results) + "\n")
    ok = sum(1 for r in results if r.get("ok") is True)
    tot = sum(1 for r in results if "ok" in r)
    print(f"=== {name}: {ok}/{tot} checks ok → {out}", flush=True)
    return {"driver": name, "ok": ok, "total": tot, "file": str(out)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--driver", action="append", required=True)
    p.add_argument("--scenarios", default="S1,S2,S4,S7,S6")
    p.add_argument("--out", default="results")
    a = p.parse_args()
    outdir = Path(a.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    scen = set(a.scenarios.split(","))
    summary = [run_driver(Path(d).resolve(), scen, outdir) for d in a.driver]
    print(json.dumps({"summary": summary}, indent=2))


if __name__ == "__main__":
    main()
