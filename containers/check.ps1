# One command to verify this repo in a container, from a Windows host.
#
#   containers\check.ps1              Windows container (docker, Windows-container mode)
#   containers\check.ps1 -Family linux  Linux container (podman)
#   containers\check.ps1 -NoBuild     run the existing image
#
# Exit 0 = all checks passed inside the container.
[CmdletBinding()]
param(
    [ValidateSet('windows', 'linux')][string]$Family = 'windows',
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if ($Family -eq 'linux') {
    $image = 'asd-linux'
    if (-not $NoBuild) {
        podman build -t $image -f (Join-Path $repo 'containers\linux\Containerfile') $repo
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    podman run --rm $image
    exit $LASTEXITCODE
}

# Windows containers only. Docker Desktop must be switched to Windows containers;
# in Linux-container mode the build fails on the servercore base image.
$osType = (docker info --format '{{.OSType}}')
if ($osType -ne 'windows') {
    Write-Error "Docker is in '$osType' container mode. Switch Docker Desktop to Windows containers (tray icon -> Switch to Windows containers)."
    exit 1
}

$image = 'asd-windows'
if (-not $NoBuild) {
    docker build -t $image -f (Join-Path $repo 'containers\windows\Dockerfile') $repo
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
docker run --rm $image
exit $LASTEXITCODE
