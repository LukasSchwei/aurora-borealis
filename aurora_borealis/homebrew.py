"""Visual Homebrew XML builder, validator, and custom directory persistence."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional

from lxml import etree

from .loader import ContentRepository

HOMEBREW_ELEMENT_TYPES: tuple[str, ...] = (
    "Race",
    "Archetype",
    "Feat",
    "Spell",
    "Magic Item",
    "Weapon",
    "Armor",
    "Background",
)


def _slug_upper(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", (text or "").upper()).strip("_") or "CUSTOM"


def _slug_lower(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "homebrew_pack"


def make_homebrew_id(etype: str, name: str, source: str = "Homebrew") -> str:
    """Generate a clean Aurora-compatible element ID."""
    return f"ID_{_slug_upper(source)}_{_slug_upper(etype)}_{_slug_upper(name)}"


def _append_description_node(parent: etree._Element, desc_text: str) -> None:
    desc = etree.SubElement(parent, "description")
    clean = (desc_text or "").strip()
    if not clean:
        etree.SubElement(desc, "p")
        return
    if "<" in clean and ">" in clean:
        try:
            wrapped = etree.fromstring(f"<description>{clean}</description>")
            for child in wrapped:
                desc.append(child)
            if wrapped.text:
                desc.text = wrapped.text
            return
        except etree.XMLSyntaxError:
            pass
    for para in [p.strip() for p in clean.splitlines() if p.strip()]:
        pnode = etree.SubElement(desc, "p")
        pnode.text = para


def build_homebrew_element(spec: dict) -> etree._Element:
    """Build a valid Aurora <element> node from a structured GUI dictionary."""
    etype = str(spec.get("type") or "Feat").strip()
    name = str(spec.get("name") or "Custom Element").strip() or "Custom Element"
    source = str(spec.get("source") or "Homebrew").strip() or "Homebrew"
    eid = str(spec.get("id") or "").strip() or make_homebrew_id(etype, name, source)

    el = etree.Element("element", name=name, type=etype, source=source, id=eid)

    supports = [s.strip() for s in str(spec.get("supports") or "").split(",") if s.strip()]
    if supports:
        etree.SubElement(el, "supports").text = ", ".join(supports)

    _append_description_node(el, str(spec.get("description") or ""))

    sheet_desc = str(spec.get("sheet_description") or "").strip()
    sheet_action = str(spec.get("sheet_action") or "").strip()
    sheet_usage = str(spec.get("sheet_usage") or "").strip()
    if sheet_desc or sheet_action or sheet_usage:
        s_attrs = {}
        if sheet_action:
            s_attrs["action"] = sheet_action
        if sheet_usage:
            s_attrs["usage"] = sheet_usage
        s_node = etree.SubElement(el, "sheet", **s_attrs)
        if sheet_desc:
            d_node = etree.SubElement(s_node, "description")
            d_node.text = sheet_desc

    setters_dict: dict[str, tuple[str, dict[str, str]]] = {}
    for k, v in (spec.get("setters") or {}).items():
        if isinstance(v, tuple):
            val, attrs = str(v[0]), dict(v[1])
        else:
            val, attrs = str(v), {}
        if k and val != "":
            setters_dict[str(k)] = (val, attrs)

    if setters_dict:
        st_node = etree.SubElement(el, "setters")
        for k, (val, attrs) in setters_dict.items():
            sn = etree.SubElement(st_node, "set", name=k, **attrs)
            sn.text = val

    rules_data = spec.get("rules") or []
    grants = spec.get("grants") or []
    stats = spec.get("stats") or []
    selects = spec.get("selects") or []
    if rules_data or grants or stats or selects:
        r_node = etree.SubElement(el, "rules")
        for g in grants:
            if isinstance(g, dict) and g.get("id"):
                attrs = {"type": str(g.get("type") or "Feat"), "id": str(g["id"])}
                if g.get("level") and int(g["level"]) > 1:
                    attrs["level"] = str(int(g["level"]))
                if g.get("requirements"):
                    attrs["requirements"] = str(g["requirements"])
                etree.SubElement(r_node, "grant", **attrs)
        for st in stats:
            if isinstance(st, dict) and st.get("name") and st.get("value"):
                attrs = {"name": str(st["name"]), "value": str(st["value"])}
                if st.get("bonus"):
                    attrs["bonus"] = str(st["bonus"])
                if st.get("level") and int(st["level"]) > 1:
                    attrs["level"] = str(int(st["level"]))
                if st.get("maximum"):
                    attrs["maximum"] = str(st["maximum"])
                etree.SubElement(r_node, "stat", **attrs)
        for sl in selects:
            if isinstance(sl, dict) and sl.get("type"):
                attrs = {
                    "type": str(sl["type"]),
                    "name": str(sl.get("name") or sl["type"]),
                }
                if sl.get("supports"):
                    attrs["supports"] = str(sl["supports"])
                if sl.get("number") and int(sl["number"]) > 1:
                    attrs["number"] = str(int(sl["number"]))
                if sl.get("level") and int(sl["level"]) > 1:
                    attrs["level"] = str(int(sl["level"]))
                etree.SubElement(r_node, "select", **attrs)
        for raw_r in rules_data:
            if isinstance(raw_r, etree._Element):
                r_node.append(raw_r)

    return el


def serialize_homebrew_elements(elements: list[etree._Element]) -> str:
    """Serialize a list of <element> nodes into a formatted Aurora <elements> XML string."""
    root = etree.Element("elements")
    for el in elements:
        root.append(el)
    return etree.tostring(root, encoding="unicode", pretty_print=True)


def serialize_homebrew_document(elements: list[etree._Element]) -> bytes:
    """Serialize a list of <element> nodes into UTF-8 XML bytes with XML declaration."""
    root = etree.Element("elements")
    for el in elements:
        root.append(el)
    return etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True)


def validate_homebrew_xml(xml_text: str) -> tuple[bool, list[str]]:
    """Validate Aurora homebrew XML syntax, structure, duplicate IDs, and repo parsing."""
    errors: list[str] = []
    txt = (xml_text or "").strip()
    if not txt:
        return False, ["XML content is empty."]

    try:
        root = etree.fromstring(txt.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return False, [f"XML Syntax Error: {exc}"]

    if root.tag != "elements":
        return False, [f"Root element must be <elements>, found <{root.tag}>."]

    elements = root.findall("element")
    if not elements:
        return False, ["No <element> entries found inside <elements>."]

    seen_ids: set[str] = set()
    for idx, node in enumerate(elements, start=1):
        eid = (node.get("id") or "").strip()
        name = (node.get("name") or "").strip()
        etype = (node.get("type") or "").strip()
        if not eid:
            errors.append(f"Element #{idx}: missing 'id' attribute.")
        elif eid in seen_ids:
            errors.append(f"Element #{idx}: duplicate ID '{eid}'.")
        else:
            seen_ids.add(eid)
        if not name:
            errors.append(f"Element #{idx}: missing 'name' attribute.")
        if not etype:
            errors.append(f"Element #{idx}: missing 'type' attribute.")

    if errors:
        return False, errors

    repo = ContentRepository()
    parser = etree.XMLParser(recover=False)
    try:
        parsed_root = etree.fromstring(txt.encode("utf-8"), parser=parser)
        for node in parsed_root.findall("element"):
            if repo._parse_element(node) is None:
                errors.append(f"Failed to parse element '{node.get('id', '?')}'.")
    except Exception as exc:
        errors.append(f"Parser error: {exc}")

    return (len(errors) == 0), errors


def save_homebrew_pack(xml_text: str, custom_dir: Path, filename: str) -> Path:
    """Validate and save a homebrew XML file into custom_dir/homebrew/<filename>.xml."""
    ok, errs = validate_homebrew_xml(xml_text)
    if not ok:
        raise ValueError("\n".join(errs))
    hb_dir = Path(custom_dir) / "homebrew"
    hb_dir.mkdir(parents=True, exist_ok=True)
    stem = _slug_lower(Path(filename).stem)
    out_path = hb_dir / f"{stem}.xml"
    body = xml_text.strip()
    if not body.startswith("<?xml"):
        body = '<?xml version="1.0" encoding="utf-8" ?>\n' + body
    out_path.write_text(body + "\n", encoding="utf-8")
    return out_path


def list_homebrew_files(custom_dir: Path) -> list[Path]:
    hb_dir = Path(custom_dir) / "homebrew"
    if not hb_dir.is_dir():
        return []
    return sorted(hb_dir.glob("*.xml"), key=lambda p: p.name.lower())


def parse_homebrew_file_to_specs(xml_path: Path) -> list[dict]:
    """Load an existing homebrew XML file back into editable spec dicts."""
    repo = ContentRepository()
    repo.load_directory(xml_path.parent)
    parser = etree.XMLParser(recover=True, remove_comments=True)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()
    if root is None:
        return []
    specs: list[dict] = []
    for node in root.findall("element"):
        el = repo._parse_element(node)
        if el is None:
            continue
        specs.append(
            {
                "id": el.id,
                "name": el.name,
                "type": el.type,
                "source": el.source or "Homebrew",
                "supports": ", ".join(el.supports),
                "description": re.sub(r"</?(?:p|description)>", "\n", el.description_html or "").strip(),
                "sheet_description": el.sheet_description,
                "sheet_action": el.sheet_action,
                "sheet_usage": el.sheet_usage,
                "setters": dict(el.setters),
                "grants": [{"type": g.type, "id": g.id, "level": g.level} for g in el.grant_rules],
                "stats": [{"name": s.name, "value": s.value, "bonus": s.bonus, "level": s.level} for s in el.stat_rules],
                "selects": [
                    {"type": s.type, "name": s.name, "supports": s.supports, "number": s.number, "level": s.level}
                    for s in el.select_rules
                ],
            }
        )
    return specs
