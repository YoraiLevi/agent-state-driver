# DuckDuckGo search: ConPTY pseudo console readiness Windows terminal API

## 1. Creating a Pseudoconsole session - Windows Console | Microsoft Learn
<https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session>

September 20, 2022 - The hosting application could launch a window in another thread to collect user interaction input and serialize it into the write end of the input pipe for the pseudoconsole and the hosted character-mode application. Another thread could be launched to drain the read end of the output pipe for the pseudoconsole, decode the text and virtual terminal sequence information, and present that to the screen.

## 2. Windows Terminal sample code | Microsoft Learn
<https://learn.microsoft.com/en-us/windows/terminal/samples>

November 12, 2025 - GUIConsole.ConPTY: a .NET Standard 2.0 library that handles the creation of the console and enables pseudoconsole behavior. The Terminal.cs file contains the publicly visible pieces that the WPF application interacts with.

## 3. Windows Command-Line: Introducing the Windows Pseudo Console (ConPTY) - Windows Command Line
<https://devblogs.microsoft.com/commandline/windows-command-line-introducing-the-windows-pseudo-console-conpty/>

January 4, 2021 - I’ve read the article some more times and I think I got it. New Windows Terminal handles all input by itself, and then pass it to conhost via text encoding(conpty), and then conhost converts it to console api calls to far.

## 4. ConPTY and VT I/O | microsoft/terminal | DeepWiki
<https://deepwiki.com/microsoft/terminal/2.4-conpty-and-vt-io>

June 21, 2026 - This page describes how the pseudo-console (ConPTY) layer initializes its I/O pipes, reads VT sequences from a connected terminal, and converts those sequences into Win32 INPUT_RECORDs that console client applications can read.

## 5. Windows Console API Problem - Microsoft Q&A
<https://learn.microsoft.com/en-us/answers/questions/531961/windows-console-api-problem>

29 Aug 2021 ... See Windows Command-Line: Introducing the Windows Pseudo Console (ConPTY). It references microsoft/terminal: The new Windows Terminal and ...

## 6. Windows APIs - Lib.rs
<https://lib.rs/os/windows-apis>

... conpty #windows #pseudo-terminal · win_etw_provider. Enables apps to report ... v0.11.1 9.6K #terminal #console-input #console #input #windows · gpui ...

## 7. Windows Console and Terminal Ecosystem Roadmap
<https://learn.microsoft.com/en-us/windows/console/ecosystem-roadmap>

20 Sept 2022 ... The console host would then become a simple API call servicer and relay from device calls to the hosting application via the pseudoconsole. This ...

## 8. What is ConPTY in Windows Terminal? The Windows Pseudo-Console API Explained | terminal | Instagit
<https://instagit.com/microsoft/terminal/what-is-conpty-in-windows-terminal/>

ConPTY (Pseudo-Console) is a Windows 10/Server 2019 API that enables applications to create headless console sessions and communicate via anonymous pipes, allowing Windows Terminal to host traditional command-line tools in modern tabbed interfaces ...

## 9. r/programming on Reddit: Windows Command-Line: Introducing the Windows Pseudo Console (ConPTY)
<https://www.reddit.com/r/programming/comments/97lh1k/windows_commandline_introducing_the_windows/>

August 15, 2018 - Terminals will be able to interact with the conpty using only a stream of characters, while commandline applications will be able to keep using the entire console API surface as they always have.

## 10. ConPTY - Tag | Windows Command Line
<https://devblogs.microsoft.com/commandline/tag/conpty/>

As always, you can install Windows Terminal and Windows Terminal Preview from the Microsoft Store, from the GitHub releases page, or by using winget. H... ... In this, the fourth post in the Windows Command-Line series, we'll discuss the new Windows Pseudo Console (ConPTY) infrastructure and API - why we built it, what it's for, how it works, how to use it, and more.

## 11. How to use Windows ConPTY API from a process whose output has been redirected? · microsoft/terminal · Discussion #15814
<https://github.com/microsoft/terminal/discussions/15814>

