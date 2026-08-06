# agent-state-driver

**Know what your AI coding agent is doing — and drive it — without guessing.**

Works with Claude Code on **macOS, Linux and Windows**, verified against the real CLI on all
three.

---

## The problem, in one screen

You want to automate an agent in a terminal. So you send it a prompt and then… wait? How
long? Is it thinking, running a command, or stuck on a permission dialog nobody will ever
answer?

The obvious answer is wrong in a way that costs you hours:

```python
send_prompt("refactor the auth module")
sleep(30)                         # ← a guess
send_prompt("now run the tests")  # ← may land mid-generation and be silently dropped
```

Polling for the `❯` prompt doesn't help either — **it's on screen the entire time the agent
is generating.** Waiting for the screen to change doesn't help — an idle statusline clock
changes it. So orchestrators guess, and a fleet built on guesses fails quietly.

This gives you the real answer instead:

```bash
uv run prototypes/fused/driver.py --workdir . state --id $SESSION
```
```json
{"state": "waiting:permission",
 "evidence": [{"channel": "sidecar", "signal": "status=waiting waitingFor=permission prompt"},
              {"channel": "screen",  "signal": "permission_dialog"}]}
```

Not just *what* state — **which signal proved it**.

---

## What you get

| | |
|---|---|
| **Seven states, not two** | `starting` · `busy` · `idle` · `waiting:permission` · `waiting:input` · `presumed_hung` · `dead` — plus `conflict` when channels disagree |
| **It refuses to guess** | When the vendor status file and the screen disagree you get `conflict` with a reason, never a confident wrong answer |
| **It refuses to lose your prompt** | `send` fails loudly if the agent isn't idle, instead of typing into a blocked dialog |
| **Drive it, don't just watch it** | Launch, answer permission dialogs, wait for a state, kill — as a CLI or a library |
| **Evidence on every answer** | Every report names the channel and signal behind it, so you can audit a wrong call |
| **Cross-platform** | tmux on macOS/Linux; a node ConPTY host on Windows (no tmux needed). Same states everywhere |
| **No dependencies** | The drivers are stdlib-only Python 3.9+. Drop them on a strange machine and they work |

---

## 60 seconds

```bash
git clone https://github.com/YoraiLevi/agent-state-driver && cd agent-state-driver

uv run demo.py --mock     # free: no credentials, no API turns
uv run demo.py            # the real thing: drives a live Claude Code session
```

The demo launches an agent and narrates each state as it is detected — going busy, hitting a
permission dialog, **refusing a send while blocked**, verifying a denial actually took effect,
and establishing death from process exit rather than the terminal vanishing. Every line is a
real observation; nothing is scripted.

```
[4/6] Asking it to run a command that needs permission…
   → state: waiting:permission
     evidence [sidecar] status=waiting waitingFor=permission prompt
     evidence [screen]  permission_dialog

[5/6] Trying to send while it is blocked on a dialog (should be REFUSED)…
   → refused, correctly: refusing send in state waiting:permission
```

Then: **[docs/INDEX.md](docs/INDEX.md)** — a map of everything else.

---

## Using it in your own tooling

Every driver speaks the same JSON CLI ([full contract](prototypes/common/SPEC.md)):

```bash
D="uv run prototypes/fused/driver.py --workdir ."

ID=$($D launch | jq -r .id)                      # handles the trust dialog for you
$D wait   --id $ID --until idle --timeout 90
$D send   --id $ID --text "run the test suite"   # refuses unless idle
$D wait   --id $ID --until idle,waiting:permission
$D answer --id $ID --option 1                    # approve a dialog
$D state  --id $ID                               # {state, attrs, evidence[]}
$D kill   --id $ID
```

Exit codes are meaningful: `3` timeout, `4` refused (wrong state), `5` launch failure.
State is never encoded in an exit code.

**Attaching to a session you didn't start** is possible in principle — the vendor status file
needs no setup and hooks can be retrofitted mid-session — but the `attach` verb itself is
[not yet built](https://github.com/YoraiLevi/agent-state-driver/issues/11).

---

## How it works, briefly

Three channels, fused, because each has a hole the others cover:

```
sidecar   ~/.claude/sessions/<pid>.json   vendor-written status + waitingFor
   │      fast, needs no setup, works on sessions you didn't spawn
   │      …but blind before the first prompt, and carries no dialog options
screen    tmux capture / ConPTY           the always-available floor
   │      …but vendor UI copy drifts, and an idle clock fakes motion
process   the agent PID                   the only channel that survives death
          …but knows nothing except alive/dead
```

The interesting one is the **sidecar**: Claude Code writes a machine-readable status file per
session that appears in none of the projects surveyed and in no vendor doc. It answers "is it
blocked on a human?" directly, in milliseconds.
→ [docs/discovery-session-sidecar.md](docs/discovery-session-sidecar.md)

---

## Testing and containers

```bash
uv run pytest -m "not slow"   # 16 unit tests, instant
uv run pytest                 # 23 tests incl. live tmux sessions — no credentials, no cost
```

Prebuilt environments for both OS families — no dependency archaeology:

```bash
containers/check.sh          # macOS/Linux host, podman  → 16/16, or `test` for 23 tests
containers\check.ps1         # Windows host, docker      → 11/11 ConPTY host checks
```

The Linux image carries tmux, uv and a pinned CPython; the Windows image carries node +
node-pty (ConPTY) + `@xterm/headless`, which is how an agent TUI is hosted where there is no
tmux. Neither image contains credentials, so both run the credential-free checks only.
Details and the build traps: **[containers/README.md](containers/README.md)**.

---

## What is proven, and what isn't

Verified against the **real CLI**: `starting`, `busy`, `idle`, `waiting:permission`, `dead` —
on macOS ([race](docs/results/RACE-macos.md)), Linux
([WSL2, kernel 6.18](docs/results/linux/)) and Windows
([all four channels](docs/.research/empirical/windows-leg.md)).

**Not verified** — listed because it would be easy not to mention:
`waiting:input` against a real question dialog · `presumed_hung` live · compaction behavior
(so the hang-watchdog threshold is still a guess) · the `attach` verb · HTTP hooks ·
stream-json mode · concurrent sessions · Windows persistence across logoff.

Every number in this README traces to a record under [docs/results/](docs/results/) or a probe
under [docs/.research/empirical/](docs/.research/empirical/). An adversarial review was run
against these claims before publication and its findings applied.

## License

MIT
