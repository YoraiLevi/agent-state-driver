# Discovery: `~/.claude/sessions/<pid>.json` — a vendor-written status sidecar

**Status: verified independently, twice.** Found by prototype C (2026-08-05), then
re-verified by the orchestrator in a separate controlled session before being adopted.
This channel appears in none of the 14 projects surveyed in
`docs/.research/prior-art/SYNTHESIS.md`, and in none of the vendor docs read for Q5.

## What it is

Claude Code writes one JSON file per running session, named by PID, under
`~/.claude/sessions/`. Observed schema (2.1.222):

```json
{"pid":40326,"sessionId":"bfaf7ed8-...","cwd":"/abs/path","startedAt":1785953027931,
 "procStart":"Wed Aug  5 18:03:45 2026","version":"2.1.222","peerProtocol":1,
 "kind":"interactive","entrypoint":"cli","name":"protoc-c5","nameSource":"derived",
 "status":"idle","updatedAt":...,"statusUpdatedAt":...,"bridgeSessionId":"session_..."}
```

Status vocabulary observed: `idle` · `busy` · `waiting` (with `waitingFor`, e.g.
`"permission prompt"`).

## Why it matters

It is the only channel found that is **all** of the following at once:

- **Machine-readable and vendor-emitted** — not scraped, not inferred, no UI copy to drift.
- **Available for attached sessions** — no settings write, no spawn requirement, no hooks.
  Combined with the Q1 hook-retrofit result, this demolishes the survey's C1 conclusion
  that observing a human-launched session is screen-scrape-only.
- **Fast** — `statusUpdatedAt` measured 18 ms after the transcript `tool_use` record,
  10 ms after a prompt record, 9 ms after `turn_duration` (prototype C measurements).
- **Directly answers the hardest state.** `waitingFor: "permission prompt"` is exactly the
  signal the OTel `blocked_on_user` span promised and failed to deliver live (Q4: 37.9 s
  export lag). Here it is, on disk, in milliseconds.

## Verification log

Orchestrator's independent run (session `bfaf7ed8-a50f-46c8-a285-e4f7bc033622`):

```
sidecar=/Users/m5air/.claude/sessions/40326.json
t+3s .. t+24s   status=waiting  waitingFor=permission prompt   (8 consecutive polls)
driver A (screen channel), same instant: state=waiting:permission
after deny:     status=idle     waitingFor=-
after kill:     file DELETED (clean termination), pid confirmed dead
```

Cross-channel agreement with the independent screen channel was exact.

## How it lies — mandatory guards

1. **It is edge-triggered, not a heartbeat.** `statusUpdatedAt` does not advance while a
   state persists (observed: unchanged across 24 s of a pending dialog; a live `busy`
   session showed an `updatedAt` 23 minutes old). **Staleness is not evidence of death or
   of a hang.** Never build a watchdog on its timestamp alone.
2. **Death handling differs by death kind** (orchestrator finding, refining prototype C's):
   - clean termination → **file is deleted**;
   - `SIGKILL` → **file survives with a stale status** (prototype C observed `"idle"` on a
     killed process).
   Therefore: every read MUST be gated on `kill -0 <pid>` liveness. File absence is a
   death *hint*, not proof (the session may never have written one yet).
3. **Look it up by `sessionId`, not by PID.** The PID in the filename is the claude
   process, which may or may not be the tmux pane's direct child depending on how it was
   launched (the orchestrator's first attempt failed on exactly this: `pgrep -P <pane_pid>`
   returned nothing because `claude` *was* the pane process). Grep the directory for the
   session UUID you already own via `--session-id`.
4. **Undocumented and unversioned.** Same risk class as the transcript JSONL: no vendor
   contract, may change without notice. Pin the observed version, self-test loudly, and
   keep the screen channel as the fallback that never disappears.
5. **`waitingFor` literals are a small vocabulary of unknown size.** Only
   `"permission prompt"` has been observed. An unrecognized literal must produce
   `conflict`, never a guess (SPEC rule 8).

## Design consequence

Adopted as a first-class channel in `docs/design/functional-design.md` (channel table,
section 3). It outranks transcript silence-inference for `waiting:permission` and is the
preferred cheap poll for `busy`/`idle`, with the screen composite retained as the
always-available floor and process liveness as the mandatory gate.

**It does not replace the screen channel.** It cannot see the trust/theme/login dialogs
(pre-session), carries no dialog option text (so it cannot drive an answer), and its
vocabulary is unverified beyond three values.