It starts a PowerShell session (for test), and shows everything ConPTY sends from that session via the pseudoconsole, and everything works really well.

## 12. conpty package - github.com/ActiveState/termtest/conpty - Go Packages
<https://pkg.go.dev/github.com/ActiveState/termtest/conpty>

April 29, 2020 - Support for the Windows pseudo console in Go. Developed as part of the cross-platform terminal automation library expect for the ActiveState state tool.

## 13. Meet the Windows pseudo console (ConPTY) | Sudonull
<https://sudonull.com/post/12229-Meet-the-Windows-pseudo-console-ConPTY>

August 2, 2018 - Seamless PTY-like infrastructure for communicating with modern consoles and terminals · Modernize legacy / traditional command line applications · Receiving and converting UTF-8 text / VT to input records (as if entered by the user) Calls to the console API for a hosted application, updating its output buffer accordingly. Display of modified output buffer areas in UTF-8 encoding, text / VT Below is an example of how a modern console application communicates with a command line application via ConPTY ConHost.

## 14. Anyone familair with PseudoConsole API in Windows 10? | Notepad++ Community
<https://community.notepad-plus-plus.org/topic/24295/anyone-familair-with-pseudoconsole-api-in-windows-10>

April 6, 2023 - It is part of a series of blog posts about the Windows console in general, maybe the other parts could be helpful for you as well. This blog post explicitely states that the ConPTY or PseudoConsole feature works with UTF-8 character encoding. So, this seems to be the reason for your point 1. Another helpful resource could be Microsoft’s Terminal GitHub repo with example projects of how to use the new ConPTY feature.

## 15. r/Windows10 on Reddit: Windows Command-Line: Introducing the Windows Pseudo Console (ConPTY)
<https://www.reddit.com/r/Windows10/comments/97m1gm/windows_commandline_introducing_the_windows/>

August 15, 2018 - Basically it makes ConHost headless, unless a Console wants to hook up to it. It doesn't have to be connected to a traditional console window and provides a way to interact with the console over an API.

## 16. Windows ConPTY Implementation | phuslu/pty | DeepWiki
<https://deepwiki.com/phuslu/pty/2.2-windows-conpty-implementation>

April 30, 2026 - The Windows implementation of the ... systems that use /dev/ptmx, Windows utilizes a dedicated API to create a console hosting environment and wires it to a process using extended startup attributes....

## 17. GitHub - melwyncarlo/PyConPTY: A Python-based interface for the ConPTY (Windows Pseudo-console) API. · GitHub
<https://github.com/melwyncarlo/PyConPTY>

A Python-based interface for the ConPTY (Windows Pseudo-console) API. Check out the PyPI package · Your ultimate space to get immensely creative with unique terminals, remote accesses, and interactive and automated processes.

## 18. ConPtyShell/README.md at master · antonioCoco/ConPtyShell
<https://github.com/antonioCoco/ConPtyShell/blob/master/README.md>

NOTE2: If the ConPTY is not available on the target system you will get a normal netcat-like interactive shell. Client Side: Windows version >= 10 / 2019 1809 (build >= 10.0.17763) Server Side: any tcp listener, i.e. netcat · It's important to have the same rows and cols size between your terminal and the remote terminal if you want to have an aligned output on the shell.

## 19. The in and outs of Microsoft's new Windows Terminal • The Register
<https://www.theregister.com/2019/06/25/microsofts_new_terminal_put_through_paces/>

June 26, 2019 - Microsoft is embracing this, hence Program Manager Richard Turner's appeal in December 2018: "start writing (or update existing) Command-Line apps to emit VT enriched text, rather than calling Win32 Console APIs to control/format Console output." The VT approach now has superior features including 24-bit colour support and a proper concept of foreground and background. This is why the latest Insider Build of Windows 10 includes a "Terminal" tab in Command Prompt properties. In the new command line infrastructure, Microsoft puts ConHost's ConPTY between new console applications like Windows Terminal and the old Windows Console API, enabling both approaches to work.

