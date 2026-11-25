"""Save and load Aurora .dnd5e character XML files."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from lxml import etree

from .engine import RulesEngine, class_display_summary
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


def save_dnd5e(
    state: CharacterState,
    repo: ContentRepository,
    computed: ComputedCharacter,
    path: Path,
) -> None:
    path = Path(path)
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

    # Equipment
    equip_node = etree.SubElement(build, "equipment")
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

    xml_bytes = etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(xml_bytes)


def load_dnd5e(path: Path, repo: ContentRepository) -> CharacterState:
    path = Path(path)
    parser = etree.XMLParser(recover=True, remove_comments=True)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    if root is None:
        raise ValueError(f"Invalid .dnd5e file: {path}")

    state = CharacterState()
    build = root.find("build")
    disp = root.find("display-properties")

    if disp is not None:
        state.name = (disp.findtext("name") or state.name).strip()
        lvl_txt = (disp.findtext("level") or "").strip()
        if lvl_txt.isdigit():
            state.level = max(1, min(20, int(lvl_txt)))
        xp_disp = (disp.findtext("experience") or "").strip()
        if xp_disp.isdigit():
            state.xp = int(xp_disp)
        rs = (disp.findtext("ruleset") or "").strip()
        if rs in ("5e", "5.5e"):
            state.ruleset = rs
        state.portrait_path = (disp.findtext("portrait") or "").strip()
        state.portrait_base64 = (disp.findtext("portrait-data") or "").strip()

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
        if not state.portrait_path:
            state.portrait_path = (inp.findtext("portrait") or "").strip()
        if not state.portrait_base64:
            state.portrait_base64 = (inp.findtext("portrait-data") or "").strip()

        app = inp.find("appearance")
        if app is not None:
            if not state.gender:
                state.gender = (app.findtext("gender") or "").strip()
            state.age = (app.findtext("age") or "").strip()
            state.height = (app.findtext("height") or "").strip()
            state.weight = (app.findtext("weight") or "").strip()
            state.eyes = (app.findtext("eyes") or "").strip()
            state.skin = (app.findtext("skin") or "").strip()
            state.hair = (app.findtext("hair") or "").strip()

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
    parsed_classes: list[tuple[bool, ClassLevel]] = []
    has_explicit_class_levels = False
    elems_node = build.find("elements")
    if elems_node is not None:
        max_lvl = 0
        for el in elems_node.findall(".//element"):
            etype = (el.get("type") or "").strip()
            eid = (el.get("id") or "").strip()
            reg = (el.get("registered") or "").strip()
            if reg and reg.lower() not in ("true", "false") and reg not in legacy_element_ids:
                legacy_element_ids.append(reg)
            if eid and eid not in legacy_element_ids:
                legacy_element_ids.append(eid)
            if not eid:
                continue
            if etype == "Race" and not state.race_id:
                state.race_id = eid
            elif etype == "Class":
                if not state.class_id:
                    state.class_id = eid
                lvl_attr = (el.get("level") or "").strip()
                is_prim = (el.get("primary") or "").strip().lower() == "true"
                if lvl_attr.isdigit():
                    has_explicit_class_levels = True
                    parsed_classes.append((is_prim, ClassLevel(eid, max(1, min(20, int(lvl_attr))))))
                else:
                    parsed_classes.append((is_prim or len(parsed_classes) == 0, ClassLevel(eid, 1)))
            elif etype == "Background" and not state.background_id:
                state.background_id = eid
            elif etype == "Alignment" and not state.alignment_id:
                state.alignment_id = eid
            elif etype == "Deity" and not state.deity_id:
                state.deity_id = eid
            elif etype == "Level":
                name_txt = (el.get("name") or "").strip()
                if name_txt.isdigit():
                    max_lvl = max(max_lvl, int(name_txt))
        if max_lvl > 0:
            state.level = max(1, min(20, max_lvl))

    if parsed_classes:
        if has_explicit_class_levels or len(parsed_classes) > 1:
            ordered_mc = [cl for prim, cl in parsed_classes if prim] + [cl for prim, cl in parsed_classes if not prim]
            state.classes = ordered_mc
            state.sync_from_classes()
        elif state.class_id:
            state.classes = [ClassLevel(state.class_id, state.level)]
            state.sync_from_classes()

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

    sum_node = build.find("sum")
    if sum_node is not None:
        for el in sum_node.findall(".//element"):
            eid = (el.get("id") or "").strip()
            if eid and eid not in legacy_element_ids:
                legacy_element_ids.append(eid)

    sel_node = build.find("selections")
    if sel_node is not None:
        for s in sel_node.findall("selection"):
            key = (s.get("key") or "").strip()
            val = (s.get("value") or "").strip()
            if key and val:
                state.selections.setdefault(key, []).append(val)
    elif legacy_element_ids and repo.by_id:
        # Backward compatibility with original Aurora Builder .dnd5e files:
        # reconstruct user selections from nested <build><elements> / <sum> IDs.
        engine = RulesEngine(repo)
        consumed_ids: set[str] = set()
        for _ in range(6):
            comp = engine.evaluate(state)
            progressed = False
            for active_sel in comp.active_selections:
                existing = list(state.selections.get(active_sel.key, []))
                if len([v for v in existing if v]) >= active_sel.rule.number:
                    continue
                opt_ids = {oid for oid, _oname in active_sel.options}
                for cand in legacy_element_ids:
                    if len([v for v in existing if v]) >= active_sel.rule.number:
                        break
                    if cand in opt_ids and cand not in existing and cand not in consumed_ids:
                        existing.append(cand)
                        consumed_ids.add(cand)
                        progressed = True
                if existing:
                    state.selections[active_sel.key] = existing[: active_sel.rule.number]
            if not progressed:
                break

    equip_node = build.find("equipment")
    if equip_node is not None:
        for item in equip_node.findall(".//item"):
            eid = (item.get("identifier") or item.get("id") or "").strip()
            name = (item.get("name") or "").strip()
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
            cat = (item.get("category") or (el.type if el else "")).strip()
            try:
                m_bonus = int(item.get("magic-bonus") or "0")
            except ValueError:
                m_bonus = 0
            ench = (item.get("enchantment") or "").strip()
            attuned = (item.get("attuned") or "").lower() == "true"
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
                    )
                )

    magic_node = build.find("magic")
    if magic_node is not None:
        state.allow_extra_spells = (magic_node.get("allow-extra") or "false").lower() == "true"
        for sp in magic_node.findall(".//spell"):
            sid = (sp.get("id") or "").strip()
            if not sid:
                continue
            is_known = (sp.get("known") or "true").lower() == "true"
            is_prep = (
                (sp.get("prepared") or "false").lower() == "true"
                or (sp.get("always-prepared") or "false").lower() == "true"
            )
            if is_known and sid not in state.known_spells:
                state.known_spells.append(sid)
            if is_prep and sid not in state.prepared_spells:
                state.prepared_spells.append(sid)
            src_cls = (sp.get("source-class") or "").strip()
            if src_cls:
                state.spell_sources[sid] = src_cls

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

    return state
