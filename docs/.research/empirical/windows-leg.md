# Phase 4 — Windows leg: can we host, drive and observe an interactive `claude.exe` on native Windows?

**Verdict: yes, fully — and every detection channel we rely on survives the port.**
An interactive Claude Code TUI was hosted on native Windows 11 over a non-interactive SSH
session, driven programmatically, and observed on **four independent channels**
(session sidecar, hooks, transcript JSONL, rendered screen). Nothing needed admin rights,
no compiler, no tmux, no WSL.

Run date 2026-08-05 · host `devic@windesk` · Windows 11 build 26200.8875 · pwsh 7.6.3 ·
claude.exe 2.1.222 · node 26.3.0 (fnm) · driven from macOS over `ssh`.

Everything below is labelled **OBSERVED** (a command was run and its output is quoted) or
**INFERRED** (reasoned, not exercised). No capability is claimed that was not exercised.

---

## 1. Minimal working way to host an interactive `claude.exe`

**Answer: node + `node-pty` (ConPTY) + `@xterm/headless`, ~90 lines, user scope only.**

**OBSERVED.** Both packages install into a plain `npm install` in `%TEMP%` with no admin,
no Visual Studio, no `node-gyp`: `node-pty@1.1.0` ships prebuilds plus a vendored
`conpty.dll` + `OpenConsole.exe`, and `@xterm/headless` is pure JS.

```
> npm install node-pty @xterm/headless      # added 2 packages in 2s / added 1 package in 961ms
node_modules\node-pty\build\Release\conpty\conpty.dll
node_modules\node-pty\build\Release\conpty\OpenConsole.exe
```

Smoke test (`probe0.js`), first try, from a non-interactive SSH command:

```
OK node-pty loaded, exports: spawn,fork,createTerminal,open,native
EXIT {"exitCode":0}
DATA: "\u001b[?9001h\u001b[?1004h…HELLO-CONPTY\r\n24356\r\n"
```

Then `claude.exe` itself under the same ConPTY — the trust dialog painted immediately:

```
 Accessing workspace:
 C:\Users\devic\AppData\Local\Temp\aspd-win\proj
 Quick safety check: Is this a project you created or one you trust? …
 ? 1. Yes, I trust this folder
   2. No, exit
 Enter to confirm · Esc to cancel
```

### Candidate evaluation (the gist's shortlist, decided on evidence)

| Candidate | Verdict | Basis |
|---|---|---|
| **node-pty (ConPTY) + xterm-headless** | **CHOSEN — works** | OBSERVED end-to-end: spawn, screen render, keystroke injection, dialog answering, clean exit |
| `conhost.exe` / `OpenConsole.exe` direct | not needed | node-pty vendors OpenConsole and drives it for us; INFERRED that hand-rolling `CreatePseudoConsole` via P/Invoke would work, NOT exercised |
| winpty / pywinpty | rejected without testing | gist: winpty is `ReadConsoleOutputW` console scraping, dormant since 2024-02-19 and superseded by ConPTY; pywinpty binds a per-PTY loopback TCP listener with an `accept()` race and is Windows-only (costs cross-platform uniformity) |
| Windows Terminal / `wt.exe` | rejected | requires a GUI session; useless over SSH, unobservable programmatically |
| PTY-as-a-service daemons (psmux, Zellij, rmux, herdr, oly, qscreen, quil, `wezterm-mux-server`) | not needed for this project | all add a second process, a rendezvous and a bus factor to buy something we already got in 90 lines of node. Re-evaluate only if a **human** must walk up and attach to a live session |
| no-PTY (`claude -p --input-format stream-json`) | complementary, not a substitute | already established: `claude -p` writes **no** sidecar (`kind: interactive` only) and paints no TUI, so it cannot answer the "observe a real interactive session" question this project exists for |
| **no usable Python on PATH** | worked around, not fixed | Microsoft Store alias stub only; the whole leg was done in node + PowerShell, so **no Python was installed** |

### The host process must be detached correctly — two traps, both OBSERVED

1. **`Start-Process … -RedirectStandardOutput/-RedirectStandardError` breaks the ConPTY
   spawn.** The driver reached `fs.writeFileSync(inbox)` (files created, 0 bytes) and died
   at `pty.spawn` with *no* stderr. Removing the redirects fixed it. INFERRED cause:
   node-pty's ConPTY startup handshake needs unredirected std handles on the host process.
