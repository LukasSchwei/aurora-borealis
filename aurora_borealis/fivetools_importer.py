"""Import D&D 5e / 5.5e data from 5e.tools JSON files into Aurora XML format."""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from lxml import etree

from .github_importer import IndexRecord, fetch_url_bytes

DEFAULT_5ETOOLS_RAW_BASE = (
    "https://raw.githubusercontent.com/5etools-mirror-3/5etools-src/main/data/"
)

# Official WotC 5e & 5.5e source abbreviations (excludes homebrew, UA, Plane Shift, 3rd-party)
OFFICIAL_5ETOOLS_SOURCES: set[str] = {
    "PHB",
    "XPHB",
    "DMG",
    "XDMG",
    "MM",
    "XMM",
    "XGE",
    "TCE",
    "VGM",
    "MTF",
    "MPMM",
    "SCAG",
    "ERLW",
    "GGR",
    "MOT",
    "VRGR",
    "FTD",
    "SCC",
    "AAG",
    "BAM",
    "BGG",
    "BMT",
    "EGW",
    "AI",
    "IDROTF",
    "COS",
    "TOA",
    "SKT",
    "OOTA",
    "POTA",
    "WBTW",
    "SATO",
    "DSOTDQ",
    "PABTSO",
    "VEOR",
    "QFTIS",
    "EEPC",
    "SRD",
    "BASICRULES",
}


def is_official_5etools_source(source: str, entry: Optional[dict] = None) -> bool:
    """Return True only for official non-homebrew WotC 5e/5.5e entries."""
    if entry:
        if entry.get("_isHomebrew") or entry.get("isHomebrew") or entry.get("homebrew"):
            return False
    src_up = (source or "").strip().upper()
    if not src_up or src_up.startswith("UA") or src_up.startswith("PS"):
        return False
    return src_up in OFFICIAL_5ETOOLS_SOURCES

_TAG_RE = re.compile(r"\{@([a-zA-Z0-9_]+)\s+([^}]+)\}")

_SIZE_MAP = {
    "T": "ID_SIZE_TINY",
    "S": "ID_SIZE_SMALL",
    "M": "ID_SIZE_MEDIUM",
    "L": "ID_SIZE_LARGE",
    "H": "ID_SIZE_HUGE",
    "G": "ID_SIZE_GARGANTUAN",
}

_ABILITY_FULL = {
    "str": "strength",
    "dex": "dexterity",
    "con": "constitution",
    "int": "intelligence",
    "wis": "wisdom",
    "cha": "charisma",
}

_SPELL_SCHOOL_MAP = {
    "A": "Abjuration",
    "C": "Conjuration",
    "D": "Divination",
    "E": "Enchantment",
    "V": "Evocation",
    "I": "Illusion",
    "N": "Necromancy",
    "T": "Transmutation",
}


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_") or "ITEM"


def render_5etools_text(text: str) -> str:
    """Convert 5e.tools inline {@tag ...} syntax to clean plain/HTML text."""

    def _repl(match: re.Match[str]) -> str:
        tag = match.group(1).lower()
        body = match.group(2)
        parts = body.split("|")
        display = parts[0].strip()
        if tag in ("bold", "b"):
            return f"<b>{html.escape(display)}</b>"
        if tag in ("italic", "i"):
            return f"<i>{html.escape(display)}</i>"
        if tag == "dc":
            return f"DC {html.escape(display)}"
        if tag == "hit":
            return f"+{html.escape(display)}" if not display.startswith(("+", "-")) else html.escape(display)
        if tag in ("h",):
            return ""
        if tag in ("atk",):
            return "Attack:"
        if tag == "recharge":
            return f"(Recharge {html.escape(display)})" if display else "(Recharge 6)"
        return html.escape(display)

    escaped = html.escape(text)
    # Restore {@...} markers that only contain text before running _TAG_RE
    return _TAG_RE.sub(_repl, text)