## 20. ConPTY repeats character at top left of buffer during every operation...
<https://github.com/Microsoft/Terminal/issues/235>

When APIs are called that modify the Console display, the resulting changes are made to ConPTY's internal buffer, and changes are subsequently rendered to the connected Console/Terminal as text/VT. Unlike *NIX, Windows does not support *NIX signals...

## 21. Using tmux on Windows without WSL: Pane Splitting and AI Agent...
<https://zenn.dev/sora_biz/articles/psmux-windows-native-tmux?locale=en>

ConPTY (Console Pseudo Terminal) is a pseudo-terminal API introduced in Windows 10 and later. It provides a mechanism equivalent to Unix PTY, which made it possible to implement terminal multiplexers on Windows. psmux calls this API directly from Rust. Comparison with tmux.

## 22. Microsoft Answers Developer Calls for Linux-Like Pseudo Console in...
<https://visualstudiomagazine.com/articles/2018/08/21/pseudo-console.aspx>

His Windows Pseudo Console announcement recounted how terminal communications have evolved over the years.Turner indicated that the Windows Pseudo Console in Windows 10 will fix problems currently associated with connecting command-line applications in Windows.

## 23. The in and outs of Microsoft's new Windows Terminal
<https://www.theregister.com/software/2019/06/25/the-in-and-outs-of-microsofts-new-windows-terminal/653927>

Unix-like operating systems use a Pseudo Terminal (PTY) which sends and receives text.Windows has been moving towards the Unix/Linux model, introducing a Windows Pseudo Console called ConPTY which sends and receives text as an alternative to the old API.

## 24. Why Linux-first WSL Wins for Windows Developers | Windows Forum
<https://windowsforum.com/threads/why-linux-first-wsl-wins-for-windows-developers.377807/>

The Windows Console team eventually introduced the Windows Pseudo Console (ConPTY) API which enabled third‑party terminals and terminal‑oriented applications to interoperate with the Windows command-line ecosystem.

## 25. Terminal vs Shell vs Console: A Short Guide
<https://dsimunovic.hashnode.dev/terminal-vs-shell-vs-console-a-short-guide/rss.xml>

Pseudo Terminal(PTY). With the developments in general computing, a new problem was introduced: How can a terminal speak to another CLI application on the same machine? And, of course, you can’t use a cable between the two applications running on the same computer.

## 26. Next Windows 10 Release To Get Linux-Like Support for Console Apps
<https://redmondmag.com/articles/2018/08/16/windows-10-console-apps-support.aspx>

His Windows Pseudo Console announcement recounted how terminal communications have evolved over the years.Turner indicated that the Windows Pseudo Console in Windows 10 will fix problems currently associated with connecting command-line applications in Windows.

## 27. Biswa96/XConPty: Experiments with Pseudo Console in Windows 10
<https://github.gitop.top/Biswa96/XConPty>

XConPty. Proof-of-concept new Pseudo Console APIs' implementation in Windows 10 19H1 builds or greater. This repository uses many low level NTDLL APIs (without many error checking steps) and is dedicated to educational purposes.

## 28. Windows Console — Grokipedia
<https://grokipedia.com/page/Windows_Console>

Introducing the Windows Pseudo Console (ConPTY). Windows Terminal Build 2019 FAQ - Microsoft Developer Blogs.

## 29. What's the difference between a console, a terminal, and a shell?
<https://www.hanselman.com/blog/whats-the-difference-between-a-console-a-terminal-and-a-shell>

Pseudo Console, Pseudo Terminal, PTY, Pseudo TTY (ConPTY). Pseudo Terminals are terminal emulators or software interfaces that emulate terminals. They pretend to be terminals like the ones above.

## 30. c++ - How to use Windows ConPTY API from a process whose output has been redirected? - Stack Overflow
<https://stackoverflow.com/questions/69244994/how-to-use-windows-conpty-api-from-a-process-whose-output-has-been-redirected>
