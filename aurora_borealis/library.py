"""Folder-based character library scanner and file operations."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lxml import etree


@dataclass
class CharacterSummary:
    path: Path
    filename: str
    name: str
    race: str
    class_name: str
    background: str
    level: int
    favorite: bool
    modified_ts: float
    ruleset: str = "5e"
    portrait_path: str = ""
    portrait_base64: str = ""
    hp: int = 0
    ac: int = 10
    speed: int = 30
    entry_kind: str = "character"  # "character" or "companion"


def scan_characters_folder(
    folder: Path, favorites: Optional[set[str]] = None
) -> list[CharacterSummary]:
    """Scan folder for *.dnd5e, *.dnd55e, and *.dndcomp files and extract display summaries."""
    folder = Path(folder)
    if not folder.is_dir():
        return []

    favs = favorites or set()
    parser = etree.XMLParser(recover=True, remove_comments=True)
    summaries: list[CharacterSummary] = []

    files = sorted(
        [*folder.glob("*.dnd5e"), *folder.glob("*.dnd55e"), *folder.glob("*.dndcomp")],
        key=lambda p: p.name.lower(),
    )
    for dnd_path in files:
        try:
            stat = dnd_path.stat()
            tree = etree.parse(str(dnd_path), parser)
            root = tree.getroot()
        except Exception:
            continue
        if root is None:
            continue

        if dnd_path.suffix.lower() == ".dndcomp" or root.tag == "companion":
            disp = root.find("display-properties")
            name = (disp.findtext("name") if disp is not None else None) or dnd_path.stem
            ctype = (disp.findtext("type") if disp is not None else None) or "Companion"
            cr_type = (disp.findtext("creature-type") if disp is not None else None) or "Beast"
            owner = (disp.findtext("owner") if disp is not None else None) or ""
            lvl_s = (disp.findtext("level") if disp is not None else None) or "1"
            lvl = int(lvl_s) if lvl_s.isdigit() else 1
            hp_s = (disp.findtext("hp") if disp is not None else None) or "0"
            ac_s = (disp.findtext("ac") if disp is not None else None) or "10"
            p_path = (disp.findtext("portrait") if disp is not None else None) or ""
            p_b64 = (disp.findtext("portrait-data") if disp is not None else None) or ""
            is_fav = dnd_path.name in favs or str(dnd_path) in favs
            summaries.append(
                CharacterSummary(
                    path=dnd_path,
                    filename=dnd_path.name,
                    name=name.strip(),
                    race=cr_type.strip(),
                    class_name=f"{ctype.strip()}{f' ({owner.strip()})' if owner.strip() else ''}",
                    background="",
                    level=lvl,
                    favorite=is_fav,
                    modified_ts=stat.st_mtime,
                    ruleset="Companion",
                    portrait_path=p_path.strip(),
                    portrait_base64=p_b64.strip(),
                    hp=int(hp_s) if hp_s.isdigit() else 0,
                    ac=int(ac_s) if ac_s.isdigit() else 10,
                    speed=30,
                    entry_kind="companion",
                )
            )
            continue

        disp = root.find("display-properties")
        build = root.find("build")
        inp = build.find("input") if build is not None else None

        name = ""
        race = ""
        class_name = ""
        background = ""
        level = 1
        ruleset = "5.5e" if dnd_path.suffix.lower() == ".dnd55e" else "5e"
        portrait_path = ""
        portrait_base64 = ""
        hp = 0
        ac = 10
        speed = 30

        if disp is not None:
            name = (disp.findtext("name") or "").strip()
            race = (disp.findtext("race") or "").strip()
            class_name = (disp.findtext("class") or "").strip()
            background = (disp.findtext("background") or "").strip()
            lvl_txt = (disp.findtext("level") or "").strip()
            if lvl_txt.isdigit():
                level = max(1, min(20, int(lvl_txt)))
            rs = (disp.findtext("ruleset") or "").strip()
            if rs in ("5e", "5.5e"):
                ruleset = rs
            portrait_path = (disp.findtext("portrait") or "").strip()
            portrait_base64 = (disp.findtext("portrait-data") or "").strip()
            hp_txt = (disp.findtext("hp") or "").strip()
            ac_txt = (disp.findtext("ac") or "").strip()
            spd_txt = (disp.findtext("speed") or "").strip()
            if hp_txt.isdigit():
                hp = int(hp_txt)
            if ac_txt.isdigit():
                ac = int(ac_txt)
            if spd_txt.isdigit():
                speed = int(spd_txt)

        if inp is not None:
            if not name:
                name = (inp.findtext("name") or "").strip()
            if ruleset == "5e":
                rs_inp = (inp.findtext("ruleset") or "").strip()
                if rs_inp in ("5e", "5.5e"):
                    ruleset = rs_inp
            if not portrait_path:
                portrait_path = (inp.findtext("portrait") or "").strip()
            if not portrait_base64:
                portrait_base64 = (inp.findtext("portrait-data") or "").strip()
        if not name:
            name = dnd_path.stem

        is_fav = (
            dnd_path.name in favs
            or str(dnd_path) in favs
            or (disp is not None and (disp.get("favorite") or "").lower() == "true")
        )

        summaries.append(
            CharacterSummary(
                path=dnd_path,
                filename=dnd_path.name,
                name=name,
                race=race,
                class_name=class_name,
                background=background,
                level=level,
                favorite=is_fav,
                modified_ts=stat.st_mtime,
                ruleset=ruleset,
                portrait_path=portrait_path,
                portrait_base64=portrait_base64,
                hp=hp,
                ac=ac,
                speed=speed,
            )
        )

    summaries.sort(key=lambda s: (not s.favorite, -s.modified_ts, s.name.lower()))
    return summaries


def duplicate_character(src_path: Path) -> Path:
    src_path = Path(src_path)
    if not src_path.is_file():
        raise FileNotFoundError(f"Character file not found: {src_path}")

    stem = src_path.stem
    ext = src_path.suffix or ".dnd5e"
    candidate = src_path.with_name(f"{stem}_copy{ext}")
    counter = 2
    while candidate.exists():
        candidate = src_path.with_name(f"{stem}_copy_{counter}{ext}")
        counter += 1
    shutil.copy2(src_path, candidate)
    return candidate


def delete_character(path: Path) -> None:
    path = Path(path)
    if path.is_file():
        path.unlink()
