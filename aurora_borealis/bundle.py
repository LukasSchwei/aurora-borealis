"""Portable Character Bundle (.aurorapack) export and import."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lxml import etree

from .companions import CompanionState, save_dndcomp
from .loader import ContentRepository
from .models import CharacterState, ComputedCharacter
from .persistence import default_character_extension, serialize_character_xml

BUNDLE_EXTENSION = ".aurorapack"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_") or "bundle"


def _is_under_any(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for root in roots:
        try:
            r_res = root.resolve()
            if resolved == r_res or r_res in resolved.parents:
                return True
        except Exception:
            continue
    return False


def collect_custom_xml_files(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
    custom_dirs: list[Path],
) -> list[Path]:
    """Return unique custom XML file paths used by this character under custom_dirs."""
    ref_ids: set[str] = set()
    for eid in (state.race_id, state.class_id, state.background_id, state.alignment_id, state.deity_id):
        if eid:
            ref_ids.add(eid)
    for cl in state.normalized_classes():
        if cl.class_id:
            ref_ids.add(cl.class_id)
    for el in computed.granted_elements:
        if el.id:
            ref_ids.add(el.id)
    for sid in (*state.known_spells, *state.prepared_spells):
        if sid:
            ref_ids.add(sid)
    for item in state.inventory:
        if item.element_id:
            ref_ids.add(item.element_id)
    for vals in state.selections.values():
        for v in vals:
            if v:
                ref_ids.add(v)
    for fid in state.level_up_feats.values():
        if fid:
            ref_ids.add(fid)

    files: list[Path] = []
    seen: set[Path] = set()
    for eid in sorted(ref_ids):
        fpath = repo.source_files.get(eid)
        if fpath is None or not fpath.is_file():
            continue
        if custom_dirs and not _is_under_any(fpath, custom_dirs):
            continue
        resolved = fpath.resolve()
        if resolved not in seen:
            seen.add(resolved)
            files.append(fpath)
    return files


def export_character_bundle(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
    output_path: Path,
    custom_dirs: Optional[list[Path]] = None,
) -> dict:
    """Export character, attached companions, and referenced custom XML files into a .aurorapack ZIP."""
    output_path = Path(output_path)
    if not output_path.name.lower().endswith(BUNDLE_EXTENSION):
        output_path = output_path.with_suffix(BUNDLE_EXTENSION)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    slug = _slug(state.name)
    ext = default_character_extension(state.ruleset)
    char_arc = f"character/{slug}{ext}"
    char_bytes = serialize_character_xml(state, repo, computed)

    custom_xmls = collect_custom_xml_files(state, computed, repo, custom_dirs or [])
    companion_entries: list[tuple[str, bytes]] = []
    for idx, raw_comp in enumerate(state.companions, start=1):
        if not isinstance(raw_comp, dict):
            continue
        comp = CompanionState.from_dict(raw_comp)
        c_slug = _slug(comp.name) or f"companion_{idx}"
        c_arc = f"companions/{idx:02d}_{c_slug}.dndcomp"
        # Render via CompanionState XML builder
        tmp_root = etree.Element("companion", version="1.0")
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix="aurora_comp_bnd_") as td:
            tp = Path(td) / "c.dndcomp"
            save_dndcomp(comp, tp)
            companion_entries.append((c_arc, tp.read_bytes()))
        del tmp_root

    xml_arc_names: list[str] = []
    manifest = {
        "format": "aurora-borealis-bundle",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "character_name": state.name,
        "ruleset": state.ruleset,
        "level": state.level,
        "character_file": char_arc,
        "companions": [arc for arc, _ in companion_entries],
        "custom_xml": [],
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(char_arc, char_bytes)
        for c_arc, c_bytes in companion_entries:
            zf.writestr(c_arc, c_bytes)
        for idx, xml_path in enumerate(custom_xmls, start=1):
            arc = f"custom_xml/{idx:02d}_{xml_path.name}"
            zf.write(xml_path, arc)
            xml_arc_names.append(arc)
        manifest["custom_xml"] = xml_arc_names
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    return manifest


def _is_safe_zip_member(name: str) -> bool:
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        return False
    return True


def inspect_character_bundle(bundle_path: Path) -> dict:
    """Inspect a .aurorapack bundle and return its validated manifest."""
    bundle_path = Path(bundle_path)
    with zipfile.ZipFile(bundle_path, "r") as zf:
        for member in zf.namelist():
            if not _is_safe_zip_member(member):
                raise ValueError(f"Unsafe path in bundle: {member}")
        if "manifest.json" not in zf.namelist():
            raise ValueError("Invalid bundle: missing manifest.json")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        if not isinstance(manifest, dict) or not manifest.get("character_file"):
            raise ValueError("Invalid bundle manifest.")
        return manifest


def _unique_dest(directory: Path, filename: str) -> Path:
    dest = directory / filename
    if not dest.exists():
        return dest
    stem = Path(filename).stem
    ext = Path(filename).suffix
    counter = 2
    while True:
        cand = directory / f"{stem}_{counter}{ext}"
        if not cand.exists():
            return cand
        counter += 1


def import_character_bundle(
    bundle_path: Path,
    characters_dir: Path,
    custom_dir: Path,
) -> dict:
    """Import a .aurorapack bundle into characters_dir and custom_dir/bundled/<slug>/."""
    bundle_path = Path(bundle_path)
    characters_dir = Path(characters_dir)
    custom_dir = Path(custom_dir)
    characters_dir.mkdir(parents=True, exist_ok=True)
    custom_dir.mkdir(parents=True, exist_ok=True)

    manifest = inspect_character_bundle(bundle_path)
    char_arc = str(manifest["character_file"])
    bundle_slug = _slug(str(manifest.get("character_name") or bundle_path.stem))

    char_out: Optional[Path] = None
    companion_paths: list[Path] = []
    xml_paths: list[Path] = []

    with zipfile.ZipFile(bundle_path, "r") as zf:
        if char_arc not in zf.namelist():
            raise ValueError(f"Character file '{char_arc}' missing from bundle.")
        char_dest = _unique_dest(characters_dir, Path(char_arc).name)
        char_dest.write_bytes(zf.read(char_arc))
        char_out = char_dest

        for c_arc in manifest.get("companions", []):
            if c_arc in zf.namelist() and _is_safe_zip_member(c_arc):
                c_dest = _unique_dest(characters_dir, Path(c_arc).name)
                c_dest.write_bytes(zf.read(c_arc))
                companion_paths.append(c_dest)

        xml_list = [x for x in manifest.get("custom_xml", []) if x in zf.namelist() and _is_safe_zip_member(x)]
        if xml_list:
            xml_dir = custom_dir / "bundled" / bundle_slug
            xml_dir.mkdir(parents=True, exist_ok=True)
            for x_arc in xml_list:
                x_dest = xml_dir / Path(x_arc).name
                x_dest.write_bytes(zf.read(x_arc))
                xml_paths.append(x_dest)

    return {
        "character_path": char_out,
        "companion_paths": companion_paths,
        "xml_paths": xml_paths,
        "manifest": manifest,
    }
