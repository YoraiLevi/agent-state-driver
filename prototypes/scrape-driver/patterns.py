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
    re.compile(r"No, and tell Claude what to do differently"),
    re.compile(r"Do you want to (?:make this edit|proceed)"),
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
    re.compile(r"Choose the text style"),          # theme picker (virgin config)
    re.compile(r"Select login method"),            # login picker
]

# --- prompt marker (necessary-not-sufficient; PITFALLS: never an idle gate) ----
PROMPT_MARK = re.compile(r"^\s*❯", re.M)


def classify_screen(text: str) -> dict:
    """Pure classification of one capture. No state decisions here — the engine
    composes captures over time (SPEC rule 1). Returns raw signal booleans."""
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
