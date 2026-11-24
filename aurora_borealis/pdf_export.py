"""Official 5e (AcroForm) and 5.5e (Overlay) PDF character sheet exporter."""

from __future__ import annotations

import base64
import html
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument

from .loader import ContentRepository
from .models import ABILITIES, ABILITY_ABBR, SKILLS, CharacterState, ComputedCharacter
from .paths import get_templates_dir

_SAVE_CHECKBOXES = {
    "strength": "Check Box 11",
    "dexterity": "Check Box 18",
    "constitution": "Check Box 19",
    "intelligence": "Check Box 20",
    "wisdom": "Check Box 21",
    "charisma": "Check Box 22",
}

_SKILL_CHECKBOXES = {
    skill_name: f"Check Box {23 + idx}"
    for idx, (skill_name, _ab) in enumerate(SKILLS)
}

_SKILL_PDF_FIELDS = {
    "Acrobatics": "Acrobatics",
    "Animal Handling": "Animal",
    "Arcana": "Arcana",
    "Athletics": "Athletics",
    "Deception": "Deception ",
    "History": "History ",
    "Insight": "Insight",
    "Intimidation": "Intimidation",
    "Investigation": "Investigation ",
    "Medicine": "Medicine",
    "Nature": "Nature",
    "Perception": "Perception ",
    "Performance": "Performance",
    "Persuasion": "Persuasion",
    "Religion": "Religion",
    "Sleight of Hand": "SleightofHand",
    "Stealth": "Stealth ",
    "Survival": "Survival",
}

# Spell slots by level on page 3 of official 5e sheet
_SPELL_FIELDS_BY_LEVEL: dict[int, list[str]] = {
    0: [f"Spells {n}" for n in range(1014, 1023)],
    1: [f"Spells {n}" for n in range(1023, 1034)],
    2: [f"Spells {n}" for n in range(1034, 1047)],
    3: [f"Spells {n}" for n in range(1047, 1060)],
    4: [f"Spells {n}" for n in range(1060, 1073)],
    5: [f"Spells {n}" for n in range(1073, 1082)],
    6: [f"Spells {n}" for n in range(1082, 1091)],
    7: [f"Spells {n}" for n in range(1091, 1100)],
    8: [f"Spells {n}" for n in range(1100, 1107)],
    9: [f"Spells {n}" for n in range(1107, 1114)],
}


def validate_character_for_pdf(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
) -> list[str]:
    """Return a list of missing or incomplete fields before exporting a character PDF."""
    missing: list[str] = []
    name = (state.name or "").strip()
    if not name or name == "New Adventurer":
        missing.append("Character Name")
    if not state.race_id or repo.get(state.race_id) is None:
        missing.append("Species" if state.ruleset == "5.5e" else "Race")
    if not state.class_id or repo.get(state.class_id) is None:
        missing.append("Class")
    if not state.background_id or repo.get(state.background_id) is None:
        missing.append("Background")
    if not state.alignment_id or repo.get(state.alignment_id) is None:
        missing.append("Alignment")

    if state.ruleset == "5.5e":
        asi_sum = sum(v for v in state.background_asi.values() if v > 0)
        if asi_sum != 3:
            missing.append(f"5.5e Background Attribute Points (currently +{asi_sum}, expected +3)")

    for active_sel in computed.active_selections:
        if active_sel.rule.optional:
            continue
        chosen = state.selections.get(active_sel.key, [])
        filled = sum(1 for i in range(active_sel.rule.number) if i < len(chosen) and chosen[i])
        if filled < active_sel.rule.number:
            rem = active_sel.rule.number - filled
            missing.append(f"Choice: {active_sel.rule.name} ({rem} remaining)")

    if computed.spellcasting:
        sc = computed.spellcasting
        combined = list(dict.fromkeys([*sc.granted_spell_ids, *state.known_spells]))
        cantrip_cnt = 0
        leveled_cnt = 0
        for sid in combined:
            sel = repo.get(sid)
            lvl = sel.setters.get("level", "0") if sel else "0"
            if lvl == "0":
                cantrip_cnt += 1
            else:
                leveled_cnt += 1
        if sc.max_cantrips > 0 and cantrip_cnt == 0:
            missing.append(f"Cantrips (0 / {sc.max_cantrips} selected)")
        if sc.max_known_spells and sc.max_known_spells > 0 and leveled_cnt == 0:
            missing.append(f"Spells Known (0 / {sc.max_known_spells} selected)")

    return missing


