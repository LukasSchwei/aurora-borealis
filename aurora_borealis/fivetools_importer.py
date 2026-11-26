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


_DAMAGE_TYPE_MAP = {
    "A": "Acid",
    "B": "Bludgeoning",
    "C": "Cold",
    "F": "Fire",
    "O": "Force",
    "L": "Lightning",
    "N": "Necrotic",
    "P": "Piercing",
    "I": "Poison",
    "Y": "Psychic",
    "R": "Radiant",
    "S": "Slashing",
    "T": "Thunder",
}

_WEAPON_PROPERTY_MAP = {
    "A": "Ammunition",
    "F": "Finesse",
    "H": "Heavy",
    "L": "Light",
    "LD": "Loading",
    "R": "Reach",
    "S": "Special",
    "T": "Thrown",
    "2H": "Two-Handed",
    "V": "Versatile",
}


def _format_5etools_time(time_list: Any) -> str:
    if not isinstance(time_list, list) or not time_list:
        return ""
    t0 = time_list[0]
    if not isinstance(t0, dict):
        return ""
    num = t0.get("number", 1)
    unit = str(t0.get("unit") or "").strip()
    if not unit:
        return ""
    return f"{num} {unit}"


def _format_5etools_range(range_obj: Any) -> str:
    if not isinstance(range_obj, dict):
        return ""
    rtype = str(range_obj.get("type") or "").strip()
    dist = range_obj.get("distance") or {}
    if isinstance(dist, dict):
        dtype = str(dist.get("type") or "").strip()
        amt = dist.get("amount")
        if dtype == "self":
            return "Self"
        if dtype == "touch":
            return "Touch"
        if dtype == "sight":
            return "Sight"
        if dtype == "unlimited":
            return "Unlimited"
        if amt is not None and dtype:
            base = f"{amt} {dtype}"
            if rtype and rtype != "point":
                return f"Self ({base} {rtype})"
            return base
    return rtype.capitalize() if rtype else ""