2. **A process started from an SSH command dies when that SSH session ends.** Two runs of
   `Start-Process -WindowStyle Hidden -PassThru` produced the identical corpse signature
   (`raw.log` + `inbox.txt` at 0 bytes, no `meta.json`) when the SSH command returned
   immediately; the same call succeeded when the SSH session stayed alive through a
   `Start-Sleep 8`. INFERRED cause: Windows OpenSSH kills the session's process tree.
   **Fix, OBSERVED working:** run the host from a per-user scheduled task —
   `schtasks /create /tn … /tr <.cmd> /sc once /st 00:00 /f` then `schtasks /run /tn …`.
   The driver launched this way was still alive and serving in a *later, separate* SSH
   session (`meta.json` `{"ptyPid":16040,"driverPid":8068}`, live screen render).
3. **fnm-managed node is not on any non-interactive PATH.** The first scheduled-task attempt
   returned `Last Result: 1` and created nothing, because `node` resolves through a
   per-shell `fnm_multishells` directory. Absolute path
   (`%APPDATA%\fnm\node-versions\v26.3.0\installation\node.exe`) fixed it. OBSERVED.

---

## 2. Does an interactive `claude.exe` write `~/.claude/sessions/<pid>.json`? — **YES**

**OBSERVED**, on two independent sessions. Immediately after the trust dialog was accepted:

```json
{"pid":22240,"sessionId":"49762bcf-1bed-4c87-9f0b-457390d2c10d",
 "cwd":"C:\\Users\\devic\\AppData\\Local\\Temp\\aspd-win\\proj",
 "startedAt":1785957724426,"procStart":"134304313072057287","version":"2.1.222",
 "peerProtocol":1,"kind":"interactive","entrypoint":"cli","name":"proj-43",
 "nameSource":"derived","status":"idle","updatedAt":1785957724621,
 "statusUpdatedAt":1785957724621,"bridgeSessionId":"session_019SaR4Q1AWZrV3CLTTf54vk"}
```

**The schema is schema-identical (key-for-key) the macOS schema** (docs/discovery-session-sidecar.md) with one
difference: `procStart` is a Windows FILETIME-style integer string
(`"134304313072057287"`) where macOS carries a ctime string (`"Wed Aug  5 18:03:45 2026"`).
A parser that treats `procStart` as a date string breaks on Windows.

### `status` transitions — OBSERVED, 1 Hz poll

Prompt `Reply with exactly: pong`:

```
t+00s status=busy    waitingFor=      statusUpdatedAt=1785957750927
t+02s status=idle    waitingFor=      statusUpdatedAt=1785957753166   (stable to t+39s)
```

Prompt `Create a file named probe.txt containing the text hi` (triggers a Write permission dialog):

```
t+00s..t+07s status=busy     waitingFor=
t+08s        status=waiting  waitingFor=permission prompt  statusUpdatedAt=1785957836118
              … held unchanged through t+24s …
```

`waitingFor` carries the **identical literal** `"permission prompt"` as macOS. **The whole
sidecar detection story is cross-platform.**

### The latch that hooks cannot clear, the sidecar does — OBSERVED, and it matters

PITFALLS records that on macOS a *denied* permission dialog emits **no hook event at all**,
so a hook-only observer latches `waiting:permission` forever. Windows reproduces the hook
silence **and** shows the sidecar closing the hole:

```
ESC pressed (deny) →
t+00s..t+11s status=idle  waitingFor=            # sidecar cleared within one poll
hook event count before deny: 7 · after deny: 7  # zero new hook events, incl. no Stop
screen: "⎿ User rejected write to …probe.txt"    # turn provably ended
```

**Read as:** on Windows the sidecar is the channel that *resolves* the deny-latch. A Windows
driver that fuses sidecar + hooks needs the sidecar as the tiebreaker, not the corroborator.

### Death handling — matches macOS exactly, OBSERVED both kinds

| Death | Result |
|---|---|
| `/exit` (clean) | sidecar file **deleted** — verified twice, `sessions/` empty afterwards |
| `Stop-Process -Force` (TerminateProcess ≈ SIGKILL) | sidecar **survives with stale `status":"idle"`**, `Get-Process -Id 21212` returns 0 |

