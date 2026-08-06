# agent-state-driver — Windows container (WINDOWS containers, not Linux).
#
# Provides the Windows hosting layer proven in docs/.research/empirical/windows-leg.md:
# node + node-pty (ConPTY, with vendored conpty.dll/OpenConsole.exe) + @xterm/headless.
# There is no tmux on Windows; this is the substitute, and the detection channels
# (sidecar, hooks, transcript, screen) are unchanged.
#
# Contains NO credentials and NO claude CLI — see containers/README.md.
#
# Requires Docker Desktop switched to Windows containers. Build context is the REPO ROOT:
#   docker build -t asd-windows -f containers\windows\Dockerfile .
#
# Base: servercore, not nanoserver. nanoserver has no PowerShell and a reduced
# Win32 surface; ConPTY hosting via OpenConsole.exe is not something we verified
# there. servercore ltsc2022 under Hyper-V isolation runs on Windows 11 hosts.
FROM mcr.microsoft.com/windows/servercore:ltsc2022

SHELL ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';"]

# Node is installed from the official zip, not a package manager: the image must
# not depend on fnm/nvm, whose shims do not exist on a non-interactive PATH
# (PITFALLS, Windows hosting).
ARG NODE_VERSION=24.19.0
RUN curl.exe -fsSLo C:\node.zip https://nodejs.org/dist/v$env:NODE_VERSION/node-v$env:NODE_VERSION-win-x64.zip ; \
    tar.exe -xf C:\node.zip -C C:\ ; \
    Rename-Item C:\node-v$env:NODE_VERSION-win-x64 C:\nodejs ; \
    Remove-Item C:\node.zip

# The servercore base sets PATH in the registry, not as an image ENV, so
# `${PATH}` expands to EMPTY here and a naive prepend leaves PATH="C:\nodejs;" —
# after which the build fails with hcs::System::CreateProcess "The system cannot
# find the file specified" because even powershell.exe is no longer resolvable.
# OBSERVED, first build attempt. Spell the base PATH out.
ENV PATH="C:\\nodejs;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0;C:\\Windows\\System32\\OpenSSH;C:\\Users\\ContainerAdministrator\\AppData\\Roaming\\npm"
RUN node --version ; npm --version

# Escaped: `WORKDIR C:\host` loses the backslash to the Dockerfile parser and
# fails with "the working directory 'C:host' is invalid". OBSERVED.
WORKDIR C:\\host

# node-pty ships Windows prebuilds plus the vendored ConPTY runtime, so this
# needs no Visual Studio and no node-gyp toolchain in the image.
COPY containers/windows/package.json C:/host/package.json
RUN npm install --no-audit --no-fund

COPY containers/windows/conpty-host.js C:/host/conpty-host.js
COPY containers/windows/conpty-selftest.js C:/host/conpty-selftest.js
COPY containers/windows/entrypoint.ps1 C:/entrypoint.ps1

# A baked copy of the repo, so the container is self-describing without a mount.
COPY . C:/agent-state-driver

ENTRYPOINT ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\entrypoint.ps1"]
CMD ["check"]
