"""Official 2024 (5.5e) background ability score assignments and thematic fallbacks."""

from __future__ import annotations

from typing import Optional

from .models import Element

# Official 2024 Player's Handbook (5.5e) 16 Backgrounds -> 3 allowed abilities
OFFICIAL_55E_BACKGROUND_ABILITIES: dict[str, tuple[str, str, str]] = {
    "acolyte": ("intelligence", "wisdom", "charisma"),
    "artisan": ("strength", "dexterity", "intelligence"),
    "charlatan": ("dexterity", "constitution", "charisma"),
    "criminal": ("dexterity", "constitution", "intelligence"),
    "entertainer": ("strength", "dexterity", "charisma"),
    "farmer": ("strength", "constitution", "wisdom"),
    "guard": ("strength", "intelligence", "wisdom"),
    "guide": ("dexterity", "constitution", "wisdom"),
    "hermit": ("constitution", "wisdom", "charisma"),
    "merchant": ("constitution", "intelligence", "charisma"),
    "noble": ("strength", "intelligence", "charisma"),
    "sage": ("constitution", "intelligence", "wisdom"),
    "sailor": ("strength", "dexterity", "wisdom"),
    "scribe": ("dexterity", "intelligence", "wisdom"),
    "soldier": ("strength", "dexterity", "constitution"),
    "wayfarer": ("dexterity", "wisdom", "charisma"),
}

# Thematic triplets for 2014 PHB & supplement backgrounds without 2024 equivalents
LEGACY_BACKGROUND_ABILITIES: dict[str, tuple[str, str, str]] = {
    "anthropologist": ("intelligence", "wisdom", "charisma"),
    "archaeologist": ("strength", "dexterity", "intelligence"),
    "city watch": ("strength", "intelligence", "wisdom"),
    "clan crafter": ("strength", "constitution", "intelligence"),
    "cloistered scholar": ("constitution", "intelligence", "wisdom"),
    "courtier": ("intelligence", "wisdom", "charisma"),
    "custom": ("strength", "dexterity", "constitution"),
    "entertainer (gladiator)": ("strength", "dexterity", "charisma"),
    "faceless": ("dexterity", "constitution", "charisma"),
    "faction agent": ("intelligence", "wisdom", "charisma"),
    "far traveler": ("dexterity", "wisdom", "charisma"),
    "feylost": ("dexterity", "wisdom", "charisma"),
    "fisher": ("strength", "constitution", "wisdom"),
    "folk hero": ("strength", "constitution", "wisdom"),
    "giant foundling": ("strength", "constitution", "wisdom"),
    "guild artisan": ("strength", "dexterity", "intelligence"),
    "guild merchant": ("constitution", "intelligence", "charisma"),
    "haunted one": ("constitution", "wisdom", "charisma"),
    "house agent": ("dexterity", "intelligence", "charisma"),
    "inheritor": ("constitution", "intelligence", "charisma"),
    "investigator": ("dexterity", "intelligence", "wisdom"),
    "knight": ("strength", "constitution", "charisma"),
    "knight of the order": ("strength", "wisdom", "charisma"),
    "lorehold student": ("constitution", "intelligence", "wisdom"),
    "marine": ("strength", "dexterity", "constitution"),
    "mercenary veteran": ("strength", "dexterity", "constitution"),
    "outlander": ("strength", "constitution", "wisdom"),
    "pirate": ("strength", "dexterity", "charisma"),
    "planar philosopher": ("constitution", "intelligence", "wisdom"),
    "prismari student": ("dexterity", "intelligence", "charisma"),
    "quandrix student": ("constitution", "intelligence", "wisdom"),
    "rewarded": ("dexterity", "wisdom", "charisma"),
    "ruined": ("strength", "constitution", "wisdom"),
    "rune carver": ("strength", "constitution", "intelligence"),
    "sailer": ("strength", "dexterity", "wisdom"),
    "silverquill student": ("intelligence", "wisdom", "charisma"),
    "smuggler": ("dexterity", "constitution", "charisma"),
    "spy": ("dexterity", "intelligence", "charisma"),
    "urban bounty hunter": ("dexterity", "intelligence", "charisma"),
    "urchin": ("dexterity", "constitution", "wisdom"),
    "waterdhavian noble": ("strength", "intelligence", "charisma"),
    "witchlight hand": ("dexterity", "wisdom", "charisma"),
    "witherbloom student": ("constitution", "intelligence", "wisdom"),
}

