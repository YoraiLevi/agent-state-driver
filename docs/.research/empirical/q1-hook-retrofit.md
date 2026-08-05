# Q1 — Can hooks be retrofitted onto a RUNNING Claude Code session?

Probe date: 2026-08-05 · claude 2.1.222 · macOS (darwin 25.5.0) · tmux 3.x on private socket `probe-q1`

## Question

Can a Stop hook be added to a Claude Code interactive session that is ALREADY RUNNING, by
writing the project `.claude/settings.json` mid-session — or must hooks be present at launch
("own-from-birth" precondition)?

## Method (exact commands)

Test project dir: `/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/q1-hooks`

1. Create dir with `.claude/settings.json` = `{"hasTrustDialogAccepted": true}` (NO hooks).
2. Launch the real TUI on a private socket:
   ```
   tmux -L probe-q1 -f /dev/null new-session -d -s q1 -x 200 -y 50 -c "$D" "cd '$D' && claude"
   ```
   No `--safe-mode` (the probe needs project settings/hooks to be honored). No
   `--dangerously-skip-permissions`. Trust dialog answered with `send-keys -t q1 Enter`.
3. Readiness gate (bash, per PITFALLS.md — the shipped `wait_for_prompt.py` has no `-L`
   socket flag, so the loop was reimplemented): poll
   `tmux -L probe-q1 capture-pane -p -t q1 -S -200`, strip trailing blank rows, require
   `❯` in the last 12 rows AND `esc to interrupt` absent AND 3 consecutive byte-identical
   captures. Script: `<scratchpad>/waitq1.sh`.
4. Turn 1: `send-keys -t q1 -l 'Reply with exactly: pong'` then, as a SEPARATE call,
   `send-keys -t q1 Enter`. Wait for ready.
5. Record baseline: transcript `stop_hook_summary` for turn 1; `ls STOP_FIRED` (control).
6. MID-SESSION WRITE: overwrite `.claude/settings.json` adding
   `hooks.Stop[0].hooks[0] = {"type":"command","command":"touch <D>/STOP_FIRED"}`.
   The claude process was never restarted, never signalled, no `/config` was opened.
7. Turn 2: `Reply with exactly: pong2`. Wait for ready. Check sentinel + transcript.
8. Turn 3 (reverse control): `rm STOP_FIRED`, restore settings to the hookless version,
   send `Reply with exactly: pong3`. Check sentinel + transcript.
9. `tmux -L probe-q1 kill-server`.

Transcript: `~/.claude/projects/-private-tmp-claude-501--Users-m5air-038e9d40-3d58-49c5-aee8-971b793af350-scratchpad-q1-hooks/b50c25f8-a362-4302-b100-01f8e3da4f3c.jsonl`

## Observed (verbatim)

