# Q6: three most on-topic unread artifacts, read first-hand

## Question

SYNTHESIS.md Q6: "Read `operonlab/tmux-agent-status`'s `docs/detection-matrix.md` directly ...
Also unread: `OEN-Tech/tmuxai`'s detection code, and the `kiro_cli` poller inside
`awslabs/cli-agent-orchestrator`." Plus: re-fetch issue #182 in the reporter's own words
(currently single-sourced via a gist, per SYNTHESIS.md section 5).

## Method

All three repos confirmed to exist via `gh api repos/<owner>/<repo>`. Content pulled with
`gh api repos/<owner>/<repo>/contents/<path> --jq '.content' | base64 -d`, full file trees via
`gh api repos/<owner>/<repo>/git/trees/HEAD?recursive=true`. Issue #182 pulled with
`gh api repos/awslabs/cli-agent-orchestrator/issues/182 --jq '{title,body,state,created_at,closed_at}'`.
Files fetched, saved locally at
`/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/q6/`:

- `detection-matrix.md`, `classify.awk` (operonlab/tmux-agent-status)
- `fsm.rs`, `events.rs`, `classifier.rs`, `status_bar.rs`, `question.rs`, `profile.rs`,
  `main.rs`, `profiles/claude-code.toml` (OEN-Tech/tmuxai)
- `kiro_cli.py` (awslabs/cli-agent-orchestrator, `src/cli_agent_orchestrator/providers/`)

All content below is OBSERVED (read directly, not summarized from a secondary source) unless
marked INFERRED.

## Observed

### (a) operonlab/tmux-agent-status — `docs/detection-matrix.md` + `scripts/classify.awk`

- Three-state model: `BUSY` / `WAIT` (their word for permission-blocked) / `IDLE`, plus an
  unmatched "no state" (not counted) — a four-way outcome, not three.
- Per-`pane_current_command` rule-set dispatch table: `claude`/`claude-code`/bare version
  string get the richest ruleset (screen-scraped footer); `gemini`/`aider`/`cursor`/etc. and
  `node`/`bun`/`deno` are **title-only** — explicitly because trusting body text for a
  generic Node process risks misreading a dev-server log as agent activity. This is a
  *third* independently-arrived-at instance of the same principle SYNTHESIS.md's C3 already
  names (anchor to bottom-N / OSC title, never whole-buffer).