_SKILL_TO_ABILITY = {
    "ACROBATICS": "dexterity",
    "ANIMAL_HANDLING": "wisdom",
    "ARCANA": "intelligence",
    "ATHLETICS": "strength",
    "DECEPTION": "charisma",
    "HISTORY": "intelligence",
    "INSIGHT": "wisdom",
    "INTIMIDATION": "charisma",
    "INVESTIGATION": "intelligence",
    "MEDICINE": "wisdom",
    "NATURE": "intelligence",
    "PERCEPTION": "wisdom",
    "PERFORMANCE": "charisma",
    "PERSUASION": "charisma",
    "RELIGION": "intelligence",
    "SLEIGHT_OF_HAND": "dexterity",
    "STEALTH": "dexterity",
    "SURVIVAL": "wisdom",
}


def get_55e_background_abilities(bg_el: Optional[Element]) -> tuple[str, str, str]:
    """Return 3 allowed 5.5e ability scores for a Background element."""
    if bg_el is None:
        return ("strength", "dexterity", "constitution")

    key = bg_el.name.strip().lower()
    if key in OFFICIAL_55E_BACKGROUND_ABILITIES:
        return OFFICIAL_55E_BACKGROUND_ABILITIES[key]
    if key in LEGACY_BACKGROUND_ABILITIES:
        return LEGACY_BACKGROUND_ABILITIES[key]

    # Partial match against official 2024 names (e.g. "Noble (Variant)")
    for off_name, triplet in OFFICIAL_55E_BACKGROUND_ABILITIES.items():
        if off_name in key:
            return triplet

    # Thematic fallback based on granted skill proficiencies + description hints
    picked: list[str] = []
    for g in bg_el.grant_rules:
        if g.id.startswith("ID_PROFICIENCY_SKILL_"):
            sk = g.id[len("ID_PROFICIENCY_SKILL_") :]
            ab = _SKILL_TO_ABILITY.get(sk)
            if ab and ab not in picked:
                picked.append(ab)

    for fallback_ab in ("constitution", "wisdom", "intelligence", "charisma", "dexterity", "strength"):
        if len(picked) >= 3:
            break
        if fallback_ab not in picked:
            picked.append(fallback_ab)

    return (picked[0], picked[1], picked[2])


# ==============================================================================
# D&D 5.5e (2024 Player's Handbook) Weapon Masteries, Weapon Updates & Heavy Req
# ==============================================================================

WEAPON_MASTERY_DESCRIPTIONS: dict[str, str] = {
    "Cleave": "Once per turn on a melee hit, make another melee attack against a second creature within 5 ft (no ability mod to damage unless negative).",
    "Graze": "If your attack roll misses, deal damage equal to the ability modifier used for the attack roll.",
    "Nick": "The extra attack of the Light property can be made as part of the Attack action instead of a Bonus Action (once per turn).",
    "Push": "On a hit, push a Large or smaller target up to 10 ft straight away from you.",
    "Sap": "On a hit, the target has Disadvantage on its next attack roll before the start of your next turn.",
    "Slow": "On a hit that deals damage, reduce the target's Speed by 10 ft until the start of your next turn.",
    "Topple": "On a hit, target must make a CON save (DC 8 + PB + attack mod) or fall Prone.",
    "Vex": "On a hit that deals damage, you have Advantage on your next attack roll against that target before the end of your next turn.",
}

