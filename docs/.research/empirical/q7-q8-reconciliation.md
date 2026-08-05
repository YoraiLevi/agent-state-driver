# Reconciliation: does `esc to interrupt` exist in Claude Code 2.1.222?

Two first-hand probes on the same build, same host, same day, contradicted each other.
A third experiment settles it. Date 2026-08-05, claude 2.1.222, macOS.

## The contradiction

- **Q7** (`q7-false-idle.md`): 0 hits in 155 captures across 3 runs; `strings` on the binary
  found no `to interrupt`. Concluded "the string no longer exists in the product."
- **Q8** (`q8-altscreen-bel.md`): used `grep -c 'esc to interrupt'` as its busy ground truth
  and reported busy=1 transitions — i.e. the string was present in its captures.

## The settling experiment

One fresh `claude --safe-mode` TUI (private tmux socket `conflict`), one pure text-generation
turn ("Count from 1 to 30"), 14 captures at 0.7 s.

**Observed:** `esc to interrupt` present in **4 of 14** captures, rendered as
`… to interrupt · ← 1 agent …` in the footer. Spinner forms seen concurrently:
`✶ Clauding… (0s)`, `✢ Hullaballooing… (2s)`.

## Read as

The hint is **phase- and configuration-dependent**, not removed:

| Condition | Hint visible? | Evidence |
|---|---|---|
| Text generation, `--safe-mode` session | yes (intermittently — 4/14 samples) | this experiment |
| Turn dominated by a foreground tool call | no — tool hint `(ctrl+b ctrl+b (twice) to run in background)` shown instead | Q7 run 3, samples 5-41 |
| Session with user config active (statusline etc.), incl. generation-phase samples | no, 0/75 | Q7 run 3 samples 1-4 + runs 1-2 — suppressing factor not isolated |

Q7's `strings`-on-binary negative is unreliable (the CLI is a compiled/packed bundle; absence
from `strings` output does not prove absence from the product) and is hereby retracted as
evidence. Q7's **capture** evidence stands. Q8's ground-truth label stands.

## Design consequence (supersedes both probes' phrasing)

`esc to interrupt` is **worse than absent — it is intermittent**, varying by turn phase,
sample timing, and (unisolated) configuration. A gate on it fails closed (reads idle) in
whole classes of sessions, silently.

The busy predicate must be the composite from Q7, which survives every observed condition:

1. **Busy** = a line matching spinner-verb form `^[✢✳✶✽✻·*]\s+\w+…\s*\(\d+s` OR a tool-run
   line `⎿\s+Running…\s*\(\d+s`.
2. **Idle** = busy-regex absent AND N≥3 consecutive byte-identical ANSI-stripped captures
   (hash-stability; busy screens change every ≤1 s via two independent tickers).
3. Exclude past-tense completion forms (`\w+ed for \d+s`, no ellipsis/timer parens).
4. Treat any footer-hint string (`esc to interrupt`, tool background hint) as corroboration
   only, never as the gate.

## Coverage declared

Verified on one build (2.1.222), one host, macOS, three session configurations. Not verified:
which configuration factor suppresses the hint (statusline vs output-style vs other); Linux
and Windows rendering; non-English locales.
