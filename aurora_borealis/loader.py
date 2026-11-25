"""Load and index Aurora Builder XML element files."""

from __future__ import annotations

import functools
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from lxml import etree

from .models import (
    DuplicateEntry,
    Element,
    GrantRule,
    MulticlassInfo,
    SelectRule,
    SpellcastingInfo,
    StatRule,
)

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


@functools.lru_cache(maxsize=1024)
def _compile_boolean_expr(expr: str) -> Any:
    """Compile an Aurora boolean expression into a cached AST tuple."""
    tokens = [t.strip() for t in _EXPR_TOKEN_RE.findall(expr) if t.strip()]
    if not tokens:
        return ("CONST", True)

    pos = 0

    def peek() -> Optional[str]:
        return tokens[pos] if pos < len(tokens) else None

    def consume() -> str:
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        return tok

    def parse_or() -> Any:
        node = parse_and()
        while peek() == "||":
            consume()
            rhs = parse_and()
            node = ("OR", node, rhs)
        return node

    def parse_and() -> Any:
        node = parse_not()
        while peek() in (",", "&&"):
            consume()
            rhs = parse_not()
            node = ("AND", node, rhs)
        return node

    def parse_not() -> Any:
        if peek() == "!":
            consume()
            return ("NOT", parse_not())
        return parse_primary()

    def parse_primary() -> Any:
        tok = peek()
        if tok is None:
            return ("CONST", True)
        if tok == "(":
            consume()
            node = parse_or()
            if peek() == ")":
                consume()
            return node
        if tok in (")", ",", "&&", "||"):
            return ("CONST", True)
        consume()
        return ("TERM", tok)

    return parse_or()


def _eval_ast(node: Any, predicate: Callable[[str], bool]) -> bool:
    kind = node[0]
    if kind == "CONST":
        return node[1]
    if kind == "TERM":
        return predicate(node[1])
    if kind == "NOT":
        return not _eval_ast(node[1], predicate)
    if kind == "AND":
        return _eval_ast(node[1], predicate) and _eval_ast(node[2], predicate)
    if kind == "OR":
        return _eval_ast(node[1], predicate) or _eval_ast(node[2], predicate)
    return True


def evaluate_boolean_expr(expr: str, predicate: Callable[[str], bool]) -> bool:
    """Evaluate Aurora boolean expressions supporting ',', '&&', '||', '!', and '()'."""
    expr = (expr or "").strip()
    if not expr:
        return True
    ast = _compile_boolean_expr(expr)
    return _eval_ast(ast, predicate)


