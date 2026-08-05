# Prior art: expect/pexpect lineage, Windows PTYs, and terminal-bench

Researched 2026-08-05. Question: how do mature "drive an interactive CLI
programmatically" systems solve "is the program ready for input?" without
screen heuristics — or do they all fall back to pattern+timeout?

## Verdict

- **Every PTY/automation layer we examined exposes only two primitives:
  a raw output byte stream, and child-process liveness/exit status.** None
  expose a native "idle"/"ready for input" signal. `pexpect`, ConPTY,
  winpty, and wezterm's `portable-pty` all sit at this same low altitude —
  confirmed by reading `portable-pty`'s trait definitions directly
  (`MasterPty`/`Child` expose `try_clone_reader`/`take_writer`/`try_wait`,
  nothing else).
- **pexpect's answer to readiness is pattern+timeout, full stop** — `expect()`
  blocks until a caller-supplied regex matches the stream or a `TIMEOUT`/`EOF`
  sentinel fires. There is no framework-level "prompt detected" signal; the
  caller must know the exact string/regex the target program will emit. This
  is the same class of heuristic our design is trying to avoid, just
  formalized as a library.
- **winpty is explicitly a polling screen-buffer differ**, not a stream reader
  — because pre-ConPTY Windows consoles are buffer/grid based, not
  stream-based, winpty starts a hidden `conhost` and polls its screen buffer
  for changes to synthesize an output stream. ConPTY (Windows 10 1809+)
  replaced this with a real bidirectional VT-sequence pipe pair, but even
  ConPTY is just I/O plumbing — it has no readiness concept either.
- **terminal-bench — the most relevant "does an agent harness solve this"
  precedent — does not solve interactive-TUI readiness detection at all.** It
  sidesteps the problem: every one of its 9+ agent adapters (Claude Code,
  Codex, Goose, aider, gemini-cli, etc.) invokes the agent's **non-interactive
  print/exec mode** (`claude -p ... --output-format stream-json`, `codex exec
  ...`) as a single blocking shell command, and detects "done" via a
  **shell-level sentinel** (`; tmux wait -S done` appended to the command,
  polled with `tmux wait done` under a `timeout` wrapper) — i.e., it detects
  "the shell command returned," not "the TUI is idle." This is strong
  evidence that even a well-funded, widely-adopted eval harness treats
  interactive-TUI-state detection as out of scope and avoids it by construction.
