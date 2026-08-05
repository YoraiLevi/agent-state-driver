# Functional design: agent state detection & driving

Status: settled draft v1 (2026-08-05). Grounded in `docs/.research/prior-art/SYNTHESIS.md`
(conclusions cited as C1-C11) and the empirical probes in `docs/.research/empirical/`
(cited as Q1-Q8). Every load-bearing claim carries its source; unverified claims are
marked (INFERRED) or (UNVERIFIED).

## 1. Problem and scope

An interactive CLI AI agent is, to its supervisor, a byte stream with no machine-readable
state. This design specifies a system that (a) detects which of a defined set of states such
an agent is in, (b) drives it (input, dialog answers, lifecycle), (c) works on macOS, Linux,
and Windows, and (d) fails loudly instead of misdetecting silently.

**Two attachment postures**, per C1 — but C1 is *revised* by our Q1 result:

- **Spawned** (we launch the agent): every channel is available — hooks, stream-json,
  transcript, PTY, screen.
- **Attached** (a human launched it): the prior-art survey concluded this posture was
  screen-scrape-only. Q1 proved otherwise for Claude Code: **hooks can be retrofitted onto a
  running session** by writing the project `.claude/settings.json` mid-session — the file is
  re-read per hook dispatch, causally proven in both directions (install → fires; remove →
  stops) [Q1]. Attached sessions therefore get hooks + transcript + screen; only
  stream-json remains spawn-only [SYNTHESIS 1.5].

