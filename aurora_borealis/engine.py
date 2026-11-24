"""Aurora XML Rules Engine for D&D 5e characters."""

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
    ComputedCharacter,
    Element,
    SavingThrowValue,
    SelectRule,
    SkillValue,
    SpellcastingSummary,
)

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
    lvl: FULL_CASTER_SLOTS.get(math.ceil(lvl / 2), {}) if lvl >= 2 else {}
    for lvl in range(1, 21)
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


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def parse_weight_lb(el: Optional[Element]) -> float:
    if el is None:
        return 0.0
    raw = el.setters.get("weight_lb") or el.setters.get("weight") or "0"
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw)
    return float(m.group(1)) if m else 0.0


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
    ) -> bool:
        expr = (expr or "").strip()
        if not expr:
            return True

        abbr_to_full = {v.lower(): k for k, v in ABILITY_ABBR.items()}

        def predicate(term: str) -> bool:
            t = term.strip()
            tl = t.lower()
            if tl.startswith("[") and tl.endswith("]"):
                inner = tl[1:-1].strip()
                if tl in equip_tags:
                    return True
                if inner.startswith("level:"):
                    try:
                        return level >= int(inner.split(":", 1)[1])
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

    def _active_spellcasting_info(self, elements: list[Element]):
        for el in elements:
            if el.spellcasting is not None:
                return el.spellcasting
        return None

    def _slots_from_elements_or_table(
        self,
        elements: list[Element],
        class_el: Optional[Element],
        caster_name: str,
        level: int,
        stats: Optional[dict[str, float]] = None,
    ) -> dict[int, int]:
        slots: dict[int, int] = {}
        prefixes = (
            f"{caster_name.lower()}:spellcasting:slots:",
            f"{caster_name.lower()}:spellcasting:slot:",
        )
        if stats:
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
            cname = (class_el.name if class_el else caster_name).lower()
            if "warlock" in cname:
                slots = dict(WARLOCK_SLOTS.get(level, {}))
            elif "paladin" in cname or "ranger" in cname:
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
    ) -> str:
        if "$(" not in expr:
            return expr
        sc_info = self._active_spellcasting_info(elements)
        spell_list = sc_info.spell_list if sc_info else (class_el.name if class_el else "")
        caster_name = sc_info.name if sc_info else (class_el.name if class_el else "")
        slots = self._slots_from_elements_or_table(elements, class_el, caster_name, level)
        slot_levels = sorted(slots.keys())
        slots_expr = "(" + "||".join(str(l) for l in slot_levels) + ")" if slot_levels else "0"

        out = expr.replace("$(spellcasting:list)", spell_list or "")
        out = out.replace("$(spellcasting:slots)", slots_expr)
        return out

    def _collect_elements(
        self, state: CharacterState, equip_tags: set[str]
    ) -> tuple[list[Element], set[str], list[ActiveSelection]]:
        level = max(1, min(20, state.level))
        seed_ids: list[str] = []
        for eid in (
            state.race_id,
            state.class_id,
            state.background_id,
            state.alignment_id,
            state.deity_id,
        ):
            if eid:
                seed_ids.append(eid)

        # Level marker element IDs in Aurora (e.g. ID_INTERNAL_LEVEL_1 .. N)
        granted_ids: set[str] = set()
        for lvl in range(1, level + 1):
            granted_ids.add(f"ID_INTERNAL_LEVEL_{lvl}")
            level_el = self.repo.get(f"ID_INTERNAL_LEVEL_{lvl}")
            if level_el and level_el.id not in seed_ids:
                seed_ids.append(level_el.id)

        # Equipped items can also grant rules/stats
        for item in state.inventory:
            if item.equipped and item.quantity > 0 and item.element_id:
                seed_ids.append(item.element_id)

        ordered_elements: list[Element] = []
        seen_elements: set[str] = set()

        def add_element(eid: str) -> None:
            if not eid or eid in seen_elements:
                return
            el = self.repo.get(eid)
            if el is not None:
                seen_elements.add(eid)
                granted_ids.add(eid)
                ordered_elements.append(el)

        for sid in seed_ids:
            add_element(sid)

        active_selections: list[ActiveSelection] = []
        seen_select_keys: set[str] = set()

        # Iterate to fixed point as grants & user selections cascade
        for _ in range(12):
            changed = False
            snapshot = list(ordered_elements)
            for el in snapshot:
                for g in el.grant_rules:
                    if g.level > level:
                        continue
                    if not self._check_requirement(
                        g.requirements, granted_ids, level, state.abilities, equip_tags
                    ):
                        continue
                    if g.id not in seen_elements:
                        granted_ids.add(g.id)
                        add_element(g.id)
                        changed = True

                for idx, sel in enumerate(el.select_rules):
                    if sel.level > level:
                        continue
                    if not self._check_requirement(
                        sel.requirements, granted_ids, level, state.abilities, equip_tags
                    ):
                        continue
                    key = self.selection_key(el.id, sel.type, sel.name, sel.level, idx)
                    if key not in seen_select_keys:
                        seen_select_keys.add(key)
                        if sel.type == "List":
                            options = list(sel.items)
                        else:
                            supports_expr = sel.supports
                            if sel.type == "Spell" and "$(" in supports_expr:
                                class_el = self.repo.get(state.class_id) if state.class_id else None
                                supports_expr = self._expand_spell_supports(
                                    supports_expr, ordered_elements, class_el, level
                                )
                            matches = self.repo.find_matching(sel.type, supports_expr)
                            options = [(m.id, m.name) for m in matches]
                        active_selections.append(
                            ActiveSelection(
                                key=key,
                                rule=sel,
                                source_element_id=el.id,
                                source_element_name=el.name,
                                options=options,
                            )
                        )
                    chosen = state.selections.get(key, [])
                    for cid in chosen[: sel.number]:
                        if cid and sel.type != "List" and cid not in seen_elements:
                            granted_ids.add(cid)
                            add_element(cid)
                            changed = True
            if not changed:
                break

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
                        # Also expand grants from the chosen Origin Feat
                        chosen_el = self.repo.get(cid)
                        if chosen_el is not None:
                            for g in chosen_el.grant_rules:
                                if g.level <= level:
                                    add_element(g.id)

        return ordered_elements, granted_ids, active_selections

    def _compute_stats(
        self,
        elements: list[Element],
        granted_ids: set[str],
        state: CharacterState,
        equip_tags: set[str],
        initial_stats: dict[str, float],
    ) -> dict[str, float]:
        level = max(1, min(20, state.level))
        stats = dict(initial_stats)

        # Multi-pass stat resolution so derived stats can reference earlier stats
        for _ in range(4):
            untyped_acc: dict[str, float] = defaultdict(float)
            typed_max: dict[tuple[str, str], float] = {}

            for el in elements:
                is_racial_el = el.type in ("Race", "Sub Race", "Race Variant", "Racial Trait")
                for sr in el.stat_rules:
                    if sr.level > level:
                        continue
                    if state.ruleset == "5.5e" and is_racial_el and sr.name.lower() in ABILITIES:
                        continue
                    if sr.equipped and not self._check_requirement(
                        sr.equipped, granted_ids, level, state.abilities, equip_tags
                    ):
                        continue
                    if sr.requirements and not self._check_requirement(
                        sr.requirements, granted_ids, level, state.abilities, equip_tags
                    ):
                        continue

                    val = self._eval_stat_value(sr.value, stats, level)
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

            # Also expose ability totals & modifiers dynamically
            if state.ruleset == "5.5e":
                for ab, asi_val in state.background_asi.items():
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
        level = max(1, min(20, state.level))
        equip_tags = self._equipment_tags(state)
        elements, granted_ids, active_selections = self._collect_elements(state, equip_tags)

        proficiency_bonus = 2 + (level - 1) // 4
        seed_stats: dict[str, float] = {
            "level": float(level),
            "proficiency": float(proficiency_bonus),
        }
        for ab in ABILITIES:
            seed_stats[f"{ab}:total"] = float(state.abilities.get(ab, 10))
            seed_stats[f"{ab}:modifier"] = float(ability_modifier(state.abilities.get(ab, 10)))

        stats = self._compute_stats(elements, granted_ids, state, equip_tags, seed_stats)

        ability_bonuses: dict[str, int] = {}
        ability_totals: dict[str, int] = {}
        ability_modifiers: dict[str, int] = {}
        for ab in ABILITIES:
            bonus = int(round(stats.get(ab, 0.0)))
            total = int(state.abilities.get(ab, 10)) + bonus
            ability_bonuses[ab] = bonus
            ability_totals[ab] = total
            ability_modifiers[ab] = ability_modifier(total)

        proficiency_bonus = 2 + (level - 1) // 4 + int(round(stats.get("proficiency:bonus", 0.0)))

        # Hit Points
        class_el = self.repo.get(state.class_id) if state.class_id else None
        hd_str = class_el.setters.get("hd", "d8") if class_el else "d8"
        hd_num = 8
        m_hd = re.search(r"d(\d+)", hd_str.lower())
        if m_hd:
            hd_num = int(m_hd.group(1))
        con_mod = ability_modifiers["constitution"]
        avg_per_level = (hd_num // 2) + 1
        base_hp = hd_num + max(0, level - 1) * avg_per_level + level * con_mod
        bonus_hp = int(round(stats.get("hp", 0.0)))
        max_hp = max(1, base_hp + bonus_hp)

        # Armor Class
        armor_class = self._compute_ac(state, granted_ids, ability_modifiers, stats)

        # Initiative & Speed
        initiative = ability_modifiers["dexterity"] + int(round(stats.get("initiative", 0.0)))
        speed = int(round(stats.get("innate speed", 0.0) or stats.get("speed", 0.0) or 30))

        # Saving Throws
        saving_throws: dict[str, SavingThrowValue] = {}
        for ab in ABILITIES:
            save_id = f"ID_PROFICIENCY_SAVINGTHROW_{ab.upper()}"
            prof = save_id in granted_ids or any(
                e.type == "Proficiency" and f"{ab} saving throw" in e.name.lower()
                for e in elements
            )
            bonus = ability_modifiers[ab] + (proficiency_bonus if prof else 0)
            saving_throws[ab] = SavingThrowValue(ability=ab, bonus=bonus, proficient=prof)

        # Skills
        skills: dict[str, SkillValue] = {}
        expertise_names = {
            e.name.lower()
            for e in elements
            if "expertise" in e.id.lower() or "expertise" in e.name.lower()
        }
        for skill_name, ab in SKILLS:
            skill_id = SKILL_ID_MAP[skill_name]
            prof = skill_id in granted_ids or any(
                e.type == "Proficiency" and e.name.lower() == f"skill ({skill_name.lower()})"
                for e in elements
            )
            expertise = (
                f"expertise ({skill_name.lower()})" in expertise_names
                or f"{skill_name.lower()} expertise" in expertise_names
                or f"ID_INTERNAL_EXPERTISE_SKILL_{skill_name.upper().replace(' ', '_')}" in granted_ids
            )
            mult = 2 if (prof and expertise) else (1 if prof else 0)
            bonus = ability_modifiers[ab] + mult * proficiency_bonus
            skills[skill_name] = SkillValue(
                name=skill_name,
                ability=ab,
                bonus=bonus,
                proficient=prof,
                expertise=expertise,
            )

        passive_perception = 10 + skills["Perception"].bonus

        # Proficiencies & Languages
        proficiencies = sorted(
            {
                e.name
                for e in elements
                if e.type == "Proficiency"
                and not e.id.startswith("ID_PROFICIENCY_SKILL_")
                and not e.id.startswith("ID_PROFICIENCY_SAVINGTHROW_")
            }
        )
        languages = sorted({e.name for e in elements if e.type == "Language"})

        # Spellcasting
        spellcasting = self._compute_spellcasting(
            elements, class_el, level, ability_modifiers, proficiency_bonus, stats, active_selections
        )

        # Inventory Weight
        total_weight = 0.0
        for item in state.inventory:
            el = self.repo.get(item.element_id)
            w = item.weight if item.weight > 0 else parse_weight_lb(el)
            total_weight += w * max(0, item.quantity)

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
        elements: list[Element],
        class_el: Optional[Element],
        level: int,
        mods: dict[str, int],
        proficiency_bonus: int,
        stats: dict[str, float],
        active_selections: Optional[list[ActiveSelection]] = None,
    ) -> Optional[SpellcastingSummary]:
        sc_info = self._active_spellcasting_info(elements)
        if sc_info is None:
            return None

        ab_key = sc_info.ability.strip().lower()
        if ab_key not in mods:
            ab_key = "intelligence"
        ab_mod = mods[ab_key]
        save_dc = 8 + proficiency_bonus + ab_mod
        attack_bonus = proficiency_bonus + ab_mod

        slots = self._slots_from_elements_or_table(
            elements, class_el, sc_info.name, level, stats=stats
        )
        max_spell_level = max(slots.keys(), default=0)

        # Derive cantrip & spellbook/known limits from active <select type="Spell"> rules
        max_cantrips = 0
        select_known = 0
        for active_sel in active_selections or []:
            if active_sel.rule.type != "Spell":
                continue
            rname = active_sel.rule.name.lower()
            rsup = active_sel.rule.supports.lower()
            if "cantrip" in rname or rsup.endswith(", 0") or rsup.strip() == "0":
                max_cantrips += active_sel.rule.number
            else:
                select_known += active_sel.rule.number

        cname = (class_el.name if class_el else sc_info.name).lower()
        if max_cantrips == 0 and "paladin" not in cname and "ranger" not in cname:
            max_cantrips = 4 if level >= 10 else (3 if level >= 4 else 2)

        max_known_spells: Optional[int] = None
        if "wizard" in cname:
            max_known_spells = max(select_known, 6 + 2 * max(0, level - 1))
        elif select_known > 0:
            max_known_spells = select_known
        elif not sc_info.prepare:
            max_known_spells = max(2, level + 1)

        max_prepared_spells: Optional[int] = None
        if sc_info.prepare:
            if "paladin" in cname or "artificer" in cname:
                max_prepared_spells = max(1, ab_mod + max(1, level // 2))
            else:
                max_prepared_spells = max(1, ab_mod + level)

        granted_spell_ids = [el.id for el in elements if el.type == "Spell"]

        return SpellcastingSummary(
            caster_name=sc_info.name,
            ability=sc_info.ability,
            ability_mod=ab_mod,
            save_dc=save_dc,
            attack_bonus=attack_bonus,
            prepare=sc_info.prepare,
            spell_list=sc_info.spell_list,
            slots=slots,
            max_cantrips=max_cantrips,
            max_known_spells=max_known_spells,
            max_prepared_spells=max_prepared_spells,
            max_spell_level=max_spell_level,
            granted_spell_ids=granted_spell_ids,
        )
