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


@dataclass
class SpellcastingInfo:
    name: str
    ability: str
    prepare: bool = False
    allow_rituals: bool = False
    extend: bool = False
    spell_list: str = ""


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
