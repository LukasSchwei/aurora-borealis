#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="${HOME}/.local/share/applications"
mkdir -p "${APPS_DIR}"

cat > "${APPS_DIR}/aurora-borealis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Aurora Borealis
Comment=Native Linux D&D 5e Character Builder
Exec="${SCRIPT_DIR}/aurora-borealis" %f
Terminal=false
Categories=Game;RolePlaying;
MimeType=application/x-dnd5e;
EOF

echo "Installed desktop entry at ${APPS_DIR}/aurora-borealis.desktop"
