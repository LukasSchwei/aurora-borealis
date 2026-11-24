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
