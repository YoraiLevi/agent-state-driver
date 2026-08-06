#!/bin/bash
# Single entry point for the Linux container.
#
#   asd-check check   (default) run the credential-free portability check
#   asd-check test [pytest args...]  run the repo's pytest suite
#   asd-check shell            interactive bash
#   asd-check <cmd...>         run anything else verbatim
#
# Repo resolution: a bind mount on /work wins (edit on the host, run in here);
# otherwise the copy baked into the image at /opt/agent-state-driver is used.
set -euo pipefail

REPO=/opt/agent-state-driver
if [ -f /work/prototypes/mockagent/portability_check.py ]; then
    REPO=/work
fi

case "${1:-check}" in
    check)
        echo "repo:   $REPO"
        echo "python: $(python3 --version 2>&1)  ($(command -v python3))"
        echo "uv:     $(uv --version 2>&1)"
        echo "tmux:   $(tmux -V 2>&1)"
        echo
        # No credentials in this image, so this is the ONLY verification that can
        # run here: it drives the deterministic mock agent, not the real CLI.
        exec python3 "$REPO/prototypes/mockagent/portability_check.py"
        ;;
    test)
        shift
        # A read-only bind mount (the documented, safe default) cannot host
        # pytest's cache. Redirect it rather than emit a warning that looks like
        # a failure to a newcomer running this for the first time.
        export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
        cd "$REPO"
        exec python3 -m pytest "$@"
        ;;
    shell)
        exec /bin/bash
        ;;
    *)
        exec "$@"
        ;;
esac