def _format_5etools_duration(dur_list: Any) -> tuple[str, bool]:
    if not isinstance(dur_list, list) or not dur_list:
        return "", False
    d0 = dur_list[0]
    if not isinstance(d0, dict):
        return "", False
    is_conc = bool(d0.get("concentration"))
    dtype = str(d0.get("type") or "").strip()
    if dtype == "instant":
        return "Instantaneous", is_conc
    if dtype == "permanent":
        return "Until dispelled", is_conc
    if dtype == "special":
        return "Special", is_conc
    dur = d0.get("duration") or {}
    if isinstance(dur, dict):
        amt = dur.get("amount", 1)
        unit = str(dur.get("type") or "").strip()
        txt = f"{amt} {unit}" if unit else dtype
        return (f"Concentration, up to {txt}" if is_conc else txt), is_conc
    return dtype.capitalize(), is_conc


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
        meta = sp.get("meta") if isinstance(sp.get("meta"), dict) else {}
        is_ritual = bool(meta.get("ritual"))
        dur_txt, is_conc = _format_5etools_duration(sp.get("duration"))
        sup_tokens = list(class_tags)
        if is_ritual:
            sup_tokens.append("Ritual")
        if is_conc:
            sup_tokens.append("Concentration")
        if sup_tokens:
            etree.SubElement(el, "supports").text = ", ".join(dict.fromkeys(sup_tokens))

        setters = etree.SubElement(el, "setters")
        etree.SubElement(setters, "set", name="level").text = str(sp.get("level", 0))
        school = _SPELL_SCHOOL_MAP.get(str(sp.get("school", "")).upper(), str(sp.get("school", "")))
        if school:
            etree.SubElement(setters, "set", name="school").text = school
        time_txt = _format_5etools_time(sp.get("time"))
        if time_txt:
            etree.SubElement(setters, "set", name="time").text = time_txt
        range_txt = _format_5etools_range(sp.get("range"))
        if range_txt:
            etree.SubElement(setters, "set", name="range").text = range_txt
        if dur_txt:
            etree.SubElement(setters, "set", name="duration").text = dur_txt
        etree.SubElement(setters, "set", name="isRitual").text = "true" if is_ritual else "false"
        etree.SubElement(setters, "set", name="isConcentration").text = "true" if is_conc else "false"

        comp_obj = sp.get("components")
        if isinstance(comp_obj, dict):
            has_v = bool(comp_obj.get("v"))
            has_s = bool(comp_obj.get("s"))
            m_raw = comp_obj.get("m")
            has_m = bool(m_raw)
            comp_letters = [ch for flag, ch in ((has_v, "V"), (has_s, "S"), (has_m, "M")) if flag]
            if comp_letters:
                etree.SubElement(setters, "set", name="components").text = ", ".join(comp_letters)
            etree.SubElement(setters, "set", name="hasVerbalComponent").text = "true" if has_v else "false"
            etree.SubElement(setters, "set", name="hasSomaticComponent").text = "true" if has_s else "false"
            etree.SubElement(setters, "set", name="hasMaterialComponent").text = "true" if has_m else "false"
            if isinstance(m_raw, str) and m_raw.strip():
                etree.SubElement(setters, "set", name="materialComponent").text = m_raw.strip()
            elif isinstance(m_raw, dict) and m_raw.get("text"):
                etree.SubElement(setters, "set", name="materialComponent").text = str(m_raw["text"]).strip()
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
        item_type = str(it.get("type", "")).upper()
        wcat = str(it.get("weaponCategory") or "").strip().lower()
        sup_tokens: list[str] = []
        if wcat:
            sup_tokens.append(wcat.title())
        type_support_map = {
            "M": "Melee",
            "R": "Ranged",
            "AT": "Artisan's Tools",
            "INS": "Musical Instrument",
            "GS": "Gaming Set",
            "T": "Tool",
            "LA": "Light",
            "MA": "Medium",
            "HA": "Heavy",
            "S": "Shield",
        }
        if item_type in type_support_map:
            sup_tokens.append(type_support_map[item_type])
        prop_names: list[str] = []
        for pcode in it.get("property", []) or []:
            pname = _WEAPON_PROPERTY_MAP.get(str(pcode).split("|")[0].upper())
            if pname:
                prop_names.append(pname)
                sup_tokens.append(pname)
        if sup_tokens:
            etree.SubElement(el, "supports").text = ", ".join(dict.fromkeys(sup_tokens))

        setters = etree.SubElement(el, "setters")
        if item_type in type_support_map:
            etree.SubElement(setters, "set", name="category").text = type_support_map[item_type]
        if rarity not in ("none", "", "unknown"):
            etree.SubElement(setters, "set", name="rarity").text = rarity.title()
        if prop_names:
            etree.SubElement(setters, "set", name="properties").text = ", ".join(dict.fromkeys(prop_names))
        if it.get("reqAttune"):
            etree.SubElement(setters, "set", name="attunement").text = "true"
        if it.get("value") is not None:
            try:
                cp_val = int(it["value"])
                if cp_val >= 100 and cp_val % 100 == 0:
                    c_node = etree.SubElement(setters, "set", name="cost", currency="gp")
                    c_node.text = str(cp_val // 100)
                elif cp_val >= 10 and cp_val % 10 == 0:
                    c_node = etree.SubElement(setters, "set", name="cost", currency="sp")
                    c_node.text = str(cp_val // 10)
                else:
                    c_node = etree.SubElement(setters, "set", name="cost", currency="cp")
                    c_node.text = str(cp_val)
            except (TypeError, ValueError):
                pass
        if it.get("weight") is not None:
            w = etree.SubElement(setters, "set", name="weight", lb=str(it["weight"]))
            w.text = f"{it['weight']} lb."
        if it.get("ac") is not None:
            etree.SubElement(setters, "set", name="armorClass").text = str(it["ac"])
            if item_type == "LA":
                etree.SubElement(setters, "set", name="armor").text = "Light"
            elif item_type == "MA":
                etree.SubElement(setters, "set", name="armor").text = "Medium"
            elif item_type == "HA":
                etree.SubElement(setters, "set", name="armor").text = "Heavy"
            elif item_type == "S":
                etree.SubElement(setters, "set", name="armor").text = "Shield"
        if it.get("dmg1"):
            dmg_type = _DAMAGE_TYPE_MAP.get(str(it.get("dmgType") or "").upper(), "")
            d_attrs = {"name": "damage"}
            if dmg_type:
                d_attrs["type"] = dmg_type
            d_node = etree.SubElement(setters, "set", **d_attrs)
            d_node.text = str(it["dmg1"])
        if it.get("dmg2"):
            etree.SubElement(setters, "set", name="versatile").text = str(it["dmg2"])
        if it.get("range"):
            etree.SubElement(setters, "set", name="range").text = str(it["range"])
        out.append(el)
    return out


def _convert_classes(data: dict) -> list[etree._Element]:
    out: list[etree._Element] = []
    class_features_by_key: dict[tuple[str, str], list[tuple[int, str, str]]] = {}
    for cf in data.get("classFeature", []):
        if not isinstance(cf, dict):
            continue
        cf_name = (cf.get("name") or "").strip()
        cf_src = (cf.get("source") or "").strip()
        cls_name = (cf.get("className") or "").strip()
        lvl = int(cf.get("level") or 1)
        if not cf_name or not cls_name or not is_official_5etools_source(cf_src, cf):
            continue
        cf_id = f"ID_5ETOOLS_CF_{_slug(cf_src)}_{_slug(cls_name)}_{lvl}_{_slug(cf_name)}"
        cf_el = _new_element(cf_name, "Class Feature", f"5e.tools ({cf_src})", cf_id)
        _set_description(cf_el, render_5etools_entries(cf.get("entries", [])))
        out.append(cf_el)
        class_features_by_key.setdefault((cls_name.lower(), cf_src.lower()), []).append((lvl, cf_id, cf_name))

    sub_features_by_key: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    for sf in data.get("subclassFeature", []):
        if not isinstance(sf, dict):
            continue
        sf_name = (sf.get("name") or "").strip()
        sf_src = (sf.get("source") or "").strip()
        cls_name = (sf.get("className") or "").strip()
        sc_short = (sf.get("subclassShortName") or "").strip()
        lvl = int(sf.get("level") or 3)
        if not sf_name or not cls_name or not sc_short or not is_official_5etools_source(sf_src, sf):
            continue
        sf_id = f"ID_5ETOOLS_AF_{_slug(sf_src)}_{_slug(cls_name)}_{_slug(sc_short)}_{lvl}_{_slug(sf_name)}"
        sf_el = _new_element(sf_name, "Archetype Feature", f"5e.tools ({sf_src})", sf_id)
        _set_description(sf_el, render_5etools_entries(sf.get("entries", [])))
        out.append(sf_el)
        sub_features_by_key.setdefault((cls_name.lower(), sc_short.lower(), sf_src.lower()), []).append((lvl, sf_id))

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
        sp_profs = cls.get("startingProficiencies") or {}
        if isinstance(sp_profs, dict):
            for armor_raw in sp_profs.get("armor", []) or []:
                al = str(armor_raw).lower()
                for ak, pid in (
                    ("light", "ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR"),
                    ("medium", "ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR"),
                    ("heavy", "ID_PROFICIENCY_ARMOR_PROFICIENCY_HEAVY_ARMOR"),
                    ("shield", "ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS"),
                ):
                    if ak in al:
                        etree.SubElement(rules, "grant", type="Proficiency", id=pid)
            for wpn_raw in sp_profs.get("weapons", []) or []:
                wl = str(wpn_raw).lower()
                if "simple" in wl:
                    etree.SubElement(rules, "grant", type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS")
                if "martial" in wl:
                    etree.SubElement(rules, "grant", type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS")
            for sk_entry in sp_profs.get("skills", []) or []:
                if isinstance(sk_entry, dict) and isinstance(sk_entry.get("choose"), dict):
                    ch = sk_entry["choose"]
                    cnt = int(ch.get("count") or 2)
                    from_sk = [str(s) for s in (ch.get("from") or []) if s]
                    sup = " || ".join(from_sk) if from_sk else "Skill"
                    etree.SubElement(rules, "select", type="Proficiency", name=f"{name} Skill", supports=sup, number=str(cnt))

        sc_title = str(cls.get("subclassTitle") or f"{name} Subclass").strip()
        sc_level = 3 if src.upper().startswith("X") else 1
        for lvl, cf_id, cf_name in sorted(class_features_by_key.get((name.lower(), src.lower()), [])):
            etree.SubElement(rules, "grant", type="Class Feature", id=cf_id, level=str(lvl))
            if sc_title.lower() in cf_name.lower():
                sc_level = lvl
        etree.SubElement(rules, "select", type="Archetype", name=sc_title, supports=name, level=str(sc_level))

        if cls.get("spellcastingAbility"):
            ab_full = _ABILITY_FULL.get(str(cls["spellcastingAbility"]).lower(), "Intelligence").capitalize()
            sc = etree.SubElement(el, "spellcasting", name=name, ability=ab_full)
            etree.SubElement(sc, "list").text = name
        out.append(el)

    for sc in data.get("subclass", []):
        name = (sc.get("name") or "").strip()
        src = (sc.get("source") or "").strip()
        cls_name = (sc.get("className") or "").strip()
        sc_short = (sc.get("shortName") or name).strip()
        if not name or not is_official_5etools_source(src, sc):
            continue
        eid = f"ID_5ETOOLS_ARCH_{_slug(src)}_{_slug(cls_name)}_{_slug(name)}"
        el = _new_element(name, "Archetype", f"5e.tools ({src})", eid)
        if cls_name:
            etree.SubElement(el, "supports").text = cls_name
        _set_description(el, render_5etools_entries(sc.get("entries", [])))
        s_rules = etree.SubElement(el, "rules")
        for lvl, sf_id in sorted(sub_features_by_key.get((cls_name.lower(), sc_short.lower(), src.lower()), [])):
            etree.SubElement(s_rules, "grant", type="Archetype Feature", id=sf_id, level=str(lvl))
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
