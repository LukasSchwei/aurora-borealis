"""Unified SVG icon loader and theme-aware tinting for Aurora Borealis."""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton, QWidget

ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


def _resolve_icon_path(name: str) -> Path:
    cand = ICONS_DIR / f"{name}.svg"
    if cand.is_file():
        return cand
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        mp = Path(meipass) / "aurora_borealis" / "assets" / "icons" / f"{name}.svg"
        if mp.is_file():
            return mp
    return cand


@functools.lru_cache(maxsize=64)
def _read_svg_template(name: str) -> str:
    path = _resolve_icon_path(name)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=256)
def svg_pixmap(name: str, color: str = "#eef0f3", size: int = 18) -> QPixmap:
    """Render an SVG asset tinted to `color` into an exact `(size, size)` QPixmap."""
    px = max(1, int(size))
    pix = QPixmap(px, px)
    pix.fill(Qt.GlobalColor.transparent)
    tmpl = _read_svg_template(name)
    if not tmpl:
        return pix
    svg_xml = tmpl.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg_xml.encode("utf-8")))
    if not renderer.isValid():
        return pix
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0.0, 0.0, float(px), float(px)))
    painter.end()
    return pix


@functools.lru_cache(maxsize=256)
def svg_icon(name: str, color: str = "#eef0f3", size: int = 18) -> QIcon:
    """Render a crisp multi-DPI QIcon (1x and 2x) from an SVG asset."""
    px = max(1, int(size))
    icon = QIcon()
    pix1 = svg_pixmap(name, color, px)
    icon.addPixmap(pix1)
    pix2 = svg_pixmap(name, color, px * 2)
    pix2.setDevicePixelRatio(2.0)
    icon.addPixmap(pix2)
    return icon


def theme_icon_color(theme: str, role: str = "default") -> str:
    """Return the foreground hex color for SVG icons matching the active theme & role."""
    is_light = str(theme).lower() == "light"
    if role == "primary":
        return "#ffffff" if is_light else "#111214"
    if role == "danger":
        return "#b91c1c" if is_light else "#fca5a5"
    if role == "muted":
        return "#5f6368" if is_light else "#9aa0a6"
    if role == "accent":
        return "#0f766e" if is_light else "#34d399"
    return "#1f1f1f" if is_light else "#eef0f3"


def _button_role(btn: QPushButton) -> str:
    obj = btn.objectName()
    if obj == "PrimaryBtn":
        return "primary"
    if obj in ("DangerBtn", "TrashBtn"):
        return "danger"
    return "default"


def apply_button_icon(
    btn: QPushButton,
    name: str,
    *,
    theme: str = "dark",
    size: int = 16,
    fixed_color: Optional[str] = None,
) -> None:
    """Attach a themed SVG icon to a QPushButton and track metadata for live theme updates."""
    btn.setProperty("_aurora_icon_name", name)
    btn.setProperty("_aurora_icon_size", int(size))
    btn.setProperty("_aurora_icon_color", fixed_color or "")
    color = fixed_color if fixed_color else theme_icon_color(theme, _button_role(btn))
    btn.setIcon(svg_icon(name, color, int(size)))
    btn.setIconSize(QSize(int(size), int(size)))


def refresh_themed_icons(root: QWidget, theme: str = "dark") -> None:
    """Re-tint all SVG icons on QPushButtons inside `root` for the given theme."""
    buttons: list[QPushButton] = []
    if isinstance(root, QPushButton):
        buttons.append(root)
    buttons.extend(root.findChildren(QPushButton))
    for btn in buttons:
        name = btn.property("_aurora_icon_name")
        if not name:
            continue
        size = int(btn.property("_aurora_icon_size") or 16)
        fixed_color = str(btn.property("_aurora_icon_color") or "")
        color = fixed_color if fixed_color else theme_icon_color(theme, _button_role(btn))
        btn.setIcon(svg_icon(str(name), color, size))
        btn.setIconSize(QSize(size, size))
