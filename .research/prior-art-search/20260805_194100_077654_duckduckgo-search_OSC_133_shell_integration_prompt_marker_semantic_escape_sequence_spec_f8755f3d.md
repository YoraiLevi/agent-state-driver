# DuckDuckGo search: OSC 133 shell integration prompt marker semantic escape sequence spec

## 1. OSC 133 | vtdn
<https://vtdn.dev/docs/osc/osc133/>

Feb 20, 2026 · Shell integration (FinalTerm semantic zones) Description Shell integration via OSC 133 allows the terminal to understand the structure of an interactive shell session. A typical command cycle looks like: A -- Shell prints the prompt (prompt text appears) B -- User has typed a command and pressed Enter C -- Command begins executing, output follows (command output appears) D;0 -- Command ...

## 2. OSC 133 - Shell Integration - Contour Terminal Emulator
<https://contour-terminal.org/vt-extensions/osc-133-shell-integration/>

Behavior: Marks the current line as a prompt line (conceptually similar to setting a "mark"). Notifies the terminal that the prompt is beginning. B - Prompt End Sent after the shell prompt has finished printing and before user input begins. Format: OSC 133 ; B ST Behavior: Notifies the terminal that the prompt has ended. C - Command Output Start

## 3. OSC 133 — Shell Integration (FTCS) | Otty
<https://docs.otty.sh/vt/osc/osc-133>

otty features try semantic-prompt — fires the full A → B → C → D;0 sequence so you can verify prompt-detection wiring (Open Quickly history, etc.). otty features try error-state — same flow with D;1 plus an OSC 9;4 error badge, to confirm Otty marks errored prompts.

## 4. Semantic prompts (OSC 133) — Terminal Support | Terminfo.dev
<https://terminfo.dev/extensions/osc-133-semantic-prompts>

Semantic prompts use OSC 133 markers to tell the terminal where each shell prompt, command input, and command output begins and ends. The markers are: A (prompt start), B (command input start — after prompt, before the user types), C (command output start — after Enter), and D (command finished, with exit code).

## 5. OSC 133 Prompt Marking | ghostty-org/ghostty | DeepWiki
<https://deepwiki.com/ghostty-org/ghostty/9.3-osc-133-prompt-marking>

Jul 11, 2026 · OSC 133 is a terminal control sequence protocol that enables semantic prompt marking in shell sessions. This protocol allows the terminal emulator to distinguish between prompts, user input, and command output by marking the boundaries of each phase in the command lifecycle.

## 6. Shell Integration | microsoft/tui-test | DeepWiki
<https://deepwiki.com/microsoft/tui-test/4-shell-integration>

Jul 7, 2026 · Shell Integration Relevant source files shell-use provides deep visibility into shell sessions by injecting integration scripts that enable semantic tracking. This allows the daemon to distinguish between the shell prompt, user input, and command output using standard terminal escape sequences. The integration primarily leverages two types of Operating System Command (OSC) sequences: OSC 133 ...

## 7. Shell Integration - Wez's Terminal Emulator - wezterm.org
<https://wezterm.org/shell-integration.html>

Shell Integration wezterm supports integrating with the shell through the following means: OSC 7 Escape sequences to advise the terminal of the working directory OSC 133 Escape sequence to define Input, Output and Prompt zones OSC 1337 Escape sequences to set user vars for tracking additional shell state OSC is escape sequence jargon for Operating System Command. These sequences enable some ...

## 8. Proprietary Escape Codes - Documentation - iTerm2 - macOS...
<https://iterm2.com/documentation-escape-codes.html>

iTerm2's Shell Integration feature is made possible by proprietary escape sequences pioneered by the FinalTerm emulator.The best remaining references to these codes are in iTerm2's source code. Ftcs_prompt. Osc 133 ; a st.

## 9. iTerm2 Shell Integration Protocol · GitHub
<https://gist.github.com/tep/e3f3d384de40dbda932577c7da576ec3/0412a93027386e4bbac4cf118758e28a0b00b944>

FinalTerm sequences (OSC 133), providing semantic markup of the prompt-command-output cycle. iTerm2 extension sequences (OSC 1337), providing environmental metadata such as hostname, working directory, user-defined variables, and version reporting.

## 10. semantic_prompt.rs - source
<https://docs.rs/reedline/latest/src/reedline/terminal_extensions/semantic_prompt.rs.html>

Semantic prompt support for OSC 133 and OSC 633 escape sequences. 2 //! 3 //! These escape sequences help terminals understand the structure of prompts, 4 //! user input, and command output.

## 11. Tmux Jump between Prompt Output with OSC 133 Shell Integration Standard ...
<https://tanutaran.medium.com/tmux-jump-between-prompt-output-with-osc-133-shell-integration-standard-84241b2defb5>

This apply for Tmux version 3.4 + Step 1 — The OSC 133 Standard for Prompt Jump The OSC is Operating System Command. We have many standard here like OSC7 etc. OSC 133 marks where the prompt start executed, end. Let's see what the standard says. I found the one on MS website explain it pretty good.

## 12. Shell Integration | TermPod
<https://termpod.dev/docs/desktop/shell-integration>

OSC 133 shell integration for command blocks — zsh, bash, and fish support.

