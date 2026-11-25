#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
APPS_DIR="${DATA_HOME}/applications"
ICON_SCALABLE_DIR="${DATA_HOME}/icons/hicolor/scalable/apps"
ICON_256_DIR="${DATA_HOME}/icons/hicolor/256x256/apps"
MIME_DIR="${DATA_HOME}/mime/packages"

mkdir -p "${APPS_DIR}" "${ICON_SCALABLE_DIR}" "${ICON_256_DIR}" "${MIME_DIR}"

cp "${SCRIPT_DIR}/aurora_borealis/assets/aurora-borealis.svg" "${ICON_SCALABLE_DIR}/aurora-borealis.svg"
if [ -f "${SCRIPT_DIR}/aurora_borealis/assets/aurora-borealis.png" ]; then
    cp "${SCRIPT_DIR}/aurora_borealis/assets/aurora-borealis.png" "${ICON_256_DIR}/aurora-borealis.png"
fi

cat > "${MIME_DIR}/aurora-borealis.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-dnd5e">
    <comment>Aurora Borealis D&amp;D 5e Character</comment>
    <glob pattern="*.dnd5e"/>
  </mime-type>
  <mime-type type="application/x-dnd55e">
    <comment>Aurora Borealis D&amp;D 5.5e Character</comment>
    <glob pattern="*.dnd55e"/>
  </mime-type>
  <mime-type type="application/x-dndcomp">
    <comment>Aurora Borealis Companion Sheet</comment>
    <glob pattern="*.dndcomp"/>
  </mime-type>
</mime-info>
EOF

cat > "${APPS_DIR}/aurora-borealis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Aurora Borealis
GenericName=D&D 5e / 5.5e Character Builder
Comment=Native D&D 5e / 5.5e Character & Companion Builder
Exec="${SCRIPT_DIR}/aurora-borealis" --open %f
TryExec=${SCRIPT_DIR}/aurora-borealis
Icon=aurora-borealis
Terminal=false
Categories=Game;RolePlaying;
MimeType=application/x-dnd5e;application/x-dnd55e;application/x-dndcomp;
StartupWMClass=aurora-borealis
EOF

if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database "${DATA_HOME}/mime" || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPS_DIR}" || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${DATA_HOME}/icons/hicolor" 2>/dev/null || true
fi

echo "Installed desktop entry at ${APPS_DIR}/aurora-borealis.desktop"
