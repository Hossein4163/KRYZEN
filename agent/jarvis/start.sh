#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1
export SUDO_PASS=33303330
export SUDO_PASSWORD=33303330
export JARVIS_PORT=${JARVIS_PORT:-8770}

echo "Starting Antigravity CLI Agent Studio (Jarvis Web App)..."
echo "Listening on: http://127.0.0.1:${JARVIS_PORT}"
exec /usr/bin/python3 "$DIR/server.py"
