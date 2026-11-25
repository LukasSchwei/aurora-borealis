#!/usr/bin/env bash
set -euo pipefail

# Aurora Borealis Linux All-in-One Installer
# Installs Python virtualenv + PySide6/lxml/pypdf, system tools (7z/qpdf),
# CLI command (~/.local/bin/aurora-borealis), SVG icon, MIME types (.dnd5e/.dnd55e/.dndcomp),
# and desktop application menu shortcut.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
INSTALL_DIR="${DATA_HOME}/aurora-borealis/app"
BIN_DIR="${HOME}/.local/bin"
IN_PLACE=0
INSTALL_SYSTEM_DEPS=1
INSTALL_DESKTOP=1
ASSUME_YES=0

usage() {
    cat <<'EOF'
Usage: ./install-linux.sh [OPTIONS]

Options:
  --prefix DIR        Target installation directory (default: ~/.local/share/aurora-borealis/app)
  --in-place          Create .venv directly in the repository folder instead of copying
  --no-system-deps    Skip apt/dnf/pacman/zypper system package installation
  --no-desktop        Skip .desktop, icon, and MIME association setup
  --yes, -y           Run package manager / installer non-interactively
  --help, -h          Show this help message
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --prefix)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --in-place)
            IN_PLACE=1
            shift
            ;;
        --no-system-deps)
            INSTALL_SYSTEM_DEPS=0
            shift
            ;;
        --no-desktop)
            INSTALL_DESKTOP=0
            shift
            ;;
        --yes|-y)
            ASSUME_YES=1
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

install_system_packages() {
    local need_py=0 need_7z=0 need_qpdf=0 need_venv=0
    command -v python3 >/dev/null 2>&1 || need_py=1
    command -v 7z >/dev/null 2>&1 || command -v 7za >/dev/null 2>&1 || command -v 7zz >/dev/null 2>&1 || need_7z=1
    command -v qpdf >/dev/null 2>&1 || need_qpdf=1
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv --help >/dev/null 2>&1 || need_venv=1
    else
        need_venv=1
    fi

    if [ "${need_py}" -eq 0 ] && [ "${need_7z}" -eq 0 ] && [ "${need_qpdf}" -eq 0 ] && [ "${need_venv}" -eq 0 ]; then
        echo "[1/4] System dependencies already satisfied (python3, venv, 7z, qpdf)."
        return 0
    fi

    echo "[1/4] Checking/installing system packages (python3, venv, 7z, qpdf, Qt xcb deps)..."
    local sudo_cmd=""
    if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        sudo_cmd="sudo"
    fi

    if command -v apt-get >/dev/null 2>&1; then
        local apt_yes=""
        [ "${ASSUME_YES}" -eq 1 ] && apt_yes="-y"
        ${sudo_cmd} apt-get update
        ${sudo_cmd} apt-get install ${apt_yes} python3 python3-venv python3-pip p7zip-full qpdf libxcb-cursor0 libegl1 libxkbcommon0 || \
            ${sudo_cmd} apt-get install ${apt_yes} python3 python3-venv python3-pip 7zip qpdf libxcb-cursor0 libegl1 libxkbcommon0
    elif command -v dnf >/dev/null 2>&1; then
        local dnf_yes=""
        [ "${ASSUME_YES}" -eq 1 ] && dnf_yes="-y"
        ${sudo_cmd} dnf install ${dnf_yes} python3 python3-pip p7zip p7zip-plugins qpdf xcb-util-cursor
    elif command -v pacman >/dev/null 2>&1; then
        local pac_yes=""
        [ "${ASSUME_YES}" -eq 1 ] && pac_yes="--noconfirm"
        ${sudo_cmd} pacman -S --needed ${pac_yes} python python-pip p7zip qpdf xcb-util-cursor || \
            ${sudo_cmd} pacman -S --needed ${pac_yes} python python-pip 7zip qpdf xcb-util-cursor
    elif command -v zypper >/dev/null 2>&1; then
        local zyp_yes=""
        [ "${ASSUME_YES}" -eq 1 ] && zyp_yes="-n"
        ${sudo_cmd} zypper install ${zyp_yes} python3 python3-pip p7zip qpdf libxcb-cursor0
    else
        echo "Warning: No supported package manager (apt/dnf/pacman/zypper) found. Ensure python3, python3-venv, 7z, and qpdf are installed." >&2
    fi
}

if [ "${INSTALL_SYSTEM_DEPS}" -eq 1 ]; then
    install_system_packages
else
    echo "[1/4] Skipping system package installation (--no-system-deps)."
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required but not found in PATH." >&2
    exit 1
fi

if [ "${IN_PLACE}" -eq 1 ]; then
    TARGET_DIR="${SCRIPT_DIR}"
    echo "[2/4] Installing in-place at ${TARGET_DIR}..."
else
    TARGET_DIR="${INSTALL_DIR}"
    echo "[2/4] Copying Aurora Borealis files to ${TARGET_DIR}..."
    mkdir -p "${TARGET_DIR}"
    for item in aurora_borealis aurora-borealis aurora-borealis.bat aurora-borealis.ps1 install-desktop.sh install-linux.sh uninstall-linux.sh pyproject.toml requirements.txt README.md; do
        if [ -e "${SCRIPT_DIR}/${item}" ]; then
            rm -rf "${TARGET_DIR}/${item}"
            cp -R "${SCRIPT_DIR}/${item}" "${TARGET_DIR}/${item}"
        fi
    done
    find "${TARGET_DIR}/aurora_borealis" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
fi

chmod +x "${TARGET_DIR}/aurora-borealis" "${TARGET_DIR}/install-desktop.sh" 2>/dev/null || true

echo "[3/4] Creating Python virtual environment and installing dependencies..."
python3 -m venv "${TARGET_DIR}/.venv"
"${TARGET_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"${TARGET_DIR}/.venv/bin/python" -m pip install -r "${TARGET_DIR}/requirements.txt"
"${TARGET_DIR}/.venv/bin/python" -m pip install --no-deps --no-build-isolation -e "${TARGET_DIR}"

mkdir -p "${BIN_DIR}"
cat > "${BIN_DIR}/aurora-borealis" <<EOF
#!/usr/bin/env bash
exec "${TARGET_DIR}/aurora-borealis" "\$@"
EOF
chmod +x "${BIN_DIR}/aurora-borealis"

if [ "${INSTALL_DESKTOP}" -eq 1 ]; then
    echo "[4/4] Installing desktop entry, icon, and MIME file associations (.dnd5e, .dnd55e, .dndcomp)..."
    bash "${TARGET_DIR}/install-desktop.sh"
else
    echo "[4/4] Skipping desktop integration (--no-desktop)."
fi

cat <<EOF

Aurora Borealis installation complete!
  App directory : ${TARGET_DIR}
  CLI launcher  : ${BIN_DIR}/aurora-borealis
  Run now       : aurora-borealis  (or "${TARGET_DIR}/aurora-borealis")
EOF
