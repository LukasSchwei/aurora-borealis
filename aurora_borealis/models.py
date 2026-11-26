"""Data models for Aurora Borealis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

ABILITIES = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)

ABILITY_ABBR = {
    "strength": "STR",
    "dexterity": "DEX",
    "constitution": "CON",
    "intelligence": "INT",
    "wisdom": "WIS",
    "charisma": "CHA",
}

SKILLS: list[tuple[str, str]] = [
    ("Acrobatics", "dexterity"),
    ("Animal Handling", "wisdom"),
    ("Arcana", "intelligence"),
    ("Athletics", "strength"),
    ("Deception", "charisma"),
    ("History", "intelligence"),
    ("Insight", "wisdom"),
    ("Intimidation", "charisma"),
    ("Investigation", "intelligence"),
    ("Medicine", "wisdom"),
    ("Nature", "intelligence"),
    ("Perception", "wisdom"),
    ("Performance", "charisma"),
    ("Persuasion", "charisma"),
    ("Religion", "intelligence"),
    ("Sleight of Hand", "dexterity"),
    ("Stealth", "dexterity"),
    ("Survival", "wisdom"),
]

SKILL_ID_MAP = {
    name: f"ID_PROFICIENCY_SKILL_{name.upper().replace(' ', '_')}"
    for name, _ in SKILLS
}


@dataclass
class GrantRule:
    type: str
    id: str
    level: int = 1
    requirements: str = ""


@dataclass
class SelectRule:
    type: str
    name: str
    number: int = 1
    supports: str = ""
    level: int = 1
    requirements: str = ""
    optional: bool = False
    items: list[tuple[str, str]] = field(default_factory=list)
    default: str = ""


@dataclass
class StatRule:
    name: str
    value: str
    bonus: str = ""
    level: int = 1
    requirements: str = ""
    equipped: str = ""
    inline: bool = False
    maximum: str = ""
    minimum: str = ""
    alt: str = ""


@dataclass
class SheetAction:
    name: str
    action: str = ""
    usage: str = ""
    alt: str = ""
    description: str = ""
    level: int = 1
    source_element_id: str = ""


@dataclass
class SpellcastingInfo:
    name: str
    ability: str
    prepare: bool = False
    allow_rituals: bool = False
    extend: bool = False
    spell_list: str = ""
    extended: list[str] = field(default_factory=list)


@dataclass
class MulticlassInfo:
    id: str = ""
    prerequisite: str = ""
    requirements: str = ""
    grant_rules: list[GrantRule] = field(default_factory=list)
    select_rules: list[SelectRule] = field(default_factory=list)
    stat_rules: list[StatRule] = field(default_factory=list)


@dataclass
class Element:
    id: str
    name: str
    type: str
    source: str = ""
    supports: list[str] = field(default_factory=list)
    description_html: str = ""
    sheet_description: str = ""
    setters: dict[str, str] = field(default_factory=dict)
    grant_rules: list[GrantRule] = field(default_factory=list)
    select_rules: list[SelectRule] = field(default_factory=list)
    stat_rules: list[StatRule] = field(default_factory=list)
    spellcasting: Optional[SpellcastingInfo] = None
    multiclass: Optional[MulticlassInfo] = None
    sheet_action: str = ""
    sheet_usage: str = ""
    sheet_alt: str = ""
    sheet_descriptions: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class DuplicateEntry:
    kind: str  # "id" or "name"
    element_id: str
    name: str
    element_type: str
    kept_source: str
    duplicate_source: str
    file_path: str = ""


@dataclass
class InventoryItem:
    element_id: str
    name: str
    quantity: int = 1
    equipped: bool = False
    weight: float = 0.0
    category: str = ""
    magic_bonus: int = 0
    enchantment: str = ""
    attuned: bool = False
    container: str = "On Person"
    ignore_weight: bool = False
    notes: str = ""
    charges: int = 0
    max_charges: int = 0
    custom: bool = False


@dataclass
class ClassLevel:
    class_id: str
    level: int = 1


@dataclass
class CharacterState:
    name: str = "New Adventurer"
    player_name: str = "Player One"
    ruleset: str = "5e"  # "5e" or "5.5e"
    gender: str = ""
    faith: str = ""
    alignment_id: str = ""
    deity_id: str = ""
    age: str = ""
    height: str = ""
    weight: str = ""
    eyes: str = ""
    skin: str = ""
    hair: str = ""
    backstory: str = ""
    notes: str = ""
    portrait_path: str = ""
    portrait_base64: str = ""

    race_id: str = ""
    class_id: str = ""
    background_id: str = ""
    level: int = 1
    xp: int = 0
    classes: list[ClassLevel] = field(default_factory=list)
    level_order: list[str] = field(default_factory=list)
    hp_mode: str = "average"  # "average" or "rolled"
    hp_rolls: dict[int, int] = field(default_factory=dict)  # 1-indexed char level -> die result
    level_up_asi: dict[str, dict[str, int]] = field(default_factory=dict)
    level_up_feats: dict[str, str] = field(default_factory=dict)
    spell_sources: dict[str, str] = field(default_factory=dict)
    rule_overrides: dict[str, bool] = field(default_factory=dict)
    weapon_masteries: list[str] = field(default_factory=list)
    heroic_inspiration: bool = False
    exhaustion_level: int = 0
    divine_order_55e: str = ""
    primal_order_55e: str = ""
    animal_forms: list[str] = field(default_factory=list)
    active_animal_form_id: str = ""
    custom_animal_forms: list[dict] = field(default_factory=list)
    companions: list[dict] = field(default_factory=list)

    abilities: dict[str, int] = field(
        default_factory=lambda: {
            "strength": 15,
            "dexterity": 14,
            "constitution": 13,
            "intelligence": 12,
            "wisdom": 10,
            "charisma": 8,
        }
    )
    background_asi: dict[str, int] = field(default_factory=dict)

    selections: dict[str, list[str]] = field(default_factory=dict)
    inventory: list[InventoryItem] = field(default_factory=list)
    currency: dict[str, int] = field(
        default_factory=lambda: {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}
    )
    known_spells: list[str] = field(default_factory=list)
    prepared_spells: list[str] = field(default_factory=list)
    allow_extra_spells: bool = False
    manual_save_profs: list[str] = field(default_factory=list)
    manual_skill_profs: list[str] = field(default_factory=list)
    manual_skill_expertise: list[str] = field(default_factory=list)
    manual_proficiencies: list[str] = field(default_factory=list)
    containers: list[dict] = field(default_factory=list)
    build_plan: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.classes:
            self.sync_from_classes()
        elif self.class_id:
            self.level = max(1, min(20, int(self.level or 1)))
            self.classes = [ClassLevel(self.class_id, self.level)]
            if not self.level_order:
                self.level_order = [self.class_id] * self.level
        else:
            self.level = max(1, min(20, int(self.level or 1)))

    def normalized_classes(self) -> list[ClassLevel]:
        """Return cleaned class list, respecting legacy direct mutations of class_id / level."""
        if not self.classes:
            if self.class_id:
                return [ClassLevel(self.class_id, max(1, min(20, int(self.level or 1))))]
            return []
        if len(self.classes) == 1:
            if not self.class_id:
                return []
            lvl = max(1, min(20, int(self.level or self.classes[0].level or 1)))
            return [ClassLevel(self.class_id, lvl)]

        merged: dict[str, int] = {}
        remaining = 20
        for cl in self.classes:
            if not cl.class_id or cl.level <= 0 or remaining <= 0:
                continue
            take = min(int(cl.level), remaining)
            merged[cl.class_id] = merged.get(cl.class_id, 0) + take
            remaining -= take
        return [ClassLevel(cid, lvl) for cid, lvl in merged.items()]

    def sync_from_classes(self) -> None:
        """Synchronize class_id, level, classes, and level_order consistently."""
        cleaned: dict[str, int] = {}
        remaining = 20
        for cl in self.classes:
            if not cl.class_id or cl.level <= 0 or remaining <= 0:
                continue
            take = min(int(cl.level), remaining)
            cleaned[cl.class_id] = cleaned.get(cl.class_id, 0) + take
            remaining -= take
        self.classes = [ClassLevel(cid, lvl) for cid, lvl in cleaned.items()]

        if self.classes:
            self.class_id = self.classes[0].class_id
            self.level = max(1, min(20, sum(c.level for c in self.classes)))
            self.level_order = self.normalized_level_order()
        else:
            self.class_id = ""
            self.level = max(1, min(20, int(self.level or 1)))
            self.level_order = []

    def normalized_level_order(self) -> list[str]:
        """Return per-level class IDs matching normalized_classes() counts with primary class first."""
        norm = self.normalized_classes()
        if not norm:
            return []
        target_counts = {c.class_id: c.level for c in norm}
        primary_id = norm[0].class_id
        order: list[str] = [primary_id]
        used: dict[str, int] = {primary_id: 1}

        for cid in self.level_order:
            if cid in target_counts and used.get(cid, 0) < target_counts[cid]:
                order.append(cid)
                used[cid] = used.get(cid, 0) + 1

        for cl in norm:
            while used.get(cl.class_id, 0) < cl.level:
                order.append(cl.class_id)
                used[cl.class_id] = used.get(cl.class_id, 0) + 1
        return order

    def has_override(self, key: str) -> bool:
        """Return True if a manual rule override is enabled for this character."""
        if key == "allow_extra_spells":
            return bool(self.allow_extra_spells or self.rule_overrides.get("allow_extra_spells", False))
        return bool(self.rule_overrides.get(key, False))

    def set_override(self, key: str, value: bool) -> None:
        val = bool(value)
        if key == "allow_extra_spells":
            self.allow_extra_spells = val
        self.rule_overrides[key] = val


@dataclass
class ActiveSelection:
    key: str
    rule: SelectRule
    source_element_id: str
    source_element_name: str
    options: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class SkillValue:
    name: str
    ability: str
    bonus: int
    proficient: bool
    expertise: bool


@dataclass
class SavingThrowValue:
    ability: str
    bonus: int
    proficient: bool


@dataclass
class ClassSpellcasting:
    source_class_id: str
    source_class_name: str
    subclass_name: str
    class_level: int
    caster_type: str  # "full", "half", "half_up", "third", "pact"
    ability: str
    ability_mod: int
    save_dc: int
    attack_bonus: int
    prepare: bool
    spell_list: str
    extended_spell_ids: list[str] = field(default_factory=list)
    extended_spell_lists: list[str] = field(default_factory=list)
    school_restrictions: list[str] = field(default_factory=list)
    class_slots: dict[int, int] = field(default_factory=dict)
    max_spell_level: int = 0
    max_cantrips: int = 0
    max_known_spells: Optional[int] = None
    max_prepared_spells: Optional[int] = None
    granted_spell_ids: list[str] = field(default_factory=list)
    always_prepared_spell_ids: list[str] = field(default_factory=list)
    is_pact_magic: bool = False


@dataclass
class SpellcastingSummary:
    caster_name: str
    ability: str
    ability_mod: int
    save_dc: int
    attack_bonus: int
    prepare: bool
    spell_list: str
    slots: dict[int, int] = field(default_factory=dict)
    max_cantrips: int = 0
    max_known_spells: Optional[int] = None
    max_prepared_spells: Optional[int] = None
    max_spell_level: int = 0
    granted_spell_ids: list[str] = field(default_factory=list)
    casters: list[ClassSpellcasting] = field(default_factory=list)
    pact_slots: dict[int, int] = field(default_factory=dict)
    is_multiclass_caster: bool = False
    multiclass_caster_level: int = 0
    always_prepared_spell_ids: list[str] = field(default_factory=list)
    extended_spell_ids: list[str] = field(default_factory=list)
    extended_spell_lists: list[str] = field(default_factory=list)


@dataclass
class ComputedCharacter:
    ability_totals: dict[str, int]
    ability_bonuses: dict[str, int]
    ability_modifiers: dict[str, int]
    proficiency_bonus: int
    max_hp: int
    hit_die: str
    armor_class: int
    initiative: int
    speed: int
    passive_perception: int
    saving_throws: dict[str, SavingThrowValue]
    skills: dict[str, SkillValue]
    granted_elements: list[Element]
    active_selections: list[ActiveSelection]
    proficiencies: list[str]
    languages: list[str]
    spellcasting: Optional[SpellcastingSummary]
    total_weight: float
    stats: dict[str, float] = field(default_factory=dict)
    class_levels: list[tuple[str, str, int]] = field(default_factory=list)
    hit_dice_summary: str = ""
    hp_breakdown: list[dict] = field(default_factory=list)
    weapon_mastery_limit: int = 0
    weapon_mastery_details: list[dict] = field(default_factory=list)
    ruleset_55e_notes: list[str] = field(default_factory=list)
    exhaustion_d20_penalty: int = 0
    passive_investigation: int = 10
    passive_insight: int = 10
    speeds: dict[str, int] = field(default_factory=dict)
    senses: dict[str, int] = field(default_factory=dict)
    damage_resistances: list[str] = field(default_factory=list)
    damage_immunities: list[str] = field(default_factory=list)
    damage_vulnerabilities: list[str] = field(default_factory=list)
    condition_immunities: list[str] = field(default_factory=list)
    sheet_actions: list[SheetAction] = field(default_factory=list)
    resolved_descriptions: dict[str, str] = field(default_factory=dict)
    carrying_capacity: float = 150.0
    carried_weight: float = 0.0
    encumbrance_status: str = "Normal"
