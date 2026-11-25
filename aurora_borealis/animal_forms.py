"""Animal Forms / Wild Shape catalog, 5e/5.5e eligibility rules, and transformed stat calculation."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Optional

from .loader import ContentRepository
from .models import ABILITIES, ABILITY_ABBR, CharacterState, ComputedCharacter


@dataclass(frozen=True)
class AnimalForm:
    id: str
    name: str
    cr: float
    cr_label: str
    size: str
    creature_type: str
    ac: int
    hp: int
    speed: str
    walk_speed: int
    swim_speed: int
    fly_speed: int
    abilities: dict[str, int]
    senses: str
    traits: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    category: str = "Beast"


def _ab(s: int, d: int, c: int, i: int, w: int, ch: int) -> dict[str, int]:
    return {
        "strength": s,
        "dexterity": d,
        "constitution": c,
        "intelligence": i,
        "wisdom": w,
        "charisma": ch,
    }


ANIMAL_FORMS: list[AnimalForm] = [
    AnimalForm("cat", "Cat", 0.0, "0", "Tiny", "Beast", 12, 2, "40 ft., climb 30 ft.", 40, 0, 0, _ab(3, 15, 10, 3, 12, 7), "Darkvision 60 ft., PP 13", ["Keen Smell"], ["Claws (+0, 1 slashing)"]),
    AnimalForm("owl", "Owl", 0.0, "0", "Tiny", "Beast", 11, 1, "5 ft., fly 60 ft.", 5, 0, 60, _ab(3, 13, 8, 2, 12, 7), "Darkvision 120 ft., PP 13", ["Flyby", "Keen Hearing and Sight"], ["Talons (+3, 1 slashing)"]),
    AnimalForm("hawk", "Hawk", 0.0, "0", "Tiny", "Beast", 11, 1, "10 ft., fly 60 ft.", 10, 0, 60, _ab(5, 16, 8, 2, 14, 6), "PP 14", ["Keen Sight"], ["Talons (+5, 1 slashing)"]),
    AnimalForm("rat", "Rat", 0.0, "0", "Tiny", "Beast", 10, 1, "20 ft.", 20, 0, 0, _ab(2, 11, 9, 2, 10, 4), "Darkvision 30 ft., PP 10", ["Keen Smell"], ["Bite (+0, 1 piercing)"]),
    AnimalForm("spider", "Spider", 0.0, "0", "Tiny", "Beast", 12, 1, "20 ft., climb 20 ft.", 20, 0, 0, _ab(2, 14, 8, 1, 10, 2), "Darkvision 30 ft., PP 10", ["Spider Climb", "Web Sense", "Web Walker"], ["Bite (+4, 1 piercing + 1d4 poison)"]),
    AnimalForm("frog", "Frog", 0.0, "0", "Tiny", "Beast", 11, 1, "20 ft., swim 20 ft.", 20, 20, 0, _ab(1, 13, 8, 1, 8, 3), "Darkvision 30 ft., PP 9", ["Amphibious", "Standing Leap"], []),
    AnimalForm("bat", "Bat", 0.0, "0", "Tiny", "Beast", 12, 1, "5 ft., fly 30 ft.", 5, 0, 30, _ab(2, 15, 8, 2, 12, 4), "Blindsight 60 ft., PP 11", ["Echolocation", "Keen Hearing"], ["Bite (+0, 1 piercing)"]),
    AnimalForm("octopus", "Octopus", 0.0, "0", "Small", "Beast", 12, 3, "5 ft., swim 30 ft.", 5, 30, 0, _ab(4, 15, 11, 3, 10, 4), "Darkvision 30 ft., PP 12", ["Hold Breath", "Underwater Camouflage"], ["Tentacles (+4, 1 bludgeoning + grapple)", "Ink Cloud"]),
    AnimalForm("mastiff", "Mastiff", 0.125, "1/8", "Medium", "Beast", 12, 5, "40 ft.", 40, 0, 0, _ab(13, 14, 12, 3, 12, 7), "PP 13", ["Keen Hearing and Smell"], ["Bite (+3, 1d6+1 piercing, DC 11 STR or prone)"]),
    AnimalForm("blood_hawk", "Blood Hawk", 0.125, "1/8", "Small", "Beast", 12, 7, "10 ft., fly 60 ft.", 10, 0, 60, _ab(6, 14, 10, 3, 14, 5), "PP 14", ["Keen Sight", "Pack Tactics"], ["Beak (+4, 1d4+2 piercing)"]),
    AnimalForm("giant_crab", "Giant Crab", 0.125, "1/8", "Medium", "Beast", 15, 13, "30 ft., swim 30 ft.", 30, 30, 0, _ab(13, 15, 11, 1, 9, 3), "Blindsight 30 ft., PP 9", ["Amphibious"], ["Claw (+3, 1d6+1 bludgeoning + grapple)"]),
    AnimalForm("wolf", "Wolf", 0.25, "1/4", "Medium", "Beast", 13, 11, "40 ft.", 40, 0, 0, _ab(12, 15, 12, 3, 12, 6), "PP 13", ["Keen Hearing and Smell", "Pack Tactics"], ["Bite (+4, 2d4+2 piercing, DC 11 STR or prone)"]),
    AnimalForm("panther", "Panther", 0.25, "1/4", "Medium", "Beast", 12, 13, "50 ft., climb 40 ft.", 50, 0, 0, _ab(14, 15, 10, 3, 14, 7), "PP 14", ["Keen Smell", "Pounce"], ["Bite (+4, 1d6+2 piercing)", "Claw (+4, 1d4+2 slashing)"]),
    AnimalForm("riding_horse", "Riding Horse", 0.25, "1/4", "Large", "Beast", 10, 13, "60 ft.", 60, 0, 0, _ab(16, 10, 12, 2, 11, 7), "PP 10", [], ["Hooves (+5, 2d4+3 bludgeoning)"]),
    AnimalForm("elk", "Elk", 0.25, "1/4", "Large", "Beast", 10, 13, "50 ft.", 50, 0, 0, _ab(16, 10, 12, 2, 10, 6), "PP 10", ["Charge (+2d6 & prone)"], ["Ram (+5, 1d6+3 bludgeoning)", "Hooves (+5, 2d4+3 bludgeoning)"]),
    AnimalForm("giant_badger", "Giant Badger", 0.25, "1/4", "Medium", "Beast", 10, 13, "30 ft., burrow 10 ft.", 30, 0, 0, _ab(13, 10, 15, 2, 12, 5), "Darkvision 30 ft., PP 11", ["Keen Smell"], ["Multiattack (Bite + Claws)"]),
    AnimalForm("giant_frog", "Giant Frog", 0.25, "1/4", "Medium", "Beast", 11, 18, "30 ft., swim 30 ft.", 30, 30, 0, _ab(12, 13, 11, 2, 10, 3), "Darkvision 30 ft., PP 10", ["Amphibious", "Standing Leap"], ["Bite (+3, 1d6+1 piercing + grapple)", "Swallow"]),
    AnimalForm("giant_owl", "Giant Owl", 0.25, "1/4", "Large", "Beast", 12, 19, "5 ft., fly 60 ft.", 5, 0, 60, _ab(13, 15, 12, 8, 13, 10), "Darkvision 120 ft., PP 15", ["Flyby", "Keen Hearing and Sight"], ["Talons (+3, 2d6+1 slashing)"]),
    AnimalForm("boar", "Boar", 0.25, "1/4", "Medium", "Beast", 11, 11, "40 ft.", 40, 0, 0, _ab(13, 11, 12, 2, 9, 5), "PP 9", ["Charge", "Relentless"], ["Tusk (+3, 1d6+1 slashing)"]),
    AnimalForm("constrictor_snake", "Constrictor Snake", 0.25, "1/4", "Large", "Beast", 12, 13, "30 ft., swim 30 ft.", 30, 30, 0, _ab(15, 14, 12, 1, 10, 3), "Blindsight 10 ft., PP 10", [], ["Bite (+4, 1d6+2 piercing)", "Constrict (+4, 1d8+2 bludgeoning + grapple)"]),
    AnimalForm("black_bear", "Black Bear", 0.5, "1/2", "Medium", "Beast", 11, 19, "40 ft., climb 30 ft.", 40, 0, 0, _ab(15, 10, 14, 2, 12, 7), "PP 13", ["Keen Smell"], ["Multiattack (Bite + Claws)"]),
    AnimalForm("crocodile", "Crocodile", 0.5, "1/2", "Large", "Beast", 12, 19, "20 ft., swim 30 ft.", 20, 30, 0, _ab(15, 10, 13, 2, 10, 5), "PP 10", ["Hold Breath"], ["Bite (+4, 1d10+2 piercing + grapple)"]),
    AnimalForm("reef_shark", "Reef Shark", 0.5, "1/2", "Medium", "Beast", 12, 22, "0 ft., swim 40 ft.", 0, 40, 0, _ab(14, 13, 13, 1, 10, 4), "Blindsight 30 ft., PP 12", ["Pack Tactics", "Water Breathing"], ["Bite (+4, 1d8+2 piercing)"]),
    AnimalForm("warhorse", "Warhorse", 0.5, "1/2", "Large", "Beast", 11, 19, "60 ft.", 60, 0, 0, _ab(18, 12, 13, 2, 12, 7), "PP 11", ["Trampling Charge"], ["Hooves (+6, 2d6+4 bludgeoning)"]),
    AnimalForm("ape", "Ape", 0.5, "1/2", "Medium", "Beast", 12, 19, "30 ft., climb 30 ft.", 30, 0, 0, _ab(16, 14, 14, 6, 12, 7), "PP 13", [], ["Multiattack (2x Fist +5, 1d6+3 bludgeoning)", "Rock (+5, 1d6+3)"]),
    AnimalForm("giant_wasp", "Giant Wasp", 0.5, "1/2", "Medium", "Beast", 12, 13, "10 ft., fly 50 ft.", 10, 0, 50, _ab(10, 14, 10, 1, 10, 3), "PP 10", [], ["Sting (+4, 1d6+2 piercing + 3d6 poison)"]),
    AnimalForm("brown_bear", "Brown Bear", 1.0, "1", "Large", "Beast", 11, 34, "40 ft., climb 30 ft.", 40, 0, 0, _ab(19, 10, 16, 2, 13, 7), "PP 13", ["Keen Smell"], ["Multiattack (Bite +6, 1d8+4 & Claws +6, 2d6+4)"]),
    AnimalForm("dire_wolf", "Dire Wolf", 1.0, "1", "Large", "Beast", 14, 37, "50 ft.", 50, 0, 0, _ab(17, 15, 15, 3, 12, 7), "PP 13", ["Keen Hearing and Smell", "Pack Tactics"], ["Bite (+5, 2d6+3 piercing, DC 13 STR or prone)"]),
    AnimalForm("giant_eagle", "Giant Eagle", 1.0, "1", "Large", "Beast", 13, 26, "10 ft., fly 80 ft.", 10, 0, 80, _ab(16, 17, 13, 8, 14, 10), "PP 14", ["Keen Sight"], ["Multiattack (Beak +5, 1d6+3 & Talons +5, 2d6+3)"]),
    AnimalForm("giant_octopus", "Giant Octopus", 1.0, "1", "Large", "Beast", 11, 52, "10 ft., swim 60 ft.", 10, 60, 0, _ab(17, 13, 13, 4, 10, 4), "Darkvision 60 ft., PP 14", ["Hold Breath", "Underwater Camouflage"], ["Tentacles (+5, 2d6+3 bludgeoning + grapple)", "Ink Cloud"]),
    AnimalForm("giant_spider", "Giant Spider", 1.0, "1", "Large", "Beast", 14, 26, "30 ft., climb 30 ft.", 30, 0, 0, _ab(14, 16, 12, 2, 11, 4), "Blindsight 10 ft., Darkvision 60 ft., PP 10", ["Spider Climb", "Web Sense", "Web Walker"], ["Bite (+5, 1d8+3 piercing + 2d8 poison)", "Web (+5, Restrained)"]),
    AnimalForm("lion", "Lion", 1.0, "1", "Large", "Beast", 12, 26, "50 ft.", 50, 0, 0, _ab(17, 15, 13, 3, 12, 8), "PP 13", ["Keen Smell", "Pack Tactics", "Pounce", "Running Leap"], ["Bite (+5, 1d8+3)", "Claw (+5, 1d6+3)"]),
    AnimalForm("tiger", "Tiger", 1.0, "1", "Large", "Beast", 12, 37, "40 ft.", 40, 0, 0, _ab(17, 15, 14, 3, 12, 8), "Darkvision 60 ft., PP 13", ["Keen Smell", "Pounce"], ["Bite (+5, 1d10+3)", "Claw (+5, 1d8+3)"]),
    AnimalForm("giant_boar", "Giant Boar", 2.0, "2", "Large", "Beast", 12, 42, "40 ft.", 40, 0, 0, _ab(17, 10, 16, 2, 7, 5), "PP 8", ["Charge", "Relentless"], ["Tusk (+5, 2d6+3 slashing)"]),
    AnimalForm("giant_constrictor_snake", "Giant Constrictor Snake", 2.0, "2", "Huge", "Beast", 12, 60, "30 ft., swim 30 ft.", 30, 30, 0, _ab(19, 14, 12, 1, 10, 3), "Blindsight 10 ft., PP 10", [], ["Bite (+6, 2d6+4)", "Constrict (+6, 2d8+4 + grapple)"]),
    AnimalForm("giant_elk", "Giant Elk", 2.0, "2", "Huge", "Beast", 14, 42, "60 ft.", 60, 0, 0, _ab(19, 16, 14, 7, 14, 10), "PP 14", ["Charge"], ["Ram (+6, 2d6+4)", "Hooves (+6, 4d8+4)"]),
    AnimalForm("polar_bear", "Polar Bear", 2.0, "2", "Large", "Beast", 12, 42, "40 ft., swim 30 ft.", 40, 30, 0, _ab(20, 10, 16, 2, 13, 7), "PP 13", ["Keen Smell"], ["Multiattack (Bite +7, 1d8+5 & Claws +7, 2d6+5)"]),
    AnimalForm("saber_toothed_tiger", "Saber-Toothed Tiger", 2.0, "2", "Large", "Beast", 12, 52, "40 ft.", 40, 0, 0, _ab(18, 14, 15, 3, 12, 8), "PP 13", ["Keen Smell", "Pounce"], ["Bite (+6, 1d10+5)", "Claw (+6, 2d6+5)"]),
    AnimalForm("giant_scorpion", "Giant Scorpion", 3.0, "3", "Large", "Beast", 15, 52, "40 ft.", 40, 0, 0, _ab(15, 13, 15, 1, 9, 3), "Blindsight 60 ft., PP 9", [], ["Multiattack (2x Claw +4 & Sting +4 + 4d10 poison)"]),
    AnimalForm("killer_whale", "Killer Whale", 3.0, "3", "Huge", "Beast", 12, 90, "0 ft., swim 60 ft.", 0, 60, 0, _ab(19, 10, 13, 3, 12, 7), "Blindsight 120 ft., PP 13", ["Echolocation", "Hold Breath", "Keen Hearing"], ["Bite (+6, 5d6+4 piercing)"]),
    AnimalForm("elephant", "Elephant", 4.0, "4", "Huge", "Beast", 12, 76, "40 ft.", 40, 0, 0, _ab(22, 9, 17, 3, 11, 6), "PP 10", ["Trampling Charge"], ["Gore (+8, 3d8+6)", "Stomp (+8, 3d10+6)"]),
    AnimalForm("giant_crocodile", "Giant Crocodile", 5.0, "5", "Huge", "Beast", 14, 85, "30 ft., swim 50 ft.", 30, 50, 0, _ab(21, 9, 17, 2, 10, 7), "PP 10", ["Hold Breath"], ["Multiattack (Bite +8, 3d10+5 & Tail +8, 2d8+5)"]),
    AnimalForm("triceratops", "Triceratops", 5.0, "5", "Huge", "Beast", 13, 95, "50 ft.", 50, 0, 0, _ab(22, 9, 17, 2, 11, 5), "PP 10", ["Trampling Charge"], ["Gore (+9, 4d8+6)", "Stomp (+9, 3d10+6)"]),
    AnimalForm("mammoth", "Mammoth", 6.0, "6", "Huge", "Beast", 13, 126, "40 ft.", 40, 0, 0, _ab(24, 9, 21, 3, 11, 6), "PP 10", ["Trampling Charge"], ["Gore (+10, 4d8+7)", "Stomp (+10, 4d10+7)"]),
    # Elemental Wild Shape forms (Circle of the Moon 5e Lv 10+)
    AnimalForm("air_elemental", "Air Elemental", 5.0, "5", "Large", "Elemental", 15, 90, "0 ft., fly 90 ft. (hover)", 0, 0, 90, _ab(14, 20, 14, 6, 10, 6), "Darkvision 60 ft., PP 10", ["Air Form", "Resist Nonmagical B/P/S, Lightning, Thunder", "Immune Poison"], ["Multiattack (2x Slam +8, 2d8+5)", "Whirlwind"], category="Elemental"),
    AnimalForm("earth_elemental", "Earth Elemental", 5.0, "5", "Large", "Elemental", 17, 126, "30 ft., burrow 30 ft.", 30, 0, 0, _ab(20, 8, 20, 5, 10, 5), "Darkvision 60 ft., Tremorsense 60 ft., PP 10", ["Earth Glide", "Siege Monster", "Resist Nonmagical B/P/S"], ["Multiattack (2x Slam +8, 2d8+5)"], category="Elemental"),
    AnimalForm("fire_elemental", "Fire Elemental", 5.0, "5", "Large", "Elemental", 13, 102, "50 ft.", 50, 0, 0, _ab(10, 17, 16, 6, 10, 7), "Darkvision 60 ft., PP 10", ["Fire Form", "Illumination", "Water Susceptibility", "Immune Fire, Poison"], ["Multiattack (2x Touch +6, 2d6+3 fire)"], category="Elemental"),
    AnimalForm("water_elemental", "Water Elemental", 5.0, "5", "Large", "Elemental", 14, 114, "30 ft., swim 90 ft.", 30, 90, 0, _ab(18, 14, 18, 5, 10, 8), "Darkvision 60 ft., PP 10", ["Water Form", "Freeze", "Resist Acid, Nonmagical B/P/S"], ["Multiattack (2x Slam +7, 2d8+4)", "Whelm"], category="Elemental"),
]

ANIMAL_FORMS_BY_ID: dict[str, AnimalForm] = {f.id: f for f in ANIMAL_FORMS}


def parse_cr_label(cr_label: str) -> float:
    raw = (cr_label or "0").strip()
    if "/" in raw:
        parts = raw.split("/", 1)
        try:
            num = float(parts[0].strip())
            den = float(parts[1].strip())
            return num / den if den != 0 else 0.0
        except ValueError:
            return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def animal_form_to_dict(form: AnimalForm) -> dict:
    return {
        "id": form.id,
        "name": form.name,
        "cr": form.cr,
        "cr_label": form.cr_label,
        "size": form.size,
        "creature_type": form.creature_type,
        "ac": int(form.ac),
        "hp": int(form.hp),
        "speed": form.speed,
        "walk_speed": int(form.walk_speed),
        "swim_speed": int(form.swim_speed),
        "fly_speed": int(form.fly_speed),
        "abilities": {ab: int(form.abilities.get(ab, 10)) for ab in ABILITIES},
        "senses": form.senses,
        "traits": list(form.traits),
        "actions": list(form.actions),
        "category": form.category,
    }


def animal_form_from_dict(data: dict) -> AnimalForm:
    name = str(data.get("name") or "Custom Animal Form").strip() or "Custom Animal Form"
    raw_id = str(data.get("id") or "").strip()
    if not raw_id:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "form"
        raw_id = f"custom_{slug}"
    cr_label = str(data.get("cr_label") or str(data.get("cr") or "0")).strip() or "0"
    cr_val = parse_cr_label(cr_label) if "cr_label" in data or isinstance(data.get("cr"), str) else float(data.get("cr", 0.0))
    walk = max(0, int(data.get("walk_speed", 30)))
    swim = max(0, int(data.get("swim_speed", 0)))
    fly = max(0, int(data.get("fly_speed", 0)))
    speed = str(data.get("speed") or "").strip()
    if not speed:
        sp_parts = [f"{walk} ft."]
        if swim > 0:
            sp_parts.append(f"swim {swim} ft.")
        if fly > 0:
            sp_parts.append(f"fly {fly} ft.")
        speed = ", ".join(sp_parts)
    ab_raw = data.get("abilities") or {}
    abilities = {ab: int(ab_raw.get(ab, 10)) for ab in ABILITIES}
    return AnimalForm(
        id=raw_id,
        name=name,
        cr=cr_val,
        cr_label=cr_label,
        size=str(data.get("size") or "Medium"),
        creature_type=str(data.get("creature_type") or "Beast"),
        ac=max(1, int(data.get("ac", 12))),
        hp=max(1, int(data.get("hp", 10))),
        speed=speed,
        walk_speed=walk,
        swim_speed=swim,
        fly_speed=fly,
        abilities=abilities,
        senses=str(data.get("senses") or "PP 10"),
        traits=[str(t).strip() for t in data.get("traits", []) if str(t).strip()],
        actions=[str(a).strip() for a in data.get("actions", []) if str(a).strip()],
        category=str(data.get("category") or "Beast"),
    )


def all_animal_forms(state: Optional[CharacterState] = None) -> list[AnimalForm]:
    forms: dict[str, AnimalForm] = {f.id: f for f in ANIMAL_FORMS}
    if state is not None:
        for raw in getattr(state, "custom_animal_forms", []):
            if isinstance(raw, dict):
                cf = animal_form_from_dict(raw)
                forms[cf.id] = cf
    return list(forms.values())


def find_animal_form(form_id: str, state: Optional[CharacterState] = None) -> Optional[AnimalForm]:
    if state is not None:
        for raw in getattr(state, "custom_animal_forms", []):
            if isinstance(raw, dict) and str(raw.get("id") or "").strip() == form_id:
                return animal_form_from_dict(raw)
    return ANIMAL_FORMS_BY_ID.get(form_id)


@dataclass
class AnimalFormAccess:
    has_access: bool
    source_summary: str
    druid_level: int = 0
    is_moon_druid: bool = False
    is_55e: bool = False
    max_cr: float = 0.0
    allow_swim: bool = False
    allow_fly: bool = False
    allow_elementals: bool = False
    known_forms_limit: Optional[int] = None
    temp_hp_55e: int = 0
    moon_ac_55e: int = 0


def compute_animal_form_access(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
) -> AnimalFormAccess:
    """Determine Wild Shape / Polymorph / Familiar Animal Form limits for the character."""
    is_55e = state.ruleset == "5.5e"
    druid_lvl = 0
    for cl in state.normalized_classes():
        cel = repo.get(cl.class_id)
        if cel and "druid" in cel.name.lower():
            druid_lvl = max(druid_lvl, cl.level)

    arch_names = " ".join(
        e.name.lower() for e in computed.granted_elements if e.type in ("Archetype", "Archetype Feature", "Class Feature")
    )
    is_moon = "moon" in arch_names

    # Check Wild Shape-granting spells
    all_spells = set(state.known_spells) | set(
        computed.spellcasting.granted_spell_ids if computed.spellcasting else []
    )
    spell_names = {(repo.get(sid).name.lower() if repo.get(sid) else "") for sid in all_spells}
    has_shapechange = "shapechange" in spell_names
    has_true_poly = "true polymorph" in spell_names
    has_polymorph = "polymorph" in spell_names
    has_familiar = "find familiar" in spell_names

    min_druid_ws = 2  # Druid unlocks Wild Shape at Lv 2 in both 5e and 5.5e
    if druid_lvl >= min_druid_ws:
        if is_55e:
            allow_swim = True
            allow_fly = druid_lvl >= 8
            if is_moon:
                max_cr = max(1.0, float(druid_lvl // 3))
                temp_hp = 3 * druid_lvl
                moon_ac = max(13, 13 + computed.ability_modifiers["wisdom"])
            else:
                max_cr = 1.0 if druid_lvl >= 8 else (0.5 if druid_lvl >= 4 else 0.25)
                temp_hp = druid_lvl
                moon_ac = 0
            known_lim = 8 if druid_lvl >= 8 else (6 if druid_lvl >= 4 else 4)
            src = (
                f"5.5e {'Circle of the Moon ' if is_moon else ''}Druid Lv {druid_lvl} "
                f"(Max CR {max_cr:g}, Known Forms {known_lim}, Temp HP +{temp_hp})"
            )
            return AnimalFormAccess(
                has_access=True,
                source_summary=src,
                druid_level=druid_lvl,
                is_moon_druid=is_moon,
                is_55e=True,
                max_cr=max_cr,
                allow_swim=allow_swim,
                allow_fly=allow_fly,
                allow_elementals=False,
                known_forms_limit=known_lim,
                temp_hp_55e=temp_hp,
                moon_ac_55e=moon_ac,
            )

        # 5e (2014) Druid
        allow_swim = druid_lvl >= 4
        allow_fly = druid_lvl >= 8
        allow_elem = is_moon and druid_lvl >= 10
        if is_moon:
            max_cr = max(1.0, float(druid_lvl // 3))
        else:
            max_cr = 1.0 if druid_lvl >= 8 else (0.5 if druid_lvl >= 4 else 0.25)
        src = f"5e {'Circle of the Moon ' if is_moon else ''}Druid Lv {druid_lvl} (Max CR {max_cr:g})"
        return AnimalFormAccess(
            has_access=True,
            source_summary=src,
            druid_level=druid_lvl,
            is_moon_druid=is_moon,
            is_55e=False,
            max_cr=max_cr,
            allow_swim=allow_swim,
            allow_fly=allow_fly,
            allow_elementals=allow_elem,
        )

    if has_shapechange or has_true_poly:
        return AnimalFormAccess(
            has_access=True,
            source_summary="Shapechange / True Polymorph (CR up to character level)",
            is_55e=is_55e,
            max_cr=float(state.level),
            allow_swim=True,
            allow_fly=True,
            allow_elementals=True,
        )
    if has_polymorph:
        return AnimalFormAccess(
            has_access=True,
            source_summary=f"Polymorph (Beast CR up to {state.level})",
            is_55e=is_55e,
            max_cr=float(state.level),
            allow_swim=True,
            allow_fly=True,
            allow_elementals=False,
        )
    if has_familiar:
        return AnimalFormAccess(
            has_access=True,
            source_summary="Find Familiar (CR 0 Tiny Beasts)",
            is_55e=is_55e,
            max_cr=0.0,
            allow_swim=True,
            allow_fly=True,
            allow_elementals=False,
        )

    return AnimalFormAccess(
        has_access=False,
        source_summary="No Wild Shape / Polymorph feature active (enable Manual Override to use any form)",
        is_55e=is_55e,
    )


def is_form_eligible(
    form: AnimalForm,
    access: AnimalFormAccess,
    override_all: bool = False,
) -> tuple[bool, str]:
    if override_all:
        return True, "Allowed (Manual Override)"
    if not access.has_access:
        return False, "No Wild Shape / Polymorph feature active"
    if form.category == "Elemental" and not access.allow_elementals:
        return False, "Requires Circle of the Moon Lv 10+ (5e)"
    if form.cr > access.max_cr + 1e-6:
        return False, f"CR {form.cr_label} exceeds max CR {access.max_cr:g}"
    if form.swim_speed > 0 and not access.allow_swim:
        return False, "Swim speed requires Druid Lv 4+ (5e)"
    if form.fly_speed > 0 and not access.allow_fly:
        return False, "Fly speed requires Druid Lv 8+"
    return True, "Eligible"


def compute_transformed_stats(
    form: AnimalForm,
    state: CharacterState,
    computed: ComputedCharacter,
    access: AnimalFormAccess,
) -> dict:
    """Compute character stats while Wild Shaped / Polymorphed into form."""
    is_55e = state.ruleset == "5.5e"
    merged_abilities: dict[str, int] = {}
    for ab in ABILITIES:
        if ab in ("intelligence", "wisdom", "charisma") and access.druid_level >= 2:
            merged_abilities[ab] = computed.ability_totals[ab]
        else:
            merged_abilities[ab] = form.abilities[ab]

    if is_55e and access.druid_level >= 2:
        ac = max(form.ac, access.moon_ac_55e) if access.moon_ac_55e else form.ac
        hp_display = f"{computed.max_hp} HP (+{access.temp_hp_55e} Temp HP)"
    else:
        ac = form.ac
        hp_display = f"{form.hp} Beast HP (reverts at 0 HP)"

    return {
        "ac": ac,
        "hp_display": hp_display,
        "speed": form.speed,
        "abilities": merged_abilities,
    }


def render_animal_form_html(form: AnimalForm, transformed: Optional[dict] = None) -> str:
    ab_row = " | ".join(
        f"<b>{ABILITY_ABBR[ab]}</b> {(transformed['abilities'][ab] if transformed else form.abilities[ab])}"
        for ab in ABILITIES
    )
    ac_txt = str(transformed["ac"]) if transformed else str(form.ac)
    hp_txt = transformed["hp_display"] if transformed else str(form.hp)
    traits_html = "".join(f"<li>{html.escape(t)}</li>" for t in form.traits) or "<li>None</li>"
    actions_html = "".join(f"<li>{html.escape(a)}</li>" for a in form.actions) or "<li>None</li>"
    return (
        f"<h3>{html.escape(form.name)}</h3>"
        f"<p style='color:#7dd3fc;'>{html.escape(form.size)} {html.escape(form.creature_type)} • CR {html.escape(form.cr_label)}</p>"
        f"<p><b>AC:</b> {html.escape(ac_txt)} | <b>HP:</b> {html.escape(hp_txt)} | <b>Speed:</b> {html.escape(form.speed)}</p>"
        f"<p>{ab_row}</p>"
        f"<p><b>Senses:</b> {html.escape(form.senses)}</p>"
        f"<h4>Traits</h4><ul>{traits_html}</ul>"
        f"<h4>Actions</h4><ul>{actions_html}</ul>"
    )
