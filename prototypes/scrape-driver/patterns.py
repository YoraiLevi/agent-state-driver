"""Version-pinned screen pattern sets for Claude Code.

Every pattern here is a HEURISTIC over unversioned vendor UI copy (design FMA 6.1).
COMPAT_RANGE declares the builds these were verified against; the self-test contract
(SPEC rule 6) requires a loud failure when a session provably rendered a dialog and
no member of the relevant set matched.

Sources: Q7/Q8 probes + q7-q8-reconciliation (docs/.research/empirical/), verified live
on claude 2.1.222 macOS. Glyph sets extend operonlab's 8-glyph observation (Q6).
"""

import re

COMPAT_RANGE = ("2.1.222", "2.1.222")  # [min, max] verified

# --- busy composite, leg 1: spinner-verb line ---------------------------------
# `✽ Deciphering… (30s · ↓ 150 tokens)` / `✢ Clauding… (1s)`  — BUSY
# `✻ Cogitated for 45s`                                        — NOT busy (past tense)
# Glyph class deliberately wide; the discriminator is `…` + `(<N>s`.
SPINNER_BUSY = re.compile(r"^\s*[✢✳✶✽✻·∗*+~≈∴]\s+\S+…\s*\(\d+s", re.M)

# `⎿  Running… (26s · timeout 45s)` — tool-level busy
TOOL_RUNNING = re.compile(r"⎿\s+Running…\s*\(\d+s", re.M)

# Past-tense completion forms — NOT-gate (FMA 6.1 glyph trap)
COMPLETION_LINE = re.compile(r"^\s*[✢✳✶✽✻·∗*+~≈∴]\s+\w+ed\s+for\s+\d+s", re.M)

# --- idle attributes -----------------------------------------------------------
BACKGROUND_WORK = re.compile(r"\d+\s+shell(?:s)?\s+still\s+running")

# --- dialog literal sets (waiting states) --------------------------------------
# Sets, not single strings (C4). Each entry: (regex, dialog_kind).
PERMISSION_DIALOG = [
    # 2.1.222 Bash-command dialog, verified live. NOTE (found by prototype B,
    # 2026-08-05): of the four literals originally taken from prior art, ONLY
    # "Do you want to proceed" actually matched this build. The rest are kept as
    # set members for other dialog kinds / older builds — this is exactly the
    # C4 failure class (unversioned vendor copy) the set design exists for.
    re.compile(r"Do you want to (?:make this edit|proceed)"),
    re.compile(r"Yes, and always allow access to .* from this project"),
    # other builds / dialog kinds (unverified on 2.1.222):
    re.compile(r"No, and tell Claude what to do differently"),
    re.compile(r"Yes, allow all .* this session"),
    re.compile(r"Yes, and (?:don't|do not) ask again"),
]
INPUT_DIALOG = [
    # AskUserQuestion renders numbered options with an "Other" affordance
    re.compile(r"❯\s*\d+\.\s"),          # highlighted numbered option row
    re.compile(r"Type something\.?|Other \(type"),
]
TRUST_DIALOG = [
    # 2.1.222 copy (verified live 2026-08-05):
    re.compile(r"Quick safety check: Is this a project you created"),
    re.compile(r"Yes, I trust this folder"),
    # older copy kept as set members (C4: sets, not single strings):
    re.compile(r"Do you trust the files in this folder"),
    re.compile(r"Yes, proceed"),
]
STARTING_SCREENS = [
    re.compile(r"Choose the text style"),          # theme picker header…
    # …but the header scrolls out of the anchored tail, leaving only option rows that
    # look like any numbered dialog — which made the theme picker read as
    # `waiting:input` and blocked every send. Found on a fresh WSL2 Linux config,
    # 2026-08-06: match the option literals, which are always in the tail.
    re.compile(r"Dark mode \(colorblind-friendly\)"),
    re.compile(r"Auto \(match terminal\)"),
    re.compile(r"Select login method"),            # login picker
    re.compile(r"Claude account with subscription"),
    re.compile(r"Anthropic Console account"),
]

# --- prompt marker (necessary-not-sufficient; PITFALLS: never an idle gate) ----
PROMPT_MARK = re.compile(r"^\s*❯", re.M)


# How many trailing non-blank lines constitute "now" on screen.
# Anchoring is not a tuning knob, it is a correctness requirement (design C3):
# a capture that includes scrollback contains spinner lines from EARLIER frames,
# so a whole-buffer match reports `busy` on a session that has been idle for
# minutes. Caught by the mock-agent portability check on 2026-08-05
# ("completion is NOT busy-shaped" failed against a 60-line capture) — the same
# stale-buffer class as awslabs/cli-agent-orchestrator#182.
TAIL_LINES = 15


def tail_region(text: str, lines: int = TAIL_LINES) -> str:
    """The bottom of the screen — the only region that describes the present."""
    keep = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(keep[-lines:])


def classify_screen(text: str) -> dict:
    """Pure classification of one capture. No state decisions here — the engine
    composes captures over time (SPEC rule 1). Returns raw signal booleans.

    Liveness/dialog signals are read from the TAIL only (see TAIL_REGION);
    passing a full-scrollback capture here is safe because we anchor internally.
    """
    text = tail_region(text)
    return {
        "spinner_busy": bool(SPINNER_BUSY.search(text)),
        "tool_running": bool(TOOL_RUNNING.search(text)),
        "completion_line": bool(COMPLETION_LINE.search(text)),
        "background_work": bool(BACKGROUND_WORK.search(text)),
        "permission_dialog": any(p.search(text) for p in PERMISSION_DIALOG),
        "input_dialog_rows": bool(INPUT_DIALOG[0].search(text)),
        "trust_dialog": any(p.search(text) for p in TRUST_DIALOG),
        "starting_screen": any(p.search(text) for p in STARTING_SCREENS),
        "prompt_mark": bool(PROMPT_MARK.search(text)),
    }
