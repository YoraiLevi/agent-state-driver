# Q4 — `claude_code.tool.blocked_on_user`: does it exist, what is it, how fast?

Probe date: 2026-08-05 · claude 2.1.222 (macOS arm64, Darwin 25.5.0) · tmux 3.7b

## Question

Does the telemetry identifier `claude_code.tool.blocked_on_user` exist first-hand? What kind of
signal is it (metric / log event / span)? What is its emit-to-observe latency — i.e. can it serve
as a PTY-free "this agent is waiting on a permission decision **right now**" signal?

## Method

Test project: `/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/q4-otel`, containing only `.claude/settings.json`
with `{"permissions":{"allow":[],"deny":[]}}`. The user's `~/.claude` was never written.
All sessions ran `claude --safe-mode`, max 3 turns, one short prompt each. Private tmux socket
`-L probe-otel -f /dev/null`, killed at the end (`no server running on /private/tmp/tmux-501/probe-otel`).

Readiness/dialog detection used a bash poll on `tmux -L probe-otel capture-pane -p -S -80`
(blank rows stripped), gated on the string `Do you want to proceed`, per PITFALLS.md.

**Run 1 — console exporters (as briefed).**

```
cd $D && CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_METRICS_EXPORTER=console OTEL_LOGS_EXPORTER=console \
  OTEL_METRIC_EXPORT_INTERVAL=5000 OTEL_LOGS_EXPORT_INTERVAL=2500 claude --safe-mode 2>console.log
```

Prompt: `Run exactly this bash command: touch probe.txt` → permission dialog appeared → held ~35 s
→ Escape → `/exit`.

**Run 2 — self-hosted OTLP collector (fallback, because run 1 produced nothing).**

A 30-line Python `http.server` bound to `127.0.0.1:4318` answering `POST /v1/metrics|/v1/logs|/v1/traces`
with `200`, appending each raw protobuf body to `otlp.dump` prefixed by a `time.time()` receive
stamp. Launch:

```
CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_METRICS_EXPORTER=otlp OTEL_LOGS_EXPORTER=otlp \
  OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
  OTEL_METRIC_EXPORT_INTERVAL=5000 OTEL_LOGS_EXPORT_INTERVAL=2500 claude --safe-mode
```

**Run 3 — same, plus traces and the enhanced-telemetry beta flag** (chosen after reading the
shipped bundle, see Observed):

```
... CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 OTEL_TRACES_EXPORTER=otlp ... claude --safe-mode
```

Same prompt; dialog held ~33 s; answered `1. Yes` (Enter). Span fields decoded with a hand-rolled
protobuf walker (`startTimeUnixNano` = field 7, `endTimeUnixNano` = field 8, attributes = field 9).

**Static check.** `strings -n 8 /Users/m5air/.local/share/claude/versions/2.1.222` on the shipped
Mach-O binary (the `claude` shim is a symlink to it).

## Observed

### 1. The identifier exists in the shipped binary — as a TRACE SPAN

`strings` over the 2.1.222 binary yields exactly 20 `claude_code.*` identifiers, including:

```
claude_code.tool
claude_code.tool.blocked_on_user
claude_code.tool.execution
```

The creating code (verbatim from the bundle, function names are minified):

```js
function fpu(){ ... let r=mG(), n=DLt("tool.blocked_on_user"),
  o=r.startSpan("claude_code.tool.blocked_on_user",{attributes:n},t);
  return kdt(DQr,{span:o,startTime:performance.now(),attributes:n,perfettoSpanId:e,priorContext:t}),o }

function MQr(e,t){ let r=Flr(DQr); if(!r)return; ...
  let o={duration_ms:Math.max(0,Math.round(performance.now()-r.startTime))};
  if(e)o.decision=e; if(t)o.source=t;
  r.span.setAttributes(o), r.span.end(), xdt(DQr,r) }
```

`mG()` is `BT.trace.getTracer("com.anthropic.claude_code.tracing","1.0.0")`. So it is an
**OpenTelemetry span**, not a metric and not a log record. It is **started** when the permission
prompt opens and **ended** only when the decision arrives (`MQr(decision, source)`), carrying
`duration_ms`, `decision`, `source`.

Gating, verbatim:

```js
function Sls(){ let e=process.env.CLAUDE_CODE_ENHANCED_TELEMETRY_BETA??process.env.ENABLE_ENHANCED_TELEMETRY_BETA;
  if(tr(e))return!0; if($u(e))return!1; return!1 }
function Jae(){ return Sls()||NL() }
```

Every real-span path is behind `Jae()`; when it is false the code returns a throwaway
`mG().startSpan("dummy")`. There is also a Perfetto-only sibling `tpu("tool_permission")` producing
a local trace event named `"Waiting for User Input"` (`CLAUDE_CODE_PERFETTO_TRACE`) — same
start/end shape.

### 2. Console exporters emit nothing observable

`console.log` (stderr) stayed **0 bytes** for the entire run 1 session — through startup, the
prompt, ~35 s of dialog, and shutdown flush. `tmux capture-pane -p -S -3000 | grep -c claude_code`
returned `0`, so it did not go to stdout-in-pane either. Same for both OTLP runs' stderr files:

```
0 .../q4-otel/console.log
0 .../q4-otel/otlp-stderr.log
0 .../q4-otel/otlp2-stderr.log
```

Meanwhile the identical env with `OTEL_*_EXPORTER=otlp` produced traffic within seconds — so
telemetry itself was on, and `--safe-mode` did not suppress it. **The console exporter path is
unusable for out-of-process observation in the TUI.** (Scope note: run 1 covered metrics + logs
consoles only; `OTEL_TRACES_EXPORTER=console` was not separately tested, but the same silence
applies to the two exporters that were.)