class ContentRepository:
    """Repository of parsed Aurora <element> definitions."""

    def __init__(self) -> None:
        self.by_id: dict[str, Element] = {}
        self.by_type: dict[str, list[Element]] = defaultdict(list)
        self.loaded_dirs: list[Path] = []
        self.file_count: int = 0
        self.duplicates: list[DuplicateEntry] = []
        self._by_type_name: dict[tuple[str, str], Element] = {}
        self._type_by_id: dict[str, dict[str, Element]] = defaultdict(dict)
        self._search_blobs: dict[str, str] = {}
        self._support_tokens: dict[str, frozenset[str]] = {}
        self._match_cache: dict[tuple[str, str], tuple[Element, ...]] = {}
        self._pending_appends: list[tuple[str, list[str], list[GrantRule], list[SelectRule], list[StatRule]]] = []

    def clear(self) -> None:
        self.by_id.clear()
        self.by_type.clear()
        self.loaded_dirs.clear()
        self.file_count = 0
        self.duplicates.clear()
        self._by_type_name.clear()
        self._type_by_id.clear()
        self._search_blobs.clear()
        self._support_tokens.clear()
        self._match_cache.clear()
        self._pending_appends.clear()

    def duplicate_summary(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for d in self.duplicates:
            counts[d.element_type] += 1
        return dict(sorted(counts.items()))

    def _sync_type_lists_and_caches(self, affected_types: Optional[Iterable[str]] = None) -> None:
        types_to_sync = affected_types if affected_types is not None else list(self._type_by_id.keys())
        for etype in types_to_sync:
            elems = list(self._type_by_id.get(etype, {}).values())
            elems.sort(key=lambda e: (e.name.lower(), e.id))
            self.by_type[etype] = elems
        self._match_cache.clear()

    def _index_element_metadata(self, el: Element) -> None:
        self._search_blobs[el.id] = (
            f"{el.name}\n{el.id}\n{el.source}\n{' '.join(el.supports)}".lower()
        )
        tokens = {
            el.id.lower(),
            el.name.lower(),
            el.type.lower(),
            el.source.lower(),
            *(s.lower() for s in el.supports),
        }
        if el.type == "Spell":
            lvl = el.setters.get("level", "").strip().lower()
            if lvl:
                tokens.add(lvl)
            school = el.setters.get("school", "").strip().lower()
            if school:
                tokens.add(school)
            if el.setters.get("isRitual", "").strip().lower() == "true":
                tokens.add("ritual")
        self._support_tokens[el.id] = frozenset(tokens)

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
        self._apply_pending_appends()
        self._sync_type_lists_and_caches()
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
        for app_node in root.findall("append"):
            target_id = (app_node.get("id") or "").strip()
            if not target_id:
                continue
            sup_txt = (app_node.findtext("supports") or "").strip()
            extra_sups = [s.strip() for s in sup_txt.split(",") if s.strip()]
            g_rules, s_rules, st_rules = self._parse_rules(app_node.find("rules"))
            if extra_sups or g_rules or s_rules or st_rules:
                self._pending_appends.append((target_id, extra_sups, g_rules, s_rules, st_rules))
                added += 1

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
                    self._type_by_id[old.type].pop(old.id, None)
                    self.by_id[el.id] = el
                    self._index_element_metadata(el)
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
            self._index_element_metadata(el)
            self._register_in_type_list(el, path)
            added += 1
        return added

    def _apply_pending_appends(self) -> None:
        """Apply Aurora <append id='...'> extensions to loaded elements."""
        if not self._pending_appends:
            return
        remaining: list[tuple[str, list[str], list[GrantRule], list[SelectRule], list[StatRule]]] = []
        for target_id, extra_sups, g_rules, s_rules, st_rules in self._pending_appends:
            el = self.by_id.get(target_id)
            if el is None:
                remaining.append((target_id, extra_sups, g_rules, s_rules, st_rules))
                continue
            existing_sups = {s.lower() for s in el.supports}
            for sup in extra_sups:
                if sup.lower() not in existing_sups:
                    el.supports.append(sup)
                    existing_sups.add(sup.lower())
            el.grant_rules.extend(g_rules)
            el.select_rules.extend(s_rules)
            el.stat_rules.extend(st_rules)
            self._index_element_metadata(el)
        self._pending_appends = remaining

    def _register_in_type_list(self, el: Element, path: Path) -> None:
        if el.type not in _CHARACTER_FACING_TYPES:
            self._type_by_id[el.type][el.id] = el
            return

        tn_key = (el.type.lower(), el.name.lower())
        existing = self._by_type_name.get(tn_key)
        if existing is None or existing.id == el.id:
            if existing is not None:
                self._type_by_id[existing.type].pop(existing.id, None)
            self._type_by_id[el.type][el.id] = el
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
            self._type_by_id[existing.type].pop(existing.id, None)
            self._type_by_id[el.type][el.id] = el
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

    @staticmethod
    def _parse_rules(
        rules_node: Optional[etree._Element],
    ) -> tuple[list[GrantRule], list[SelectRule], list[StatRule]]:
        grant_rules: list[GrantRule] = []
        select_rules: list[SelectRule] = []
        stat_rules: list[StatRule] = []

        if rules_node is None:
            return grant_rules, select_rules, stat_rules

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
        return grant_rules, select_rules, stat_rules

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

        grant_rules, select_rules, stat_rules = self._parse_rules(node.find("rules"))

        spellcasting: Optional[SpellcastingInfo] = None
        sc_node = node.find("spellcasting")
        if sc_node is not None:
            list_node = sc_node.find("list")
            spell_list = (list_node.text or "").strip() if list_node is not None else ""
            extended = [
                (ex.text or "").strip()
                for ex in sc_node.findall("extend")
                if (ex.text or "").strip()
            ]
            spellcasting = SpellcastingInfo(
                name=(sc_node.get("name") or name).strip(),
                ability=(sc_node.get("ability") or "Intelligence").strip(),
                prepare=(sc_node.get("prepare") or "").lower() == "true",
                allow_rituals=(sc_node.get("allowRituals") or "").lower() == "true",
                extend=(sc_node.get("extend") or "").lower() == "true",
                spell_list=spell_list or (sc_node.get("name") or "").strip(),
                extended=extended,
            )

        multiclass: Optional[MulticlassInfo] = None
        mc_node = node.find("multiclass")
        if mc_node is not None:
            mc_grants, mc_selects, mc_stats = self._parse_rules(mc_node.find("rules"))
            multiclass = MulticlassInfo(
                id=(mc_node.get("id") or "").strip(),
                prerequisite=(mc_node.findtext("prerequisite") or "").strip(),
                requirements=(mc_node.findtext("requirements") or "").strip(),
                grant_rules=mc_grants,
                select_rules=mc_selects,
                stat_rules=mc_stats,
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
            multiclass=multiclass,
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

        tokens_lower = self._support_tokens.get(element.id)
        if tokens_lower is None:
            self._index_element_metadata(element)
            tokens_lower = self._support_tokens[element.id]
        return evaluate_boolean_expr(
            expr,
            lambda term: term.lower() in tokens_lower,
        )

    def find_matching(self, element_type: str, supports_expr: str = "") -> list[Element]:
        key = (element_type, (supports_expr or "").strip())
        cached = self._match_cache.get(key)
        if cached is not None:
            return list(cached)
        candidates = self.by_type.get(element_type, [])
        if not key[1]:
            res = tuple(candidates)
        else:
            res = tuple(el for el in candidates if self.match_supports(el, key[1]))
        if len(self._match_cache) > 2048:
            self._match_cache.clear()
        self._match_cache[key] = res
        return list(res)

    def available_spell_classes(self) -> list[str]:
        """Return sorted D&D spellcasting class names present across standard + loaded spells."""
        base = {
            "Artificer",
            "Bard",
            "Cleric",
            "Druid",
            "Paladin",
            "Ranger",
            "Sorcerer",
            "Warlock",
            "Wizard",
        }
        known_lower = {b.lower(): b for b in base}
        for sp in self.by_type.get("Spell", []):
            for tok in sp.supports:
                tl = tok.strip().lower()
                if tl in known_lower:
                    base.add(known_lower[tl])
        return sorted(base)

    def search(
        self,
        query: str = "",
        element_types: Optional[Iterable[str]] = None,
    ) -> list[Element]:
        q = query.strip().lower()
        if element_types is not None:
            pool: list[Element] = []
            type_list = list(element_types)
            for t in type_list:
                pool.extend(self.by_type.get(t, []))
            if not q and len(type_list) == 1:
                return list(pool)
        else:
            pool = list(self.by_id.values())

        if not q:
            return sorted(pool, key=lambda e: (e.name.lower(), e.id))

        blobs = self._search_blobs
        out: list[Element] = []
        for el in pool:
            blob = blobs.get(el.id)
            if blob is None:
                self._index_element_metadata(el)
                blob = self._search_blobs[el.id]
            if q in blob:
                out.append(el)
        out.sort(key=lambda e: (e.name.lower(), e.id))
        return out
