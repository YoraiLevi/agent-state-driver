"""Detector unit tests — the screen predicates, against captured real frames.

These are fast (no tmux, no processes) and they encode the traps that actually bit,
so a regression fails here in milliseconds rather than in a live session.

Every fixture string below is copied from a REAL capture recorded in
docs/.research/empirical/ — not invented. Where a frame caused a specific bug, the
test names the bug.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes" / "scrape-driver"))
from patterns import classify_screen, tail_region  # noqa: E402


# --- real captures (docs/.research/empirical/q7-false-idle.md) -----------------

BUSY_GENERATION = """
❯ Run exactly this one command: ping -c 40 -i 1 127.0.0.1 > /dev/null . Then reply pong.
∴ I should just execute what's being asked and respond with pong.
✽ Deciphering… (30s · ↓ 150 tokens)
"""

BUSY_TOOL_CALL = """
  Bash(ping -c 40 -i 1 127.0.0.1 > /dev/null)
  ⎿  Running… (26s · timeout 45s)
     (ctrl+b ctrl+b (twice) to run in background)
✽ Deciphering… (30s · ↓ 150 tokens)
"""

IDLE_AFTER_TURN = """
⏺ Bash(ping -c 40 -i 1 127.0.0.1 > /dev/null)
  ⎿  (No output)
⏺ pong
✻ Cogitated for 45s
❯
"""

IDLE_WITH_BACKGROUND = """
⏺ pong
✻ Crunched for 9s · 1 shell still running
❯
"""

# docs/.research/empirical/ + live capture 2026-08-05
PERMISSION_DIALOG = """
⏺ Bash(touch probe.txt)
  ⎿  Waiting…
 Bash command
   touch probe.txt
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and always allow access to protoA/ from this project
   3. No
 Esc to cancel · Tab to amend · ctrl+e to explain
"""

TRUST_DIALOG = """
 Quick safety check: Is this a project you created or one you trust?
 Claude Code'll be able to read, edit, and execute files here.
 ❯ 1. Yes, I trust this folder
   2. No, exit
 Enter to confirm · Esc to cancel
"""

# The Linux first-run screens (docs/results/linux/README.md) — these two caused a
# real failure: the header scrolls out of the tail, leaving only option rows.
THEME_PICKER_TAIL_ONLY = """
   1. Auto (match terminal)
 ❯ 2. Dark mode ✔
   3. Light mode
   4. Dark mode (colorblind-friendly)
   5. Light mode (colorblind-friendly)
   6. Dark mode (ANSI colors only)
   7. Light mode (ANSI colors only)
"""

LOGIN_PICKER = """
 Claude Code can be used with your Claude subscription or billed based on API usage.
 Select login method:
 ❯ 1. Claude account with subscription · Pro, Max, Team, or Enterprise
   2. Anthropic Console account · API usage billing
"""


class TestBusy:
    def test_generation_spinner_is_busy(self):
        assert classify_screen(BUSY_GENERATION)["spinner_busy"] is True

    def test_tool_run_line_is_busy(self):
        sig = classify_screen(BUSY_TOOL_CALL)
        assert sig["tool_running"] is True

    @pytest.mark.parametrize("verb", ["Clauding", "Marinating", "Simmering",
                                      "Hullaballooing", "Deciphering"])
    def test_busy_vocabulary_rotates(self, verb):
        """The vendor's busy verbs are a rotating SET, not a fixed string
        (SYNTHESIS C4). A detector matching one literal is already incomplete."""
        assert classify_screen("✽ %s… (3s · ↓ 12 tokens)" % verb)["spinner_busy"] is True


class TestIdle:
    def test_completed_turn_is_not_busy(self):
        """THE GLYPH TRAP: the completion line starts with the same glyph class as
        the spinner. A detector matching glyph + '(Ns' latches busy forever."""
        sig = classify_screen(IDLE_AFTER_TURN)
        assert sig["spinner_busy"] is False
        assert sig["tool_running"] is False
        assert sig["completion_line"] is True

    def test_background_work_is_an_attribute_not_a_state(self):
        """Turn-end is not 'nothing running' (SYNTHESIS C7)."""
        sig = classify_screen(IDLE_WITH_BACKGROUND)
        assert sig["background_work"] is True
        assert sig["spinner_busy"] is False


class TestDialogs:
    def test_permission_dialog_detected(self):
        assert classify_screen(PERMISSION_DIALOG)["permission_dialog"] is True

    def test_trust_dialog_detected(self):
        assert classify_screen(TRUST_DIALOG)["trust_dialog"] is True

    def test_theme_picker_is_a_startup_screen_not_user_input(self):
        """REGRESSION (docs/results/linux/): on a fresh Linux config the theme
        picker's header scrolls out of the anchored tail, leaving only numbered
        option rows. Classified as waiting:input, it blocked every send and the
        whole Linux run failed at the first check."""
        sig = classify_screen(THEME_PICKER_TAIL_ONLY)
        assert sig["starting_screen"] is True

    def test_login_picker_is_a_startup_screen(self):
        assert classify_screen(LOGIN_PICKER)["starting_screen"] is True


class TestAnchoring:
    def test_stale_scrollback_does_not_read_as_busy(self):
        """REGRESSION (docs/results/PORTABILITY.md): matching liveness over
        scrollback finds spinner lines from frames long past, so a session idle
        for minutes reads as busy. Anchor to the tail."""
        stale = "✽ Deciphering… (30s · ↓ 150 tokens)\n" + ("filler line\n" * 40) + IDLE_AFTER_TURN
        assert classify_screen(stale)["spinner_busy"] is False

    def test_tail_region_keeps_the_present(self):
        assert "Cogitated for 45s" in tail_region(("noise\n" * 50) + IDLE_AFTER_TURN)

    def test_prompt_mark_is_present_while_busy(self):
        """`❯` is NOT an idle signal — it is rendered during generation too.
        This test exists to stop anyone 'simplifying' idle detection to a prompt check."""
        assert classify_screen(BUSY_GENERATION)["prompt_mark"] is True
        assert classify_screen(BUSY_GENERATION)["spinner_busy"] is True