- **A real non-heuristic solution class exists — OSC 133 semantic prompt
  markers — but it is shell-cooperative and scoped to command boundaries, not
  full-screen-app internal busy/idle state.** Terminal emulators (wezterm,
  iTerm2, ghostty, VS Code's terminal) and testing tools (`microsoft/tui-test`)
  inject shell-rc hooks that emit `OSC 133;A/B/C/D;<exit-code>` around each
  prompt cycle. This gives an unambiguous "shell is at a fresh prompt" signal
  — but only because the *shell* cooperates by sourcing an injected script.
  It says nothing about what a full-screen TUI program (like Claude Code's
  own interface) is doing internally; the moment a program takes over the
  screen, OSC 133 boundary detection goes silent until the shell prompt
  returns. This is architecturally exactly our PITFALLS.md "❯ is not an idle
  signal" problem, generalized: OSC 133 fixes the shell-prompt case but is
  not a general-purpose full-screen-TUI-app readiness protocol.
- **Practical implication for our design:** there is no shortcut available
  from the PTY/automation layer alone. The field's mature answer is either
  (a) avoid interactive-TUI driving entirely by using the target's
  non-interactive/scriptable mode when one exists (terminal-bench's
  approach — directly validates our own hooks/transcript-JSONL prototype
  track over pure screen-scraping), or (b) pattern+timeout+stability-polling
  against the raw output stream (pexpect/expect's approach — validates the
  screen-scrape prototype track, with PITFALLS.md's N-stable-polls +
  busy-indicator-absent rule being the correct, standard mitigation, not a
  novel workaround).

## Mechanisms found

### expect (Tcl) / pexpect (Python) — the founding lineage

- Core primitive: `spawn()` a child under a pty, then `expect(pattern)` blocks
  reading the child's output until `pattern` (a regex, or a list of regexes)
  matches, or a special `TIMEOUT`/`EOF` pseudo-pattern fires.
  Source: pexpect docs, https://pexpect.readthedocs.io/en/stable/overview.html
  ("There are two special patterns to match the End Of File (EOF) or a
  Timeout condition (TIMEOUT). ... If nothing matches an expected pattern
  then expect() will eventually raise a TIMEOUT exception. The default time
  is 30 seconds").
- `EOF` and `TIMEOUT` are literally exception classes
  (`pexpect.exceptions.EOF`, `pexpect.exceptions.TIMEOUT`), raised from
  `pty_spawn.py`'s read loop when the child's fd closes or the read
  deadline elapses. Passing `timeout=None` blocks forever (source:
  overview.html, "Exceptions" section).
- **No readiness signal beyond the caller's own regex.** The library gives
  you nothing about "is the child waiting for input" — you must already know
  what string the child prints when it wants input (e.g. `"Password:"`,
  `"[#\$] "`) and write that regex yourself. This is screen/text pattern
  matching by design, not by omission.
- CR/LF matching gotcha explicitly documented: pexpect reads one character
  at a time from a pty, so `$` (end-of-line anchor) never matches; you must
  match the literal `\r\n` the tty driver inserts. This is a foundational
  gotcha our own tmux-polling prototype already rediscovered independently
  (PITFALLS.md's stripped-blank-rows problem is a sibling issue).
- **Pexpect on Windows is explicitly degraded**: `pexpect.spawn` and
  `pexpect.run()` require a real Unix pty and are *unavailable* on Windows.
  The docs steer Windows users to `pexpect.popen_spawn.PopenSpawn` (pipes,
  not a pty — many programs behave differently/non-interactively when they
  detect no real terminal) or to two unmaintained third-party shims,
  `winpexpect` and `wexpect`. Source: same overview.html, "Pexpect on
  Windows" section. This is a direct precedent for why our own design needs
  a distinct Windows story rather than a a thin pexpect-alike.

### winpty (rprichard/winpty) — pre-ConPTY Windows pty emulation

- Repo: https://github.com/rprichard/winpty (1,381 stars, MIT).
- Mechanism, from the README verbatim: "The software works by starting the
  `winpty-agent.exe` process with a new, hidden console window, which
  bridges between the console API and terminal input/output escape codes.
  **It polls the hidden console's screen buffer for changes and generates a
  corresponding stream of output.**" This is a screen-buffer differ baked
  into the pty emulation layer itself — because pre-Windows-10 consoles are
  a 2D character grid with no append-only output stream, there was no other
  way to synthesize one. It predates ConPTY (Microsoft's official native
  pseudo console, introduced Windows 10 1809 / 2018) and is now the fallback
  path.
- `pywinpty` (andfoy/pywinpty, 164 stars, MIT) wraps both winpty and native
  ConPTY behind one Python API (`winpty.PTY` / `winpty.PtyProcess`),
  auto-selecting ConPTY when available. Source: README,
  https://github.com/andfoy/pywinpty (fetched via `gh api contents`).
  It exposes only `write()`, `read()`/`readline()`, `isalive()`, `resize()`
  — the same read/write/liveness primitives as everything else here, no
  readiness signal.

### ConPTY — Microsoft's native Windows pseudo console (Win10 1809+)

- Docs: https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session
  (fetched directly). Mechanism: caller creates two anonymous pipes,
  calls `CreatePseudoConsole(size, inputReadSide, outputWriteSide, 0, &hPC)`
  to get an `HPCON`, attaches it to a child via
  `UpdateProcThreadAttribute(..., PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE, hPC, ...)`
  and `CreateProcess(..., EXTENDED_STARTUPINFO_PRESENT, ...)`. The
  pseudoconsole then translates between the child's Win32 console-API calls
  and a stream of VT (ANSI/xterm-style) escape sequences on the output pipe,
  and VT input sequences → `INPUT_RECORD`s on the input pipe.
- This is I/O plumbing only. ConPTY gives you the same thing a Unix pty
  gives you (a byte-stream VT channel in and out) — it does not expose an
  "idle"/"prompt ready" event of any kind. Any readiness detection built on
  top of ConPTY has to do exactly what a Unix-side caller does: read the VT
  stream and pattern-match/diff it.
- The docs explicitly warn each I/O direction must be serviced on its own
  thread to avoid deadlock when a buffer fills — an operational gotcha for
  anyone driving a pty layer synchronously (relevant if our design ever
  moves off tmux/expect-style blocking reads to raw ConPTY handles).

### portable-pty (wezterm's Rust pty crate) — cross-platform abstraction

- Repo: https://github.com/wez/wezterm, crate at `pty/src/`
  (`pty/src/lib.rs`, `pty/src/unix.rs`, `pty/src/win/conpty.rs`,
  `pty/src/win/psuedocon.rs`) — fetched via `gh api contents`.
- The public trait surface (`pty/src/lib.rs`, verified by grep of the
  fetched source) is exactly:
  - `MasterPty`: `resize()`, `get_size()`, `try_clone_reader() -> Read`,
    `take_writer() -> Write`, `process_group_leader()`, `as_raw_fd()`.
  - `Child`/`ChildKiller`: `try_wait() -> Option<ExitStatus>`, `wait()`,
    `process_id()`, `kill()`.
  - `PtySystem`: `openpty(size) -> PtyPair`.
- That's the entire cross-platform contract: a `Read`, a `Write`, and
  process exit-status polling. No busy/idle/ready abstraction exists at
  this layer on either the Unix or Windows (ConPTY) backend — confirming
  the same conclusion reached independently for pexpect, winpty, and raw
  ConPTY: **the PTY layer, on every platform, is deliberately silent about
  readiness; that's a problem every layer above it must solve for itself.**

### terminal-bench (harbor-framework/terminal-bench) — how the benchmark knows an agent finished

- Repo: https://github.com/harbor-framework/terminal-bench (2,530 stars,
  Apache-2.0) — read `terminal_bench/terminal/tmux_session.py` and
  `terminal_bench/agents/installed_agents/{abstract_installed_agent.py,
  claude_code/claude_code_agent.py, codex/codex_agent.py, goose/goose_agent.py}`
  directly via `gh api contents`.
- **Sentinel-on-shell mechanism** (`tmux_session.py`, class `TmuxSession`):
  a blocking command is sent as `<command>; tmux wait -S done` (the constant
  `_TMUX_COMPLETION_COMMAND = "; tmux wait -S done"`, appended by
  `_prepare_keys()`), then the harness runs
  `timeout {max_timeout_sec}s tmux wait done` inside the container and
  raises `TimeoutError` on non-zero exit. This detects "the shell command
  I appended a suffix to has returned control to the shell" — a **positive,
  unambiguous, non-heuristic signal**, but only because the harness controls
  and can rewrite the exact command line being run. `capture_pane()` /
  `get_incremental_output()` exist and are used for logging/context, but
  completion is never inferred from screen content — only from the
  `tmux wait` sentinel.
- **Every installed-agent adapter runs the target agent in its
  non-interactive/print/exec mode, as one single blocking command**,
  sidestepping "is the interactive TUI idle" entirely:
  - Claude Code (`claude_code_agent.py`): `claude --verbose
    --output-format stream-json -p <instruction> --allowedTools ...`,
    `block=True, max_timeout_sec=inf`. `-p` (print mode) means Claude Code
    never renders its interactive TUI in this harness at all — it runs
    once, streams structured JSON events, and exits, so "readiness" reduces
    to "process exit," already solved by the tmux sentinel.
  - Codex (`codex_agent.py`): `codex exec --sandbox danger-full-access
    --skip-git-repo-check --model <m> -- <instruction>`, same
    `block=True` pattern — `codex exec` is Codex's non-interactive mode.
  - Goose (`goose_agent.py`): writes a YAML "recipe" file, then runs
    `goose run --recipe ~/terminal-bench-recipe.yaml`, again blocking,
    again a single-shot non-interactive invocation.
  - This pattern (non-interactive invocation + shell-return sentinel) is
    uniform across all `installed_agents/*` adapters checked (Claude Code,
    Codex, Goose) — none of them attempt to detect mid-turn TUI state
    (working/idle/waiting-on-permission/waiting-on-input) because none of
    them run the TUI.
- **Direct implication:** terminal-bench is not prior art for *our* problem
  (driving the interactive TUI and classifying its live state) — it is
  prior art for *avoiding* our problem by using each agent's scriptable
  batch mode instead. That itself is a finding worth weighing against our
  own hooks/transcript-JSONL prototype track: where a target agent exposes
  a non-interactive/print mode with structured output (Claude Code's
  `-p --output-format stream-json`, hooks, transcript JSONL under
  `~/.claude/projects/`), that channel is strictly more reliable than
  screen-state inference and should be preferred; screen-scraping is the
  correct fallback only for targets that offer no such channel, or when the
  requirement is specifically to drive the *interactive* TUI (e.g. for
  fidelity to what a human operator sees, or because the interactive mode
  has features/permission-prompt flows the batch mode lacks).

### OSC 133 semantic shell-integration markers — the one real non-heuristic signal, and its limits

- Spec/adopters: Contour (https://contour-terminal.org/vt-extensions/osc-133-shell-integration/),
  vtdn (https://vtdn.dev/docs/osc/osc133/), wezterm
  (https://wezterm.org/shell-integration.html), ghostty, iTerm2, VS Code.
- Mechanism: the *shell* (not the pty layer) is made to emit
  `OSC 133;A ST` (prompt start), `OSC 133;B ST` (prompt end / input start),
  `OSC 133;C ST` (command output start), `OSC 133;D;<exit-code> ST`
  (command finished) around every prompt cycle, via injected rc-file hooks.
  `microsoft/tui-test`'s `shell-use` component (DeepWiki:
  https://deepwiki.com/microsoft/tui-test/4-shell-integration) is a concrete,
  actively maintained implementation: it materializes per-shell integration
  scripts (bash `--init-file`, zsh `ZDOTDIR` redirection, fish
  `--init-command`, PowerShell `-command` sourcing, nu/xonsh/elvish
  equivalents) into `~/.shell-use/shell/` and forces the shell to source
  them at launch, without touching the user's own rc files.
- This is a genuine, well-specified, non-heuristic "ready" signal — but
  strictly for **shell prompt boundaries**. It tells you "the shell just
  returned to its prompt with exit code N." It says nothing about a
  full-screen TUI program's internal state while that program owns the
  terminal (e.g., Claude Code's own busy spinner / `esc to interrupt`
  indicator, or a permission dialog). OSC 133 goes silent for the entire
  duration a full-screen app is running, and only resumes when control
  returns to the shell — which is exactly the boundary our own detection
  problem lives *inside of*, not at. This confirms PITFALLS.md's finding
  that a naive prompt-glyph (`❯`) is not an idle signal is not a shortcut
  we missed; it is the field's known, still-unsolved-in-general boundary.

## Sources

- pexpect API overview (readiness/EOF/TIMEOUT semantics, CR/LF matching,
  Windows limitations) — https://pexpect.readthedocs.io/en/stable/overview.html
- pexpect core API docs (EOF/TIMEOUT as sentinel patterns) —
  https://pexpect.readthedocs.io/en/stable/api/pexpect.html
- pexpect exceptions source —
  https://pexpect.readthedocs.io/en/stable/_modules/pexpect/exceptions.html
- winpty README (screen-buffer polling mechanism) —
  https://github.com/rprichard/winpty
- pywinpty README (ConPTY + winpty dual backend) —
  https://github.com/andfoy/pywinpty
- ConPTY: Creating a Pseudoconsole session (official API walkthrough) —
  https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session
- ConPTY announcement blog —
  https://devblogs.microsoft.com/commandline/windows-command-line-introducing-the-windows-pseudo-console-conpty/
- wezterm `portable-pty` crate source (`pty/src/lib.rs` trait definitions) —
  https://github.com/wez/wezterm/blob/main/pty/src/lib.rs
- terminal-bench repo —
  https://github.com/harbor-framework/terminal-bench
- terminal-bench tmux session + sentinel mechanism —
  `terminal_bench/terminal/tmux_session.py` in the above repo
  (`_TMUX_COMPLETION_COMMAND`, `_send_blocking_keys`)
- terminal-bench installed-agent adapters —
  `terminal_bench/agents/installed_agents/{abstract_installed_agent.py,
  claude_code/claude_code_agent.py, codex/codex_agent.py,
  goose/goose_agent.py}` in the above repo
- OSC 133 shell integration spec (Contour) —
  https://contour-terminal.org/vt-extensions/osc-133-shell-integration/
- OSC 133 spec (vtdn) — https://vtdn.dev/docs/osc/osc133/
- wezterm shell integration docs — https://wezterm.org/shell-integration.html
- microsoft/tui-test `shell-use` shell-integration architecture (DeepWiki) —
  https://deepwiki.com/microsoft/tui-test/4-shell-integration
