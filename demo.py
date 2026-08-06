#!/usr/bin/env python3
"""Guided demo — watch an agent's state be detected, live, with the evidence.

    uv run demo.py            # against a real Claude Code session (spends API turns)
    uv run demo.py --mock     # against the deterministic mock (free, no credentials)

Each step announces what it is about to do, what it observed, and WHICH CHANNEL
proved it — because "the tool said idle" is not the interesting part; "the tool
said idle, and here is the signal it read" is.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRIVER = ROOT / "prototypes" / "fused" / "driver.py"

BOLD, DIM, GREEN, YELLOW, CYAN, RED, OFF = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[36m", "\033[31m", "\033[0m")


def say(step, text):
    print("\n%s%s %s%s" % (BOLD, step, text, OFF), flush=True)


def note(text):
    print("   %s%s%s" % (DIM, text, OFF), flush=True)


def show_state(rep, expect=None):
    st = rep.get("state", "?")
    colour = GREEN if (expect is None or st == expect) else RED
    print("   → state: %s%s%s" % (colour + BOLD, st, OFF), flush=True)
    for k, v in (rep.get("attrs") or {}).items():
        if v not in (False, None):
            print("     %sattr%s %s = %s" % (DIM, OFF, k, v), flush=True)
    for e in (rep.get("evidence") or [])[:4]:
        print("     %sevidence%s [%s%s%s] %s"
              % (DIM, OFF, CYAN, e.get("channel"), OFF, e.get("signal")), flush=True)
    if expect and st != expect:
        print("   %s(expected %s — this is a real disagreement, not a script)%s"
              % (YELLOW, expect, OFF), flush=True)


def drive(workdir, *args, timeout=240):
    r = subprocess.run([sys.executable, str(DRIVER), "--workdir", str(workdir), *args],
                       capture_output=True, text=True, timeout=timeout)
    line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "{}"
    try:
        return json.loads(line), r.returncode
    except json.JSONDecodeError:
        return {"error": "unparseable", "raw": line}, r.returncode


def banner(mode):
    print("%s%s" % (BOLD, "=" * 74))
    print("  agent-state-driver — guided demo (%s)" % mode)
    print("=" * 74 + OFF)
    print("""