## 13. Shell Integration | ghostty-org/ghostty | DeepWiki
<https://deepwiki.com/ghostty-org/ghostty/9-shell-integration>

The shell integration system enhances terminal functionality by automatically injecting hooks into supported shells. These hooks enable semantic prompt marking (OSC 133 sequences), working directory r.

## 14. Shell integration in the Windows Terminal | Microsoft Learn
<https://learn.microsoft.com/en-us/windows/terminal/tutorials/shell-integration>

Shell integration works by having the shell (or any command line application) write special "escape sequences" to the Terminal.The relevant supported shell integration sequences as of Terminal v1.18 are: OSC 133 ; A ST ("FTCS_PROMPT") - The start of a prompt.

## 15. iTerm2 Shell Integration Protocol · GitHub
<https://gist.github.com/tep/e3f3d384de40dbda932577c7da576ec3>

FinalTerm sequences (OSC 133), providing semantic markup of the prompt-command-output cycle. iTerm2 extension sequences (OSC 1337), providing environmental metadata such as hostname, working directory, user-defined variables, and version reporting.

## 16. Shell Integration - Ghostty
<https://mintlify.wiki/ghostty-org/ghostty/features/shell-integration>

SSH Integration. Prompt Markers (OSC 133). Environment Variables. Troubleshooting.Ghostty’s shell integration provides enhanced terminal features like semantic prompt detection, cursor shape control, and improved sudo/SSH workflows. Integration is automatic for supported shells.

## 17. Terminal Features: How Escape Sequences Work | Terminfo.dev
<https://terminfo.dev/features>

Semantic prompts (OSC 133).These sequences are used by virtually every TUI application: vim, tmux, less, htop, every readline-based shell prompt. They're so fundamental they're easy to take for granted.

## 18. Terminal Shell Integration
<https://code.visualstudio.com/docs/terminal/shell-integration>

Supported escape sequences. Common questions. Terminal Shell Integration.Here are the specific sequences that are supported: OSC 133 ; A ST: Mark prompt start.

## 19. OSC 133 (shell integration / semantic prompt) support #3064 - GitHub
<https://github.com/tmux/tmux/issues/3064>

10 Feb 2022 ... It would be good if tmux supported OSC 133, which is a control sequence that specifies where the prompt ended, and where the output of the ...

## 20. Add OSC 133 semantic prompt sequences for terminal integration
<https://github.com/anthropics/claude-code/issues/32635>

9 Mar 2026 ... Summary Claude Code should emit OSC 133 Semantic Prompt escape sequences to enable modern terminal features like click-to-move cursor, ...

## 21. Shell integration - kitty - Kovid's software projects
<https://sw.kovidgoyal.net/kitty/shell-integration/>

kitty has the ability to integrate closely within common shells, such as zsh, fish and bash to enable features such as jumping to previous prompts in the ...

## 22. Release notes — fish-shell 4.8.1 documentation
<https://fishshell.com/docs/current/relnotes.html>

OSC 133 prompt markers now also mark the prompt end ... fish now sends the commandline along with the OSC 133 semantic prompt command start sequence.

## 23. escape sequences - GitHub Gist
<https://gist.github.com/fdncred/c649b8ab3577a0e2873a8f229730e939>

First do a fresh-line. Then start a new command, and enter prompt mode: Subsequent text (until a OSC "133;B" or OSC "133; ...

## 24. Neovim help pages, always up-to-date
<https://neo.vimhelp.org/terminal.txt.html>

OSC 133: shell integration terminal-osc133 shell-prompt. Shells can emit semantic escape sequences (OSC 133) to mark where each prompt starts and ends.

## 25. Release notes for Ghostty 1.3.0, released on March 9, 2026.
<https://ghostty.org/docs/install/release-notes/1-3-0>

Ghostty now supports the click-events and cl=line extensions to the OSC 133 Semantic Prompts specification.For other shells, support varies based on Ghostty's injected shell integration. If you're using a supported shell, this will just magically work.

## 26. How vibeflow knows what your AI agent is doing — Brian Hengen
<https://brianhengen.us/posts/how-vibeflow-detects-ai-state/?trk=public_post_comment-text>

Enabling OSC 133 prompt markers in your shell (the standard shell-integration sequence, distinct from vibeflow’s own OSC 1338), or just running the next thing, clears it.

## 27. Option Reference - Configuration - Ghostty
<https://ghostty.org/docs/config/reference>

This feature requires shell integration, specifically prompt marking via OSC 133 . ... shell sends OSC 133 escape sequences to mark the start and end of commands.

## 28. Tachi/foot: A fast, lightweight and minimalistic Wayland terminal ...
<https://codeberg.org/Tachi/foot>

For this to work, the shell needs to emit an OSC-133;A ( \E]133;A\E\\ ) sequence before each prompt. In zsh, one way to do this is to add a precmd hook: precmd ...

## 29. Claude Code changelog - Claude Code Docs
<https://code.claude.com/docs/en/changelog>

Fixed a prompt-caching regression on Bedrock, Vertex, Mantle, and Foundry that billed the trailing system context block as fresh input tokens on every request.

## 30. fish-doc(1) - Arch manual pages
<https://man.archlinux.org/man/extra/fish/fish-doc.1.en>

... escape key from the start of an escape sequence. The default is ... OSC 133 prompt markers now also mark the prompt end, which improves shell integration ...
