"""Icon, rarity badge, and formatting helpers for equipment & spell tables."""

from __future__ import annotations

import functools
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ...models import Element
from ...persistence import default_character_extension
from ..icons import svg_pixmap


def _fmt_mod(val: int) -> str:
    return f"+{val}" if val >= 0 else str(val)


def _safe_filename(name: str, ruleset: str = "5e") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "character").strip().lower()).strip("_")
    ext = default_character_extension(ruleset)
    return f"{cleaned or 'character'}{ext}"


_RARITY_TABLE: dict[str, tuple[int, str, str, str, str]] = {
    "common": (1, "C", "Common", "#cbd5e1", "#1e293b"),
    "uncommon": (2, "U", "Uncommon", "#4ade80", "#052e16"),
    "rare": (3, "R", "Rare", "#60a5fa", "#0c2d48"),
    "very rare": (4, "V", "Very Rare", "#c084fc", "#2e1065"),
    "legendary": (5, "L", "Legendary", "#fbbf24", "#451a03"),
    "artifact": (6, "A", "Artifact", "#f87171", "#450a0a"),
}


def _item_rarity_info(el: Element) -> tuple[int, str, str, str, str]:
    """Return (rank, letter, label, fg_hex, bg_hex) for an equipment/magic item."""
    raw = (el.setters.get("rarity") or "").strip().lower()
    if raw in _RARITY_TABLE:
        return _RARITY_TABLE[raw]
    for key, info in _RARITY_TABLE.items():
        if key in raw:
            return info
    return _RARITY_TABLE["common"]


def _item_cost_gp(el: Element) -> float:
    raw = (el.setters.get("cost") or "").strip()
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw.replace(",", ""))
    if not m:
        return 0.0
    val = float(m.group(1))
    cur = (el.setters.get("currency") or "gp").strip().lower()
    mult = {"cp": 0.01, "sp": 0.1, "ep": 0.5, "gp": 1.0, "pp": 10.0}.get(cur, 1.0)
    return val * mult


def _make_magic_sparkles_pixmap(color_hex: str, size: int = 14) -> QPixmap:
    """Render crisp 4-pointed sparkle stars from the sparkles SVG asset."""
    return svg_pixmap("sparkles", color_hex, size)


@functools.lru_cache(maxsize=64)
def _spell_level_icon(lvl: str) -> QIcon:
    lvl_colors = {
        "0": ("#94a3b8", "#1e293b"),
        "1": ("#38bdf8", "#0c2d48"),
        "2": ("#34d399", "#064e3b"),
        "3": ("#fb923c", "#3b1d0a"),
        "4": ("#f472b6", "#500724"),
        "5": ("#c084fc", "#2e1065"),
        "6": ("#facc15", "#422006"),
        "7": ("#f87171", "#450a0a"),
        "8": ("#2dd4bf", "#042f2e"),
        "9": ("#fbbf24", "#451a03"),
    }
    fg, bg = lvl_colors.get(str(lvl), ("#7dd3fc", "#1e3a5f"))
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(QColor(bg))
    p.setPen(QPen(QColor(fg), 1.5))
    p.drawEllipse(2, 2, 20, 20)
    f = QFont("Sans Serif", 9)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(fg))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, str(lvl))
    p.end()
    return QIcon(pix)


@functools.lru_cache(maxsize=32)
def _spell_school_icon(school: str) -> QIcon:
    school_colors = {
        "abjuration": ("#60a5fa", "#0c2d48", "Ab"),
        "conjuration": ("#fbbf24", "#451a03", "Cj"),
        "divination": ("#38bdf8", "#082f49", "Dv"),
        "enchantment": ("#f472b6", "#500724", "En"),
        "evocation": ("#f87171", "#450a0a", "Ev"),
        "illusion": ("#c084fc", "#2e1065", "Il"),
        "necromancy": ("#4ade80", "#052e16", "Nc"),
        "transmutation": ("#fb923c", "#431407", "Tr"),
    }
    fg, bg, abbr = school_colors.get((school or "").strip().lower(), ("#94a3b8", "#1e293b", "—"))
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(QColor(bg))
    p.setPen(QPen(QColor(fg), 1.4))
    p.drawRoundedRect(2, 2, 20, 20, 5, 5)
    f = QFont("Sans Serif", 8)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(fg))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, abbr)
    p.end()
    return QIcon(pix)


@functools.lru_cache(maxsize=8)
def _spell_tags_icon(is_ritual: bool, is_conc: bool) -> QIcon:
    if not is_ritual and not is_conc:
        return QIcon()
    w = 46 if (is_ritual and is_conc) else 24
    pix = QPixmap(w, 24)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    f = QFont("Sans Serif", 8)
    f.setBold(True)
    p.setFont(f)
    x = 2
    if is_ritual:
        p.setBrush(QColor("#083344"))
        p.setPen(QPen(QColor("#22d3ee"), 1.4))
        p.drawEllipse(x, 2, 20, 20)
        p.setPen(QColor("#22d3ee"))
        p.drawText(x, 2, 20, 20, Qt.AlignmentFlag.AlignCenter, "R")
        x += 22
    if is_conc:
        p.setBrush(QColor("#451a03"))
        p.setPen(QPen(QColor("#fbbf24"), 1.4))
        cx, cy = x + 10.0, 12.0
        diamond = QPainterPath()
        diamond.moveTo(cx, 2.0)
        diamond.lineTo(cx + 10.0, cy)
        diamond.lineTo(cx, 22.0)
        diamond.lineTo(cx - 10.0, cy)
        diamond.closeSubpath()
        p.drawPath(diamond)
        p.setPen(QColor("#fbbf24"))
        p.drawText(x, 2, 20, 20, Qt.AlignmentFlag.AlignCenter, "C")
    p.end()
    return QIcon(pix)


@functools.lru_cache(maxsize=16)
def _equip_type_icon(el_type: str) -> QIcon:
    pix = QPixmap(28, 28)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    icon_map = {
        "Magic Item": ("sparkles", "#f472b6", "#331829", "#f472b6"),
        "Weapon": ("sword", "#e2e8f0", "#292524", "#a8a29e"),
        "Armor": ("shield", "#67e8f9", "#162c36", "#22d3ee"),
        "Item": ("backpack", "#9ca3af", "#1f2937", "#6b7280"),
    }
    icon_name, fg, bg, border = icon_map.get(el_type, ("backpack", "#9ca3af", "#1f2937", "#6b7280"))
    p.setBrush(QColor(bg))
    p.setPen(QPen(QColor(border), 1.6))
    p.drawEllipse(1, 1, 26, 26)
    p.drawPixmap(6, 6, svg_pixmap(icon_name, fg, 16))
    p.end()
    return QIcon(pix)


@functools.lru_cache(maxsize=16)
def _equip_rarity_icon(r_letter: str, r_fg: str, r_bg: str) -> QIcon:
    pix = QPixmap(28, 28)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(QColor(r_bg))
    p.setPen(QPen(QColor(r_fg), 1.6))
    p.drawEllipse(1, 1, 26, 26)
    p.setPen(QColor(r_fg))
    f = QFont("Sans Serif", 11)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, r_letter)
    p.end()
    return QIcon(pix)
