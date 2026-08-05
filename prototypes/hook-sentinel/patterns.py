"""Version-pinned pattern/mapping sets for the hook channel (prototype B).

Two kinds of pinned knowledge live here:

1. HOOK_STATE_MAP — event-name -> state effect. This is *documented* vendor surface
   (code.claude.com/docs/en/hooks, Q5) rather than UI copy, so it drifts far slower
   than the screen literals in prototype A. It is still versioned: an event name that
   disappears from a future build makes this prototype's channel go quiet, which the
   liveness rule (Q1) turns into a loud `conflict`, never a guess.

2. Screen literals — used by prototype B ONLY for *driving* (the launch trust dialog
   and the `answer` verb) and for the SPEC rule 6 self-test cross-check. State
   decisions never read them.

Sources: Q1 (retrofit protocol, stop_hook_summary oracle), Q5 (event inventory,
hook types), Q7 (trust-dialog copy on 2.1.222). Verified live on claude 2.1.222 macOS.
"""

import re

COMPAT_RANGE = ("2.1.222", "2.1.222")  # [min, max] verified

# --- hook channel ------------------------------------------------------------
# Events we install. Order is irrelevant; membership is the contract.
# "busy_refine" events do not change the coarse state, they only refresh evidence
# (and therefore the staleness watchdog).
HOOK_EVENTS = (
    "SessionStart",       # session ready
    "UserPromptSubmit",   # -> busy (turn started)
    "PreToolUse",         # -> busy (refinement); clears a stale permission latch
    "PostToolUse",        # -> busy (refinement); clears a stale permission latch
    "PermissionRequest",  # -> waiting:permission  (PASSIVE: emits no decision)
    "PermissionDenied",   # clears the permission latch fast
    "Notification",       # -> waiting:input / agent_completed, build-dependent
    "Stop",               # -> idle candidate; payload carries background_tasks
    "SessionEnd",         # NOT death (fires on /clear too — design 6.4)
    "PreCompact",         # suppress staleness watchdog
    "PostCompact",        # resume staleness watchdog
)

# Events whose arrival clears a waiting:permission latch (SPEC/brief: permission is
# cleared by the next PreToolUse/PostToolUse/Stop).
PERMISSION_CLEARING = ("PreToolUse", "PostToolUse", "Stop", "PermissionDenied",
                       "UserPromptSubmit")

# Notification payload classification. Sets, not single strings (C4).
NOTIFY_INPUT = [
    re.compile(r"waiting for your input", re.I),
    re.compile(r"needs your (?:input|permission)", re.I),
    re.compile(r"is waiting", re.I),
]
NOTIFY_PERMISSION = [
    re.compile(r"needs your permission", re.I),
    re.compile(r"permission to use", re.I),
]

# --- screen literals: DRIVING ONLY (never a state decision in prototype B) ----
TRUST_DIALOG = [
    re.compile(r"Quick safety check: Is this a project you created"),
    re.compile(r"Yes, I trust this folder"),
    re.compile(r"Do you trust the files in this folder"),
    re.compile(r"Yes, proceed"),
]
STARTING_SCREENS = [
    re.compile(r"Choose the text style"),
    re.compile(r"Select login method"),
]
# Used only by the SPEC rule 6 self-test: when the hook channel PROVES a permission
# dialog was rendered (PermissionRequest fired) and none of these matched the screen,
# the literal set is stale and must fail loudly rather than degrade silently.
PERMISSION_DIALOG = [
    re.compile(r"No, and tell Claude what to do differently"),
    re.compile(r"Do you want to (?:make this edit|proceed)"),
    re.compile(r"Yes, allow all .* this session"),
    re.compile(r"Yes, and (?:don't|do not) ask again"),
]


def classify_notification(text: str) -> str:
    """-> 'permission' | 'input' | 'other'."""
    if any(p.search(text) for p in NOTIFY_PERMISSION):
        return "permission"
    if any(p.search(text) for p in NOTIFY_INPUT):
        return "input"
    return "other"


def screen_has(kind: str, text: str) -> bool:
    sets = {"trust": TRUST_DIALOG, "starting": STARTING_SCREENS,
            "permission": PERMISSION_DIALOG}
    return any(p.search(text) for p in sets[kind])
