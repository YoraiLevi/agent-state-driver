# Q8 — Alternate screen and BEL as state signals (Claude Code TUI v2.1.222)

Probe date: 2026-08-05 · macOS 25.5.0 (arm64) · tmux 3.7b · claude 2.1.222 · `--safe-mode`

## Question

Does the Claude Code TUI use the terminal **alternate screen buffer**, and does it emit **BEL**
(or an OSC 9 / OSC 777 notification) on turn completion? Either would be a free, cross-platform,
scrape-independent state signal.

## Method

Test project: `/private/tmp/claude-501/-Users-m5air/038e9d40-3d58-49c5-aee8-971b793af350/scratchpad/q8-alt`
with its own `.claude/settings.json` (`{"permissions":{"defaultMode":"default","allow":[],"deny":[]}}`).
The user's `~/.claude` was never written. No `claude config set --global`. No
`--dangerously-skip-permissions`. Private tmux socket, killed at the end.

```
tmux -L probe-q8 -f /dev/null new-session -d -s q8 -x 200 -y 50 -c $D
tmux -L probe-q8 set -g monitor-bell on \; set -g bell-action any \; set -g visual-bell off
```

Three independent measurement channels:

1. **`tmux display -p '#{alternate_on}'`** — sampled at the shell baseline, at the trust dialog,
   at the idle TUI, and every 0.4 s across a full generate/complete cycle.
2. **`tmux display -p '#{window_bell_flag}'`** with `monitor-bell on` — with a positive control
   (`printf "\a"` from the shell in the same server) proving the flag mechanism works.
3. **Raw PTY byte capture**: `script -q $D/raw.log claude --safe-mode` inside a tmux pane, so every
   byte the TUI writes is recorded before tmux interprets it. Scanned with `grep -a` / `perl -0777`
   for `ESC [ ? 1049 h/l`, `ESC [ ? 47 h`, and every `\a` byte with 40 bytes of context.

Nested-session budget respected: 2 sessions, ≤3 minimal turns each ("Reply with exactly: pong",
"Count from 1 to 20, one number per line").

Busy/idle ground truth came from the PITFALLS recipe: `capture-pane -p -S -60 | grep -c 'esc to interrupt'`.

## Observed

### Signal 1 — alternate screen: NEVER entered

`alternate_on` was `0` at every single sample, in every phase:

```
--- baseline (plain shell) ---
alternate_on=0 bell=0 activity=0
fresh_window: bell=0 alternate_on=0
T+8s: alternate_on=0 bell=0            <- trust dialog on screen
post_trust: alternate_on=0 bell=0      <- idle TUI, banner rendered
t=000.4s alt=0 bell=0 busy=0
t=000.8s alt=0 bell=0 busy=1           <- generating
t=002.4s alt=0 bell=0 busy=1
t=002.8s alt=0 bell=0 busy=0           <- turn complete
... (through t=036.0s, alt=0 throughout)
raw_win: alt=0 bell=0
alt=0 bell=0 title=[✳ Respond with pong message]   <- after 3 completed turns
```

Corroborated by raw bytes — the escape sequence is simply never written:

```
0   <- ESC[?1049 (alt screen enter/leave) count
0   <- ESC[?47 (legacy alt screen) count
```

The pane content confirms the TUI scrolls the *normal* buffer: the shell command line
`m5air@MacBook-Air q8-alt % claude --safe-mode` remained visible in scrollback above the
Claude banner for the whole session.

### Signal 2 — BEL on turn completion: NOT emitted

Positive control first, proving the detector works:

```
--- control: emit BEL from shell ---
after_shell_bel: bell=1 alternate_on=0
```

With the same `monitor-bell on` server, across three completed turns (each verified complete —
`⏺ pong` / `✻ Worked for 2s` in the pane, busy indicator gone), `window_bell_flag` never left `0`.

The raw log settles it. 15 `\a` bytes exist in 13763 bytes of output, and **every one is an OSC
string terminator**, not a bell:

```
CTX: m<ESC>[>0q<ESC>[c<ESC>[?2026$p<ESC>[c<ESC>]0;... Claude Code<BEL>
CTX: ai/code/session_01JkYNoJpkiHYF4Xkev3AP8B<BEL>
CTX: <ESC>[38;5;114m/rc<ESC>[39m<ESC>]8;;<BEL>
CTX: [?2026l<ESC>]0;... Respond with pong message<BEL>
CTX: [?1004l<ESC>[?2031l<ESC>[?2004l<ESC>[?25h<ESC>7<ESC>[r<ESC>8<ESC>]0;<BEL>
```

Complete inventory of OSC introducers in the log — only title (OSC 0) and hyperlink (OSC 8):

```
   7 ^[]0;
   8 ^[]8;
```

**Zero OSC 9. Zero OSC 777. Zero standalone BEL.** The BEL bytes are `ST` for `ESC]0;…` and
`ESC]8;;…`; the final `ESC]0;<BEL>` is the exit-time title clear.

