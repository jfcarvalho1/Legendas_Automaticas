#!/usr/bin/env bash
# Media Organizer — instalação automática para Ubuntu.
# Uso:  bash instalar.sh
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "== Media Organizer: instalação =="

# 1. Pacotes do sistema (só os que faltarem)
NEED=()
command -v ffprobe >/dev/null 2>&1 || NEED+=(ffmpeg)
python3 -c "import ensurepip" >/dev/null 2>&1 || NEED+=(python3-venv)
dpkg -s libxcb-cursor0 >/dev/null 2>&1 || NEED+=(libxcb-cursor0)
if [ ${#NEED[@]} -gt 0 ]; then
    echo "-> A instalar pacotes do sistema: ${NEED[*]}"
    echo "   (vai ser pedida a sua palavra-passe)"
    sudo apt-get update
    sudo apt-get install -y "${NEED[@]}"
fi

# 2. Ambiente Python próprio (não mexe no Python do sistema)
echo "-> A preparar o ambiente Python…"
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"
chmod +x "$DIR/media-organizer.sh"

# 3. Atalho no menu de aplicações e no ambiente de trabalho
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
DESKTOP_FILE="$APPS/media-organizer.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Media Organizer
Comment=Organizar filmes e música (compatível com Jellyfin)
Exec="$DIR/media-organizer.sh"
Icon=$DIR/assets/icon.svg
Terminal=false
Categories=AudioVideo;Utility;
StartupWMClass=media-organizer
EOF
chmod +x "$DESKTOP_FILE"

DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESK" ]; then
    cp "$DESKTOP_FILE" "$DESK/"
    chmod +x "$DESK/media-organizer.desktop"
    gio set "$DESK/media-organizer.desktop" metadata::trusted true 2>/dev/null || true
fi

echo
echo "== Instalação concluída =="
echo "Abra o 'Media Organizer' no menu de aplicações ou no ambiente de trabalho."
