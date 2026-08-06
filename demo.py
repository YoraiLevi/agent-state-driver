#!/usr/bin/env python3
"""Guided walkthrough — see an agent, see what the tool says about it, see why.

    uv run demo.py            # real Claude Code session (spends a few API turns)
    uv run demo.py --mock     # fake agent, free, no credentials
    uv run demo.py --no-pause # don't wait for Enter between steps

DESIGN NOTE (why this file looks the way it does)
-------------------------------------------------
The first version of this demo printed only the tool's conclusions. A reader
called it correctly: *"this reads more like a test."* And it was — because the
agent being observed was invisible. You cannot judge "the tool says busy" without
seeing the thing it is looking at.

So every step now shows THREE things in order:

    1. what is about to happen, in one plain sentence
    2. THE AGENT'S ACTUAL SCREEN, right now
    3. what the tool concluded, and which signal proved it

and then waits for you. Showing beats telling; a walkthrough is paced by the
person walking.
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

B, D, G, Y, C, R, M, OFF = ("\033[1m", "\033[2m", "\033[32m", "\033[33m",
                            "\033[36m", "\033[31m", "\033[35m", "\033[0m")
W = 78

PAUSE = True


def rule(ch="─"):
    print(D + ch * W + OFF, flush=True)


def step(n, total, title, why):
    print()
    rule("━")
    print("%s STEP %d/%d  %s%s" % (B, n, total, title, OFF))
    print("%s %s%s" % (D, why, OFF))
    rule("━")


def wait(prompt="Press Enter to continue"):
    if not PAUSE:
        time.sleep(1.2)
        return
    try:
        input("\n%s   ↵ %s …%s" % (D, prompt, OFF))
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nstopped.")


def show_screen(workdir, sid, lines=14, label="WHAT THE AGENT LOOKS LIKE RIGHT NOW"):
    """The actual TUI. This is the half the first version was missing."""
    r = subprocess.run([sys.executable, str(DRIVER), "--workdir", str(workdir),
                        "screen", "--id", sid, "--lines", str(lines)],
                       capture_output=True, text=True, timeout=60)
    print("\n%s┌─ %s %s%s" % (C, label, "─" * max(0, W - len(label) - 4), OFF))
    body = (r.stdout or "(could not read the screen)").rstrip().splitlines()
    for ln in body[-lines:]:
        print("%s│%s %s" % (C, OFF, ln[:W - 2]))
    print("%s└%s%s" % (C, "─" * (W - 1), OFF))


def show_verdict(rep, expect=None):
    st = rep.get("state", "?")
    good = expect is None or st == expect
    print("\n%s┌─ WHAT THE TOOL SAYS %s%s" % (M, "─" * (W - 22), OFF))
    print("%s│%s   state: %s%s%s" % (M, OFF, (G if good else R) + B, st, OFF))
    for k, v in (rep.get("attrs") or {}).items():
        if v not in (False, None):
            print("%s│%s     %s%s = %s%s" % (M, OFF, D, k, v, OFF))
    ev = rep.get("evidence") or []
    if ev:
        print("%s│%s   how it knows:" % (M, OFF))
        for e in ev[:4]:
            print("%s│%s     %s[%s]%s %s"
                  % (M, OFF, C, e.get("channel"), OFF, e.get("signal")))
    print("%s└%s%s" % (M, "─" * (W - 1), OFF))
    if not good:
        print("%s   (expected %s — a real disagreement, not a script)%s" % (Y, expect, OFF))


def drive(workdir, *args, timeout=240):
    r = subprocess.run([sys.executable, str(DRIVER), "--workdir", str(workdir), *args],
                       capture_output=True, text=True, timeout=timeout)
    line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "{}"
    try:
        return json.loads(line), r.returncode
    except json.JSONDecodeError:
        return {"error": "unparseable", "raw": line}, r.returncode


def intro(mock):
    print("%s%s" % (B, "═" * W))
    print("  agent-state-driver — guided walkthrough")
    print("═" * W + OFF)
    print("""