def render_5etools_entries(entries: Any) -> str:
    """Recursively render 5e.tools entries blocks to Aurora description HTML."""
    if not entries:
        return ""
    if isinstance(entries, str):
        return f"<p>{render_5etools_text(entries)}</p>"
    if not isinstance(entries, list):
        return ""

    out: list[str] = []
    for item in entries:
        if isinstance(item, str):
            out.append(f"<p>{render_5etools_text(item)}</p>")
        elif isinstance(item, dict):
            etype = item.get("type", "")
            name = item.get("name", "")
            if etype == "list":
                out.append("<ul>")
                for li in item.get("items", []):
                    if isinstance(li, str):
                        out.append(f"<li>{render_5etools_text(li)}</li>")
                    elif isinstance(li, dict):
                        liname = li.get("name", "")
                        lientry = li.get("entry") or render_5etools_entries(li.get("entries", []))
                        prefix = f"<b>{html.escape(liname)}:</b> " if liname else ""
                        if isinstance(lientry, str) and not lientry.startswith("<"):
                            lientry = render_5etools_text(lientry)
                        out.append(f"<li>{prefix}{lientry}</li>")
                out.append("</ul>")
            elif etype in ("entries", "section", "inset"):
                if name:
                    out.append(f"<h4>{html.escape(str(name))}</h4>")
                out.append(render_5etools_entries(item.get("entries", [])))
            elif etype == "table":
                if item.get("caption"):
                    out.append(f"<p><b>{html.escape(str(item['caption']))}</b></p>")
            elif "entries" in item:
                if name:
                    out.append(f"<h4>{html.escape(str(name))}</h4>")
                out.append(render_5etools_entries(item.get("entries", [])))
    return "".join(out)


def _new_element(name: str, etype: str, source: str, eid: str) -> etree._Element:
    el = etree.Element("element", name=name, type=etype, source=source, id=eid)
    return el


def _set_description(el: etree._Element, desc_html: str) -> None:
    desc = etree.SubElement(el, "description")
    if desc_html:
        try:
            wrapped = etree.fromstring(f"<description>{desc_html}</description>")
            for child in wrapped:
                desc.append(child)
            if wrapped.text:
                desc.text = wrapped.text
            return
        except etree.XMLSyntaxError:
            pass
        p = etree.SubElement(desc, "p")
        p.text = re.sub(r"<[^>]+>", "", desc_html)
    else:
        etree.SubElement(desc, "p")


def _convert_races(data: dict) -> list[etree._Element]:
    out: list[etree._Element] = []
    for r in data.get("race", []):
        name = (r.get("name") or "").strip()
        src = (r.get("source") or "").strip()
        if not name or not is_official_5etools_source(src, r):
            continue
        eid = f"ID_5ETOOLS_RACE_{_slug(src)}_{_slug(name)}"
        el = _new_element(name, "Race", f"5e.tools ({src})", eid)
        _set_description(el, render_5etools_entries(r.get("entries", [])))
        rules = etree.SubElement(el, "rules")

        # Speed
        spd = r.get("speed")
        walk = spd.get("walk") if isinstance(spd, dict) else (spd if isinstance(spd, int) else 30)
        if isinstance(walk, int) and walk > 0:
            etree.SubElement(rules, "stat", name="innate speed", value=str(walk), bonus="base")

        # Size
        sizes = r.get("size") or ["M"]
        size_id = _SIZE_MAP.get(str(sizes[0]).upper(), "ID_SIZE_MEDIUM")
        etree.SubElement(rules, "grant", type="Size", id=size_id)

        # Ability bonuses (2014 style)
        for ab_obj in r.get("ability", []):
            if not isinstance(ab_obj, dict):
                continue
            for short_ab, full_ab in _ABILITY_FULL.items():
                val = ab_obj.get(short_ab)
                if isinstance(val, int) and val != 0:
                    etree.SubElement(rules, "stat", name=full_ab, value=str(val))
        out.append(el)
    return out


