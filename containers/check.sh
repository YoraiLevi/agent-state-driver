#!/usr/bin/env bash
# One command to verify this repo in a container. macOS or Linux host, podman.
#
#   containers/check.sh              build + run the credential-free check
#   containers/check.sh --no-build   run the existing image
#   containers/check.sh --mount      run against the WORKING TREE, not the baked copy
#
# Exit 0 = 16/16 checks passed inside the container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${ASD_IMAGE:-asd-linux}"
ENGINE="${ASD_ENGINE:-podman}"
build=1
mount=0
for a in "$@"; do
    case "$a" in
        --no-build) build=0 ;;
        --mount) mount=1 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

command -v "$ENGINE" >/dev/null || { echo "$ENGINE not found on PATH" >&2; exit 127; }

if [ "$build" = 1 ]; then
    "$ENGINE" build -t "$IMAGE" -f "$REPO_ROOT/containers/linux/Containerfile" "$REPO_ROOT"
fi

# ,Z relabels for SELinux hosts and is a no-op elsewhere; ro because nothing in
# the check writes to the repo (it works under $TMPDIR).
if [ "$mount" = 1 ]; then
    exec "$ENGINE" run --rm -v "$REPO_ROOT:/work:ro,Z" "$IMAGE"
else
    exec "$ENGINE" run --rm "$IMAGE"
fi
