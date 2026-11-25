"""Google-inspired neutral Dark & Light stylesheets with live UI scaling for Aurora Borealis."""

from __future__ import annotations

import functools
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

_DARK_TOKENS = {
    "bg": "#0e0f11",
    "titlebar": "#131417",
    "surface": "#18191d",
    "card": "#1d1f24",
    "card_elev": "#24262c",
    "input": "#121316",
    "border": "#2c2f36",
    "border_subtle": "#23252b",
    "text": "#eef0f3",
    "text_muted": "#9aa0a6",
    "text_dim": "#70757c",
    "accent": "#34d399",
    "accent_soft": "#162a24",
    "accent_border": "#245446",
    "pill_active_bg": "#eef0f3",
    "pill_active_fg": "#111214",
    "pill_active_hover": "#ffffff",
    "btn_bg": "#24262c",
    "btn_hover": "#2e3139",
    "btn_pressed": "#1b1d22",
    "danger_bg": "#2a1618",
    "danger_border": "#6b2228",
    "danger_fg": "#fca5a5",
    "danger_hover": "#3f1c20",
    "warn_border": "#b7791f",
    "warn_fg": "#f6ad55",
    "selection_bg": "#2d333b",
    "selection_fg": "#ffffff",
    "header_bg": "#18191d",
    "scroll_handle": "#343740",
    "scroll_handle_hover": "#484c58",
}

_LIGHT_TOKENS = {
    "bg": "#f4f5f7",
    "titlebar": "#ffffff",
    "surface": "#f8f9fa",
    "card": "#ffffff",
    "card_elev": "#f1f3f4",
    "input": "#f8f9fa",
    "border": "#dadce0",
    "border_subtle": "#e8eaed",
    "text": "#1f1f1f",
    "text_muted": "#5f6368",
    "text_dim": "#80868b",
    "accent": "#0f766e",
    "accent_soft": "#e6f4f1",
    "accent_border": "#99d5c9",
    "pill_active_bg": "#1f1f1f",
    "pill_active_fg": "#ffffff",
    "pill_active_hover": "#33363b",
    "btn_bg": "#f1f3f4",
    "btn_hover": "#e8eaed",
    "btn_pressed": "#dadce0",
    "danger_bg": "#fef2f2",
    "danger_border": "#fca5a5",
    "danger_fg": "#b91c1c",
    "danger_hover": "#fee2e2",
    "warn_border": "#d97706",
    "warn_fg": "#b45309",
    "selection_bg": "#e0f2fe",
    "selection_fg": "#111827",
    "header_bg": "#f1f3f4",
    "scroll_handle": "#cbd5e1",
    "scroll_handle_hover": "#94a3b8",
}


