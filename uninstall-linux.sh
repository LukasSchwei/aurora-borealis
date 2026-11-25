#!/usr/bin/env bash
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
INSTALL_DIR="${DATA_HOME}/aurora-borealis/app"
PURGE_CONFIG=0

usage() {
    cat <<'EOF'
Usage: ./uninstall-linux.sh [OPTIONS]

Options:
  --prefix DIR      Target installation directory to remove (default: ~/.local/share/aurora-borealis/app)
  --purge-config    Also remove Aurora Borealis config & cached XML/repositories (~/.config/aurora-borealis and ~/.local/share/aurora-borealis). Saved characters in Documents are always preserved.
  --help, -h        Show this help message
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --prefix)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --purge-config)
            PURGE_CONFIG=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

BIN_FILE="${HOME}/.local/bin/aurora-borealis"
APPS_DIR="${DATA_HOME}/applications"
DESKTOP_FILE="${APPS_DIR}/aurora-borealis.desktop"
ICON_FILE="${DATA_HOME}/icons/hicolor/scalable/apps/aurora-borealis.svg"
MIME_FILE="${DATA_HOME}/mime/packages/aurora-borealis.xml"

echo "[1/3] Removing launcher, desktop entry, icon, and MIME association..."
rm -f "${BIN_FILE}" "${DESKTOP_FILE}" "${ICON_FILE}" "${MIME_FILE}"

echo "[2/3] Removing application directory (${INSTALL_DIR})..."
if [ -n "${INSTALL_DIR}" ] && [ "${INSTALL_DIR}" != "/" ] && [ "${INSTALL_DIR}" != "${HOME}" ]; then
    rm -rf "${INSTALL_DIR}"
fi

if [ "${PURGE_CONFIG}" -eq 1 ]; then
    echo "Removing configuration & downloaded content caches..."
    rm -rf "${CONFIG_HOME}/aurora-borealis" "${DATA_HOME}/aurora-borealis"
fi

echo "[3/3] Refreshing desktop & MIME databases..."
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database "${DATA_HOME}/mime" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPS_DIR}" 2>/dev/null || true
fi

echo "Aurora Borealis application files and desktop integration removed."
echo "Note: Your saved characters in ~/Documents (or custom library folder) were kept."
