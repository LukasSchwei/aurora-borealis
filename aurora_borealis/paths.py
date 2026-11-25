"""OS-standard data, config, Documents, and Downloads folder resolution."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .platform_utils import get_windows_documents_dir, get_windows_downloads_dir, is_windows


def _detect_os_known_dir(
    win_getter: Callable[[], Optional[Path]],
    xdg_name: str,
    xdg_env_key: str,
    qt_loc_name: str,
    fallback_names: tuple[str, ...],
) -> Path:
    """Detect an OS standard user directory (Documents / Downloads) without fabricating it."""
    home = Path.home()

    def _valid(cand: Optional[Path]) -> Optional[Path]:
        if cand is not None and cand.is_dir() and cand.resolve() != home.resolve():
            return cand
        return None

    if is_windows():
        hit = _valid(win_getter())
        if hit is not None:
            return hit

        try:
            from PySide6.QtCore import QStandardPaths

            loc_enum = getattr(QStandardPaths.StandardLocation, qt_loc_name)
            loc = QStandardPaths.writableLocation(loc_enum)
            if loc:
                hit = _valid(Path(loc))
                if hit is not None:
                    return hit
        except Exception:
            pass

        for folder_name in fallback_names:
            cand = home / folder_name
            if cand.is_dir():
                return cand
        return home

    # 1. xdg-user-dir <TYPE>
    try:
        proc = subprocess.run(
            ["xdg-user-dir", xdg_name],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            hit = _valid(Path(proc.stdout.strip()))
            if hit is not None:
                return hit
    except Exception:
        pass

    # 2. ~/.config/user-dirs.dirs
    user_dirs = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "user-dirs.dirs"
    if user_dirs.is_file():
        try:
            text = user_dirs.read_text(encoding="utf-8", errors="ignore")
            m = re.search(rf'^{xdg_env_key}="([^"]+)"', text, re.MULTILINE)
            if m:
                raw = m.group(1).replace("$HOME", str(home))
                hit = _valid(Path(os.path.expandvars(raw)).expanduser())
                if hit is not None:
                    return hit
        except Exception:
            pass

    # 3. Qt QStandardPaths
    try:
        from PySide6.QtCore import QStandardPaths

        loc_enum = getattr(QStandardPaths.StandardLocation, qt_loc_name)
        loc = QStandardPaths.writableLocation(loc_enum)
        if loc:
            hit = _valid(Path(loc))
            if hit is not None:
                return hit
    except Exception:
        pass

    # 4. Existing localized directories
    for folder_name in fallback_names:
        cand = home / folder_name
        if cand.is_dir():
            return cand

    # 5. Fallback to home directory
    return home


def get_os_documents_dir() -> Path:
    """Detect the OS standard Documents folder without creating ~/Documents blindly."""
    return _detect_os_known_dir(
        get_windows_documents_dir,
        xdg_name="DOCUMENTS",
        xdg_env_key="XDG_DOCUMENTS_DIR",
        qt_loc_name="DocumentsLocation",
        fallback_names=("Documents", "Dokumente"),
    )


def get_os_downloads_dir() -> Path:
    """Detect the OS standard Downloads folder without creating ~/Downloads blindly."""
    return _detect_os_known_dir(
        get_windows_downloads_dir,
        xdg_name="DOWNLOAD",
        xdg_env_key="XDG_DOWNLOAD_DIR",
        qt_loc_name="DownloadLocation",
        fallback_names=("Downloads",),
    )


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
