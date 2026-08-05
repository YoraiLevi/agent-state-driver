#!/usr/bin/env python3
"""A deterministic stand-in for the Claude Code TUI.

WHY THIS EXISTS
---------------
Two reasons, and the second matters more than the first.

1. Cross-platform proof without shipping credentials. Verifying the drivers on
   Linux/Windows with the real CLI would mean putting the user's OAuth token into
   a container. The mock lets us prove the *detection logic* is platform-portable
   without that, and we declare honestly what it does and does not prove.

2. A zero-cost, deterministic regression fixture. Every finding in
   docs/.research/empirical/ was bought with real API turns and is not repeatable
   on demand. The mock replays the exact rendered shapes those probes recorded —
   spinner forms, the trust dialog, the permission dialog, the statusline
   wall-clock that caused the live `sidecar=idle screen=busy` conflict — so a
   detector regression fails in milliseconds instead of going unnoticed.

WHAT IT REPRODUCES (all copied from live captures, 2.1.222, 2026-08-05)
  * the unconditional trust dialog, with its 2.1.222 copy
  * `✽ Deciphering… (3s · ↓ 150 tokens)` spinner + per-second elapsed ticker
  * `⎿  Running… (26s · timeout 45s)` tool-run line
  * the past-tense completion form `✻ Cogitated for 45s` (the glyph trap)
  * the Bash permission dialog with its real option rows
  * a statusline containing a live wall-clock — the false-busy source
  * the vendor session sidecar ~/.claude/sessions/<pid>.json with status/waitingFor

WHAT IT DOES NOT PROVE
  Real-CLI behavior on the target OS. It proves the driver's parsing, fusion,
  timing and process handling are portable. Real-claude-on-Linux stays declared
  UNVERIFIED until a Linux host with credentials is available.

Usage: run it as a tmux pane command, exactly like `claude`:
    mock_claude.py --session-id <uuid> [--sessions-dir DIR]
Type a prompt + Enter. A prompt containing "touch" raises a permission dialog.
"""

import argparse
import json
import os
import sys
import threading
import time
import uuid

SPINNER = "✢✳✶✽✻"
VERBS = ["Clauding", "Deciphering", "Marinating", "Simmering", "Hullaballooing"]

state = {"phase": "trust", "t0": time.time(), "started": time.time(),
         "last_reply": "", "dialog_cmd": "", "tokens": 0}
lock = threading.Lock()


class Sidecar:
    """Mirrors the vendor sidecar contract, including its two sharp edges:
    it is edge-triggered (timestamp does not advance while a state persists),
    and a clean exit DELETES the file."""

    def __init__(self, d, sid):
        self.dir = d
        self.sid = sid
        self.path = os.path.join(d, "%d.json" % os.getpid())
        os.makedirs(d, exist_ok=True)
        self.status = None
        self.write("idle")

    def write(self, status, waiting_for=None):
        if status == self.status:
            return                      # edge-triggered: no refresh while unchanged
        self.status = status
        now = int(time.time() * 1000)
        doc = {"pid": os.getpid(), "sessionId": self.sid, "cwd": os.getcwd(),
               "startedAt": int(state["started"] * 1000), "version": "2.1.222-mock",
               "kind": "interactive", "entrypoint": "cli", "status": status,
               "updatedAt": now, "statusUpdatedAt": now}
        if waiting_for:
            doc["waitingFor"] = waiting_for
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(doc, f)
        os.replace(tmp, self.path)

    def remove(self):
        try:
            os.remove(self.path)
        except OSError:
            pass


