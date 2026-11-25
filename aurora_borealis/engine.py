"""Aurora XML Rules Engine for D&D 5e / 5.5e characters (with multiclassing & rolled HP)."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Optional

from .loader import ContentRepository, evaluate_boolean_expr
from .models import (
    ABILITIES,
    ABILITY_ABBR,
    SKILL_ID_MAP,
    SKILLS,
    ActiveSelection,
    CharacterState,
    ClassSpellcasting,
    ComputedCharacter,
    Element,
    SavingThrowValue,
    SelectRule,
    SkillValue,
    SpellcastingInfo,
    SpellcastingSummary,
    StatRule,
)
from .rules_55e import (
    WEAPON_MASTERY_DESCRIPTIONS,
    check_55e_heavy_weapon_requirement,
    compute_weapon_mastery_limit,
    exhaustion_55e_penalty,
    get_55e_epic_boon_elements,
    get_55e_prepared_spells,
    get_weapon_mastery,
    monk_martial_arts_die_55e,
)

# Standard 5e / 5.5e XP thresholds by character level (1..20)
XP_THRESHOLDS: dict[int, int] = {
    1: 0,
    2: 300,
    3: 900,
    4: 2700,
    5: 6500,
    6: 14000,
    7: 23000,
    8: 34000,
    9: 48000,
    10: 64000,
    11: 85000,
    12: 100000,
    13: 120000,
    14: 140000,
    15: 165000,
    16: 195000,
    17: 225000,
    18: 265000,
    19: 305000,
    20: 355000,
}


def xp_for_level(level: int) -> int:
    """Return the minimum XP threshold for a D&D level (1..20)."""
    clamped = max(1, min(20, int(level or 1)))
    return XP_THRESHOLDS[clamped]


def level_for_xp(xp: int) -> int:
    """Return the character level (1..20) corresponding to total XP."""
    xp_val = max(0, int(xp or 0))
    lvl = 1
    for candidate_lvl, threshold in XP_THRESHOLDS.items():
        if xp_val >= threshold:
            lvl = candidate_lvl
    return lvl


def sync_xp_to_level(state: CharacterState) -> None:
    """Keep state.xp inside the active level's XP bracket [T(lvl), T(lvl+1)-1]."""
    lvl = max(1, min(20, int(state.level or 1)))
    cur_xp = max(0, int(state.xp or 0))
    low = XP_THRESHOLDS[lvl]
    high = XP_THRESHOLDS.get(lvl + 1)
    if cur_xp < low or (high is not None and cur_xp >= high):
        state.xp = low


SYNTHETIC_ASI_PREFIX = "ID_AURORA_ASI_"


def is_synthetic_asi_id(eid: str) -> bool:
    """Return True if eid identifies a built-in synthetic ASI option."""
    return bool(eid and eid.startswith(SYNTHETIC_ASI_PREFIX))


def effective_selection_slot_count(
    active_sel: ActiveSelection,
    state: CharacterState,
    computed: ComputedCharacter,
) -> int:
    """Return how many picks an active selection can actually offer (capped by available options)."""
    rule_num = max(0, int(active_sel.rule.number or 0))
    if rule_num == 0:
        return 0
    if any(is_synthetic_asi_id(opt_id) for opt_id, _ in active_sel.options):
        return rule_num
    distinct_opts = {opt_id for opt_id, _ in active_sel.options if opt_id}
    if active_sel.rule.type == "List":
        return min(rule_num, len(distinct_opts))
    chosen = state.selections.get(active_sel.key, [])
    chosen_set = {v for v in chosen[:rule_num] if v}
    all_granted_ids = {el.id for el in computed.granted_elements}
    other_sel_ids = {
        sv
        for skey, svals in state.selections.items()
        if skey != active_sel.key
        for sv in svals
        if sv
    }
    blocked = (all_granted_ids - chosen_set) | other_sel_ids
    selectable = {opt_id for opt_id in distinct_opts if opt_id not in blocked}
    return min(rule_num, len(selectable))


def selection_filled_count(
    active_sel: ActiveSelection,
    state: CharacterState,
    effective_count: int,
) -> int:
    """Return the number of filled selections capped by effective_count."""
    if effective_count <= 0:
        return 0
    chosen = state.selections.get(active_sel.key, [])
    return min(
        effective_count,
        sum(1 for v in chosen[: max(effective_count, int(active_sel.rule.number or 0))] if v),
    )


def is_asi_select_rule(sel: SelectRule) -> bool:
    """Return True if sel represents an Ability Score Improvement selection."""
    stype = (sel.type or "").strip().lower()
    sname = (sel.name or "").strip().lower()
    ssupp = (sel.supports or "").strip().lower()
    return (
        stype == "ability score improvement"
        or "ability score improvement" in sname
        or "improvement option" in ssupp
    )


def _build_synthetic_asi_catalog() -> tuple[dict[str, Element], list[Element], list[Element]]:
    plus1_list: list[Element] = []
    plus2_list: list[Element] = []
    pair_list: list[Element] = []

    for ab in ABILITIES:
        ab_title = ab.title()
        plus1_list.append(
            Element(
                id=f"ID_AURORA_ASI_PLUS1_{ab.upper()}",
                name=f"Ability Score Increase: {ab_title} +1",
                type="Ability Score Improvement",
                source="Core Rules (Built-in)",
                description_html=(
                    f"<p>Increase your <b>{ab_title}</b> score by <b>1</b> "
                    "(up to 20, or higher with the ASI cap rule override).</p>"
                ),
                stat_rules=[StatRule(name=ab, value="1")],
            )
        )
        plus2_list.append(
            Element(
                id=f"ID_AURORA_ASI_PLUS2_{ab.upper()}",
                name=f"Ability Score Improvement: {ab_title} +2",
                type="Ability Score Improvement",
                source="Core Rules (Built-in)",
                description_html=(
                    f"<p>Increase your <b>{ab_title}</b> score by <b>2</b> "
                    "(up to 20, or higher with the ASI cap rule override).</p>"
                ),
                stat_rules=[StatRule(name=ab, value="2")],
            )
        )

    for i in range(len(ABILITIES)):
        for j in range(i + 1, len(ABILITIES)):
            ab_a = ABILITIES[i]
            ab_b = ABILITIES[j]
            pair_list.append(
                Element(
                    id=f"ID_AURORA_ASI_PLUS1_{ab_a.upper()}_{ab_b.upper()}",
                    name=f"Ability Score Improvement: {ab_a.title()} +1, {ab_b.title()} +1",
                    type="Ability Score Improvement",
                    source="Core Rules (Built-in)",
                    description_html=(
                        f"<p>Increase your <b>{ab_a.title()}</b> and <b>{ab_b.title()}</b> scores "
                        "by <b>1</b> each (up to 20, or higher with the ASI cap rule override).</p>"
                    ),
                    stat_rules=[StatRule(name=ab_a, value="1"), StatRule(name=ab_b, value="1")],
                )
            )

    full_list = [*plus2_list, *pair_list]
    by_id = {e.id: e for e in [*plus1_list, *full_list]}
    return by_id, plus1_list, full_list


_SYNTHETIC_ASI_BY_ID, _SYNTHETIC_ASI_PLUS1, _SYNTHETIC_ASI_FULL = _build_synthetic_asi_catalog()


def get_synthetic_asi_element(eid: str) -> Optional[Element]:
    """Return the built-in synthetic ASI Element for eid, or None."""
    return _SYNTHETIC_ASI_BY_ID.get(eid)


def _synthetic_asi_options(
    repo: ContentRepository, number: int, supports_expr: str = ""
) -> list[tuple[str, str]]:
    if number >= 2:
        return [(e.id, e.name) for e in _SYNTHETIC_ASI_PLUS1]
    opts: list[tuple[str, str]] = [(e.id, e.name) for e in _SYNTHETIC_ASI_FULL]
    if "!feat" not in (supports_expr or "").lower():
        for f in repo.of_type("Feat"):
            opts.append((f.id, f"Feat: {f.name}"))
    return opts


def _class_asi_levels(class_el: Optional[Element]) -> tuple[int, ...]:
    if class_el is not None:
        cname = class_el.name.lower()
        if "fighter" in cname:
            return (4, 6, 8, 12, 14, 16, 19)
        if "rogue" in cname:
            return (4, 8, 10, 12, 16, 19)
    return (4, 8, 12, 16, 19)


# Standard 5e full-caster spell slot table (levels 1..20 -> slot level 1..9)
FULL_CASTER_SLOTS: dict[int, dict[int, int]] = {
    1: {1: 2},
    2: {1: 3},
    3: {1: 4, 2: 2},
    4: {1: 4, 2: 3},
    5: {1: 4, 2: 3, 3: 2},
    6: {1: 4, 2: 3, 3: 3},
    7: {1: 4, 2: 3, 3: 3, 4: 1},
    8: {1: 4, 2: 3, 3: 3, 4: 2},
    9: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    10: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
    11: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    12: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    13: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    14: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    15: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    16: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1, 9: 1},
    18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 1, 7: 1, 8: 1, 9: 1},
    19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 1, 8: 1, 9: 1},
    20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1},
}

HALF_CASTER_SLOTS: dict[int, dict[int, int]] = {
    lvl: dict(FULL_CASTER_SLOTS.get(math.ceil(lvl / 2), {})) if lvl >= 2 else {}
    for lvl in range(1, 21)
}

HALF_CASTER_UP_SLOTS: dict[int, dict[int, int]] = {
    lvl: dict(FULL_CASTER_SLOTS.get(math.ceil(lvl / 2), {}))
    for lvl in range(1, 21)
}

THIRD_CASTER_SLOTS: dict[int, dict[int, int]] = {
    lvl: dict(FULL_CASTER_SLOTS.get(math.ceil(lvl / 3), {})) if lvl >= 3 else {}
    for lvl in range(1, 21)
}

THIRD_CASTER_KNOWN: dict[int, int] = {
    1: 0, 2: 0, 3: 3, 4: 4, 5: 4, 6: 4, 7: 5, 8: 6, 9: 6, 10: 7,
    11: 8, 12: 8, 13: 9, 14: 10, 15: 10, 16: 11, 17: 11, 18: 11, 19: 12, 20: 13,
}

WARLOCK_SLOTS: dict[int, dict[int, int]] = {
    1: {1: 1},
    2: {1: 2},
    3: {2: 2},
    4: {2: 2},
    5: {3: 2},
    6: {3: 2},
    7: {4: 2},
    8: {4: 2},
    9: {5: 2},
    10: {5: 2},
    11: {5: 3},
    12: {5: 3},
    13: {5: 3},
    14: {5: 3},
    15: {5: 3},
    16: {5: 3},
    17: {5: 4},
    18: {5: 4},
    19: {5: 4},
    20: {5: 4},
}

