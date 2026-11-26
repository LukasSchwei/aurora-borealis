"""Save and load Aurora .dnd5e character XML files."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Optional

from lxml import etree

from .engine import RulesEngine, class_display_summary, is_asi_select_rule, parse_weight_lb
from .loader import ContentRepository
from .models import ABILITIES, CharacterState, ClassLevel, ComputedCharacter, InventoryItem


def encode_portrait_file(image_path: Path) -> str:
    """Scale portrait image to fit 256x256 PNG and encode as base64."""
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Portrait image not found: {image_path}")
    try:
        from PySide6.QtCore import QBuffer, QIODevice, Qt
        from PySide6.QtGui import QImage

        img = QImage(str(image_path))
        if not img.isNull():
            scaled = img.scaled(
                256,
                256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            if scaled.save(buf, "PNG"):
                return base64.b64encode(bytes(buf.data())).decode("ascii")
    except Exception:
        pass
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


def default_character_extension(ruleset: str) -> str:
    """Return '.dnd55e' for 5.5e characters and '.dnd5e' for 5e characters."""
    return ".dnd55e" if (ruleset or "").strip() == "5.5e" else ".dnd5e"


_SOURCE_ID_PREFIXES: tuple[str, ...] = (
    "ID_WOTC_PHB_",
    "ID_WOTC_XGE_",
    "ID_WOTC_TCE_",
    "ID_WOTC_DMG_",
    "ID_WOTC_VGM_",
    "ID_WOTC_MTF_",
    "ID_WOTC_SCAG_",
    "ID_WOTC_ERLW_",
    "ID_WOTC_EGW_",
    "ID_WOTC_FTD_",
    "ID_WOTC_MOT_",
    "ID_WOTC_VRGR_",
    "ID_WOTC_MPMM_",
    "ID_WOTC_",
    "ID_PHB_",
    "ID_SRD_",
    "ID_5ETOOLS_",
    "ID_",
)

_TYPE_ID_PREFIXES: tuple[str, ...] = (
    "RACE_",
    "SUBRACE_",
    "SUB_RACE_",
    "CLASS_",
    "ARCHETYPE_",
    "BACKGROUND_",
    "ALIGNMENT_",
    "DEITY_",
    "FEAT_",
    "SPELL_",
    "WEAPON_",
    "ARMOR_",
    "MAGIC_ITEM_",
    "ITEM_",
    "MULTICLASS_",
    "LANGUAGE_",
)


def _extract_portrait_fields(node: Optional[etree._Element]) -> tuple[str, str]:
    """Extract (portrait_path, portrait_base64) supporting flat and nested <portrait> tags."""
    if node is None:
        return "", ""
    p_path = ""
    p_b64 = (node.findtext("portrait-data") or "").strip()
    p_node = node.find("portrait")
    if p_node is not None:
        local = (p_node.findtext("local") or "").strip()
        b64 = (p_node.findtext("base64") or "").strip()
        if local:
            p_path = local
        if b64 and not p_b64:
            p_b64 = b64
        if not local and not b64:
            flat = (p_node.text or "").strip()
            if flat:
                p_path = flat
    return p_path, p_b64


def _strip_id_prefixes(raw_id: str) -> str:
    up = (raw_id or "").strip().upper()
    for pfx in _SOURCE_ID_PREFIXES:
        if up.startswith(pfx):
            up = up[len(pfx) :]
            break
    for tpfx in _TYPE_ID_PREFIXES:
        if up.startswith(tpfx):
            up = up[len(tpfx) :]
            break
    return re.sub(r"[^A-Z0-9]+", "_", up).strip("_")


def _resolve_element_id(
    raw_id: str,
    etype: str,
    fallback_name: str,
    repo: ContentRepository,
) -> str:
    """Resolve a legacy or cross-pack Aurora ID against loaded repository elements."""
    raw = (raw_id or "").strip()
    fname = (fallback_name or "").strip()
    if raw and repo.get(raw) is not None:
        return raw
    if not repo.by_id:
        return raw

    if raw:
        raw_low = raw.lower()
        for eid in repo.by_id:
            if eid.lower() == raw_low:
                return eid

    candidates = repo.of_type(etype) if etype else []
    if not candidates and etype:
        if etype in ("Weapon", "Armor", "Item", "Magic Item"):
            for t in ("Weapon", "Armor", "Item", "Magic Item"):
                candidates.extend(repo.of_type(t))
        elif etype in ("Race", "Sub Race", "Race Variant"):
            for t in ("Race", "Sub Race", "Race Variant"):
                candidates.extend(repo.of_type(t))

    search_pool = candidates or list(repo.by_id.values())
    if fname:
        fn_low = fname.lower()
        for el in search_pool:
            if el.name.strip().lower() == fn_low:
                return el.id

    if raw:
        slug_raw = _strip_id_prefixes(raw)
        if slug_raw:
            for el in search_pool:
                if _strip_id_prefixes(el.id) == slug_raw:
                    return el.id
                el_slug = re.sub(r"[^A-Z0-9]+", "_", el.name.upper()).strip("_")
                if el_slug == slug_raw:
                    return el.id
    return raw


def _resolve_multiclass_to_class_id(
    raw_id: str,
    name_hint: str,
    repo: ContentRepository,
) -> str:
    """Map an Aurora <element type='Multiclass'> ID/name to the corresponding Class element ID."""
    raw = (raw_id or "").strip()
    hint = (name_hint or "").strip()
    if raw:
        raw_low = raw.lower()
        for cel in repo.of_type("Class"):
            if cel.multiclass and cel.multiclass.id and cel.multiclass.id.lower() == raw_low:
                return cel.id
        if "MULTICLASS" in raw.upper():
            cls_cand = re.sub(r"MULTICLASS", "CLASS", raw, flags=re.IGNORECASE)
            resolved = _resolve_element_id(cls_cand, "Class", hint, repo)
            if resolved != cls_cand or repo.get(resolved) is not None:
                return resolved
    return _resolve_element_id(raw, "Class", hint, repo)


def _extract_legacy_asi_ability(eid: str, name: str = "") -> Optional[str]:
    """Return ability name if an element ID or name represents a legacy single-ability ASI."""
    combined = f"{eid} {name}".lower()
    if "asi" not in combined and "ability score" not in combined and "ability_score" not in combined:
        return None
    for ab in ABILITIES:
        if re.search(rf"(?<![a-z0-9]){ab}(?![a-z0-9])", combined):
            return ab
    return None


def _parse_rndhp_list(raw: str) -> list[int]:
    vals: list[int] = []
    for tok in re.split(r"[,;\s]+", (raw or "").strip()):
        if tok.isdigit():
            vals.append(int(tok))
    return vals


def serialize_character_xml(
    state: CharacterState,
    repo: ContentRepository,
    computed: ComputedCharacter,
) -> bytes:
    fmt = "dnd55e" if state.ruleset == "5.5e" else "dnd5e"
    root = etree.Element("character", version="0.2", preview="false", format=fmt)

    # Display properties
    disp = etree.SubElement(root, "display-properties", favorite="false")
    etree.SubElement(disp, "name").text = state.name
    race_el = repo.get(state.race_id)
    norm_classes = state.normalized_classes()
    class_el = repo.get(norm_classes[0].class_id) if norm_classes else repo.get(state.class_id)
    bg_el = repo.get(state.background_id)
    etree.SubElement(disp, "race").text = race_el.name if race_el else ""
    if len(norm_classes) > 1:
        disp_class = class_display_summary(state, repo)
    else:
        disp_class = class_el.name if class_el else ""
    etree.SubElement(disp, "class").text = disp_class
    archetypes = [e.name for e in computed.granted_elements if e.type == "Archetype"]
    etree.SubElement(disp, "archetype").text = ", ".join(archetypes)
    etree.SubElement(disp, "background").text = bg_el.name if bg_el else ""
    etree.SubElement(disp, "level").text = str(state.level)
    etree.SubElement(disp, "experience").text = str(state.xp)
    etree.SubElement(disp, "ruleset").text = state.ruleset or "5e"
    etree.SubElement(disp, "hp").text = str(computed.max_hp)
    etree.SubElement(disp, "ac").text = str(computed.armor_class)
    etree.SubElement(disp, "speed").text = str(computed.speed)
    if state.portrait_path:
        etree.SubElement(disp, "portrait").text = state.portrait_path
    if state.portrait_base64:
        etree.SubElement(disp, "portrait-data").text = state.portrait_base64

    build = etree.SubElement(root, "build")

    # Input metadata
    inp = etree.SubElement(build, "input")
    etree.SubElement(inp, "name").text = state.name
    etree.SubElement(inp, "player-name").text = state.player_name
    etree.SubElement(inp, "experience").text = str(state.xp)
    etree.SubElement(inp, "ruleset").text = state.ruleset or "5e"
    etree.SubElement(inp, "gender").text = state.gender
    etree.SubElement(inp, "faith").text = state.faith
    etree.SubElement(inp, "backstory").text = state.backstory
    etree.SubElement(inp, "notes").text = state.notes
    if state.portrait_path:
        etree.SubElement(inp, "portrait").text = state.portrait_path
    if state.portrait_base64:
        etree.SubElement(inp, "portrait-data").text = state.portrait_base64

    appearance = etree.SubElement(inp, "appearance")
    etree.SubElement(appearance, "age").text = state.age
    etree.SubElement(appearance, "height").text = state.height
    etree.SubElement(appearance, "weight").text = state.weight
    etree.SubElement(appearance, "eyes").text = state.eyes
    etree.SubElement(appearance, "skin").text = state.skin
    etree.SubElement(appearance, "hair").text = state.hair

    currency = etree.SubElement(inp, "currency")
    etree.SubElement(currency, "copper").text = str(state.currency.get("cp", 0))
    etree.SubElement(currency, "silver").text = str(state.currency.get("sp", 0))
    etree.SubElement(currency, "electrum").text = str(state.currency.get("ep", 0))
    etree.SubElement(currency, "gold").text = str(state.currency.get("gp", 0))
    etree.SubElement(currency, "platinum").text = str(state.currency.get("pp", 0))

    # Abilities
    ab_node = etree.SubElement(build, "abilities", {"available-points": "27"})
    for ab in ABILITIES:
        etree.SubElement(ab_node, ab).text = str(state.abilities.get(ab, 10))
    if state.background_asi:
        bg_asi_node = etree.SubElement(ab_node, "background-asi")
        for ab, val in state.background_asi.items():
            if ab in ABILITIES and val:
                etree.SubElement(bg_asi_node, ab).text = str(val)

    # Elements tree
    elems_node = etree.SubElement(build, "elements")
    etree.SubElement(elems_node, "element", type="Level", name=str(state.level), id=f"ID_INTERNAL_LEVEL_{state.level}")
    for etype, eid in (
        ("Race", state.race_id),
        ("Background", state.background_id),
        ("Alignment", state.alignment_id),
        ("Deity", state.deity_id),
    ):
        if eid:
            el = repo.get(eid)
            etree.SubElement(
                elems_node,
                "element",
                type=etype,
                name=el.name if el else eid,
                id=eid,
                registered="true",
            )
    for idx, cl in enumerate(norm_classes):
        cel = repo.get(cl.class_id)
        etree.SubElement(
            elems_node,
            "element",
            type="Class",
            name=cel.name if cel else cl.class_id,
            id=cl.class_id,
            level=str(cl.level),
            primary="true" if idx == 0 else "false",
            registered="true",
        )

    # Hit Points mode, level order, and rolled/manual per-level rolls
    hp_node = etree.SubElement(build, "hit-points", mode=state.hp_mode or "average")
    for lvl_idx, cid in enumerate(state.normalized_level_order(), start=1):
        attrs = {"level": str(lvl_idx), "class-id": cid}
        if lvl_idx in state.hp_rolls:
            attrs["roll"] = str(state.hp_rolls[lvl_idx])
        etree.SubElement(hp_node, "level-entry", **attrs)

    # Level-Up Wizard ASI & Feat overrides
    if state.level_up_asi or state.level_up_feats:
        lu_node = etree.SubElement(build, "level-ups")
        for key, asi_map in sorted(state.level_up_asi.items()):
            for ab, val in sorted(asi_map.items()):
                if val:
                    etree.SubElement(lu_node, "asi", key=key, ability=ab, value=str(val))
        for key, fid in sorted(state.level_up_feats.items()):
            if fid:
                etree.SubElement(lu_node, "feat", key=key, id=fid)

    # Persist user selections cleanly
    selections_node = etree.SubElement(build, "selections")
    for sel_key, chosen_ids in sorted(state.selections.items()):
        for idx, cid in enumerate(chosen_ids):
            if cid:
                etree.SubElement(
                    selections_node,
                    "selection",
                    key=sel_key,
                    index=str(idx),
                    value=cid,
                )

    # Equipment & Storage Containers
    equip_node = etree.SubElement(build, "equipment")
    if state.containers:
        containers_node = etree.SubElement(equip_node, "containers")
        for cinfo in state.containers:
            if not isinstance(cinfo, dict) or not (cinfo.get("name") or "").strip():
                continue
            etree.SubElement(
                containers_node,
                "container",
                name=str(cinfo.get("name", "")).strip(),
                **{
                    "ignore-weight": "true" if cinfo.get("ignore_weight") else "false",
                    "notes": str(cinfo.get("notes") or ""),
                },
            )
    for item in state.inventory:
        attrs = {
            "identifier": item.element_id,
            "name": item.name,
            "amount": str(item.quantity),
            "equipped": "true" if item.equipped else "false",
            "weight": str(item.weight),
            "category": item.category,
        }
        if item.magic_bonus:
            attrs["magic-bonus"] = str(item.magic_bonus)
        if item.enchantment:
            attrs["enchantment"] = item.enchantment
        if item.attuned:
            attrs["attuned"] = "true"
        if item.container and item.container != "On Person":
            attrs["container"] = item.container
        if item.ignore_weight:
            attrs["ignore-weight"] = "true"
        if item.notes:
            attrs["notes"] = item.notes
        if item.charges:
            attrs["charges"] = str(item.charges)
        if item.max_charges:
            attrs["max-charges"] = str(item.max_charges)
        if item.custom:
            attrs["custom"] = "true"
        etree.SubElement(equip_node, "item", **attrs)

    # Magic / Spells
    magic_node = etree.SubElement(
        build,
        "magic",
        {"allow-extra": "true" if state.allow_extra_spells else "false"},
    )
    if computed.spellcasting or state.known_spells or state.prepared_spells:
        sc = etree.SubElement(
            magic_node,
            "spellcasting",
            name=computed.spellcasting.caster_name if computed.spellcasting else "Manual",
            ability=computed.spellcasting.ability if computed.spellcasting else "Intelligence",
        )
        spells_node = etree.SubElement(sc, "spells")
        prepared_set = set(state.prepared_spells)
        known_union = list(dict.fromkeys([*state.known_spells, *state.prepared_spells]))
        for sid in known_union:
            sel = repo.get(sid)
            s_attrs = {
                "name": sel.name if sel else sid,
                "id": sid,
                "known": "true" if sid in state.known_spells else "false",
                "prepared": "true" if sid in prepared_set else "false",
            }
            if sid in state.spell_sources and state.spell_sources[sid]:
                s_attrs["source-class"] = state.spell_sources[sid]
            etree.SubElement(spells_node, "spell", **s_attrs)

    # 5.5e rules state
    r55 = etree.SubElement(
        build,
        "rules-55e",
        {
            "heroic-inspiration": "true" if state.heroic_inspiration else "false",
            "exhaustion": str(max(0, min(6, int(state.exhaustion_level or 0)))),
            "divine-order": state.divine_order_55e,
            "primal-order": state.primal_order_55e,
        },
    )
    for wm in state.weapon_masteries:
        if wm:
            etree.SubElement(r55, "weapon-mastery").text = wm

    # Manual rule overrides
    if state.rule_overrides or state.allow_extra_spells:
        ov_node = etree.SubElement(build, "rule-overrides")
        merged_ov = dict(state.rule_overrides)
        if state.allow_extra_spells:
            merged_ov["allow_extra_spells"] = True
        for k, v in sorted(merged_ov.items()):
            etree.SubElement(ov_node, "override", key=k, value="true" if v else "false")

    # Animal Forms / Wild Shape
    if state.animal_forms or state.active_animal_form_id or state.custom_animal_forms:
        import json

        af_node = etree.SubElement(build, "animal-forms", active=state.active_animal_form_id)
        for fid in state.animal_forms:
            if fid:
                etree.SubElement(af_node, "form", id=fid)
        for cf in state.custom_animal_forms:
            if isinstance(cf, dict):
                etree.SubElement(af_node, "custom-form").text = json.dumps(cf, ensure_ascii=False)

    # Attached Companions
    if state.companions:
        import json

        comp_node = etree.SubElement(build, "companions")
        for cdata in state.companions:
            etree.SubElement(comp_node, "companion").text = json.dumps(cdata, ensure_ascii=False)

    # Manual Proficiency Overrides
    if (
        state.manual_save_profs
        or state.manual_skill_profs
        or state.manual_skill_expertise
        or state.manual_proficiencies
    ):
        mp_node = etree.SubElement(build, "manual-proficiencies")
        for ab in state.manual_save_profs:
            etree.SubElement(mp_node, "save").text = ab
        for sk in state.manual_skill_profs:
            etree.SubElement(mp_node, "skill").text = sk
        for sk in state.manual_skill_expertise:
            etree.SubElement(mp_node, "expertise").text = sk
        for pr in state.manual_proficiencies:
            etree.SubElement(mp_node, "proficiency").text = pr

    # Level 1-20 Build Plan
    if state.build_plan:
        import json

        bp_node = etree.SubElement(build, "build-plan")
        for entry in state.build_plan:
            if not isinstance(entry, dict):
                continue
            attrs = {
                "level": str(entry.get("level", 1)),
                "class-id": str(entry.get("class_id") or ""),
                "subclass-id": str(entry.get("subclass_id") or ""),
                "asi-or-feat": str(entry.get("asi_or_feat") or ""),
                "spells": json.dumps(entry.get("spells") or [], ensure_ascii=False),
            }
            en = etree.SubElement(bp_node, "entry", **attrs)
            en.text = str(entry.get("notes") or "")

    return etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True)


def save_dnd5e(
    state: CharacterState,
    repo: ContentRepository,
    computed: ComputedCharacter,
    path: Path,
) -> None:
    path = Path(path)
    xml_bytes = serialize_character_xml(state, repo, computed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(xml_bytes)


def load_dnd5e(path: Path, repo: ContentRepository) -> CharacterState:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Character file not found: {path}")
    return parse_character_xml(path.read_bytes(), repo, source_label=str(path))


def parse_character_xml(
    xml_bytes: bytes,
    repo: ContentRepository,
    source_label: str = "<bytes>",
) -> CharacterState:
    parser = etree.XMLParser(recover=True, remove_comments=True)
    root = etree.fromstring(xml_bytes, parser=parser)
    if root is None:
        raise ValueError(f"Invalid .dnd5e file: {source_label}")

    state = CharacterState()
    build = root.find("build")
    disp = root.find("display-properties")

    disp_race_name = ""
    disp_class_name = ""
    disp_bg_name = ""
    if disp is not None:
        state.name = (disp.findtext("name") or state.name).strip()
        disp_race_name = (disp.findtext("race") or "").strip()
        disp_class_name = (disp.findtext("class") or "").strip()
        disp_bg_name = (disp.findtext("background") or "").strip()
        lvl_txt = (disp.findtext("level") or "").strip()
        if lvl_txt.isdigit():
            state.level = max(1, min(20, int(lvl_txt)))
        xp_disp = (disp.findtext("experience") or "").strip()
        if xp_disp.isdigit():
            state.xp = int(xp_disp)
        rs = (disp.findtext("ruleset") or "").strip()
        if rs in ("5e", "5.5e"):
            state.ruleset = rs
        p_path, p_b64 = _extract_portrait_fields(disp)
        if p_path:
            state.portrait_path = p_path
        if p_b64:
            state.portrait_base64 = p_b64

    if build is None:
        return state

    inp = build.find("input")
    if inp is not None:
        state.name = (inp.findtext("name") or state.name).strip()
        state.player_name = (inp.findtext("player-name") or state.player_name).strip()
        xp_inp = (inp.findtext("experience") or "").strip()
        if xp_inp.isdigit():
            state.xp = int(xp_inp)
        rs_inp = (inp.findtext("ruleset") or "").strip()
        if rs_inp in ("5e", "5.5e"):
            state.ruleset = rs_inp
        state.gender = (inp.findtext("gender") or "").strip()
        state.faith = (inp.findtext("faith") or "").strip()
        state.backstory = (
            inp.findtext("backstory")
            or inp.findtext("background-story")
            or ""
        ).strip()
        notes_el = inp.find("notes")
        if notes_el is not None:
            sub_notes = [(n.text or "").strip() for n in notes_el.findall("note") if (n.text or "").strip()]
            if sub_notes:
                state.notes = "\n\n".join(sub_notes)
            else:
                state.notes = (notes_el.text or "").strip()

        # Append optional legacy Aurora roleplay/character details if present
        legacy_note_sections: list[str] = []
        for tag, label in (
            ("background-traits", "Personality Traits"),
            ("background-ideals", "Ideals"),
            ("background-bonds", "Bonds"),
            ("background-flaws", "Flaws"),
            ("background-trinket", "Trinket"),
            ("additional-features", "Additional Features"),
            ("quest", "Quest"),
        ):
            txt = (inp.findtext(tag) or "").strip()
            if txt and txt not in state.notes:
                legacy_note_sections.append(f"{label}: {txt}")
        org_el = inp.find("organization")
        if org_el is not None:
            org_name = (org_el.findtext("name") or "").strip()
            org_allies = (org_el.findtext("allies") or "").strip()
            if org_name and org_name not in state.notes:
                legacy_note_sections.append(f"Organization: {org_name}")
            if org_allies and org_allies not in state.notes:
                legacy_note_sections.append(f"Allies: {org_allies}")
        if legacy_note_sections:
            joined_extra = "\n".join(legacy_note_sections)
            state.notes = f"{state.notes}\n\n{joined_extra}".strip() if state.notes else joined_extra

        inp_p, inp_b64 = _extract_portrait_fields(inp)
        if not state.portrait_path and inp_p:
            state.portrait_path = inp_p
        if not state.portrait_base64 and inp_b64:
            state.portrait_base64 = inp_b64

        app_inp = inp.find("appearance")
        if app_inp is not None:
            if not state.gender:
                state.gender = (app_inp.findtext("gender") or "").strip()
            state.age = (app_inp.findtext("age") or "").strip()
            state.height = (app_inp.findtext("height") or "").strip()
            state.weight = (app_inp.findtext("weight") or "").strip()
            state.eyes = (app_inp.findtext("eyes") or "").strip()
            state.skin = (app_inp.findtext("skin") or "").strip()
            state.hair = (app_inp.findtext("hair") or "").strip()
            ap_p, ap_b64 = _extract_portrait_fields(app_inp)
            if not state.portrait_path and ap_p:
                state.portrait_path = ap_p
            if not state.portrait_base64 and ap_b64:
                state.portrait_base64 = ap_b64

        cur = inp.find("currency")
        if cur is not None:
            mapping = {
                "copper": "cp",
                "silver": "sp",
                "electrum": "ep",
                "gold": "gp",
                "platinum": "pp",
            }
            for tag, key in mapping.items():
                txt = (cur.findtext(tag) or "0").strip()
                try:
                    state.currency[key] = int(txt)
                except ValueError:
                    pass

    app_build = build.find("appearance")
    if app_build is not None:
        if not state.gender:
            state.gender = (app_build.findtext("gender") or "").strip()
        if not state.age:
            state.age = (app_build.findtext("age") or "").strip()
        if not state.height:
            state.height = (app_build.findtext("height") or "").strip()
        if not state.weight:
            state.weight = (app_build.findtext("weight") or "").strip()
        if not state.eyes:
            state.eyes = (app_build.findtext("eyes") or "").strip()
        if not state.skin:
            state.skin = (app_build.findtext("skin") or "").strip()
        if not state.hair:
            state.hair = (app_build.findtext("hair") or "").strip()
        ab_p, ab_b64 = _extract_portrait_fields(app_build)
        if not state.portrait_path and ab_p:
            state.portrait_path = ab_p
        if not state.portrait_base64 and ab_b64:
            state.portrait_base64 = ab_b64

    if inp is None or inp.find("currency") is None:
        cur_eq = build.find("equipment/currency")
        if cur_eq is not None:
            mapping = {
                "copper": "cp",
                "silver": "sp",
                "electrum": "ep",
                "gold": "gp",
                "platinum": "pp",
            }
            for tag, key in mapping.items():
                txt = (cur_eq.findtext(tag) or "0").strip()
                try:
                    state.currency[key] = int(txt)
                except ValueError:
                    pass

    ab_node = build.find("abilities")
    if ab_node is not None:
        for ab in ABILITIES:
            txt = (ab_node.findtext(ab) or "").strip()
            if txt.isdigit():
                state.abilities[ab] = int(txt)
        bg_asi_node = ab_node.find("background-asi")
        if bg_asi_node is not None:
            for ab in ABILITIES:
                txt = (bg_asi_node.findtext(ab) or "").strip()
                if txt.lstrip("-").isdigit():
                    val = int(txt)
                    if val:
                        state.background_asi[ab] = val

    legacy_element_ids: list[str] = []
    legacy_asi_abilities: list[str] = []
    parsed_classes: list[tuple[bool, ClassLevel]] = []
    has_explicit_class_levels = False
    legacy_level_classes: list[tuple[int, str, Optional[int]]] = []
    legacy_class_rndhp: dict[str, list[int]] = {}
    legacy_hp_rolled_hint = False

    def _add_legacy_id(cand_id: str, cand_name: str = "") -> None:
        if not cand_id:
            return
        if cand_id not in legacy_element_ids:
            legacy_element_ids.append(cand_id)
        ab = _extract_legacy_asi_ability(cand_id, cand_name)
        if ab:
            legacy_asi_abilities.append(ab)

    def _scan_elements_tree(container: Optional[etree._Element]) -> None:
        nonlocal has_explicit_class_levels, legacy_hp_rolled_hint
        if container is None:
            return
        max_lvl = 0
        for el in container.findall(".//element"):
            etype = (el.get("type") or "").strip()
            ename = (el.get("name") or "").strip()
            raw_id = (el.get("id") or "").strip()
            reg = (el.get("registered") or "").strip()
            reg_id = reg if reg and reg.lower() not in ("true", "false") else ""
            eff_id = raw_id or reg_id

            if reg_id:
                _add_legacy_id(reg_id, ename)
            if raw_id:
                _add_legacy_id(raw_id, ename)

            if "rolled_hp" in eff_id.lower() or "roll_hp" in eff_id.lower():
                legacy_hp_rolled_hint = True
            if (el.get("average-hp") or "").strip().lower() == "false":
                legacy_hp_rolled_hint = True

            if etype == "Race" and eff_id and not state.race_id:
                state.race_id = _resolve_element_id(eff_id, "Race", ename or disp_race_name, repo)
            elif etype == "Class" and eff_id:
                resolved_cid = _resolve_element_id(eff_id, "Class", ename, repo)
                if not state.class_id:
                    state.class_id = resolved_cid
                lvl_attr = (el.get("level") or "").strip()
                is_prim = (el.get("primary") or "").strip().lower() == "true"
                if lvl_attr.isdigit():
                    has_explicit_class_levels = True
                    parsed_classes.append((is_prim, ClassLevel(resolved_cid, max(1, min(20, int(lvl_attr))))))
                elif not any(c.class_id == resolved_cid for _, c in parsed_classes):
                    parsed_classes.append((is_prim or len(parsed_classes) == 0, ClassLevel(resolved_cid, 1)))
                rndhp = _parse_rndhp_list(el.get("rndhp") or "")
                if rndhp:
                    legacy_class_rndhp[resolved_cid] = rndhp
            elif etype == "Multiclass" and eff_id:
                resolved_cid = _resolve_multiclass_to_class_id(eff_id, ename, repo)
                if resolved_cid:
                    if not any(c.class_id == resolved_cid for _, c in parsed_classes):
                        parsed_classes.append((False, ClassLevel(resolved_cid, 1)))
                    rndhp = _parse_rndhp_list(el.get("rndhp") or "")
                    if rndhp:
                        legacy_class_rndhp[resolved_cid] = rndhp
            elif etype == "Background" and eff_id and not state.background_id:
                state.background_id = _resolve_element_id(eff_id, "Background", ename or disp_bg_name, repo)
            elif etype == "Alignment" and eff_id and not state.alignment_id:
                state.alignment_id = _resolve_element_id(eff_id, "Alignment", ename, repo)
            elif etype == "Deity" and eff_id and not state.deity_id:
                state.deity_id = _resolve_element_id(eff_id, "Deity", ename, repo)
            elif etype == "Level":
                lvl_num = 0
                if ename.isdigit():
                    lvl_num = int(ename)
                else:
                    m_lvl = re.search(r"ID_INTERNAL_LEVEL_(\d+)", eff_id, re.IGNORECASE)
                    if m_lvl:
                        lvl_num = int(m_lvl.group(1))
                if lvl_num > 0:
                    max_lvl = max(max_lvl, lvl_num)
                    lvl_cls_raw = (el.get("class") or "").strip()
                    lvl_cls_id = ""
                    if lvl_cls_raw:
                        lvl_cls_id = _resolve_multiclass_to_class_id(lvl_cls_raw, "", repo)
                    else:
                        child_mc = el.find("element[@type='Multiclass']")
                        child_cls = el.find("element[@type='Class']")
                        cnode = child_mc if child_mc is not None else child_cls
                        if cnode is not None:
                            cid_raw = (cnode.get("id") or cnode.get("registered") or "").strip()
                            cname_raw = (cnode.get("name") or "").strip()
                            lvl_cls_id = (
                                _resolve_multiclass_to_class_id(cid_raw, cname_raw, repo)
                                if child_mc is not None
                                else _resolve_element_id(cid_raw, "Class", cname_raw, repo)
                            )
                    rnd_raw = (el.get("rndhp") or "").strip()
                    rnd_val = int(rnd_raw) if rnd_raw.isdigit() else None
                    legacy_level_classes.append((lvl_num, lvl_cls_id, rnd_val))
        if max_lvl > 0:
            state.level = max(state.level, max(1, min(20, max_lvl)))

    elems_node = build.find("elements")
    _scan_elements_tree(elems_node)
    sum_node = build.find("sum")
    _scan_elements_tree(sum_node)

    # Display-properties fallback when <elements> omitted Race/Class/Background
    if repo.by_id:
        if not state.race_id and disp_race_name:
            cand = _resolve_element_id("", "Race", disp_race_name, repo)
            if cand:
                state.race_id = cand
        if not state.background_id and disp_bg_name:
            cand = _resolve_element_id("", "Background", disp_bg_name, repo)
            if cand:
                state.background_id = cand
        if not parsed_classes and disp_class_name:
            # Handle "Wizard", "Wizard 5", or "Fighter 3 / Wizard 2"
            parts = [p.strip() for p in re.split(r"[/,]", disp_class_name) if p.strip()]
            for p_idx, part in enumerate(parts):
                m_c = re.match(r"^(.+?)(?:\s+(\d+))?$", part)
                if m_c:
                    cname_part = m_c.group(1).strip()
                    clvl_part = int(m_c.group(2)) if m_c.group(2) else (state.level if len(parts) == 1 else 1)
                    cid_res = _resolve_element_id("", "Class", cname_part, repo)
                    if cid_res:
                        if not state.class_id:
                            state.class_id = cid_res
                        parsed_classes.append((p_idx == 0, ClassLevel(cid_res, max(1, min(20, clvl_part)))))
                        if len(parts) > 1 or m_c.group(2):
                            has_explicit_class_levels = True

    if parsed_classes:
        if has_explicit_class_levels:
            ordered_mc = [cl for prim, cl in parsed_classes if prim] + [cl for prim, cl in parsed_classes if not prim]
            state.classes = ordered_mc
            state.sync_from_classes()
        elif len(parsed_classes) > 1 or any(cid for _, cid, _ in legacy_level_classes):
            # Reconstruct multiclass counts & level_order from legacy <element type="Level"> nodes
            ordered_cids = [cl.class_id for prim, cl in parsed_classes if prim] + [
                cl.class_id for prim, cl in parsed_classes if not prim
            ]
            primary_cid = ordered_cids[0]
            counts: dict[str, int] = {}
            lvl_order: list[str] = []
            for _lvl_n, lcid, _rnd in sorted(legacy_level_classes, key=lambda x: x[0]):
                use_cid = lcid or primary_cid
                counts[use_cid] = counts.get(use_cid, 0) + 1
                lvl_order.append(use_cid)
            for cid in ordered_cids:
                if cid not in counts:
                    counts[cid] = 1
            if not lvl_order and state.level > 0:
                lvl_order = [primary_cid] * state.level
            state.classes = [ClassLevel(cid, counts[cid]) for cid in ordered_cids if counts.get(cid, 0) > 0]
            for cid, cnt in counts.items():
                if cid not in ordered_cids and cnt > 0:
                    state.classes.append(ClassLevel(cid, cnt))
            state.level_order = lvl_order
            state.sync_from_classes()
        elif state.class_id:
            state.classes = [ClassLevel(state.class_id, state.level)]
            state.sync_from_classes()

    # Apply legacy rndhp values if present
    for lvl_num, _lcid, rnd_val in legacy_level_classes:
        if rnd_val is not None and lvl_num not in state.hp_rolls:
            state.hp_rolls[lvl_num] = rnd_val
    if legacy_class_rndhp:
        order = state.normalized_level_order() or ([state.class_id] * state.level if state.class_id else [])
        per_class_idx: dict[str, int] = {}
        for lvl_idx, cid in enumerate(order, start=1):
            idx_in_cls = per_class_idx.get(cid, 0)
            per_class_idx[cid] = idx_in_cls + 1
            rolls = legacy_class_rndhp.get(cid, [])
            if idx_in_cls < len(rolls) and lvl_idx not in state.hp_rolls:
                state.hp_rolls[lvl_idx] = rolls[idx_in_cls]
    if legacy_hp_rolled_hint:
        state.hp_mode = "rolled"

    hp_node = build.find("hit-points")
    if hp_node is not None:
        mode = (hp_node.get("mode") or "average").strip().lower()
        state.hp_mode = "rolled" if mode == "rolled" else "average"
        entries: list[tuple[int, str, Optional[int]]] = []
        for entry in hp_node.findall("level-entry"):
            lvl_s = (entry.get("level") or "").strip()
            cid = (entry.get("class-id") or "").strip()
            roll_s = (entry.get("roll") or "").strip()
            if lvl_s.isdigit():
                lvl_i = int(lvl_s)
                roll_i = int(roll_s) if roll_s.lstrip("-").isdigit() else None
                entries.append((lvl_i, cid, roll_i))
        entries.sort(key=lambda x: x[0])
        if entries:
            order_cids = [cid for _, cid, _ in entries if cid]
            if order_cids:
                state.level_order = order_cids
            for lvl_i, _cid, roll_i in entries:
                if roll_i is not None:
                    state.hp_rolls[lvl_i] = roll_i

    lu_node = build.find("level-ups")
    if lu_node is not None:
        for asi in lu_node.findall("asi"):
            key = (asi.get("key") or "").strip()
            ab = (asi.get("ability") or "").strip().lower()
            val_s = (asi.get("value") or "").strip()
            if key and ab in ABILITIES and val_s.lstrip("-").isdigit():
                state.level_up_asi.setdefault(key, {})[ab] = int(val_s)
        for ft in lu_node.findall("feat"):
            key = (ft.get("key") or "").strip()
            fid = (ft.get("id") or "").strip()
            if key and fid:
                state.level_up_feats[key] = fid

    sel_node = build.find("selections")
    if sel_node is not None and len(sel_node.findall("selection")) > 0:
        for s in sel_node.findall("selection"):
            key = (s.get("key") or "").strip()
            val = (s.get("value") or "").strip()
            if key and val:
                state.selections.setdefault(key, []).append(val)
    elif legacy_element_ids and repo.by_id:
        # Backward compatibility with original Aurora Builder .dnd5e files:
        # reconstruct user selections (including ASI & cross-pack IDs) from nested <build><elements> / <sum>.
        engine = RulesEngine(repo)
        consumed_ids: set[str] = set()
        remaining_asi = list(legacy_asi_abilities)

        resolved_legacy_candidates: list[str] = []
        for cand in legacy_element_ids:
            if cand not in resolved_legacy_candidates:
                resolved_legacy_candidates.append(cand)
            res = _resolve_element_id(cand, "", "", repo)
            if res and res not in resolved_legacy_candidates:
                resolved_legacy_candidates.append(res)

        for _ in range(8):
            comp = engine.evaluate(state)
            progressed = False
            for active_sel in comp.active_selections:
                existing = list(state.selections.get(active_sel.key, []))
                if len([v for v in existing if v]) >= active_sel.rule.number:
                    continue
                opt_ids = {oid for oid, _oname in active_sel.options}

                # Handle ASI selections (allowing repeated ability picks across levels/slots)
                if is_asi_select_rule(active_sel.rule) and remaining_asi:
                    if active_sel.rule.number >= 2:
                        while len([v for v in existing if v]) < active_sel.rule.number and remaining_asi:
                            ab = remaining_asi.pop(0)
                            syn_id = f"ID_AURORA_ASI_PLUS1_{ab.upper()}"
                            if syn_id in opt_ids:
                                existing.append(syn_id)
                                progressed = True
                    elif len(remaining_asi) >= 2:
                        ab1 = remaining_asi.pop(0)
                        ab2 = remaining_asi.pop(0)
                        if ab1 == ab2:
                            cand_asi = f"ID_AURORA_ASI_PLUS2_{ab1.upper()}"
                        else:
                            ordered_pair = [a for a in ABILITIES if a in (ab1, ab2)]
                            cand_asi = f"ID_AURORA_ASI_PLUS1_{ordered_pair[0].upper()}_{ordered_pair[1].upper()}"
                        if cand_asi in opt_ids:
                            existing.append(cand_asi)
                            progressed = True
                        else:
                            remaining_asi.insert(0, ab2)
                            remaining_asi.insert(0, ab1)
                    if existing:
                        state.selections[active_sel.key] = existing[: active_sel.rule.number]
                        continue

                opt_by_slug = {
                    _strip_id_prefixes(oid): oid
                    for oid, _oname in active_sel.options
                    if _strip_id_prefixes(oid)
                }
                for cand in resolved_legacy_candidates:
                    if len([v for v in existing if v]) >= active_sel.rule.number:
                        break
                    matched_oid = ""
                    if cand in opt_ids:
                        matched_oid = cand
                    else:
                        cslug = _strip_id_prefixes(cand)
                        if cslug and cslug in opt_by_slug:
                            matched_oid = opt_by_slug[cslug]
                    if (
                        matched_oid
                        and matched_oid not in existing
                        and matched_oid not in consumed_ids
                    ):
                        existing.append(matched_oid)
                        consumed_ids.add(matched_oid)
                        progressed = True
                if existing:
                    state.selections[active_sel.key] = existing[: active_sel.rule.number]
            if not progressed:
                break

    equip_node = build.find("equipment")
    if equip_node is not None:
        containers_node = equip_node.find("containers")
        if containers_node is not None:
            for cnode in containers_node.findall("container"):
                cname = (cnode.get("name") or "").strip()
                if cname:
                    state.containers.append(
                        {
                            "name": cname,
                            "ignore_weight": (cnode.get("ignore-weight") or "false").lower() == "true",
                            "notes": (cnode.get("notes") or "").strip(),
                        }
                    )
        storage_node = build.find("storage")
        if storage_node is not None and not state.containers:
            for loc in storage_node.findall("location"):
                lname = (loc.get("name") or "").strip()
                if lname:
                    state.containers.append(
                        {
                            "name": lname,
                            "ignore_weight": True,
                            "notes": "Imported legacy storage location",
                        }
                    )
        for item in equip_node.findall(".//item"):
            raw_eid = (item.get("identifier") or item.get("id") or "").strip()
            name = (item.get("name") or "").strip()
            details_name = (item.findtext("details/name") or "").strip()
            if details_name:
                name = details_name
            eid = _resolve_element_id(raw_eid, "Item", name, repo) if (raw_eid or name) else ""
            el = repo.get(eid) if eid else None
            if not name and el is not None:
                name = el.name
            try:
                qty = int(item.get("amount") or "1")
            except ValueError:
                qty = 1
            equipped = (item.get("equipped") or "").lower() == "true"
            raw_w = (item.get("weight") or "0").strip()
            m_w = re.search(r"(\d+(?:\.\d+)?)", raw_w)
            w = float(m_w.group(1)) if m_w else 0.0
            if w <= 0.0 and el is not None:
                w = parse_weight_lb(el)
            cat = (item.get("category") or (el.type if el else "")).strip()
            try:
                m_bonus = int(item.get("magic-bonus") or "0")
            except ValueError:
                m_bonus = 0
            ench = (item.get("enchantment") or "").strip()
            adorners = [
                (ad.get("name") or "").strip()
                for ad in item.findall(".//adorner")
                if (ad.get("name") or "").strip()
            ]
            if adorners:
                if not ench:
                    ench = ", ".join(adorners)
                if m_bonus == 0:
                    for ad_name in adorners:
                        m_b = re.search(r"\+(\d+)", ad_name)
                        if m_b:
                            m_bonus = int(m_b.group(1))
                            break
            attuned = (
                (item.get("attuned") or "").lower() == "true"
                or (item.get("attunement") or "").lower() == "true"
            )
            container = (item.get("container") or item.get("stored") or "On Person").strip() or "On Person"
            ignore_w = (item.get("ignore-weight") or "false").lower() == "true"
            notes = (item.get("notes") or "").strip()
            try:
                charges = int(item.get("charges") or "0")
            except ValueError:
                charges = 0
            try:
                max_charges = int(item.get("max-charges") or "0")
            except ValueError:
                max_charges = 0
            custom = (item.get("custom") or "false").lower() == "true"
            if eid or name:
                state.inventory.append(
                    InventoryItem(
                        element_id=eid,
                        name=name or eid,
                        quantity=max(1, qty),
                        equipped=equipped,
                        weight=w,
                        category=cat,
                        magic_bonus=m_bonus,
                        enchantment=ench,
                        attuned=attuned,
                        container=container,
                        ignore_weight=ignore_w,
                        notes=notes,
                        charges=charges,
                        max_charges=max_charges,
                        custom=custom,
                    )
                )

    magic_node = build.find("magic")
    if magic_node is not None:
        state.allow_extra_spells = (magic_node.get("allow-extra") or "false").lower() == "true"

        def _ingest_spell_node(sp: etree._Element, default_src_cls: str = "") -> None:
            raw_sid = (sp.get("id") or "").strip()
            sp_name = (sp.get("name") or "").strip()
            if not raw_sid and not sp_name:
                return
            sid = _resolve_element_id(raw_sid, "Spell", sp_name, repo) if repo.by_id else (raw_sid or sp_name)
            if not sid:
                return
            is_known = (sp.get("known") or "true").lower() == "true"
            is_prep = (
                (sp.get("prepared") or "false").lower() == "true"
                or (sp.get("always-prepared") or "false").lower() == "true"
            )
            if is_known and sid not in state.known_spells:
                state.known_spells.append(sid)
            if is_prep and sid not in state.prepared_spells:
                state.prepared_spells.append(sid)
            src_cls = (sp.get("source-class") or "").strip() or default_src_cls
            if src_cls and sid not in state.spell_sources:
                state.spell_sources[sid] = src_cls

        seen_sp_nodes: set[int] = set()
        for sc_node in magic_node.findall("spellcasting"):
            sc_src_raw = (sc_node.get("source") or "").strip()
            sc_name = (sc_node.get("name") or "").strip()
            sc_class_id = ""
            if sc_src_raw and sc_src_raw != "Manual":
                sc_class_id = _resolve_element_id(sc_src_raw, "Class", sc_name, repo)
            elif sc_name and sc_name != "Manual":
                sc_class_id = _resolve_element_id("", "Class", sc_name, repo)
                if sc_class_id and not repo.get(sc_class_id):
                    sc_class_id = ""
            for sp in sc_node.findall(".//spell"):
                seen_sp_nodes.add(id(sp))
                _ingest_spell_node(sp, default_src_cls=sc_class_id)

        for sp in magic_node.findall(".//spell"):
            if id(sp) not in seen_sp_nodes:
                _ingest_spell_node(sp)

    r55 = build.find("rules-55e")
    if r55 is not None:
        state.heroic_inspiration = (r55.get("heroic-inspiration") or "false").lower() == "true"
        ex_s = (r55.get("exhaustion") or "0").strip()
        if ex_s.isdigit():
            state.exhaustion_level = max(0, min(6, int(ex_s)))
        state.divine_order_55e = (r55.get("divine-order") or "").strip()
        state.primal_order_55e = (r55.get("primal-order") or "").strip()
        state.weapon_masteries = [
            (wm.text or "").strip()
            for wm in r55.findall("weapon-mastery")
            if (wm.text or "").strip()
        ]

    ov_node = build.find("rule-overrides")
    if ov_node is not None:
        for ov in ov_node.findall("override"):
            k = (ov.get("key") or "").strip()
            v = (ov.get("value") or "false").lower() == "true"
            if k:
                state.set_override(k, v)
    elif state.allow_extra_spells:
        state.rule_overrides["allow_extra_spells"] = True

    af_node = build.find("animal-forms")
    if af_node is not None:
        import json

        state.active_animal_form_id = (af_node.get("active") or "").strip()
        state.animal_forms = [
            (fn.get("id") or "").strip()
            for fn in af_node.findall("form")
            if (fn.get("id") or "").strip()
        ]
        for cfn in af_node.findall("custom-form"):
            raw_txt = (cfn.text or "").strip()
            if raw_txt:
                try:
                    obj = json.loads(raw_txt)
                    if isinstance(obj, dict):
                        state.custom_animal_forms.append(obj)
                except Exception:
                    pass

    comp_node = build.find("companions")
    if comp_node is not None:
        import json

        for cn in comp_node.findall("companion"):
            raw_txt = (cn.text or "").strip()
            if raw_txt:
                try:
                    obj = json.loads(raw_txt)
                    if isinstance(obj, dict):
                        state.companions.append(obj)
                except Exception:
                    pass

    mp_node = build.find("manual-proficiencies")
    if mp_node is not None:
        state.manual_save_profs = [
            (n.text or "").strip() for n in mp_node.findall("save") if (n.text or "").strip()
        ]
        state.manual_skill_profs = [
            (n.text or "").strip() for n in mp_node.findall("skill") if (n.text or "").strip()
        ]
        state.manual_skill_expertise = [
            (n.text or "").strip() for n in mp_node.findall("expertise") if (n.text or "").strip()
        ]
        state.manual_proficiencies = [
            (n.text or "").strip() for n in mp_node.findall("proficiency") if (n.text or "").strip()
        ]

    bp_node = build.find("build-plan")
    if bp_node is not None:
        import json

        for en in bp_node.findall("entry"):
            lvl_s = (en.get("level") or "1").strip()
            lvl_i = int(lvl_s) if lvl_s.isdigit() else 1
            spells_raw = en.get("spells") or "[]"
            try:
                spells_list = json.loads(spells_raw)
                if not isinstance(spells_list, list):
                    spells_list = []
            except Exception:
                spells_list = []
            state.build_plan.append(
                {
                    "level": lvl_i,
                    "class_id": (en.get("class-id") or "").strip(),
                    "subclass_id": (en.get("subclass-id") or "").strip(),
                    "asi_or_feat": (en.get("asi-or-feat") or "").strip(),
                    "spells": [str(s) for s in spells_list if s],
                    "notes": (en.text or "").strip(),
                }
            )

    return state
