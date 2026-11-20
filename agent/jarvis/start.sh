#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1
if [ -f "$DIR/../runtime.env" ]; then set -a; . "$DIR/../runtime.env"; set +a; fi
export JARVIS_PORT=${JARVIS_PORT:-8780}

if ! command -v bwrap >/dev/null || ! command -v git >/dev/null; then
    echo "K.R.Y.Z.E.N requires Bubblewrap and Git." >&2
    exit 1
fi

/usr/bin/python3 -B "$DIR/bootstrap.py"
echo "Starting K.R.Y.Z.E.N..."
exec /usr/bin/python3 "$DIR/server.py"
