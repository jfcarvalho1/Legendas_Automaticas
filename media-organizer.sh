#!/usr/bin/env bash
# Arranque do Media Organizer (usado pelo atalho).
DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$DIR"
if [ ! -x "$DIR/.venv/bin/python" ]; then
    x-terminal-emulator -e bash "$DIR/instalar.sh" 2>/dev/null || bash "$DIR/instalar.sh"
fi
exec "$DIR/.venv/bin/python" "$DIR/app.py" "$@"
