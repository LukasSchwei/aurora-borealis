"""Equipment currency, containers, encumbrance, and starting equipment helpers."""

from __future__ import annotations

import random
import re
from typing import Optional

from .loader import ContentRepository
from .models import CharacterState, Element, InventoryItem

COIN_TO_CP: dict[str, int] = {
    "cp": 1,
    "sp": 10,
    "ep": 50,
    "gp": 100,
    "pp": 1000,
}

DEFAULT_CONTAINERS: list[dict] = [
    {"name": "On Person", "ignore_weight": False, "notes": "Worn or carried directly"},
    {"name": "Backpack", "ignore_weight": False, "notes": "Standard pack"},
    {
        "name": "Bag of Holding",
        "ignore_weight": True,
        "notes": "Extradimensional storage (contents weigh 0 lb)",
    },
]

# Standard 5e / 5.5e class starting equipment packages & starting gold dice (count, sides, mult)
CLASS_STARTING_EQUIPMENT: dict[str, dict] = {
    "artificer": {
        "items": [
            ("Studded Leather Armor", 1),
            ("Light Crossbow", 1),
            ("Crossbow Bolts", 20),
            ("Dagger", 2),
            ("Thieves' Tools", 1),
            ("Dungeoneer's Pack", 1),
        ],
        "gold_dice": (5, 4, 10),
    },
    "barbarian": {
        "items": [
            ("Greataxe", 1),
            ("Handaxe", 2),
            ("Javelin", 4),
            ("Explorer's Pack", 1),
        ],
        "gold_dice": (2, 4, 10),
    },
    "bard": {
        "items": [
            ("Leather Armor", 1),
            ("Rapier", 1),
            ("Dagger", 1),
            ("Lute", 1),
            ("Diplomat's Pack", 1),
        ],
        "gold_dice": (5, 4, 10),
    },
    "cleric": {
        "items": [
            ("Scale Mail", 1),
            ("Shield", 1),
            ("Mace", 1),
            ("Light Crossbow", 1),
            ("Crossbow Bolts", 20),
            ("Holy Symbol", 1),
            ("Priest's Pack", 1),
        ],
        "gold_dice": (5, 4, 10),
    },
    "druid": {
        "items": [
            ("Leather Armor", 1),
            ("Shield", 1),
            ("Quarterstaff", 1),
            ("Druidic Focus", 1),
            ("Explorer's Pack", 1),
        ],
        "gold_dice": (2, 4, 10),
    },
    "fighter": {
        "items": [
            ("Chain Mail", 1),
            ("Shield", 1),
            ("Longsword", 1),
            ("Light Crossbow", 1),
            ("Crossbow Bolts", 20),
            ("Dungeoneer's Pack", 1),
        ],
        "gold_dice": (5, 4, 10),
    },
    "monk": {
        "items": [
            ("Shortsword", 1),
            ("Dart", 10),
            ("Explorer's Pack", 1),
        ],
        "gold_dice": (5, 4, 1),
    },
    "paladin": {
        "items": [
            ("Chain Mail", 1),
            ("Shield", 1),
            ("Longsword", 1),
            ("Javelin", 5),
            ("Holy Symbol", 1),
            ("Priest's Pack", 1),
        ],
        "gold_dice": (5, 4, 10),
    },
    "ranger": {
        "items": [
            ("Scale Mail", 1),
            ("Shortsword", 2),
            ("Longbow", 1),
            ("Arrows", 20),
            ("Explorer's Pack", 1),
        ],
        "gold_dice": (5, 4, 10),
    },
    "rogue": {
        "items": [
            ("Leather Armor", 1),
            ("Rapier", 1),
            ("Shortbow", 1),
            ("Arrows", 20),
            ("Dagger", 2),
            ("Thieves' Tools", 1),
            ("Burglar's Pack", 1),
        ],
        "gold_dice": (4, 4, 10),
    },
    "sorcerer": {
        "items": [
            ("Light Crossbow", 1),
            ("Crossbow Bolts", 20),
            ("Dagger", 2),
            ("Arcane Focus", 1),
            ("Dungeoneer's Pack", 1),
        ],
        "gold_dice": (3, 4, 10),
    },
    "warlock": {
        "items": [
            ("Leather Armor", 1),
            ("Light Crossbow", 1),
            ("Crossbow Bolts", 20),
            ("Dagger", 2),
            ("Arcane Focus", 1),
            ("Scholar's Pack", 1),
        ],
        "gold_dice": (4, 4, 10),
    },
    "wizard": {
        "items": [
            ("Quarterstaff", 1),
            ("Arcane Focus", 1),
            ("Spellbook", 1),
            ("Scholar's Pack", 1),
        ],
        "gold_dice": (4, 4, 10),
    },
}