An AI agent in a terminal is just a stream of text. Nothing in it says
"I am busy" or "I am stuck waiting for you". So automation guesses — it
sleeps 30 seconds and hopes.

This tool answers the question properly. Over the next few minutes you will
watch it do that on a %s agent: you see the agent's screen, then you see
what the tool concluded, then you see the signal it used.

Nothing here is scripted output. Every screen is captured live.""" % (
        "FAKE (free)" if mock else "REAL, live"))
    if not mock:
        print("%s\nThis launches a real Claude session and spends a few API turns.%s"
              % (Y, OFF))


def watch_hint(workdir, sid):
    """Tell the reader how to watch it live in another terminal. The session is
    a normal tmux server — there is no reason to keep that a secret."""
    meta = next(Path(workdir).glob(".fused/*/meta.json"), None)
    sock = None
    if meta:
        try:
            sock = json.loads(meta.read_text()).get("socket")
        except (OSError, ValueError):
            pass
    if sock:
        print("\n%s   Want to watch it live? In ANOTHER terminal, run:%s" % (D, OFF))
        print("     %stmux -L %s attach -t %s%s" % (B, sock, sid[:8], OFF))
        print("     %s(detach again with Ctrl-B then D — closing it would kill the agent)%s"
              % (D, OFF))


def main():
    global PAUSE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true", help="fake agent; free, no credentials")
    ap.add_argument("--no-pause", action="store_true", help="run without waiting for Enter")
    ap.add_argument("--keep", action="store_true", help="leave the session running at the end")
    a = ap.parse_args()
    PAUSE = not a.no_pause

    if not a.mock and not shutil.which("claude"):
        print("claude not found on PATH — try:  uv run demo.py --mock")
        return 2

    intro(a.mock)
    wait("Press Enter to start")

    workdir = Path(os.environ.get("TMPDIR", "/tmp")) / ("asd-demo-" + uuid.uuid4().hex[:6])
    workdir.mkdir(parents=True, exist_ok=True)

    if a.mock:
        return run_mock(workdir)
    return run_real(workdir, a)


# ---------------------------------------------------------------- real agent

def run_real(workdir, a):
    TOTAL = 6

    step(1, TOTAL, "Start an agent",
         "Claude always asks 'do you trust this folder?' on a new directory. "
         "The tool answers it for you, because automation can't stop for that.")
    print("\n   launching…", flush=True)
    rep, rc = drive(workdir, "launch")
    if rc != 0 or "id" not in rep:
        print("%slaunch failed: %s%s" % (R, rep, OFF))
        return 1
    sid = rep["id"]
    print("   %sagent started%s  (session %s)" % (G, OFF, sid[:8]))
    show_screen(workdir, sid)
    watch_hint(workdir, sid)
    wait()

    step(2, TOTAL, "Ask: is it free?",
         "Look at the screen above — the ❯ prompt is showing. That is NOT proof "
         "it is free: that same prompt is on screen while it is thinking.")
    rep, _ = drive(workdir, "state", "--id", sid)
    show_verdict(rep, "idle")
    print("\n%s   It said idle because a busy-marker was ABSENT and the screen had"
          "\n   stopped changing — not because it saw a prompt.%s" % (D, OFF))
    wait()

    step(3, TOTAL, "Give it work and catch it mid-thought",
         "We send a prompt, then ask again immediately. The screen will look "
         "different — and so will the answer.")
    drive(workdir, "send", "--id", sid, "--text",
          "Count from 1 to 60, one number per line, with a short sentence about each.")
    rep, rc = drive(workdir, "wait", "--id", sid, "--until", "busy", "--timeout", "30")
    show_screen(workdir, sid)
    show_verdict(rep, "busy")
    wait()

    step(4, TOTAL, "Wait for it to finish",
         "Not by sleeping — by watching until the busy marker goes away and the "
         "screen settles.")
    rep, _ = drive(workdir, "wait", "--id", sid, "--until", "idle", "--timeout", "180")
    show_screen(workdir, sid)
    show_verdict(rep, "idle")
    wait()

    step(5, TOTAL, "The one that matters: it gets stuck, and refuses your next prompt",
         "We ask it to run a command. Claude stops and asks permission. Watch "
         "what happens when we then try to send it something else.")
    marker = "demo-%s.txt" % uuid.uuid4().hex[:4]
    drive(workdir, "send", "--id", sid, "--text",
          "Run exactly this bash command: touch %s" % marker)
    rep, _ = drive(workdir, "wait", "--id", sid,
                   "--until", "waiting:permission", "--timeout", "90")
    show_screen(workdir, sid)
    show_verdict(rep, "waiting:permission")
    print("\n%s   Now we try to send a prompt anyway — the thing normal automation"
          "\n   does, which quietly loses the prompt:%s" % (D, OFF))
    rep2, rc2 = drive(workdir, "send", "--id", sid, "--text", "this should not go through")
    if rc2 != 0:
        print("\n   %s✓ REFUSED%s  — %s" % (G + B, OFF, rep2.get("error")))
        print("   %sYour prompt was not typed into a dialog box and lost.%s" % (D, OFF))
    else:
        print("\n   %s✗ NOT refused — that is a bug, and this walkthrough just found it%s"
              % (R, OFF))
    wait()

    print("\n   Answering the dialog with 'No'…", flush=True)
    drive(workdir, "answer", "--id", sid, "--option", "3")
    rep, _ = drive(workdir, "wait", "--id", sid, "--until", "idle", "--timeout", "90")
    show_verdict(rep, "idle")
    denied = not (workdir / marker).exists()
    print("   %s%s%s we checked the file %s was never created — so the refusal"
          "\n     really took effect. We did not take the agent's word for it."
          % (G if denied else R, "✓" if denied else "✗", OFF, marker))
    wait()

    step(6, TOTAL, "Kill it, and notice the difference between gone and dead",
         "We close the terminal. A terminal closing is NOT the same as the agent "
         "dying — it outlives its terminal by about a second, and forever if "
         "detached. The tool checks the actual process.")
    drive(workdir, "kill", "--id", sid)
    time.sleep(2)
    rep, _ = drive(workdir, "state", "--id", sid)
    show_verdict(rep, "dead")

    outro()
    if not a.keep:
        drive(workdir, "kill", "--id", sid)
    return 0


# ---------------------------------------------------------------- fake agent

def run_mock(workdir):
    print("\n%sThe fake agent replays screens recorded from a real Claude session,"
          "\nso the detector sees exactly the shapes it would see live.%s" % (D, OFF))
    wait("Press Enter to run the checks")
    rc = subprocess.call([sys.executable,
                          str(ROOT / "prototypes/mockagent/portability_check.py")])
    print("\n%sThat exercised the detector against every state. To watch the full"
          "\nwalkthrough on a real agent:  uv run demo.py%s" % (D, OFF))
    return rc


def outro():
    print("""
%s%s
  What you just watched
%s%s
  · the agent's real screen at every step, next to what the tool concluded
  · "idle" proven by a missing busy-marker + a settled screen — not by a prompt
  · a prompt REFUSED because the agent was stuck on a dialog, instead of
    being typed into the void
  · a denial checked against the filesystem, not taken on the agent's word
  · "dead" established from the process exiting, not the terminal closing

  Where next:
    %sdocs/INDEX.md%s                     a map of the repo
    %sPITFALLS.md%s                       every trap that cost us a run
    %suv run pytest%s                     58 tests, no credentials, no cost
%s""" % (B, "═" * W, "═" * W, OFF, B, OFF, B, OFF, B, OFF, OFF))


if __name__ == "__main__":
    sys.exit(main())
