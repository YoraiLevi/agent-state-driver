#!/usr/bin/env python3
"""Offline self-test for prototype B's state engine.

The state of this prototype is a PURE FUNCTION of the event log plus two clocks
(last-event age, process liveness), so the paths that are unsafe or slow to produce
live — a real hang, a 90 s idle wait, a compaction — are exercised here against
synthesised logs instead. Live coverage is reported separately; this file is not a
substitute for it, it is the part of the matrix a live run cannot reach cheaply.

Run: python3 selftest.py   (exit 0 = all pass)
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver  # noqa: E402

FAILED = []
CHECKS = []


def check(name, got, want):
    ok = got == want
    CHECKS.append(name)
    print("%-42s %-18s %s" % (name, got, "ok" if ok else "FAIL want=%s" % (want,)))
    if not ok:
        FAILED.append(name)


def log(*events):
    """events: (offset_seconds_ago, name, payload_dict_or_None)."""
    now = time.time()
    out = []
    for off, name, pl in events:
        raw = json.dumps(pl) if pl is not None else ""
        out.append({"at": now - off, "event": name,
                    "payload": pl, "payload_raw": raw})
    return out


def fake_session(tmp, events, last_age):
    """A Session whose channels are stubbed: log on disk, pid always alive."""
    s = driver.Session(Path(tmp), "selftest")
    s.dir.mkdir(parents=True, exist_ok=True)
    s.save({"id": "selftest", "workdir": tmp, "created": time.time() - 1000,
            "claude_pid": 1})
    s.read_events = lambda: (events, time.time() - last_age)
    s.claude_pid = lambda: 4242
    s.first_send_at = lambda: time.time() - 300
    s.capture = lambda: ""
    return s


def main():
    tmp = "/tmp/hook-sentinel-selftest"
    # stub the process channel: these cases are about the EVENT channel + clocks
    driver.pid_alive = lambda pid: True

    # -- pure log replay -------------------------------------------------------
    cases = [
        ("SessionStart -> idle", [(5, "SessionStart", {})], "idle"),
        ("UserPromptSubmit -> busy",
         [(9, "SessionStart", {}), (5, "UserPromptSubmit", {})], "busy"),
        ("PreToolUse -> busy",
         [(9, "UserPromptSubmit", {}), (5, "PreToolUse", {})], "busy"),
        ("PermissionRequest -> waiting:permission",
         [(9, "PreToolUse", {}), (5, "PermissionRequest", {})],
         "waiting:permission"),
        ("permission cleared by PostToolUse",
         [(9, "PermissionRequest", {}), (5, "PostToolUse", {})], "busy"),
        ("permission cleared by Stop",
         [(9, "PermissionRequest", {}), (5, "Stop", {})], "idle"),
        ("Stop -> idle",
         [(9, "UserPromptSubmit", {}), (5, "Stop", {"background_tasks": []})],
         "idle"),
        ("Notification permission_prompt",
         [(9, "UserPromptSubmit", {}),
          (5, "Notification", {"notification_type": "permission_prompt"})],
         "waiting:permission"),
        ("Notification idle_prompt -> waiting:input",
         [(9, "UserPromptSubmit", {}),
          (5, "Notification", {"notification_type": "idle_prompt"})],
         "waiting:input"),
        ("StopFailure -> idle",
         [(9, "UserPromptSubmit", {}), (5, "StopFailure", {})], "idle"),
        ("SessionEnd is NOT death (design 6.4)",
         [(9, "UserPromptSubmit", {}), (7, "Stop", {}), (5, "SessionEnd", {})],
         "idle"),
    ]
    for name, evs, want in cases:
        st, _, _ = driver.derive_from_events(log(*evs))
        check(name, st, want)

    st, attrs, _ = driver.derive_from_events(
        log((9, "UserPromptSubmit", {}),
            (5, "Stop", {"background_tasks": [{"id": "bash_1"}]})))
    check("Stop w/ background_tasks -> attr", attrs.get("background_work"), True)

    # -- clock-dependent paths (observe) --------------------------------------
    s = fake_session(tmp, log((300, "UserPromptSubmit", {})), last_age=300)
    check("busy + stale 300s -> presumed_hung", driver.observe(s)["state"],
          "presumed_hung")

    # S7: a 300 s-old idle must NOT trip the watchdog (watchdog gates on busy only)
    s = fake_session(tmp, log((305, "UserPromptSubmit", {}), (300, "Stop", {})),
                     last_age=300)
    check("idle + stale 300s -> stays idle", driver.observe(s)["state"], "idle")

    # compaction suppresses the watchdog (design 2 / C7)
    s = fake_session(tmp, log((320, "UserPromptSubmit", {}),
                              (300, "PreCompact", {})), last_age=300)
    rep = driver.observe(s)
    check("busy + PreCompact + stale -> busy", rep["state"], "busy")
    check("  ...flagged compaction", rep["attrs"].get("compaction"), True)
    s = fake_session(tmp, log((340, "UserPromptSubmit", {}),
                              (330, "PreCompact", {}), (300, "PostCompact", {})),
                     last_age=300)
    check("PostCompact re-arms watchdog", driver.observe(s)["state"],
          "presumed_hung")

    # hook liveness (Q1): a live process + a silent channel after a send = conflict
    s = fake_session(tmp, [], last_age=0)
    rep = driver.observe(s)
    check("no events after send -> conflict", rep["state"], "conflict")
    check("  ...reason", rep["attrs"].get("reason"), "hooks_never_fired")

    # process channel outranks everything for dead (SPEC rule 3)
    s = fake_session(tmp, log((1, "UserPromptSubmit", {})), last_age=1)
    s.claude_pid = lambda: None
    driver.pid_alive = lambda pid: False
    check("no pid -> dead", driver.observe(s)["state"], "dead")

    print("\n%d/%d passed" % (len(CHECKS) - len(FAILED), len(CHECKS)))
    if FAILED:
        print("FAILED: %s" % ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