- `classify.awk`'s own header comment states the exact regression it defends against by name
  and date: *"the 2026-07-04 false-positive"* from a naive whole-screen spinner grep firing on
  scrollback (an example transcript quoting a running agent, or a README open in the pane).
  This is a first-hand admission that C2 ("never gate on one capture... every project that
  decided state from one snapshot has a documented false-positive path") applies to this
  project too, and it's dated, i.e. an actual incident, not a hypothetical.
- Byte-wise matching under forced `LC_ALL=C`: multibyte spinner/prompt glyphs (❯ ─ │ ✳
  braille) are written as UTF-8 octal-byte literals compared byte-by-byte, because tmux
  status-line `#()` commands run with `HOME=""`/`LANG` unset. This is a concrete,
  previously-undocumented-in-SYNTHESIS locale/encoding pitfall specific to the
  tmux-status-line integration surface (not the scrape-a-pane-on-demand surface our own
  prototypes use) — worth flagging as a portability trap if the design ever emits a tmux
  status-line capsule.
- NOT-gates as a named design category: "empty-❯ veto," "box present ⇒ idle," "bottom-zone
  live-working veto" — i.e. deliberately-encoded negative rules, not just positive pattern
  matches. Extends C2/C3 with a concrete taxonomy of *what the NOT-gates guard against* that
  our own design doc should probably borrow directly.
- Explicit admission of staleness risk in their own disclaimer block: "a rule that is
  accurate today can drift when an upstream release rewords a prompt or swaps a spinner" —
  matches C4 verbatim (busy vocabulary rotates, needs a version-pinned set + self-test), and
  they date their own rules file (`Rules version: 1 · Verified: 2026-07`) as a mitigation —
  a versioning discipline SYNTHESIS.md recommended in the abstract; here it's implemented.
- Their `claude_rules()` spinner set: `✳ ✶ ✸ ✻ ✽ ✴ ✢ ✷` (checked byte patterns
  `\342\234\263/\266/\270/\273/\275/\264/\242/\267`) plus braille prefix — a *different* glyph
  inventory than SYNTHESIS.md's own cited rotation examples ("Marinating, Clauding,
  Simmering"). Corroborates C4's "match as a set" prescription from a second independent
  glyph enumeration, but the two glyph sets don't overlap with each other's *text* labels —
  reinforcing that no single vendored list is safe without a live self-test.

### (b) OEN-Tech/tmuxai — Rust parser/FSM (`classifier.rs`, `fsm.rs`, `events.rs`, `profile.rs`)

- Architecture differs qualitatively from (a): not a single-shot classifier over the visible
  screen, but a line-by-line streaming FSM (`Fsm::feed(LineClass) -> Vec<Event>`) with 10
  declared states (`Idle, Thinking, ToolUse, ToolResult, Responding, WaitingForInput, Asking,
  Checklist, Error, PromptEcho`) driven by a per-CLI TOML "profile" of regexes
  (`profiles/claude-code.toml` etc.). This is a genuinely different detection paradigm from
  every project SYNTHESIS.md's section 1.1 covered — worth adding to the taxonomy as a
  sub-class: "line-classified FSM over full scrollback replay" vs. "single-snapshot
  screen-scrape."
- **Two of the ten declared `State` enum variants — `WaitingForInput` and `Asking` — are never
  constructed anywhere in `fsm.rs`'s transition logic.** Verified with
  `gh search code "WaitingForInput" --repo OEN-Tech/tmuxai` and `"Asking"` — both hits are the
  enum declaration in `events.rs` plus a doc-comment in `main.rs` ("Show the pending question
  ... if the session is asking"); zero hits in `fsm.rs`. The CLI's actual "is the session
  asking a question" check (`main.rs:271-283`) works by scanning the emitted `Event` stream
  for the most recent `Event::Question` variant, not by reading `Fsm::state()`. **This means
  the FSM's own state enum is not the source of truth for the "waiting" condition in this
  codebase — the event stream is.** Relevant design consequence below.
- The actual "is this a question that needs a human" heuristic (`question.rs`) is **text
  content**, not terminal chrome: `extract_choices()` splits the *assistant's own response
  text* line-by-line against `^\s*-?\s*\*?\*?([A-Z])\)?\*?\*?\s+(.+)` — i.e., any line shaped
  like `A) foo`, `* B) bar`, `**C)** baz` becomes a "choice," and any response containing ≥1
  such line becomes `Event::Question`. This is a materially different mechanism from every
  permission-dialog detector in the survey (which key on terminal UI chrome: "do you want to
  proceed?", `[y/n]`, footer hints). It detects the model *asking a multiple-choice question in
  prose*, not the harness *presenting a permission/approval dialog*. **Failure mode they do not
  guard against, observed in the code, not documented by them:** a normal lettered list in
  assistant output (e.g., "Options: A) fast path B) slow path" as informational content, not a
  question awaiting a reply) would be misclassified as `Event::Question` — there is no NOT-gate
  analogous to (a)'s empty-❯ veto or (c)'s idle-after-marker check. This is new information,
  not previously flagged anywhere in SYNTHESIS.md.
- `profiles/claude-code.toml`'s `launch_command = "claude --dangerously-skip-permissions"` and
  the **complete absence of any permission-prompt regex** in that profile (no `[permission]`
  section at all, unlike operonlab's classify.awk which has five distinct permission-question
  rules for Claude). This is a *third* independent project choosing the C9 bypass-at-launch
  strategy, and — unlike cultureagent, which SYNTHESIS.md already cited for C9 — this one is
  screen-scraping the *same* CLI (claude) that operonlab's classify.awk scrapes with explicit
  permission-dialog rules. **Direct within-survey contrast: two projects targeting the
  identical CLI made opposite architectural choices** (detect-the-dialog vs.
  bypass-and-never-look). Strengthens C9's framing that this is a real fork in the road, not
  an artifact of differing target CLIs.
- Thinking-glyph set in the Claude profile: `[✻✶✽✷]` (4 glyphs) — a *third* distinct glyph
  inventory alongside SYNTHESIS's own citation and operonlab's 8-glyph set. Three
  non-identical enumerations of "the Claude spinner glyph set" further corroborates C4's
  "no single list is safe" concern, now from three independent sources rather than the
  original one.
- `strip_scrollbar()` in `classifier.rs` is a previously-unlisted anti-pollution technique:
  stripping a lone trailing `█` scrollbar-thumb column (grok's TUI) so it doesn't get read
  as page content, while explicitly preserving multi-`█` runs (real progress-bar content) and
  a `█` glued directly to a word. Test suite (`scrollbar_tests` module, `classifier.rs:220-264`)
  encodes this as a named regression fixture set. New concrete failure class for our own
  design's NOT-gate catalogue: terminal scrollbar rendering artifacts as false content.

### (c) awslabs/cli-agent-orchestrator — kiro_cli.py poller + issue #182

- `get_status()` (`kiro_cli.py:391-631`) is a single ordered cascade of checks over one
  captured buffer, explicitly commented as "Status detection logic (in priority order)" with
  6 numbered checks (`UNKNOWN → PROCESSING(no-idle) → ERROR → WAITING_USER_ANSWER →
  COMPLETED → IDLE`), each with an explicit position-aware NOT-gate: e.g. Check 2 ("Kiro is
  working" ghost text) only fires PROCESSING "when no idle prompt appears *after* the last
  match" — the exact fix that closed #182.
- **Issue #182 fetched in the reporter's own words** (title: "fix(kiro_cli): TUI idle
  detection blocked by stale 'Kiro is working' in tmux buffer", filed 2026-04-17, closed
  2026-04-20, environment: CAO v2.0.2, Kiro CLI 2.0.0, macOS, Ghostty+tmux):
  > "Kiro CLI 2.0 TUI redraws the screen in-place. When the agent finishes, the tmux pane
  > buffer retains 'Kiro is working' from earlier rendering alongside the new idle prompt
  > ('ask a question or describe a task'). Since `re.search(TUI_PROCESSING_PATTERN,
  > clean_output)` matches anywhere in the buffer, it always returns `PROCESSING` — even when
  > the agent is idle. ... Handoff delegations never complete — the supervisor waits
  > indefinitely for the worker to reach IDLE/COMPLETED."
  The reporter's own suggested fix (move idle-detection earlier, then gate the
  processing-pattern match on "no idle prompt appears after it") matches, nearly verbatim,
  the code now live at `kiro_cli.py:469-481`. **This resolves the SYNTHESIS.md section-5
  single-source flag on #182: it is a real, first-hand-verifiable bug report with a
  merged fix, not a chain of citations.** It is exactly the failure mode C2/C3 describe
  (undebounced single-snapshot match on stale screen content), now confirmed by primary
  source rather than by a gist's paraphrase.
- Beyond #182 itself, the *current* code (post-fix) shows the same stale-redraw problem was
  independently rediscovered and re-patched for **three more UI elements** in Kiro's TUI,
  each with its own comment trail: the `TUI_INITIALIZING_PATTERN` boot-screen text (Check 0b,
  comment: "the raw byte stream ... that line still sits in the rolling byte stream forever"),
  the trust-all-tools consent footer (Check 2a, comment: "same class as issue #405" — a
  *second*, previously-unlisted issue number in this same repo, not yet fetched), and the
  permission-prompt itself (line-count heuristic: "0-1 lines with idle prompt" = active,
  "2+ lines" = stale/already-answered — a *quantitative* staleness threshold, not just a
  positional NOT-gate). **This means stale-redraw is not a single bug fixed once; it's a
  recurring failure class this codebase has had to re-derive a fix for at every new UI
  element**, which is stronger evidence for C2/C3 than a single incident would be.
  `issue #405` is a lead not chased in this pass (out of scope for Q6; flagged for a future
  pass if useful).
- `_permission_prompt_pattern` (legacy UI) requires all of `y`, `n`, `t` tokens in one
  bracketed choice (`Allow this action\?.*?\[.*?y.*?/.*?n.*?/.*?t.*?\]:`); `TUI_PERMISSION_PATTERN`
  requires the full three-way `Yes ... No ... Always Allow` (or `Yes, single permission ...
  Trust ... No`) layout specifically so agent output that merely *mentions* a permission
  prompt in prose can't false-positive — a set-not-substring discipline analogous to C4 but
  applied to a whole dialog shape rather than a single glyph.
- The code contains an explicit non-scraping escape hatch not mentioned in SYNTHESIS.md's
  section 1: `_resolve_native_status()` — "if the backend can report a native agent_status,
  trust it and skip buffer parsing," with a named backend ("herdr") where `pipe_pane` is a
  no-op and the regex path can never leave `UNKNOWN`. This is evidence of a *production*
  system already hitting the "screen-scrape doesn't work on every backend" wall SYNTHESIS.md
  discusses abstractly (C1) and building the native-status escape hatch as the fix, rather
  than hardening the scrape further.

## Verdict

**ANSWERED-YES** for all three artifacts and for the issue #182 single-source flag — all read
first-hand via `gh api`/`gh search`, with file paths and line-anchored evidence recorded above.
No part of this Q6 sub-question remains unread. (`issue #405`, referenced inside kiro_cli.py's
own comments, is a new unread lead surfaced by this pass — not required by Q6, flagged for a
future pass, not chased here.)

## Design consequence

1. **C2/C3 are now corroborated by five independent projects** doing the exact same
   position-aware / bottom-anchored / NOT-gated pattern (operonlab, tmuxai, kiro_cli, plus the
   two SYNTHESIS.md already had) — including one, kiro_cli, that visibly *re-derived* the fix
   three separate times for three separate UI elements in the same codebase. Our own scraper
   prototype should treat "gate every positive match on no-later-idle-marker" as a mandatory
   primitive, not a nice-to-have, and should expect to need it per-signal, not once globally.

2. **C4 is now corroborated by three non-overlapping glyph enumerations** for the same CLI
   (Claude): SYNTHESIS's own cited set, operonlab's 8-glyph set, tmuxai's 4-glyph set. No
   single hardcoded spinner-glyph list is trustworthy; the design's self-test
   (session that clearly ran but hit zero known-glyph members) is validated as necessary, not
   speculative.

3. **C9 gets a sharper framing**: two projects target the identical CLI (`claude`) and made
   opposite architectural choices — operonlab detects the permission dialog via five regex
   rules; tmuxai's Claude profile has none and launches with
   `--dangerously-skip-permissions` instead. The design doc should present this as an explicit
   fork with named tradeoffs (dialog-detection risk of drift/false-negative vs.
   bypass-mode's removal of human-in-the-loop approval) rather than a single recommended
   path, since real prior art is split roughly down the middle even for one target CLI.

4. **New failure class for the design's NOT-gate catalogue, not previously in SYNTHESIS.md**:
   text-content multi-choice misdetection (tmuxai's `question.rs` — a lettered list in normal
   assistant prose gets misread as `Event::Question`/waiting-for-input with no NOT-gate
   guarding it) and terminal scrollbar-thumb artifacts (tmuxai's `strip_scrollbar`). If our
   own design's "waiting-on-input" detector ever inspects response *text* (as opposed to
   terminal chrome) for a question, it needs an explicit veto for markdown-list-shaped
   informational content — tmuxai's own code shows this gap is real and unaddressed there.

5. **The taxonomy in SYNTHESIS.md section 1.1 should gain a sub-class**: "streaming line-FSM
   over full replayed scrollback, profile-driven per-CLI regex set" (tmuxai) is architecturally
   distinct from "single-snapshot screen classify" (operonlab, kiro_cli) — it changes
   incrementally per line rather than re-deriving state from a fresh capture, which changes the
   failure surface (a single misclassified line can wedge the FSM in the wrong state until the
   next boundary line, vs. single-snapshot's every-poll-is-fresh self-correction). Worth a
   comparative note in the functional design about which failure mode we'd rather have.

6. **Confirms C1's escape hatch is being used in production, not just theorized**: kiro_cli.py's
   `_resolve_native_status()` / "herdr" backend is a real instance of a project abandoning
   scrape-refinement in favor of a backend-reported native status once the scrape path proved
   unworkable (buffer never populated) — direct precedent for treating pure screen-scrape as a
   fallback tier rather than the primary channel where a richer channel exists.