So the mandatory liveness gate ports as `Get-Process -Id <pid>` in place of `kill -0`.

**Bonus, OBSERVED:** because our driver owns the ConPTY, `ptyProcess.pid` **is** the claude
PID **is** the sidecar filename (`meta.json ptyPid: 21212` ↔ `sessions\21212.json`). The
macOS PID-discovery trap (PITFALLS: `pgrep -P <pane_pid>` returns nothing) does not arise
on this architecture at all — cache `ptyPid` at launch and you are done.

---

## 3. Transcript JSONL and hooks — **both work**, with one Windows-specific hook trap

### Transcript — OBSERVED

```
C:\Users\devic\.claude\projects\C--Users-devic-AppData-Local-Temp-aspd-win-proj\
    49762bcf-1bed-4c87-9f0b-457390d2c10d.jsonl        (47,829 bytes)
```

The mangled-cwd directory name is the drive-colon form `C--Users-devic-…` (colon and each
separator become `-`). Flat session JSONL, exactly the layout STATE.md already recorded
from the mac side. The path is also handed to you for free in every hook payload as
`transcript_path`, which is the robust way to find it (no mangling rules to reimplement).

### Hooks — OBSERVED firing, from a **project-scoped** `.claude/settings.json`

A `.claude/settings.json` written only into the throwaway `%TEMP%\aspd-win\proj` directory
(the user's `C:\Users\devic\.claude` settings were never touched) produced, in order:

```
SessionStart      {"source":"startup","model":"claude-opus-5"}
UserPromptSubmit  {"prompt":"Reply with exactly: pong"}
Stop              {"stop_hook_active":false,"last_assistant_message":"pong",…}
Notification      {"message":"Claude is waiting for your input","notification_type":"idle_prompt"}
UserPromptSubmit  {"prompt":"Create a file named probe.txt containing the text hi"}
PermissionRequest {"tool_name":"Write","tool_input":{"file_path":"C:\\Users\\devic\\AppDat…
Notification      {"message":"Claude needs your permission","notification_type":"permission_prompt"}
```

Every payload arrived as full JSON on the hook command's **stdin**, carrying `session_id`,
`transcript_path`, `cwd`, `hook_event_name` and the structured
`notification_type` the design relies on. The macOS event vocabulary ports unchanged.

**PITFALL (new, Windows-only, OBSERVED).** The hook command was written as
`cmd /c echo Stop >> "C:\…\hooks.log"`. The literal `Stop` **never appeared**. What landed
in the file instead was `cmd.exe`'s interactive banner, its prompt, and the hook JSON echoed
back from stdin — i.e. the `>>` was consumed by an outer shell and `cmd` ran without its
`/c` taking effect, reading the hook payload as console input.

> Consequence: **a hook `command` on Windows must not contain shell redirection or chained
> operators.** Point it at a script that reads stdin —
> `"command": "node C:\\path\\hook.js"` or `"command": "pwsh -NoProfile -File C:\\path\\hook.ps1"`
> — and let the script do the writing. (The accident was informative: it proved the stdin
> payload contract holds on Windows. It would have been a silent zero-evidence failure in a
> real detector.)

---

## 4. Screen channel — available, and **better** than the tmux surface

**OBSERVED.** Feeding the ConPTY byte stream into `@xterm/headless` and dumping
`buffer.active` every 500 ms gives a `capture-pane` equivalent with no tmux:

```
? Reply with exactly: pong

? pong

? Cooked for 2s
```

```
 Create file / probe.txt
   1 hi
 Do you want to create probe.txt?
 ? 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No
```

Both the trust dialog and the permission dialog were read off this surface, and both were
answered by writing bytes back into the PTY (`\r`, `\x1b`).

**Is it needed if 2+3 work? Yes — for two things the sidecar and hooks cannot do:**

- **Pre-session dialogs.** The trust dialog is painted *before* any sidecar exists and
  before `SessionStart` fires (OBSERVED: `sessions/` was empty while the dialog was up).
  Nothing but the screen can see it, and something must answer it — PITFALLS already
  records that `hasTrustDialogAccepted` does not suppress it.
- **Dialog option text.** The sidecar says `waitingFor: "permission prompt"` but carries no
  options; you cannot choose "3. No" without reading the screen.

Note also: because the driver owns the raw byte stream, the alt-screen/OSC/BEL evidence that
PITFALLS says `capture-pane` *cannot* see is available for free in `raw.log`. This surface
strictly dominates tmux `capture-pane` for our purposes.

Trust is remembered per folder: a second launch in the same directory skipped the dialog
entirely (OBSERVED). The launch sequence must still handle it unconditionally.

---

## 5. Recommended Windows architecture for the driver

- **Backend = a node ConPTY host process** (`node-pty` for the PTY, `@xterm/headless` for
  the screen model), one host per agent session. This is the Windows sibling of the tmux
  backend, and it satisfies the design-doc verb set (`launch/send/keys/screen/state/kill`)
  without any third-party daemon from the gist census.
- **Detach via a per-user scheduled task**, never a bare `Start-Process` from an SSH
  command, and never with `-RedirectStandardOutput/-RedirectStandardError`. Resolve
  `node.exe` by absolute path — fnm's PATH does not exist for a task.
- **Fusion order is the same as macOS, with the sidecar promoted to tiebreaker**: sidecar
  (`status`/`waitingFor`) for busy/idle/waiting, hooks for edge events and
  `transcript_path`, screen for pre-session dialogs and dialog option text, process
  liveness (`Get-Process -Id`) as the mandatory gate on every report.
- **Cache `ptyPid` at launch** — it is simultaneously the claude PID, the sidecar filename,
  and the liveness handle. No PID discovery, no `pgrep` analogue, no substring trap.
- **Two Windows-only guards in shared code**: `procStart` is an integer string, not a date;
  hook `command` values must be script invocations with no shell redirection.
- **Keep `claude -p --output-format stream-json` as a separate, non-competing mode.** It is
  the right answer when nobody needs to see a TUI, and it is already known to emit no
  sidecar; it does not replace this backend.

---

## 6. Declared coverage

**Exercised (OBSERVED):** node-pty/ConPTY install + spawn without admin; interactive
claude.exe under ConPTY over non-interactive SSH; trust-dialog detection and answering;
prompt injection and reply; sidecar creation, `busy`→`idle`, `waiting`+`waitingFor`,
clean-exit deletion, hard-kill staleness; permission dialog raised, read off-screen, denied,
and the deny-latch resolved by the sidecar while hooks stayed silent; five hook events with
full stdin payloads from a project-scoped settings file; transcript JSONL path and size;
headless screen rendering; detached hosting via scheduled task surviving SSH-session exit;
`Start-Process` redirect failure and fnm-PATH failure.

**Not exercised (remains open):**

- **Long-horizon persistence (L2/L3).** Survival across SSH-session exit is proven;
  survival across logoff/reboot, and behaviour in Windows Session 0, are not.
- **Concurrency.** One session at a time throughout. Two ConPTY hosts side by side, and
  sidecar disambiguation with a *foreign* claude also running, were not tested. (A
  pre-existing foreign `claude.exe`, PID 23024, ran the whole time and never wrote a
  sidecar — INFERRED headless/`-p`; not investigated.)
- **`waitingFor` vocabulary beyond `"permission prompt"`.** An AskUserQuestion-style dialog
  (scenario S5) was never raised on Windows.
- **`presumed_hung` / watchdog timing, and hook latency measurements.** No latency deltas
  were measured on Windows; only ordering and 1 Hz status transitions.
- **Nesting.** The gist's double-ConPTY hazard (our host running *inside* another ADE's
  ConPTY) was not tested; here the host's parent was `sshd`/`schtasks`, not a PTY.
