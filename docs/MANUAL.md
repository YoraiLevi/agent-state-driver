# Manual

Reference for the single-agent driver. Every command, every state, every exit code.

For *why* it works this way, see [design/functional-design.md](design/functional-design.md).
This file is the *what* and the *how*.

---

## 1. Requirements

| | |
|---|---|
| Python | 3.9 or newer |
| tmux | any recent version (macOS/Linux). Not needed on Windows — see §8 |
| `claude` | on `PATH`, logged in |
| dependencies | none — the driver is stdlib-only |

`uv` is optional. `uv run X` and `python3 X` are interchangeable everywhere below.

---

## 2. The one command you run first

```bash
uv run prototypes/fused/driver.py --workdir . list
```

Lists every Claude session on this machine, whether you started it or not.

```json
{"sessions":[
  {"sessionId":"e09b7d42-…","pid":63472,"cwd":"/tmp/x","status":"idle",
   "waitingFor":null,"name":"attachdemo-07","nameSource":"derived",
   "kind":"interactive","version":"2.1.222","alive":true}
]}
```

If this returns an empty list while a Claude session is running, see §7.

---

## 3. Commands

All commands take `--workdir DIR` (before the subcommand). It is where per-session
bookkeeping is stored; use the same one for a given session.

**Define a shortcut as a function, not a variable.** `D="uv run … --workdir ."`
then `d launch` works in bash but **fails in zsh** (the default macOS shell),
because zsh does not word-split unquoted variables. A function works in both:

```bash
d() { uv run prototypes/fused/driver.py --workdir . "$@"; }
d list
```
The recipes in §6 use `d`.

Every command prints **one JSON object per line** to stdout.

### `launch`
Starts a new agent in its own tmux server and answers the startup dialogs.

```bash
d launch
```
```json
{"id":"e09b7d42-…","state":"idle","settled":"idle"}
```
Keep `id` — every other command needs it. Takes 8–20 s (it waits out startup).

### `list`
Every live session on the machine. No arguments. See §2.

### `attach`
Adopt a session this process did not launch.

```bash
d attach --session-id <uuid> [--socket <tmux-socket>]
```
```json
{"id":"…","pid":63472,"screen_available":true,"report":{…}}
```
Without `--socket` there is no terminal to read: state still works, but dialogs
**cannot be answered**. The reply says so explicitly:
`"screen_available": false, "cannot": "answer dialogs (no terminal); detection only"`.

### `state`
What the agent is doing, now.

```bash
d state --id <id>
```
```json
{"state":"waiting:permission",
 "attrs":{"background_work":false},
 "evidence":[{"channel":"sidecar","signal":"status=waiting waitingFor=permission prompt","at":1785…},
             {"channel":"screen","signal":"permission_dialog","at":1785…}]}
```
Takes ~1–4 s: it deliberately samples more than once (§5).

### `wait`
Block until the agent reaches one of the given states.

```bash
d wait --id <id> --until idle [--timeout 120]
d wait --id <id> --until idle,waiting:permission --timeout 300
```
Comma-separated. Exit **3** on timeout, with the last reading attached.

### `send`
Type a prompt and press Enter.

```bash
d send --id <id> --text "run the tests"
d send --id <id> --text "…" --force     # send anyway, whatever the state
```
```json
{"sent":true,"verified_on_screen":true}
```
**Refuses with exit 4 unless the agent is `idle`.** That refusal is the feature —
see §6. `verified_on_screen` confirms the text actually landed.

### `answer`
Answer a dialog by option number, top to bottom, 1-based.

```bash
d answer --id <id> --option 1     # usually "Yes"
d answer --id <id> --option 3     # usually "No"
```
Read `screen` first — option order is not guaranteed and differs per dialog.
Exit **4** if no dialog is showing.

### `screen`
The agent's visible screen. For debugging and for reading dialog options.

```bash
d screen --id <id> [--lines 25]
```
Plain text, not JSON.

### `kill`
Terminate the session and clean up.

```bash
d kill --id <id>
```

---

## 4. States