def _convert_backgrounds(data: dict) -> list[etree._Element]:
    out: list[etree._Element] = []
    for bg in data.get("background", []):
        name = (bg.get("name") or "").strip()
        src = (bg.get("source") or "").strip()
        if not name or not is_official_5etools_source(src, bg):
            continue
        eid = f"ID_5ETOOLS_BG_{_slug(src)}_{_slug(name)}"
        el = _new_element(name, "Background", f"5e.tools ({src})", eid)
        _set_description(el, render_5etools_entries(bg.get("entries", [])))
        rules = etree.SubElement(el, "rules")
        for sk_obj in bg.get("skillProficiencies", []):
            if isinstance(sk_obj, dict):
                for sk_name, enabled in sk_obj.items():
                    if enabled is True and sk_name not in ("choose", "any"):
                        etree.SubElement(
                            rules,
                            "grant",
                            type="Proficiency",
                            id=f"ID_PROFICIENCY_SKILL_{_slug(sk_name)}",
                        )
        out.append(el)
    return out


def _convert_feats(data: dict) -> list[etree._Element]:
    out: list[etree._Element] = []
    for ft in data.get("feat", []):
        name = (ft.get("name") or "").strip()
        src = (ft.get("source") or "").strip()
        if not name or not is_official_5etools_source(src, ft):
            continue
        eid = f"ID_5ETOOLS_FEAT_{_slug(src)}_{_slug(name)}"
        el = _new_element(name, "Feat", f"5e.tools ({src})", eid)
        _set_description(el, render_5etools_entries(ft.get("entries", [])))
        rules = etree.SubElement(el, "rules")
        for ab_obj in ft.get("ability", []):
            if isinstance(ab_obj, dict):
                for short_ab, full_ab in _ABILITY_FULL.items():
                    val = ab_obj.get(short_ab)
                    if isinstance(val, int) and val != 0:
                        etree.SubElement(rules, "stat", name=full_ab, value=str(val))
        out.append(el)
    return out


def _convert_spells(data: dict) -> list[etree._Element]:
    out: list[etree._Element] = []
    for sp in data.get("spell", []):
        name = (sp.get("name") or "").strip()
        src = (sp.get("source") or "").strip()
        if not name or not is_official_5etools_source(src, sp):
            continue
        eid = f"ID_5ETOOLS_SPELL_{_slug(src)}_{_slug(name)}"
        el = _new_element(name, "Spell", f"5e.tools ({src})", eid)
        _set_description(el, render_5etools_entries(sp.get("entries", [])))
        class_tags: list[str] = []
        classes_obj = sp.get("classes")
        if isinstance(classes_obj, dict):
            from_list = classes_obj.get("fromClassList")
            if isinstance(from_list, list):
                seen_cls: set[str] = set()
                for entry in from_list:
                    if isinstance(entry, dict):
                        cname = str(entry.get("name") or "").strip()
                        if cname and cname.lower() not in seen_cls:
                            seen_cls.add(cname.lower())
                            class_tags.append(cname)
        if class_tags:
            etree.SubElement(el, "supports").text = ", ".join(class_tags)
        setters = etree.SubElement(el, "setters")
        etree.SubElement(setters, "set", name="level").text = str(sp.get("level", 0))
        school = _SPELL_SCHOOL_MAP.get(str(sp.get("school", "")).upper(), str(sp.get("school", "")))
        if school:
            etree.SubElement(setters, "set", name="school").text = school
        out.append(el)
    return out