def render():
    """Full-screen repaint, like the real TUI (normal buffer, no alt screen —
    verified: Claude Code does not use the alternate screen)."""
    with lock:
        ph, t0 = state["phase"], state["t0"]
        reply, cmd = state["last_reply"], state["dialog_cmd"]
        toks = state["tokens"]
    el = int(time.time() - t0)
    # Repaint IN PLACE: cursor home, then erase-to-end-of-line per row, then
    # erase-below. Using \x1b[2J instead would scroll each frame into tmux's
    # history, so a scrollback capture would carry stale busy frames — which is
    # not how the real TUI behaves (it does not use the alternate screen and
    # does not push a frame per second into history).
    out = ["\x1b[H", "Welcome to Claude Code (mock)", ""]

    if ph == "trust":
        out += [" Quick safety check: Is this a project you created or one you trust?",
                " ❯ 1. Yes, I trust this folder", "   2. No, exit",
                " Enter to confirm · Esc to cancel"]
    elif ph == "permission":
        out += ["⏺ Bash(%s)" % cmd, "  ⎿  Waiting…", "-" * 70,
                " Bash command", "   %s" % cmd, " Do you want to proceed?",
                " ❯ 1. Yes",
                " 　 2. Yes, and always allow access to this dir from this project",
                "   3. No", " Esc to cancel · Tab to amend"]
    elif ph == "busy":
        g = SPINNER[el % len(SPINNER)]
        v = VERBS[(el // 7) % len(VERBS)]
        out += ["%s %s… (%ds · ↓ %d tokens)" % (g, v, el, toks)]
    elif ph == "tool":
        out += ["⏺ Bash(sleep-like tool)",
                "  ⎿  Running… (%ds · timeout 45s)" % el,
                "     (ctrl+b ctrl+b (twice) to run in background)",
                "%s %s… (%ds · ↓ %d tokens)" % (SPINNER[el % len(SPINNER)],
                                                VERBS[0], el, toks)]
    else:  # idle
        if reply:
            out += ["⏺ %s" % reply, "✻ Cogitated for %ds" % max(1, el)]
        out += ["❯ "]

    # The statusline: byte-identical to itself EXCEPT a live wall-clock. This is
    # the false-busy source that made a screen-hash detector disagree with the
    # sidecar on a genuinely idle session.
    out += ["-" * 70,
            "  $0.00 | wall %ds | API 0s | mock" % int(time.time() - state["started"])]
    body = "\r\n".join(ln + "\x1b[K" for ln in out)   # erase to EOL per row
    sys.stdout.write(body + "\r\n\x1b[J")             # erase everything below
    sys.stdout.flush()


def painter():
    while True:
        render()
        time.sleep(1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", default=str(uuid.uuid4()))
    ap.add_argument("--sessions-dir",
                    default=os.path.join(os.path.expanduser("~"), ".claude", "sessions"))
    ap.add_argument("--busy-seconds", type=float, default=4.0)
    a = ap.parse_args()

    sc = Sidecar(a.sessions_dir, a.session_id)
    threading.Thread(target=painter, daemon=True).start()

    try:
        for line in sys.stdin:
            text = line.strip()
            if text in ("/exit", "/quit"):
                break
            with lock:
                if state["phase"] == "trust":
                    state.update(phase="idle", t0=time.time())
                    sc.write("idle")
                    continue
                if state["phase"] == "permission":
                    # any input answers the dialog
                    state.update(phase="idle", t0=time.time(),
                                 last_reply="(denied)" if text == "3" else "(allowed)")
                    sc.write("idle")
                    continue
            if not text:
                continue
            if "touch" in text:
                with lock:
                    state.update(phase="permission", t0=time.time(), dialog_cmd=text)
                sc.write("waiting", "permission prompt")
                continue
            with lock:
                state.update(phase="tool" if "sleep" in text else "busy",
                             t0=time.time(), tokens=0)
            sc.write("busy")
            end = time.time() + a.busy_seconds
            while time.time() < end:
                with lock:
                    state["tokens"] += 37
                time.sleep(0.5)
            with lock:
                state.update(phase="idle", t0=time.time(), last_reply="pong")
            sc.write("idle")
    except KeyboardInterrupt:
        pass
    finally:
        sc.remove()   # clean exit deletes the sidecar, like the real CLI


if __name__ == "__main__":
    main()
