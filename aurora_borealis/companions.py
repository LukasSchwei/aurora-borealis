"""Companion / Familiar / Mount state, templates, scaling engine, .dndcomp XML persistence & PDF sheet."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree
from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from .models import ABILITIES, ABILITY_ABBR, SKILLS, CharacterState, ComputedCharacter


@dataclass
class CompanionTrait:
    name: str
    description: str


@dataclass
class CompanionAction:
    name: str
    attack_bonus: str = ""
    damage: str = ""
    description: str = ""


@dataclass
class CompanionState:
    name: str = "New Companion"
    template_key: str = "custom"
    companion_type: str = "Companion"
    creature_type: str = "Beast"
    size: str = "Medium"
    cr: str = "1/4"
    ruleset: str = "5e"
    owner_name: str = ""
    owner_level: int = 1
    owner_proficiency: int = 2
    owner_spell_attack: int = 5
    owner_ability_mod: int = 3
    scale_with_owner: bool = True
    portrait_path: str = ""
    portrait_base64: str = ""

    ac: int = 13
    max_hp: int = 15
    current_hp: int = 15
    temp_hp: int = 0
    hit_dice: str = "3d8"
    speed: str = "40 ft."
    abilities: dict[str, int] = field(
        default_factory=lambda: {
            "strength": 14,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 8,
            "wisdom": 12,
            "charisma": 10,
        }
    )
    saving_throw_profs: list[str] = field(default_factory=list)
    skill_profs: list[str] = field(default_factory=list)
    senses: str = "Darkvision 60 ft."
    languages: str = "Understands the languages you speak"
    damage_immunities: str = ""
    condition_immunities: str = ""
    traits: list[CompanionTrait] = field(default_factory=list)
    actions: list[CompanionAction] = field(default_factory=list)
    notes: str = ""
    file_path: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "template_key": self.template_key,
            "companion_type": self.companion_type,
            "creature_type": self.creature_type,
            "size": self.size,
            "cr": self.cr,
            "ruleset": self.ruleset,
            "owner_name": self.owner_name,
            "owner_level": self.owner_level,
            "owner_proficiency": self.owner_proficiency,
            "owner_spell_attack": self.owner_spell_attack,
            "owner_ability_mod": self.owner_ability_mod,
            "scale_with_owner": self.scale_with_owner,
            "portrait_path": self.portrait_path,
            "portrait_base64": self.portrait_base64,
            "ac": self.ac,
            "max_hp": self.max_hp,
            "current_hp": self.current_hp,
            "temp_hp": self.temp_hp,
            "hit_dice": self.hit_dice,
            "speed": self.speed,
            "abilities": dict(self.abilities),
            "saving_throw_profs": list(self.saving_throw_profs),
            "skill_profs": list(self.skill_profs),
            "senses": self.senses,
            "languages": self.languages,
            "damage_immunities": self.damage_immunities,
            "condition_immunities": self.condition_immunities,
            "traits": [{"name": t.name, "description": t.description} for t in self.traits],
            "actions": [
                {
                    "name": a.name,
                    "attack_bonus": a.attack_bonus,
                    "damage": a.damage,
                    "description": a.description,
                }
                for a in self.actions
            ],
            "notes": self.notes,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CompanionState:
        ab_raw = data.get("abilities") or {}
        abilities = {ab: int(ab_raw.get(ab, 10)) for ab in ABILITIES}
        traits = [
            CompanionTrait(str(t.get("name", "")), str(t.get("description", "")))
            for t in data.get("traits", [])
            if isinstance(t, dict)
        ]
        actions = [
            CompanionAction(
                str(a.get("name", "")),
                str(a.get("attack_bonus", "")),
                str(a.get("damage", "")),
                str(a.get("description", "")),
            )
            for a in data.get("actions", [])
            if isinstance(a, dict)
        ]
        return cls(
            name=str(data.get("name") or "New Companion"),
            template_key=str(data.get("template_key") or "custom"),
            companion_type=str(data.get("companion_type") or "Companion"),
            creature_type=str(data.get("creature_type") or "Beast"),
            size=str(data.get("size") or "Medium"),
            cr=str(data.get("cr") or "1/4"),
            ruleset=str(data.get("ruleset") or "5e"),
            owner_name=str(data.get("owner_name") or ""),
            owner_level=int(data.get("owner_level", 1)),
            owner_proficiency=int(data.get("owner_proficiency", 2)),
            owner_spell_attack=int(data.get("owner_spell_attack", 5)),
            owner_ability_mod=int(data.get("owner_ability_mod", 3)),
            scale_with_owner=bool(data.get("scale_with_owner", True)),
            portrait_path=str(data.get("portrait_path") or ""),
            portrait_base64=str(data.get("portrait_base64") or ""),
            ac=int(data.get("ac", 13)),
            max_hp=int(data.get("max_hp", 15)),
            current_hp=int(data.get("current_hp", data.get("max_hp", 15))),
            temp_hp=int(data.get("temp_hp", 0)),
            hit_dice=str(data.get("hit_dice") or "3d8"),
            speed=str(data.get("speed") or "40 ft."),
            abilities=abilities,
            saving_throw_profs=[str(x) for x in data.get("saving_throw_profs", [])],
            skill_profs=[str(x) for x in data.get("skill_profs", [])],
            senses=str(data.get("senses") or ""),
            languages=str(data.get("languages") or ""),
            damage_immunities=str(data.get("damage_immunities") or ""),
            condition_immunities=str(data.get("condition_immunities") or ""),
            traits=traits,
            actions=actions,
            notes=str(data.get("notes") or ""),
            file_path=str(data.get("file_path") or ""),
        )


COMPANION_TEMPLATES: dict[str, dict] = {
    "beast_land": {
        "name": "Primal Companion (Beast of the Land)",
        "companion_type": "Primal Companion",
        "creature_type": "Beast",
        "size": "Medium",
        "cr": "PB",
        "ac_base": 13,
        "ac_pb": True,
        "hp_base": 5,
        "hp_per_lvl": 5,
        "speed": "40 ft., climb 40 ft.",
        "abilities": {"strength": 14, "dexterity": 14, "constitution": 15, "intelligence": 8, "wisdom": 14, "charisma": 11},
        "senses": "Darkvision 60 ft.",
        "traits": [("Primal Bond", "Add your Proficiency Bonus to any ability check or saving throw the beast makes."), ("Charge", "If the beast moves at least 20 ft straight toward a target and hits with Maul, it deals +1d6 slashing and knocks Prone.")],
        "actions": [("Maul", "Spell Attack", "1d8 + 2 + PB", "Melee Weapon Attack: your spell attack modifier to hit.")],
    },
    "beast_sea": {
        "name": "Primal Companion (Beast of the Sea)",
        "companion_type": "Primal Companion",
        "creature_type": "Beast",
        "size": "Medium",
        "cr": "PB",
        "ac_base": 13,
        "ac_pb": True,
        "hp_base": 5,
        "hp_per_lvl": 5,
        "speed": "5 ft., swim 60 ft.",
        "abilities": {"strength": 14, "dexterity": 14, "constitution": 15, "intelligence": 8, "wisdom": 14, "charisma": 11},
        "senses": "Darkvision 60 ft.",
        "traits": [("Amphibious", "Can breathe air and water."), ("Primal Bond", "Add your Proficiency Bonus to ability checks and saving throws.")],
        "actions": [("Binding Strike", "Spell Attack", "1d6 + 2 + PB", "Melee Weapon Attack; target is Grappled (escape DC = Spell Save DC).")],
    },
    "beast_sky": {
        "name": "Primal Companion (Beast of the Sky)",
        "companion_type": "Primal Companion",
        "creature_type": "Beast",
        "size": "Small",
        "cr": "PB",
        "ac_base": 13,
        "ac_pb": True,
        "hp_base": 4,
        "hp_per_lvl": 4,
        "speed": "10 ft., fly 60 ft.",
        "abilities": {"strength": 6, "dexterity": 16, "constitution": 13, "intelligence": 8, "wisdom": 14, "charisma": 11},
        "senses": "Darkvision 60 ft.",
        "traits": [("Flyby", "Does not provoke opportunity attacks when flying out of enemy reach."), ("Primal Bond", "Add your Proficiency Bonus to ability checks and saving throws.")],
        "actions": [("Shred", "Spell Attack", "1d4 + 3 + PB", "Melee Weapon Attack: your spell attack modifier to hit.")],
    },
    "steel_defender": {
        "name": "Steel Defender",
        "companion_type": "Artificer Companion",
        "creature_type": "Construct",
        "size": "Medium",
        "cr": "PB",
        "ac_base": 15,
        "ac_pb": False,
        "hp_base": 2,
        "hp_per_lvl": 5,
        "hp_add_mod": True,
        "speed": "40 ft.",
        "abilities": {"strength": 14, "dexterity": 12, "constitution": 14, "intelligence": 4, "wisdom": 10, "charisma": 6},
        "saving_throw_profs": ["dexterity", "constitution"],
        "skill_profs": ["Athletics", "Perception"],
        "senses": "Darkvision 60 ft.",
        "damage_immunities": "Poison",
        "condition_immunities": "Charmed, Exhaustion, Poisoned",
        "traits": [("Vigilant", "The defender can't be surprised.")],
        "actions": [
            ("Force-Empowered Rend", "Spell Attack", "1d8 + PB force", "Melee Weapon Attack: your spell attack modifier to hit."),
            ("Repair (3/Day)", "", "2d8 + PB", "Restores hit points to itself or a construct/object within 5 ft."),
            ("Deflect Attack (Reaction)", "", "", "Imposes Disadvantage on an attack roll against another target within 5 ft."),
        ],
    },
    "homunculus": {
        "name": "Homunculus Servant",
        "companion_type": "Artificer Companion",
        "creature_type": "Construct",
        "size": "Tiny",
        "cr": "PB",
        "ac_base": 13,
        "ac_pb": False,
        "hp_base": 1,
        "hp_per_lvl": 1,
        "hp_add_mod": True,
        "speed": "20 ft., fly 30 ft.",
        "abilities": {"strength": 4, "dexterity": 15, "constitution": 12, "intelligence": 10, "wisdom": 10, "charisma": 7},
        "saving_throw_profs": ["dexterity"],
        "skill_profs": ["Perception", "Stealth"],
        "senses": "Darkvision 60 ft.",
        "damage_immunities": "Poison",
        "condition_immunities": "Exhaustion, Poisoned",
        "traits": [("Evasion", "Takes no damage on successful DEX save, half on fail."), ("Channel Magic", "Delivers touch spells cast by you within 120 ft.")],
        "actions": [("Force Strike", "Spell Attack", "1d4 + PB force", "Ranged Weapon Attack (30 ft.): your spell attack modifier to hit.")],
    },
    "drake": {
        "name": "Drake Companion",
        "companion_type": "Drakewarden Companion",
        "creature_type": "Dragon",
        "size": "Small",
        "cr": "PB",
        "ac_base": 14,
        "ac_pb": True,
        "hp_base": 5,
        "hp_per_lvl": 5,
        "speed": "40 ft.",
        "abilities": {"strength": 16, "dexterity": 12, "constitution": 15, "intelligence": 8, "wisdom": 14, "charisma": 8},
        "saving_throw_profs": ["dexterity", "wisdom"],
        "senses": "Darkvision 60 ft.",
        "languages": "Draconic",
        "traits": [("Draconic Essence", "Resistance to chosen elemental damage type (Acid, Cold, Fire, Lightning, or Poison)."), ("Infused Strikes (Reaction)", "Add +1d6 elemental damage to a nearby ally's weapon hit.")],
        "actions": [("Bite", "+3 + PB", "1d6 + PB", "Melee Weapon Attack: +3 + your Proficiency Bonus to hit.")],
    },
    "wildfire_spirit": {
        "name": "Wildfire Spirit",
        "companion_type": "Druid Spirit",
        "creature_type": "Elemental",
        "size": "Small",
        "cr": "PB",
        "ac_base": 13,
        "ac_pb": False,
        "hp_base": 5,
        "hp_per_lvl": 5,
        "speed": "30 ft., fly 30 ft. (hover)",
        "abilities": {"strength": 10, "dexterity": 14, "constitution": 14, "intelligence": 13, "wisdom": 15, "charisma": 11},
        "senses": "Darkvision 60 ft.",
        "damage_immunities": "Fire",
        "condition_immunities": "Charmed, Frightened, Grappled, Prone, Restrained",
        "traits": [("Enhanced Bond", "Add +1d8 to fire damage or healing spells cast through the spirit.")],
        "actions": [
            ("Flame Seed", "Spell Attack", "1d6 + PB fire", "Ranged Weapon Attack (60 ft.)."),
            ("Fiery Teleportation", "", "1d6 + PB fire", "Teleport 15 ft; deals fire damage to enemies within 5 ft."),
        ],
    },
    "otherworldly_steed": {
        "name": "Otherworldly Steed (2024)",
        "companion_type": "Paladin Steed",
        "creature_type": "Celestial / Fey / Fiend",
        "size": "Large",
        "cr": "Spell Level",
        "ac_base": 14,
        "ac_pb": False,
        "hp_base": 15,
        "hp_per_lvl": 5,
        "speed": "60 ft.",
        "abilities": {"strength": 18, "dexterity": 12, "constitution": 14, "intelligence": 10, "wisdom": 12, "charisma": 8},
        "senses": "Telepathy 1 mile",
        "traits": [("Life Bond", "When you regain HP from a spell, the steed also regains the same amount while within 5 ft.")],
        "actions": [("Otherworldly Slam", "Spell Attack", "1d8 + Spell Level", "Celestial (radiant), Fey (psychic), or Fiend (necrotic).")],
    },
    "familiar_owl": {
        "name": "Owl Familiar",
        "companion_type": "Familiar",
        "creature_type": "Beast / Fey",
        "size": "Tiny",
        "cr": "0",
        "ac_base": 11,
        "ac_pb": False,
        "hp_base": 1,
        "hp_per_lvl": 0,
        "speed": "5 ft., fly 60 ft.",
        "abilities": {"strength": 3, "dexterity": 13, "constitution": 8, "intelligence": 2, "wisdom": 12, "charisma": 7},
        "skill_profs": ["Perception", "Stealth"],
        "senses": "Darkvision 120 ft.",
        "traits": [("Flyby", "Does not provoke opportunity attacks when flying out of enemy reach."), ("Keen Hearing and Sight", "Advantage on Perception checks relying on hearing or sight.")],
        "actions": [("Help", "", "", "Grants Advantage on ally's next attack roll.")],
    },
    "familiar_cat": {
        "name": "Cat Familiar",
        "companion_type": "Familiar",
        "creature_type": "Beast / Fey",
        "size": "Tiny",
        "cr": "0",
        "ac_base": 12,
        "ac_pb": False,
        "hp_base": 2,
        "hp_per_lvl": 0,
        "speed": "40 ft., climb 30 ft.",
        "abilities": {"strength": 3, "dexterity": 15, "constitution": 10, "intelligence": 3, "wisdom": 12, "charisma": 7},
        "skill_profs": ["Perception", "Stealth"],
        "senses": "Darkvision 60 ft.",
        "traits": [("Keen Smell", "Advantage on Perception checks relying on smell.")],
        "actions": [("Claws", "+0", "1 slashing", "Melee Weapon Attack.")],
    },
    "familiar_imp": {
        "name": "Imp Familiar (Pact of the Chain)",
        "companion_type": "Familiar",
        "creature_type": "Fiend",
        "size": "Tiny",
        "cr": "1",
        "ac_base": 13,
        "ac_pb": False,
        "hp_base": 10,
        "hp_per_lvl": 0,
        "speed": "20 ft., fly 40 ft.",
        "abilities": {"strength": 6, "dexterity": 17, "constitution": 13, "intelligence": 11, "wisdom": 12, "charisma": 14},
        "skill_profs": ["Deception", "Insight", "Persuasion", "Stealth"],
        "senses": "Darkvision 120 ft.",
        "damage_immunities": "Fire, Poison",
        "condition_immunities": "Poisoned",
        "traits": [("Devil's Sight", "Magical darkness doesn't impede darkvision."), ("Magic Resistance", "Advantage on saving throws against spells.")],
        "actions": [("Sting", "+5", "1d4+3 piercing + 3d6 poison", "CON save DC 11 for half poison damage.")],
    },
    "warhorse": {
        "name": "Warhorse Mount",
        "companion_type": "Mount",
        "creature_type": "Beast",
        "size": "Large",
        "cr": "1/2",
        "ac_base": 11,
        "ac_pb": False,
        "hp_base": 19,
        "hp_per_lvl": 0,
        "speed": "60 ft.",
        "abilities": {"strength": 18, "dexterity": 12, "constitution": 13, "intelligence": 2, "wisdom": 12, "charisma": 7},
        "senses": "Passive Perception 11",
        "traits": [("Trampling Charge", "If moving 20+ ft straight, DC 14 STR save or Prone + bonus Hooves attack.")],
        "actions": [("Hooves", "+6", "2d6+4 bludgeoning", "Melee Weapon Attack.")],
    },
    "custom": {
        "name": "Custom Companion",
        "companion_type": "Custom",
        "creature_type": "Beast",
        "size": "Medium",
        "cr": "1",
        "ac_base": 13,
        "ac_pb": False,
        "hp_base": 10,
        "hp_per_lvl": 4,
        "speed": "30 ft.",
        "abilities": {"strength": 12, "dexterity": 14, "constitution": 14, "intelligence": 8, "wisdom": 12, "charisma": 10},
        "senses": "Darkvision 60 ft.",
        "traits": [],
        "actions": [("Strike", "+4", "1d6+2", "Melee Weapon Attack.")],
    },
}


def create_companion_from_template(
    template_key: str,
    owner_state: Optional[CharacterState] = None,
    owner_comp: Optional[ComputedCharacter] = None,
) -> CompanionState:
    tpl = COMPANION_TEMPLATES.get(template_key, COMPANION_TEMPLATES["custom"])
    owner_lvl = owner_state.level if owner_state else 1
    owner_pb = owner_comp.proficiency_bonus if owner_comp else 2
    owner_sc = owner_comp.spellcasting if owner_comp else None
    owner_atk = owner_sc.attack_bonus if owner_sc else (owner_pb + 3)
    owner_mod = owner_sc.ability_mod if owner_sc else 3

    ac_val = tpl["ac_base"] + (owner_pb if tpl.get("ac_pb") else 0)
    hp_val = tpl["hp_base"] + tpl.get("hp_per_lvl", 0) * owner_lvl + (owner_mod if tpl.get("hp_add_mod") else 0)
    hp_val = max(1, hp_val)

    return CompanionState(
        name=tpl["name"],
        template_key=template_key,
        companion_type=tpl["companion_type"],
        creature_type=tpl["creature_type"],
        size=tpl["size"],
        cr=tpl["cr"],
        ruleset=owner_state.ruleset if owner_state else "5e",
        owner_name=owner_state.name if owner_state else "",
        owner_level=owner_lvl,
        owner_proficiency=owner_pb,
        owner_spell_attack=owner_atk,
        owner_ability_mod=owner_mod,
        scale_with_owner=tpl.get("hp_per_lvl", 0) > 0 or bool(tpl.get("ac_pb")),
        ac=ac_val,
        max_hp=hp_val,
        current_hp=hp_val,
        hit_dice=f"{max(1, owner_lvl)}d8" if tpl.get("hp_per_lvl", 0) > 0 else "1d4",
        speed=tpl["speed"],
        abilities=dict(tpl["abilities"]),
        saving_throw_profs=list(tpl.get("saving_throw_profs", [])),
        skill_profs=list(tpl.get("skill_profs", [])),
        senses=tpl.get("senses", ""),
        damage_immunities=tpl.get("damage_immunities", ""),
        condition_immunities=tpl.get("condition_immunities", ""),
        traits=[CompanionTrait(n, d) for n, d in tpl.get("traits", [])],
        actions=[CompanionAction(n, ab, dmg, desc) for n, ab, dmg, desc in tpl.get("actions", [])],
    )


def compute_companion_stats(comp: CompanionState) -> dict:
    """Compute effective AC, HP, modifiers, saves, skills, and scaled attack strings."""
    pb = comp.owner_proficiency if comp.scale_with_owner else max(2, 2 + (comp.owner_level - 1) // 4)
    tpl = COMPANION_TEMPLATES.get(comp.template_key)
    eff_ac = comp.ac
    eff_hp = comp.max_hp
    if comp.scale_with_owner and tpl is not None:
        eff_ac = tpl["ac_base"] + (pb if tpl.get("ac_pb") else 0)
        eff_hp = max(
            1,
            tpl["hp_base"]
            + tpl.get("hp_per_lvl", 0) * comp.owner_level
            + (comp.owner_ability_mod if tpl.get("hp_add_mod") else 0),
        )

    mods = {ab: (comp.abilities.get(ab, 10) - 10) // 2 for ab in ABILITIES}
    saves = {
        ab: mods[ab] + (pb if ab in comp.saving_throw_profs else 0)
        for ab in ABILITIES
    }
    skills = {
        sk_name: mods[ab] + (pb if sk_name in comp.skill_profs else 0)
        for sk_name, ab in SKILLS
    }
    passive_perc = 10 + skills.get("Perception", mods["wisdom"])
    return {
        "ac": eff_ac,
        "max_hp": eff_hp,
        "proficiency": pb,
        "mods": mods,
        "saves": saves,
        "skills": skills,
        "passive_perception": passive_perc,
    }


def save_dndcomp(comp: CompanionState, path: Path) -> None:
    """Save a standalone .dndcomp XML companion file."""
    path = Path(path)
    stats = compute_companion_stats(comp)
    root = etree.Element("companion", version="1.0")

    disp = etree.SubElement(root, "display-properties")
    etree.SubElement(disp, "name").text = comp.name
    etree.SubElement(disp, "type").text = comp.companion_type
    etree.SubElement(disp, "creature-type").text = comp.creature_type
    etree.SubElement(disp, "size").text = comp.size
    etree.SubElement(disp, "cr").text = comp.cr
    etree.SubElement(disp, "ruleset").text = comp.ruleset or "5e"
    etree.SubElement(disp, "owner").text = comp.owner_name
    etree.SubElement(disp, "level").text = str(comp.owner_level)
    etree.SubElement(disp, "ac").text = str(stats["ac"])
    etree.SubElement(disp, "hp").text = str(stats["max_hp"])
    etree.SubElement(disp, "speed").text = comp.speed
    if comp.portrait_path:
        etree.SubElement(disp, "portrait").text = comp.portrait_path
    if comp.portrait_base64:
        etree.SubElement(disp, "portrait-data").text = comp.portrait_base64

    body = etree.SubElement(root, "data")
    etree.SubElement(body, "template").text = comp.template_key
    etree.SubElement(body, "scale-with-owner").text = "true" if comp.scale_with_owner else "false"
    etree.SubElement(body, "owner-proficiency").text = str(comp.owner_proficiency)
    etree.SubElement(body, "owner-spell-attack").text = str(comp.owner_spell_attack)
    etree.SubElement(body, "owner-ability-mod").text = str(comp.owner_ability_mod)
    etree.SubElement(body, "ac").text = str(comp.ac)
    etree.SubElement(body, "max-hp").text = str(comp.max_hp)
    etree.SubElement(body, "current-hp").text = str(comp.current_hp)
    etree.SubElement(body, "temp-hp").text = str(comp.temp_hp)
    etree.SubElement(body, "hit-dice").text = comp.hit_dice
    etree.SubElement(body, "speed").text = comp.speed
    etree.SubElement(body, "senses").text = comp.senses
    etree.SubElement(body, "languages").text = comp.languages
    etree.SubElement(body, "damage-immunities").text = comp.damage_immunities
    etree.SubElement(body, "condition-immunities").text = comp.condition_immunities
    etree.SubElement(body, "notes").text = comp.notes

    ab_node = etree.SubElement(body, "abilities")
    for ab in ABILITIES:
        etree.SubElement(ab_node, ab).text = str(comp.abilities.get(ab, 10))

    saves_node = etree.SubElement(body, "saving-throws")
    for sv in comp.saving_throw_profs:
        etree.SubElement(saves_node, "save").text = sv

    skills_node = etree.SubElement(body, "skills")
    for sk in comp.skill_profs:
        etree.SubElement(skills_node, "skill").text = sk

    traits_node = etree.SubElement(body, "traits")
    for tr in comp.traits:
        tn = etree.SubElement(traits_node, "trait", name=tr.name)
        tn.text = tr.description

    actions_node = etree.SubElement(body, "actions")
    for act in comp.actions:
        an = etree.SubElement(
            actions_node,
            "action",
            name=act.name,
            attack=act.attack_bonus,
            damage=act.damage,
        )
        an.text = act.description

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True))


def load_dndcomp(path: Path) -> CompanionState:
    """Load a standalone .dndcomp XML companion file."""
    path = Path(path)
    parser = etree.XMLParser(recover=True, remove_comments=True)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    if root is None:
        raise ValueError(f"Invalid .dndcomp file: {path}")

    comp = CompanionState(file_path=str(path))
    disp = root.find("display-properties")
    if disp is not None:
        comp.name = (disp.findtext("name") or comp.name).strip()
        comp.companion_type = (disp.findtext("type") or comp.companion_type).strip()
        comp.creature_type = (disp.findtext("creature-type") or comp.creature_type).strip()
        comp.size = (disp.findtext("size") or comp.size).strip()
        comp.cr = (disp.findtext("cr") or comp.cr).strip()
        comp.ruleset = (disp.findtext("ruleset") or comp.ruleset).strip()
        comp.owner_name = (disp.findtext("owner") or "").strip()
        lvl_s = (disp.findtext("level") or "1").strip()
        if lvl_s.isdigit():
            comp.owner_level = max(1, min(20, int(lvl_s)))
        comp.portrait_path = (disp.findtext("portrait") or "").strip()
        comp.portrait_base64 = (disp.findtext("portrait-data") or "").strip()

    body = root.find("data")
    if body is not None:
        comp.template_key = (body.findtext("template") or comp.template_key).strip()
        comp.scale_with_owner = (body.findtext("scale-with-owner") or "true").strip().lower() == "true"
        for tag, attr in (
            ("owner-proficiency", "owner_proficiency"),
            ("owner-spell-attack", "owner_spell_attack"),
            ("owner-ability-mod", "owner_ability_mod"),
            ("ac", "ac"),
            ("max-hp", "max_hp"),
            ("current-hp", "current_hp"),
            ("temp-hp", "temp_hp"),
        ):
            val = (body.findtext(tag) or "").strip()
            if val.lstrip("-").isdigit():
                setattr(comp, attr, int(val))
        comp.hit_dice = (body.findtext("hit-dice") or comp.hit_dice).strip()
        comp.speed = (body.findtext("speed") or comp.speed).strip()
        comp.senses = (body.findtext("senses") or "").strip()
        comp.languages = (body.findtext("languages") or "").strip()
        comp.damage_immunities = (body.findtext("damage-immunities") or "").strip()
        comp.condition_immunities = (body.findtext("condition-immunities") or "").strip()
        comp.notes = (body.findtext("notes") or "").strip()

        ab_node = body.find("abilities")
        if ab_node is not None:
            for ab in ABILITIES:
                v = (ab_node.findtext(ab) or "").strip()
                if v.isdigit():
                    comp.abilities[ab] = int(v)

        comp.saving_throw_profs = [
            (n.text or "").strip().lower()
            for n in body.findall("saving-throws/save")
            if (n.text or "").strip()
        ]
        comp.skill_profs = [
            (n.text or "").strip()
            for n in body.findall("skills/skill")
            if (n.text or "").strip()
        ]
        comp.traits = [
            CompanionTrait(
                name=(n.get("name") or "").strip(),
                description=(n.text or "").strip(),
            )
            for n in body.findall("traits/trait")
        ]
        comp.actions = [
            CompanionAction(
                name=(n.get("name") or "").strip(),
                attack_bonus=(n.get("attack") or "").strip(),
                damage=(n.get("damage") or "").strip(),
                description=(n.text or "").strip(),
            )
            for n in body.findall("actions/action")
        ]
    return comp


def _fmt_signed(val: int) -> str:
    return f"+{val}" if val >= 0 else str(val)


def render_companion_sheet_html(comp: CompanionState, for_pdf: bool = False) -> str:
    """Render a full stat-block & character sheet HTML for a Companion."""
    stats = compute_companion_stats(comp)
    fg = "#111827" if for_pdf else "#eef0f3"
    muted = "#4b5563" if for_pdf else "#9aa0a6"
    card_bg = "#f8fafc" if for_pdf else "#1d1f24"
    border = "#cbd5e1" if for_pdf else "#2c2f36"
    accent = "#0f766e" if for_pdf else "#34d399"

    ab_cells = "".join(
        f"<td align='center' style='border:1px solid {border}; background:{card_bg}; padding:6px;'>"
        f"<b style='color:{muted};'>{ABILITY_ABBR[ab]}</b><br/>"
        f"<span style='font-size:12pt; font-weight:bold;'>{comp.abilities.get(ab, 10)}</span> "
        f"<span style='color:{accent};'>({_fmt_signed(stats['mods'][ab])})</span></td>"
        for ab in ABILITIES
    )
    saves_txt = ", ".join(
        f"{'*' if ab in comp.saving_throw_profs else ''}{ABILITY_ABBR[ab]} {_fmt_signed(stats['saves'][ab])}"
        for ab in ABILITIES
    )
    skills_txt = ", ".join(
        f"<b>{sk}</b> {_fmt_signed(stats['skills'][sk])}"
        for sk in comp.skill_profs
        if sk in stats["skills"]
    ) or "None"

    traits_html = "".join(
        f"<p><b>{html.escape(t.name)}.</b> {html.escape(t.description)}</p>"
        for t in comp.traits
    ) or f"<p style='color:{muted};'>None</p>"

    actions_html = "".join(
        f"<p><b>{html.escape(a.name)}</b>"
        + (f" <i>({html.escape(a.attack_bonus)}" if a.attack_bonus else "")
        + (f", {html.escape(a.damage)}" if a.attack_bonus and a.damage else (f" <i>({html.escape(a.damage)}" if a.damage else ""))
        + (")</i>" if (a.attack_bonus or a.damage) else "")
        + f". {html.escape(a.description)}</p>"
        for a in comp.actions
    ) or f"<p style='color:{muted};'>None</p>"

    portrait_td = ""
    if comp.portrait_base64:
        portrait_td = (
            f"<td width='74' align='right' valign='middle'>"
            f"<img src='data:image/png;base64,{comp.portrait_base64}' width='66' height='66' /></td>"
        )

    owner_txt = f" • Master: {comp.owner_name} (Lv {comp.owner_level})" if comp.owner_name else ""
    return f"""
    <html>
    <body style='font-family:sans-serif; font-size:9.8pt; color:{fg};'>
      <div style='background-color:#162a24; color:#ffffff; padding:10px 14px; border-radius:6px;'>
        <table width='100%' cellspacing='0' cellpadding='0'>
          <tr>
            <td valign='middle'>
              <h2 style='margin:0; color:#ffffff;'>{html.escape(comp.name)}</h2>
              <div style='color:#a7f3d0; font-size:9.5pt;'>
                {html.escape(comp.size)} {html.escape(comp.creature_type)} • {html.escape(comp.companion_type)} • CR {html.escape(comp.cr)}{html.escape(owner_txt)}
              </div>
            </td>
            {portrait_td}
          </tr>
        </table>
      </div>
      <p style='margin-top:10px;'>
        <b>Armor Class:</b> {stats['ac']} &nbsp;|&nbsp;
        <b>Hit Points:</b> {comp.current_hp} / {stats['max_hp']} (Temp: {comp.temp_hp}, Hit Dice: {html.escape(comp.hit_dice)}) &nbsp;|&nbsp;
        <b>Speed:</b> {html.escape(comp.speed)} &nbsp;|&nbsp;
        <b>PB:</b> +{stats['proficiency']} &nbsp;|&nbsp;
        <b>Passive Perception:</b> {stats['passive_perception']}
      </p>
      <table width='100%' cellspacing='4' cellpadding='2'><tr>{ab_cells}</tr></table>
      <p><b>Saving Throws:</b> {html.escape(saves_txt)}</p>
      <p><b>Skill Proficiencies:</b> {skills_txt}</p>
      <p><b>Senses:</b> {html.escape(comp.senses or '—')} &nbsp;|&nbsp; <b>Languages:</b> {html.escape(comp.languages or '—')}</p>
      {f"<p><b>Damage Immunities:</b> {html.escape(comp.damage_immunities)}</p>" if comp.damage_immunities else ""}
      {f"<p><b>Condition Immunities:</b> {html.escape(comp.condition_immunities)}</p>" if comp.condition_immunities else ""}
      <hr/>
      <h3 style='color:{accent}; margin-bottom:4px;'>Traits</h3>
      {traits_html}
      <h3 style='color:{accent}; margin-bottom:4px;'>Actions</h3>
      {actions_html}
      {f"<hr/><h3 style='color:{accent}; margin-bottom:4px;'>Notes</h3><p>{html.escape(comp.notes)}</p>" if comp.notes else ""}
    </body>
    </html>
    """


def export_companion_pdf(comp: CompanionState, output_path: Path) -> None:
    """Export a standalone printable Companion character sheet PDF."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(output_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter)
    writer.setTitle(f"{comp.name} — Companion Sheet")
    doc = QTextDocument()
    doc.setHtml(render_companion_sheet_html(comp, for_pdf=True))
    doc.print_(writer)