- **P/Invoke `CreatePseudoConsole` without node**, winpty, pywinpty, and every standalone
  daemon in the gist census — rejected on documentary grounds, not on measurement.
- **Stale-sidecar garbage collection.** After a later launch the previously stale
  `24176.json` was gone; whether claude GCs stale sidecars at startup is INFERRED and
  unverified. Do not depend on it.

## 7. What was installed / left on windesk

- **Installed:** nothing durable. `node-pty` and `@xterm/headless` went into
  `%TEMP%\aspd-win\node_modules` (local project install, user scope) — **directory deleted**.
- **Removed:** `%TEMP%\aspd-win` (entire tree, incl. the test project and its
  `.claude/settings.json`), and the `aspd-driver` scheduled task
  (`schtasks /delete /tn aspd-driver /f` → SUCCESS).
- **Processes:** none left running by this work. All claude sessions were ended with `/exit`
  (sidecar deleted) or `Stop-Process`; `sessions/` was verified empty at teardown. The
  pre-existing foreign `claude.exe` PID 23024 predates this session and was left untouched.
- **Left behind, deliberately (evidence, harmless):**
  `C:\Users\devic\.claude\projects\C--Users-devic-AppData-Local-Temp-aspd-win-proj\` —
  one 47 KB transcript JSONL from the two-prompt test.
- **Left behind, unavoidable:** `%TEMP%\aspd-win\proj` was recorded as a trusted folder in
  the user's `C:\Users\devic\.claude.json` when the trust dialog was accepted. The folder no
  longer exists. No other user-global config was written.

## Appendix — the driver (reproduce in one file)

`driver.js`, run as `node driver.js <workdir> <statedir>`; commands are appended as lines to
`<statedir>\inbox.txt` (`TEXT <s>`, `CR`, `ESC`, `CTRLC`, `UP`, `DOWN`, `DIGIT n`, `KILL`);
state is published to `<statedir>\{meta.json,raw.log,screen.txt}`.

```js
const fs = require('fs'), path = require('path'), pty = require('node-pty');
const [workdir, statedir] = process.argv.slice(2);
fs.mkdirSync(statedir, { recursive: true });
const rawPath = path.join(statedir, 'raw.log'), inboxPath = path.join(statedir, 'inbox.txt');
fs.writeFileSync(rawPath, ''); fs.writeFileSync(inboxPath, '');
const CLAUDE = process.env.CLAUDE_EXE || 'C:\\Users\\<user>\\.local\\bin\\claude.exe';
const p = pty.spawn(CLAUDE, [], { name: 'xterm-256color', cols: 120, rows: 40, cwd: workdir, env: process.env });
fs.writeFileSync(path.join(statedir, 'meta.json'),
  JSON.stringify({ ptyPid: p.pid, driverPid: process.pid, workdir, startedAt: Date.now() }));
