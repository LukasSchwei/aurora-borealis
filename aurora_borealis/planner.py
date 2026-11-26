"""Level 1-20 Build Planner."""

from __future__ import annotations

from .engine import FULL_CASTER_SLOTS
from .level_up import is_asi_level
from .loader import ContentRepository
from .models import CharacterState


def generate_default_plan(state: CharacterState, repo: ContentRepository) -> list[dict]:
    """Generate a 20-level progression plan seeded from current class levels & selections."""
    existing_by_lvl = {
        int(e.get("level", 0)): dict(e)
        for e in (state.build_plan or [])
        if isinstance(e, dict) and str(e.get("level", "")).isdigit()
    }
    order = state.normalized_level_order()
    primary_cid = order[0] if order else state.class_id

    subclass_by_class: dict[str, str] = {}
    for active_sel_key, chosen in state.selections.items():
        if "::Archetype::" in active_sel_key and chosen and chosen[0]:
            src_cid = active_sel_key.split("::", 1)[0]
            subclass_by_class[src_cid] = chosen[0]

    plan: list[dict] = []
    class_counts: dict[str, int] = {}
    for lvl in range(1, 21):
        prev = existing_by_lvl.get(lvl)
        cid = (prev.get("class_id") if prev else "") or (
            order[lvl - 1] if lvl - 1 < len(order) else primary_cid
        )
        if cid:
            class_counts[cid] = class_counts.get(cid, 0) + 1
        cls_lvl = class_counts.get(cid, lvl) if cid else lvl
        cel = repo.get(cid) if cid else None

        asi_text = (prev.get("asi_or_feat") if prev else "") or ""
        if not asi_text and cid:
            lu_key = f"{cid}::{cls_lvl}"
            if lu_key in state.level_up_feats:
                fel = repo.get(state.level_up_feats[lu_key])
                asi_text = f"Feat: {fel.name if fel else state.level_up_feats[lu_key]}"
            elif lu_key in state.level_up_asi:
                asi_text = ", ".join(
                    f"{k[:3].upper()} +{v}" for k, v in state.level_up_asi[lu_key].items() if v
                )
            elif cel and is_asi_level(cel, cls_lvl):
                asi_text = "ASI / Feat"

        sub_id = (prev.get("subclass_id") if prev else "") or subclass_by_class.get(cid, "")
        spells = list(prev.get("spells") or []) if prev else []
        notes = str(prev.get("notes") or "") if prev else ""
        plan.append(
            {
                "level": lvl,
                "class_id": cid,
                "subclass_id": sub_id,
                "asi_or_feat": asi_text,
                "spells": spells,
                "notes": notes,
            }
        )
    return plan


def summarize_build_plan(plan: list[dict], repo: ContentRepository) -> dict:
    """Summarize class split, ASI/Feat milestones, and projected Lv 20 spell slots."""
    class_levels: dict[str, int] = {}
    asi_levels: list[tuple[int, str]] = []
    warnings: list[str] = []

    sorted_plan = sorted(
        [p for p in plan if isinstance(p, dict)],
        key=lambda p: int(p.get("level", 0)),
    )
    if len(sorted_plan) > 20:
        warnings.append(f"Plan has {len(sorted_plan)} levels (max 20).")

    for entry in sorted_plan:
        lvl = int(entry.get("level", 0))
        cid = str(entry.get("class_id") or "").strip()
        if cid:
            class_levels[cid] = class_levels.get(cid, 0) + 1
        elif lvl <= 20:
            warnings.append(f"Level {lvl}: no class assigned.")
        asi = str(entry.get("asi_or_feat") or "").strip()
        if asi:
            asi_levels.append((lvl, asi))

    split_parts: list[str] = []
    mc_caster_lvl = 0
    pact_lvl = 0
    for cid, cnt in class_levels.items():
        cel = repo.get(cid)
        cname = cel.name if cel else cid
        split_parts.append(f"{cname} {cnt}")
        cl_low = cname.lower()
        if "warlock" in cl_low:
            pact_lvl += cnt
        elif any(k in cl_low for k in ("bard", "cleric", "druid", "sorcerer", "wizard")):
            mc_caster_lvl += cnt
        elif any(k in cl_low for k in ("paladin", "ranger", "artificer")):
            mc_caster_lvl += cnt // 2

    mc_caster_lvl = min(20, mc_caster_lvl)
    slots = dict(FULL_CASTER_SLOTS.get(mc_caster_lvl, {})) if mc_caster_lvl > 0 else {}

    return {
        "class_split": " / ".join(split_parts) if split_parts else "No Classes Planned",
        "class_levels": class_levels,
        "asi_levels": asi_levels,
        "caster_level": mc_caster_lvl,
        "pact_level": pact_lvl,
        "projected_slots": slots,
        "warnings": warnings,
    }
