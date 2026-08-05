# Q7 — The silent-tool-call false-idle hole (real session)

Probe date 2026-08-05 · macOS 25.5.0 · claude 2.1.222 · model Sonnet 5 · tmux socket `probe-q7`
(`-f /dev/null`) · pane 200x50 · test dir
`/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/q7-idle`

## Question

During a long, output-silent **foreground tool call**, does the Claude Code TUI screen keep
changing? Specifically:

- (a) Is there a longest run of byte-identical consecutive captures while the agent is busy —
  i.e. would a hash-diff / silence-timer detector false-idle?
- (b) Does the busy indicator stay visible for the WHOLE silent call?

## Method (exact commands)

Settings written to the test dir (never `~/.claude`):

```
/private/tmp/.../q7-idle/.claude/settings.json
{"hasTrustDialogAccepted": true, "permissions":{"allow":["Bash(sleep:*)","Bash(echo:*)","Bash(ping:*)"]}}
```

Launch and drive:

```bash
tmux -L probe-q7 -f /dev/null new-session -d -s q7 -x 200 -y 50 -c "$D" "cd $D && claude --model sonnet"
tmux -L probe-q7 -f /dev/null send-keys -t q7 -l '<prompt>'      # literal text
tmux -L probe-q7 -f /dev/null send-keys -t q7 Enter              # SEPARATE call
```

Sampler (`sample3.sh`, 1 s interval, 75 samples) — both encodings hashed each tick:

```bash
tmux -L probe-q7 -f /dev/null capture-pane -t q7 -p -e -S -60 > raw_$i.txt   # with ANSI
tmux -L probe-q7 -f /dev/null capture-pane -t q7 -p    -S -60 > plain_$i.txt # stripped
shasum raw_$i.txt ; shasum plain_$i.txt
```

Teardown: `/exit` then `tmux -L probe-q7 -f /dev/null kill-server` (verified:
`no server running on /private/tmp/tmux-501/probe-q7`).

Three runs were needed:

| Run | Prompt | Outcome |
|---|---|---|
| 1 | `sleep 45 && echo DONE-MARKER` | **Invalid** — nested claude inherited the host's Bash guard: `Error: Blocked: sleep 45 followed by: echo DONE-MARKER`. It backgrounded the sleep instead; no foreground silent call happened. |
| 2 | bare `sleep 40`, foreground | **Invalid** — `Error: Blocked: standalone sleep 40`. Same guard. |
| 3 | `ping -c 40 -i 1 127.0.0.1 > /dev/null` | **Valid** — ran 40 s in the foreground, produced `⎿  (No output)`. This is the run analysed below. |

`sleep` is unusable as a nested-probe workload on this host — the harness's foreground-sleep
block is inherited by nested sessions. Use `ping -c N -i 1 127.0.0.1 > /dev/null`.

## Observed

### (a) Screen change during the silent call — zero identical consecutive captures

Run 3 timeline (1 s sampling; `raw` = `-e` ANSI capture, `plain` = stripped). Every hash is
distinct while busy; the first repeat only appears after the turn ends.

```
 5   4s  raw=841ce6f2  plain=d4ab4287     <- tool call visible, "Running… (3s)"
20  20s  raw=11666575  plain=55404030
30  31s  raw=b708afc8  plain=741fea3c
40  41s  raw=4e885310  plain=fe0fef5a
43  44s  raw=d7fe5c5a  plain=464b13c7     <- last busy sample
44  45s  raw=f3c20a03  plain=12f5a4dd
46  47s  raw=d0d0d9d4  plain=9cd5b411     <- turn done; screen freezes here
...
75  78s  raw=d0d0d9d4  plain=9cd5b411     <- 30 identical samples, all post-turn
```

Longest identical run, raw and plain alike:

```
=== longest identical runs (plain) ===   === longest identical runs (raw) ===
  30 9cd5b411                              30 d0d0d9d4
   1 fe0fef5a                               1 fb468a46
```

The single run of 30 is entirely **after** the turn finished (samples 46-75). Across samples
1-45 (busy), the longest identical run is **1** — the screen changed on every single 1 s tick.

Two independent per-second tickers are responsible. Mid-call pane content (sample 30, t=31 s):

```
❯ Run exactly this one command: ping -c 40 -i 1 127.0.0.1 > /dev/null . Then reply pong.
∴ I should just execute what's being asked and respond with pong.
  Bash(ping -c 40 -i 1 127.0.0.1 > /dev/null)
  ⎿  Running… (26s · timeout 45s)
     (ctrl+b ctrl+b (twice) to run in background)
✽ Deciphering… (30s · ↓ 150 tokens)
```

- `⎿  Running… (26s · timeout 45s)` — a **per-tool-call elapsed timer** with the tool's timeout.
- `✽ Deciphering… (30s · ↓ 150 tokens)` — the **turn spinner**: rotating glyph
  (`✢ ✳ ✶ ✽ ✻` all observed) + elapsed seconds + a token counter.

The call really was silent — its completed form (sample 46) is:

```
⏺ Bash(ping -c 40 -i 1 127.0.0.1 > /dev/null)
  ⎿  (No output)
  ⎿  (timeout 45s)
⏺ pong
✻ Cogitated for 45s
```

The custom statusline (`$0.305 | wall 27s | API 5s | …`) is **not** a ticker — it was
byte-identical from sample 5 to sample 43 and only re-rendered on turn events. It cannot be
relied on for liveness.

Counter-evidence for the idle side, from run 1: with no turn running (a background shell was
still executing), the pane was byte-identical for **26 consecutive 2 s samples (~39 s)**,
t=13 s → t=52 s, until the background-completion notification landed. So the screen genuinely
does freeze when idle — the change signal is not ambient noise.

