#!/usr/bin/env bash
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
INSTALL_DIR="${DATA_HOME}/aurora-borealis/app"
BIN_FILE="${HOME}/.local/bin/aurora-borealis"
APPS_DIR="${DATA_HOME}/applications"
DESKTOP_FILE="${APPS_DIR}/aurora-borealis.desktop"
ICON_FILE="${DATA_HOME}/icons/hicolor/scalable/apps/aurora-borealis.svg"
MIME_FILE="${DATA_HOME}/mime/packages/aurora-borealis.xml"

rm -f "${BIN_FILE}" "${DESKTOP_FILE}" "${ICON_FILE}" "${MIME_FILE}"
rm -rf "${INSTALL_DIR}"

if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database "${DATA_HOME}/mime" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPS_DIR}" 2>/dev/null || true
fi

echo "Aurora Borealis application files and desktop integration removed."
echo "Note: Your saved characters in ~/Documents (or custom library folder) were kept."
