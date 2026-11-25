"""Level-up progression helpers and Before/After character diff computation."""

from __future__ import annotations

import copy
import html
from dataclasses import dataclass, field
from typing import Optional

from .engine import class_display_summary, parse_hit_die
from .loader import ContentRepository
from .models import ABILITIES, ABILITY_ABBR, CharacterState, ClassLevel, ComputedCharacter, Element

_STANDARD_ASI_LEVELS = {4, 8, 12, 16, 19}
_FIGHTER_ASI_LEVELS = {4, 6, 8, 12, 14, 16, 19}
_ROGUE_ASI_LEVELS = {4, 8, 10, 12, 16, 19}


@dataclass
class StatDelta:
    label: str
    before: str
    after: str
    delta: str = ""


@dataclass
class CharacterDiff:
    level_before: int
    level_after: int
    classes_before: str
    classes_after: str
    target_class_name: str
    target_class_new_level: int
    is_new_multiclass: bool
    hp_before: int
    hp_after: int
    hp_delta: int
    hp_detail: str
    hit_dice_before: str
    hit_dice_after: str
    stat_deltas: list[StatDelta] = field(default_factory=list)
    new_features: list[Element] = field(default_factory=list)
    new_feats: list[Element] = field(default_factory=list)
    new_proficiencies: list[str] = field(default_factory=list)
    new_languages: list[str] = field(default_factory=list)
    slot_deltas: list[tuple[int, int, int]] = field(default_factory=list)
    pact_slot_deltas: list[tuple[int, int, int]] = field(default_factory=list)
    new_spells: list[tuple[str, str]] = field(default_factory=list)
    asi_summary: list[str] = field(default_factory=list)


def is_asi_level(class_el: Optional[Element], class_level: int) -> bool:
    """Return True if class_el grants an Ability Score Improvement at class_level."""
    if class_el is not None:
        for sel in class_el.select_rules:
            if sel.level == class_level and (
                sel.type == "Ability Score Improvement"
                or "ability score improvement" in sel.name.lower()
            ):
                return True
        for gr in class_el.grant_rules:
            if gr.level == class_level and "ability_score_improvement" in gr.id.lower():
                return True
        cname = class_el.name.lower()
        if "fighter" in cname:
            return class_level in _FIGHTER_ASI_LEVELS
        if "rogue" in cname:
            return class_level in _ROGUE_ASI_LEVELS
    return class_level in _STANDARD_ASI_LEVELS


def apply_level_up_step(
    state: CharacterState,
    class_id: str,
    hp_mode: Optional[str] = None,
    hp_roll: Optional[int] = None,
) -> CharacterState:
    """Return a deep-copied CharacterState advanced by 1 level in class_id."""
    new_state = copy.deepcopy(state)
    norm = new_state.normalized_classes()
    total_before = sum(c.level for c in norm) if norm else 0
    if total_before >= 20:
        raise ValueError("Character is already at maximum level 20.")

    updated = False
    for cl in norm:
        if cl.class_id == class_id:
            cl.level += 1
            updated = True
            break
    if not updated:
        norm.append(ClassLevel(class_id=class_id, level=1))

    new_state.classes = norm
    if not new_state.level_order:
        new_state.level_order = state.normalized_level_order()
    new_state.level_order.append(class_id)
    new_state.sync_from_classes()

    if hp_mode in ("average", "rolled"):
        new_state.hp_mode = hp_mode
    if hp_roll is not None:
        new_state.hp_rolls[new_state.level] = int(hp_roll)
    return new_state


def _fmt_signed(val: int) -> str:
    return f"+{val}" if val >= 0 else str(val)


