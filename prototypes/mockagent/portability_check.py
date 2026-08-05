#!/usr/bin/env python3
"""Cross-platform portability check: drive the mock agent through the state
machine and assert each detector reads the right state.

Runs anywhere with tmux + python3, no credentials, no API cost. Its purpose is
narrow and stated: prove the driver's PARSING, FUSION, TIMING and PROCESS
handling behave identically across OSes. It does NOT prove real-CLI behavior on
the target OS — see mock_claude.py's docstring.

Usage: python3 portability_check.py
Exit 0 = all checks passed.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOCK = HERE / "mock_claude.py"

# Exercise the SHIPPED detector, not a copy of it.
# An earlier version of this check reimplemented the busy predicate inline, so
# patterns.py could have been deleted and the check would still have printed
# 15/15 — while three documents claimed it proved the drivers portable. An
# adversarial review caught that (2026-08-05). The import below is what makes
# the claim true: a regression in patterns.py now fails this check.
sys.path.insert(0, str(HERE.parent / "scrape-driver"))
from patterns import classify_screen, tail_region  # noqa: E402


def sh(*args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def tmux(sock, *args, timeout=15):
    return sh("tmux", "-L", sock, "-f", "/dev/null", *args, timeout=timeout)


def capture(sock, target, scrollback=True):
    args = ["capture-pane", "-p", "-t", target]
    if scrollback:
        args += ["-S", "-40"]
    r = tmux(sock, *args)
    return r.stdout if r.returncode == 0 else ""


def tail(text, lines=15):
    """The present moment on screen. A scrollback capture contains spinner lines
    from earlier frames; matching liveness over it reports busy on an idle
    session (design C3). This check found exactly that defect in the drivers."""
    keep = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(keep[-lines:])


def check(name, got, want, results):
    ok = got == want
    results.append({"check": name, "want": want, "got": got, "ok": ok})
    print("%-34s want=%-20s got=%-20s %s" %
          (name, want, got, "ok" if ok else "FAIL"), flush=True)
    return ok


def run_mock_checks(results):
    """Drive the mock directly and assert the RENDERED SHAPES are what the
    detectors were built against. If this fails, every downstream conclusion
    about a real session is suspect on this platform."""
    sock = "mockchk-" + uuid.uuid4().hex[:6]
    sid = str(uuid.uuid4())
    workdir = Path(os.environ.get("TMPDIR", "/tmp")) / ("mockchk-" + uuid.uuid4().hex[:6])
    workdir.mkdir(parents=True, exist_ok=True)
    # Sidecars go in a THROWAWAY dir, never the user's real ~/.claude/sessions.
    # An interrupted run would otherwise leave a synthetic kind:"interactive"
    # file in the directory a real orchestrator polls (found by review).
    sessions = workdir / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    cmd = "%s %s --session-id %s --sessions-dir %s" % (
        sys.executable, MOCK, sid, sessions)
    tmux(sock, "new-session", "-d", "-s", "m", "-x", "200", "-y", "50",
         "-c", str(workdir), cmd)
    try:
        time.sleep(2)
        cap = capture(sock, "m")
        check("detector: trust_dialog", classify_screen(cap)["trust_dialog"], True,
              results)

        def sidecar():
            for f in sessions.glob("*.json"):
                try:
                    d = json.loads(f.read_text())
                    if d.get("sessionId") == sid:
                        return d
                except (ValueError, OSError):
                    pass
            return {}

        check("sidecar exists at startup", bool(sidecar()), True, results)
        tmux(sock, "send-keys", "-t", "m", "Enter")
        time.sleep(2)
        check("detector: prompt_mark", classify_screen(capture(sock, "m"))["prompt_mark"],
              True, results)
        check("sidecar idle", sidecar().get("status"), "idle", results)

        # statusline wall-clock must move while IDLE — the false-busy source.
        a = capture(sock, "m")
        time.sleep(2.0)
        b = capture(sock, "m")
        check("idle screen moves (wall-clock)", a != b, True, results)

        tmux(sock, "send-keys", "-t", "m", "-l", "say hello")
        tmux(sock, "send-keys", "-t", "m", "Enter")
        time.sleep(1.5)
        sig = classify_screen(capture(sock, "m"))   # THE SHIPPED DETECTOR
        check("detector: spinner_busy", sig["spinner_busy"], True, results)
        check("sidecar busy", sidecar().get("status"), "busy", results)
        time.sleep(5)
        cap = capture(sock, "m")
        sig = classify_screen(cap)
        check("completion form present", "Cogitated for" in tail_region(cap), True,
              results)
        # the glyph trap: past-tense completion must NOT read as busy
        check("detector: completion not busy", sig["spinner_busy"], False, results)
        check("detector: completion_line seen", sig["completion_line"], True, results)
        check("sidecar back to idle", sidecar().get("status"), "idle", results)

        tmux(sock, "send-keys", "-t", "m", "-l", "touch probe.txt")
        tmux(sock, "send-keys", "-t", "m", "Enter")
        time.sleep(2)
        cap = capture(sock, "m")
        sig = classify_screen(cap)
        check("detector: permission_dialog", sig["permission_dialog"], True, results)
        check("sidecar waiting", sidecar().get("status"), "waiting", results)
        check("sidecar waitingFor", sidecar().get("waitingFor"), "permission prompt",
              results)

        tmux(sock, "send-keys", "-t", "m", "-l", "3")
        tmux(sock, "send-keys", "-t", "m", "Enter")
        time.sleep(2)
        check("sidecar cleared after answer", sidecar().get("status"), "idle", results)

        tmux(sock, "send-keys", "-t", "m", "-l", "/exit")
        tmux(sock, "send-keys", "-t", "m", "Enter")
        time.sleep(2)
        check("sidecar deleted on clean exit", bool(sidecar()), False, results)
    finally:
        tmux(sock, "kill-server")


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    results = []
    print("platform:", sys.platform, "| python", ".".join(map(str, sys.version_info[:3])))
    print("tmux:", sh("tmux", "-V").stdout.strip())
    run_mock_checks(results)
    bad = [r for r in results if not r["ok"]]
    print("\n%d/%d checks passed" % (len(results) - len(bad), len(results)))
    out = Path(os.environ.get("PORTCHECK_OUT", "")) if os.environ.get("PORTCHECK_OUT") \
        else None
    if out:
        out.write_text(json.dumps({"platform": sys.platform, "results": results},
                                  indent=2))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