# List of OR-alternatives; each alternative is a list of AND (ability, min_score) pairs.
MULTICLASS_PREREQUISITES: dict[str, list[list[tuple[str, int]]]] = {
    "artificer": [[("intelligence", 13)]],
    "barbarian": [[("strength", 13)]],
    "bard": [[("charisma", 13)]],
    "cleric": [[("wisdom", 13)]],
    "druid": [[("wisdom", 13)]],
    "fighter": [[("strength", 13)], [("dexterity", 13)]],
    "monk": [[("dexterity", 13), ("wisdom", 13)]],
    "paladin": [[("strength", 13), ("charisma", 13)]],
    "ranger": [[("dexterity", 13), ("wisdom", 13)]],
    "rogue": [[("dexterity", 13)]],
    "sorcerer": [[("charisma", 13)]],
    "warlock": [[("charisma", 13)]],
    "wizard": [[("intelligence", 13)]],
}

MULTICLASS_PROFICIENCY_FALLBACK: dict[str, list[str]] = {
    "artificer": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS"],
    "barbarian": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS"],
    "bard": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR"],
    "cleric": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS"],
    "druid": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS"],
    "fighter": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS"],
    "monk": ["ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS"],
    "paladin": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS"],
    "ranger": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", "ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS", "ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS"],
    "rogue": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR"],
    "sorcerer": [],
    "warlock": ["ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", "ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS"],
    "wizard": [],
}

_KNOWN_CASTER_CLASS_NAMES = {
    "artificer",
    "bard",
    "cleric",
    "druid",
    "paladin",
    "ranger",
    "sorcerer",
    "warlock",
    "wizard",
}


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def parse_weight_lb(el: Optional[Element]) -> float:
    if el is None:
        return 0.0
    raw = el.setters.get("weight_lb") or el.setters.get("weight") or "0"
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw)
    return float(m.group(1)) if m else 0.0


def parse_hit_die(class_el: Optional[Element]) -> int:
    if class_el is None:
        return 8
    hd_str = class_el.setters.get("hd", "d8")
    m_hd = re.search(r"d(\d+)", hd_str.lower())
    return int(m_hd.group(1)) if m_hd else 8


def class_display_summary(state: CharacterState, repo: ContentRepository) -> str:
    """Return 'Wizard 5' for single-class or 'Fighter 3 / Wizard 2' for multiclass."""
    classes = state.normalized_classes()
    if not classes:
        return ""
    parts: list[str] = []
    for cl in classes:
        el = repo.get(cl.class_id)
        cname = el.name if el else cl.class_id
        parts.append(f"{cname} {cl.level}")
    return " / ".join(parts)


def _check_single_class_prereq(
    class_el: Element,
    ability_totals: dict[str, int],
) -> tuple[bool, str]:
    cname = class_el.name.strip()
    key = cname.lower()
    alts = MULTICLASS_PREREQUISITES.get(key)
    if alts is None:
        for known_key, known_alts in MULTICLASS_PREREQUISITES.items():
            if known_key in key:
                alts = known_alts
                break
    if alts:
        for group in alts:
            if all(ability_totals.get(ab, 10) >= min_val for ab, min_val in group):
                return True, ""
        req_text = " or ".join(
            " & ".join(f"{ABILITY_ABBR[ab]} {val}+" for ab, val in group)
            for group in alts
        )
        return False, f"{cname} requires {req_text}"

    if class_el.multiclass and class_el.multiclass.requirements:
        req_expr = class_el.multiclass.requirements
        abbr_to_full = {v.lower(): k for k, v in ABILITY_ABBR.items()}

        def pred(term: str) -> bool:
            tl = term.strip().lower()
            if tl.startswith("[") and tl.endswith("]") and ":" in tl:
                lhs, rhs = tl[1:-1].split(":", 1)
                if lhs in abbr_to_full:
                    try:
                        return ability_totals.get(abbr_to_full[lhs], 10) >= int(rhs)
                    except ValueError:
                        return False
            return True

        if not evaluate_boolean_expr(req_expr, pred):
            hint = class_el.multiclass.prerequisite or req_expr
            return False, f"{cname} requires {hint}"

    return True, ""


def check_multiclass_prerequisites(
    state: CharacterState,
    computed: ComputedCharacter,
    target_class_el: Element,
    repo: ContentRepository,
) -> tuple[bool, str]:
    """Verify PHB multiclassing prerequisites for both current classes and target class."""
    if state.has_override("override_multiclass_prereqs"):
        return True, "Allowed (Manual Override)"
    problems: list[str] = []
    seen_ids: set[str] = set()
    for cl in state.normalized_classes():
        seen_ids.add(cl.class_id)
        cel = repo.get(cl.class_id)
        if cel is not None:
            ok, msg = _check_single_class_prereq(cel, computed.ability_totals)
            if not ok and msg:
                problems.append(msg)
    if target_class_el.id not in seen_ids:
        ok, msg = _check_single_class_prereq(target_class_el, computed.ability_totals)
        if not ok and msg:
            problems.append(msg)
    if problems:
        return False, "; ".join(problems)
    return True, "Prerequisites met"


def is_spell_ritual(spell: Optional[Element]) -> bool:
    if spell is None:
        return False
    if spell.setters.get("isRitual", "").strip().lower() == "true":
        return True
    return any("ritual" in s.lower() for s in spell.supports)


def is_spell_concentration(spell: Optional[Element]) -> bool:
    if spell is None:
        return False
    if spell.setters.get("isConcentration", "").strip().lower() == "true":
        return True
    if "concentration" in spell.setters.get("duration", "").lower():
        return True
    return any("concentration" in s.lower() for s in spell.supports)


def spell_school(spell: Optional[Element]) -> str:
    if spell is None:
        return ""
    s = spell.setters.get("school", "").strip()
    if s:
        return s.capitalize()
    for known in (
        "Abjuration",
        "Conjuration",
        "Divination",
        "Enchantment",
        "Evocation",
        "Illusion",
        "Necromancy",
        "Transmutation",
    ):
        if any(known.lower() == tok.strip().lower() for tok in spell.supports):
            return known
    return ""


def spell_classes(spell: Optional[Element]) -> list[str]:
    if spell is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for tok in spell.supports:
        tl = tok.strip().lower()
        if tl in _KNOWN_CASTER_CLASS_NAMES and tl not in seen:
            seen.add(tl)
            out.append(tl.capitalize())
    return out


def spell_has_class_tags(spell: Element) -> bool:
    sup_tokens = {s.strip().lower() for s in spell.supports if s.strip()}
    return bool(sup_tokens & _KNOWN_CASTER_CLASS_NAMES)


def is_spell_eligible_for_caster(spell: Element, caster: ClassSpellcasting) -> bool:
    """Return True if a spell belongs to this class/subclass's spell list or grants."""
    if (
        spell.id in caster.granted_spell_ids
        or spell.id in caster.always_prepared_spell_ids
        or spell.id in caster.extended_spell_ids
    ):
        return True

    sup_lower = {s.strip().lower() for s in spell.supports if s.strip()}
    allowed_lists: set[str] = set()
    for lst in [caster.spell_list, caster.source_class_name, *caster.extended_spell_lists]:
        clean = (lst or "").strip().lower()
        if clean:
            allowed_lists.add(clean)
            if "(" in clean:
                allowed_lists.add(clean.split("(", 1)[0].strip())

    if sup_lower & allowed_lists:
        return True

    if not spell_has_class_tags(spell):
        return True
    return False


_SIMPLE_WEAPONS: frozenset[str] = frozenset({
    "club", "dagger", "greatclub", "handaxe", "javelin", "light hammer",
    "mace", "quarterstaff", "sickle", "spear", "light crossbow", "dart",
    "shortbow", "sling",
})

_MARTIAL_WEAPONS: frozenset[str] = frozenset({
    "battleaxe", "flail", "glaive", "greataxe", "greatsword", "halberd",
    "lance", "longsword", "maul", "morningstar", "pike", "rapier",
    "scimitar", "shortsword", "trident", "war pick", "warhammer", "whip",
    "blowgun", "hand crossbow", "heavy crossbow", "longbow", "net",
})

_FIREARM_WEAPONS: frozenset[str] = frozenset({
    "pistol", "musket", "blunderbuss", "pepperbox", "bad news", "palm pistol",
    "hunting rifle", "automatic rifle", "revolver", "shotgun",
    "laser pistol", "antimatter rifle", "laser rifle",
})

_ARMOR_KIND_BY_NAME: dict[str, str] = {
    "padded": "light",
    "padded armor": "light",
    "leather": "light",
    "leather armor": "light",
    "studded leather": "light",
    "studded leather armor": "light",
    "hide": "medium",
    "hide armor": "medium",
    "chain shirt": "medium",
    "scale mail": "medium",
    "breastplate": "medium",
    "half plate": "medium",
    "half plate armor": "medium",
    "spiked armor": "medium",
    "ring mail": "heavy",
    "chain mail": "heavy",
    "splint": "heavy",
    "splint armor": "heavy",
    "plate": "heavy",
    "plate armor": "heavy",
    "shield": "shield",
    "buckler": "shield",
}

_ALL_WEAPON_NAMES_SORTED: tuple[str, ...] = tuple(
    sorted(_SIMPLE_WEAPONS | _MARTIAL_WEAPONS | _FIREARM_WEAPONS, key=len, reverse=True)
)
_ALL_ARMOR_NAMES_SORTED: tuple[str, ...] = tuple(
    sorted(_ARMOR_KIND_BY_NAME.keys(), key=len, reverse=True)
)


def _normalize_prof_variants(raw: str) -> set[str]:
    """Normalize a proficiency label into lowercase base and singular/plural variants."""
    s = (raw or "").strip().lower()
    if not s:
        return set()
    for prefix in (
        "weapon proficiency (",
        "armor proficiency (",
        "tool proficiency (",
        "musical instrument (",
        "gaming set (",
        "proficiency (",
    ):
        if s.startswith(prefix) and s.endswith(")"):
            s = s[len(prefix) : -1].strip()
            break
    s = re.sub(r"\s+", " ", s).strip()
    variants = {s}
    if s.endswith("staves"):
        variants.add(s[:-6] + "staff")
    elif s.endswith("ves") and len(s) > 4:
        variants.add(s[:-3] + "f")
        variants.add(s[:-3] + "fe")
    elif s.endswith("ies") and len(s) > 4:
        variants.add(s[:-3] + "y")
    elif s.endswith("s") and not s.endswith("ss") and len(s) > 3:
        variants.add(s[:-1])
    if s.endswith("staff"):
        variants.add(s[:-5] + "staves")
    elif not s.endswith("s"):
        variants.add(s + "s")
    if s.endswith(" armor"):
        variants.add(s[:-6].strip())
    return {v for v in variants if v}