def _convert_items(data: dict) -> list[etree._Element]:
    out: list[etree._Element] = []
    items = [*data.get("baseitem", []), *data.get("item", [])]
    for it in items:
        name = (it.get("name") or "").strip()
        src = (it.get("source") or "").strip()
        if not name or not is_official_5etools_source(src, it):
            continue
        rarity = str(it.get("rarity") or "none").lower()
        is_weapon = bool(it.get("weapon") or it.get("weaponCategory"))
        is_armor = bool(it.get("armor") or it.get("ac"))
        if rarity not in ("none", "", "unknown"):
            etype = "Magic Item"
        elif is_weapon:
            etype = "Weapon"
        elif is_armor:
            etype = "Armor"
        else:
            etype = "Item"

        eid = f"ID_5ETOOLS_ITEM_{_slug(src)}_{_slug(name)}"
        el = _new_element(name, etype, f"5e.tools ({src})", eid)
        _set_description(el, render_5etools_entries(it.get("entries", [])))
        setters = etree.SubElement(el, "setters")
        if rarity not in ("none", "", "unknown"):
            etree.SubElement(setters, "set", name="rarity").text = rarity.title()
        if it.get("weight") is not None:
            w = etree.SubElement(setters, "set", name="weight", lb=str(it["weight"]))
            w.text = f"{it['weight']} lb."
        if it.get("ac") is not None:
            etree.SubElement(setters, "set", name="armorClass").text = str(it["ac"])
            item_type = str(it.get("type", "")).upper()
            if item_type == "LA":
                etree.SubElement(setters, "set", name="armor").text = "Light"
            elif item_type == "MA":
                etree.SubElement(setters, "set", name="armor").text = "Medium"
            elif item_type == "HA":
                etree.SubElement(setters, "set", name="armor").text = "Heavy"
            elif item_type == "S":
                etree.SubElement(setters, "set", name="armor").text = "Shield"
        if it.get("dmg1"):
            etree.SubElement(setters, "set", name="damage").text = str(it["dmg1"])
        out.append(el)
    return out


def _convert_classes(data: dict) -> list[etree._Element]:
    out: list[etree._Element] = []
    for cls in data.get("class", []):
        name = (cls.get("name") or "").strip()
        src = (cls.get("source") or "").strip()
        if not name or "sidekick" in name.lower() or not is_official_5etools_source(src, cls):
            continue
        cls_id = f"ID_5ETOOLS_CLASS_{_slug(src)}_{_slug(name)}"
        el = _new_element(name, "Class", f"5e.tools ({src})", cls_id)
        _set_description(el, render_5etools_entries(cls.get("entries", [])))
        setters = etree.SubElement(el, "setters")
        hd = cls.get("hd")
        if isinstance(hd, dict) and hd.get("faces"):
            etree.SubElement(setters, "set", name="hd").text = f"d{hd['faces']}"
        rules = etree.SubElement(el, "rules")
        for ab in cls.get("proficiency", []):
            full_ab = _ABILITY_FULL.get(str(ab).lower())
            if full_ab:
                etree.SubElement(
                    rules,
                    "grant",
                    type="Proficiency",
                    id=f"ID_PROFICIENCY_SAVINGTHROW_{full_ab.upper()}",
                )
        if cls.get("spellcastingAbility"):
            ab_full = _ABILITY_FULL.get(str(cls["spellcastingAbility"]).lower(), "Intelligence").capitalize()
            sc = etree.SubElement(el, "spellcasting", name=name, ability=ab_full)
            etree.SubElement(sc, "list").text = name
        out.append(el)

    for sc in data.get("subclass", []):
        name = (sc.get("name") or "").strip()
        src = (sc.get("source") or "").strip()
        cls_name = (sc.get("className") or "").strip()
        if not name or not is_official_5etools_source(src, sc):
            continue
        eid = f"ID_5ETOOLS_ARCH_{_slug(src)}_{_slug(cls_name)}_{_slug(name)}"
        el = _new_element(name, "Archetype", f"5e.tools ({src})", eid)
        _set_description(el, render_5etools_entries(sc.get("entries", [])))
        out.append(el)
    return out


def _write_elements_xml(elements: list[etree._Element], out_path: Path) -> bool:
    if not elements:
        return False
    root = etree.Element("elements")
    for el in elements:
        root.append(el)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(
        etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True)
    )
    return True