const { Terminal } = require('@xterm/headless');
const term = new Terminal({ cols: 120, rows: 40, allowProposedApi: true, scrollback: 2000 });
setInterval(() => {                                   // the screen channel
  const b = term.buffer.active, out = [];
  for (let i = 0; i < term.rows; i++) {
    const l = b.getLine(b.viewportY + i);
    out.push(l ? l.translateToString(true) : '');
  }
  fs.writeFileSync(path.join(statedir, 'screen.txt'), out.join('\n') + '\n');
}, 500);
p.onData(d => { fs.appendFileSync(rawPath, d); term.write(d); });
p.onExit(e => { fs.appendFileSync(rawPath, `\n[[exited ${JSON.stringify(e)}]]\n`); process.exit(0); });
let offset = 0;                                       // the drive channel
setInterval(() => {
  const s = fs.readFileSync(inboxPath, 'utf8');
  if (s.length <= offset) return;
  const chunk = s.slice(offset); offset = s.length;
  for (const line of chunk.split('\n')) {
    if (!line.trim()) continue;
    const sp = line.indexOf(' ');
    const verb = sp === -1 ? line.trim() : line.slice(0, sp);
    const arg  = sp === -1 ? ''          : line.slice(sp + 1);
    if (verb === 'TEXT') p.write(arg);
    else if (verb === 'CR') p.write('\r');
    else if (verb === 'ESC') p.write('\x1b');
    else if (verb === 'CTRLC') p.write('\x03');
    else if (verb === 'DOWN') p.write('\x1b[B');
    else if (verb === 'UP') p.write('\x1b[A');
    else if (verb === 'DIGIT') p.write(arg.trim());
    else if (verb === 'KILL') p.kill();
  }
}, 250);
setTimeout(() => { p.kill(); setTimeout(() => process.exit(0), 1500); },
           Number(process.env.DRIVER_TTL_MS || 600000));   // bounded run — subscription safety
```