### (b) The busy indicator — `esc to interrupt` DOES NOT EXIST in 2.1.222

Per-capture presence over run 3 (`Running…` line, and a spinner line of shape
`<glyph> <Verb>… (<N>s`):

```
1 run=0 spin=0 | 2 run=0 spin=1 | 3 run=0 spin=1 | 4 run=0 spin=1 | 5 run=1 spin=1 |
... (unbroken) ... | 41 run=1 spin=1 | 42 run=0 spin=1 | 43 run=0 spin=1 |
44 run=0 spin=0 | 45 run=0 spin=0 | 46 run=0 spin=0 | ...
```

The spinner is present **continuously from sample 2 (t=1 s) through sample 43 (t=44 s)** — the
entire turn including the whole 40 s silent call — with **no gap**. The `Running…` line covers
the tool call itself, samples 5-41.

But the PITFALLS-prescribed gate string is absent:

```
$ grep -c 'esc to interrupt' caps3/plain_*.txt | grep -v ':0' | wc -l
       0                                    # 0 of 75 captures (also 0 of the 80 in runs 1-2)

$ strings /Users/m5air/.local/share/claude/versions/2.1.222 | grep -i 'to interrupt'
(no output)
```

The literal substring `to interrupt` **does not occur anywhere in the 2.1.222 binary**. The
nearest hints in the binary are keybinding descriptions (`"User interruption with CTRL-C"`) and
the in-pane hint under a running tool is `(ctrl+b ctrl+b (twice) to run in background)`, not an
esc hint.

### The idle/busy glyph trap

Both busy and idle lines start with the same glyph class. Busy vs finished:

```
✽ Deciphering… (30s · ↓ 150 tokens)     <- BUSY  (present participle + "…" + "(Ns · ↓ N tokens)")
✻ Cogitated for 45s                     <- IDLE  (past tense + "for Ns", no parens)
✻ Crunched for 9s · 1 shell still running <- IDLE (with a background shell still alive)
```

A detector matching only the spinner glyph, or `\(\d+s`, will latch busy forever on the
finished line.

## Verdict

**ANSWERED-YES** — the hole is characterised, and on 2.1.222 it is *not* a hole for a screen-diff
detector, but the busy-gate recipe in PITFALLS is broken.

- (a) ANSWERED-YES: during a 40 s output-silent foreground tool call the pane changed on **every
  1 s sample** — longest identical run while busy = **1** (raw and ANSI-stripped alike). A
  hash-diff / silence-timer detector with any threshold ≥ 2 s does **not** false-idle here.
- (b) ANSWERED-NO as written: `esc to interrupt` was never visible because **it no longer exists
  in the product**. The equivalent gate — the turn spinner — *was* visible for the whole silent
  call with no gap, so the busy-gate concept survives; only its string is wrong.

Remaining / not covered by this probe:

- Sampling was 1 s; a sub-second render gap could exist but is irrelevant to any practical
  detector.
- Only one silent-tool shape was tested (foreground Bash, 40 s, no output). Not tested: a silent
  MCP/network tool call, a tool exceeding its timeout, or a turn awaiting a permission dialog
  (the dialog case is a different state, Q-permission).
- Only one build (2.1.222) and one host. The ticker's existence is likely stable, but the exact
  strings are clearly version-volatile — `esc to interrupt` was real in earlier builds and is
  gone now.
- Windows/Linux rendering unverified.

## Design consequence

1. **Do not gate on `esc to interrupt`.** It is absent from 2.1.222 entirely. Update PITFALLS —
   the current entry will make every busy-gate read "idle" instantly, which is a *worse* failure
   than the one it was written to prevent.
2. **Busy predicate (screen channel), version-tolerant:** a line matching a spinner glyph
   `[✢✳✶✽✻·*]` followed by a word ending in `…`, followed by `(<N>s` — i.e.
   `(?m)^\s*[^\w\s]\s+\w+…\s*\(\d+s\b`. Explicitly **exclude** the past-tense completion form
   `\w+ed for \d+s` (no ellipsis, no parenthesised timer). Optionally OR in
   `⎿\s+Running…\s*\(\d+s` for tool-level granularity.
3. **Screen-change is a usable liveness signal on this build, and is version-independent** in a
   way string matching is not: two per-second tickers guarantee ≥1 change/second while busy, and
   the pane is provably byte-stable (39 s observed) when idle. Recommend the driver use
   *hash-stability* as the primary liveness gate and the busy regex as a corroborating gate —
   ready = busy-regex absent **AND** N consecutive identical captures. That composite survives a
   future rename of the spinner verbs, which a string-only gate does not.
4. **Stability threshold:** with 1 s polling, `--settle 3` (≈3 s of stillness) is safely above
   the observed busy-change period of 1 s. Do not go below 2.
5. **Hash the ANSI-stripped capture (`-p` without `-e`).** Raw `-e` and stripped agreed
   perfectly on every sample in this probe, so `-e` buys nothing and costs cursor/colour noise.
6. **Idle ≠ nothing running.** A finished turn can leave a background shell alive
   (`✻ Crunched for 9s · 1 shell still running`), and its completion later redraws the pane
   ~39 s after the turn ended. The driver must treat a post-idle redraw as a legitimate event,
   not a state-machine violation.
7. **Nested-probe workload note (harness-specific):** foreground `sleep` is blocked for nested
   sessions by the inherited Bash guard. Any future timing probe must use
   `ping -c N -i 1 127.0.0.1 > /dev/null`.
8. `hasTrustDialogAccepted` in a project's `.claude/settings.json` does **not** suppress the
   folder-trust dialog on first launch — it still appeared and had to be answered with `Enter`.
   The driver's launch sequence must handle the trust dialog unconditionally.
