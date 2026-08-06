# Documentation index

Three ways in. Pick the one that matches why you're here.

---

## I want to use this

| Read | Why |
|---|---|
| **[MANUAL.md](MANUAL.md)** | **The reference: every command, state, exit code, recipe, and limit** |
| [ecosystem-map.md](ecosystem-map.md) | AgentCulture: all ~78 repos categorised, with ADOPT/WATCH/IGNORE and a build order |
| [../README.md](../README.md) | What it does, in 60 seconds |
| [../demo.py](../demo.py) — `uv run demo.py` | Watch all six states detected on a real session |
| [../prototypes/common/SPEC.md](../prototypes/common/SPEC.md) | The driver contract: every command, every state, every rule |
| [../containers/README.md](../containers/README.md) | Prebuilt Linux and Windows environments |
| [../PITFALLS.md](../PITFALLS.md) | **Read before writing your own detector.** Every trap here cost us a run |

**Which driver should I use?** `prototypes/fused/` unless you have a reason. It reads the
vendor sidecar, the screen, and the process, and reports `conflict` instead of guessing
when they disagree. The others exist to show what each channel can do *alone* —
see the [race results](results/RACE-macos.md).

---

## I want to understand the problem

| Read | Why |
|---|---|
| [design/functional-design.md](design/functional-design.md) | The state model, all channels compared, fusion rules, and the failure-mode analysis |
| [discovery-session-sidecar.md](discovery-session-sidecar.md) | The undocumented vendor status file — the single most useful thing found here |
| [.research/prior-art/SYNTHESIS.md](.research/prior-art/SYNTHESIS.md) | How 14 other projects solve this, what each gets wrong, and the conclusions (C1–C11) that constrain the design |

**Start with the design doc's section 3** (the channel table) if you only read one thing.
It says what each channel can prove, how fast, and exactly how it lies.

---

## I want the evidence

Nothing in this repo is asserted without a record. These are the records.

| Read | Contains |
|---|---|
| [results/RACE-macos.md](results/RACE-macos.md) | Four prototypes raced under an independent referee, with latencies |
| [results/linux/](results/linux/) | Real CLI on real Linux (WSL2) — and the two bugs that only Linux could expose |
| [results/PORTABILITY.md](results/PORTABILITY.md) | Cross-platform detector verification |
| [results/s6b/](results/s6b/) | The premature-death probe — two prototypes caught claiming `dead` on a live process |
| [results/conflict/](results/conflict/) | A live channel disagreement, reported rather than resolved |
| [.research/empirical/](.research/empirical/) | Every probe that settled an open question, with method and raw observations |

Two documents are worth reading purely as method:
- [.research/empirical/q7-q8-reconciliation.md](.research/empirical/q7-q8-reconciliation.md) —
  two probes contradicted each other; a third experiment settled it and the losing evidence
  is explicitly retracted.
- [.research/empirical/windows-leg.md](.research/empirical/windows-leg.md) — hosting an
  interactive agent on native Windows with no tmux.

---

## I want to contribute

| Read | Why |
|---|---|
| [../HANDOFF.md](../HANDOFF.md) | Current state, open work, and what is deliberately unbuilt |
| [../STATE.md](../STATE.md) | Ground truth: phases, locked decisions, environment facts |
| [../tests/](../tests/) | `uv run pytest` — 23 tests, no credentials, no API cost |

House rules, in one line each: **no claim without a record**; **a channel that fails must
fail loudly**; **a test that cannot fail the defect it targets is not evidence**; and
inconclusive is never scored as a pass.
