"""Cross-platform OS helpers for Linux and Windows compatibility."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def is_windows() -> bool:
    """Return True when running on Windows."""
    return sys.platform == "win32"


def subprocess_no_window_kwargs() -> dict[str, int]:
    """Return subprocess keyword arguments suppressing console popups on Windows."""
    if is_windows() and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def find_executable(name: str) -> Optional[str]:
    """Locate an external CLI executable across PATH and common Windows install directories."""
    found = shutil.which(name)
    if found:
        return found

    if not is_windows():
        return None

    project_root = Path(__file__).resolve().parent.parent
    exe_name = name if name.lower().endswith(".exe") else f"{name}.exe"
    candidates: list[Path] = [project_root / "bin" / exe_name]

    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_app = os.environ.get("LOCALAPPDATA", "")

    low = name.lower().removesuffix(".exe")
    if low == "qpdf":
        patterns = [
            f"{pf}\\qpdf*\\bin\\qpdf.exe",
            f"{pf86}\\qpdf*\\bin\\qpdf.exe",
        ]
        if local_app:
            patterns.append(f"{local_app}\\Programs\\qpdf*\\bin\\qpdf.exe")
        for pat in patterns:
            for match in sorted(glob.glob(pat), reverse=True):
                candidates.append(Path(match))
    elif low == "7z":
        candidates.extend(
            [
                Path(pf) / "7-Zip" / "7z.exe",
                Path(pf86) / "7-Zip" / "7z.exe",
            ]
        )

    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


def get_windows_documents_dir() -> Optional[Path]:
    """Query Windows Known Folder FOLDERID_Documents via SHGetKnownFolderPath."""
    if not is_windows():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Documents: {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        docs_guid = _GUID(
            0xFDD39AD0,
            0x238F,
            0x46AF,
            (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        )
        ptr = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(docs_guid), 0, None, ctypes.byref(ptr))
        try:
            if hr == 0 and ptr.value:
                cand = Path(ptr.value)
                if cand.is_dir():
                    return cand
        finally:
            if ptr:
                ole32.CoTaskMemFree(ptr)
    except Exception:
        return None
    return None


def configure_windows_app_id(app_id: str = "AuroraBorealis.CharacterBuilder") -> None:
    """Set explicit AppUserModelID so Windows taskbar pins and groups the app icon properly."""
    if not is_windows():
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)  # type: ignore[attr-defined]
    except Exception:
        pass