def _build_stylesheet(t: dict[str, str], scale: float = 1.0, is_light: bool = False) -> str:
    s = max(0.85, min(1.5, float(scale)))
    suffix = "dark" if is_light else "light"
    up_svg = (_ASSETS_DIR / f"chevron-up-{suffix}.svg").as_posix()
    down_svg = (_ASSETS_DIR / f"chevron-down-{suffix}.svg").as_posix()

    def pt(val: float) -> str:
        return f"{val * s:.1f}pt"

    def px(val: float) -> str:
        return f"{max(1, round(val * s))}px"

    return f"""
QMainWindow, QWidget, QDialog {{
    background-color: {t["surface"]};
    color: {t["text"]};
    font-family: "Inter", "Google Sans", "Noto Sans", "Segoe UI", sans-serif;
    font-size: {pt(11.0)};
}}
QMainWindow {{
    background-color: {t["bg"]};
}}
QLabel {{
    background-color: transparent;
}}
QMenuBar {{
    background-color: {t["titlebar"]};
    border: none;
}}
QMenu {{
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    border-radius: {px(10)};
    padding: {px(4)};
}}
QMenu::item {{
    padding: {px(7)} {px(16)};
    border-radius: {px(7)};
}}
QMenu::item:selected {{
    background-color: {t["btn_hover"]};
}}

/* Compact In-App Header Bar (OS provides native window buttons) */
QFrame#WindowTitleBar {{
    background-color: {t["titlebar"]};
    border-bottom: 1px solid {t["border_subtle"]};
}}
QLabel#WindowTitleText {{
    font-size: {pt(11.5)};
    font-weight: 700;
    color: {t["text"]};
    background: transparent;
}}
QLabel#WindowBreadcrumb {{
    font-size: {pt(9.8)};
    color: {t["text_muted"]};
    background: transparent;
}}
QPushButton#ThemeToggleBtn {{
    background-color: {t["btn_bg"]};
    border: 1px solid {t["border"]};
    border-radius: {px(16)};
    color: {t["text"]};
    min-width: {px(34)};
    max-width: {px(34)};
    min-height: {px(32)};
    max-height: {px(32)};
    padding: 0px;
    font-size: {pt(12.5)};
    font-weight: 700;
}}
QPushButton#ThemeToggleBtn:hover {{
    background-color: {t["btn_hover"]};
    border-color: {t["accent"]};
}}
QLabel#ScaleValuePill {{
    background-color: {t["card_elev"]};
    border: 1px solid {t["border"]};
    border-radius: {px(12)};
    color: {t["text"]};
    font-size: {pt(9.8)};
    font-weight: 700;
    padding: {px(3)} {px(10)};
    min-width: {px(50)};
}}
QPushButton#KdeWinBtn {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {px(14)};
    color: {t["text_muted"]};
    min-width: {px(28)};
    max-width: {px(28)};
    min-height: {px(28)};
    max-height: {px(28)};
    padding: 0px;
}}
QPushButton#KdeWinBtn:hover {{
    background-color: {t["btn_hover"]};
    color: {t["text"]};
}}
QPushButton#KdeCloseBtn {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {px(14)};
    color: {t["text_muted"]};
    min-width: {px(28)};
    max-width: {px(28)};
    min-height: {px(28)};
    max-height: {px(28)};
    padding: 0px;
}}
QPushButton#KdeCloseBtn:hover {{
    background-color: #da4453;
    color: #ffffff;
}}

/* Top Nav & Sub Nav Bars */
QFrame#TopNavBar {{
    background-color: {t["titlebar"]};
    border-bottom: 1px solid {t["border_subtle"]};
}}
QFrame#SubBar {{
    background-color: {t["titlebar"]};
    border-bottom: 1px solid {t["border_subtle"]};
}}

/* Cards & Panels */
QFrame#SidebarCard, QFrame#CharCard, QFrame#ChoiceCard {{
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    border-radius: {px(14)};
}}
QFrame#CharCard:hover {{
    border: 2px solid {t["accent"]};
}}
QFrame#ChoiceCardPending {{
    background-color: {t["card"]};
    border: 1.5px solid {t["warn_border"]};
    border-radius: {px(14)};
}}
QFrame#StatPillBox {{
    background-color: {t["card_elev"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: {px(9)};
}}
QPushButton#NewCharDashedCard {{
    background-color: {t["card"]};
    border: 2px dashed {t["border"]};
    border-radius: {px(14)};
    color: {t["text_muted"]};
    padding: {px(18)};
    font-size: {pt(11.5)};
}}
QPushButton#NewCharDashedCard:hover {{
    border-color: {t["accent"]};
    color: {t["text"]};
    background-color: {t["card_elev"]};
}}
QPushButton#CharPortraitBtn {{
    background-color: {t["card_elev"]};
    border: none;
    border-top-left-radius: {px(12)};
    border-top-right-radius: {px(12)};
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
    color: {t["accent"]};
    font-size: {pt(28.0)};
    font-weight: 800;
    padding: 0px;
}}
QPushButton#CharPortraitBtn:hover {{
    background-color: {t["btn_hover"]};
}}
QPushButton#OverviewCard {{
    text-align: left;
    padding: {px(16)};
    border-radius: {px(14)};
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    color: {t["text"]};
    font-size: {pt(10.8)};
    font-weight: 500;
}}
QPushButton#OverviewCard:hover {{
    border-color: {t["accent"]};
    background-color: {t["card_elev"]};
}}
QPushButton#RailPortraitBtn {{
    background-color: {t["card_elev"]};
    border: 1px solid {t["border"]};
    border-radius: {px(12)};
    color: {t["accent"]};
    font-weight: 700;
    padding: 0px;
}}
QPushButton#RailPortraitBtn:hover {{
    border-color: {t["accent"]};
}}

/* Group Boxes */
QGroupBox {{
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    border-radius: {px(14)};
    margin-top: {px(13)};
    padding-top: {px(15)};
    font-weight: 600;
    color: {t["text"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {px(12)};
    padding: 0 {px(6)};
    color: {t["text_muted"]};
}}

/* Inputs, Lists, Tables */
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTableWidget {{
    background-color: {t["input"]};
    border: 1px solid {t["border"]};
    border-radius: {px(9)};
    padding: {px(6)} {px(11)};
    color: {t["text"]};
    selection-background-color: {t["selection_bg"]};
    selection-color: {t["selection_fg"]};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {t["accent"]};
}}
QTableWidget {{
    padding: 0px;
    gridline-color: {t["border_subtle"]};
    alternate-background-color: {t["card_elev"]};
}}
QRadioButton, QCheckBox {{
    spacing: {px(8)};
    background-color: transparent;
}}
QRadioButton::indicator {{
    width: {px(16)};
    height: {px(16)};
    border-radius: {px(9)};
    border: 1.5px solid {t["text_dim"]};
    background-color: {t["input"]};
}}
QRadioButton::indicator:hover {{
    border-color: {t["accent"]};
}}
QRadioButton::indicator:checked {{
    border: 1.5px solid {t["accent"]};
    background-color: qradialgradient(
        cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
        stop: 0 {t["accent"]},
        stop: 0.44 {t["accent"]},
        stop: 0.48 {t["input"]},
        stop: 1 {t["input"]}
    );
}}
QCheckBox::indicator {{
    width: {px(15)};
    height: {px(15)};
    border-radius: {px(4)};
    border: 1.5px solid {t["text_dim"]};
    background-color: {t["input"]};
}}
QCheckBox::indicator:hover {{
    border-color: {t["accent"]};
}}
QCheckBox::indicator:checked {{
    background-color: {t["accent"]};
    border-color: {t["accent"]};
}}
QSpinBox[buttonSymbols="0"] {{
    padding: {px(4)} {px(22)} {px(4)} {px(8)};
    min-height: {px(26)};
}}
QSpinBox[buttonSymbols="0"]::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: {px(18)};
    border: none;
    border-left: 1px solid {t["border_subtle"]};
    border-top-right-radius: {px(8)};
    background-color: transparent;
}}
QSpinBox[buttonSymbols="0"]::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: {px(18)};
    border: none;
    border-left: 1px solid {t["border_subtle"]};
    border-bottom-right-radius: {px(8)};
    background-color: transparent;
}}
QSpinBox[buttonSymbols="0"]::up-button:hover, QSpinBox[buttonSymbols="0"]::down-button:hover {{
    background-color: {t["btn_hover"]};
}}
QSpinBox[buttonSymbols="0"]::up-arrow {{
    image: url("{up_svg}");
    width: {px(9)};
    height: {px(6)};
}}
QSpinBox[buttonSymbols="0"]::down-arrow {{
    image: url("{down_svg}");
    width: {px(9)};
    height: {px(6)};
}}
QSpinBox#StepperSpin {{
    padding: {px(2)} {px(4)};
    min-height: {px(26)};
}}
QSpinBox#StepperSpin::up-button, QSpinBox#StepperSpin::down-button {{
    subcontrol-origin: border;
    width: 0px;
    height: 0px;
    border: none;
}}
QSpinBox QLineEdit {{
    border: none;
    padding: 0px;
    background: transparent;
}}
QComboBox {{
    combobox-popup: 0;
    padding-right: {px(26)};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    border: none;
    width: {px(24)};
}}
QComboBox::down-arrow {{
    image: url("{down_svg}");
    width: {px(10)};
    height: {px(6)};
}}
QComboBox QAbstractItemView {{
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    border-radius: {px(8)};
    padding: {px(4)};
    outline: 0;
    selection-background-color: {t["btn_hover"]};
    selection-color: {t["text"]};
}}
QComboBox QAbstractItemView::item {{
    min-height: {px(24)};
    padding: {px(4)} {px(8)};
}}

/* Buttons (Chubby Google Material Pill style) */
QPushButton {{
    background-color: {t["btn_bg"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: {px(16)};
    padding: {px(7)} {px(15)};
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {t["btn_hover"]};
    border-color: {t["text_dim"]};
}}
QPushButton:pressed {{
    background-color: {t["btn_pressed"]};
}}
QPushButton#PrimaryBtn {{
    background-color: {t["pill_active_bg"]};
    border: 1px solid {t["pill_active_bg"]};
    color: {t["pill_active_fg"]};
}}
QPushButton#PrimaryBtn:hover {{
    background-color: {t["pill_active_hover"]};
    border-color: {t["pill_active_hover"]};
}}
QPushButton#DangerBtn, QPushButton#TrashBtn {{
    background-color: {t["danger_bg"]};
    border: 1px solid {t["danger_border"]};
    color: {t["danger_fg"]};
}}
QPushButton#DangerBtn:hover, QPushButton#TrashBtn:hover {{
    background-color: {t["danger_hover"]};
    border-color: #ef4444;
}}
QPushButton#TrashBtn {{
    padding: {px(4)};
    border-radius: {px(10)};
    min-width: {px(32)};
    max-width: {px(32)};
    min-height: {px(30)};
    max-height: {px(30)};
}}
QPushButton#CompactCardBtn {{
    padding: {px(4)} {px(10)};
    border-radius: {px(10)};
    font-size: {pt(9.5)};
}}
QPushButton#StepperBtn {{
    padding: 0px;
    font-size: {pt(14.0)};
    font-weight: bold;
    border-radius: {px(16)};
    min-width: {px(32)};
    max-width: {px(32)};
    min-height: {px(32)};
    max-height: {px(32)};
}}
QPushButton#NavTabBtn {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {t["text_muted"]};
    padding: {px(6)} {px(15)};
    border-radius: {px(16)};
    font-weight: 500;
}}
QPushButton#NavTabBtn:hover {{
    color: {t["text"]};
    background-color: {t["btn_bg"]};
}}
QPushButton#NavTabBtn[active="true"] {{
    background-color: {t["pill_active_bg"]};
    color: {t["pill_active_fg"]};
    border-color: {t["pill_active_bg"]};
    font-weight: 600;
}}
QPushButton#FavBtn {{
    background: transparent;
    border: none;
    font-size: {pt(14.5)};
    padding: 0px;
    color: {t["text_dim"]};
}}
QPushButton#FavBtn[fav="true"] {{
    color: #f59e0b;
}}

/* Headers & Table Items */
QHeaderView::section {{
    background-color: {t["header_bg"]};
    color: {t["text_muted"]};
    border: none;
    border-bottom: 1px solid {t["border_subtle"]};
    padding: {px(4)} {px(9)};
    font-weight: 600;
}}
QTableWidget::item {{
    padding: 0px {px(8)};
}}
QTableWidget::item:selected, QListWidget::item:selected {{
    background-color: {t["selection_bg"]};
    color: {t["selection_fg"]};
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: {px(9)};
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {t["scroll_handle"]};
    border-radius: {px(4)};
    min-height: {px(28)};
}}
QScrollBar::handle:vertical:hover {{
    background: {t["scroll_handle_hover"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: {px(9)};
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t["scroll_handle"]};
    border-radius: {px(4)};
    min-width: {px(28)};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Semantic Typography Labels */
QLabel#StatValue {{
    font-size: {pt(16.5)};
    font-weight: 700;
    color: {t["accent"]};
    background: transparent;
}}
QLabel#StatLabel {{
    font-size: {pt(9.2)};
    color: {t["text_muted"]};
    background: transparent;
}}
QLabel#CharTitle, QLabel#TitleText {{
    font-size: {pt(13.5)};
    font-weight: 700;
    color: {t["text"]};
    background: transparent;
}}
QLabel#CharSubtitle, QLabel#AccentText {{
    font-size: {pt(10.2)};
    font-weight: 600;
    color: {t["accent"]};
    background: transparent;
}}
QLabel#MutedText {{
    font-size: {pt(9.2)};
    color: {t["text_muted"]};
    background: transparent;
}}
QLabel#MonoDimText {{
    font-size: {pt(9.0)};
    color: {t["text_dim"]};
    font-family: monospace;
    background: transparent;
}}
QLabel#WarnText {{
    font-size: {pt(9.2)};
    font-weight: 600;
    color: {t["warn_fg"]};
    background: transparent;
}}
QLabel#SectionHeading {{
    font-weight: 600;
    color: {t["text_muted"]};
    background: transparent;
}}
QLabel#FolderChip {{
    background-color: {t["card_elev"]};
    border: 1px solid {t["border"]};
    border-radius: {px(9)};
    padding: {px(5)} {px(11)};
    color: {t["text_muted"]};
    font-family: monospace;
    font-size: {pt(9.2)};
}}
QLabel#RulesetPill {{
    background-color: {t["accent_soft"]};
    color: {t["accent"]};
    border: 1px solid {t["accent_border"]};
    border-radius: {px(11)};
    padding: {px(2)} {px(10)};
    font-size: {pt(9.0)};
    font-weight: 700;
}}
QLabel#PortraitFrame {{
    background-color: {t["card_elev"]};
    border: 1px solid {t["border"]};
    border-radius: {px(12)};
    color: {t["accent"]};
    font-weight: 700;
}}
QSplitter::handle {{
    background-color: {t["border_subtle"]};
    width: 1px;
    height: 1px;
}}
"""


DARK_STYLESHEET = _build_stylesheet(_DARK_TOKENS, 1.0, is_light=False)
LIGHT_STYLESHEET = _build_stylesheet(_LIGHT_TOKENS, 1.0, is_light=True)


@functools.lru_cache(maxsize=32)
def _cached_stylesheet(is_light: bool, scale_pct: int) -> str:
    tokens = _LIGHT_TOKENS if is_light else _DARK_TOKENS
    return _build_stylesheet(tokens, scale_pct / 100.0, is_light=is_light)


def get_stylesheet(theme: str = "dark", scale: float = 1.0) -> str:
    is_light = str(theme).lower() == "light"
    scale_pct = max(85, min(150, round(float(scale) * 100)))
    return _cached_stylesheet(is_light, scale_pct)
