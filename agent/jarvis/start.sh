#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1
if [ -f "$DIR/../runtime.env" ]; then set -a; . "$DIR/../runtime.env"; set +a; fi
export JARVIS_PORT=${JARVIS_PORT:-8770}

# Probing headless browser automation engine (Obscura)
if command -v obscura >/dev/null 2>&1; then
    OBSCURA_VER=$(obscura -V 2>/dev/null || echo "detected")
    echo "Browser Engine: Obscura ($OBSCURA_VER) · 30MB V8 DOM · Stealth Active"
elif [ -x "/usr/local/bin/obscura" ]; then
    OBSCURA_VER=$(/usr/local/bin/obscura -V 2>/dev/null || echo "detected")
    echo "Browser Engine: Obscura ($OBSCURA_VER) at /usr/local/bin/obscura · 30MB V8 DOM"
else
    echo "Browser Engine: Agent-Browser fallback (Run 'docs/SETUP.md' to install ultralight Obscura)"
fi

echo "Starting K.R.Y.Z.E.N..."
echo "Listening on: http://127.0.0.1:${JARVIS_PORT}"
exec /usr/bin/python3 "$DIR/server.py"
