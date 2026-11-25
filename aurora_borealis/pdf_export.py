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

from .animal_forms import find_animal_form
from .engine import class_display_summary
from .loader import ContentRepository
from .models import ABILITIES, ABILITY_ABBR, SKILLS, CharacterState, ComputedCharacter
from .paths import get_templates_dir
from .platform_utils import find_executable, is_windows, subprocess_no_window_kwargs
from .rules_55e import get_weapon_mastery

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
    norm_classes = state.normalized_classes()
    if not norm_classes or any(repo.get(cl.class_id) is None for cl in norm_classes):
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


def _fill_pdf_form_pypdf(
    template_pdf: Path,
    text_fields: dict[str, str],
    checkbox_fields: set[str],
    output_path: Path,
) -> None:
    """Pure-Python AcroForm fallback using pypdf when qpdf is not installed (e.g. Windows)."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject

    reader = PdfReader(str(template_pdf))
    writer = PdfWriter(clone_from=reader)
    text_lookup = {k: v for k, v in text_fields.items()}
    text_stripped = {k.strip(): v for k, v in text_fields.items()}

    if "/AcroForm" in writer._root_object:
        acro = writer._root_object["/AcroForm"].get_object()
        acro[NameObject("/NeedAppearances")] = BooleanObject(True)

    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for annot_ref in annots:
            annot = annot_ref.get_object()
            fname = str(annot.get("/T") or "")
            if not fname:
                parent = annot.get("/Parent")
                if parent is not None:
                    fname = str(parent.get_object().get("/T") or "")
            if not fname:
                continue
            if fname in text_lookup or fname.strip() in text_stripped:
                from pypdf.generic import TextStringObject

                txt = text_lookup.get(fname, text_stripped.get(fname.strip(), ""))
                annot[NameObject("/V")] = TextStringObject(txt)
                if "/AP" in annot:
                    del annot["/AP"]
            elif fname in checkbox_fields:
                on_state = "/Yes"
                ap = annot.get("/AP")
                if ap and "/N" in ap:
                    keys = [str(k) for k in ap["/N"].keys() if str(k) != "/Off"]
                    if keys:
                        on_state = keys[0]
                annot[NameObject("/V")] = NameObject(on_state)
                annot[NameObject("/AS")] = NameObject(on_state)

    with output_path.open("wb") as fh:
        writer.write(fh)


def _overlay_pdf_pypdf(base_pdf: Path, overlay_pdf: Path, output_path: Path) -> None:
    """Pure-Python PDF overlay fallback using pypdf when qpdf is not installed."""
    from pypdf import PdfReader, PdfWriter

    base_reader = PdfReader(str(base_pdf))
    over_reader = PdfReader(str(overlay_pdf))
    writer = PdfWriter()
    for idx, base_page in enumerate(base_reader.pages):
        if idx < len(over_reader.pages):
            base_page.merge_page(over_reader.pages[idx])
        writer.add_page(base_page)
    with output_path.open("wb") as fh:
        writer.write(fh)


def fill_pdf_form_qpdf(
    template_pdf: Path,
    text_fields: dict[str, str],
    checkbox_fields: set[str],
    output_path: Path,
) -> None:
    """Populate AcroForm fields in a fillable PDF using qpdf JSON round-trip (or pypdf fallback)."""
    template_pdf = Path(template_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    qpdf_exe = find_executable("qpdf")
    if not qpdf_exe:
        _fill_pdf_form_pypdf(template_pdf, text_fields, checkbox_fields, output_path)
        return

    probe = subprocess.run(
        [
            qpdf_exe,
            "--json",
            "--json-stream-data=inline",
            "--json-key=acroform",
            "--json-key=qpdf",
            str(template_pdf),
        ],
        capture_output=True,
        text=True,
        check=False,
        **subprocess_no_window_kwargs(),
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
            [qpdf_exe, "--json-input", str(json_path), str(output_path)],
            capture_output=True,
            text=True,
            check=False,
            **subprocess_no_window_kwargs(),
        )
        if res.returncode not in (0, 3) or not output_path.is_file():
            raise RuntimeError(f"qpdf --json-input failed: {res.stderr.strip()}")


def _extract_5e_spell_slots(template_pdf: Path) -> dict[int, list[tuple[str, Optional[str]]]]:
    """Read Page 3 of the 5e AcroForm PDF in exact visual top-to-bottom order per spell level (0..9),
    pairing each spell text field with its prepared-dot checkbox."""
    qpdf_exe = find_executable("qpdf")
    if qpdf_exe:
        try:
            proc = subprocess.run(
                [qpdf_exe, "--json", "--json-key=acroform", "--json-key=pages", "--json-key=qpdf", str(template_pdf)],
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
                **subprocess_no_window_kwargs(),
            )
            if proc.returncode not in (0, 3):
                raise RuntimeError(proc.stderr)
            data = json.loads(proc.stdout)
            objs = data["qpdf"][1]
            page_map = {pg["object"]: idx + 1 for idx, pg in enumerate(data.get("pages", []))}
            p3_spells: list[tuple[float, float, str]] = []
            p3_checks: list[tuple[float, float, str]] = []
            for f in data.get("acroform", {}).get("fields", []):
                fn = f.get("fullname", "")
                v = objs.get(f"obj:{f.get('object', '')}", {}).get("value", {})
                rect = v.get("/Rect")
                if not rect or page_map.get(v.get("/P", ""), 0) != 3:
                    continue
                qx, qy = float(rect[0]), 792.0 - float(rect[3])
                if fn.startswith("Spells "):
                    p3_spells.append((qx, qy, fn))
                elif fn.startswith("Check Box"):
                    p3_checks.append((qx, qy, fn))

            lvl = 0
            mapping: dict[int, list[tuple[str, Optional[str]]]] = {}
            for lo, hi in ((0.0, 200.0), (200.0, 400.0), (400.0, 620.0)):
                col_sp = sorted([s for s in p3_spells if lo <= s[0] < hi], key=lambda s: s[1])
                col_ck = sorted([c for c in p3_checks if lo <= c[0] < hi], key=lambda c: c[1])
                blocks: list[list[tuple[float, float, str]]] = []
                for s in col_sp:
                    if not blocks or (s[1] - blocks[-1][-1][1]) > 25.0:
                        blocks.append([s])
                    else:
                        blocks[-1].append(s)
                for b in blocks:
                    pairs: list[tuple[str, Optional[str]]] = []
                    for s in b:
                        near = [c[2] for c in col_ck if abs(c[1] - s[1]) < 6.0]
                        pairs.append((s[2], near[0] if near else None))
                    mapping[lvl] = pairs
                    lvl += 1
            if len(mapping) >= 10:
                return mapping
        except Exception:
            pass
    else:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(template_pdf))
            if len(reader.pages) >= 3:
                p3_spells = []
                p3_checks = []
                for annot_ref in reader.pages[2].get("/Annots") or []:
                    annot = annot_ref.get_object()
                    fn = str(annot.get("/T") or "")
                    rect = annot.get("/Rect")
                    if not rect:
                        continue
                    qx, qy = float(rect[0]), 792.0 - float(rect[3])
                    if fn.startswith("Spells "):
                        p3_spells.append((qx, qy, fn))
                    elif fn.startswith("Check Box"):
                        p3_checks.append((qx, qy, fn))
                lvl = 0
                mapping = {}
                for lo, hi in ((0.0, 200.0), (200.0, 400.0), (400.0, 620.0)):
                    col_sp = sorted([s for s in p3_spells if lo <= s[0] < hi], key=lambda s: s[1])
                    col_ck = sorted([c for c in p3_checks if lo <= c[0] < hi], key=lambda c: c[1])
                    blocks = []
                    for s in col_sp:
                        if not blocks or (s[1] - blocks[-1][-1][1]) > 25.0:
                            blocks.append([s])
                        else:
                            blocks[-1].append(s)
                    for b in blocks:
                        pairs = []
                        for s in b:
                            near = [c[2] for c in col_ck if abs(c[1] - s[1]) < 6.0]
                            pairs.append((s[2], near[0] if near else None))
                        mapping[lvl] = pairs
                        lvl += 1
                if len(mapping) >= 10:
                    return mapping
        except Exception:
            pass
    return {lvl: [(fn, None) for fn in fields] for lvl, fields in _SPELL_FIELDS_BY_LEVEL.items()}


def _overlay_5e_appearance(
    filled_pdf: Path,
    state: CharacterState,
    output_path: Path,
    prepared_dot_rects: Optional[list[tuple[float, float, float, float]]] = None,
) -> None:
    """Overlay Character Appearance portrait + descriptive text onto Page 2 and crisp prepared spell dots onto Page 3."""
    img: Optional[QImage] = None
    if state.portrait_base64:
        try:
            cand = QImage.fromData(base64.b64decode(state.portrait_base64))
            if not cand.isNull():
                img = cand
        except Exception:
            pass
    if img is None and state.portrait_path and Path(state.portrait_path).is_file():
        cand = QImage(state.portrait_path)
        if not cand.isNull():
            img = cand

    app_parts = []
    if state.gender:
        app_parts.append(f"Gender: {state.gender}")
    if state.faith:
        app_parts.append(f"Faith: {state.faith}")
    phys = [
        f"{lbl}: {val}"
        for lbl, val in (
            ("Age", state.age),
            ("Height", state.height),
            ("Weight", state.weight),
            ("Eyes", state.eyes),
            ("Skin", state.skin),
            ("Hair", state.hair),
        )
        if val
    ]
    if phys:
        app_parts.append(" | ".join(phys))
    app_text = "\n".join(app_parts)

    if img is None and not app_text and not prepared_dot_rects:
        if filled_pdf.resolve() != output_path.resolve():
            output_path.write_bytes(filled_pdf.read_bytes())
        return

    with tempfile.TemporaryDirectory(prefix="aurora_5e_app_") as tmpdir:
        overlay_pdf = Path(tmpdir) / "app_overlay.pdf"
        writer = QPdfWriter(str(overlay_pdf))
        writer.setResolution(72)
        writer.setPageSize(QPageSize(QSizeF(612, 792), QPageSize.Unit.Point))
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
        painter = QPainter(writer)
        try:
            # Page 1: blank
            writer.newPage()
            # Page 2: CHARACTER IMAGE box (x=36.5, y=130.5, w=162.7, h=218.1)
            box_x, box_y, box_w, box_h = 41.0, 136.0, 153.0, 206.0
            if img is not None:
                img_h = 146.0 if app_text else box_h
                scaled = img.scaled(
                    int(box_w * 2),
                    int(img_h * 2),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                draw_w = scaled.width() / 2.0
                draw_h = scaled.height() / 2.0
                dx = box_x + (box_w - draw_w) / 2.0
                dy = box_y + (img_h - draw_h) / 2.0
                painter.drawImage(QRectF(dx, dy, draw_w, draw_h), scaled)
                if app_text:
                    _draw_text(
                        painter, box_x, box_y + img_h + 4.0, box_w, box_h - img_h - 4.0,
                        app_text, size=7.5, wrap=True,
                        align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    )
            elif app_text:
                _draw_text(
                    painter, box_x, box_y, box_w, box_h,
                    app_text, size=8.5, wrap=True,
                    align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )
            # Page 3: crisp filled dots for prepared spells (works even where WotC /AP stream is blank)
            writer.newPage()
            if prepared_dot_rects:
                painter.save()
                painter.setBrush(QColor("#111827"))
                painter.setPen(Qt.PenStyle.NoPen)
                for rx, ry, rw, rh in prepared_dot_rects:
                    cx = rx + rw / 2.0
                    cy = ry + rh / 2.0
                    d = min(rw, rh, 4.4)
                    painter.drawEllipse(QRectF(cx - d / 2.0, cy - d / 2.0, d, d))
                painter.restore()
        finally:
            painter.end()

        qpdf_exe = find_executable("qpdf")
        if qpdf_exe:
            res = subprocess.run(
                [qpdf_exe, str(filled_pdf), "--overlay", str(overlay_pdf), "--", str(output_path)],
                capture_output=True,
                text=True,
                check=False,
                **subprocess_no_window_kwargs(),
            )
            if res.returncode not in (0, 3) or not output_path.is_file():
                raise RuntimeError(f"qpdf --overlay (5e appearance) failed: {res.stderr.strip()}")
        else:
            _overlay_pdf_pypdf(filled_pdf, overlay_pdf, output_path)


def _build_5e_field_map(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
    template_pdf: Optional[Path] = None,
) -> tuple[dict[str, str], set[str]]:
    race_el = repo.get(state.race_id)
    bg_el = repo.get(state.background_id)
    align_el = repo.get(state.alignment_id)

    class_level_str = class_display_summary(state, repo)
    hd_total_str = computed.hit_dice_summary or f"{state.level}{computed.hit_die}"

    text: dict[str, str] = {
        "CharacterName": state.name or "New Adventurer",
        "CharacterName 2": state.name or "New Adventurer",
        "ClassLevel": class_level_str,
        "Background": bg_el.name if bg_el else "",
        "PlayerName": state.player_name,
        "Race ": race_el.name if race_el else "",
        "Alignment": align_el.name if align_el else "",
        "XP": str(state.xp),
        "ProfBonus": _fmt_mod(computed.proficiency_bonus),
        "AC": str(computed.armor_class),
        "Initiative": _fmt_mod(computed.initiative),
        "Speed": f"{computed.speed} ft",
        "HPMax": str(computed.max_hp),
        "HPCurrent": str(computed.max_hp),
        "HDTotal": hd_total_str,
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
        text[a_key] = _fmt_mod(atk_mod + computed.proficiency_bonus + wpn.magic_bonus)
        dmg_bonus = f"+{wpn.magic_bonus}" if wpn.magic_bonus > 0 else ""
        text[d_key] = f"{dmg}{dmg_bonus} {short_type}".strip()

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
        if len(sc.casters) > 1:
            text["Spellcasting Class 2"] = sc.caster_name
            text["SpellcastingAbility 2"] = " / ".join(ABILITY_ABBR.get(c.ability.lower(), c.ability[:3].upper()) for c in sc.casters)
            text["SpellSaveDC  2"] = " / ".join(str(c.save_dc) for c in sc.casters)
            text["SpellAtkBonus 2"] = " / ".join(_fmt_mod(c.attack_bonus) for c in sc.casters)
        else:
            text["Spellcasting Class 2"] = sc.caster_name
            text["SpellcastingAbility 2"] = sc.ability
            text["SpellSaveDC  2"] = str(sc.save_dc)
            text["SpellAtkBonus 2"] = _fmt_mod(sc.attack_bonus)
        merged_slots = dict(sc.slots)
        for slvl, cnt in sc.pact_slots.items():
            if slvl not in merged_slots:
                merged_slots[slvl] = cnt
        for lvl in range(1, 10):
            cnt = merged_slots.get(lvl, 0)
            if cnt:
                text[f"SlotsTotal {18 + lvl}"] = str(cnt)

        spell_slots_map = (
            _extract_5e_spell_slots(template_pdf)
            if template_pdf is not None and template_pdf.is_file()
            else {lvl: [(fn, None) for fn in fields] for lvl, fields in _SPELL_FIELDS_BY_LEVEL.items()}
        )
        prepared_set = set(state.prepared_spells) | set(sc.always_prepared_spell_ids)
        grouped: dict[int, list[tuple[str, bool]]] = {lvl: [] for lvl in range(10)}
        for sid in _all_character_spells(state, computed):
            sel = repo.get(sid)
            sname = sel.name if sel else sid
            lvl_str = sel.setters.get("level", "0") if sel else "0"
            lvl = int(lvl_str) if lvl_str.isdigit() else 0
            grouped.setdefault(max(0, min(9, lvl)), []).append((sname, sid in prepared_set))

        for lvl, spell_entries in grouped.items():
            targets = spell_slots_map.get(lvl, [])
            for idx, (sname, is_prep) in enumerate(spell_entries[: len(targets)]):
                field_name, chk_name = targets[idx]
                text[field_name] = sname
                if is_prep and chk_name:
                    checked.add(chk_name)

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
    font = QFont("Arial" if is_windows() else "Sans Serif", int(size))
    font.setPointSizeF(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor("#111827"))
    flags = int(align)
    if wrap:
        flags |= int(Qt.TextFlag.TextWordWrap)
    painter.drawText(QRectF(x, y, w, h), flags, text)


def _get_pdf_page_size(pdf_path: Path) -> tuple[float, float]:
    """Read page 1 MediaBox width/height in points via qpdf or pypdf, defaulting to US Letter (612x792)."""
    qpdf_exe = find_executable("qpdf")
    if qpdf_exe:
        try:
            proc = subprocess.run(
                [qpdf_exe, "--json", "--json-key=pages", "--json-key=qpdf", str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                **subprocess_no_window_kwargs(),
            )
            if proc.returncode in (0, 3):
                data = json.loads(proc.stdout)
                pages = data.get("pages", [])
                objs = data.get("qpdf", [None, {}])[1]
                if pages:
                    page_obj = objs.get(f"obj:{pages[0].get('object', '')}", {}).get("value", {})
                    mbox = page_obj.get("/CropBox") or page_obj.get("/MediaBox")
                    if isinstance(mbox, list) and len(mbox) == 4:
                        w = float(mbox[2]) - float(mbox[0])
                        h = float(mbox[3]) - float(mbox[1])
                        if w > 100 and h > 100:
                            return w, h
        except Exception:
            pass
    else:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path))
            if reader.pages:
                box = reader.pages[0].cropbox or reader.pages[0].mediabox
                w = float(box.width)
                h = float(box.height)
                if w > 100 and h > 100:
                    return w, h
        except Exception:
            pass
    return 612.0, 792.0


def export_55e_overlay_pdf(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
    template_pdf: Path,
    output_path: Path,
) -> None:
    """Render a 2-page vector overlay matching DnD_2024_Character-Sheet.pdf (612x792 pt) and composite via qpdf."""
    template_pdf = Path(template_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    race_el = repo.get(state.race_id)
    class_el = repo.get(state.class_id)
    bg_el = repo.get(state.background_id)
    align_el = repo.get(state.alignment_id)

    tpl_w, tpl_h = _get_pdf_page_size(template_pdf)
    # Official 2024 sheet is 612 x 792 pt; if a cropped copy is used, center-offset cleanly.
    off_x = (tpl_w - 612.0) / 2.0
    off_y = (tpl_h - 792.0) / 2.0

    with tempfile.TemporaryDirectory(prefix="aurora_55e_") as tmpdir:
        overlay_pdf = Path(tmpdir) / "overlay.pdf"
        writer = QPdfWriter(str(overlay_pdf))
        writer.setResolution(72)
        writer.setPageSize(QPageSize(QSizeF(tpl_w, tpl_h), QPageSize.Unit.Point))
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)

        painter = QPainter(writer)
        try:
            painter.translate(off_x, off_y)

            # --- PAGE 1 (612 x 792 pt official 2024 sheet coordinates) ---
            _draw_text(painter, 26.6, 15.0, 221.5, 14.9, state.name or "", size=10.5, bold=True)
            _draw_text(painter, 25.5, 39.0, 120.0, 13.5, bg_el.name if bg_el else "", size=8.5)
            norm_classes = state.normalized_classes()
            cls_55e_txt = (
                class_display_summary(state, repo)
                if len(norm_classes) > 1
                else (class_el.name if class_el else "")
            )
            _draw_text(painter, 150.6, 39.0, 98.2, 13.5, cls_55e_txt, size=8.5 if len(cls_55e_txt) < 18 else 7.2)
            _draw_text(painter, 25.0, 60.5, 120.2, 14.1, race_el.name if race_el else "", size=8.5)
            archetypes = [e.name for e in computed.granted_elements if e.type == "Archetype"]
            _draw_text(painter, 150.6, 60.5, 98.7, 14.1, ", ".join(archetypes), size=8.5)

            # Level, XP, AC, HP Current, HP Max, Hit Dice Max
            _draw_text(
                painter, 266.2, 28.0, 27.3, 22.3, str(state.level), size=13, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            if state.xp > 0:
                _draw_text(
                    painter, 261.3, 56.5, 37.5, 13.7, str(state.xp), size=7.8, bold=True,
                    align=Qt.AlignmentFlag.AlignCenter,
                )
            _draw_text(
                painter, 325.5, 40.0, 37.3, 22.8, str(computed.armor_class), size=13, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 384.0, 47.0, 48.8, 26.8, str(computed.max_hp), size=13, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 444.9, 59.5, 43.3, 13.9, str(computed.max_hp), size=8.5, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            hd_55e_txt = computed.hit_dice_summary or f"{state.level}{computed.hit_die}"
            _draw_text(
                painter, 499.8, 59.5, 37.8, 14.1, hd_55e_txt, size=8.5 if len(hd_55e_txt) <= 6 else 7.0, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )

            # Proficiency Bonus, Initiative, Speed, Size, Passive Perception
            _draw_text(
                painter, 43.0, 147.0, 31.6, 22.3, _fmt_mod(computed.proficiency_bonus), size=12, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 245.1, 131.5, 42.6, 22.3, _fmt_mod(computed.initiative), size=11.5, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 338.1, 131.5, 48.4, 22.3, f"{computed.speed} ft", size=10.5, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            size_els = [e.name for e in computed.granted_elements if e.type == "Size"]
            _draw_text(
                painter, 436.7, 131.5, 42.8, 22.3, size_els[0] if size_els else "Medium", size=9.0, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )
            _draw_text(
                painter, 528.8, 131.5, 53.0, 22.3, str(computed.passive_perception), size=11.5, bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )

            # Exact measured ability boxes, saving throw lines, and skill lines (612x792 pt)
            # (mod_rect, score_rect, dot_x, val_x, save_dot_y, save_val_y, skills: [(name, dot_y, val_y)])
            ab_specs = {
                "strength": (
                    (29.3, 220.0, 29.8, 22.3),
                    (64.4, 222.4, 24.0, 22.3),
                    17.3,
                    28.1,
                    268.1,
                    263.8,
                    [("Athletics", 288.0, 283.7)],
                ),
                "dexterity": (
                    (29.7, 339.6, 28.7, 22.3),
                    (64.4, 343.2, 23.0, 20.7),
                    17.0,
                    27.8,
                    387.6,
                    383.3,
                    [
                        ("Acrobatics", 407.4, 403.2),
                        ("Sleight of Hand", 421.7, 417.4),
                        ("Stealth", 436.0, 431.5),
                    ],
                ),
                "constitution": (
                    (29.7, 487.6, 28.9, 22.3),
                    (63.1, 491.2, 26.7, 20.7),
                    17.2,
                    27.9,
                    535.7,
                    531.5,
                    [],
                ),
                "intelligence": (
                    (137.9, 141.8, 28.7, 22.3),
                    (172.1, 145.1, 23.4, 20.7),
                    124.9,
                    135.7,
                    189.7,
                    185.4,
                    [
                        ("Arcana", 209.5, 205.1),
                        ("History", 223.7, 219.4),
                        ("Investigation", 238.1, 233.5),
                        ("Nature", 252.3, 247.7),
                        ("Religion", 266.4, 261.9),
                    ],
                ),
                "wisdom": (
                    (136.6, 317.8, 29.6, 22.3),
                    (171.7, 321.5, 22.7, 20.9),
                    125.1,
                    135.7,
                    366.2,
                    361.6,
                    [
                        ("Animal Handling", 386.0, 381.6),
                        ("Insight", 400.2, 395.6),
                        ("Medicine", 414.6, 409.8),
                        ("Perception", 428.8, 424.2),
                        ("Survival", 443.0, 438.4),
                    ],
                ),
                "charisma": (
                    (137.5, 494.2, 29.1, 22.3),
                    (170.1, 498.0, 25.0, 20.9),
                    125.0,
                    135.7,
                    542.7,
                    538.2,
                    [
                        ("Deception", 562.5, 558.1),
                        ("Intimidation", 576.8, 572.4),
                        ("Performance", 591.1, 586.6),
                        ("Persuasion", 605.3, 600.7),
                    ],
                ),
            }
            for ab, (mod_r, score_r, dot_x, val_x, sv_dot_y, sv_val_y, sk_rows) in ab_specs.items():
                mod_txt = _fmt_mod(computed.ability_modifiers[ab])
                tot_txt = str(computed.ability_totals[ab])
                _draw_text(painter, *mod_r, mod_txt, size=11.5, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, *score_r, tot_txt, size=9.0, bold=True, align=Qt.AlignmentFlag.AlignCenter)

                sv = computed.saving_throws[ab]
                if sv.proficient:
                    painter.save()
                    painter.setBrush(QColor("#111827"))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QRectF(dot_x + 0.8, sv_dot_y + 2.0, 5.2, 5.2))
                    painter.restore()
                _draw_text(
                    painter, val_x, sv_val_y + 1.5, 17.4, 13.0, _fmt_mod(sv.bonus),
                    size=8.0, bold=True, align=Qt.AlignmentFlag.AlignCenter,
                )

                for sk_name, sk_dot_y, sk_val_y in sk_rows:
                    sk = computed.skills[sk_name]
                    if sk.proficient:
                        painter.save()
                        painter.setBrush(QColor("#111827"))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawEllipse(QRectF(dot_x + 0.8, sk_dot_y + 2.0, 5.2, 5.2))
                        painter.restore()
                    _draw_text(
                        painter, val_x, sk_val_y + 1.5, 17.4, 13.0, _fmt_mod(sk.bonus),
                        size=8.0, align=Qt.AlignmentFlag.AlignCenter,
                    )

            # Equipment Training & Proficiencies (Armor Training diamonds + Weapons & Tools)
            profs_lower = " ".join(
                [*computed.proficiencies, *(e.name for e in computed.granted_elements), *(e.id for e in computed.granted_elements)]
            ).lower()
            armor_diamonds = [
                (("light armor", "light_armor"), 59.7, 657.3),
                (("medium armor", "medium_armor"), 94.2, 656.8),
                (("heavy armor", "heavy_armor"), 139.1, 657.2),
                (("shield",), 177.0, 656.8),
            ]
            for kws, dx, dy in armor_diamonds:
                if any(kw in profs_lower for kw in kws):
                    painter.save()
                    painter.setBrush(QColor("#111827"))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QRectF(dx + 1.4, dy + 1.8, 5.2, 5.2))
                    painter.restore()

            clean_profs = [
                p.replace("Weapon Proficiency (", "").replace("Armor Proficiency (", "").rstrip(")")
                for p in computed.proficiencies
            ]
            prof_txt = ", ".join(clean_profs[:12])
            _draw_text(
                painter, 17.8, 682.2, 191.1, 50.2, prof_txt, size=7.2, wrap=True,
                align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )

            # Weapons & Damage Cantrips (6 rows)
            weapons = [it for it in state.inventory if it.category == "Weapon"][:6]
            mastered_set = {w.strip().lower() for w in state.weapon_masteries}
            str_mod = computed.ability_modifiers["strength"]
            dex_mod = computed.ability_modifiers["dexterity"]
            for idx, wpn in enumerate(weapons):
                wy = 202.0 + idx * 19.65
                el = repo.get(wpn.element_id)
                dmg = el.setters.get("damage", "") if el else ""
                is_ranged = el and (
                    "ranged" in " ".join(el.supports).lower()
                    or "finesse" in " ".join(el.supports).lower()
                )
                atk_mod = max(str_mod, dex_mod) if is_ranged else str_mod
                m_prop = get_weapon_mastery(wpn.name) if wpn.name.lower() in mastered_set else None
                wpn_label = f"{wpn.name} [{m_prop}]" if m_prop else wpn.name
                _draw_text(painter, 231.5, wy, 105.6, 16.8, wpn_label, size=7.8 if m_prop else 8.0)
                _draw_text(
                    painter, 341.5, wy, 43.8, 16.8,
                    _fmt_mod(atk_mod + computed.proficiency_bonus + wpn.magic_bonus),
                    size=8.0, bold=True, align=Qt.AlignmentFlag.AlignCenter,
                )
                dmg_txt = f"{dmg} +{wpn.magic_bonus}" if (dmg and wpn.magic_bonus > 0) else dmg
                _draw_text(painter, 390.0, wy, 74.6, 16.8, dmg_txt, size=7.8)

            # Class Features (2 columns), Species Traits, Feats (plus 5.5e notes & animal forms)
            cls_feat_list = [
                f"• {e.name}" for e in computed.granted_elements if e.type in ("Class Feature", "Archetype Feature")
            ]
            if state.heroic_inspiration:
                cls_feat_list.append("• Heroic Inspiration: Active")
            if state.exhaustion_level > 0:
                cls_feat_list.append(f"• Exhaustion Lv {state.exhaustion_level} ({computed.exhaustion_d20_penalty} d20)")
            if state.animal_forms:
                af_names = [
                    (find_animal_form(fid, state).name if find_animal_form(fid, state) else fid)
                    for fid in state.animal_forms[:6]
                ]
                cls_feat_list.append(f"• Wild Shape Forms: {', '.join(af_names)}")
            split_idx = max(14, (len(cls_feat_list) + 1) // 2) if len(cls_feat_list) > 14 else len(cls_feat_list)
            cls_col1 = "\n".join(cls_feat_list[:split_idx])
            cls_col2 = "\n".join(cls_feat_list[split_idx:])
            spc_feats = "\n".join(
                f"• {e.name}" for e in computed.granted_elements if e.type in ("Racial Trait", "Background Feature")
            )
            feats_txt = "\n".join(
                f"• {e.name}" for e in computed.granted_elements if e.type == "Feat"
            )
            _draw_text(painter, 232.1, 361.2, 175.9, 202.6, cls_col1, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            if cls_col2:
                _draw_text(painter, 418.5, 361.2, 175.2, 202.3, cls_col2, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            _draw_text(painter, 232.4, 606.2, 163.6, 164.1, spc_feats, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            _draw_text(painter, 419.1, 605.5, 176.2, 165.4, feats_txt, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

            # --- PAGE 2 (612 x 792 pt official 2024 sheet coordinates) ---
            writer.newPage()
            painter.resetTransform()
            painter.translate(off_x, off_y)

            if computed.spellcasting:
                sc = computed.spellcasting
                if len(sc.casters) > 1:
                    ab_hdr = " / ".join(ABILITY_ABBR.get(c.ability.lower(), c.ability[:3].upper()) for c in sc.casters)
                    mod_hdr = "/".join(_fmt_mod(c.ability_mod) for c in sc.casters)
                    dc_hdr = "/".join(str(c.save_dc) for c in sc.casters)
                    atk_hdr = "/".join(_fmt_mod(c.attack_bonus) for c in sc.casters)
                else:
                    ab_hdr, mod_hdr, dc_hdr, atk_hdr = (
                        sc.ability,
                        _fmt_mod(sc.ability_mod),
                        str(sc.save_dc),
                        _fmt_mod(sc.attack_bonus),
                    )
                _draw_text(painter, 24.9, 15.0, 110.2, 18.0, ab_hdr, size=9.5 if len(ab_hdr) <= 14 else 7.8, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 14.0, 49.7, 33.7, 26.5, mod_hdr, size=11 if len(mod_hdr) <= 4 else 8.0, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 13.2, 78.6, 34.6, 25.7, dc_hdr, size=11 if len(dc_hdr) <= 4 else 8.0, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 13.3, 107.2, 34.3, 25.3, atk_hdr, size=11 if len(atk_hdr) <= 4 else 8.0, bold=True, align=Qt.AlignmentFlag.AlignCenter)

                slot_coords = {
                    1: (184.3, 87.3), 2: (184.3, 101.7), 3: (184.3, 115.9),
                    4: (273.8, 87.5), 5: (273.8, 101.8), 6: (273.8, 115.9),
                    7: (353.5, 87.4), 8: (353.5, 101.7), 9: (353.5, 115.8),
                }
                merged_slots = dict(sc.slots)
                for slvl, cnt in sc.pact_slots.items():
                    if slvl not in merged_slots:
                        merged_slots[slvl] = cnt
                for lvl, cnt in merged_slots.items():
                    if lvl in slot_coords:
                        sx, sy = slot_coords[lvl]
                        _draw_text(painter, sx, sy, 15.1, 10.4, str(cnt), size=8.0, bold=True, align=Qt.AlignmentFlag.AlignCenter)

            # Cantrips & Prepared Spells table (30 rows, exact 19.72 pt row pitch + C/R/M diamonds)
            for idx, sid in enumerate(_all_character_spells(state, computed)[:30]):
                sel = repo.get(sid)
                sname = sel.name if sel else sid
                lvl = sel.setters.get("level", "0") if sel else "0"
                ctime = sel.setters.get("time", "") if sel else ""
                srange = sel.setters.get("range", "") if sel else ""
                sy = 182.5 + idx * 19.72
                _draw_text(painter, 17.8, sy, 20.4, 16.5, lvl, size=8.0, align=Qt.AlignmentFlag.AlignCenter)
                _draw_text(painter, 42.9, sy, 109.4, 16.5, sname, size=8.0)
                if ctime:
                    _draw_text(painter, 157.1, sy, 29.8, 16.5, ctime, size=6.8)
                if srange:
                    _draw_text(painter, 191.7, sy, 41.9, 16.5, srange, size=6.8)

                if sel is not None:
                    sup_l = " ".join(sel.supports).lower()
                    is_conc = (
                        sel.setters.get("isConcentration", "").strip().lower() == "true"
                        or "concentration" in sel.setters.get("duration", "").lower()
                        or "concentration" in sup_l
                    )
                    is_rit = (
                        sel.setters.get("isRitual", "").strip().lower() == "true"
                        or "ritual" in sup_l
                    )
                    is_mat = (
                        sel.setters.get("hasMaterialComponent", "").strip().lower() == "true"
                        or bool(sel.setters.get("materialComponent", "").strip())
                        or "m" in re.findall(r"[a-z]+", sel.setters.get("components", "").lower())
                    )
                    dot_y = 186.5 + idx * 19.72 + 1.8
                    for flag, dx in ((is_conc, 244.0), (is_rit, 266.0), (is_mat, 288.2)):
                        if flag:
                            painter.save()
                            painter.setBrush(QColor("#111827"))
                            painter.setPen(Qt.PenStyle.NoPen)
                            painter.drawEllipse(QRectF(dx, dot_y, 5.2, 5.2))
                            painter.restore()

            # Appearance + Portrait (top right)
            app_txt = f"Age: {state.age}  Ht: {state.height}  Wt: {state.weight}\nEyes: {state.eyes}  Skin: {state.skin}  Hair: {state.hair}"
            app_w = 114.0 if state.portrait_base64 else 175.8
            _draw_text(painter, 417.9, 38.4, app_w, 67.5, app_txt, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            if state.portrait_base64:
                try:
                    img = QImage.fromData(base64.b64decode(state.portrait_base64))
                    if not img.isNull():
                        painter.drawImage(QRectF(536.0, 38.4, 56.0, 67.0), img)
                except Exception:
                    pass

            # Backstory, Alignment, Languages, Equipment, Coins
            _draw_text(painter, 418.5, 146.4, 175.8, 137.3, state.backstory or state.notes, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            _draw_text(painter, 419.2, 294.2, 174.8, 16.2, align_el.name if align_el else "", size=8.5)
            _draw_text(painter, 418.5, 351.7, 177.2, 32.0, ", ".join(computed.languages), size=8.0, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            eq_txt = "\n".join(f"{it.name} x{it.quantity}" if it.quantity > 1 else it.name for it in state.inventory)
            _draw_text(painter, 418.9, 421.4, 175.5, 176.1, eq_txt, size=7.5, wrap=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

            # Magic Item Attunement (3 slots below Equipment on Page 2)
            attuned_items = [it.name for it in state.inventory if it.attuned][:3]
            attune_ys = (606.8, 626.8, 646.6)
            for idx, aname in enumerate(attuned_items):
                ay = attune_ys[idx]
                painter.save()
                painter.setBrush(QColor("#111827"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QRectF(425.6, ay + 6.0, 5.0, 5.0))
                painter.restore()
                _draw_text(painter, 437.8, ay, 156.2, 16.5, aname, size=7.8)

            coin_rects = {
                "cp": (418.5, 717.4, 32.2, 20.1),
                "sp": (455.1, 717.9, 31.6, 20.1),
                "ep": (491.2, 717.7, 31.6, 20.1),
                "gp": (526.7, 717.3, 31.6, 20.1),
                "pp": (562.4, 717.9, 31.6, 20.1),
            }
            for coin, rect in coin_rects.items():
                _draw_text(painter, *rect, str(state.currency.get(coin, 0)), size=8.5, bold=True, align=Qt.AlignmentFlag.AlignCenter)
        finally:
            painter.end()

        qpdf_exe = find_executable("qpdf")
        if qpdf_exe:
            res = subprocess.run(
                [qpdf_exe, str(template_pdf), "--overlay", str(overlay_pdf), "--", str(output_path)],
                capture_output=True,
                text=True,
                check=False,
                **subprocess_no_window_kwargs(),
            )
            if res.returncode not in (0, 3) or not output_path.is_file():
                raise RuntimeError(f"qpdf --overlay failed: {res.stderr.strip()}")
        else:
            _overlay_pdf_pypdf(template_pdf, overlay_pdf, output_path)


def build_sheet_html(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
) -> str:
    """Fallback HTML character sheet if official PDF templates or qpdf/pypdf are unavailable."""
    race_el = repo.get(state.race_id)
    bg_el = repo.get(state.background_id)
    align_el = repo.get(state.alignment_id)

    cls_summary = class_display_summary(state, repo) or "No Class"
    subtitle_parts = [
        f"Level {state.level}",
        race_el.name if race_el else "No Race",
        cls_summary,
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

    ab_cells = "".join(
        f"<td align='center' style='border:1px solid #cbd5e1; padding:4px;'>"
        f"<b>{ABILITY_ABBR[ab]}</b><br/>{computed.ability_totals[ab]} ({_fmt_mod(computed.ability_modifiers[ab])})</td>"
        for ab in ABILITIES
    )
    saves_txt = ", ".join(
        f"{'*' if computed.saving_throws[ab].proficient else ''}{ABILITY_ABBR[ab]} {_fmt_mod(computed.saving_throws[ab].bonus)}"
        for ab in ABILITIES
    )
    skills_txt = ", ".join(
        f"{'*' if sk.proficient else ''}{name} {_fmt_mod(sk.bonus)}"
        for name, sk in computed.skills.items()
    )
    feats_txt = ", ".join(
        el.name
        for el in computed.granted_elements
        if el.type in ("Class Feature", "Archetype", "Archetype Feature", "Racial Trait", "Background Feature", "Feat")
    )
    equip_txt = ", ".join(
        f"{it.name} x{it.quantity}" if it.quantity > 1 else it.name for it in state.inventory
    )
    spells_txt = ", ".join(
        (repo.get(sid).name if repo.get(sid) else sid) for sid in _all_character_spells(state, computed)
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
      <p><b>AC:</b> {computed.armor_class} | <b>HP:</b> {computed.max_hp} | <b>Hit Dice:</b> {html.escape(computed.hit_dice_summary or computed.hit_die)} | <b>Speed:</b> {computed.speed} ft | <b>Prof:</b> +{computed.proficiency_bonus} | <b>Init:</b> {_fmt_mod(computed.initiative)}</p>
      <table width='100%' cellspacing='4' cellpadding='2'><tr>{ab_cells}</tr></table>
      <p><b>Saving Throws:</b> {html.escape(saves_txt)}</p>
      <p><b>Skills:</b> {html.escape(skills_txt)}</p>
      <p><b>Features &amp; Traits:</b> {html.escape(feats_txt or '-')}</p>
      <p><b>Equipment:</b> {html.escape(equip_txt or '-')}</p>
      <p><b>Spells:</b> {html.escape(spells_txt or '-')}</p>
      <p><b>Notes:</b> {html.escape(state.notes or '-')}</p>
    </body>
    </html>
    """