def compute_character_diff(
    before_state: CharacterState,
    before_comp: ComputedCharacter,
    after_state: CharacterState,
    after_comp: ComputedCharacter,
    repo: ContentRepository,
    target_class_id: str = "",
) -> CharacterDiff:
    """Compute a structured Before -> After diff between two character snapshots."""
    before_classes = {c.class_id: c.level for c in before_state.normalized_classes()}
    after_classes = {c.class_id: c.level for c in after_state.normalized_classes()}

    if not target_class_id:
        for cid, lvl in after_classes.items():
            if lvl > before_classes.get(cid, 0):
                target_class_id = cid
                break
        if not target_class_id and after_state.class_id:
            target_class_id = after_state.class_id

    target_el = repo.get(target_class_id) if target_class_id else None
    target_name = target_el.name if target_el else (target_class_id or "Class")
    target_new_lvl = after_classes.get(target_class_id, after_state.level)
    is_new_mc = target_class_id not in before_classes and bool(before_classes)

    hp_delta = after_comp.max_hp - before_comp.max_hp
    hd_num = parse_hit_die(target_el)
    last_row = after_comp.hp_breakdown[-1] if after_comp.hp_breakdown else None
    if last_row:
        hp_detail = (
            f"d{hd_num} ({last_row['source']}: {last_row['roll']}) + CON ({_fmt_signed(last_row['con_mod'])})"
        )
    else:
        hp_detail = f"{_fmt_signed(hp_delta)} HP"

    stat_deltas: list[StatDelta] = []
    if after_comp.proficiency_bonus != before_comp.proficiency_bonus:
        stat_deltas.append(
            StatDelta(
                "Proficiency Bonus",
                f"+{before_comp.proficiency_bonus}",
                f"+{after_comp.proficiency_bonus}",
                f"+{after_comp.proficiency_bonus - before_comp.proficiency_bonus}",
            )
        )
    if after_comp.armor_class != before_comp.armor_class:
        stat_deltas.append(
            StatDelta(
                "Armor Class",
                str(before_comp.armor_class),
                str(after_comp.armor_class),
                _fmt_signed(after_comp.armor_class - before_comp.armor_class),
            )
        )
    if after_comp.initiative != before_comp.initiative:
        stat_deltas.append(
            StatDelta(
                "Initiative",
                _fmt_signed(before_comp.initiative),
                _fmt_signed(after_comp.initiative),
                _fmt_signed(after_comp.initiative - before_comp.initiative),
            )
        )
    if after_comp.speed != before_comp.speed:
        stat_deltas.append(
            StatDelta(
                "Speed",
                f"{before_comp.speed} ft",
                f"{after_comp.speed} ft",
                f"{_fmt_signed(after_comp.speed - before_comp.speed)} ft",
            )
        )
    if after_comp.passive_perception != before_comp.passive_perception:
        stat_deltas.append(
            StatDelta(
                "Passive Perception",
                str(before_comp.passive_perception),
                str(after_comp.passive_perception),
                _fmt_signed(after_comp.passive_perception - before_comp.passive_perception),
            )
        )
    for ab in ABILITIES:
        b_tot = before_comp.ability_totals[ab]
        a_tot = after_comp.ability_totals[ab]
        if a_tot != b_tot:
            stat_deltas.append(
                StatDelta(
                    ABILITY_ABBR[ab],
                    f"{b_tot} ({_fmt_signed(before_comp.ability_modifiers[ab])})",
                    f"{a_tot} ({_fmt_signed(after_comp.ability_modifiers[ab])})",
                    _fmt_signed(a_tot - b_tot),
                )
            )

    before_ids = {el.id for el in before_comp.granted_elements}
    new_features = [
        el
        for el in after_comp.granted_elements
        if el.id not in before_ids
        and el.type in ("Class Feature", "Archetype", "Archetype Feature", "Racial Trait", "Background Feature")
    ]
    new_feats = [
        el for el in after_comp.granted_elements if el.id not in before_ids and el.type == "Feat"
    ]

    new_profs = sorted(set(after_comp.proficiencies) - set(before_comp.proficiencies))
    new_langs = sorted(set(after_comp.languages) - set(before_comp.languages))

    b_slots = before_comp.spellcasting.slots if before_comp.spellcasting else {}
    a_slots = after_comp.spellcasting.slots if after_comp.spellcasting else {}
    slot_deltas: list[tuple[int, int, int]] = []
    for slvl in sorted(set(b_slots.keys()) | set(a_slots.keys())):
        bc = b_slots.get(slvl, 0)
        ac = a_slots.get(slvl, 0)
        if ac != bc:
            slot_deltas.append((slvl, bc, ac))

    b_pact = before_comp.spellcasting.pact_slots if before_comp.spellcasting else {}
    a_pact = after_comp.spellcasting.pact_slots if after_comp.spellcasting else {}
    pact_slot_deltas: list[tuple[int, int, int]] = []
    for slvl in sorted(set(b_pact.keys()) | set(a_pact.keys())):
        bc = b_pact.get(slvl, 0)
        ac = a_pact.get(slvl, 0)
        if ac != bc:
            pact_slot_deltas.append((slvl, bc, ac))

    b_granted_sp = set(before_comp.spellcasting.granted_spell_ids if before_comp.spellcasting else [])
    a_granted_sp = set(after_comp.spellcasting.granted_spell_ids if after_comp.spellcasting else [])
    b_spells = set(before_state.known_spells) | b_granted_sp
    a_spells_ordered = list(dict.fromkeys([*(after_comp.spellcasting.granted_spell_ids if after_comp.spellcasting else []), *after_state.known_spells]))
    always_prep_set = set(after_comp.spellcasting.always_prepared_spell_ids if after_comp.spellcasting else [])
    new_spells: list[tuple[str, str]] = []
    for sid in a_spells_ordered:
        if sid not in b_spells:
            sel = repo.get(sid)
            sname = sel.name if sel else sid
            src_cid = after_state.spell_sources.get(sid, "")
            src_el = repo.get(src_cid) if src_cid else None
            if sid in always_prep_set:
                src_lbl = "Subclass (Always Prepared)"
            elif src_el is not None:
                src_lbl = src_el.name
            elif sid in a_granted_sp:
                src_lbl = "Class / Feature"
            else:
                src_lbl = "Known / Learned"
            new_spells.append((sname, src_lbl))

    asi_summary: list[str] = []
    asi_key = f"{target_class_id}::{target_new_lvl}" if target_class_id else ""
    if asi_key and asi_key in after_state.level_up_asi:
        for ab, val in after_state.level_up_asi[asi_key].items():
            if val:
                asi_summary.append(f"{ABILITY_ABBR.get(ab, ab.upper())} +{val}")
    if asi_key and asi_key in after_state.level_up_feats:
        fid = after_state.level_up_feats[asi_key]
        fel = repo.get(fid)
        asi_summary.append(f"Feat: {fel.name if fel else fid}")

    return CharacterDiff(
        level_before=before_state.level,
        level_after=after_state.level,
        classes_before=class_display_summary(before_state, repo) or "No Class",
        classes_after=class_display_summary(after_state, repo) or "No Class",
        target_class_name=target_name,
        target_class_new_level=target_new_lvl,
        is_new_multiclass=is_new_mc,
        hp_before=before_comp.max_hp,
        hp_after=after_comp.max_hp,
        hp_delta=hp_delta,
        hp_detail=hp_detail,
        hit_dice_before=before_comp.hit_dice_summary or f"{before_state.level}{before_comp.hit_die}",
        hit_dice_after=after_comp.hit_dice_summary or f"{after_state.level}{after_comp.hit_die}",
        stat_deltas=stat_deltas,
        new_features=new_features,
        new_feats=new_feats,
        new_proficiencies=new_profs,
        new_languages=new_langs,
        slot_deltas=slot_deltas,
        pact_slot_deltas=pact_slot_deltas,
        new_spells=new_spells,
        asi_summary=asi_summary,
    )