def import_5etools_directory(
    src_dir: Path,
    custom_root: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> IndexRecord:
    """Convert a local 5e.tools data directory into Aurora XML files under custom_root/5etools."""
    src_dir = Path(src_dir)
    if not src_dir.is_dir():
        raise FileNotFoundError(f"5e.tools directory not found: {src_dir}")

    target_dir = Path(custom_root) / "5etools"
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    def _load_json(path: Path) -> Optional[dict]:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    single_files = [
        ("races.json", _convert_races, "races.xml"),
        ("backgrounds.json", _convert_backgrounds, "backgrounds.xml"),
        ("feats.json", _convert_feats, "feats.xml"),
        ("items-base.json", _convert_items, "items_base.xml"),
        ("items.json", _convert_items, "items.xml"),
    ]
    for rel_json, conv_fn, out_xml in single_files:
        jp = src_dir / rel_json
        if jp.is_file():
            data = _load_json(jp)
            if data and _write_elements_xml(conv_fn(data), target_dir / out_xml):
                written += 1
                if progress_cb:
                    progress_cb(f"Converted {rel_json} -> {out_xml}")

    for sub_dir, conv_fn, prefix in (
        ("spells", _convert_spells, "spells"),
        ("class", _convert_classes, "class"),
    ):
        sub_path = src_dir / sub_dir
        if sub_path.is_dir():
            for jp in sorted(sub_path.glob("*.json")):
                if jp.name in ("index.json", "class-sidekick.json", "class-generic.json"):
                    continue
                data = _load_json(jp)
                if data and _write_elements_xml(conv_fn(data), target_dir / f"{prefix}_{jp.stem}.xml"):
                    written += 1
                    if progress_cb:
                        progress_cb(f"Converted {sub_dir}/{jp.name}")

    return IndexRecord(
        slug="5etools",
        name="5e.tools Data",
        url=str(src_dir),
        version="local",
        author="5e.tools",
        description="Converted 5e.tools JSON datasets",
        local_dir=str(target_dir),
        file_count=written,
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def import_5etools_from_github(
    custom_root: Path,
    base_url: str = DEFAULT_5ETOOLS_RAW_BASE,
    progress_cb: Optional[Callable[[str], None]] = None,
    fetcher: Callable[[str], bytes] = fetch_url_bytes,
) -> IndexRecord:
    """Fetch core & 2024 5e.tools JSON files from GitHub and convert them to Aurora XML."""
    target_dir = Path(custom_root) / "5etools"
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    if not base_url.endswith("/"):
        base_url += "/"
    written = 0

    def _fetch_json(rel_path: str) -> Optional[dict]:
        url = base_url + rel_path
        if progress_cb:
            progress_cb(f"Fetching {url}...")
        try:
            raw = fetcher(url)
            obj = json.loads(raw.decode("utf-8"))
            return obj if isinstance(obj, dict) else None
        except Exception as exc:
            if progress_cb:
                progress_cb(f"Skipped {rel_path}: {exc}")
            return None

    direct_specs = [
        ("races.json", _convert_races, "races.xml"),
        ("backgrounds.json", _convert_backgrounds, "backgrounds.xml"),
        ("feats.json", _convert_feats, "feats.xml"),
        ("items-base.json", _convert_items, "items_base.xml"),
        ("spells/spells-phb.json", _convert_spells, "spells_phb.xml"),
        ("spells/spells-xphb.json", _convert_spells, "spells_xphb.xml"),
    ]
    for rel_json, conv_fn, out_xml in direct_specs:
        data = _fetch_json(rel_json)
        if data and _write_elements_xml(conv_fn(data), target_dir / out_xml):
            written += 1

    cls_idx = _fetch_json("class/index.json")
    if cls_idx:
        for _cls_name, rel_file in cls_idx.items():
            if not isinstance(rel_file, str):
                continue
            if Path(rel_file).name in ("class-sidekick.json", "class-generic.json"):
                continue
            cdata = _fetch_json(f"class/{rel_file}")
            if cdata and _write_elements_xml(_convert_classes(cdata), target_dir / f"class_{Path(rel_file).stem}.xml"):
                written += 1

    if progress_cb:
        progress_cb(f"5e.tools import complete ({written} XML files written)")

    return IndexRecord(
        slug="5etools",
        name="5e.tools Data (GitHub)",
        url=base_url,
        version="main",
        author="5e.tools",
        description="Imported from 5e.tools JSON data",
        local_dir=str(target_dir),
        file_count=written,
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