Out of scope for v1: driving agents other than Claude Code (the adapter interface is designed
for N backends per C11, but only the Claude Code adapter is specified); Windows late-attach
into a foreign console (documented non-mechanism, pywinauto#492 [SYNTHESIS C1]).

## 2. State model

Seven states. Five are the mission's target set; two were forced by evidence.

```
                    ┌──────────┐
        launch ────▶│ starting │  trust dialog / theme picker / login live here
                    └────┬─────┘
                         ▼
      ┌───────────────▶ idle ◀───────────────────┐
      │                  │ prompt submitted       │ turn end [Stop hook / spinner
      │                  ▼                        │  gone + hash-stable, Q7]
      │                busy ─────────────────────┤
      │                  │                        │
      │                  ├─▶ waiting:permission ──┘  (dialog answered → busy)
      │                  ├─▶ waiting:input ──────┘  (question answered → busy)
      │                  │
      │   staleness      ▼
      └── recovery   presumed_hung ── kill/timeout ─▶ dead
                         ▲                            ▲
                         │ (observer-computed)        │ EOF / exit code
                        busy                       any state
```

| State | Definition (provable, per C6) | Primary evidence channel |
|---|---|---|
| `starting` | process alive, first idle not yet reached | screen (dialog literals) + process |
| `busy` | a turn is executing: spinner-verb/tool-run line present OR screen hash changing ≤1 s [Q7] | screen; hooks (`PreToolUse`..) when installed |
| `idle` | busy-regex absent AND ≥3 consecutive identical captures [Q7]; `Stop` fired with no pending dialog | screen + hooks |
| `waiting:permission` | permission dialog rendered / `PermissionRequest` hook fired [SYNTHESIS 1.3] | hooks (proof) or screen (dialog literal set) |
| `waiting:input` | `AskUserQuestion`-style dialog or MCP `Elicitation` [C8 — merged deliberately in v1; split when a consumer needs it, coverage declared] | hooks or screen |
| `presumed_hung` | busy asserted AND no state-refresh for > staleness threshold; observer-computed at read time [C5, cultureagent] | composite watchdog |
| `dead` | process exited: EOF/exit code | process (only channel that survives death, C5) |

Model notes forced by evidence:

- **Turn-end ≠ idle** [C7]: `Stop` carries `background_tasks`; a finished turn can leave
  `✻ Crunched for 9s · 1 shell still running`, and a background completion **redraws the pane
  ~39 s after idle** [Q7]. The state machine treats post-idle redraws as legitimate events,
  and exposes `idle.background_work: bool` as an attribute rather than a state.
- **Compaction looks like a hang** [C7]: `PreCompact`/`PostCompact` hooks (when installed) or
  the transcript's `compact_boundary` record [SYNTHESIS 1.4] must suppress the staleness
  watchdog during compaction. Coverage declared: without hooks or transcript, screen-only
  posture cannot distinguish compaction from a wedge — the watchdog will false-alarm
  `presumed_hung`; threshold must exceed observed compaction times (to be measured, Phase 3).
- `starting` exists because the trust dialog appears **unconditionally** — the
  `hasTrustDialogAccepted` project setting does not suppress it [Q7] — and a virgin config
  additionally shows theme/login pickers (verified live earlier this session; PITFALLS).

## 3. Detection channels — what each proves, and how each lies

Reliability table, empirically grounded. "Proof" = state is certain when signal fires;
"heuristic" = inference with named failure modes.

| Channel | Proves | Latency | Lies / limits | Posture |
|---|---|---|---|---|
| **Screen composite** (busy-regex + hash-stability) [Q7] | busy/idle (heuristic, strong) | poll-bound, 1 s | version-volatile strings (rotating verb sets, C4); `esc to interrupt` is **intermittent** — phase- and config-dependent (q7-q8-reconciliation) — never gate on it; stale-redraw class requires bottom-anchor + NOT-gates [C3, Q6: independently re-patched 3× in kiro_cli] | both |
| **Screen dialog literals** | waiting:permission / waiting:input (heuristic) | poll-bound | unversioned UI copy, breaks silently [C4]; mitigations: literal *sets*, self-test that fails loudly, version pin | both |
| **Hooks** (command type) | waiting:permission (`PermissionRequest`, proof), turn-end (`Stop`), tool activity (`PreToolUse`/`Post…`), compaction | ~5-20 ms | not on crash/SIGKILL [C5]; silent non-install (verify via `stop_hook_summary`, Q1); retrofit is silent + costs one turn to confirm [Q1]; read-modify-write settings (other-scope hooks exist, Q1) | both (Q1) |
| **HTTP hooks** | same events as command hooks, pushed as per-event stateless POST | ms + RTT | fail-open (non-2xx/timeout ignored); not on `SessionStart`/`Setup`; gated by `allowedHttpHookUrls` [Q5] | both |
| **Transcript JSONL** | turn boundaries + wall-clock (`turn_duration`), hook-ran proof (`stop_hook_summary`), compaction, permission-mode; subagent fan-out via `subagents/` sidecar tree (both OSes, Q11-settled) | FS-watch-bound | undocumented schema, version-fragile [SYNTHESIS 1.4]; forks need `sessionId`/`forkedFrom` tracking | both |
| **stream-json** (`-p --include-hook-events --include-partial-messages`) | richest: token-level busy, api_retry, hook lifecycle inline | stream | **spawn-only**; headless (dialog tools block; `defer`+`--resume` documented not exercised — Q10, Phase 3) | spawned |
| **OTel telemetry** | post-hoc audit only. `tool.blocked_on_user` is real but structurally useless live: span ends only at decision; measured 37.9 s emit lag. `tool_decision` log lands ~2.5 s post-answer [Q4] | 5 s+ batch | console exporters emit **nothing** — OTLP sink required [Q4]; PII in dumps (email, org id) — never commit raw exports [Q4] | spawned (env at launch) |
| **Session sidecar** `~/.claude/sessions/<pid>.json` — **discovered 2026-08-05, in no surveyed prior art** [docs/discovery-session-sidecar.md] | vendor-emitted `status` (`idle`/`busy`/`waiting`) + `waitingFor` (`"permission prompt"`) — answers the hardest state directly | 9-18 ms after the corresponding transcript record | edge-triggered, NOT a heartbeat (timestamp stale while state persists — never watchdog on it); clean exit deletes the file, SIGKILL leaves it stale ⇒ `kill -0` liveness gate mandatory; look up by `sessionId` not PID; undocumented/unversioned; `waitingFor` vocabulary of unknown size ⇒ unknown literal must yield `conflict` | **both** — no settings write, no spawn requirement |
| **Process/OS** | dead (proof; the only channel surviving death) | immediate on wait/EOF | existence ≠ liveness (claude-flow anti-pattern) [SYNTHESIS 1.8] | both |
| **PTY/emulator signals** | nothing usable from Claude Code today: **no alt-screen, no BEL, no OSC 9/777** [Q8]; OSC 0 title exists but laggy + non-monotonic [Q8]; OSC 133 unavailable (excluded from terminalSequence allowlist [Q5]; silent inside TUIs anyway) | — | ruled out for v1 as state signals; title usable as display metadata only | — |

**Fusion rule** (C2: never gate on a single capture; Q9 pending for measured hierarchy):

0. The **session sidecar** is the preferred reading for `busy`/`idle`/`waiting:permission`
   when present AND its PID is live — it is vendor-emitted and millisecond-fresh. It is
   never sufficient alone: it cannot see pre-session dialogs, carries no option text, and
   its staleness means nothing.
1. If hooks are confirmed installed (sentinel verified per Q1), hook events are authoritative
   for their states; screen composite corroborates. **Hooks alone cannot clear a permission
   latch** — denial emits no hook event at all (verified live, prototype B) — so a hook-only
   detector must fuse sidecar or screen or report `conflict`.
2. Screen composite is the always-available floor: `busy` = regex OR hash-motion; `idle`
   requires BOTH regex-absent AND ≥3 stable captures.
3. Process channel overrides everything for `dead`.
4. The staleness watchdog runs observer-side [C5]: threshold > heartbeat interval, asserts
   fail-fast at config time (cultureagent's shape), suppressed during known-long quiet ops
   (compaction) when that knowledge is available.
5. Disagreement between channels is surfaced as a first-class `conflict` event, never
   silently resolved (quality bar: fail loudly).

## 4. Driving

- **Input**: `send-keys -l` text + separate `Enter` (PITFALLS); dialogs answered by
  arrow/Enter with the dialog literal verified on screen first.
- **Launch sequence** handles `starting` unconditionally: wait for trust dialog OR idle
  marker, answer trust if present [Q7].
- **Permission flow**: v1 default is *detect and surface* `waiting:permission` (not bypass) —
  the C9 tension resolved on the side of safety: bypass flags on driven sessions are the
  documented footgun class (PITFALLS; classifier-blocked in this very session). An operator
  can opt in to auto-approval policies per tool pattern via the settings allowlist instead
  (pre-allow, Q7 method), which is scoped and auditable, unlike global bypass.
- **Never patch the target binary** [C10]. Never write user-global config (`claude config
  set --global` is banned; `config get` needs a timeout wrapper [Q8]).

## 5. Cross-platform architecture

One driver interface, three capture backends. Interface verbs (convergent with the PTY-daemon
ecosystem's shape [SYNTHESIS 2]): `launch, attach, send, keys, screen, state, wait_state,
answer_dialog, kill` — each returning typed results; `state` returns
`{state, attrs, evidence: [{channel, signal, at}]}` so consumers can audit *why*.

```
            driver core (state fusion, watchdog, dialog literals, version pins)
                 │
     ┌───────────┼──────────────────┐
     ▼           ▼                  ▼
 tmux backend   wezterm/kitty     ConPTY backend (Windows)
 (macOS/Linux)  backend           options, decision Phase 4:
 capture-pane   (all 3 OSes;      – wezterm native (also col. 2)
 + send-keys    native Windows;   – PTY session daemon (gist map)
                get-text/send)    – headless stream-json only (no TUI)
```

- tmux is the mature Unix surface; **wezterm/kitty are the only credible cross-platform
  native capture surfaces found** [SYNTHESIS 1.1] — the Windows decision is explicitly
  deferred to Phase 4 evidence (Q2: daemon verbs with no console attached, untested; gist
  rates it "can kill the entire PTY branch").
- windesk reality check: no tmux; pwsh 7.6.3; claude.exe 2.1.222 present (STATE.md).

## 6. Failure-mode analysis — by mechanism

Coverage: enumerated below = analyzed; anything not listed = not yet analyzed (not cleared).

**6.1 Silent misdetection (worst class — reports a state that is wrong)**
- Stale-redraw: old status text survives partial TUI redraw → whole-buffer match reports
  stale state. Mitigation: bottom-N anchor + NOT-gates [C3]; observed re-patched 3× in one
  production file [Q6]. Residual: a stale *bottom* line (not observed; (INFERRED) possible).
- Intermittent footer hints (`esc to interrupt`): gate reads idle during busy. Mitigation:
  composite gate; hint strings demoted to corroboration [q7-q8-reconciliation].
- Glyph trap: spinner glyph + `(Ns` matches the past-tense completion line → busy latch.
  Mitigation: exclude `\w+ed for \d+s` forms [Q7].
- Dialog copy drift: vendor changes dialog string → waiting states vanish silently.
  Mitigation: literal sets + version pin + **self-test that fails loudly when a session
  provably ran without any literal ever matching** [C4].
- Locale/encoding: `LC_ALL=C` byte-wise matching pitfall [Q6, operonlab]. Mitigation: force
  UTF-8 in the capture path; test non-ASCII spinner glyphs explicitly.

**6.2 False-busy / false-idle (timing class)**
- Silent foreground tool call: **empirically NOT a false-idle hole on 2.1.222** — two
  independent 1 s tickers guarantee screen motion; longest identical run while busy = 1
  sample [Q7]. Residual risk: ticker removal in a future build → the regex leg still holds;
  both legs failing simultaneously is the declared detection boundary.
- Idle screen redraw by background-shell completion ~39 s post-idle [Q7]: must not re-latch
  busy without the busy-regex confirming; classified as `idle` attribute change.
- Compaction: silent multi-second gap [C7]. Screen-only posture: watchdog false-alarm risk,
  declared. Hook/transcript posture: suppressed via `PreCompact`/`compact_boundary`.

**6.3 Reports-success-falsely (driving class)**
- Send-before-ready: input lands mid-busy, queued or dropped. Mitigation: `wait_state(idle)`
  precondition on `send` (C2 composite), plus post-send verification that the prompt line
  appeared.
- Hook "installed" but never ran: `disableAllHooks`, trust gates [SYNTHESIS 1.3]. Mitigation:
  Q1 protocol — sentinel + `stop_hook_summary` hookCount delta before trusting the channel.
- Model narrates un-run constructs (prose ≠ proof). Mitigation: every driver assertion is a
  machine signal; nothing accepted from agent text (PITFALLS).

**6.4 Death and wedges**
- SIGKILL: no hook fires [C5] → process channel mandatory; `SessionEnd` fires on `/clear`
  too — never map it to death alone [SYNTHESIS 1.3].
- Hang: `presumed_hung` observer-computed with threshold > heartbeat, fail-fast config
  assertion [C5]; timeouts convert stalls to deaths deliberately so one recovery path
  handles both (cultureagent's `.terminate()` pattern) [SYNTHESIS 1.8].
- Driver's own capture hanging (claude-squad #216) [SYNTHESIS 1.1]: every backend call
  wrapped in its own timeout; a capture timeout is a `conflict` event, not a crash.

**6.5 Environment class**
- Config isolation severs auth (`--bare`, virgin `CLAUDE_CONFIG_DIR`) — PITFALLS, verified.
- Wrapper shims inject flags (windesk `Invoke-Claude` adds skip-permissions) — always invoke
  the real binary (STATE.md).
- MSYS path mangling on Windows bare slashes — `MSYS_NO_PATHCONV=1` (PITFALLS).
- Multi-byte chars split across stream reads → permanent U+FFFD under `from_utf8_lossy`
  [C10]; byte-typed wires required if we ever proxy streams.

## 7. Prototype plan (Phase 3) and what each must answer

| Prototype | Channels | Answers | Success oracle |
|---|---|---|---|
| A `scrape-driver` | screen composite + process | does the composite gate hold across scenario matrix; Q9 latency baseline | scenario suite: detect each of 7 states within declared latency; zero silent misdetections |
| B `hook-sentinel` | retrofit hooks (Q1 protocol) + HTTP hooks [Q5] + process | push-based detection viability; retrofit confirm-latency; Q10 defer/resume | same suite; hook events match screen ground truth |
| C `transcript-watch` | JSONL tail + process | turn boundaries/compaction from disk alone; schema-drift resilience | same suite; agreement matrix vs A/B |
| Harness | drives all three against identical scripted scenarios (idle waits, silent tool, permission dialog, question dialog, kill -9, compaction) | Q9 comparative latency table; disagreement matrix | reproducible on a stranger's machine |

## 8. Locked decisions and open questions

Locked (relitigable only with new evidence): composite busy gate [Q7+reconciliation];
detect-don't-bypass permissions default [C9 resolved]; observer-side staleness [C5]; two-tier
death [C5]; no binary patching [C10]; evidence-carrying `state` API; Windows backend decision
deferred to Phase 4 empirical results [Q2].

Open (Phase 3/4 will answer): Q2 (headless ConPTY daemon verbs), Q3 (stream-json cross-OS
parity), Q9 (per-channel latency race), Q10 (defer + `--resume` permission flow), compaction
duration distribution (watchdog threshold), which config factor suppresses the footer hint
(reconciliation residual), Linux/Windows rendering of spinner/dialog literals.