def render_diff_html(diff: CharacterDiff) -> str:
    """Render a CharacterDiff as clean HTML for the Level-Up Wizard summary view."""
    badge = (
        f"Multiclass unlocked: {html.escape(diff.target_class_name)} 1"
        if diff.is_new_multiclass
        else f"{html.escape(diff.target_class_name)} → Level {diff.target_class_new_level}"
    )
    parts: list[str] = [
        f"<h2 style='margin-bottom:4px;'>Level {diff.level_before} → Level {diff.level_after}</h2>",
        f"<p style='color:#34d399; font-weight:bold;'>{badge}</p>",
        "<table cellpadding='6' cellspacing='0' width='100%' style='border-collapse:collapse;'>",
        "<tr style='background-color:rgba(128,128,128,0.14);'>"
        "<th align='left'>Attribute</th><th align='left'>Before</th><th align='left'>After</th><th align='left'>Change</th></tr>",
        f"<tr><td><b>Classes</b></td><td>{html.escape(diff.classes_before)}</td>"
        f"<td><b>{html.escape(diff.classes_after)}</b></td><td style='color:#34d399;'>+1 Level</td></tr>",
        f"<tr><td><b>Max HP</b></td><td>{diff.hp_before}</td><td><b>{diff.hp_after}</b></td>"
        f"<td style='color:#34d399;'>{_fmt_signed(diff.hp_delta)} ({html.escape(diff.hp_detail)})</td></tr>",
        f"<tr><td><b>Hit Dice</b></td><td>{html.escape(diff.hit_dice_before)}</td>"
        f"<td><b>{html.escape(diff.hit_dice_after)}</b></td><td>—</td></tr>",
    ]
    for sd in diff.stat_deltas:
        parts.append(
            f"<tr><td><b>{html.escape(sd.label)}</b></td><td>{html.escape(sd.before)}</td>"
            f"<td><b>{html.escape(sd.after)}</b></td><td style='color:#34d399;'>{html.escape(sd.delta)}</td></tr>"
        )
    parts.append("</table>")

    if diff.asi_summary:
        parts.append("<h3>ASI / Feat</h3><ul>")
        for item in diff.asi_summary:
            parts.append(f"<li><b>{html.escape(item)}</b></li>")
        parts.append("</ul>")

    if diff.new_features or diff.new_feats:
        parts.append("<h3>New Features &amp; Feats</h3><ul>")
        for el in [*diff.new_features, *diff.new_feats]:
            parts.append(f"<li><b>{html.escape(el.name)}</b> <span style='color:#94a3b8;'>({html.escape(el.type)})</span></li>")
        parts.append("</ul>")

    if diff.new_proficiencies or diff.new_languages:
        parts.append("<h3>New Proficiencies &amp; Languages</h3><ul>")
        for p in diff.new_proficiencies:
            parts.append(f"<li>Proficiency: {html.escape(p)}</li>")
        for l in diff.new_languages:
            parts.append(f"<li>Language: {html.escape(l)}</li>")
        parts.append("</ul>")

    if diff.slot_deltas or diff.pact_slot_deltas:
        parts.append("<h3>Spell Slot Changes</h3><ul>")
        for slvl, bc, ac in diff.slot_deltas:
            parts.append(
                f"<li>Level {slvl} Slots: {bc} → <b>{ac}</b> "
                f"<span style='color:#34d399;'>({_fmt_signed(ac - bc)})</span></li>"
            )
        for slvl, bc, ac in diff.pact_slot_deltas:
            parts.append(
                f"<li>Pact Magic (Level {slvl}): {bc} → <b>{ac}</b> "
                f"<span style='color:#34d399;'>({_fmt_signed(ac - bc)})</span></li>"
            )
        parts.append("</ul>")

    if diff.new_spells:
        parts.append("<h3>New Spells</h3><ul>")
        for sname, src in diff.new_spells:
            parts.append(f"<li><b>{html.escape(sname)}</b> <span style='color:#94a3b8;'>({html.escape(src)})</span></li>")
        parts.append("</ul>")

    return "".join(parts)