def _all_character_spells(state: CharacterState, computed: ComputedCharacter) -> list[str]:
    granted = computed.spellcasting.granted_spell_ids if computed.spellcasting else []
    return list(dict.fromkeys([*granted, *state.known_spells]))


def _fmt_mod(val: int) -> str:
    return f"+{val}" if val >= 0 else str(val)


def fill_pdf_form_qpdf(
    template_pdf: Path,
    text_fields: dict[str, str],
    checkbox_fields: set[str],
    output_path: Path,
) -> None:
    """Populate AcroForm fields in a fillable PDF using qpdf JSON round-trip."""
    template_pdf = Path(template_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    probe = subprocess.run(
        [
            "qpdf",
            "--json",
            "--json-stream-data=inline",
            "--json-key=acroform",
            "--json-key=qpdf",
            str(template_pdf),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode not in (0, 3):
        raise RuntimeError(f"qpdf --json failed: {probe.stderr.strip()}")

    data = json.loads(probe.stdout)
    objects: dict = data["qpdf"][1]
    fields: list[dict] = data.get("acroform", {}).get("fields", [])

    # Locate /AcroForm dict to set /NeedAppearances = true
    trailer_obj = objects.get("trailer", {}).get("value", {})
    root_ref = trailer_obj.get("/Root", "")
    if isinstance(root_ref, str) and f"obj:{root_ref}" in objects:
        root_obj = objects[f"obj:{root_ref}"].get("value", {})
        acro_ref = root_obj.get("/AcroForm")
        if isinstance(acro_ref, str) and f"obj:{acro_ref}" in objects:
            objects[f"obj:{acro_ref}"]["value"]["/NeedAppearances"] = True

    text_lookup = {k: v for k, v in text_fields.items()}
    text_stripped = {k.strip(): v for k, v in text_fields.items()}
    chk_lookup = set(checkbox_fields)

    for f in fields:
        fullname = f.get("fullname", "")
        obj_ref = f.get("object")
        if not obj_ref:
            continue
        obj_key = f"obj:{obj_ref}"
        if obj_key not in objects:
            continue
        val_dict = objects[obj_key].get("value")
        if not isinstance(val_dict, dict):
            continue

        if fullname in text_lookup or fullname.strip() in text_stripped:
            txt = text_lookup.get(fullname, text_stripped.get(fullname.strip(), ""))
            val_dict["/V"] = f"u:{txt}"
            if fullname in (
                "Features and Traits",
                "Feat+Traits",
                "Equipment",
                "ProficienciesLang",
                "Backstory",
                "Allies",
            ):
                val_dict["/DA"] = "/Helv 8 Tf 0 g"
            val_dict.pop("/AP", None)
        elif fullname in chk_lookup:
            on_state = "/Yes"
            ap = val_dict.get("/AP", {})
            if isinstance(ap, dict) and isinstance(ap.get("/N"), dict):
                keys = [k for k in ap["/N"].keys() if k != "/Off"]
                if keys:
                    on_state = keys[0]
            val_dict["/V"] = on_state
            val_dict["/AS"] = on_state

    with tempfile.TemporaryDirectory(prefix="aurora_qpdf_") as tmpdir:
        json_path = Path(tmpdir) / "filled.json"
        json_path.write_text(json.dumps({"qpdf": data["qpdf"]}), encoding="utf-8")
        res = subprocess.run(
            ["qpdf", "--json-input", str(json_path), str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode not in (0, 3) or not output_path.is_file():
            raise RuntimeError(f"qpdf --json-input failed: {res.stderr.strip()}")


def _build_5e_field_map(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
) -> tuple[dict[str, str], set[str]]:
    race_el = repo.get(state.race_id)
    class_el = repo.get(state.class_id)
    bg_el = repo.get(state.background_id)
    align_el = repo.get(state.alignment_id)

    text: dict[str, str] = {
        "CharacterName": state.name or "New Adventurer",
        "CharacterName 2": state.name or "New Adventurer",
        "ClassLevel": f"{class_el.name if class_el else ''} {state.level}".strip(),
        "Background": bg_el.name if bg_el else "",
        "PlayerName": state.player_name,
        "Race ": race_el.name if race_el else "",
        "Alignment": align_el.name if align_el else "",
        "ProfBonus": _fmt_mod(computed.proficiency_bonus),
        "AC": str(computed.armor_class),
        "Initiative": _fmt_mod(computed.initiative),
        "Speed": f"{computed.speed} ft",
        "HPMax": str(computed.max_hp),
        "HPCurrent": str(computed.max_hp),
        "HDTotal": f"{state.level}{computed.hit_die}",
        "HD": computed.hit_die,
        "Passive": str(computed.passive_perception),
        "CP": str(state.currency.get("cp", 0)),
        "SP": str(state.currency.get("sp", 0)),
        "EP": str(state.currency.get("ep", 0)),
        "GP": str(state.currency.get("gp", 0)),
        "PP": str(state.currency.get("pp", 0)),
        "Age": state.age,
        "Height": state.height,
        "Weight": state.weight,
        "Eyes": state.eyes,
        "Skin": state.skin,
        "Hair": state.hair,
        "Backstory": state.backstory,
        "Allies": state.notes,
    }
    checked: set[str] = set()

    # Ability Scores & Modifiers
    mod_field_names = {
        "strength": "STRmod",
        "dexterity": "DEXmod ",
        "constitution": "CONmod",
        "intelligence": "INTmod",
        "wisdom": "WISmod",
        "charisma": "CHamod",
    }
    for ab in ABILITIES:
        text[ABILITY_ABBR[ab]] = str(computed.ability_totals[ab])
        text[mod_field_names[ab]] = _fmt_mod(computed.ability_modifiers[ab])

    # Saving Throws
    save_field_names = {
        "strength": "ST Strength",
        "dexterity": "ST Dexterity",
        "constitution": "ST Constitution",
        "intelligence": "ST Intelligence",
        "wisdom": "ST Wisdom",
        "charisma": "ST Charisma",
    }
    for ab in ABILITIES:
        sv = computed.saving_throws[ab]
        text[save_field_names[ab]] = _fmt_mod(sv.bonus)
        if sv.proficient:
            checked.add(_SAVE_CHECKBOXES[ab])

    # Skills
    for skill_name, sk in computed.skills.items():
        field_name = _SKILL_PDF_FIELDS.get(skill_name)
        if field_name:
            text[field_name] = _fmt_mod(sk.bonus)
        if sk.proficient:
            checked.add(_SKILL_CHECKBOXES[skill_name])

    # Weapons (up to 3 rows)
    weapons = [it for it in state.inventory if it.category == "Weapon"][:3]
    wpn_slots = [
        ("Wpn Name", "Wpn1 AtkBonus", "Wpn1 Damage"),
        ("Wpn Name 2", "Wpn2 AtkBonus ", "Wpn2 Damage "),
        ("Wpn Name 3", "Wpn3 AtkBonus  ", "Wpn3 Damage  "),
    ]
    str_mod = computed.ability_modifiers["strength"]
    dex_mod = computed.ability_modifiers["dexterity"]
    for idx, wpn in enumerate(weapons):
        el = repo.get(wpn.element_id)
        dmg = el.setters.get("damage", "") if el else ""
        dmg_type = (el.setters.get("damage_type", "") if el else "").lower()
        short_type = {
            "piercing": "pierc.",
            "bludgeoning": "bludg.",
            "slashing": "slash.",
        }.get(dmg_type, dmg_type[:6])
        is_ranged = el and ("ranged" in " ".join(el.supports).lower() or "finesse" in " ".join(el.supports).lower())
        atk_mod = max(str_mod, dex_mod) if is_ranged else str_mod
        n_key, a_key, d_key = wpn_slots[idx]
        text[n_key] = wpn.name
        text[a_key] = _fmt_mod(atk_mod + computed.proficiency_bonus)
        text[d_key] = f"{dmg} {short_type}".strip()

    # Equipment, Proficiencies & Features
    eq_lines = [f"{it.name} x{it.quantity}" if it.quantity > 1 else it.name for it in state.inventory]
    text["Equipment"] = "\n".join(eq_lines)

    prof_parts: list[str] = []
    if computed.languages:
        prof_parts.append("Languages: " + ", ".join(computed.languages))
    if computed.proficiencies:
        prof_parts.append("Proficiencies: " + ", ".join(computed.proficiencies))
    text["ProficienciesLang"] = "\n\n".join(prof_parts)

    feat_lines = [
        f"• {el.name} ({el.type})"
        for el in computed.granted_elements
        if el.type in ("Class Feature", "Archetype Feature", "Racial Trait", "Background Feature", "Feat")
    ]
    text["Features and Traits"] = "\n".join(feat_lines)
    text["Feat+Traits"] = "\n".join(feat_lines)

    # Spellcasting (Page 3)
    if computed.spellcasting:
        sc = computed.spellcasting
        text["Spellcasting Class 2"] = sc.caster_name
        text["SpellcastingAbility 2"] = sc.ability
        text["SpellSaveDC  2"] = str(sc.save_dc)
        text["SpellAtkBonus 2"] = _fmt_mod(sc.attack_bonus)
        for lvl in range(1, 10):
            cnt = sc.slots.get(lvl, 0)
            if cnt:
                text[f"SlotsTotal {18 + lvl}"] = str(cnt)

        grouped: dict[int, list[str]] = {lvl: [] for lvl in range(10)}
        for sid in _all_character_spells(state, computed):
            sel = repo.get(sid)
            sname = sel.name if sel else sid
            lvl_str = sel.setters.get("level", "0") if sel else "0"
            lvl = int(lvl_str) if lvl_str.isdigit() else 0
            grouped.setdefault(max(0, min(9, lvl)), []).append(sname)

        for lvl, spell_names in grouped.items():
            targets = _SPELL_FIELDS_BY_LEVEL.get(lvl, [])
            for idx, sname in enumerate(spell_names[: len(targets)]):
                text[targets[idx]] = sname

    return text, checked


def _draw_text(
    painter: QPainter,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    size: float = 9.0,
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    wrap: bool = False,
) -> None:
    font = QFont("Sans Serif", int(size))
    font.setPointSizeF(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor("#111827"))
    flags = int(align)
    if wrap:
        flags |= int(Qt.TextFlag.TextWordWrap)
    painter.drawText(QRectF(x, y, w, h), flags, text)


def export_55e_overlay_pdf(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
    template_pdf: Path,
    output_path: Path,
) -> None:
    """Render a 2-page vector overlay matching DnD_2024_Character-Sheet.pdf and composite via qpdf."""
    template_pdf = Path(template_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    race_el = repo.get(state.race_id)
    class_el = repo.get(state.class_id)
    bg_el = repo.get(state.background_id)
    align_el = repo.get(state.alignment_id)

    with tempfile.TemporaryDirectory(prefix="aurora_55e_") as tmpdir:
        overlay_pdf = Path(tmpdir) / "overlay.pdf"
        writer = QPdfWriter(str(overlay_pdf))
        writer.setResolution(72)
        writer.setPageSize(QPageSize(QSizeF(603, 774), QPageSize.Unit.Point))
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)

        painter = QPainter(writer)
        try:
            # --- PAGE 1 (603 x 774 pt) ---
            _draw_text(painter, 24, 13, 215, 14, state.name or "", size=10.5, bold=True)
            _draw_text(painter, 24, 36, 110, 12, bg_el.name if bg_el else "", size=8.5)
            _draw_text(painter, 146, 36, 100, 12, class_el.name if class_el else "", size=8.5)
            _draw_text(painter, 24, 56, 110, 12, race_el.name if race_el else "", size=8.5)
            archetypes = [e.name for e in computed.granted_elements if e.type == "Archetype"]
            _draw_text(painter, 146, 56, 100, 12, archetypes[0] if archetypes else "", size=8.5)

            # Level, AC, HP, Hit Dice
            _draw_text(
                painter, 260, 22, 40, 20, str(state.level), size=13, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 318, 33, 44, 22, str(computed.armor_class), size=13, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 376, 36, 52, 22, str(computed.max_hp), size=12, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 441, 56, 36, 13, str(computed.max_hp), size=8.5,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 488, 56, 40, 13, f"{state.level}{computed.hit_die}", size=8.5,
                align=Qt.AlignmentFlag.AlignCenter,
            )

            # Proficiency, Initiative, Speed, Size, Passive Perception
            _draw_text(
                painter, 36, 136, 48, 22, _fmt_mod(computed.proficiency_bonus), size=12, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 232, 131, 66, 16, _fmt_mod(computed.initiative), size=11, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 322, 131, 72, 16, f"{computed.speed} ft", size=10.5, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            size_els = [e.name for e in computed.granted_elements if e.type == "Size"]
            _draw_text(
                painter, 412, 131, 66, 16, size_els[0] if size_els else "Medium", size=9.5, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 502, 131, 66, 16, str(computed.passive_perception), size=11, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )

            # Exact measured ability boxes, saving throw lines, and skill lines
            # Tuple: (col_x, mod_y, score_y, save_line_y, first_skill_line_y, skills)
            ab_specs = {
                "strength": (18, 208, 217, 269, 289, ["Athletics"]),
                "dexterity": (18, 322, 331, 387, 406, ["Acrobatics", "Sleight of Hand", "Stealth"]),
                "constitution": (18, 472, 481, 533, 550, []),
                "intelligence": (122, 134, 142, 192, 211, ["Arcana", "History", "Investigation", "Nature", "Religion"]),
                "wisdom": (122, 309, 317, 366, 385, ["Animal Handling", "Insight", "Medicine", "Perception", "Survival"]),
                "charisma": (122, 484, 492, 540, 559, ["Deception", "Intimidation", "Performance", "Persuasion"]),
            }
            for ab, (ax, mod_y, score_y, save_y, sk_y0, sk_list) in ab_specs.items():
                mod_txt = _fmt_mod(computed.ability_modifiers[ab])
                tot_txt = str(computed.ability_totals[ab])
                score_x = ax + (42 if ab == "dexterity" else (46 if ax < 50 else 50))
                _draw_text(painter, ax + 14, mod_y, 28, 18, mod_txt, size=11, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, score_x, score_y, 24, 13, tot_txt, size=8.5, align=Qt.AlignmentFlag.AlignCenter)

                dot_x = ax + (0.5 if ax < 50 else 2.5)
                sv = computed.saving_throws[ab]
                if sv.proficient:
                    painter.save()
                    painter.setBrush(QColor("#111827"))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QRectF(dot_x, save_y - 6.5, 5.0, 5.0))
                    painter.restore()
                _draw_text(painter, ax + 14, save_y - 11, 20, 11, _fmt_mod(sv.bonus), size=8, bold=True)

                for s_idx, sk_name in enumerate(sk_list):
                    sk = computed.skills[sk_name]
                    line_y = sk_y0 + s_idx * 14.0
                    if sk.proficient:
                        painter.save()
                        painter.setBrush(QColor("#111827"))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawEllipse(QRectF(dot_x, line_y - 6.5, 5.0, 5.0))
                        painter.restore()
                    _draw_text(painter, ax + 14, line_y - 11, 20, 11, _fmt_mod(sk.bonus), size=8)

            # Equipment Training & Proficiencies (bottom-left)
            clean_profs = [
                p.replace("Weapon Proficiency (", "").replace("Armor Proficiency (", "").rstrip(")")
                for p in computed.proficiencies
            ]
            prof_txt = ", ".join(clean_profs[:10])
            _draw_text(painter, 18, 676, 182, 40, prof_txt, size=7.2, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

            # Weapons & Damage Cantrips (middle-right table, baselines 212, 232, 251, ...)
            weapons = [it for it in state.inventory if it.category == "Weapon"][:6]
            for idx, wpn in enumerate(weapons):
                wy = (212 + idx * 19.6) - 13
                el = repo.get(wpn.element_id)
                dmg = el.setters.get("damage", "") if el else ""
                _draw_text(painter, 224, wy, 102, 13, wpn.name, size=8)
                _draw_text(painter, 336, wy, 40, 13, _fmt_mod(computed.ability_modifiers["strength"] + computed.proficiency_bonus), size=8)
                _draw_text(painter, 384, wy, 70, 13, dmg, size=8)

            # Class Features, Species Traits, Feats
            cls_feats = "\n".join(
                f"• {e.name}" for e in computed.granted_elements if e.type in ("Class Feature", "Archetype Feature")
            )
            spc_feats = "\n".join(
                f"• {e.name}" for e in computed.granted_elements if e.type in ("Racial Trait", "Background Feature")
            )
            feats_txt = "\n".join(
                f"• {e.name}" for e in computed.granted_elements if e.type == "Feat"
            )
            _draw_text(painter, 224, 350, 354, 196, cls_feats, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            _draw_text(painter, 224, 594, 166, 162, spc_feats, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            _draw_text(painter, 412, 594, 166, 162, feats_txt, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

            # --- PAGE 2 ---
            writer.newPage()
            if computed.spellcasting:
                sc = computed.spellcasting
                _draw_text(painter, 18, 12, 108, 14, sc.ability, size=9, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 18, 48, 36, 18, _fmt_mod(sc.ability_mod), size=10, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 18, 76, 36, 18, str(sc.save_dc), size=10, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 18, 104, 36, 18, _fmt_mod(sc.attack_bonus), size=10, bold=True, align=Qt.AlignmentFlag.AlignCenter)

                slot_coords = {
                    1: (185, 81), 2: (185, 97), 3: (185, 113),
                    4: (269, 81), 5: (269, 97), 6: (269, 113),
                    7: (347, 81), 8: (347, 97), 9: (347, 113),
                }
                for lvl, cnt in sc.slots.items():
                    if lvl in slot_coords:
                        sx, sy = slot_coords[lvl]
                        _draw_text(painter, sx, sy, 20, 12, str(cnt), size=8.5, bold=True)

            # Spells list (Cantrips & Prepared Spells table, baselines 192, 212, 231, ...)
            for idx, sid in enumerate(_all_character_spells(state, computed)[:29]):
                sel = repo.get(sid)
                sname = sel.name if sel else sid
                lvl = sel.setters.get("level", "0") if sel else "0"
                sy = (192 + idx * 19.5) - 13
                _draw_text(painter, 18, sy, 22, 13, lvl, size=8, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 46, sy, 108, 13, sname, size=8)

            # Appearance + Portrait (top right)
            app_txt = f"Age: {state.age}  Ht: {state.height}  Wt: {state.weight}\nEyes: {state.eyes}  Skin: {state.skin}  Hair: {state.hair}"
            _draw_text(painter, 412, 34, 112, 68, app_txt, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            if state.portrait_base64:
                try:
                    img = QImage.fromData(base64.b64decode(state.portrait_base64))
                    if not img.isNull():
                        painter.drawImage(QRectF(528, 32, 54, 66), img)
                except Exception:
                    pass

            # Backstory, Alignment, Languages, Equipment, Coins
            _draw_text(painter, 412, 144, 168, 104, state.backstory or state.notes, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            _draw_text(painter, 412, 259, 168, 14, align_el.name if align_el else "", size=8.5)
            _draw_text(painter, 412, 328, 168, 34, ", ".join(computed.languages), size=8, wrap=True)
            eq_txt = "\n".join(f"{it.name} x{it.quantity}" if it.quantity > 1 else it.name for it in state.inventory)
            _draw_text(painter, 412, 412, 168, 190, eq_txt, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

            coin_xs = {"cp": 411, "sp": 447, "ep": 483, "gp": 519, "pp": 555}
            for coin, cx in coin_xs.items():
                _draw_text(painter, cx, 703, 32, 18, str(state.currency.get(coin, 0)), size=8.5, bold=True, align=Qt.AlignmentFlag.AlignCenter)
        finally:
            painter.end()

        res = subprocess.run(
            ["qpdf", str(template_pdf), "--overlay", str(overlay_pdf), "--", str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode not in (0, 3) or not output_path.is_file():
            raise RuntimeError(f"qpdf --overlay failed: {res.stderr.strip()}")


def build_sheet_html(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
) -> str:
    """Fallback HTML character sheet if official PDF templates are unavailable."""
    race_el = repo.get(state.race_id)
    class_el = repo.get(state.class_id)
    bg_el = repo.get(state.background_id)
    align_el = repo.get(state.alignment_id)

    subtitle_parts = [
        f"Level {state.level}",
        race_el.name if race_el else "No Race",
        class_el.name if class_el else "No Class",
    ]
    if bg_el:
        subtitle_parts.append(bg_el.name)
    if align_el:
        subtitle_parts.append(align_el.name)

    ruleset_badge = html.escape(state.ruleset or "5e")
    portrait_cell = ""
    if state.portrait_base64:
        portrait_cell = (
            f"<td width='76' align='right' valign='middle'>"
            f"<img src='data:image/png;base64,{state.portrait_base64}' width='68' height='68' />"
            f"</td>"
        )

    return f"""
    <html>
    <body style='font-family:sans-serif; font-size:9.5pt; color:#1c242b;'>
      <div style='background-color:#1f3a56; color:#ffffff; padding:10px 14px;'>
        <table width='100%' cellspacing='0' cellpadding='0'>
          <tr>
            <td valign='middle'>
              <h1 style='margin:0; font-size:18pt; color:#ffffff;'>{html.escape(state.name)} [{ruleset_badge}]</h1>
              <div style='font-size:10pt; color:#dce9f5;'>{html.escape(' • '.join(subtitle_parts))}</div>
            </td>
            {portrait_cell}
          </tr>
        </table>
      </div>
      <p><b>AC:</b> {computed.armor_class} | <b>HP:</b> {computed.max_hp} | <b>Speed:</b> {computed.speed} ft | <b>Prof:</b> +{computed.proficiency_bonus}</p>
      <p><b>Notes:</b> {html.escape(state.notes or '-')}</p>
    </body>
    </html>
    """


def export_character_pdf(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
    output_path: Path,
    templates_dir: Optional[Path] = None,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tdir = Path(templates_dir) if templates_dir else get_templates_dir()

    if state.ruleset == "5.5e":
        tpl = tdir / "dnd55e_sheet.pdf"
        if tpl.is_file():
            export_55e_overlay_pdf(state, computed, repo, tpl, output_path)
            return
    else:
        tpl = tdir / "dnd5e_sheet.pdf"
        if tpl.is_file():
            text_fields, checked = _build_5e_field_map(state, computed, repo)
            fill_pdf_form_qpdf(tpl, text_fields, checked, output_path)
            return

    # Fallback HTML export if template PDF is not installed
    writer = QPdfWriter(str(output_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    writer.setTitle(f"{state.name} - D&D {state.ruleset} Character Sheet")
    doc = QTextDocument()
    doc.setHtml(build_sheet_html(state, computed, repo))
    doc.print_(writer)
