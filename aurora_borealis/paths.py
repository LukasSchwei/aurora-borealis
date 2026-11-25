"""OS-standard data, config, and Documents folder resolution."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .platform_utils import get_windows_documents_dir, is_windows


def get_os_documents_dir() -> Path:
    """Detect the OS standard Documents folder without creating ~/Documents blindly."""
    home = Path.home()

    if is_windows():
        win_docs = get_windows_documents_dir()
        if win_docs is not None and win_docs.is_dir() and win_docs.resolve() != home.resolve():
            return win_docs

        try:
            from PySide6.QtCore import QStandardPaths

            loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            if loc:
                cand = Path(loc)
                if cand.is_dir() and cand.resolve() != home.resolve():
                    return cand
        except Exception:
            pass

        for folder_name in ("Documents", "Dokumente"):
            cand = home / folder_name
            if cand.is_dir():
                return cand
        return home

    # 1. xdg-user-dir DOCUMENTS
    try:
        proc = subprocess.run(
            ["xdg-user-dir", "DOCUMENTS"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0:
            cand = Path(proc.stdout.strip())
            if cand.is_dir() and cand.resolve() != home.resolve():
                return cand
    except Exception:
        pass

    # 2. ~/.config/user-dirs.dirs
    user_dirs = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "user-dirs.dirs"
    if user_dirs.is_file():
        try:
            text = user_dirs.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'^XDG_DOCUMENTS_DIR="([^"]+)"', text, re.MULTILINE)
            if m:
                raw = m.group(1).replace("$HOME", str(home))
                cand = Path(os.path.expandvars(raw)).expanduser()
                if cand.is_dir() and cand.resolve() != home.resolve():
                    return cand
        except Exception:
            pass

    # 3. Qt QStandardPaths DocumentsLocation
    try:
        from PySide6.QtCore import QStandardPaths

        loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        if loc:
            cand = Path(loc)
            if cand.is_dir() and cand.resolve() != home.resolve():
                return cand
    except Exception:
        pass

    # 4. Existing localized Documents directories
    for folder_name in ("Documents", "Dokumente"):
        cand = home / folder_name
        if cand.is_dir():
            return cand

    # 5. Fallback to home directory (do not fabricate ~/Documents)
    return home


def get_default_characters_dir() -> Path:
    return get_os_documents_dir() / "Aurora Borealis" / "Characters"


def get_app_data_dir() -> Path:
    override = os.environ.get("AURORA_BOREALIS_DATA_DIR")
    if override:
        return Path(override)
    if is_windows():
        local_app = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return local_app / "Aurora Borealis"
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return xdg_data / "aurora-borealis"


def get_elements_dir() -> Path:
    return get_app_data_dir() / "elements"


def get_custom_dir() -> Path:
    return get_app_data_dir() / "custom"


def get_templates_dir() -> Path:
    return get_app_data_dir() / "templates"


def get_config_path() -> Path:
    override = os.environ.get("AURORA_BOREALIS_CONFIG_PATH")
    if override:
        return Path(override)
    if is_windows():
        roaming_app = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return roaming_app / "Aurora Borealis" / "config.json"
    xdg_cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg_cfg / "aurora-borealis" / "config.json"