WEAPON_MASTERY_TABLE: dict[str, str] = {
    # Cleave
    "greataxe": "Cleave",
    "halberd": "Cleave",
    # Graze
    "glaive": "Graze",
    "greatsword": "Graze",
    # Nick
    "dagger": "Nick",
    "light hammer": "Nick",
    "sickle": "Nick",
    "scimitar": "Nick",
    # Push
    "greatclub": "Push",
    "heavy crossbow": "Push",
    "pike": "Push",
    "warhammer": "Push",
    # Sap
    "flail": "Sap",
    "longsword": "Sap",
    "mace": "Sap",
    "morningstar": "Sap",
    "spear": "Sap",
    "war pick": "Sap",
    # Slow
    "club": "Slow",
    "javelin": "Slow",
    "light crossbow": "Slow",
    "longbow": "Slow",
    "musket": "Slow",
    "sling": "Slow",
    "whip": "Slow",
    # Topple
    "battleaxe": "Topple",
    "lance": "Topple",
    "maul": "Topple",
    "quarterstaff": "Topple",
    "trident": "Topple",
    # Vex
    "blowgun": "Vex",
    "dart": "Vex",
    "handaxe": "Vex",
    "hand crossbow": "Vex",
    "pistol": "Vex",
    "rapier": "Vex",
    "shortbow": "Vex",
    "shortsword": "Vex",
}

WEAPON_55E_UPDATES: dict[str, dict[str, str]] = {
    "trident": {"damage": "1d8 (1d10 Versatile)", "mastery": "Topple", "note": "Buffed from 1d6/1d8 to 1d8/1d10 in 2024 PHB."},
    "lance": {"damage": "1d10", "mastery": "Topple", "note": "Heavy (if not mounted) and Reach; no 5-ft disadvantage in 2024 PHB."},
    "warhammer": {"damage": "1d8 (1d10 Versatile)", "mastery": "Push", "note": "Pushes Large or smaller targets 10 ft."},
    "pistol": {"damage": "1d10", "mastery": "Vex", "note": "Standard Martial Ranged firearm in 2024 PHB."},
    "musket": {"damage": "1d12", "mastery": "Slow", "note": "Standard Martial Ranged firearm in 2024 PHB."},
    "net": {"damage": "—", "mastery": "—", "note": "Replaced by Attack-action DC 8+DEX+PB Restrained save in 2024 PHB."},
    "unarmed strike": {"damage": "1 + STR", "mastery": "—", "note": "Damage, Grapple, or Shove (DC 8 + STR + PB) in 2024 PHB."},
}


def get_weapon_mastery(weapon_name: str) -> Optional[str]:
    """Return the 2024 PHB Weapon Mastery property for a weapon name."""
    low = (weapon_name or "").strip().lower()
    if not low:
        return None
    # Strip magic suffixes like "Longsword (+1)" or "Flame Tongue Rapier"
    base = low.split("(")[0].strip()
    if base in WEAPON_MASTERY_TABLE:
        return WEAPON_MASTERY_TABLE[base]
    # Check longest keys first so "heavy crossbow" matches before "crossbow" / "hand crossbow"
    for key in sorted(WEAPON_MASTERY_TABLE.keys(), key=len, reverse=True):
        if key in base:
            return WEAPON_MASTERY_TABLE[key]
    return None


def check_55e_heavy_weapon_requirement(
    weapon_el: Optional[Element],
    ability_totals: dict[str, int],
) -> tuple[bool, str]:
    """In 2024 PHB, Heavy melee weapons require STR 13+ and Heavy ranged weapons require DEX 13+."""
    if weapon_el is None:
        return True, ""
    blob = " ".join([weapon_el.name, weapon_el.setters.get("properties", ""), *weapon_el.supports]).lower()
    if "heavy" not in blob:
        return True, ""
    is_ranged = "ranged" in blob or "crossbow" in blob or "bow" in blob or "musket" in blob
    if is_ranged:
        dex = ability_totals.get("dexterity", 10)
        if dex < 13:
            return False, f"Heavy ranged weapon requires DEX 13+ (currently {dex}; Disadvantage in 5.5e)"
        return True, ""
    str_val = ability_totals.get("strength", 10)
    if str_val < 13:
        return False, f"Heavy melee weapon requires STR 13+ (currently {str_val}; Disadvantage in 5.5e)"
    return True, ""


