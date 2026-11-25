#!/usr/bin/env bash
set -euo pipefail

# Aurora Borealis Linux Setup Wizard Launcher (GUI Install / Uninstall)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
APP_VENV_PY="${DATA_HOME}/aurora-borealis/app/.venv/bin/python"
LOCAL_VENV_PY="${SCRIPT_DIR}/.venv/bin/python"

if [ -x "${LOCAL_VENV_PY}" ]; then
    exec "${LOCAL_VENV_PY}" -m installer.linux_wizard "$@"
elif [ -x "${APP_VENV_PY}" ]; then
    exec env PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" "${APP_VENV_PY}" "${SCRIPT_DIR}/installer/linux_wizard.py" "$@"
elif command -v python3 >/dev/null 2>&1; then
    exec env PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" python3 "${SCRIPT_DIR}/installer/linux_wizard.py" "$@"
elif command -v zenity >/dev/null 2>&1 && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    CHOICE=$(zenity --list --radiolist \
        --title="Aurora Borealis Setup Wizard" \
        --text="Python 3 is not installed yet. Choose an action:" \
        --column="Select" --column="Action" \
        TRUE "Install / Repair Aurora Borealis (installs Python + deps)" \
        FALSE "Uninstall Aurora Borealis" || true)
    case "${CHOICE}" in
        Install*)
            PACKS=$(zenity --list --checklist \
                --title="D&D Content Packs" \
                --text="Select content packs to install during setup:" \
                --column="Install" --column="Content Pack" \
                TRUE "Aurora Legacy (official PHB / SRD / Supplements)" \
                TRUE "5e.tools (D&D 5e / 5.5e data)" || true)
            EXTRA_FLAGS=()
            case "${PACKS}" in
                *Aurora*) EXTRA_FLAGS+=("--install-aurora-legacy") ;;
            esac
            case "${PACKS}" in
                *5e.tools*) EXTRA_FLAGS+=("--install-5etools") ;;
            esac
            exec bash "${SCRIPT_DIR}/install-linux.sh" -y "${EXTRA_FLAGS[@]}"
            ;;
        Uninstall*)
            exec bash "${SCRIPT_DIR}/uninstall-linux.sh"
            ;;
        *)
            exit 0
            ;;
    esac
else
    echo "=== Aurora Borealis Linux Setup ==="
    echo "1) Install / Repair Aurora Borealis"
    echo "2) Uninstall Aurora Borealis"
    printf "Choose [1/2]: "
    read -r ANS
    if [ "${ANS}" = "2" ]; then
        exec bash "${SCRIPT_DIR}/uninstall-linux.sh"
    else
        exec bash "${SCRIPT_DIR}/install-linux.sh"
    fi
fi
