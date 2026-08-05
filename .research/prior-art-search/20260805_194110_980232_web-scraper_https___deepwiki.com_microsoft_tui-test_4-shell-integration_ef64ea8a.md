# Shell Integration | microsoft/tui-test | DeepWiki

*Date: 2026-07-07*

---
title: Shell Integration | microsoft/tui-test | DeepWiki
url: https://deepwiki.com/microsoft/tui-test/4-shell-integration
hostname: deepwiki.com
description: `shell-use` provides deep visibility into shell sessions by injecting integration scripts that enable semantic tracking. This allows the daemon to distinguish between the shell prompt, user input, and
sitename: DeepWiki
date: 2026-07-07
tags: ['microsoft/tui-test,microsoft,tui-test,documentation,wiki,codebase,AI documentation,Devin,Shell Integration']
---
Loading...
Loading...
Menu
shell-use provides deep visibility into shell sessions by injecting integration scripts that enable semantic tracking. This allows the daemon to distinguish between the shell prompt, user input, and command output using standard terminal escape sequences.
The integration primarily leverages two types of Operating System Command (OSC) sequences:
- OSC 133: Semantic prompt tracking (e.g., marking the start of a prompt, the start of output, and the exit code of the last command).
- OSC 7: Reporting the Current Working Directory (CWD) to the terminal emulator.
The following diagram illustrates how the shell-use CLI prepares the environment and launches a shell with these integrations active.
Shell Launch Sequence
Sources: src/main.rs91-104 src/shell/mod.rs137-226 src/shell/mod.rs65-114
When a session is opened, shell-use does not rely on pre-installed global scripts. Instead, it "materializes" bundled scripts from the binary into a local directory (~/.shell-use/shell/) using write_integration_scripts() src/shell/mod.rs65-114
The shell_launch() function determines the specific execution arguments and environment variables required to force the shell to load these scripts src/shell/mod.rs137-226
- ZDOTDIR Redirection: For Zsh, shell-usecreates a temporary directory and sets theZDOTDIRenvironment variable to point there, allowing it to override shell startup without touching the user's global config src/shell/mod.rs186-195
- Windows Discovery: On Windows, the system attempts to locate git-bashor appropriate.exewrappers to ensure a consistent environment src/shell/mod.rs144-156
- Init Files: Most shells are launched with flags like --init-file(Bash) or-rc(Elvish) to source the integration immediately src/shell/mod.rs152-154 src/shell/mod.rs209-215
For details, see Integration Architecture and Script Materialization.
Sources: src/shell/mod.rs65-114 src/shell/mod.rs137-226 src/shell/mod.rs116-128
shell-use supports a wide variety of shells, each with a custom integration script designed to hook into the prompt and command execution lifecycle.
| Shell | Mechanism | Primary File | 
|---|---|---|
| Bash | --init-file | shellIntegration.bash | 
| Zsh | ZDOTDIRredirection | shellIntegration-rc.zsh | 
| Fish | --init-command | shellIntegration.fish | 
| PowerShell | -commandsourcing | shellIntegration.ps1 | 
| Nushell | sourcecommand | shellIntegration.nu | 
| Xonsh | @eventshooks | shellIntegration.xsh | 
| Elvish | -rcflag | shellIntegration.elv | 
The scripts are responsible for emitting specific sequences that the alacritty_terminal based emulator interprets:
- OSC 133 ; A ST: Prompt start.
- OSC 133 ; B ST: Prompt end / Input start.
- OSC 133 ; C ST: Command start / Output start.
- OSC 133 ; D ; <ExitCode> ST: Command finished with exit code.
Example: Xonsh Event Integration The Xonsh integration uses Python-based event decorators to trigger these sequences.
Sources: shell/shellIntegration.xsh12-19 src/shell/mod.rs10-20
Most integrations also emit OSC 7;file://<hostname><path> to ensure the Get(Cwd) command returns the accurate current directory of the shell shell/shellIntegration.xsh9-10
For details, see Per-Shell Integration Scripts.
Sources: shell/shellIntegration.nu1-15 shell/shellIntegration.xsh1-26 src/shell/mod.rs10-20