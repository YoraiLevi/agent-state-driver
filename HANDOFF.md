# HANDOFF

For the next session/agent picking this up cold. Read STATE.md first, then this, then PITFALLS.md.

## Mission

Build and prove a reliable, cross-platform system for detecting the state of interactive
CLI AI agents (working / idle / waiting-on-permission / waiting-on-input / dead) and
driving them programmatically. **Phases 0-4 are complete and Phase 5 is nearly done** —
see STATE.md for the current line. The bar is unchanged: prove things by running them,
never claim a capability that was not exercised, and never endanger the owner's Claude
subscription (bounded loops, no unattended spend amplification, no `--dangerously-skip-permissions`).

## What exists now

- **Four prototypes**, each implementing `prototypes/common/SPEC.md`, each declaring its own
  coverage in its module docstring: `scrape-driver` (screen+process), `hook-sentinel`
  (hooks+process), `transcript-watch` (transcript+sidecar+process), `fused` (sidecar+screen+process).
- **An independent referee**, `prototypes/harness/run.py`. It derives ground truth from its
  own observations, never the driver's report, and its busy oracle is deliberately not
  imported from any driver. Scenarios S1/S2/S4/S6/S6b/S7; inconclusive runs score `ok: null`.
- **A credential-free fixture**, `prototypes/mockagent/`. Replays recorded 2.1.222 screen
  shapes plus the sidecar lifecycle and asserts the *shipped* `classify_screen` reads them.
  16/16 on macOS and Linux. Verified clean-clone-runnable with no setup.
- **Docs**: `docs/design/functional-design.md` (state model, channel table, fusion rules,
  FMA), `docs/discovery-session-sidecar.md`, `docs/results/` (race, portability, raw JSONL),
  `docs/.research/` (prior-art survey + synthesis, empirical probes, Windows leg).

## The three findings that matter most

1. **`~/.claude/sessions/<pid>.json`** — a vendor-written status file with `status` and
   `waitingFor`, in no surveyed project or vendor doc, working for sessions we did not
   spawn, schema-identical on macOS and Windows except `procStart`. Read the discovery doc
   before touching any detection code.
2. **Denying a permission dialog emits no hook event** (both OSes). Hooks alone can never
   clear that latch — this is why fusion exists, and why `conflict` is a reportable state.
3. **Terminal-gone is not agent-dead.** Liveness is the agent PID, cached at launch because
   the sidecar naming it is deleted on clean shutdown.

## Where to be careful

Everything in PITFALLS.md was paid for once; re-reading it is cheaper than rediscovering it.
The traps that bit hardest: `esc to interrupt` is intermittent (not a busy gate), motion is
necessary but not sufficient for busy, never match liveness over scrollback, and a liveness
test that cannot fail the defect it targets is not evidence (use SIGSTOP to make the window
deterministic).

## Open work

- **Blocked on the owner**: Tailscale SSH approval for `yorai@devbox`, the only thing
  keeping real-CLI-on-Linux unverified. Everything else on Linux is fixture-verified.
- **Unbuilt and declared as such**: an `attach` verb (attached posture — the mechanism is
  proven by Q1, no driver implements it), HTTP hooks, `-p --output-format stream-json` mode.
- **Unverified live**: `waiting:input` against a real question dialog, `presumed_hung`,
  compaction behavior and its duration distribution (needed to set the watchdog threshold),
  concurrent sessions, Windows persistence across logoff/Session 0.

## Operating agreements

- GitHub issues are the progress ledger; each phase closed with its evidence summarised.
- Engineering skills followed: quality-standards (evidence over claims, FMA, both paths),
  format-document-rules, explain-with-trees for architecture.
- Docs lifecycle: `docs/.research/` (active) → `docs/` (settled) → `.archive/` (retired).
- **Claims are audited adversarially before publication.** A reviewer was tasked with
  refuting this repo's claims and found the README dropping hedges its own sources carried;
  all findings were applied. Do that again before any further publication push.