def is_equipment_proficient(
    el: Optional[Element],
    computed: Optional[ComputedCharacter],
    repo: Optional[ContentRepository] = None,
) -> Optional[bool]:
    """Return True if proficient, False if lacking required proficiency, or None if no proficiency is needed."""
    if el is None or computed is None:
        return None

    prof_ids: set[str] = set()
    prof_names: set[str] = set()
    for granted in computed.granted_elements:
        if granted.type == "Proficiency":
            prof_ids.add(granted.id.strip().lower())
            prof_names.update(_normalize_prof_variants(granted.name))
    for p in computed.proficiencies:
        prof_names.update(_normalize_prof_variants(p))

    explicit_prof_id = (el.setters.get("proficiency") or "").strip().lower()
    if explicit_prof_id and explicit_prof_id in prof_ids:
        return True

    name_l = el.name.strip().lower()
    cat_l = (el.setters.get("category") or "").strip().lower()
    type_setter_l = (el.setters.get("type") or "").strip().lower()
    slot_l = (el.setters.get("slot") or "").strip().lower()
    armor_setter_l = (el.setters.get("armor") or "").strip().lower()
    supports_l = {s.strip().lower() for s in el.supports if s.strip()}
    blob = " ".join([name_l, cat_l, type_setter_l, slot_l, armor_setter_l, *supports_l])

    # 1. Armor & Shields
    armor_kind = ""
    if armor_setter_l in ("light", "medium", "heavy", "shield"):
        armor_kind = armor_setter_l
    elif el.type == "Armor":
        if "shield" in blob or slot_l == "shield":
            armor_kind = "shield"
        elif "light" in supports_l or "light armor" in blob:
            armor_kind = "light"
        elif "medium" in supports_l or "medium armor" in blob:
            armor_kind = "medium"
        elif "heavy" in supports_l or "heavy armor" in blob:
            armor_kind = "heavy"
    if not armor_kind and (el.type == "Armor" or el.type == "Magic Item"):
        for aname in _ALL_ARMOR_NAMES_SORTED:
            if re.search(rf"(?<![a-z0-9]){re.escape(aname)}(?![a-z0-9])", name_l):
                armor_kind = _ARMOR_KIND_BY_NAME[aname]
                break

    if armor_kind or el.type == "Armor":
        item_variants = _normalize_prof_variants(name_l)
        if item_variants & prof_names:
            return True
        if armor_kind == "shield":
            return bool({"shield", "shields"} & prof_names) or "id_proficiency_armor_proficiency_shields" in prof_ids
        if armor_kind in ("light", "medium", "heavy"):
            if {"all armor", "armor"} & prof_names:
                return True
            if {armor_kind, f"{armor_kind} armor"} & prof_names:
                return True
            if f"id_proficiency_armor_proficiency_{armor_kind}_armor" in prof_ids:
                return True
            return False
        return False

    # 2. Weapons (including Magic Weapons)
    matched_weapon = ""
    for wname in _ALL_WEAPON_NAMES_SORTED:
        if re.search(rf"(?<![a-z0-9]){re.escape(wname)}(?![a-z0-9])", name_l):
            matched_weapon = wname
            break
    is_weapon = (
        el.type == "Weapon"
        or bool(el.setters.get("damage"))
        or "weapon" in cat_l
        or "weapon" in supports_l
        or (el.type == "Magic Item" and bool(matched_weapon))
    )
    if is_weapon:
        if _normalize_prof_variants(name_l) & prof_names:
            return True
        if matched_weapon and (_normalize_prof_variants(matched_weapon) & prof_names):
            return True
        if explicit_prof_id and repo is not None:
            prof_el = repo.get(el.setters.get("proficiency", ""))
            if prof_el is not None and (_normalize_prof_variants(prof_el.name) & prof_names):
                return True

        is_simple = (
            "simple" in supports_l
            or "simple" in cat_l
            or "simple" in type_setter_l
            or matched_weapon in _SIMPLE_WEAPONS
        )
        is_martial = (
            "martial" in supports_l
            or "martial" in cat_l
            or "martial" in type_setter_l
            or matched_weapon in _MARTIAL_WEAPONS
        )
        is_firearm = (
            "firearm" in blob
            or matched_weapon in _FIREARM_WEAPONS
        )
        is_melee = "melee" in blob
        is_ranged = "ranged" in blob

        if is_simple and (
            {"simple", "simple weapon", "simple weapons", "all weapons"} & prof_names
            or "id_proficiency_weapon_proficiency_simple_weapons" in prof_ids
            or (is_melee and "simple melee weapons" in prof_names)
            or (is_ranged and "simple ranged weapons" in prof_names)
        ):
            return True
        if is_martial and (
            {"martial", "martial weapon", "martial weapons", "all weapons"} & prof_names
            or "id_proficiency_weapon_proficiency_martial_weapons" in prof_ids
            or (is_melee and "martial melee weapons" in prof_names)
            or (is_ranged and "martial ranged weapons" in prof_names)
        ):
            return True
        if is_firearm and ({"firearm", "firearms"} & prof_names):
            return True
        return False

    # 3. Tools, Kits, Musical Instruments, Gaming Sets
    tool_keywords = (
        "tool",
        "artisan",
        "kit",
        "instrument",
        "gaming set",
        "thieves' tools",
        "thieves tools",
        "navigator",
        "herbalism",
        "disguise",
        "forgery",
        "poisoner",
    )
    is_tool = (
        el.type in ("Item", "Magic Item")
        and any(kw in blob for kw in tool_keywords)
        and "scroll" not in blob
        and "potion" not in blob
    )
    if is_tool:
        if _normalize_prof_variants(name_l) & prof_names:
            return True
        if "artisan" in blob and ({"artisan's tools", "artisans tools", "artisan tools"} & prof_names):
            return True
        if "instrument" in blob and ({"musical instrument", "musical instruments"} & prof_names):
            return True
        if "gaming" in blob and ({"gaming set", "gaming sets"} & prof_names):
            return True
        return False

    return None


def is_spell_castable_for_character(
    spell: Element,
    computed: Optional[ComputedCharacter],
    caster: Optional[ClassSpellcasting] = None,
) -> bool:
    """Return True if the character can currently cast this spell (granted or on list within max slot level)."""
    if computed is None:
        return False
    if any(e.id == spell.id for e in computed.granted_elements):
        return True
    sc = computed.spellcasting
    if sc is None:
        return False
    if spell.id in sc.granted_spell_ids or spell.id in sc.always_prepared_spell_ids:
        return True
    if not sc.casters:
        return False

    lvl_raw = str(spell.setters.get("level", "0")).strip()
    lvl = int(lvl_raw) if lvl_raw.isdigit() else 0
    target_casters = [caster] if caster is not None else sc.casters
    for c in target_casters:
        if not is_spell_eligible_for_caster(spell, c):
            continue
        if lvl == 0:
            if c.max_cantrips > 0 or spell.id in c.extended_spell_ids or spell.id in c.granted_spell_ids:
                return True
        elif lvl <= c.max_spell_level:
            return True
    return False