**Ambient control — a global Stop hook already existed**, so every turn has a baseline
`hookCount` of 1 (the user's `~/.orca/agent-hooks/claude-hook.sh`). That makes the count
itself a clean discriminator.

`stop_hook_summary` records across the three turns (fields extracted verbatim from the JSONL):

```
2026-08-05T17:38:28.644Z hookCount= 1 ["if [ -f '/Users/m5air/.orca/agent-hooks/claude-hook.sh' ] &&"]
2026-08-05T17:39:13.479Z hookCount= 2 ["if [ -f '/Users/m5air/.orca/agent-hooks/claude-hook.sh' ] &&", 'touch /private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c']
2026-08-05T17:40:00.810Z hookCount= 1 ["if [ -f '/Users/m5air/.orca/agent-hooks/claude-hook.sh' ] &&"]
```

Turn 2's record in full (relevant fields):

```json
{"type":"system","subtype":"stop_hook_summary","hookCount":2,
 "hookInfos":[{"command":"if [ -f '/Users/m5air/.orca/agent-hooks/claude-hook.sh' ] ...","durationMs":16},
              {"command":"touch /private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/q1-hooks/STOP_FIRED","durationMs":13}],
 "hookErrors":[],"preventedContinuation":false,
 "timestamp":"2026-08-05T17:39:13.479Z","session_id":"b50c25f8-a362-4302-b100-01f8e3da4f3c","version":"2.1.222"}
```

Sentinel file, machine-checked at each stage:

```
control, before turn 2:  ls: .../STOP_FIRED: No such file or directory
after turn 2:            -rw-r--r--@ 1 m5air wheel 0 Aug 5 20:39 .../STOP_FIRED
                         mtime (UTC) = 2026-08-05T17:39:13.475288Z
after turn 3 (removed):  ls: .../STOP_FIRED: No such file or directory
```

Sentinel mtime `17:39:13.475` precedes the turn-2 `stop_hook_summary` timestamp
`17:39:13.479` by 4 ms — the file was created BY that hook invocation, not by anything else.

Screen after all three turns (verbatim, blank rows stripped) — no banner, no reload notice,
no config-change message of any kind:

```
❯ Reply with exactly: pong
⏺ pong
✻ Crunched for 3s
❯ Reply with exactly: pong2
∴ Responding to a ping with pong.
⏺ pong2
✻ Crunched for 3s
❯ Reply with exactly: pong3
⏺ pong3
✻ Worked for 2s
```

Transcript record types after turn 1 (turn-2 and turn-3 region) — no ConfigChange-like record:

```
17 system turn_duration        2026-08-05T17:38:28.646Z
18 file-history-snapshot
19 user                        2026-08-05T17:39:10.375Z
20 attachment                  2026-08-05T17:39:10.375Z
21 attachment                  2026-08-05T17:39:10.375Z
22 assistant                   2026-08-05T17:39:13.444Z
23 assistant                   2026-08-05T17:39:13.461Z
24 system stop_hook_summary    2026-08-05T17:39:13.479Z
25 system turn_duration        2026-08-05T17:39:13.480Z
```

A scan of every record for a `type`/`subtype` containing `config` returned nothing.

Incidental observation (OBSERVED): `{"hasTrustDialogAccepted": true}` in a project
`.claude/settings.json` did NOT suppress the folder-trust dialog — the TUI still asked
"Is this a project you created or one you trust?" and had to be answered with Enter. Trust
state evidently lives elsewhere (per-project entry in `~/.claude.json`), not in project
settings. (INFERRED: the location; not verified in this probe.)

## Verdict

**ANSWERED-YES.** Hooks can be retrofitted onto a running Claude Code interactive session by
writing the project settings file mid-session. The settings file is re-read per hook-event
dispatch, not cached at launch. Verified BIDIRECTIONALLY: adding the hook made it fire on the
very next turn (hookCount 1→2, sentinel created); removing it made it stop firing on the turn
after (hookCount 2→1, sentinel absent). Every claim rests on a machine signal (sentinel file
existence + mtime, transcript `stop_hook_summary.hookInfos`), not on the model's prose.

Scope of the claim, honestly bounded:
- Verified for the **Stop** event, **command**-type hook, **project-level**
  `.claude/settings.json`, claude 2.1.222, macOS, session launched WITHOUT `--safe-mode`.
- NOT verified: other events (PreToolUse/PostToolUse/Notification/SessionStart/UserPromptSubmit),
  `settings.local.json` / user-level / plugin hook sources, whether a hook added mid-session
  fires for an event that is already in flight, behavior under `--safe-mode`, and behavior on
  Linux/Windows. Each is a separate probe.
- NOT verified: whether the file is re-read on every event or on a filesystem-watch; only the
  observable ("next turn honors the new file") is established.

## Design consequence

1. **The own-from-birth precondition is DEAD for hooks.** The driver does not need to have
   launched the session to instrument it. A session a human started by hand, hours ago, can be
   given a Stop hook by the driver writing the project settings file — instrumentation is
   retrofittable and reversible at runtime. Architect the hook channel as an *attachable*
   capability, not a launch-time one.
2. **Hook config is a live control surface, not static configuration.** Adding and removing
   hooks mid-session both take effect on the next event. The driver can therefore install a
   probe hook, observe, and uninstall it, leaving the session as it found it. This also means
   the driver MUST treat the settings file as shared mutable state and merge rather than
   overwrite (see 4).
3. **The transcript is a second, independent hook oracle.** Every Stop dispatch writes a
   `system`/`stop_hook_summary` record carrying `hookCount`, the exact `command` strings,
   per-hook `durationMs`, `hookErrors`, and `preventedContinuation`. A driver can confirm its
   own hook ran — and diagnose why it didn't — without any sentinel file, purely by tailing
   the JSONL. Prefer this over screen scraping for hook-liveness checks.
4. **Retrofit is a clobber hazard.** Other hooks may already be attached from user/global
   scope (this machine had an `~/.orca` Stop hook). The driver must read-modify-write the
   project settings JSON, and the pre-existing `hookCount` is the baseline it must compare
   against — "my hook fired" is `hookCount` increased AND my command string present, never
   "a stop hook fired".
5. **Retrofit is silent.** No on-screen banner, no transcript record announces the config
   change. The driver gets no acknowledgement that its write landed; it must confirm by
   observing the NEXT hook dispatch (sentinel or `hookInfos`). Budget one turn of latency
   between "install hook" and "hook is known-live", and never assume liveness from the write
   succeeding.
6. **Trust dialog is a separate gate from settings.** Launching into a fresh directory blocks
   on the trust prompt regardless of `hasTrustDialogAccepted` in project settings, so any
   auto-attach flow that creates a new project dir must still handle that TUI dialog (or
   pre-seed trust wherever it actually lives).