### 3. Nothing at all is emitted while the dialog is open (both runs)

Run 2, dialog visible at `t=1785951614.807`, held to `t=1785951706.62` (**91.8 s**). Every OTLP
batch received in that window:

```
===== 1785951612.126 /v1/logs    len=4365 =====
===== 1785951613.969 /v1/metrics len=3215 =====
===== 1785951617.329 /v1/logs    len=1152 =====
===== 1785951618.969 /v1/metrics len=3234 =====
   (nothing for the next 88 seconds)
```

`strings otlp.dump | grep -ic blocked` → `0`. The exporters go completely quiet while blocked —
there is not even a periodic heartbeat batch to piggyback on.

### 4. The signal arrives only AFTER the human answers

Run 2 (answered `3. No` at `ANSWER_T=1785951715.871`): a `/v1/logs` batch arrived at
`1785951718.359` (**+2.49 s**, one logs-export interval) containing a log record, not a span:

```
'claude_code.tool_decision', 'event.name','tool_decision', 'event.timestamp','2026-08-05T17:41:55.853Z',
'decision','reject', 'source','user_reject', 'tool_name','Bash', 'tool_use_id','toolu_01RGHSSymcPDrrLAUhWXuDsv',
'tool_source','builtin'
```

Run 3 (enhanced beta + traces; dialog visible `1785951810.79`, answered `1. Yes` at
`ANSWER_T=1785951843.567`). Decoded span, verbatim from the walker:

```
span: claude_code.tool.blocked_on_user
  start_unix=1785951810.704 end_unix=1785951843.575  span_seconds=32.871
  export_received=1785951848.582  end->export=5.006s
  attrs: {'span.type': 'tool.blocked_on_user', 'duration_ms': 32871,
          'decision': 'accept', 'source': 'user_temporary'}
```

Span **start** (`1785951810.704`) is within 90 ms of when the dialog became visible on screen
(`1785951810.791`) — it does mark the true block onset. But the span was only put on the wire
`1785951848.582`, i.e. **5.0 s after the decision and 37.8 s after the block began**.

Causal control: `probe.txt` did not exist before (removed each run) and existed after the accept
run — `-rw-r--r-- 1 m5air wheel 0 Aug 5 20:44 probe.txt` — confirming the accepted path really ran.

Full identifier set actually observed on the wire in run 3:
`session.count`, `user_prompt`, `api_request`, `assistant_response`, `token.usage`, `cost.usage`,
`active_time.total`, `events`, `llm_request`, `tool`, `tool.execution`, `tool.blocked_on_user`,
`tool_decision`, `tool_result`, `tracing`.

## Verdict

**PARTIAL — existence ANSWERED-YES, usefulness as a waiting-signal ANSWERED-NO.**

- Exists first-hand: yes, `claude_code.tool.blocked_on_user`, confirmed both in the 2.1.222 binary
  and on the wire.
- Shape: an **OTel trace span** on tracer `com.anthropic.claude_code.tracing` v1.0.0, gated behind
  `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` / `ENABLE_ENHANCED_TELEMETRY_BETA`, attributes
  `duration_ms`, `decision` (`accept`/`reject`), `source` (`user_temporary`, `user_reject`, …),
  plus the standard resource attrs (`session.id`, `user.email`, `terminal.type`, …).
- Emit-to-observe latency **as a live waiting signal: unbounded**. OTel exports spans on `end()`,
  and this span ends at the human's decision. Observed: block began `t+0`, decision `t+32.9 s`,
  export `t+37.9 s`. A 10-minute-long block is observed 10 minutes late.
- What remains untested: whether an in-process OTel `SpanProcessor.onStart` hook (a custom
  `NODE_OPTIONS`-injected processor) could surface span-start — the OTLP protocol itself cannot,
  and Claude Code exposes no such extension point. Also untested: `OTEL_TRACES_EXPORTER=console`
  specifically, and whether `NL()` (the second half of the `Jae()` gate) can enable the span
  without the beta env var.

## Design consequence

1. **Do not build the waiting-on-permission detector on telemetry.** The one identifier that names
   the state precisely is structurally incapable of reporting it *while it is happening*: a span
   is only exported when it closes, and it closes exactly when the state ends. Telemetry is a
   post-hoc *audit* channel here, not a state channel.
2. **The block window is telemetry-silent, which is itself a weak negative signal.** Run 2 saw
   88 s with zero batches. "Last export was >N s ago" cannot distinguish waiting-on-permission
   from idle, waiting-on-input, or dead — so it is at best a corroborator, never a discriminator.
3. **Keep PTY/screen scraping (or hooks) as the primary detector for `waiting-on-permission`.**
   Screen scrape saw the dialog at `1785951810.791`; telemetry saw it at `1785951848.582`. That is
   the whole argument, in two timestamps.
4. **Telemetry earns a place as a secondary/enrichment channel**, and it is genuinely good at it:
   `claude_code.tool_decision` (a *log* record, not gated behind the beta flag) lands ~2.5 s after
   the decision with `decision`/`source`/`tool_name`/`tool_use_id`, and the blocked span gives an
   exact `duration_ms` for "how long did this agent stall a human". Use it for post-hoc metrics and
   for cross-checking the scraper's transitions — never for the live state machine.
5. **Operational notes for any prototype that ingests this:** the console exporters are dead ends
   under the TUI (write to nothing observable) — a local OTLP HTTP endpoint is the only working
   sink. Batches carry `user.email`, `user.account_uuid`, `organization.id` and `user.id`, so raw
   dumps are PII and must not be committed. The raw `otlp.dump` from this probe was deliberately
   left in the session scratchpad and not copied into the repo.