def compute_weapon_mastery_limit(state, repo, granted_elements: Optional[list[Element]] = None) -> int:
    """Compute how many Weapon Masteries a 5.5e character can keep prepared."""
    if state.ruleset != "5.5e":
        return 0
    best = 0
    for cl in state.normalized_classes():
        cel = repo.get(cl.class_id)
        if cel is None:
            continue
        cname = cel.name.lower()
        lvl = cl.level
        if "fighter" in cname:
            cnt = 6 if lvl >= 16 else (5 if lvl >= 10 else (4 if lvl >= 4 else 3))
        elif "barbarian" in cname:
            cnt = 4 if lvl >= 10 else (3 if lvl >= 4 else 2)
        elif any(k in cname for k in ("paladin", "ranger", "rogue")):
            cnt = 2
        else:
            cnt = 0
        best = max(best, cnt)

    # Weapon Master feat (2024) grants +1 mastery
    for el in granted_elements or []:
        if el.type == "Feat" and "weapon master" in el.name.lower():
            best += 1
    return best


# ==============================================================================
# D&D 5.5e Origin Feats, Epic Boons (Lv 19), Divine/Primal Orders, Monk & Exhaustion
# ==============================================================================

OFFICIAL_55E_ORIGIN_FEATS: set[str] = {
    "alert",
    "crafter",
    "healer",
    "lucky",
    "magic initiate",
    "musician",
    "savage attacker",
    "skilled",
    "tavern brawler",
    "tough",
}


def is_origin_feat_55e(el: Element) -> bool:
    low = (el.name or "").strip().lower()
    if any(k in low for k in OFFICIAL_55E_ORIGIN_FEATS):
        return True
    return any("origin" in s.lower() for s in el.supports)


OFFICIAL_55E_EPIC_BOONS: list[tuple[str, str, str]] = [
    ("ID_55E_BOON_COMBAT_PROWESS", "Boon of Combat Prowess", "<p>+1 to one ability score (max 30). When you miss with an attack roll, you can hit instead (1/turn).</p>"),
    ("ID_55E_BOON_DIMENSIONAL_TRAVEL", "Boon of Dimensional Travel", "<p>+1 to one ability score (max 30). Immediately after Attack or Magic action, teleport up to 30 ft.</p>"),
    ("ID_55E_BOON_ENERGY_RESISTANCE", "Boon of Energy Resistance", "<p>+1 to one ability score (max 30). Gain Resistance to two damage types (changeable on Long Rest) and redirect energy.</p>"),
    ("ID_55E_BOON_FATE", "Boon of Fate", "<p>+1 to one ability score (max 30). Add or subtract 2d4 from a d20 Test within 60 ft (1/Short or Long Rest or Initiative).</p>"),
    ("ID_55E_BOON_FORTITUDE", "Boon of Fortitude", "<p>+1 to one ability score (max 30). Hit Point maximum increases by 40, and regain extra HP equal to CON modifier when healed.</p>"),
    ("ID_55E_BOON_IRRESISTIBLE_OFFENSE", "Boon of Irresistible Offense", "<p>+1 STR or DEX (max 30). Ignore Bludgeoning/Piercing/Slashing resistance; crits deal extra damage equal to ability score.</p>"),
    ("ID_55E_BOON_RECOVERY", "Boon of Recovery", "<p>+1 to one ability score (max 30). Drop to 1 HP instead of 0 HP (1/Long Rest), plus pool of 10d10 healing.</p>"),
    ("ID_55E_BOON_SKILL", "Boon of Skill", "<p>+1 to one ability score (max 30). Gain proficiency in all skills and Expertise in one skill.</p>"),
    ("ID_55E_BOON_SPEED", "Boon of Speed", "<p>+1 to one ability score (max 30). Speed increases by 30 ft; Bonus Action Disengage to end Grappled.</p>"),
    ("ID_55E_BOON_SPELL_RECALL", "Boon of Spell Recall", "<p>+1 INT, WIS, or CHA (max 30). Casting a level 1–4 spell has a chance (roll d4) not to expend the spell slot.</p>"),
    ("ID_55E_BOON_NIGHT_SPIRIT", "Boon of the Night Spirit", "<p>+1 to one ability score (max 30). Gain Invisibility as Bonus Action in Dim Light/Darkness and resistance to most damage.</p>"),
    ("ID_55E_BOON_TRUESIGHT", "Boon of Truesight", "<p>+1 to one ability score (max 30). Gain Truesight out to 60 ft.</p>"),
]


