"""Load and index Aurora Builder XML element files."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable, Optional

from lxml import etree

from .models import DuplicateEntry, Element, GrantRule, SelectRule, SpellcastingInfo, StatRule

_EXPR_TOKEN_RE = re.compile(r"\s*(\|\||&&|\(|\)|,|!|[^|&(),!]+)")

_CHARACTER_FACING_TYPES = {
    "Race",
    "Sub Race",
    "Race Variant",
    "Class",
    "Archetype",
    "Background",
    "Feat",
    "Spell",
    "Weapon",
    "Armor",
    "Magic Item",
    "Item",
    "Deity",
    "Language",
}

_OFFICIAL_SOURCE_KEYWORDS = (
    "player",
    "tasha",
    "xanathar",
    "mordenkainen",
    "volo",
    "sword coast",
    "eberron",
    "fizban",
    "van richten",
    "dungeon master",
    "monster manual",
)


def _source_priority(source: str) -> int:
    sl = (source or "").lower()
    if "system reference document" in sl or "srd" in sl:
        return 1
    if sl.startswith("5e.tools"):
        return 2
    if any(k in sl for k in _OFFICIAL_SOURCE_KEYWORDS):
        return 4
    return 3


def _parse_int(value: Optional[str], default: int = 1) -> int:
    if not value:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _inner_html(node: Optional[etree._Element]) -> str:
    if node is None:
        return ""
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node:
        parts.append(etree.tostring(child, encoding="unicode"))
    return "".join(parts).strip()


def evaluate_boolean_expr(expr: str, predicate: Callable[[str], bool]) -> bool:
    """Evaluate Aurora boolean expressions supporting ',', '&&', '||', '!', and '()'."""
    expr = (expr or "").strip()
    if not expr:
        return True

    tokens = [t.strip() for t in _EXPR_TOKEN_RE.findall(expr) if t.strip()]
    if not tokens:
        return True

    pos = 0

    def peek() -> Optional[str]:
        return tokens[pos] if pos < len(tokens) else None

    def consume() -> str:
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        return tok

    def parse_or() -> bool:
        val = parse_and()
        while peek() == "||":
            consume()
            rhs = parse_and()
            val = val or rhs
        return val

    def parse_and() -> bool:
        val = parse_not()
        while peek() in (",", "&&"):
            consume()
            rhs = parse_not()
            val = val and rhs
        return val

    def parse_not() -> bool:
        if peek() == "!":
            consume()
            return not parse_not()
        return parse_primary()

    def parse_primary() -> bool:
        tok = peek()
        if tok is None:
            return True
        if tok == "(":
            consume()
            val = parse_or()
            if peek() == ")":
                consume()
            return val
        if tok in (")", ",", "&&", "||"):
            return True
        consume()
        return predicate(tok)

    return parse_or()


class ContentRepository:
    """Repository of parsed Aurora <element> definitions."""

    def __init__(self) -> None:
        self.by_id: dict[str, Element] = {}
        self.by_type: dict[str, list[Element]] = defaultdict(list)
        self.loaded_dirs: list[Path] = []
        self.file_count: int = 0
        self.duplicates: list[DuplicateEntry] = []
        self._by_type_name: dict[tuple[str, str], Element] = {}

    def clear(self) -> None:
        self.by_id.clear()
        self.by_type.clear()
        self.loaded_dirs.clear()
        self.file_count = 0
        self.duplicates.clear()
        self._by_type_name.clear()

    def duplicate_summary(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for d in self.duplicates:
            counts[d.element_type] += 1
        return dict(sorted(counts.items()))

    def load_directory(self, directory: Path) -> int:
        directory = Path(directory)
        if not directory.is_dir():
            return 0
        if directory not in self.loaded_dirs:
            self.loaded_dirs.append(directory)

        parser = etree.XMLParser(recover=True, remove_comments=True)
        count = 0
        for xml_path in sorted(directory.rglob("*.xml")):
            loaded = self._load_file(xml_path, parser)
            if loaded > 0:
                self.file_count += 1
                count += loaded
        for elems in self.by_type.values():
            elems.sort(key=lambda e: (e.name.lower(), e.id))
        return count

    def load_directories(self, directories: Iterable[Path]) -> int:
        total = 0
        for d in directories:
            total += self.load_directory(d)
        return total

    def _load_file(self, path: Path, parser: etree.XMLParser) -> int:
        try:
            tree = etree.parse(str(path), parser)
        except Exception:
            return 0
        root = tree.getroot()
        if root is None or root.tag != "elements":
            return 0

        added = 0
        for node in root.findall("element"):
            el = self._parse_element(node)
            if el is None:
                continue
            if el.id in self.by_id:
                old = self.by_id[el.id]
                new_prio = _source_priority(el.source)
                old_prio = _source_priority(old.source)
                if new_prio >= old_prio:
                    self.duplicates.append(
                        DuplicateEntry(
                            kind="id",
                            element_id=el.id,
                            name=el.name,
                            element_type=el.type,
                            kept_source=el.source,
                            duplicate_source=old.source,
                            file_path=str(path),
                        )
                    )
                    if old in self.by_type[old.type]:
                        self.by_type[old.type].remove(old)
                    self.by_id[el.id] = el
                    self._register_in_type_list(el, path)
                else:
                    self.duplicates.append(
                        DuplicateEntry(
                            kind="id",
                            element_id=el.id,
                            name=el.name,
                            element_type=el.type,
                            kept_source=old.source,
                            duplicate_source=el.source,
                            file_path=str(path),
                        )
                    )
                added += 1
                continue

            self.by_id[el.id] = el
            self._register_in_type_list(el, path)
            added += 1
        return added

    def _register_in_type_list(self, el: Element, path: Path) -> None:
        if el.type not in _CHARACTER_FACING_TYPES:
            if el not in self.by_type[el.type]:
                self.by_type[el.type].append(el)
            return

        tn_key = (el.type.lower(), el.name.lower())
        existing = self._by_type_name.get(tn_key)
        if existing is None or existing.id == el.id:
            if existing is not None and existing in self.by_type[existing.type]:
                self.by_type[existing.type].remove(existing)
            self.by_type[el.type].append(el)
            self._by_type_name[tn_key] = el
            return

        new_prio = _source_priority(el.source)
        old_prio = _source_priority(existing.source)
        if new_prio > old_prio:
            self.duplicates.append(
                DuplicateEntry(
                    kind="name",
                    element_id=el.id,
                    name=el.name,
                    element_type=el.type,
                    kept_source=el.source,
                    duplicate_source=existing.source,
                    file_path=str(path),
                )
            )
            if existing in self.by_type[existing.type]:
                self.by_type[existing.type].remove(existing)
            self.by_type[el.type].append(el)
            self._by_type_name[tn_key] = el
        else:
            self.duplicates.append(
                DuplicateEntry(
                    kind="name",
                    element_id=el.id,
                    name=el.name,
                    element_type=el.type,
                    kept_source=existing.source,
                    duplicate_source=el.source,
                    file_path=str(path),
                )
            )

    def _parse_element(self, node: etree._Element) -> Optional[Element]:
        el_id = (node.get("id") or "").strip()
        name = (node.get("name") or "").strip()
        el_type = (node.get("type") or "").strip()
        if not el_id or not name or not el_type:
            return None

        source = (node.get("source") or "").strip()
        supports_text = (node.findtext("supports") or "").strip()
        supports = [s.strip() for s in supports_text.split(",") if s.strip()]

        description_html = _inner_html(node.find("description"))

        sheet_node = node.find("sheet")
        sheet_desc = ""
        if sheet_node is not None:
            desc_child = sheet_node.find("description")
            sheet_desc = _inner_html(desc_child) if desc_child is not None else _inner_html(sheet_node)

        setters: dict[str, str] = {}
        setters_node = node.find("setters")
        if setters_node is not None:
            for s in setters_node.findall("set"):
                sname = (s.get("name") or "").strip()
                if sname:
                    setters[sname] = (s.text or "").strip()
                    if sname == "cost" and s.get("currency"):
                        setters["currency"] = s.get("currency", "")
                    if sname == "weight" and s.get("lb"):
                        setters["weight_lb"] = s.get("lb", "")
                    if sname == "damage" and s.get("type"):
                        setters["damage_type"] = s.get("type", "")

        grant_rules: list[GrantRule] = []
        select_rules: list[SelectRule] = []
        stat_rules: list[StatRule] = []

        rules_node = node.find("rules")
        if rules_node is not None:
            for r in rules_node:
                if r.tag == "grant":
                    gid = (r.get("id") or "").strip()
                    gtype = (r.get("type") or "").strip()
                    if gid:
                        grant_rules.append(
                            GrantRule(
                                type=gtype,
                                id=gid,
                                level=_parse_int(r.get("level"), 1),
                                requirements=(r.get("requirements") or "").strip(),
                            )
                        )
                elif r.tag == "select":
                    stype = (r.get("type") or "").strip()
                    sname = (r.get("name") or stype).strip()
                    items: list[tuple[str, str]] = []
                    for item_node in r.findall("item"):
                        iid = (item_node.get("id") or "").strip()
                        itext = (item_node.text or "").strip()
                        if iid or itext:
                            items.append((iid or itext, itext or iid))
                    select_rules.append(
                        SelectRule(
                            type=stype,
                            name=sname,
                            number=max(1, _parse_int(r.get("number"), 1)),
                            supports=(r.get("supports") or "").strip(),
                            level=_parse_int(r.get("level"), 1),
                            requirements=(r.get("requirements") or "").strip(),
                            optional=(r.get("optional") or "").lower() == "true",
                            items=items,
                            default=(r.get("default") or "").strip(),
                        )
                    )
                elif r.tag == "stat":
                    st_name = (r.get("name") or "").strip()
                    st_val = (r.get("value") or "").strip()
                    if st_name and st_val:
                        stat_rules.append(
                            StatRule(
                                name=st_name,
                                value=st_val,
                                bonus=(r.get("bonus") or "").strip(),
                                level=_parse_int(r.get("level"), 1),
                                requirements=(r.get("requirements") or "").strip(),
                                equipped=(r.get("equipped") or "").strip(),
                            )
                        )

        spellcasting: Optional[SpellcastingInfo] = None
        sc_node = node.find("spellcasting")
        if sc_node is not None:
            list_node = sc_node.find("list")
            spell_list = (list_node.text or "").strip() if list_node is not None else ""
            spellcasting = SpellcastingInfo(
                name=(sc_node.get("name") or name).strip(),
                ability=(sc_node.get("ability") or "Intelligence").strip(),
                prepare=(sc_node.get("prepare") or "").lower() == "true",
                allow_rituals=(sc_node.get("allowRituals") or "").lower() == "true",
                extend=(sc_node.get("extend") or "").lower() == "true",
                spell_list=spell_list or (sc_node.get("name") or "").strip(),
            )

        return Element(
            id=el_id,
            name=name,
            type=el_type,
            source=source,
            supports=supports,
            description_html=description_html,
            sheet_description=sheet_desc,
            setters=setters,
            grant_rules=grant_rules,
            select_rules=select_rules,
            stat_rules=stat_rules,
            spellcasting=spellcasting,
        )

    def get(self, element_id: str) -> Optional[Element]:
        return self.by_id.get(element_id)

    def of_type(self, element_type: str) -> list[Element]:
        return list(self.by_type.get(element_type, []))

    def types(self) -> list[str]:
        return sorted(self.by_type.keys())

    def match_supports(self, element: Element, supports_expr: str) -> bool:
        expr = (supports_expr or "").strip()
        if not expr:
            return True

        tokens_lower = {
            element.id.lower(),
            element.name.lower(),
            element.type.lower(),
            element.source.lower(),
            *(s.lower() for s in element.supports),
        }
        if element.type == "Spell":
            lvl = element.setters.get("level", "").strip().lower()
            if lvl:
                tokens_lower.add(lvl)
            school = element.setters.get("school", "").strip().lower()
            if school:
                tokens_lower.add(school)
            if element.setters.get("isRitual", "").strip().lower() == "true":
                tokens_lower.add("ritual")
        return evaluate_boolean_expr(
            expr,
            lambda term: term.lower() in tokens_lower,
        )

    def find_matching(self, element_type: str, supports_expr: str = "") -> list[Element]:
        candidates = self.of_type(element_type)
        if not supports_expr:
            return candidates
        return [el for el in candidates if self.match_supports(el, supports_expr)]

    def search(
        self,
        query: str = "",
        element_types: Optional[Iterable[str]] = None,
    ) -> list[Element]:
        q = query.strip().lower()
        if element_types is not None:
            pool: list[Element] = []
            for t in element_types:
                pool.extend(self.by_type.get(t, []))
        else:
            pool = list(self.by_id.values())

        if not q:
            return sorted(pool, key=lambda e: (e.name.lower(), e.id))
        return sorted(
            [
                el
                for el in pool
                if q in el.name.lower()
                or q in el.id.lower()
                or q in el.source.lower()
                or any(q in s.lower() for s in el.supports)
            ],
            key=lambda e: (e.name.lower(), e.id),
        )
