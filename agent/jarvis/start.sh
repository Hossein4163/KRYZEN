#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1
if [ -f "$DIR/../runtime.env" ]; then set -a; . "$DIR/../runtime.env"; set +a; fi
export JARVIS_PORT=${JARVIS_PORT:-8770}

echo "Starting K.R.Y.Z.E.N..."
echo "Listening on: http://127.0.0.1:${JARVIS_PORT}"
exec /usr/bin/python3 "$DIR/server.py"