def get_55e_epic_boon_elements() -> list[Element]:
    return [
        Element(
            id=eid,
            name=name,
            type="Feat",
            source="D&D 2024 (5.5e)",
            supports=["Epic Boon", "5.5e"],
            description_html=desc,
        )
        for eid, name, desc in OFFICIAL_55E_EPIC_BOONS
    ]


# 2024 PHB Prepared Spells per Class Level (1..20)
_FULL_55E_PREPARED: dict[int, int] = {
    1: 4, 2: 5, 3: 6, 4: 7, 5: 9, 6: 10, 7: 11, 8: 12, 9: 14, 10: 15,
    11: 16, 12: 16, 13: 17, 14: 17, 15: 18, 16: 18, 17: 19, 18: 20, 19: 21, 20: 22,
}
_BARD_55E_PREPARED: dict[int, int] = {
    1: 4, 2: 5, 3: 6, 4: 7, 5: 9, 6: 10, 7: 11, 8: 12, 9: 14, 10: 15,
    11: 16, 12: 16, 13: 17, 14: 17, 15: 18, 16: 18, 17: 19, 18: 20, 19: 21, 20: 22,
}
_WIZARD_55E_PREPARED: dict[int, int] = {
    1: 4, 2: 5, 3: 6, 4: 7, 5: 9, 6: 10, 7: 11, 8: 12, 9: 14, 10: 15,
    11: 16, 12: 16, 13: 17, 14: 18, 15: 19, 16: 21, 17: 22, 18: 23, 19: 24, 20: 25,
}
_SORC_55E_PREPARED: dict[int, int] = {
    1: 2, 2: 4, 3: 6, 4: 7, 5: 9, 6: 10, 7: 11, 8: 12, 9: 14, 10: 15,
    11: 16, 12: 16, 13: 17, 14: 17, 15: 18, 16: 18, 17: 19, 18: 20, 19: 21, 20: 22,
}
_WARLOCK_55E_PREPARED: dict[int, int] = {
    1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 10,
    11: 11, 12: 11, 13: 12, 14: 12, 15: 13, 16: 13, 17: 14, 18: 14, 19: 15, 20: 15,
}
_HALF_55E_PREPARED: dict[int, int] = {
    1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 6, 7: 7, 8: 7, 9: 9, 10: 9,
    11: 10, 12: 10, 13: 11, 14: 11, 15: 12, 16: 12, 17: 14, 18: 14, 19: 15, 20: 15,
}

PREPARED_SPELLS_55E: dict[str, dict[int, int]] = {
    "cleric": _FULL_55E_PREPARED,
    "druid": _FULL_55E_PREPARED,
    "bard": _BARD_55E_PREPARED,
    "wizard": _WIZARD_55E_PREPARED,
    "sorcerer": _SORC_55E_PREPARED,
    "warlock": _WARLOCK_55E_PREPARED,
    "paladin": _HALF_55E_PREPARED,
    "ranger": _HALF_55E_PREPARED,
}


def get_55e_prepared_spells(class_name: str, class_level: int) -> Optional[int]:
    cname = (class_name or "").strip().lower()
    lvl = max(1, min(20, int(class_level)))
    for key, tbl in PREPARED_SPELLS_55E.items():
        if key in cname:
            return tbl.get(lvl)
    return None


DIVINE_ORDER_55E: dict[str, str] = {
    "protector": "Protector — Heavy Armor & Martial Weapons proficiency",
    "thaumaturge": "Thaumaturge — +1 Cleric cantrip & +WIS mod to Arcana and Religion",
}

PRIMAL_ORDER_55E: dict[str, str] = {
    "warden": "Warden — Medium Armor & Martial Weapons proficiency",
    "magician": "Magician — +1 Druid cantrip & +WIS mod to Arcana and Nature",
}


def monk_martial_arts_die_55e(monk_level: int) -> str:
    if monk_level >= 17:
        return "1d12"
    if monk_level >= 11:
        return "1d10"
    if monk_level >= 5:
        return "1d8"
    return "1d6"


def exhaustion_55e_penalty(level: int) -> tuple[int, int]:
    """Return (d20_test_penalty, speed_ft_penalty) for 2024 Exhaustion level 0..6."""
    lvl = max(0, min(6, int(level)))
    return (-2 * lvl, -5 * lvl)