BACKGROUND_STARTING_GOLD: dict[str, int] = {
    "acolyte": 15,
    "charlatan": 15,
    "criminal": 15,
    "entertainer": 15,
    "folk hero": 10,
    "guild artisan": 15,
    "hermit": 5,
    "noble": 25,
    "outlander": 10,
    "sage": 10,
    "sailor": 10,
    "soldier": 10,
    "urchin": 10,
    "artisan": 32,
    "farmer": 30,
    "guard": 12,
    "guide": 3,
    "merchant": 22,
    "scribe": 23,
    "wayfarer": 16,
}


def currency_total_cp(currency: dict[str, int]) -> int:
    total = 0
    for coin, mult in COIN_TO_CP.items():
        try:
            total += max(0, int(currency.get(coin, 0))) * mult
        except (TypeError, ValueError):
            pass
    return total


def currency_total_gp(currency: dict[str, int]) -> float:
    return currency_total_cp(currency) / 100.0


def element_cost_cp(el: Optional[Element]) -> int:
    """Parse an Element's cost & currency setters into copper pieces (cp)."""
    if el is None:
        return 0
    raw = (el.setters.get("cost") or "").strip().lower()
    if not raw:
        return 0
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)", raw.replace(",", ""))
    if not m:
        return 0
    try:
        amount = float(m.group(1))
    except ValueError:
        return 0

    cur = (el.setters.get("currency") or "").strip().lower()
    if not cur:
        for coin in ("pp", "gp", "ep", "sp", "cp"):
            if re.search(rf"\b{coin}\b", raw):
                cur = coin
                break
    if not cur:
        cur = "gp"
    mult = COIN_TO_CP.get(cur, 100)
    return max(0, int(round(amount * mult)))


def format_cp(cost_cp: int) -> str:
    if cost_cp <= 0:
        return "0 gp"
    if cost_cp % 100 == 0:
        return f"{cost_cp // 100} gp"
    if cost_cp % 10 == 0:
        return f"{cost_cp // 10} sp"
    return f"{cost_cp} cp"


