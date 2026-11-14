#!/bin/sh
# Launch only the adjacent trusted preparer; never source a PR checkout.
set -eu
exec python3 -B -E -s "$(dirname -- "$0")/prepare.py" "$@"
