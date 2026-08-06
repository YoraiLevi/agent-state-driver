# Containers

Two images, one per OS family, so this repo is adoptable without dependency archaeology.

| | `containers/linux/Containerfile` | `containers/windows/Dockerfile` |
|---|---|---|
| Base | `debian:bookworm-slim` | `mcr.microsoft.com/windows/servercore:ltsc2022` |
| Engine | **podman** (also works with docker) | **docker**, in **Windows-container** mode |
| Hosting layer | tmux | node-pty (ConPTY) + `@xterm/headless` |
| Runtime | uv-managed CPython 3.13 | node 24 LTS |
| What it verifies | `prototypes/mockagent/portability_check.py` — **16/16**, plus `pytest` — **23 passed** | `containers/windows/conpty-selftest.js` — **11/11** |
| Credentials | none, ever | none, ever |

Both images bake a copy of the repo (`/opt/agent-state-driver`, `C:\agent-state-driver`) so
`run` works with no mount; the Linux image prefers a read-only bind mount on `/work` when
one is present, so you can edit on the host and run in the container.

## One command

```bash
containers/check.sh                 # macOS / Linux host, podman        -> 16/16
containers/check.sh --mount         # run against the working tree instead of the baked copy
```

```powershell
containers\check.ps1                # Windows host, docker (Windows containers) -> 11/11
containers\check.ps1 -Family linux  # the Linux image, via podman, on the same box -> 16/16
```

Add `--no-build` / `-NoBuild` to skip the build. Exit 0 means every check passed.

The Linux image also carries the pytest suite (pytest is baked in, so the suite runs with
no network and no lockfile resolution):

```bash
podman run --rm asd-linux test          # -> 23 passed
podman run --rm asd-linux shell         # a shell with tmux, git, uv, python3
```

## What each is for

**Linux image — the portable verification environment.** It is what a newcomer runs to
confirm the shipped detector (`patterns.classify_screen`) behaves the same on their machine
as it did on ours. It drives `prototypes/mockagent/mock_claude.py`, a deterministic stand-in
that replays rendered shapes recorded from live 2.1.222 sessions, through the full state
machine: trust dialog, idle prompt, busy spinner, the past-tense completion form that must
*not* read as busy, the tool-run line, the permission dialog, and the whole sidecar
lifecycle. Sabotaging `patterns.py` fails it — that dependency is the point.

**Windows image — the hosting layer.** There is no tmux on Windows. The substitute, proven
in [windows-leg.md](../docs/.research/empirical/windows-leg.md), is a ~90-line node ConPTY
host; `containers/windows/conpty-host.js` is that host, and `conpty-selftest.js` asserts the
four capabilities it needs from the platform (spawn, byte flow, screen render, keystroke
injection, observed exit) work inside a container. The detection channels themselves —
sidecar, hooks, transcript, screen — are unchanged from macOS.

## What each cannot do

- **Neither image contains credentials, and neither contains the `claude` CLI.** That is
  deliberate: putting the owner's OAuth credentials into an image was rejected as a
  provisioning shortcut once already (see [PORTABILITY.md](../docs/results/PORTABILITY.md)).
  So **the real-CLI harness (`prototypes/harness/run.py`) does not run in either image
  as shipped** — the images run the credential-free checks only.
- **The Linux check is not a real-CLI check.** It proves parsing, fusion, timing and process
  handling are portable. It does not prove real-CLI behaviour on the target OS; that is
  covered separately by [docs/results/linux/](../docs/results/linux/) (WSL2, real CLI) and
  windows-leg.md (native Windows, real CLI).
- **The Windows check does not exercise `claude.exe`.** It exercises the host underneath it.
  See "Hosting the real CLI" below for what *was* observed.
- **The Windows image needs Windows-container mode.** In Linux-container mode the build
  fails on the base image. `check.ps1` checks `docker info --format {{.OSType}}` first and
  tells you instead of failing obscurely.
- **The Linux image is arm64/amd64 agnostic** (verified on both), but the Windows image is
  x64 only — the node zip URL is `win-x64`.

## Hosting the real CLI (Windows image, OBSERVED, not baked in)

The image ships no CLI, but it can host one. Installing the public npm package into a
throwaway container and spawning it under `conpty-host.js` painted the real first-run TUI:

```
 Let's get started.
 Choose the text style that looks best with your terminal
   1. Auto (match terminal)
 > 2. Dark mode √
   ...
```

That is the theme picker — the same first-run screen that broke the Linux leg until it was
handled. Onboarding stops there because there are no credentials, and
`~/.claude/sessions/` stays empty (no sidecar before the first session), which is exactly
the expected shape. To go further you would mount credentials at runtime
(`-v <hostdir>:C:\creds` plus `CLAUDE_CONFIG_DIR`) — **never** bake them into a layer.

```powershell
docker run --rm asd-windows powershell -NoProfile -Command `
  "npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code"
```

## Traps found while building these (all OBSERVED)

- **`ENV PATH="C:\nodejs;${PATH}"` destroys PATH in a Windows container.** The servercore
  base sets PATH in the registry, not as an image `ENV`, so `${PATH}` expands to *empty*.
  The next `RUN` dies with `hcs::System::CreateProcess … The system cannot find the file
  specified (0x2)` — because `powershell.exe` itself is no longer resolvable. Spell the base
  PATH out in full.
- **`WORKDIR C:\host` loses its backslash** to the Dockerfile parser:
  `the working directory 'C:host' is invalid`. Write `WORKDIR C:\\host`.
- **npm 11 blocks lifecycle scripts by default.** A global install of a package with a
  postinstall prints `npm warn allow-scripts` and the package is *not* usable; the failure
  is a `MODULE_NOT_FOUND` later, far from the cause. Pass
  `--allow-scripts=<pkg>`. (`node-pty` itself is unaffected — it ships Windows prebuilds
  plus the vendored `conpty.dll` / `OpenConsole.exe`, so the image needs no Visual Studio
  and no node-gyp.)
- **`ptyProcess.kill()` in a container can raise `Error: AttachConsole failed`** from
  node-pty's `conpty_console_list_agent`. Ending the child cleanly (write `exit\r`, or the
  agent's own `/exit`) avoids it; a driver that relies on `kill()` should expect this on
  Windows and treat process liveness, not the kill call, as the source of truth.
- **`uv pip install --system` refuses a uv-managed interpreter** — `hint: Virtual
  environments were not considered due to the --system flag`, exit 2. Install into a venv
  (`uv venv /opt/venv`) and put it on PATH.
- **uv's `--default` flag is still experimental**; pass
  `--preview-features python-install-default` or every build logs a warning.

## Verified on

| Image | Host | Engine | Result |
|---|---|---|---|
| linux | macOS 25.5.0, arm64 | podman 6.0.2 | 16/16 (baked copy and `--mount`) |
| linux | Windows 11 26200, x86_64 | podman 6.0.2 machine | 16/16 |
| windows | Windows 11 26200, Hyper-V isolation | docker 29.6.2 | 11/11 |
