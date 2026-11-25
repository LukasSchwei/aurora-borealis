#!/usr/bin/env bash
set -euo pipefail

# Aurora Borealis Linux All-in-One Installer
# Installs Python virtualenv + dependencies from pyproject.toml, system tools (7z/qpdf),
# CLI command (~/.local/bin/aurora-borealis), SVG/PNG icon, MIME types (.dnd5e/.dnd55e/.dndcomp),
# and desktop application menu shortcut.

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${INSTALLER_DIR}/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
INSTALL_DIR="${DATA_HOME}/aurora-borealis/app"
BIN_DIR="${HOME}/.local/bin"
IN_PLACE=0
INSTALL_SYSTEM_DEPS=1
INSTALL_DESKTOP=1
DESKTOP_ONLY=0
INSTALL_AURORA_LEGACY=0
INSTALL_5ETOOLS=0
ASSUME_YES=0

usage() {
    cat <<'EOF'
Usage: ./installer/install-linux.sh [OPTIONS]

Options:
  --prefix DIR             Target installation directory (default: ~/.local/share/aurora-borealis/app)
  --in-place               Create .venv directly in the repository folder instead of copying
  --no-system-deps         Skip apt/dnf/pacman/zypper system package installation
  --no-desktop             Skip .desktop, icon, and MIME association setup
  --desktop-only           Install only the .desktop entry, icon, and MIME types for the current folder
  --install-aurora-legacy  Download & install official Aurora Legacy content from GitHub
  --install-5etools        Download & convert 5e.tools D&D 5e/5.5e content from GitHub
  --gui                    Launch the graphical Linux Setup Wizard instead
  --yes, -y                Run package manager / installer non-interactively
  --help, -h               Show this help message
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
        --desktop-only)
            DESKTOP_ONLY=1
            shift
            ;;
        --install-aurora-legacy)
            INSTALL_AURORA_LEGACY=1
            shift
            ;;
        --install-5etools)
            INSTALL_5ETOOLS=1
            shift
            ;;
        --gui)
            exec bash "${REPO_DIR}/setup-wizard-linux.sh"
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

install_desktop_integration() {
    local app_dir="$1"
    local apps_dir="${DATA_HOME}/applications"
    local icon_scalable_dir="${DATA_HOME}/icons/hicolor/scalable/apps"
    local icon_256_dir="${DATA_HOME}/icons/hicolor/256x256/apps"
    local mime_dir="${DATA_HOME}/mime/packages"

    mkdir -p "${apps_dir}" "${icon_scalable_dir}" "${icon_256_dir}" "${mime_dir}"
    chmod +x "${app_dir}/aurora-borealis" 2>/dev/null || true

    cp "${app_dir}/aurora_borealis/assets/aurora-borealis.svg" "${icon_scalable_dir}/aurora-borealis.svg"
    if [ -f "${app_dir}/aurora_borealis/assets/aurora-borealis.png" ]; then
        cp "${app_dir}/aurora_borealis/assets/aurora-borealis.png" "${icon_256_dir}/aurora-borealis.png"
    fi

    cat > "${mime_dir}/aurora-borealis.xml" <<'EOF'
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

    cat > "${apps_dir}/aurora-borealis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Aurora Borealis
GenericName=D&D 5e / 5.5e Character Builder
Comment=Native D&D 5e / 5.5e Character & Companion Builder
Exec="${app_dir}/aurora-borealis" %f
Path=${app_dir}
TryExec=${app_dir}/aurora-borealis
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
        update-desktop-database "${apps_dir}" || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "${DATA_HOME}/icons/hicolor" 2>/dev/null || true
    fi

    echo "Installed desktop entry at ${apps_dir}/aurora-borealis.desktop"
}

if [ "${DESKTOP_ONLY}" -eq 1 ]; then
    install_desktop_integration "${REPO_DIR}"
    exit 0
fi

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
    if [ "$(id -u)" -ne 0 ]; then
        if [ ! -t 0 ] && command -v pkexec >/dev/null 2>&1; then
            sudo_cmd="pkexec"
        elif command -v sudo >/dev/null 2>&1; then
            sudo_cmd="sudo"
        fi
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
    TARGET_DIR="${REPO_DIR}"
    echo "[2/4] Installing in-place at ${TARGET_DIR}..."