def deduct_currency(currency: dict[str, int], cost_cp: int) -> tuple[bool, dict[str, int]]:
    """Deduct cost_cp from currency denominations, converting higher coins when needed."""
    clean = {coin: max(0, int(currency.get(coin, 0))) for coin in ("cp", "sp", "ep", "gp", "pp")}
    if cost_cp <= 0:
        return True, clean
    total_cp = currency_total_cp(clean)
    if total_cp < cost_cp:
        return False, clean

    # Try exact subtraction without breaking coins when possible, else normalize remainder cleanly
    rem_cp = total_cp - cost_cp
    # Preserve denomination proportions if we didn't need to break larger coins?
    # Deduct greedily from cp -> sp -> ep -> gp -> pp if exact, otherwise break lowest sufficient coin.
    work = dict(clean)
    need = cost_cp
    for coin in ("cp", "sp", "ep", "gp", "pp"):
        val = COIN_TO_CP[coin]
        if need <= 0:
            break
        if work[coin] > 0 and (need % val == 0 or coin == "cp"):
            take = min(work[coin], need // val)
            if take > 0:
                work[coin] -= take
                need -= take * val

    if need == 0:
        return True, work

    # Break coins starting from smallest denomination that can cover remainder, or normalize change
    out = dict(clean)
    # Break whole coins from smallest -> largest until we have enough cp/change
    for coin in ("cp", "sp", "ep", "gp", "pp"):
        val = COIN_TO_CP[coin]
        avail = out[coin] * val
        if avail >= need:
            coins_used = (need + val - 1) // val
            out[coin] -= coins_used
            change = coins_used * val - need
            for ch_coin in ("pp", "gp", "ep", "sp", "cp"):
                if ch_coin == "ep":
                    continue
                ch_val = COIN_TO_CP[ch_coin]
                if change >= ch_val:
                    cnt = change // ch_val
                    out[ch_coin] += cnt
                    change -= cnt * ch_val
            return True, out
        need -= avail
        out[coin] = 0

    # Fallback full normalization into gp/sp/cp
    gp = rem_cp // 100
    rem_cp %= 100
    sp = rem_cp // 10
    cp = rem_cp % 10
    return True, {"cp": cp, "sp": sp, "ep": 0, "gp": gp, "pp": 0}


def get_character_containers(state: CharacterState) -> list[dict]:
    """Return character's configured containers merged with built-in defaults."""
    by_name: dict[str, dict] = {}
    for c in DEFAULT_CONTAINERS:
        by_name[c["name"].lower()] = dict(c)
    for c in state.containers:
        if isinstance(c, dict):
            cname = str(c.get("name") or "").strip()
            if cname:
                by_name[cname.lower()] = {
                    "name": cname,
                    "ignore_weight": bool(c.get("ignore_weight", False)),
                    "notes": str(c.get("notes") or ""),
                }
    return list(by_name.values())


def is_container_weightless(container_name: str, state: CharacterState) -> bool:
    target = (container_name or "").strip().lower()
    if not target:
        return False
    for c in get_character_containers(state):
        if c["name"].lower() == target:
            return bool(c.get("ignore_weight", False))
    return False


def _match_class_key(class_name: str) -> str:
    low = (class_name or "").strip().lower()
    for key in CLASS_STARTING_EQUIPMENT:
        if key in low:
            return key
    return ""


def _resolve_item_by_name(name: str, repo: ContentRepository) -> Optional[Element]:
    target = name.strip().lower()
    for etype in ("Weapon", "Armor", "Item", "Magic Item"):
        for el in repo.of_type(etype):
            if el.name.strip().lower() == target:
                return el
    for etype in ("Weapon", "Armor", "Item", "Magic Item"):
        for el in repo.of_type(etype):
            if target in el.name.strip().lower():
                return el
    return None


def _parse_weight_lb(el: Optional[Element]) -> float:
    if el is None:
        return 0.0
    raw = el.setters.get("weight_lb") or el.setters.get("weight") or "0"
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw)
    return float(m.group(1)) if m else 0.0


def build_starting_equipment(
    class_name: str,
    background_name: str,
    repo: ContentRepository,
) -> tuple[list[InventoryItem], int]:
    """Build standard starting equipment items and starting gold (gp) for class + background."""
    items: list[InventoryItem] = []
    ckey = _match_class_key(class_name)
    spec = CLASS_STARTING_EQUIPMENT.get(ckey, {})
    for item_name, qty in spec.get("items", []):
        el = _resolve_item_by_name(item_name, repo)
        if el is not None:
            items.append(
                InventoryItem(
                    element_id=el.id,
                    name=el.name,
                    quantity=qty,
                    equipped=(el.type in ("Armor", "Weapon")),
                    weight=_parse_weight_lb(el),
                    category=el.type,
                    container="On Person" if el.type in ("Armor", "Weapon") else "Backpack",
                )
            )
        else:
            cat = "Armor" if "armor" in item_name.lower() or "shield" in item_name.lower() or "mail" in item_name.lower() else (
                "Weapon" if any(w in item_name.lower() for w in ("sword", "axe", "bow", "dagger", "mace", "staff", "javelin", "dart", "rapier")) else "Item"
            )
            items.append(
                InventoryItem(
                    element_id="",
                    name=item_name,
                    quantity=qty,
                    equipped=(cat in ("Armor", "Weapon")),
                    weight=0.0,
                    category=cat,
                    container="On Person" if cat in ("Armor", "Weapon") else "Backpack",
                    custom=True,
                )
            )

    bg_low = (background_name or "").strip().lower()
    bg_gold = 10 if bg_low else 0
    for bkey, val in BACKGROUND_STARTING_GOLD.items():
        if bkey in bg_low:
            bg_gold = val
            break
    return items, bg_gold


def roll_starting_gold(class_name: str, rng: Optional[random.Random] = None) -> int:
    """Roll starting wealth in gp for class_name when choosing gold instead of equipment."""
    ckey = _match_class_key(class_name)
    spec = CLASS_STARTING_EQUIPMENT.get(ckey)
    if not spec:
        return 100
    cnt, sides, mult = spec.get("gold_dice", (4, 4, 10))
    r = rng or random
    return sum(r.randint(1, sides) for _ in range(cnt)) * mult