_BUNDLED_TEMPLATES_DIR = Path(__file__).resolve().parent / "assets" / "templates"


def _resolve_template_pdf(filename: str, templates_dir: Optional[Path] = None) -> Optional[Path]:
    """Find a PDF sheet template in the user templates dir first, then bundled assets/templates."""
    candidates = [
        (Path(templates_dir) if templates_dir else get_templates_dir()) / filename,
        _BUNDLED_TEMPLATES_DIR / filename,
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def _can_use_pdf_tools() -> bool:
    if find_executable("qpdf"):
        return True
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        return False


def export_character_pdf(
    state: CharacterState,
    computed: ComputedCharacter,
    repo: ContentRepository,
    output_path: Path,
    templates_dir: Optional[Path] = None,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if _can_use_pdf_tools():
        if state.ruleset == "5.5e":
            tpl = _resolve_template_pdf("dnd55e_sheet.pdf", templates_dir)
            if tpl is not None:
                export_55e_overlay_pdf(state, computed, repo, tpl, output_path)
                return
        else:
            tpl = _resolve_template_pdf("dnd5e_sheet.pdf", templates_dir)
            if tpl is not None:
                text_fields, checked = _build_5e_field_map(state, computed, repo, template_pdf=tpl)
                # Collect exact Page 3 prepared checkbox rects for crisp dot rendering
                prep_rects: list[tuple[float, float, float, float]] = []
                qpdf_exe = find_executable("qpdf")
                if qpdf_exe:
                    try:
                        probe = subprocess.run(
                            [qpdf_exe, "--json", "--json-key=acroform", "--json-key=pages", "--json-key=qpdf", str(tpl)],
                            capture_output=True, text=True, timeout=6, check=False,
                            **subprocess_no_window_kwargs(),
                        )
                        if probe.returncode in (0, 3):
                            pdata = json.loads(probe.stdout)
                            pobjs = pdata["qpdf"][1]
                            pmap = {pg["object"]: idx + 1 for idx, pg in enumerate(pdata.get("pages", []))}
                            for f in pdata.get("acroform", {}).get("fields", []):
                                fn = f.get("fullname", "")
                                if fn in checked:
                                    v = pobjs.get(f"obj:{f.get('object', '')}", {}).get("value", {})
                                    rect = v.get("/Rect")
                                    if rect and pmap.get(v.get("/P", ""), 0) == 3:
                                        prep_rects.append((
                                            float(rect[0]),
                                            792.0 - float(rect[3]),
                                            float(rect[2]) - float(rect[0]),
                                            float(rect[3]) - float(rect[1]),
                                        ))
                    except Exception:
                        pass
                with tempfile.TemporaryDirectory(prefix="aurora_5e_fill_") as tmpdir:
                    filled_tmp = Path(tmpdir) / "filled.pdf"
                    fill_pdf_form_qpdf(tpl, text_fields, checked, filled_tmp)
                    _overlay_5e_appearance(filled_tmp, state, output_path, prepared_dot_rects=prep_rects)
                return

    # Fallback HTML export if template PDF or qpdf/pypdf is not installed
    writer = QPdfWriter(str(output_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    writer.setTitle(f"{state.name} - D&D {state.ruleset} Character Sheet")
    doc = QTextDocument()
    doc.setHtml(build_sheet_html(state, computed, repo))
    doc.print_(writer)