else
    TARGET_DIR="${INSTALL_DIR}"
    echo "[2/4] Copying Aurora Borealis files to ${TARGET_DIR}..."
    mkdir -p "${TARGET_DIR}"
    for item in aurora_borealis installer aurora-borealis setup-wizard-linux.sh pyproject.toml README.md; do
        if [ -e "${REPO_DIR}/${item}" ]; then
            rm -rf "${TARGET_DIR}/${item}"
            cp -R "${REPO_DIR}/${item}" "${TARGET_DIR}/${item}"
        fi
    done
    find "${TARGET_DIR}/aurora_borealis" "${TARGET_DIR}/installer" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
fi

chmod +x "${TARGET_DIR}/aurora-borealis" "${TARGET_DIR}/setup-wizard-linux.sh" "${TARGET_DIR}/installer/install-linux.sh" "${TARGET_DIR}/installer/uninstall-linux.sh" 2>/dev/null || true

echo "[3/4] Creating Python virtual environment and installing dependencies..."
python3 -m venv "${TARGET_DIR}/.venv"
"${TARGET_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"${TARGET_DIR}/.venv/bin/python" -m pip install --no-build-isolation -e "${TARGET_DIR}"

USER_TPL_DIR="${DATA_HOME}/aurora-borealis/templates"
BUNDLED_TPL_DIR="${TARGET_DIR}/aurora_borealis/assets/templates"
if [ -d "${BUNDLED_TPL_DIR}" ]; then
    mkdir -p "${USER_TPL_DIR}"
    for pdf_tpl in "${BUNDLED_TPL_DIR}"/*.pdf; do
        [ -f "${pdf_tpl}" ] || continue
        tpl_name="$(basename "${pdf_tpl}")"
        if [ ! -f "${USER_TPL_DIR}/${tpl_name}" ]; then
            cp "${pdf_tpl}" "${USER_TPL_DIR}/${tpl_name}"
        fi
    done
fi

mkdir -p "${BIN_DIR}"
cat > "${BIN_DIR}/aurora-borealis" <<EOF
#!/usr/bin/env bash
exec "${TARGET_DIR}/aurora-borealis" "\$@"
EOF
chmod +x "${BIN_DIR}/aurora-borealis"

if [ "${INSTALL_DESKTOP}" -eq 1 ]; then
    echo "[4/4] Installing desktop entry, icon, and MIME file associations (.dnd5e, .dnd55e, .dndcomp)..."
    install_desktop_integration "${TARGET_DIR}"
else
    echo "[4/4] Skipping desktop integration (--no-desktop)."
fi

INSTALLED_PACKS=""
if [ "${INSTALL_AURORA_LEGACY}" -eq 1 ]; then
    echo "[Content] Downloading & installing official Aurora Legacy content from GitHub..."
    QT_QPA_PLATFORM=offscreen "${TARGET_DIR}/.venv/bin/python" -u -m aurora_borealis.main --sync-official
    INSTALLED_PACKS="${INSTALLED_PACKS}Aurora Legacy"
fi

if [ "${INSTALL_5ETOOLS}" -eq 1 ]; then
    echo "[Content] Downloading & converting 5e.tools D&D 5e/5.5e content from GitHub..."
    QT_QPA_PLATFORM=offscreen "${TARGET_DIR}/.venv/bin/python" -u -m aurora_borealis.main --sync-5etools
    if [ -n "${INSTALLED_PACKS}" ]; then
        INSTALLED_PACKS="${INSTALLED_PACKS}, 5e.tools"
    else
        INSTALLED_PACKS="5e.tools"
    fi
fi

cat <<EOF

Aurora Borealis installation complete!
  App directory : ${TARGET_DIR}
  CLI launcher  : ${BIN_DIR}/aurora-borealis
  Content packs : ${INSTALLED_PACKS:-On-demand in app}
  Run now       : aurora-borealis  (or "${TARGET_DIR}/aurora-borealis")
EOF