### Capture-limitation checks (done, and they did not bite)

- `tmux show -gv allow-passthrough` → `off`. Passthrough being off would have hidden DCS-wrapped
  sequences from an *inner* tmux — irrelevant here, and moot because the raw `script` log sits
  *below* tmux and sees the unfiltered byte stream.
- `capture-pane -pe` cannot show OSC 9/777 at all: it replays stored cell attributes (SGR) and
  hyperlinks, not transient control strings. Its single `ESC ]` hit was an OSC 8 hyperlink. This is
  exactly why the `script` raw channel was added — **the raw log is the load-bearing evidence here,
  not the tmux capture.**

### Bonus finding — OSC 0 title is a real channel, but an unreliable state signal

The TUI *does* continuously rewrite the terminal title, and tmux surfaces it as `#{pane_title}`
with no scraping. Full ordered payloads from the raw log:

```
TITLE: [✳ Claude Code]
TITLE: [⠂ Claude Code]
TITLE: [⠐ Claude Code]
TITLE: [⠐ Respond with pong message]
TITLE: [⠂ Respond with pong message]
TITLE: [✳ Respond with pong message]
TITLE: []
```

The glyph prefix looked like a busy/idle bit — braille spinner frames while working, `✳` when
idle — and a 1 s-interval sample agreed:

```
T+1s title=[⠐ Respond with pong message] busy=1
T+2s title=[⠂ Respond with pong message] busy=1
T+3s title=[✳ Respond with pong message] busy=0
```

**It does not replicate.** A third turn sampled at 0.25 s showed the title frozen at `✳` for the
entire busy window:

```
  12 ✳ Respond with pong message|1     <- 12 samples x 0.25s = 3s BUSY, glyph still idle-shaped
  48 ✳ Respond with pong message|0
```

The title text also lags: it holds a stale conversation summary ("Respond with pong message")
into and through the next, unrelated turn. So the title is *present and free* but neither
promptly-updated nor monotonic with turn state.

### Config note

`claude config get preferredNotifChannel` produced **no output and did not terminate** (hung past
a 120 s timeout; killed). Current value therefore **not recorded** — no write was attempted.

## Verdict

| Signal | Verdict |
|---|---|
| Alternate screen used by the TUI | **ANSWERED-NO** — `alternate_on=0` in all phases; `ESC[?1049` never emitted |
| BEL on turn completion | **ANSWERED-NO** — bell flag never set (positive control passes); all 15 `\a` are OSC terminators |
| OSC 9 / OSC 777 notification | **ANSWERED-NO** — only OSC 0 and OSC 8 appear in the raw stream |
| OSC 0 title as a state signal | **PARTIAL** — channel exists and is free via `#{pane_title}`, but glyph-vs-busy correlation failed to replicate and the text lags a turn |

Remaining, not covered by this probe:

- macOS only. `ESC[?1049` absence is almost certainly platform-independent (it is a TUI
  authoring choice, not an OS behavior), but Linux/Windows re-runs are cheap and unverified.
- `preferredNotifChannel` may gate a notification path (e.g. `terminal_bell`) that is off by
  default in this environment. This probe measured the **default** behavior only. A dedicated
  probe would have to set it in a *project* settings file and re-measure — not attempted here.
- Only the plain generate→idle transition was exercised. Permission dialogs and long tool runs
  were not sampled for BEL.

## Design consequence

1. **Do not build an `alternate_on` detector.** The "is the agent in a full-screen TUI" heuristic
   used by some terminal-multiplexer tooling is dead for Claude Code — the flag is a constant `0`
   and carries no information. Any prototype that branches on it is branching on noise.
2. **Do not build a bell-based completion watcher.** `monitor-bell` + `window_bell_flag` (and the
   equivalent on other multiplexers) will never fire. Worse, it is a *silent* failure — the flag
   just stays `0`, so an unguarded implementation would report "still working" forever. The two
   "free cross-platform signals" this question hoped to unlock **do not exist by default**.
3. Consequently, the **busy-indicator scrape (`esc to interrupt` absent + N stable polls) remains
   the primary in-band detector** for prototype A, and the hooks/transcript channels (prototypes
   B and C) carry the burden of the out-of-band signal. Q8 removes a hoped-for cheap alternative;
   it does not add one.
4. **`#{pane_title}` is worth keeping as a cheap secondary — for identity, not for state.** The
   OSC 0 payload gives a per-pane conversation label with zero scraping, useful for *which agent is
   this pane* in a multi-pane supervisor. It must not be used as a busy/idle oracle: the replication
   failure above is exactly the kind of intermittently-correct signal that produces flaky
   supervisors. If it is used at all, it needs an independent oracle behind it.
5. Because the TUI stays on the **normal screen buffer**, `capture-pane -S -N` scrollback genuinely
   contains prior turns — history-based reads are viable and do not need alt-screen special-casing.
   That is a small positive for the scrape prototype.