class RulesEngine:
    """Evaluates CharacterState against ContentRepository."""

    def __init__(self, repo: ContentRepository) -> None:
        self.repo = repo

    @staticmethod
    def selection_key(source_id: str, rule_type: str, rule_name: str, level: int, index: int) -> str:
        return f"{source_id}::{rule_type}::{rule_name}::{level}::{index}"

    def _equipment_tags(self, state: CharacterState) -> set[str]:
        tags: set[str] = set()
        equipped_armor_types: set[str] = set()
        has_shield = False

        for item in state.inventory:
            if not item.equipped or item.quantity <= 0:
                continue
            el = self.repo.get(item.element_id)
            if el is None:
                continue
            armor_kind = el.setters.get("armor", "").strip().lower()
            slot = el.setters.get("slot", "").strip().lower()
            if armor_kind == "shield" or "shield" in el.name.lower() or slot == "shield":
                has_shield = True
                tags.add("[shield:any]")
                tags.add("[shield:equipped]")
            elif armor_kind in ("light", "medium", "heavy"):
                equipped_armor_types.add(armor_kind)
                tags.add(f"[armor:{armor_kind}]")
                tags.add("[armor:any]")
            if el.type == "Weapon":
                tags.add("[weapon:any]")

        if not equipped_armor_types:
            tags.add("[armor:none]")
        if not has_shield:
            tags.add("[shield:none]")
        return tags

    def _check_requirement(
        self,
        expr: str,
        granted_ids: set[str],
        level: int,
        abilities: dict[str, int],
        equip_tags: set[str],
        class_level_map: Optional[dict[str, int]] = None,
    ) -> bool:
        expr = (expr or "").strip()
        if not expr:
            return True

        abbr_to_full = {v.lower(): k for k, v in ABILITY_ABBR.items()}
        cls_lvls = class_level_map or {}

        def predicate(term: str) -> bool:
            t = term.strip()
            tl = t.lower()
            if tl.startswith("[") and tl.endswith("]"):
                inner = tl[1:-1].strip()
                if tl in equip_tags:
                    return True
                if inner.startswith("level:"):
                    parts = inner.split(":")
                    if len(parts) == 2:
                        try:
                            return level >= int(parts[1])
                        except ValueError:
                            return False
                    if len(parts) == 3:
                        try:
                            return cls_lvls.get(parts[1].strip(), 0) >= int(parts[2])
                        except ValueError:
                            return False
                if ":" in inner:
                    lhs, rhs = inner.split(":", 1)
                    if lhs in abbr_to_full:
                        try:
                            return abilities.get(abbr_to_full[lhs], 10) >= int(rhs)
                        except ValueError:
                            return False
                return tl in equip_tags
            return t in granted_ids

        return evaluate_boolean_expr(expr, predicate)

    def _active_spellcasting_info(
        self,
        elements: list[Element],
        owner_cid: Optional[str] = None,
        element_owners: Optional[dict[str, tuple[str, int, bool]]] = None,
    ) -> Optional[SpellcastingInfo]:
        for el in elements:
            if el.spellcasting is not None and not el.spellcasting.extend:
                if owner_cid and element_owners is not None:
                    own = element_owners.get(el.id)
                    if own is None or own[0] != owner_cid:
                        continue
                return el.spellcasting
        return None

    def _slots_from_elements_or_table(
        self,
        elements: list[Element],
        class_el: Optional[Element],
        caster_name: str,
        level: int,
        stats: Optional[dict[str, float]] = None,
        caster_type: Optional[str] = None,
        ruleset: str = "5e",
    ) -> dict[int, int]:
        slots: dict[int, int] = {}
        prefixes = (
            f"{caster_name.lower()}:spellcasting:slots:",
            f"{caster_name.lower()}:spellcasting:slot:",
        )
        if stats is not None:
            for k, v in stats.items():
                if any(k.startswith(p) for p in prefixes):
                    try:
                        slot_lvl = int(k.split(":")[-1])
                        if 1 <= slot_lvl <= 9 and int(round(v)) > 0:
                            slots[slot_lvl] = int(round(v))
                    except ValueError:
                        pass
        else:
            for el in elements:
                for sr in el.stat_rules:
                    if sr.level > level:
                        continue
                    sname = sr.name.lower()
                    if any(sname.startswith(p) for p in prefixes):
                        try:
                            slot_lvl = int(sname.split(":")[-1])
                            val = int(float(sr.value))
                            if 1 <= slot_lvl <= 9:
                                slots[slot_lvl] = slots.get(slot_lvl, 0) + val
                        except ValueError:
                            pass
            slots = {k: v for k, v in slots.items() if v > 0}

        if not slots:
            ctype = caster_type
            if not ctype:
                cname = (class_el.name if class_el else caster_name).lower()
                if "warlock" in cname:
                    ctype = "pact"
                elif "eldritch knight" in cname or "arcane trickster" in cname:
                    ctype = "third"
                elif "artificer" in cname or (ruleset == "5.5e" and ("paladin" in cname or "ranger" in cname)):
                    ctype = "half_up"
                elif "paladin" in cname or "ranger" in cname:
                    ctype = "half"
                else:
                    ctype = "full"

            if ctype == "pact":
                slots = dict(WARLOCK_SLOTS.get(level, {}))
            elif ctype == "third":
                slots = dict(THIRD_CASTER_SLOTS.get(level, {}))
            elif ctype == "half_up":
                slots = dict(HALF_CASTER_UP_SLOTS.get(level, {}))
            elif ctype == "half":
                slots = dict(HALF_CASTER_SLOTS.get(level, {}))
            else:
                slots = dict(FULL_CASTER_SLOTS.get(level, {}))
        return slots

    def _expand_spell_supports(
        self,
        expr: str,
        elements: list[Element],
        class_el: Optional[Element],
        level: int,
        owner_cid: Optional[str] = None,
        element_owners: Optional[dict[str, tuple[str, int, bool]]] = None,
        ruleset: str = "5e",
    ) -> str:
        if "$(" not in expr:
            return expr
        sc_info = self._active_spellcasting_info(elements, owner_cid=owner_cid, element_owners=element_owners)
        if sc_info is None and owner_cid:
            sc_info = self._active_spellcasting_info(elements)

        spell_lists: list[str] = []
        base_list = sc_info.spell_list if sc_info else (class_el.name if class_el else "")
        if base_list:
            spell_lists.append(base_list)

        for el in elements:
            if el.spellcasting is not None and el.spellcasting.extend:
                if owner_cid and element_owners is not None:
                    own = element_owners.get(el.id)
                    if own is None or own[0] != owner_cid:
                        continue
                for ext in el.spellcasting.extended:
                    if ext and not ext.startswith("ID_") and ext not in spell_lists:
                        spell_lists.append(ext)

        list_expr = "(" + "||".join(spell_lists) + ")" if len(spell_lists) > 1 else (spell_lists[0] if spell_lists else "")
        caster_name = sc_info.name if sc_info else (class_el.name if class_el else "")
        scoped_elements = (
            [el for el in elements if element_owners is None or element_owners.get(el.id, (None,))[0] == owner_cid]
            if owner_cid
            else elements
        )
        slots = self._slots_from_elements_or_table(
            scoped_elements, class_el, caster_name, level, ruleset=ruleset
        )
        slot_levels = sorted(slots.keys())
        slots_expr = "(" + "||".join(str(l) for l in slot_levels) + ")" if slot_levels else "0"

        out = expr.replace("$(spellcasting:list)", list_expr)
        out = out.replace("$(spellcasting:slots)", slots_expr)
        return out

    def _collect_elements(
        self, state: CharacterState, equip_tags: set[str]
    ) -> tuple[
        list[Element],
        set[str],
        list[ActiveSelection],
        dict[str, tuple[str, int, bool]],
        dict[str, tuple[str, str]],
    ]:
        class_entries = state.normalized_classes()
        total_level = (
            sum(c.level for c in class_entries)
            if class_entries
            else max(1, min(20, int(state.level or 1)))
        )

        class_level_by_id: dict[str, int] = {c.class_id: c.level for c in class_entries}
        class_level_by_name: dict[str, int] = {}
        for c in class_entries:
            cel = self.repo.get(c.class_id)
            if cel is not None:
                class_level_by_name[cel.name.lower()] = c.level

        seed_ids: list[str] = []
        for eid in (
            state.race_id,
            state.background_id,
            state.alignment_id,
            state.deity_id,
        ):
            if eid:
                seed_ids.append(eid)

        # Level marker element IDs in Aurora (e.g. ID_INTERNAL_LEVEL_1 .. N)
        granted_ids: set[str] = set()
        for lvl in range(1, total_level + 1):
            granted_ids.add(f"ID_INTERNAL_LEVEL_{lvl}")
            level_el = self.repo.get(f"ID_INTERNAL_LEVEL_{lvl}")
            if level_el and level_el.id not in seed_ids:
                seed_ids.append(level_el.id)

        # Equipped items can also grant rules/stats
        for item in state.inventory:
            if item.equipped and item.quantity > 0 and item.element_id:
                seed_ids.append(item.element_id)

        # Feats chosen via Level-Up Wizard for active class levels
        for key, feat_id in state.level_up_feats.items():
            if not feat_id or "::" not in key:
                continue
            cid, lvl_str = key.split("::", 1)
            try:
                req_lvl = int(lvl_str)
            except ValueError:
                continue
            if class_level_by_id.get(cid, 0) >= req_lvl:
                seed_ids.append(feat_id)

        ordered_elements: list[Element] = []
        seen_elements: set[str] = set()
        # element_id -> (owner_class_id, effective_class_level, is_primary)
        element_owners: dict[str, tuple[str, int, bool]] = {}
        # spell_id -> (owner_class_id, granting_element_type)
        spell_grant_owners: dict[str, tuple[str, str]] = {}

        def add_element(eid: str, owner: Optional[tuple[str, int, bool]] = None) -> None:
            if not eid:
                return
            if eid in seen_elements:
                if owner is not None and eid not in element_owners:
                    element_owners[eid] = owner
                return
            el = self.repo.get(eid)
            if el is not None:
                seen_elements.add(eid)
                granted_ids.add(eid)
                ordered_elements.append(el)
                if owner is not None:
                    element_owners[eid] = owner

        for sid in seed_ids:
            add_element(sid)

        for idx, cl in enumerate(class_entries):
            is_primary = idx == 0
            add_element(cl.class_id, owner=(cl.class_id, cl.level, is_primary))
            if not is_primary:
                granted_ids.add("ID_INTERNAL_GRANT_MULTICLASS")
                cel = self.repo.get(cl.class_id)
                if cel and cel.multiclass and cel.multiclass.id:
                    granted_ids.add(cel.multiclass.id)

        active_selections: list[ActiveSelection] = []
        seen_select_keys: set[str] = set()
        seen_asi_levels: set[tuple[str, int]] = set()

        def add_synthetic_asi(
            cid: str,
            sel_key: str,
            slot_idx: int,
            owner: Optional[tuple[str, int, bool]],
        ) -> bool:
            syn_el = get_synthetic_asi_element(cid)
            if syn_el is None:
                return False
            slot_eid = f"{cid}::{sel_key}::{slot_idx}"
            if slot_eid in seen_elements:
                return False
            seen_elements.add(slot_eid)
            granted_ids.add(slot_eid)
            ordered_elements.append(
                Element(
                    id=slot_eid,
                    name=syn_el.name,
                    type=syn_el.type,
                    source=syn_el.source,
                    description_html=syn_el.description_html,
                    stat_rules=list(syn_el.stat_rules),
                )
            )
            if owner is not None:
                element_owners[slot_eid] = owner
            return True

        def process_rules_for_element(
            source_id: str,
            source_name: str,
            el_type: str,
            grant_rules,
            select_rules,
            eff_level: int,
            owner_tuple: Optional[tuple[str, int, bool]],
            skip_primary_proficiencies: bool = False,
            is_multiclass_block: bool = False,
        ) -> bool:
            local_changed = False
            for g in grant_rules:
                if g.level > eff_level:
                    continue
                if skip_primary_proficiencies:
                    if g.id.startswith("ID_PROFICIENCY_SAVINGTHROW_"):
                        continue
                    if is_multiclass_block is False and g.level == 1 and g.type == "Proficiency":
                        # If class XML provides a <multiclass> block, let that handle MC proficiencies
                        src_el = self.repo.get(source_id)
                        if src_el and src_el.multiclass is not None:
                            continue
                if not self._check_requirement(
                    g.requirements, granted_ids, eff_level, state.abilities, equip_tags, class_level_by_name
                ):
                    continue
                target_el = self.repo.get(g.id)
                child_owner: Optional[tuple[str, int, bool]] = None
                if owner_tuple is not None and target_el is not None and target_el.type in (
                    "Class",
                    "Archetype",
                    "Class Feature",
                    "Archetype Feature",
                    "Spell",
                ):
                    child_owner = owner_tuple
                if target_el is not None and target_el.type == "Spell" and owner_tuple is not None:
                    spell_grant_owners[g.id] = (owner_tuple[0], el_type)
                if (
                    owner_tuple is not None
                    and target_el is not None
                    and ("ability_score_improvement" in g.id.lower() or "ability score improvement" in target_el.name.lower())
                ):
                    asi_sels = [s for s in target_el.select_rules if is_asi_select_rule(s)]
                    if len(asi_sels) == 1 and asi_sels[0].level <= 1:
                        seen_asi_levels.add((owner_tuple[0], g.level))
                if g.id not in seen_elements:
                    granted_ids.add(g.id)
                    add_element(g.id, owner=child_owner)
                    local_changed = True

            for idx, sel in enumerate(select_rules):
                sel_level = sel.level
                if (
                    state.ruleset == "5.5e"
                    and sel.type == "Archetype"
                    and sel_level < 3
                    and not state.has_override("override_55e_subclass_level")
                ):
                    sel_level = 3
                if sel_level > eff_level:
                    continue
                if skip_primary_proficiencies and sel_level == 1 and sel.type == "Proficiency":
                    continue
                if not self._check_requirement(
                    sel.requirements, granted_ids, eff_level, state.abilities, equip_tags, class_level_by_name
                ):
                    continue

                # Track & skip XML ASI select if already resolved via Level-Up Wizard
                if owner_tuple is not None and is_asi_select_rule(sel):
                    seen_asi_levels.add((owner_tuple[0], sel.level))
                    asi_key = f"{owner_tuple[0]}::{sel.level}"
                    if asi_key in state.level_up_asi or asi_key in state.level_up_feats:
                        continue

                key = self.selection_key(source_id, sel.type, sel.name, sel.level, idx)
                if key not in seen_select_keys:
                    seen_select_keys.add(key)
                    if sel.type == "List":
                        options = list(sel.items)
                    else:
                        supports_expr = sel.supports
                        if sel.type == "Spell" and "$(" in supports_expr:
                            own_cid = owner_tuple[0] if owner_tuple else state.class_id
                            cls_el = self.repo.get(own_cid) if own_cid else None
                            supports_expr = self._expand_spell_supports(
                                supports_expr,
                                ordered_elements,
                                cls_el,
                                eff_level,
                                owner_cid=own_cid,
                                element_owners=element_owners,
                                ruleset=state.ruleset,
                            )
                        matches = self.repo.find_matching(sel.type, supports_expr)
                        if not matches and is_asi_select_rule(sel):
                            options = _synthetic_asi_options(self.repo, sel.number, supports_expr)
                        else:
                            options = [(m.id, m.name) for m in matches]
                    active_selections.append(
                        ActiveSelection(
                            key=key,
                            rule=sel,
                            source_element_id=source_id,
                            source_element_name=source_name,
                            options=options,
                        )
                    )
                chosen = state.selections.get(key, [])
                for slot_idx, cid in enumerate(chosen[: sel.number]):
                    if not cid or sel.type == "List":
                        continue
                    if is_synthetic_asi_id(cid):
                        if add_synthetic_asi(cid, key, slot_idx, owner_tuple):
                            local_changed = True
                        continue
                    if cid not in seen_elements:
                        target_el = self.repo.get(cid)
                        child_owner = None
                        if owner_tuple is not None and target_el is not None and target_el.type in (
                            "Class",
                            "Archetype",
                            "Class Feature",
                            "Archetype Feature",
                            "Spell",
                        ):
                            child_owner = owner_tuple
                        granted_ids.add(cid)
                        add_element(cid, owner=child_owner)
                        local_changed = True
            return local_changed

        # Iterate to fixed point as grants & user selections cascade
        for _ in range(12):
            changed = False
            snapshot = list(ordered_elements)
            for el in snapshot:
                owner = element_owners.get(el.id)
                eff_level = owner[1] if owner is not None else total_level
                is_primary = owner[2] if owner is not None else True

                if el.type == "Class" and not is_primary:
                    if process_rules_for_element(
                        el.id,
                        el.name,
                        el.type,
                        el.grant_rules,
                        el.select_rules,
                        eff_level,
                        owner,
                        skip_primary_proficiencies=True,
                    ):
                        changed = True
                    if el.multiclass is not None:
                        mc = el.multiclass
                        mc_sid = mc.id or f"{el.id}::multiclass"
                        if process_rules_for_element(
                            mc_sid,
                            f"{el.name} (Multiclass)",
                            el.type,
                            mc.grant_rules,
                            mc.select_rules,
                            eff_level,
                            owner,
                            skip_primary_proficiencies=False,
                            is_multiclass_block=True,
                        ):
                            changed = True
                    else:
                        for pid in MULTICLASS_PROFICIENCY_FALLBACK.get(el.name.lower(), []):
                            if pid not in seen_elements and self.repo.get(pid) is not None:
                                granted_ids.add(pid)
                                add_element(pid)
                                changed = True
                else:
                    if process_rules_for_element(
                        el.id,
                        el.name,
                        el.type,
                        el.grant_rules,
                        el.select_rules,
                        eff_level,
                        owner,
                    ):
                        changed = True
            if not changed:
                break

        # Fallback ASI selections for classes whose XML omits ASI <select> rules (e.g. 5e.tools imports)
        for idx_c, cl in enumerate(class_entries):
            cel = self.repo.get(cl.class_id)
            cname = cel.name if cel else cl.class_id
            c_owner = (cl.class_id, cl.level, idx_c == 0)
            for asi_lvl in _class_asi_levels(cel):
                if asi_lvl > cl.level:
                    continue
                if (cl.class_id, asi_lvl) in seen_asi_levels:
                    continue
                asi_key_l = f"{cl.class_id}::{asi_lvl}"
                if asi_key_l in state.level_up_asi or asi_key_l in state.level_up_feats:
                    continue
                syn_key = self.selection_key(
                    cl.class_id,
                    "Ability Score Improvement",
                    f"Ability Score Improvement (Level {asi_lvl})",
                    asi_lvl,
                    0,
                )
                if syn_key not in seen_select_keys:
                    seen_select_keys.add(syn_key)
                    active_selections.append(
                        ActiveSelection(
                            key=syn_key,
                            rule=SelectRule(
                                type="Ability Score Improvement",
                                name=f"Ability Score Improvement (Level {asi_lvl})",
                                number=1,
                                level=asi_lvl,
                                optional=False,
                            ),
                            source_element_id=cl.class_id,
                            source_element_name=cname,
                            options=_synthetic_asi_options(self.repo, 1, ""),
                        )
                    )
                for slot_idx, cid in enumerate(state.selections.get(syn_key, [])[:1]):
                    if not cid:
                        continue
                    if is_synthetic_asi_id(cid):
                        add_synthetic_asi(cid, syn_key, slot_idx, c_owner)
                    elif cid not in seen_elements:
                        add_element(cid)
                        chosen_el = self.repo.get(cid)
                        if chosen_el is not None:
                            process_rules_for_element(
                                chosen_el.id,
                                chosen_el.name,
                                chosen_el.type,
                                chosen_el.grant_rules,
                                chosen_el.select_rules,
                                total_level,
                                None,
                            )

        if state.ruleset == "5.5e":
            origin_key = self.selection_key("5.5e::Origin", "Feat", "Origin Feat (5.5e)", 1, 0)
            if origin_key not in seen_select_keys:
                seen_select_keys.add(origin_key)
                feat_rule = SelectRule(
                    type="Feat",
                    name="Origin Feat (5.5e)",
                    number=1,
                    level=1,
                    optional=False,
                )
                feat_options = [(f.id, f.name) for f in self.repo.of_type("Feat")]
                active_selections.append(
                    ActiveSelection(
                        key=origin_key,
                        rule=feat_rule,
                        source_element_id="5.5e",
                        source_element_name="2024 Revised Rules (5.5e)",
                        options=feat_options,
                    )
                )
                for cid in state.selections.get(origin_key, [])[:1]:
                    if cid and cid not in seen_elements:
                        add_element(cid)
                        chosen_el = self.repo.get(cid)
                        if chosen_el is not None:
                            for g in chosen_el.grant_rules:
                                if g.level <= total_level:
                                    add_element(g.id)

            # 2024 PHB Level 19+ Epic Boon selection
            if total_level >= 19:
                boon_key = self.selection_key("5.5e::EpicBoon", "Feat", "Epic Boon (5.5e Lv 19)", 19, 0)
                if boon_key not in seen_select_keys:
                    seen_select_keys.add(boon_key)
                    boon_els = get_55e_epic_boon_elements()
                    boon_map = {b.id: b for b in boon_els}
                    repo_boons = [
                        f for f in self.repo.of_type("Feat")
                        if "boon" in f.name.lower() or "epic boon" in " ".join(f.supports).lower()
                    ]
                    boon_opts = [(b.id, b.name) for b in boon_els] + [
                        (b.id, b.name) for b in repo_boons if b.id not in boon_map
                    ]
                    active_selections.append(
                        ActiveSelection(
                            key=boon_key,
                            rule=SelectRule(
                                type="Feat",
                                name="Epic Boon (5.5e Lv 19)",
                                number=1,
                                level=19,
                                optional=False,
                            ),
                            source_element_id="5.5e",
                            source_element_name="2024 Revised Rules (5.5e)",
                            options=boon_opts,
                        )
                    )
                    for bid in state.selections.get(boon_key, [])[:1]:
                        if not bid:
                            continue
                        if bid in boon_map and bid not in seen_elements:
                            seen_elements.add(bid)
                            granted_ids.add(bid)
                            ordered_elements.append(boon_map[bid])
                        elif bid not in seen_elements:
                            add_element(bid)

            # 5.5e Divine Order (Protector) & Primal Order (Warden) armor/weapon proficiencies
            if state.divine_order_55e == "protector":
                for pid, pname in (
                    ("ID_PROFICIENCY_ARMOR_PROFICIENCY_HEAVY_ARMOR", "Armor Proficiency (Heavy Armor)"),
                    ("ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS", "Weapon Proficiency (Martial Weapons)"),
                ):
                    if pid not in seen_elements:
                        if self.repo.get(pid) is not None:
                            add_element(pid)
                        else:
                            seen_elements.add(pid)
                            granted_ids.add(pid)
                            ordered_elements.append(Element(id=pid, name=pname, type="Proficiency", source="5.5e Divine Order"))
            if state.primal_order_55e == "warden":
                for pid, pname in (
                    ("ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", "Armor Proficiency (Medium Armor)"),
                    ("ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS", "Weapon Proficiency (Martial Weapons)"),
                ):
                    if pid not in seen_elements:
                        if self.repo.get(pid) is not None:
                            add_element(pid)
                        else:
                            seen_elements.add(pid)
                            granted_ids.add(pid)
                            ordered_elements.append(Element(id=pid, name=pname, type="Proficiency", source="5.5e Primal Order"))

        return ordered_elements, granted_ids, active_selections, element_owners, spell_grant_owners

    def _compute_stats(
        self,
        elements: list[Element],
        granted_ids: set[str],
        state: CharacterState,
        equip_tags: set[str],
        initial_stats: dict[str, float],
        element_owners: dict[str, tuple[str, int, bool]],
        class_level_by_id: dict[str, int],
        class_level_by_name: dict[str, int],
        total_level: int,
    ) -> dict[str, float]:
        stats = dict(initial_stats)

        # Multi-pass stat resolution so derived stats can reference earlier stats
        for _ in range(4):
            untyped_acc: dict[str, float] = defaultdict(float)
            typed_max: dict[tuple[str, str], float] = {}

            for el in elements:
                is_racial_el = el.type in ("Race", "Sub Race", "Race Variant", "Racial Trait")
                owner = element_owners.get(el.id)
                eff_level = owner[1] if owner is not None else total_level
                is_primary = owner[2] if owner is not None else True

                stat_lists = [el.stat_rules]
                if el.type == "Class" and not is_primary and el.multiclass is not None:
                    stat_lists.append(el.multiclass.stat_rules)

                for sr_list in stat_lists:
                    for sr in sr_list:
                        if sr.level > eff_level:
                            continue
                        if state.ruleset == "5.5e" and is_racial_el and sr.name.lower() in ABILITIES:
                            continue
                        if sr.equipped and not self._check_requirement(
                            sr.equipped, granted_ids, eff_level, state.abilities, equip_tags, class_level_by_name
                        ):
                            continue
                        if sr.requirements and not self._check_requirement(
                            sr.requirements, granted_ids, eff_level, state.abilities, equip_tags, class_level_by_name
                        ):
                            continue

                        val = self._eval_stat_value(sr.value, stats, eff_level)
                        if val is None:
                            continue

                        sname = sr.name.lower()
                        if sr.bonus:
                            bkey = (sname, sr.bonus.lower())
                            if bkey not in typed_max or val > typed_max[bkey]:
                                typed_max[bkey] = val
                        else:
                            untyped_acc[sname] += val

            new_stats = dict(initial_stats)
            all_names = set(untyped_acc.keys()) | {k[0] for k in typed_max.keys()}
            for name in all_names:
                total = untyped_acc.get(name, 0.0)
                for (sname, _bonus), bval in typed_max.items():
                    if sname == name:
                        total += bval
                new_stats[name] = total

            if state.ruleset == "5.5e":
                for ab, asi_val in state.background_asi.items():
                    if ab in ABILITIES and asi_val:
                        new_stats[ab] = new_stats.get(ab, 0.0) + float(asi_val)

            # Level-up ASI bonuses (scoped to active class levels)
            for key, asi_map in state.level_up_asi.items():
                if "::" not in key:
                    continue
                cid, lvl_str = key.split("::", 1)
                try:
                    req_lvl = int(lvl_str)
                except ValueError:
                    continue
                if class_level_by_id.get(cid, 0) < req_lvl:
                    continue
                for ab, asi_val in asi_map.items():
                    if ab in ABILITIES and asi_val:
                        new_stats[ab] = new_stats.get(ab, 0.0) + float(asi_val)

            for ab in ABILITIES:
                base_val = float(state.abilities.get(ab, 10))
                bonus_val = new_stats.get(ab, 0.0)
                tot = base_val + bonus_val
                new_stats[f"{ab}:total"] = tot
                new_stats[f"{ab}:modifier"] = float(ability_modifier(int(tot)))

            if new_stats == stats:
                break
            stats = new_stats

        return stats

    @staticmethod
    def _eval_stat_value(raw: str, stats: dict[str, float], level: int) -> Optional[float]:
        s = raw.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            pass
        sl = s.lower()
        if sl == "level":
            return float(level)
        if sl == "level:half":
            return float(level // 2)
        if sl == "level:half:up":
            return float(math.ceil(level / 2))
        if sl == "proficiency":
            return float(2 + (level - 1) // 4)
        if sl in stats:
            return float(stats[sl])
        return None

    def evaluate(self, state: CharacterState) -> ComputedCharacter:
        class_entries = state.normalized_classes()
        total_level = (
            sum(c.level for c in class_entries)
            if class_entries
            else max(1, min(20, int(state.level or 1)))
        )
        equip_tags = self._equipment_tags(state)
        (
            elements,
            granted_ids,
            active_selections,
            element_owners,
            spell_grant_owners,
        ) = self._collect_elements(state, equip_tags)

        class_level_by_id = {c.class_id: c.level for c in class_entries}
        class_level_by_name: dict[str, int] = {}
        class_levels_out: list[tuple[str, str, int]] = []
        for cl in class_entries:
            cel = self.repo.get(cl.class_id)
            cname = cel.name if cel else cl.class_id
            class_level_by_name[cname.lower()] = cl.level
            class_levels_out.append((cl.class_id, cname, cl.level))

        proficiency_bonus = 2 + (total_level - 1) // 4
        seed_stats: dict[str, float] = {
            "level": float(total_level),
            "proficiency": float(proficiency_bonus),
        }
        for cname_l, clvl in class_level_by_name.items():
            seed_stats[f"level:{cname_l}"] = float(clvl)
            seed_stats[f"level:{cname_l}:half"] = float(clvl // 2)
            seed_stats[f"level:{cname_l}:half:up"] = float(math.ceil(clvl / 2))
            seed_stats[f"level:{cname_l}:third"] = float(clvl // 3)
        for ab in ABILITIES:
            seed_stats[f"{ab}:total"] = float(state.abilities.get(ab, 10))
            seed_stats[f"{ab}:modifier"] = float(ability_modifier(state.abilities.get(ab, 10)))

        stats = self._compute_stats(
            elements,
            granted_ids,
            state,
            equip_tags,
            seed_stats,
            element_owners,
            class_level_by_id,
            class_level_by_name,
            total_level,
        )

        ability_bonuses: dict[str, int] = {}
        ability_totals: dict[str, int] = {}
        ability_modifiers: dict[str, int] = {}
        for ab in ABILITIES:
            bonus = int(round(stats.get(ab, 0.0)))
            raw_total = int(state.abilities.get(ab, 10)) + bonus
            if state.has_override("override_asi_cap"):
                total = max(1, min(30, raw_total))
            else:
                cap = max(20, int(round(stats.get(f"{ab}:max", 20.0))))
                total = max(1, min(cap, raw_total))
            ability_bonuses[ab] = bonus
            ability_totals[ab] = total
            ability_modifiers[ab] = ability_modifier(total)

        proficiency_bonus = 2 + (total_level - 1) // 4 + int(round(stats.get("proficiency:bonus", 0.0)))

        # Hit Points (supports Average & Rolled/Manual, Single & Multiclass)
        con_mod = ability_modifiers["constitution"]
        primary_class_el = self.repo.get(class_entries[0].class_id) if class_entries else (
            self.repo.get(state.class_id) if state.class_id else None
        )
        hd_str = primary_class_el.setters.get("hd", "d8") if primary_class_el else "d8"

        level_order = state.normalized_level_order()
        hp_breakdown: list[dict] = []
        base_hp = 0
        if not level_order:
            hd_num = 8
            for lvl_idx in range(1, total_level + 1):
                avg = (hd_num // 2) + 1
                if state.hp_mode == "rolled" and lvl_idx in state.hp_rolls:
                    die_val = max(1, min(hd_num, int(state.hp_rolls[lvl_idx])))
                    src = "rolled"
                elif lvl_idx == 1:
                    die_val = hd_num
                    src = "max"
                else:
                    die_val = avg
                    src = "average"
                row_hp = die_val + con_mod
                base_hp += row_hp
                hp_breakdown.append(
                    {
                        "level": lvl_idx,
                        "class_id": "",
                        "class_name": "Adventurer",
                        "hit_die": f"d{hd_num}",
                        "hd_num": hd_num,
                        "roll": die_val,
                        "con_mod": con_mod,
                        "total": row_hp,
                        "source": src,
                    }
                )
            hit_dice_summary = f"{total_level}d8"
        else:
            hd_counts: dict[str, int] = {}
            for lvl_idx, cid in enumerate(level_order, start=1):
                cel = self.repo.get(cid)
                cname = cel.name if cel else cid
                hd_num = parse_hit_die(cel)
                hd_tag = f"d{hd_num}"
                hd_counts[hd_tag] = hd_counts.get(hd_tag, 0) + 1
                avg = (hd_num // 2) + 1
                if state.hp_mode == "rolled" and lvl_idx in state.hp_rolls:
                    die_val = max(1, min(hd_num, int(state.hp_rolls[lvl_idx])))
                    src = "rolled"
                elif lvl_idx == 1:
                    die_val = hd_num
                    src = "max"
                else:
                    die_val = avg
                    src = "average"
                row_hp = die_val + con_mod
                base_hp += row_hp
                hp_breakdown.append(
                    {
                        "level": lvl_idx,
                        "class_id": cid,
                        "class_name": cname,
                        "hit_die": hd_tag,
                        "hd_num": hd_num,
                        "roll": die_val,
                        "con_mod": con_mod,
                        "total": row_hp,
                        "source": src,
                    }
                )
            hit_dice_summary = " + ".join(f"{cnt}{tag}" for tag, cnt in hd_counts.items())

        bonus_hp = int(round(stats.get("hp", 0.0)))
        max_hp = max(1, base_hp + bonus_hp)

        # Armor Class
        armor_class = self._compute_ac(state, granted_ids, ability_modifiers, stats)

        # Initiative & Speed (including 5.5e Alert Origin Feat & Exhaustion)
        init_bonus = int(round(stats.get("initiative", 0.0)))
        if state.ruleset == "5.5e":
            origin_chosen = state.selections.get(
                self.selection_key("5.5e::Origin", "Feat", "Origin Feat (5.5e)", 1, 0), []
            )
            for fid in origin_chosen:
                fel = self.repo.get(fid)
                if fel and "alert" in fel.name.lower() and not any(
                    sr.name.lower() == "initiative" for sr in fel.stat_rules
                ):
                    init_bonus += proficiency_bonus
                if fel and "tough" in fel.name.lower() and not any(
                    sr.name.lower() == "hp" for sr in fel.stat_rules
                ):
                    max_hp = max(1, max_hp + 2 * total_level)

        initiative = ability_modifiers["dexterity"] + init_bonus
        speed = int(round(stats.get("innate speed", 0.0) or stats.get("speed", 0.0) or 30))
        exhaustion_d20_penalty = 0
        if state.ruleset == "5.5e" and state.exhaustion_level > 0:
            d20_pen, spd_pen = exhaustion_55e_penalty(state.exhaustion_level)
            exhaustion_d20_penalty = d20_pen
            speed = max(0, speed + spd_pen)

        # Saving Throws
        ov_profs = state.has_override("override_proficiencies")
        manual_saves = {s.lower() for s in state.manual_save_profs} if ov_profs else set()
        manual_skills = {s.lower() for s in state.manual_skill_profs} if ov_profs else set()
        manual_exp = {s.lower() for s in state.manual_skill_expertise} if ov_profs else set()

        saving_throws: dict[str, SavingThrowValue] = {}
        for ab in ABILITIES:
            save_id = f"ID_PROFICIENCY_SAVINGTHROW_{ab.upper()}"
            prof = (
                save_id in granted_ids
                or ab.lower() in manual_saves
                or any(
                    e.type == "Proficiency" and f"{ab} saving throw" in e.name.lower()
                    for e in elements
                )
            )
            bonus = ability_modifiers[ab] + (proficiency_bonus if prof else 0) + exhaustion_d20_penalty
            saving_throws[ab] = SavingThrowValue(ability=ab, bonus=bonus, proficient=prof)

        # Skills (including 5.5e Divine/Primal Order skill bonuses)
        wis_order_bonus = max(1, ability_modifiers["wisdom"])
        skill_extra: dict[str, int] = {}
        if state.ruleset == "5.5e":
            if state.divine_order_55e == "thaumaturge":
                skill_extra["Arcana"] = skill_extra.get("Arcana", 0) + wis_order_bonus
                skill_extra["Religion"] = skill_extra.get("Religion", 0) + wis_order_bonus
            if state.primal_order_55e == "magician":
                skill_extra["Arcana"] = skill_extra.get("Arcana", 0) + wis_order_bonus
                skill_extra["Nature"] = skill_extra.get("Nature", 0) + wis_order_bonus

        skills: dict[str, SkillValue] = {}
        expertise_names = {
            e.name.lower()
            for e in elements
            if "expertise" in e.id.lower() or "expertise" in e.name.lower()
        }
        for skill_name, ab in SKILLS:
            skill_id = SKILL_ID_MAP[skill_name]
            sk_lower = skill_name.lower()
            expertise = (
                sk_lower in manual_exp
                or f"expertise ({sk_lower})" in expertise_names
                or f"{sk_lower} expertise" in expertise_names
                or f"ID_INTERNAL_EXPERTISE_SKILL_{skill_name.upper().replace(' ', '_')}" in granted_ids
            )
            prof = (
                expertise
                or sk_lower in manual_skills
                or skill_id in granted_ids
                or any(
                    e.type == "Proficiency" and e.name.lower() == f"skill ({sk_lower})"
                    for e in elements
                )
            )
            mult = 2 if (prof and expertise) else (1 if prof else 0)
            bonus = (
                ability_modifiers[ab]
                + mult * proficiency_bonus
                + skill_extra.get(skill_name, 0)
                + exhaustion_d20_penalty
            )
            skills[skill_name] = SkillValue(
                name=skill_name,
                ability=ab,
                bonus=bonus,
                proficient=prof,
                expertise=expertise,
            )

        passive_perception = 10 + skills["Perception"].bonus

        # Proficiencies & Languages
        prof_set = {
            e.name
            for e in elements
            if e.type == "Proficiency"
            and not e.id.startswith("ID_PROFICIENCY_SKILL_")
            and not e.id.startswith("ID_PROFICIENCY_SAVINGTHROW_")
        }
        if ov_profs:
            prof_set.update(p for p in state.manual_proficiencies if p)
        proficiencies = sorted(prof_set)
        languages = sorted({e.name for e in elements if e.type == "Language"})

        # Spellcasting (Single-class, Subclass 1/3-caster & extensions, and Multiclass)
        spellcasting = self._compute_spellcasting(
            state,
            elements,
            class_entries,
            element_owners,
            spell_grant_owners,
            ability_modifiers,
            proficiency_bonus,
            stats,
            active_selections,
        )

        # Inventory Weight
        total_weight = 0.0
        for item in state.inventory:
            el = self.repo.get(item.element_id)
            w = item.weight if item.weight > 0 else parse_weight_lb(el)
            total_weight += w * max(0, item.quantity)

        # 5.5e Weapon Masteries & Rules Notes
        weapon_mastery_limit = compute_weapon_mastery_limit(state, self.repo, elements)
        weapon_mastery_details: list[dict] = []
        ruleset_55e_notes: list[str] = []
        if state.ruleset == "5.5e":
            mastered_lower = {w.strip().lower() for w in state.weapon_masteries if w.strip()}
            for wname in state.weapon_masteries:
                prop = get_weapon_mastery(wname)
                if prop:
                    weapon_mastery_details.append(
                        {
                            "weapon": wname,
                            "mastery": prop,
                            "description": WEAPON_MASTERY_DESCRIPTIONS.get(prop, ""),
                        }
                    )
            for item in state.inventory:
                if item.category == "Weapon" and item.equipped:
                    el = self.repo.get(item.element_id)
                    if not state.has_override("override_heavy_weapon_req"):
                        ok_hw, msg_hw = check_55e_heavy_weapon_requirement(el, ability_totals)
                        if not ok_hw and msg_hw:
                            ruleset_55e_notes.append(f"⚠ {item.name}: {msg_hw}")
                    if item.name.lower() in mastered_lower:
                        continue
            if weapon_mastery_limit > 0 or state.has_override("override_weapon_mastery"):
                ruleset_55e_notes.append(
                    f"Weapon Mastery: {len(state.weapon_masteries)} / "
                    f"{'Unlimited (Override)' if state.has_override('override_weapon_mastery') else weapon_mastery_limit} mastered"
                )
            for cid, cname, clvl in class_levels_out:
                if "monk" in cname.lower():
                    ruleset_55e_notes.append(
                        f"Monk Martial Arts Die (5.5e): {monk_martial_arts_die_55e(clvl)}"
                    )
            if state.exhaustion_level > 0:
                ruleset_55e_notes.append(
                    f"Exhaustion Lv {state.exhaustion_level}: {exhaustion_d20_penalty} to d20 Tests, "
                    f"{-5 * state.exhaustion_level} ft Speed"
                )
            if state.heroic_inspiration:
                ruleset_55e_notes.append("Heroic Inspiration: Active (reroll any die)")
            if spellcasting is not None:
                ruleset_55e_notes.append("5.5e Ritual Casting: All spellcasters can cast prepared Ritual spells as rituals.")

        return ComputedCharacter(
            ability_totals=ability_totals,
            ability_bonuses=ability_bonuses,
            ability_modifiers=ability_modifiers,
            proficiency_bonus=proficiency_bonus,
            max_hp=max_hp,
            hit_die=hd_str,
            armor_class=armor_class,
            initiative=initiative,
            speed=speed,
            passive_perception=passive_perception,
            saving_throws=saving_throws,
            skills=skills,
            granted_elements=elements,
            active_selections=active_selections,
            proficiencies=proficiencies,
            languages=languages,
            spellcasting=spellcasting,
            total_weight=round(total_weight, 2),
            stats=stats,
            class_levels=class_levels_out,
            hit_dice_summary=hit_dice_summary,
            hp_breakdown=hp_breakdown,
            weapon_mastery_limit=weapon_mastery_limit,
            weapon_mastery_details=weapon_mastery_details,
            ruleset_55e_notes=ruleset_55e_notes,
            exhaustion_d20_penalty=exhaustion_d20_penalty,
        )

    def _compute_ac(
        self,
        state: CharacterState,
        granted_ids: set[str],
        mods: dict[str, int],
        stats: dict[str, float],
    ) -> int:
        dex_mod = mods["dexterity"]
        armor_base: Optional[int] = None
        armor_kind = ""
        armor_magic = 0
        shield_bonus = 0

        for item in state.inventory:
            if not item.equipped or item.quantity <= 0:
                continue
            el = self.repo.get(item.element_id)
            if el is None:
                continue
            kind = el.setters.get("armor", "").strip().lower()
            slot = el.setters.get("slot", "").strip().lower()
            if kind == "shield" or "shield" in el.name.lower() or slot == "shield":
                shield_bonus = max(shield_bonus, 2 + max(0, item.magic_bonus))
                continue
            if kind in ("light", "medium", "heavy"):
                ac_str = el.setters.get("armorClass", "")
                m = re.search(r"(\d+)", ac_str)
                if m:
                    base_val = int(m.group(1))
                    if armor_base is None or (base_val + item.magic_bonus) > (armor_base + armor_magic):
                        armor_base = base_val
                        armor_kind = kind
                        armor_magic = max(0, item.magic_bonus)

        if armor_base is not None:
            if armor_kind == "light":
                ac = armor_base + dex_mod + armor_magic
            elif armor_kind == "medium":
                ac = armor_base + min(dex_mod, 2) + armor_magic
            else:
                ac = armor_base + armor_magic
        else:
            candidates = [10 + dex_mod]
            if "ID_WOTC_PHB_CLASS_FEATURE_BARBARIAN_UNARMORED_DEFENSE" in granted_ids:
                candidates.append(10 + dex_mod + mods["constitution"])
            if "ID_WOTC_PHB_CLASS_FEATURE_MONK_UNARMORED_DEFENSE" in granted_ids and shield_bonus == 0:
                candidates.append(10 + dex_mod + mods["wisdom"])
            if "ID_WOTC_PHB_ARCHETYPE_FEATURE_DRACONIC_RESILIENCE" in granted_ids:
                candidates.append(13 + dex_mod)
            ac = max(candidates)

        misc = int(round(stats.get("ac:misc", 0.0) + stats.get("ac:armored:enhancement", 0.0)))
        return ac + shield_bonus + misc

    def _compute_spellcasting(
        self,
        state: CharacterState,
        elements: list[Element],
        class_entries: list,
        element_owners: dict[str, tuple[str, int, bool]],
        spell_grant_owners: dict[str, tuple[str, str]],
        mods: dict[str, int],
        proficiency_bonus: int,
        stats: dict[str, float],
        active_selections: Optional[list[ActiveSelection]] = None,
    ) -> Optional[SpellcastingSummary]:
        casters: list[ClassSpellcasting] = []

        # Map each class_id to its scoped elements
        scoped_groups: list[tuple[str, int, list[Element]]] = []
        if class_entries:
            for cl in class_entries:
                scoped_els = [
                    el
                    for el in elements
                    if element_owners.get(el.id, (None,))[0] == cl.class_id
                ]
                scoped_groups.append((cl.class_id, cl.level, scoped_els))
        else:
            # Unclassed fallback (e.g. spellcasting item or race only)
            unowned_sc = [el for el in elements if el.spellcasting is not None]
            if unowned_sc:
                scoped_groups.append(("", max(1, min(20, state.level)), elements))

        for cid, cls_lvl, scoped_els in scoped_groups:
            class_el = self.repo.get(cid) if cid else None
            base_sc: Optional[SpellcastingInfo] = None
            base_sc_el: Optional[Element] = None
            ext_sc_infos: list[SpellcastingInfo] = []
            subclass_name = ""

            for el in scoped_els:
                if el.type == "Archetype" and not subclass_name:
                    subclass_name = el.name
                if el.spellcasting is not None:
                    if el.spellcasting.extend:
                        ext_sc_infos.append(el.spellcasting)
                    elif base_sc is None:
                        base_sc = el.spellcasting
                        base_sc_el = el

            if base_sc is None:
                continue

            cname_l = (class_el.name if class_el else base_sc.name).lower()
            scname_l = base_sc.name.lower()
            sub_l = subclass_name.lower()

            if "warlock" in cname_l or "warlock" in scname_l:
                caster_type = "pact"
            elif (
                "eldritch knight" in scname_l
                or "arcane trickster" in scname_l
                or "eldritch knight" in sub_l
                or "arcane trickster" in sub_l
                or (base_sc_el is not None and base_sc_el.type in ("Archetype", "Archetype Feature"))
            ):
                caster_type = "third"
            elif (
                "artificer" in cname_l
                or "artificer" in scname_l
                or (state.ruleset == "5.5e" and ("paladin" in cname_l or "ranger" in cname_l))
            ):
                caster_type = "half_up"
            elif "paladin" in cname_l or "ranger" in cname_l:
                caster_type = "half"
            else:
                caster_type = "full"

            is_pact = caster_type == "pact"

            class_slots = self._slots_from_elements_or_table(
                scoped_els,
                class_el,
                base_sc.name,
                cls_lvl,
                stats=stats if len(class_entries) <= 1 else None,
                caster_type=caster_type,
                ruleset=state.ruleset,
            )

            # Half-casters at level 1 in 5e and 1/3-casters before level 3 do not cast yet unless slots exist
            if not class_slots and caster_type in ("half", "third"):
                continue

            ab_key = base_sc.ability.strip().lower()
            if ab_key not in mods:
                ab_key = "intelligence"
            ab_mod = mods[ab_key]
            save_dc = 8 + proficiency_bonus + ab_mod
            attack_bonus = proficiency_bonus + ab_mod
            max_spell_level = max(class_slots.keys(), default=0)

            # Extended spell lists / IDs from subclasses (e.g. Genie Warlock, Divine Soul, Lore Bard)
            extended_spell_ids: list[str] = []
            extended_spell_lists: list[str] = []
            for ext_sc in ext_sc_infos:
                for token in ext_sc.extended:
                    if self.repo.get(token) is not None or token.startswith("ID_"):
                        if token not in extended_spell_ids:
                            extended_spell_ids.append(token)
                    else:
                        if token not in extended_spell_lists:
                            extended_spell_lists.append(token)

            # Derive cantrip & known/spellbook limits from active <select type="Spell"> rules owned by this class
            max_cantrips = 0
            select_known = 0
            for active_sel in active_selections or []:
                if active_sel.rule.type != "Spell":
                    continue
                sel_own = element_owners.get(active_sel.source_element_id)
                if cid and sel_own is not None and sel_own[0] != cid:
                    continue
                rname = active_sel.rule.name.lower()
                rsup = active_sel.rule.supports.lower()
                if "cantrip" in rname or rsup.endswith(", 0") or rsup.strip() == "0":
                    max_cantrips += active_sel.rule.number
                else:
                    select_known += active_sel.rule.number

            if max_cantrips == 0 and "paladin" not in cname_l and "ranger" not in cname_l:
                if caster_type == "third":
                    max_cantrips = 3 if cls_lvl >= 10 else (2 if cls_lvl >= 3 else 0)
                elif "sorcerer" in cname_l:
                    max_cantrips = 6 if cls_lvl >= 10 else (5 if cls_lvl >= 4 else 4)
                elif any(k in cname_l for k in ("wizard", "cleric")):
                    max_cantrips = 5 if cls_lvl >= 10 else (4 if cls_lvl >= 4 else 3)
                else:
                    max_cantrips = 4 if cls_lvl >= 10 else (3 if cls_lvl >= 4 else 2)
            if state.ruleset == "5.5e":
                if "cleric" in cname_l and state.divine_order_55e == "thaumaturge":
                    max_cantrips += 1
                if "druid" in cname_l and state.primal_order_55e == "magician":
                    max_cantrips += 1

            is_prepare = True if state.ruleset == "5.5e" else base_sc.prepare
            max_known_spells: Optional[int] = None
            if "wizard" in cname_l:
                max_known_spells = max(select_known, 6 + 2 * max(0, cls_lvl - 1))
            elif caster_type == "third":
                max_known_spells = max(select_known, THIRD_CASTER_KNOWN.get(cls_lvl, 0))
            elif select_known > 0:
                max_known_spells = select_known
            elif not is_prepare:
                max_known_spells = max(2, cls_lvl + 1)

            max_prepared_spells: Optional[int] = None
            if is_prepare:
                if state.ruleset == "5.5e":
                    prep_55e = get_55e_prepared_spells(cname_l, cls_lvl)
                    if prep_55e is not None:
                        max_prepared_spells = prep_55e
                if max_prepared_spells is None:
                    if caster_type in ("half", "half_up"):
                        max_prepared_spells = max(1, ab_mod + max(1, cls_lvl // 2))
                    else:
                        max_prepared_spells = max(1, ab_mod + cls_lvl)

            granted_spell_ids = [el.id for el in scoped_els if el.type == "Spell"]
            always_prepared_ids = [
                sid
                for sid in granted_spell_ids
                if spell_grant_owners.get(sid, ("", ""))[1] in ("Archetype", "Archetype Feature")
            ]

            casters.append(
                ClassSpellcasting(
                    source_class_id=cid,
                    source_class_name=class_el.name if class_el else base_sc.name,
                    subclass_name=subclass_name,
                    class_level=cls_lvl,
                    caster_type=caster_type,
                    ability=base_sc.ability,
                    ability_mod=ab_mod,
                    save_dc=save_dc,
                    attack_bonus=attack_bonus,
                    prepare=is_prepare,
                    spell_list=base_sc.spell_list or (class_el.name if class_el else base_sc.name),
                    extended_spell_ids=extended_spell_ids,
                    extended_spell_lists=extended_spell_lists,
                    class_slots=class_slots,
                    max_spell_level=max_spell_level,
                    max_cantrips=max_cantrips,
                    max_known_spells=max_known_spells,
                    max_prepared_spells=max_prepared_spells,
                    granted_spell_ids=granted_spell_ids,
                    always_prepared_spell_ids=always_prepared_ids,
                    is_pact_magic=is_pact,
                )
            )

        if not casters:
            return None

        regular_casters = [c for c in casters if not c.is_pact_magic]
        pact_casters = [c for c in casters if c.is_pact_magic]

        pact_slots: dict[int, int] = {}
        for pc in pact_casters:
            for slvl, cnt in pc.class_slots.items():
                pact_slots[slvl] = pact_slots.get(slvl, 0) + cnt

        is_mc_caster = False
        mc_caster_level = 0
        if not regular_casters:
            combined_slots = dict(pact_slots)
            is_mc_caster = len(pact_casters) > 1
        elif len(regular_casters) == 1:
            combined_slots = dict(regular_casters[0].class_slots)
            is_mc_caster = len(pact_casters) > 0
        else:
            is_mc_caster = True
            for rc in regular_casters:
                if rc.caster_type == "full":
                    mc_caster_level += rc.class_level
                elif rc.caster_type == "half_up":
                    mc_caster_level += math.ceil(rc.class_level / 2)
                elif rc.caster_type == "half":
                    mc_caster_level += rc.class_level // 2
                elif rc.caster_type == "third":
                    mc_caster_level += rc.class_level // 3
            mc_caster_level = max(1, min(20, mc_caster_level))
            combined_slots = dict(FULL_CASTER_SLOTS.get(mc_caster_level, {}))

        all_granted = list(
            dict.fromkeys(sid for c in casters for sid in c.granted_spell_ids)
        )
        all_always_prep = list(
            dict.fromkeys(sid for c in casters for sid in c.always_prepared_spell_ids)
        )
        all_ext_ids = list(
            dict.fromkeys(sid for c in casters for sid in c.extended_spell_ids)
        )
        all_ext_lists = list(
            dict.fromkeys(lst for c in casters for lst in c.extended_spell_lists)
        )

        if len(casters) == 1:
            only = casters[0]
            return SpellcastingSummary(
                caster_name=only.source_class_name if only.source_class_id else base_sc.name,
                ability=only.ability,
                ability_mod=only.ability_mod,
                save_dc=only.save_dc,
                attack_bonus=only.attack_bonus,
                prepare=only.prepare,
                spell_list=only.spell_list,
                slots=combined_slots,
                max_cantrips=only.max_cantrips,
                max_known_spells=only.max_known_spells,
                max_prepared_spells=only.max_prepared_spells,
                max_spell_level=max(combined_slots.keys(), default=0),
                granted_spell_ids=all_granted,
                casters=casters,
                pact_slots=pact_slots if only.is_pact_magic else {},
                is_multiclass_caster=False,
                multiclass_caster_level=0,
                always_prepared_spell_ids=all_always_prep,
                extended_spell_ids=all_ext_ids,
                extended_spell_lists=all_ext_lists,
            )

        known_vals = [c.max_known_spells for c in casters if c.max_known_spells is not None]
        prep_vals = [c.max_prepared_spells for c in casters if c.max_prepared_spells is not None]
        primary = casters[0]
        return SpellcastingSummary(
            caster_name=" / ".join(c.source_class_name for c in casters),
            ability=primary.ability,
            ability_mod=primary.ability_mod,
            save_dc=primary.save_dc,
            attack_bonus=primary.attack_bonus,
            prepare=any(c.prepare for c in casters),
            spell_list=", ".join(dict.fromkeys(c.spell_list for c in casters if c.spell_list)),
            slots=combined_slots,
            max_cantrips=sum(c.max_cantrips for c in casters),
            max_known_spells=sum(known_vals) if known_vals else None,
            max_prepared_spells=sum(prep_vals) if prep_vals else None,
            max_spell_level=max([*combined_slots.keys(), *pact_slots.keys()], default=0),
            granted_spell_ids=all_granted,
            casters=casters,
            pact_slots=pact_slots,
            is_multiclass_caster=is_mc_caster,
            multiclass_caster_level=mc_caster_level,
            always_prepared_spell_ids=all_always_prep,
            extended_spell_ids=all_ext_ids,
            extended_spell_lists=all_ext_lists,
        )