| State | Means | Proven by | Can you send? |
|---|---|---|---|
| `starting` | launched, still in trust/theme/login dialogs | screen | no |
| `idle` | ready for a prompt | busy-marker absent **and** screen settled | **yes** |
| `busy` | working — thinking or running a tool | spinner/tool line, or vendor status | no |
| `waiting:permission` | stopped, asking a human to approve a tool | vendor `waitingFor`, dialog on screen | no — `answer` instead |
| `waiting:input` | stopped, asking a question | dialog rows on screen | no — `answer` instead |
| `presumed_hung` | claimed busy, but nothing has changed for a long time | watchdog | no |
| `dead` | the process is gone | process check | no |
| `conflict` | signals disagree, or a state cannot be cleared | — | no |

`conflict` is not an agent state. It describes the **observer**: it means the tool
does not know, and refuses to invent an answer. `attrs.reason` says which signals
disagreed.

Attributes seen alongside states:

| Attribute | Meaning |
|---|---|
| `background_work: true` | the turn ended but a background shell is still running |
| `screen_available: false` | attached without a terminal — detection only |
| `degraded` | one channel is unavailable; the state came from the others |

---

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | unknown session id, or an attach target that is not live |
| 3 | `wait` timed out |
| 4 | refused — wrong state for this command (`send` when not idle, `answer` with no dialog) |
| 5 | launch failed (`claude` not on PATH, tmux failed) |

**State is never encoded in an exit code.** A non-zero exit means *the command*
failed, not that the agent is in some particular state.

---

## 6. Recipes

**Run a prompt and wait for the answer**
```bash
d() { uv run prototypes/fused/driver.py --workdir . "$@"; }

ID=$(d launch | jq -r .id)
d send --id $ID --text "summarise README.md"
d wait --id $ID --until idle --timeout 300
d screen --id $ID --lines 30
d kill --id $ID
```

**Handle a permission dialog**
```bash
d send --id $ID --text "run the test suite"
d wait --id $ID --until idle,waiting:permission --timeout 300

case "$(d state --id $ID | jq -r .state)" in
  waiting:permission) d screen --id $ID --lines 12   # read the options first
                      d answer --id $ID --option 1 ;;
  idle)               echo "finished without asking" ;;
esac
```

**Watch a session a human is using**
```bash
ID=$(d list | jq -r '.sessions[0].sessionId')
d attach --session-id $ID --socket <their-tmux-socket>
watch -n2 "uv run prototypes/fused/driver.py --workdir . state --id $ID | jq -c '{state}'"
```

**Attach with your own eyes**
```bash
tmux -L fused-<first-8-of-id> attach -t <first-8-of-id>
# leave with Ctrl-B then D; the agent keeps running
```

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `list` is empty but Claude is running | the session is under a different config dir | set `CLAUDE_CONFIG_DIR` to match, or check `~/.claude/sessions/` |
| `list` is empty for a `-p` / headless run | headless writes no session file | headless is not observable; use an interactive session |
| `send` exits 4 forever | the agent is on a dialog | `screen`, then `answer` |
| `state` says `conflict` | signals disagree — often a statusline clock | read `attrs.reason`; it is telling you it does not know |
| `state` says `starting` and stays | an unanswered startup dialog | `screen`, then `answer --option 1` |
| `attach` exits 2 | no live session with that id | `list` — the process may have exited |
| dialogs cannot be answered after `attach` | attached without `--socket` | re-attach with the tmux socket |
| `launch` exits 5 | `claude` not on PATH | check `command -v claude` |
| `d launch` → "no such file or directory" | zsh does not word-split variables | use the `d()` function form in §3 |

---

## 8. Platform notes

| | |
|---|---|
| **macOS / Linux** | as documented above; tmux is the terminal host |
| **Windows** | no tmux. The terminal host is a ~90-line node ConPTY program (`containers/windows/conpty-host.js`); every state and signal is unchanged. See [.research/empirical/windows-leg.md](.research/empirical/windows-leg.md) |
| **Containers** | prebuilt for both families in [containers/](../containers/) |

---

## 9. Limits

Stated plainly, because finding these out by surprise is expensive:

- **Only Claude Code.** Other CLI agents are not implemented.
- **`presumed_hung` is not tuned.** The threshold is a guess; compaction time has
  never been measured, so a long compaction may be misreported.
- **`waiting:input` is under-tested** against real question dialogs.
- **Dialog text is unversioned vendor copy.** It is matched as versioned *sets*
  with a loud self-test, but a vendor wording change can still break detection.
  Pinned to CLI 2.1.222.
- **One agent per command.** Multi-agent orchestration is designed but unfinished.
- **`attach` without a terminal cannot drive.** Detection only, and it says so.