An AI agent in a terminal is a byte stream with no machine-readable state.
This demo drives one and shows each state being detected, with the channel
that proved it. Nothing below is scripted output — every line is a real
observation of a real process.""")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true",
                    help="drive the deterministic mock instead of the real CLI "
                         "(free, no credentials, no API turns)")
    ap.add_argument("--keep", action="store_true", help="do not kill the session at the end")
    a = ap.parse_args()

    if not a.mock and not shutil.which("claude"):
        print("claude not found on PATH — run with --mock for the free demo.")
        return 2

    banner("mock" if a.mock else "REAL Claude Code session — this spends API turns")

    workdir = Path(os.environ.get("TMPDIR", "/tmp")) / ("asd-demo-" + uuid.uuid4().hex[:6])
    workdir.mkdir(parents=True, exist_ok=True)
    note("workspace: %s" % workdir)

    if a.mock:
        print("\n%sMock mode drives prototypes/mockagent/mock_claude.py, which replays"
              % DIM)
        print("recorded 2.1.222 screen shapes and the vendor sidecar lifecycle.%s" % OFF)
        rc = subprocess.call([sys.executable,
                              str(ROOT / "prototypes/mockagent/portability_check.py")])
        print("\n%sThat is the same check the test suite runs. For the full state machine"
              % DIM)
        print("with a real agent, run without --mock.%s" % OFF)
        return rc

    # ---- 1. launch -----------------------------------------------------------
    say("[1/6]", "Launching a real Claude Code session in its own tmux server…")
    note("The trust dialog appears unconditionally — a project setting does NOT")
    note("suppress it — so the driver must handle it as part of startup.")
    t0 = time.time()
    rep, rc = drive(workdir, "launch")
    if rc != 0 or "id" not in rep:
        print("%slaunch failed: %s%s" % (RED, rep, OFF))
        return 1
    sid = rep["id"]
    note("session id %s   (%.1fs)" % (sid, time.time() - t0))
    show_state(rep)

    # ---- 2. idle -------------------------------------------------------------
    say("[2/6]", "Asking: is it idle?")
    note("Idle is NOT 'the ❯ prompt is visible' — that prompt is on screen during")
    note("generation too. Idle = busy-signal absent AND the screen has settled.")
    rep, _ = drive(workdir, "state", "--id", sid)
    show_state(rep, "idle")

    # ---- 3. busy -------------------------------------------------------------
    say("[3/6]", "Sending a prompt, then watching it go busy…")
    drive(workdir, "send", "--id", sid, "--text",
          "Count from 1 to 60, one number per line, with a short sentence about each.")
    # Poll FOR busy rather than sampling once: a short turn can finish inside the
    # driver's own settle window, and a demo that shows `idle` under a heading that
    # says `busy` teaches the wrong thing.
    rep, rc = drive(workdir, "wait", "--id", sid, "--until", "busy", "--timeout", "30")
    if rc != 0:
        note("turn finished before we could catch it busy — re-run to see this step")
    show_state(rep, "busy")
    note("A busy screen re-renders at least once a second (elapsed-time tickers),")
    note("which is why 'the screen changed' alone cannot mean busy — an idle")
    note("statusline clock moves it too. The regex is what carries the claim.")

    say("[3b/6]", "Waiting for the turn to finish…")
    rep, _ = drive(workdir, "wait", "--id", sid, "--until", "idle", "--timeout", "180")
    show_state(rep, "idle")

    # ---- 4. permission -------------------------------------------------------
    say("[4/6]", "Asking it to run a command that needs permission…")
    marker = "demo-%s.txt" % uuid.uuid4().hex[:4]
    drive(workdir, "send", "--id", sid, "--text",
          "Run exactly this bash command: touch %s" % marker)
    rep, _ = drive(workdir, "wait", "--id", sid,
                   "--until", "waiting:permission", "--timeout", "90")
    show_state(rep, "waiting:permission")
    note("Note the channel: the vendor writes status=waiting / waitingFor='permission")
    note("prompt' to ~/.claude/sessions/<pid>.json. No hook, no settings write —")
    note("this works even on a session you did not start.")

    # ---- 5. refuse to send while blocked ------------------------------------
    say("[5/6]", "Trying to send while it is blocked on a dialog (should be REFUSED)…")
    rep, rc = drive(workdir, "send", "--id", sid, "--text", "this should not go through")
    if rc != 0:
        print("   %s→ refused, correctly%s: %s" % (GREEN + BOLD, OFF, rep.get("error")))
    else:
        print("   %s→ NOT refused — that is a bug, and the demo just found it%s" % (RED, OFF))
    note("Sending into a blocked session is how orchestrators silently lose prompts.")

    say("[5b/6]", "Answering the dialog with 'No'…")
    drive(workdir, "answer", "--id", sid, "--option", "3")
    rep, _ = drive(workdir, "wait", "--id", sid, "--until", "idle", "--timeout", "90")
    show_state(rep, "idle")
    denied = not (workdir / marker).exists()
    print("   %s%s%s the file was %s — the denial actually took effect"
          % (GREEN if denied else RED, "✓" if denied else "✗", OFF,
             "never created" if denied else "CREATED"))

    # ---- 6. death ------------------------------------------------------------
    say("[6/6]", "Killing the terminal, then asking again…")
    note("Terminal-gone is NOT agent-dead: the process outlives its terminal by")
    note("~1s, and indefinitely if detached. Liveness is the agent PID, not tmux.")
    drive(workdir, "kill", "--id", sid)
    time.sleep(2)
    rep, _ = drive(workdir, "state", "--id", sid)
    show_state(rep, "dead")

    print("""
%s%s
  What you just watched
%s%s
  · six states detected on a real session, each with its proving channel
  · a send REFUSED because the agent was blocked — not silently dropped
  · a denial verified causally, by the file never appearing
  · death established from process exit, not from the terminal disappearing

  Where to go next:
    docs/INDEX.md                     — a map of the whole repo
    docs/discovery-session-sidecar.md — the vendor channel used in step 4
    PITFALLS.md                       — every trap that cost us a run
%s""" % (BOLD, "=" * 74, "=" * 74, OFF, OFF))

    if not a.keep:
        drive(workdir, "kill", "--id", sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
