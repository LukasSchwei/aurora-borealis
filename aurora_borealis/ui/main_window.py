"""Main window for Aurora Borealis with 3 screens and 10-tab clickable builder."""

from __future__ import annotations

import random
import re
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, load_config, save_config
from ..engine import RulesEngine, parse_weight_lb
from ..extractor import extract_msi_assets
from ..library import delete_character, duplicate_character, scan_characters_folder
from ..loader import ContentRepository
from ..models import (
    ABILITIES,
    ABILITY_ABBR,
    ActiveSelection,
    CharacterState,
    ComputedCharacter,
    Element,
    InventoryItem,
)
from ..paths import get_config_path, get_custom_dir, get_templates_dir
from ..pdf_export import export_character_pdf, validate_character_for_pdf
from ..persistence import encode_portrait_file, load_dnd5e, save_dnd5e
from ..rules_55e import get_55e_background_abilities
from .character_select import CharacterSelectView
from .dialogs import DuplicateReportDialog, MagicGearDialog, NewCharacterDialog, pixmap_from_portrait
from .github_view import GitHubContentView
from .styles import DARK_STYLESHEET, LIGHT_STYLESHEET, get_stylesheet

POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}


def _fmt_mod(val: int) -> str:
    return f"+{val}" if val >= 0 else str(val)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "character").strip().lower()).strip("_")
    return f"{cleaned or 'character'}.dnd5e"


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
    """Draw 3 crisp 4-pointed sparkle stars in the exact given hex color."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color_hex))

    def draw_star(cx: float, cy: float, outer_r: float) -> None:
        inner_r = 0.44 * outer_r
        pts = [
            QPointF(cx, cy - outer_r),
            QPointF(cx + inner_r, cy - inner_r),
            QPointF(cx + outer_r, cy),
            QPointF(cx + inner_r, cy + inner_r),
            QPointF(cx, cy + outer_r),
            QPointF(cx - inner_r, cy + inner_r),
            QPointF(cx - outer_r, cy),
            QPointF(cx - inner_r, cy - inner_r),
        ]
        path = QPainterPath()
        path.moveTo(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        path.closeSubpath()
        painter.drawPath(path)

    draw_star(size * 0.38, size * 0.56, size * 0.38)
    draw_star(size * 0.74, size * 0.28, size * 0.24)
    draw_star(size * 0.76, size * 0.74, size * 0.17)
    painter.end()
    return pix


class _CatalogSelectorTab(QWidget):
    """Reusable clickable search + list + Select/Clear + HTML inspector + scoped choices tab."""

    def __init__(
        self,
        repo: ContentRepository,
        element_type: str,
        title: str,
        on_select_id,
        on_clear_id,
        extra_top_widget: Optional[QWidget] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.element_type = element_type
        self.title = title
        self._on_select_id = on_select_id
        self._on_clear_id = on_clear_id
        self._current_selected_id = ""
        self._preview_id = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        self.lbl_current = QLabel(f"Selected {title}: None")
        self.lbl_current.setObjectName("AccentText")
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_clicked)
        hdr.addWidget(self.lbl_current, 1)
        hdr.addWidget(btn_clear)
        left_l.addLayout(hdr)

        if extra_top_widget is not None:
            left_l.addWidget(extra_top_widget)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(f"Search {title.lower()}…")
        self.txt_search.textChanged.connect(self.refresh_list)
        left_l.addWidget(self.txt_search)

        self.lst_items = QListWidget()
        self.lst_items.currentItemChanged.connect(self._on_preview)
        self.lst_items.itemDoubleClicked.connect(lambda _: self._select_preview())
        left_l.addWidget(self.lst_items, 1)

        btn_select = QPushButton(f"Select {title}")
        btn_select.setObjectName("PrimaryBtn")
        btn_select.clicked.connect(self._select_preview)
        left_l.addWidget(btn_select)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)

        desc_box = QGroupBox(f"{title} Details")
        dl = QVBoxLayout(desc_box)
        self.desc_browser = QTextBrowser()
        self.desc_browser.setOpenExternalLinks(True)
        dl.addWidget(self.desc_browser)
        right_l.addWidget(desc_box, 1)

        self.choices_group = QGroupBox(f"{title} Choices")
        cl_outer = QVBoxLayout(self.choices_group)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.choices_container = QWidget()
        self.choices_layout = QVBoxLayout(self.choices_container)
        self.choices_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.choices_container)
        cl_outer.addWidget(scroll)
        right_l.addWidget(self.choices_group, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 580])
        layout.addWidget(splitter)

        self.refresh_list()

    def set_title(self, title: str) -> None:
        self.title = title
        self.choices_group.setTitle(f"{title} Choices")
        self.txt_search.setPlaceholderText(f"Search {title.lower()}…")

    def refresh_list(self) -> None:
        q = self.txt_search.text()
        items = self.repo.search(q, [self.element_type])
        self.lst_items.blockSignals(True)
        self.lst_items.clear()
        for el in items:
            prefix = "✓ " if el.id == self._current_selected_id else ""
            it = QListWidgetItem(f"{prefix}{el.name}")
            it.setData(Qt.ItemDataRole.UserRole, el.id)
            self.lst_items.addItem(it)
            if el.id == self._preview_id or (not self._preview_id and el.id == self._current_selected_id):
                self.lst_items.setCurrentItem(it)
        self.lst_items.blockSignals(False)

    def sync_selected(self, selected_id: str) -> None:
        self._current_selected_id = selected_id
        el = self.repo.get(selected_id) if selected_id else None
        self.lbl_current.setText(
            f"Selected {self.title}: {el.name}" if el else f"Selected {self.title}: None (click to choose)"
        )
        self.refresh_list()
        if el and not self._preview_id:
            self._show_desc(el)
        elif not el and not self._preview_id:
            self.desc_browser.setHtml(f"<p>No {self.title.lower()} selected yet. Click one on the left to inspect and select it.</p>")

    def _on_preview(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        eid = current.data(Qt.ItemDataRole.UserRole) or ""
        self._preview_id = eid
        el = self.repo.get(eid)
        if el:
            self._show_desc(el)

    def _show_desc(self, el: Element) -> None:
        body = el.description_html or el.sheet_description or "<p>No description available.</p>"
        self.desc_browser.setHtml(
            f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>{el.type} — {el.source}</p>{body}"
        )

    def _select_preview(self) -> None:
        cur = self.lst_items.currentItem()
        if cur is None:
            return
        eid = cur.data(Qt.ItemDataRole.UserRole) or ""
        if eid:
            self._on_select_id(eid)

    def _clear_clicked(self) -> None:
        self._preview_id = ""
        self._on_clear_id()


def _make_kde_win_icon(kind: str, color_hex: str, size: int = 16) -> QIcon:
    """Use system KDE/Freedesktop window control icon if available, else draw crisp KDE Breeze vector."""
    theme_map = {
        "minimize": ("window-minimize-symbolic", "window-minimize"),
        "maximize": ("window-maximize-symbolic", "window-maximize"),
        "restore": ("window-restore-symbolic", "window-restore"),
        "close": ("window-close-symbolic", "window-close"),
    }
    for tname in theme_map.get(kind, ()):
        ic = QIcon.fromTheme(tname)
        if not ic.isNull():
            return ic

    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color_hex), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m = size * 0.28
    mid = size * 0.5
    if kind == "minimize":
        # KDE Breeze downward chevron
        p.drawLine(QPointF(m, mid - 1.5), QPointF(mid, mid + 2.5))
        p.drawLine(QPointF(mid, mid + 2.5), QPointF(size - m, mid - 1.5))
    elif kind == "maximize":
        # KDE Breeze upward chevron
        p.drawLine(QPointF(m, mid + 2.0), QPointF(mid, mid - 2.0))
        p.drawLine(QPointF(mid, mid - 2.0), QPointF(size - m, mid + 2.0))
    elif kind == "restore":
        # KDE Breeze diamond
        r = size * 0.24
        p.drawLine(QPointF(mid, mid - r), QPointF(mid + r, mid))
        p.drawLine(QPointF(mid + r, mid), QPointF(mid, mid + r))
        p.drawLine(QPointF(mid, mid + r), QPointF(mid - r, mid))
        p.drawLine(QPointF(mid - r, mid), QPointF(mid, mid - r))
    else:
        # KDE Breeze close X
        p.drawLine(QPointF(m, m), QPointF(size - m, size - m))
        p.drawLine(QPointF(size - m, m), QPointF(m, size - m))
    p.end()
    return QIcon(pix)


class _WindowTitleBar(QFrame):
    """Custom integrated window bar with KDE Breeze window controls, +/- UI scale stepper & theme toggle."""

    def __init__(self, parent_win: QMainWindow, icon_path: Path) -> None:
        super().__init__(parent_win)
        self._win = parent_win
        self._drag_pos = None
        self._theme = "dark"
        self.setObjectName("WindowTitleBar")
        self.setFixedHeight(46)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(14, 4, 10, 4)
        hl.setSpacing(8)

        lbl_icon = QLabel()
        lbl_icon.setFixedSize(26, 26)
        if icon_path.is_file():
            lbl_icon.setPixmap(QIcon(str(icon_path)).pixmap(26, 26))
        hl.addWidget(lbl_icon)

        self.lbl_title = QLabel("Aurora Borealis")
        self.lbl_title.setObjectName("WindowTitleText")
        hl.addWidget(self.lbl_title)

        self.lbl_breadcrumb = QLabel("·  Character Library")
        self.lbl_breadcrumb.setObjectName("WindowBreadcrumb")
        hl.addWidget(self.lbl_breadcrumb)
        hl.addStretch()

        # Scale stepper: [-] [100%] [+]
        self.btn_scale_minus = QPushButton("−")
        self.btn_scale_minus.setObjectName("StepperBtn")
        self.btn_scale_minus.setToolTip("Decrease UI Scale")
        self.btn_scale_minus.setCursor(Qt.CursorShape.PointingHandCursor)

        self.lbl_scale_val = QLabel("100%")
        self.lbl_scale_val.setObjectName("ScaleValuePill")
        self.lbl_scale_val.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_scale_plus = QPushButton("+")
        self.btn_scale_plus.setObjectName("StepperBtn")
        self.btn_scale_plus.setToolTip("Increase UI Scale")
        self.btn_scale_plus.setCursor(Qt.CursorShape.PointingHandCursor)

        hl.addWidget(self.btn_scale_minus)
        hl.addWidget(self.lbl_scale_val)
        hl.addWidget(self.btn_scale_plus)

        self.btn_theme = QPushButton("☀")
        self.btn_theme.setObjectName("ThemeToggleBtn")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.setToolTip("Switch to Light Mode")
        hl.addWidget(self.btn_theme)

        # KDE Breeze window controls
        self.btn_min = QPushButton()
        self.btn_min.setObjectName("KdeWinBtn")
        self.btn_min.setToolTip("Minimize")
        self.btn_min.setIconSize(QSize(16, 16))
        self.btn_min.clicked.connect(self._win.showMinimized)

        self.btn_max = QPushButton()
        self.btn_max.setObjectName("KdeWinBtn")
        self.btn_max.setToolTip("Maximize / Restore")
        self.btn_max.setIconSize(QSize(16, 16))
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("KdeCloseBtn")
        self.btn_close.setToolTip("Close")
        self.btn_close.setIconSize(QSize(16, 16))
        self.btn_close.clicked.connect(self._win.close)

        hl.addSpacing(4)
        hl.addWidget(self.btn_min)
        hl.addWidget(self.btn_max)
        hl.addWidget(self.btn_close)
        self._refresh_kde_icons()

    def _refresh_kde_icons(self) -> None:
        fg = "#1f1f1f" if self._theme == "light" else "#e2e5ea"
        self.btn_min.setIcon(_make_kde_win_icon("minimize", fg))
        self.btn_max.setIcon(_make_kde_win_icon("restore" if self._win.isMaximized() else "maximize", fg))
        self.btn_close.setIcon(_make_kde_win_icon("close", fg))

    def set_theme_icon(self, theme: str) -> None:
        self._theme = "light" if theme == "light" else "dark"
        if self._theme == "light":
            self.btn_theme.setText("☾")
            self.btn_theme.setToolTip("Switch to Dark Mode")
        else:
            self.btn_theme.setText("☀")
            self.btn_theme.setToolTip("Switch to Light Mode")
        self._refresh_kde_icons()

    def set_scale_value(self, scale: float) -> None:
        self.lbl_scale_val.setText(f"{round(scale * 100)}%")

    def set_breadcrumb(self, text: str) -> None:
        self.lbl_breadcrumb.setText(f"·  {text}" if text else "")

    def _toggle_maximize(self) -> None:
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self._refresh_kde_icons()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            wh = self._win.windowHandle()
            if wh is not None and wh.startSystemMove():
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self._win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(
        self,
        repo: ContentRepository,
        data_dir: Path,
        msi_path: Optional[Path] = None,
        initial_file: Optional[Path] = None,
        custom_dir: Optional[Path] = None,
        templates_dir: Optional[Path] = None,
        config: Optional[AppConfig] = None,
        config_path: Optional[Path] = None,
        auto_sync: bool = False,
    ) -> None:
        super().__init__()
        self.repo = repo
        self.engine = RulesEngine(repo)
        self.data_dir = Path(data_dir)
        self.custom_dir = Path(custom_dir) if custom_dir else get_custom_dir()
        self.templates_dir = Path(templates_dir) if templates_dir else get_templates_dir()
        self.config_path = Path(config_path) if config_path else get_config_path()
        self.config = config if config is not None else load_config(self.config_path)
        self.msi_path = Path(msi_path) if msi_path else None
        self.current_file: Optional[Path] = None
        self._updating = False
        self._dirty = False
        self._equip_sort_col: int = 1
        self._equip_sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
        self._spell_sort_col: int = 0
        self._spell_sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

        # Start new character with NOTHING pre-selected
        self.state = CharacterState()
        self.computed: ComputedCharacter = self.engine.evaluate(self.state)

        self.setWindowTitle("Aurora Borealis — D&D 5e / 5.5e Character Builder")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMouseTracking(True)
        self._icon_path = Path(__file__).resolve().parent.parent / "assets" / "aurora-borealis.svg"
        if self._icon_path.is_file():
            self.setWindowIcon(QIcon(str(self._icon_path)))
        self.resize(1420, 920)

        self._build_shortcuts()
        self._build_screens()
        self.apply_theme(self.config.theme, persist=False)
        self.apply_scale(self.config.ui_scale, persist=False)

        self.refresh_library()
        self.github_view.set_installed_indexes(self.config.installed_indexes)
        self.github_view.set_duplicate_count(len(self.repo.duplicates))

        if initial_file and Path(initial_file).is_file():
            self.open_character_file(Path(initial_file))
        else:
            self._recalculate_and_refresh()
            self.show_character_select()

        if auto_sync and not self.config.auto_imported_official:
            QTimer.singleShot(350, self._trigger_auto_official_sync)

    # ------------------------------------------------------------------
    # Keyboard Shortcuts (no top File/Tools menu bar) & 3-Screen Stack
    # ------------------------------------------------------------------
    def _build_shortcuts(self) -> None:
        self.menuBar().setVisible(False)

        shortcuts = [
            ("Ctrl+N", self.new_character_with_dialog),
            ("Ctrl+O", self.open_dialog),
            ("Ctrl+S", self.save_character),
            ("Ctrl+Shift+S", self.save_character_as),
            ("Ctrl+P", self.export_pdf_dialog),
        ]
        for seq, slot in shortcuts:
            act = QAction(self)
            act.setShortcut(seq)
            act.triggered.connect(slot)
            self.addAction(act)

    def _build_screens(self) -> None:
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.title_bar = _WindowTitleBar(self, self._icon_path)
        self.title_bar.btn_theme.clicked.connect(self.toggle_theme)
        self.title_bar.btn_scale_minus.clicked.connect(lambda: self._step_scale(-0.10))
        self.title_bar.btn_scale_plus.clicked.connect(lambda: self._step_scale(0.10))
        shell_layout.addWidget(self.title_bar)

        self.screen_stack = QStackedWidget()
        shell_layout.addWidget(self.screen_stack, 1)
        self.setCentralWidget(shell)

        # Screen 1: Character Selection
        self.select_view = CharacterSelectView()
        self.select_view.open_character_requested.connect(self.open_character_file)
        self.select_view.new_character_requested.connect(self.new_character_with_dialog)
        self.select_view.import_dnd5e_requested.connect(self.import_dnd5e_to_library)
        self.select_view.export_pdf_requested.connect(self._export_pdf_for_path)
        self.select_view.duplicate_character_requested.connect(self._duplicate_library_char)
        self.select_view.delete_character_requested.connect(self._delete_library_char)
        self.select_view.toggle_favorite_requested.connect(self._toggle_favorite)
        self.select_view.change_folder_requested.connect(self._change_characters_folder)
        self.select_view.refresh_requested.connect(self.refresh_library)
        self.select_view.open_github_requested.connect(self.show_github_manager)

        # Screen 2: GitHub & 5e.tools Content Manager
        self.github_view = GitHubContentView(self.custom_dir)
        self.github_view.back_requested.connect(self.show_character_select)
        self.github_view.import_local_folder_requested.connect(self.import_custom_folder)
        self.github_view.show_duplicates_requested.connect(self.show_duplicates_dialog)
        self.github_view.content_changed.connect(self._on_github_content_changed)

        # Screen 3: 10-Tab Clickable Character Builder
        self.builder_view = self._build_builder_screen()

        self.screen_stack.addWidget(self.select_view)
        self.screen_stack.addWidget(self.github_view)
        self.screen_stack.addWidget(self.builder_view)
        self._update_status_summary()

    def apply_theme(self, theme: str, persist: bool = True) -> None:
        normalized = "light" if str(theme).lower() == "light" else "dark"
        self.config.theme = normalized
        self.setStyleSheet(get_stylesheet(normalized, self.config.ui_scale))
        if hasattr(self, "title_bar"):
            self.title_bar.set_theme_icon(normalized)
        if persist:
            save_config(self.config, self.config_path)

    def toggle_theme(self) -> None:
        next_theme = "light" if self.config.theme == "dark" else "dark"
        self.apply_theme(next_theme, persist=True)

    def _step_scale(self, delta: float) -> None:
        new_scale = round(max(0.85, min(1.5, self.config.ui_scale + delta)), 2)
        self.apply_scale(new_scale, persist=True)

    def _edge_at(self, pos) -> Qt.Edge:
        margin = 6
        edges = Qt.Edge(0)
        if pos.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - margin:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            edges = self._edge_at(event.position().toPoint())
            if edges:
                wh = self.windowHandle()
                if wh is not None and wh.startSystemResize(edges):
                    event.accept()
                    return
        super().mousePressEvent(event)

    def apply_scale(self, scale: float, persist: bool = True) -> None:
        clamped = max(0.85, min(1.5, float(scale)))
        self.config.ui_scale = clamped
        self.setStyleSheet(get_stylesheet(self.config.theme, clamped))
        if hasattr(self, "title_bar"):
            self.title_bar.set_scale_value(clamped)
            self.title_bar.setFixedHeight(max(40, round(46 * clamped)))
        if hasattr(self, "select_view") and hasattr(self.select_view, "set_ui_scale"):
            self.select_view.set_ui_scale(clamped)
        if persist:
            save_config(self.config, self.config_path)

    def show_character_select(self) -> None:
        if not self.confirm_leave_character():
            return
        self.refresh_library()
        self.screen_stack.setCurrentWidget(self.select_view)
        self.title_bar.set_breadcrumb("Character Library")

    def show_github_manager(self) -> None:
        if not self.confirm_leave_character():
            return
        self.github_view.set_duplicate_count(len(self.repo.duplicates))
        self.screen_stack.setCurrentWidget(self.github_view)
        self.title_bar.set_breadcrumb("Additional Content")

    def show_builder(self) -> None:
        self.screen_stack.setCurrentWidget(self.builder_view)
        self.title_bar.set_breadcrumb(self.state.name or "New Adventurer")

    def _mark_dirty(self) -> None:
        if not self._updating:
            self._dirty = True

    def confirm_leave_character(self) -> bool:
        if self.screen_stack.currentWidget() is not self.builder_view:
            return True
        if not self._dirty and self.current_file is not None:
            return True
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Leave Character Customisation")
        msg.setText(f"Do you want to save '{self.state.name or 'New Adventurer'}' before leaving?")
        btn_save = msg.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        btn_dont_save = msg.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is btn_save:
            self.save_character()
            return not self._dirty
        if clicked is btn_dont_save:
            self._dirty = False
            return True
        return False

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.confirm_leave_character():
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # Screen 3: 10-Tab Clickable Character Builder
    # ------------------------------------------------------------------
    def _build_builder_screen(self) -> QWidget:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Row 1: Identity & Actions Bar
        top_bar = QFrame()
        top_bar.setObjectName("TopNavBar")
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(14, 8, 14, 8)

        btn_back = QPushButton("← Characters")
        btn_back.clicked.connect(self.show_character_select)
        self.lbl_top_name = QLabel("New Adventurer")
        self.lbl_top_name.setObjectName("TitleText")
        self.lbl_top_sub = QLabel("Lv 1")
        self.lbl_top_sub.setObjectName("RulesetPill")
        self.lbl_top_ruleset = QLabel("5e")
        self.lbl_top_ruleset.setObjectName("RulesetPill")

        tb_layout.addWidget(btn_back)
        tb_layout.addWidget(self.lbl_top_name)
        tb_layout.addWidget(self.lbl_top_sub)
        tb_layout.addWidget(self.lbl_top_ruleset)
        tb_layout.addStretch()

        btn_save = QPushButton("Save")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.clicked.connect(self.save_character)
        btn_pdf = QPushButton("Export Official PDF")
        btn_pdf.clicked.connect(self.export_pdf_dialog)
        btn_gh = QPushButton("Content (GitHub / 5e.tools)")
        btn_gh.clicked.connect(self.show_github_manager)

        tb_layout.addWidget(btn_save)
        tb_layout.addWidget(btn_pdf)
        tb_layout.addWidget(btn_gh)
        root_layout.addWidget(top_bar)

        # Row 2: Dedicated 10-Tab Clickable Bar
        tab_bar = QFrame()
        tab_bar.setObjectName("SubBar")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(14, 6, 14, 6)
        tab_layout.setSpacing(4)

        self.builder_tabs_stack = QStackedWidget()
        self.nav_buttons: list[QPushButton] = []

        # Build dedicated clickable selector tabs
        self.tab_race = _CatalogSelectorTab(
            self.repo,
            "Race",
            "Race",
            on_select_id=self.select_race_by_id,
            on_clear_id=lambda: self.select_race_by_id(""),
        )

        cls_lvl_widget = QWidget()
        clw = QHBoxLayout(cls_lvl_widget)
        clw.setContentsMargins(0, 0, 0, 0)
        clw.addWidget(QLabel("Character Level:"))
        btn_lvl_m = QPushButton("-")
        btn_lvl_m.setObjectName("StepperBtn")
        btn_lvl_m.clicked.connect(lambda: self.spn_level.setValue(max(1, self.spn_level.value() - 1)))
        self.spn_level = QSpinBox()
        self.spn_level.setObjectName("StepperSpin")
        self.spn_level.setRange(1, 20)
        self.spn_level.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spn_level.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spn_level.setFixedWidth(56)
        self.spn_level.valueChanged.connect(self._on_level_changed)
        btn_lvl_p = QPushButton("+")
        btn_lvl_p.setObjectName("StepperBtn")
        btn_lvl_p.clicked.connect(lambda: self.spn_level.setValue(min(20, self.spn_level.value() + 1)))
        clw.addWidget(btn_lvl_m)
        clw.addWidget(self.spn_level)
        clw.addWidget(btn_lvl_p)
        clw.addStretch()

        self.tab_class = _CatalogSelectorTab(
            self.repo,
            "Class",
            "Class",
            on_select_id=self.select_class_by_id,
            on_clear_id=lambda: self.select_class_by_id(""),
            extra_top_widget=cls_lvl_widget,
        )

        # 5.5e Official Background ASI controls inside Background tab
        self.bg_asi_group = QGroupBox("5.5e Background Attribute Points")
        asi_layout = QVBoxLayout(self.bg_asi_group)
        self.lbl_bg_asi_allowed = QLabel("Allowed abilities: —")
        self.lbl_bg_asi_allowed.setObjectName("AccentText")
        asi_layout.addWidget(self.lbl_bg_asi_allowed)

        mode_row = QHBoxLayout()
        self.btn_asi_21 = QPushButton("+2 / +1")
        self.btn_asi_111 = QPushButton("+1 / +1 / +1")
        self.btn_asi_21.clicked.connect(lambda: self._set_bg_asi_mode("21"))
        self.btn_asi_111.clicked.connect(lambda: self._set_bg_asi_mode("111"))
        mode_row.addWidget(self.btn_asi_21)
        mode_row.addWidget(self.btn_asi_111)
        mode_row.addStretch()
        asi_layout.addLayout(mode_row)

        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel("+2:"))
        self.cmb_asi_plus2 = QComboBox()
        self.cmb_asi_plus2.currentIndexChanged.connect(self._on_bg_asi_combo_changed)
        pick_row.addWidget(self.cmb_asi_plus2)
        pick_row.addWidget(QLabel("+1:"))
        self.cmb_asi_plus1 = QComboBox()
        self.cmb_asi_plus1.currentIndexChanged.connect(self._on_bg_asi_combo_changed)
        pick_row.addWidget(self.cmb_asi_plus1)
        asi_layout.addLayout(pick_row)
        self.lbl_bg_asi_summary = QLabel("")
        self.lbl_bg_asi_summary.setObjectName("MutedText")
        asi_layout.addWidget(self.lbl_bg_asi_summary)

        self.tab_background = _CatalogSelectorTab(
            self.repo,
            "Background",
            "Background",
            on_select_id=self.select_background_by_id,
            on_clear_id=lambda: self.select_background_by_id(""),
            extra_top_widget=self.bg_asi_group,
        )

        tab_specs = [
            ("Overview", self._build_tab_overview()),
            ("Race / Species", self.tab_race),
            ("Class", self.tab_class),
            ("Background", self.tab_background),
            ("Abilities", self._build_tab_abilities()),
            ("Choices & Feats", self._build_tab_choices_feats()),
            ("Skills & Features", self._build_tab_skills_features()),
            ("Equipment", self._build_tab_equipment()),
            ("Spells", self._build_tab_spells()),
            ("Details & Notes", self._build_tab_notes()),
        ]
        for idx, (label, page) in enumerate(tab_specs):
            self.builder_tabs_stack.addWidget(page)
            btn = QPushButton(label)
            btn.setObjectName("NavTabBtn")
            btn.setProperty("active", idx == 0)
            btn.clicked.connect(lambda _=False, i=idx: self._switch_builder_tab(i))
            self.nav_buttons.append(btn)
            tab_layout.addWidget(btn)
        tab_layout.addStretch()
        root_layout.addWidget(tab_bar)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self._build_sidebar())
        body.addWidget(self.builder_tabs_stack)
        body.setSizes([290, 1090])
        root_layout.addWidget(body, 1)
        return root

    def _switch_builder_tab(self, index: int) -> None:
        self.builder_tabs_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setProperty("active", i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(265)
        panel.setMaximumWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 6, 10)
        layout.setSpacing(8)

        header_card = QFrame()
        header_card.setObjectName("SidebarCard")
        hc_row = QHBoxLayout(header_card)
        self.btn_rail_portrait = QPushButton("Add\nPhoto")
        self.btn_rail_portrait.setObjectName("RailPortraitBtn")
        self.btn_rail_portrait.setFixedSize(64, 64)
        self.btn_rail_portrait.clicked.connect(self._pick_character_portrait)
        self.lbl_rail_portrait = QLabel("")
        self.lbl_rail_portrait.setObjectName("PortraitFrame")
        self.lbl_rail_portrait.setFixedSize(64, 64)
        self.lbl_rail_portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rail_portrait.hide()

        name_col = QVBoxLayout()
        self.lbl_char_name = QLabel("New Adventurer")
        self.lbl_char_name.setObjectName("CharTitle")
        self.lbl_char_name.setWordWrap(True)
        self.lbl_char_sub = QLabel("Level 1")
        self.lbl_char_sub.setObjectName("CharSubtitle")
        self.lbl_char_sub.setWordWrap(True)
        name_col.addWidget(self.lbl_char_name)
        name_col.addWidget(self.lbl_char_sub)

        hc_row.addWidget(self.btn_rail_portrait)
        hc_row.addWidget(self.lbl_rail_portrait)
        hc_row.addLayout(name_col, 1)
        layout.addWidget(header_card)

        combat_card = QFrame()
        combat_card.setObjectName("SidebarCard")
        grid = QGridLayout(combat_card)
        self.stat_labels: dict[str, QLabel] = {}
        stat_defs = [
            ("hp", "Max HP", 0, 0),
            ("ac", "Armor Class", 0, 1),
            ("init", "Initiative", 1, 0),
            ("speed", "Speed", 1, 1),
            ("prof", "Proficiency", 2, 0),
            ("pp", "Passive Perc.", 2, 1),
        ]
        for key, title, r, c in stat_defs:
            box = QVBoxLayout()
            val_lbl = QLabel("0")
            val_lbl.setObjectName("StatValue")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt_lbl = QLabel(title)
            txt_lbl.setObjectName("StatLabel")
            txt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(val_lbl)
            box.addWidget(txt_lbl)
            grid.addLayout(box, r, c)
            self.stat_labels[key] = val_lbl
        layout.addWidget(combat_card)

        ab_card = QFrame()
        ab_card.setObjectName("SidebarCard")
        ab_grid = QGridLayout(ab_card)
        self.sidebar_ab_labels: dict[str, QLabel] = {}
        for idx, ab in enumerate(ABILITIES):
            r, c = divmod(idx, 2)
            box = QVBoxLayout()
            name_lbl = QLabel(ABILITY_ABBR[ab])
            name_lbl.setObjectName("StatLabel")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl = QLabel("10 (+0)")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet("font-weight:bold; font-size:10.5pt;")
            box.addWidget(name_lbl)
            box.addWidget(val_lbl)
            ab_grid.addLayout(box, r, c)
            self.sidebar_ab_labels[ab] = val_lbl
        layout.addWidget(ab_card)

        self.spell_rail_card = QFrame()
        self.spell_rail_card.setObjectName("SidebarCard")
        sp_l = QVBoxLayout(self.spell_rail_card)
        self.lbl_rail_spell_title = QLabel("Spellcasting")
        self.lbl_rail_spell_title.setObjectName("AccentText")
        self.lbl_rail_spell_body = QLabel("None")
        self.lbl_rail_spell_body.setWordWrap(True)
        self.lbl_rail_spell_body.setObjectName("MutedText")
        sp_l.addWidget(self.lbl_rail_spell_title)
        sp_l.addWidget(self.lbl_rail_spell_body)
        layout.addWidget(self.spell_rail_card)

        layout.addStretch()
        return panel

    # ------------------------------------------------------------------
    # Tab 0: Overview (Clickable summary cards)
    # ------------------------------------------------------------------
    def _build_tab_overview(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        top_box = QGroupBox("Character Summary & Ruleset")
        form = QFormLayout(top_box)
        self.txt_overview_name = QLineEdit()
        self.txt_overview_name.textChanged.connect(self._on_overview_name_changed)

        self.cmb_ruleset = QComboBox()
        self.cmb_ruleset.addItem("D&D 5e (2014)", "5e")
        self.cmb_ruleset.addItem("D&D 5.5e (2024 Revised)", "5.5e")
        self.cmb_ruleset.currentIndexChanged.connect(self._on_ruleset_changed)

        lvl_row = QHBoxLayout()
        btn_lm = QPushButton("-")
        btn_lm.setObjectName("StepperBtn")
        btn_lm.clicked.connect(lambda: self.spn_level.setValue(max(1, self.spn_level.value() - 1)))
        self.lbl_overview_level = QLabel("Level 1")
        self.lbl_overview_level.setStyleSheet("font-weight:bold; min-width:70px;")
        self.lbl_overview_level.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_lp = QPushButton("+")
        btn_lp.setObjectName("StepperBtn")
        btn_lp.clicked.connect(lambda: self.spn_level.setValue(min(20, self.spn_level.value() + 1)))
        lvl_row.addWidget(btn_lm)
        lvl_row.addWidget(self.lbl_overview_level)
        lvl_row.addWidget(btn_lp)
        lvl_row.addSpacing(18)
        lvl_row.addWidget(QLabel("XP:"))
        self.spn_xp = QSpinBox()
        self.spn_xp.setRange(0, 999999)
        self.spn_xp.setSingleStep(100)
        self.spn_xp.setFixedWidth(120)
        self.spn_xp.valueChanged.connect(self._on_xp_changed)
        lvl_row.addWidget(self.spn_xp)
        lvl_row.addStretch()

        form.addRow("Character Name:", self.txt_overview_name)
        form.addRow("Ruleset:", self.cmb_ruleset)
        form.addRow("Level / XP:", lvl_row)
        layout.addWidget(top_box)

        # Clickable Quick-Jump Step Cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(12)

        self.btn_card_race = self._make_overview_card("1. Race / Species", "Not selected — click to choose", 1)
        self.btn_card_class = self._make_overview_card("2. Class", "Not selected — click to choose", 2)
        self.btn_card_bg = self._make_overview_card("3. Background", "Not selected — click to choose", 3)
        self.btn_card_choices = self._make_overview_card("4. Choices & Feats", "0 pending choices", 5)
        self.btn_card_abilities = self._make_overview_card("5. Ability Scores", "Click to adjust scores", 4)
        self.btn_card_spells = self._make_overview_card("6. Equipment & Spells", "Click to manage gear", 7)

        cards_grid.addWidget(self.btn_card_race, 0, 0)
        cards_grid.addWidget(self.btn_card_class, 0, 1)
        cards_grid.addWidget(self.btn_card_bg, 1, 0)
        cards_grid.addWidget(self.btn_card_choices, 1, 1)
        cards_grid.addWidget(self.btn_card_abilities, 2, 0)
        cards_grid.addWidget(self.btn_card_spells, 2, 1)
        layout.addLayout(cards_grid)
        layout.addStretch()
        return tab

    def _make_overview_card(self, title: str, subtitle: str, target_tab: int) -> QPushButton:
        btn = QPushButton(f"{title}\n\n{subtitle}")
        btn.setObjectName("OverviewCard")
        btn.setMinimumHeight(110)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._switch_builder_tab(target_tab))
        return btn

    # ------------------------------------------------------------------
    # Tab 4: Abilities (Clickable - / + buttons)
    # ------------------------------------------------------------------
    def _build_tab_abilities(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        btn_row = QHBoxLayout()
        btn_std = QPushButton("Apply Standard Array (15, 14, 13, 12, 10, 8)")
        btn_std.clicked.connect(self._apply_standard_array)
        btn_roll = QPushButton("Roll 4d6 Drop Lowest")
        btn_roll.clicked.connect(self._roll_abilities)
        self.lbl_point_buy = QLabel("Point Buy: 27 / 27 used")
        self.lbl_point_buy.setObjectName("AccentText")
        btn_row.addWidget(btn_std)
        btn_row.addWidget(btn_roll)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_point_buy)
        layout.addLayout(btn_row)

        grid_box = QGroupBox("Ability Scores")
        grid = QGridLayout(grid_box)
        headers = ["Ability", "Base Score", "Bonus", "Total", "Modifier"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setObjectName("SectionHeading")
            grid.addWidget(lbl, 0, col)

        self.ab_spinboxes: dict[str, QSpinBox] = {}
        self.ab_bonus_labels: dict[str, QLabel] = {}
        self.ab_total_labels: dict[str, QLabel] = {}
        self.ab_mod_labels: dict[str, QLabel] = {}

        for row, ab in enumerate(ABILITIES, start=1):
            grid.addWidget(QLabel(ab.capitalize()), row, 0)
            ctrl_box = QHBoxLayout()
            btn_m = QPushButton("-")
            btn_m.setObjectName("StepperBtn")
            spn = QSpinBox()
            spn.setObjectName("StepperSpin")
            spn.setRange(3, 20)
            spn.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spn.setFixedWidth(56)
            spn.valueChanged.connect(self._on_ability_changed)
            btn_p = QPushButton("+")
            btn_p.setObjectName("StepperBtn")
            btn_m.clicked.connect(lambda _=False, s=spn: s.setValue(max(3, s.value() - 1)))
            btn_p.clicked.connect(lambda _=False, s=spn: s.setValue(min(20, s.value() + 1)))
            ctrl_box.addWidget(btn_m)
            ctrl_box.addWidget(spn)
            ctrl_box.addWidget(btn_p)
            ctrl_box.addStretch()
            grid.addLayout(ctrl_box, row, 1)

            b_lbl = QLabel("+0")
            t_lbl = QLabel("10")
            m_lbl = QLabel("+0")
            t_lbl.setStyleSheet("font-weight:bold; background:transparent;")
            m_lbl.setObjectName("AccentText")
            grid.addWidget(b_lbl, row, 2)
            grid.addWidget(t_lbl, row, 3)
            grid.addWidget(m_lbl, row, 4)

            self.ab_spinboxes[ab] = spn
            self.ab_bonus_labels[ab] = b_lbl
            self.ab_total_labels[ab] = t_lbl
            self.ab_mod_labels[ab] = m_lbl

        layout.addWidget(grid_box)
        layout.addStretch()
        return tab

    # ------------------------------------------------------------------
    # Tab 5: Choices & Feats
    # ------------------------------------------------------------------
    def _build_tab_choices_feats(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        sel_group = QGroupBox("All Character Choices")
        sel_outer = QVBoxLayout(sel_group)
        self.lbl_choices_pending = QLabel("")
        self.lbl_choices_pending.setObjectName("WarnText")
        sel_outer.addWidget(self.lbl_choices_pending)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.selections_container = QWidget()
        self.selections_layout = QVBoxLayout(self.selections_container)
        self.selections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.selections_container)
        sel_outer.addWidget(scroll)

        right = QGroupBox("Feat Browser & Description Inspector")
        rl = QVBoxLayout(right)
        self.txt_feat_search = QLineEdit()
        self.txt_feat_search.setPlaceholderText("Search feats…")
        self.txt_feat_search.textChanged.connect(self._refresh_feat_browser)
        rl.addWidget(self.txt_feat_search)
        self.lst_feats_browser = QListWidget()
        self.lst_feats_browser.currentItemChanged.connect(self._on_feat_browser_selected)
        rl.addWidget(self.lst_feats_browser, 1)
        self.choice_desc_browser = QTextBrowser()
        self.choice_desc_browser.setOpenExternalLinks(True)
        rl.addWidget(self.choice_desc_browser, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(sel_group)
        splitter.addWidget(right)
        splitter.setSizes([540, 480])
        layout.addWidget(splitter)
        self._refresh_feat_browser()
        return tab

    # ------------------------------------------------------------------
    # Tab 6: Skills & Features
    # ------------------------------------------------------------------
    def _build_tab_skills_features(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        row_h = 22
        header_h = 24
        saves_group = QGroupBox("Saving Throws")
        saves_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        saves_layout = QVBoxLayout(saves_group)
        saves_layout.setContentsMargins(6, 6, 6, 6)
        self.tbl_saves = QTableWidget(6, 3)
        self.tbl_saves.setHorizontalHeaderLabels(["Ability", "Prof", "Bonus"])
        saves_hdr = self.tbl_saves.horizontalHeader()
        saves_hdr.setMinimumHeight(header_h)
        saves_hdr.setFixedHeight(header_h)
        saves_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        saves_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        saves_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tbl_saves.setColumnWidth(1, 48)
        self.tbl_saves.setColumnWidth(2, 58)
        self.tbl_saves.verticalHeader().setVisible(False)
        self.tbl_saves.verticalHeader().setMinimumSectionSize(row_h)
        self.tbl_saves.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tbl_saves.verticalHeader().setDefaultSectionSize(row_h)
        for r in range(6):
            self.tbl_saves.setRowHeight(r, row_h)
        self.tbl_saves.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_saves.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_saves.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_saves.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tbl_saves.setFixedHeight(header_h + 6 * row_h + 2 * self.tbl_saves.frameWidth() + 2)
        saves_layout.addWidget(self.tbl_saves)
        left_layout.addWidget(saves_group)

        skills_group = QGroupBox("Skills")
        skills_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        skills_layout = QVBoxLayout(skills_group)
        skills_layout.setContentsMargins(6, 6, 6, 6)
        self.tbl_skills = QTableWidget(18, 4)
        self.tbl_skills.setHorizontalHeaderLabels(["Skill", "Attr", "Prof", "Bonus"])
        skills_hdr = self.tbl_skills.horizontalHeader()
        skills_hdr.setMinimumHeight(header_h)
        skills_hdr.setFixedHeight(header_h)
        skills_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        skills_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        skills_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        skills_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tbl_skills.setColumnWidth(1, 48)
        self.tbl_skills.setColumnWidth(2, 56)
        self.tbl_skills.setColumnWidth(3, 58)
        self.tbl_skills.verticalHeader().setVisible(False)
        self.tbl_skills.verticalHeader().setMinimumSectionSize(row_h)
        self.tbl_skills.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tbl_skills.verticalHeader().setDefaultSectionSize(row_h)
        for r in range(18):
            self.tbl_skills.setRowHeight(r, row_h)
        self.tbl_skills.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_skills.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_skills.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_skills.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tbl_skills.setFixedHeight(header_h + 18 * row_h + 2 * self.tbl_skills.frameWidth() + 2)
        skills_layout.addWidget(self.tbl_skills)
        left_layout.addWidget(skills_group)
        left_layout.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        feat_group = QGroupBox("Granted Features, Proficiencies & Languages")
        feat_layout = QVBoxLayout(feat_group)
        self.lst_features = QListWidget()
        self.lst_features.currentItemChanged.connect(self._on_feature_selected)
        feat_layout.addWidget(self.lst_features, 1)
        self.feat_desc_browser = QTextBrowser()
        feat_layout.addWidget(self.feat_desc_browser, 1)
        right_layout.addWidget(feat_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([450, 530])
        layout.addWidget(splitter)
        return tab

    # ------------------------------------------------------------------
    # Tab 7: Equipment
    # ------------------------------------------------------------------
    def _build_tab_equipment(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        cur_group = QGroupBox("Currency & Encumbrance")
        cur_layout = QHBoxLayout(cur_group)
        self.cur_spins: dict[str, QSpinBox] = {}
        for coin in ("cp", "sp", "ep", "gp", "pp"):
            cur_layout.addWidget(QLabel(coin.upper() + ":"))
            spn = QSpinBox()
            spn.setRange(0, 999999)
            spn.valueChanged.connect(self._on_currency_changed)
            cur_layout.addWidget(spn)
            self.cur_spins[coin] = spn
        self.lbl_total_weight = QLabel("Total Weight: 0.0 lb")
        self.lbl_total_weight.setObjectName("AccentText")
        cur_layout.addStretch()
        cur_layout.addWidget(self.lbl_total_weight)
        layout.addWidget(cur_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        cat_box = QGroupBox("Equipment Catalog")
        cat_layout = QVBoxLayout(cat_box)
        filter_row = QHBoxLayout()
        self.txt_equip_search = QLineEdit()
        self.txt_equip_search.setPlaceholderText("Search weapons, armor, gear, magic items…")
        self.txt_equip_search.textChanged.connect(self._refresh_equip_catalog)
        self.cmb_equip_type = QComboBox()
        self.cmb_equip_type.addItems(["All", "Weapon", "Armor", "Item", "Magic Item"])
        self.cmb_equip_type.currentIndexChanged.connect(self._refresh_equip_catalog)
        filter_row.addWidget(self.txt_equip_search, 2)
        filter_row.addWidget(self.cmb_equip_type, 1)
        cat_layout.addLayout(filter_row)

        filter_row2 = QHBoxLayout()
        self.cmb_equip_category = QComboBox()
        self.cmb_equip_category.addItems([
            "All Categories",
            "Consumables",
            "Potions",
            "Scrolls",
            "Adventuring Gear",
            "Tools",
            "Ammunition",
            "Wondrous Items",
            "Rings, Rods & Staves",
        ])
        self.cmb_equip_category.currentIndexChanged.connect(self._refresh_equip_catalog)
        self.cmb_equip_rarity = QComboBox()
        self.cmb_equip_rarity.addItems([
            "All Rarities",
            "Common",
            "Uncommon",
            "Rare",
            "Very Rare",
            "Legendary",
            "Artifact",
        ])
        self.cmb_equip_rarity.currentIndexChanged.connect(self._refresh_equip_catalog)
        filter_row2.addWidget(self.cmb_equip_category, 1)
        filter_row2.addWidget(self.cmb_equip_rarity, 1)
        cat_layout.addLayout(filter_row2)

        self.tbl_equip_catalog = QTableWidget(0, 5)
        self.tbl_equip_catalog.setHorizontalHeaderLabels(["Type", "Name", "Rarity", "Weight", "Cost"])
        self.tbl_equip_catalog.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_equip_catalog.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl_equip_catalog.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_equip_catalog.verticalHeader().setVisible(False)
        self.tbl_equip_catalog.verticalHeader().setDefaultSectionSize(34)
        eq_hdr = self.tbl_equip_catalog.horizontalHeader()
        eq_hdr.setSectionsClickable(True)
        eq_hdr.setSortIndicatorShown(True)
        eq_hdr.setSortIndicator(self._equip_sort_col, self._equip_sort_order)
        eq_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        eq_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        eq_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        eq_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        eq_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.tbl_equip_catalog.setColumnWidth(0, 46)
        self.tbl_equip_catalog.setColumnWidth(2, 58)
        self.tbl_equip_catalog.setColumnWidth(3, 66)
        self.tbl_equip_catalog.setColumnWidth(4, 72)
        eq_hdr.sectionClicked.connect(self._on_equip_header_clicked)
        self.tbl_equip_catalog.currentCellChanged.connect(self._on_equip_preview)
        self.tbl_equip_catalog.cellDoubleClicked.connect(lambda _r, _c: self._add_selected_equipment())
        cat_layout.addWidget(self.tbl_equip_catalog)
        eq_btn_row = QHBoxLayout()
        btn_add_eq = QPushButton("Add to Inventory")
        btn_add_eq.setObjectName("PrimaryBtn")
        btn_add_eq.clicked.connect(self._add_selected_equipment)
        self.btn_magic_gear = QPushButton("✦ Magic / Infused Armor & Weapons…")
        self.btn_magic_gear.clicked.connect(self._open_magic_gear_dialog)
        eq_btn_row.addWidget(btn_add_eq, 1)
        eq_btn_row.addWidget(self.btn_magic_gear, 1)
        cat_layout.addLayout(eq_btn_row)

        right_eq = QWidget()
        right_eq_l = QVBoxLayout(right_eq)
        right_eq_l.setContentsMargins(0, 0, 0, 0)

        inv_box = QGroupBox("Character Inventory")
        inv_layout = QVBoxLayout(inv_box)

        attune_row = QHBoxLayout()
        self.chk_enforce_attunement = QCheckBox("Enforce Magic Item Attunement Rules (max 3)")
        self.chk_enforce_attunement.setChecked(self.config.enforce_attunement)
        self.chk_enforce_attunement.stateChanged.connect(self._on_attunement_rule_toggled)
        self.lbl_attunement = QLabel("Attuned: 0 / 3")
        self.lbl_attunement.setObjectName("AccentText")
        attune_row.addWidget(self.chk_enforce_attunement, 1)
        attune_row.addWidget(self.lbl_attunement)
        inv_layout.addLayout(attune_row)

        self.tbl_inventory = QTableWidget(0, 6)
        self.tbl_inventory.setHorizontalHeaderLabels(["Item", "Type", "Qty", "Equipped", "Attuned", "Weight"])
        self.tbl_inventory.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_inventory.verticalHeader().setVisible(False)
        inv_layout.addWidget(self.tbl_inventory)
        btn_rem_eq = QPushButton("Remove Selected Item")
        btn_rem_eq.setObjectName("DangerBtn")
        btn_rem_eq.clicked.connect(self._remove_selected_inventory)
        inv_layout.addWidget(btn_rem_eq)

        eq_desc_box = QGroupBox("Item Details")
        eq_dl = QVBoxLayout(eq_desc_box)
        self.equip_desc_browser = QTextBrowser()
        eq_dl.addWidget(self.equip_desc_browser)

        right_eq_l.addWidget(inv_box, 2)
        right_eq_l.addWidget(eq_desc_box, 1)

        splitter.addWidget(cat_box)
        splitter.addWidget(right_eq)
        splitter.setSizes([490, 490])
        layout.addWidget(splitter, 1)
        self._refresh_equip_catalog()
        return tab

    # ------------------------------------------------------------------
    # Tab 8: Spells
    # ------------------------------------------------------------------
    def _build_tab_spells(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        hdr_row = QHBoxLayout()
        self.lbl_spellcasting_header = QLabel("Spellcasting: None active for current class/level")
        self.lbl_spellcasting_header.setObjectName("TitleText")
        self.chk_manual_spells = QCheckBox("Allow manual extra spells (override limits)")
        self.chk_manual_spells.setChecked(False)
        self.chk_manual_spells.stateChanged.connect(self._on_manual_spells_toggled)
        hdr_row.addWidget(self.lbl_spellcasting_header, 1)
        hdr_row.addWidget(self.chk_manual_spells)
        layout.addLayout(hdr_row)

        self.lbl_spell_limits = QLabel("")
        self.lbl_spell_limits.setObjectName("AccentText")
        layout.addWidget(self.lbl_spell_limits)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        cat_box = QGroupBox("Spell Catalog")
        cat_layout = QVBoxLayout(cat_box)
        f_row = QHBoxLayout()
        self.txt_spell_search = QLineEdit()
        self.txt_spell_search.setPlaceholderText("Search spells…")
        self.txt_spell_search.textChanged.connect(self._refresh_spell_catalog)
        self.cmb_spell_level = QComboBox()
        self.cmb_spell_level.addItem("All Levels", "")
        self.cmb_spell_level.addItem("Cantrip (0)", "0")
        for lvl in range(1, 10):
            self.cmb_spell_level.addItem(f"Level {lvl}", str(lvl))
        self.cmb_spell_level.currentIndexChanged.connect(self._refresh_spell_catalog)
        f_row.addWidget(self.txt_spell_search, 2)
        f_row.addWidget(self.cmb_spell_level, 1)
        cat_layout.addLayout(f_row)

        f_row2 = QHBoxLayout()
        self.cmb_spell_school = QComboBox()
        self.cmb_spell_school.addItem("All Schools", "")
        for school in (
            "Abjuration",
            "Conjuration",
            "Divination",
            "Enchantment",
            "Evocation",
            "Illusion",
            "Necromancy",
            "Transmutation",
        ):
            self.cmb_spell_school.addItem(school, school.lower())
        self.cmb_spell_school.currentIndexChanged.connect(self._refresh_spell_catalog)
        self.cmb_spell_prop = QComboBox()
        self.cmb_spell_prop.addItem("All Tags", "")
        self.cmb_spell_prop.addItem("Ritual", "ritual")
        self.cmb_spell_prop.addItem("Concentration", "concentration")
        self.cmb_spell_prop.currentIndexChanged.connect(self._refresh_spell_catalog)
        f_row2.addWidget(self.cmb_spell_school, 1)
        f_row2.addWidget(self.cmb_spell_prop, 1)
        cat_layout.addLayout(f_row2)

        self.tbl_spell_catalog = QTableWidget(0, 2)
        self.tbl_spell_catalog.setHorizontalHeaderLabels(["Name", "Level"])
        self.tbl_spell_catalog.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_spell_catalog.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl_spell_catalog.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_spell_catalog.verticalHeader().setVisible(False)
        self.tbl_spell_catalog.verticalHeader().setDefaultSectionSize(34)
        sp_hdr = self.tbl_spell_catalog.horizontalHeader()
        sp_hdr.setSectionsClickable(True)
        sp_hdr.setSortIndicatorShown(True)
        sp_hdr.setSortIndicator(self._spell_sort_col, self._spell_sort_order)
        sp_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        sp_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tbl_spell_catalog.setColumnWidth(1, 58)
        sp_hdr.sectionClicked.connect(self._on_spell_header_clicked)
        self.tbl_spell_catalog.currentCellChanged.connect(self._on_spell_preview)
        self.tbl_spell_catalog.cellDoubleClicked.connect(lambda _r, _c: self._add_selected_spell())
        cat_layout.addWidget(self.tbl_spell_catalog)
        btn_add_sp = QPushButton("Learn / Add Spell")
        btn_add_sp.setObjectName("PrimaryBtn")
        btn_add_sp.clicked.connect(self._add_selected_spell)
        cat_layout.addWidget(btn_add_sp)

        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        known_box = QGroupBox("Known & Prepared Spells")
        known_layout = QVBoxLayout(known_box)
        self.tbl_spells = QTableWidget(0, 3)
        self.tbl_spells.setHorizontalHeaderLabels(["Spell", "Level", "Prepared"])
        self.tbl_spells.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_spells.verticalHeader().setVisible(False)
        self.tbl_spells.currentCellChanged.connect(self._on_known_spell_selected)
        known_layout.addWidget(self.tbl_spells)
        btn_rem_sp = QPushButton("Remove Selected Spell")
        btn_rem_sp.setObjectName("DangerBtn")
        btn_rem_sp.clicked.connect(self._remove_selected_spell)
        known_layout.addWidget(btn_rem_sp)

        desc_box = QGroupBox("Spell Description")
        desc_layout = QVBoxLayout(desc_box)
        self.spell_desc_browser = QTextBrowser()
        desc_layout.addWidget(self.spell_desc_browser)

        right_layout.addWidget(known_box, 1)
        right_layout.addWidget(desc_box, 1)

        splitter.addWidget(cat_box)
        splitter.addWidget(right_box)
        splitter.setSizes([420, 560])
        layout.addWidget(splitter, 1)
        self._refresh_spell_catalog()
        return tab

    # ------------------------------------------------------------------
    # Tab 9: Details & Notes (Portrait, Alignment, Deity, Appearance, Notes)
    # ------------------------------------------------------------------
    def _build_tab_notes(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        details_box = QGroupBox("Character Details, Alignment, Deity & Portrait")
        outer_details = QHBoxLayout(details_box)

        port_col = QVBoxLayout()
        self.lbl_notes_portrait = QLabel("No Image")
        self.lbl_notes_portrait.setObjectName("PortraitFrame")
        self.lbl_notes_portrait.setFixedSize(110, 110)
        self.lbl_notes_portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_choose_p = QPushButton("Choose Portrait…")
        btn_choose_p.clicked.connect(self._pick_character_portrait)
        btn_clear_p = QPushButton("Clear Portrait")
        btn_clear_p.clicked.connect(self._clear_character_portrait)
        port_col.addWidget(self.lbl_notes_portrait)
        port_col.addWidget(btn_choose_p)
        port_col.addWidget(btn_clear_p)
        port_col.addStretch()
        outer_details.addLayout(port_col)

        form = QGridLayout()
        self.txt_name = QLineEdit()
        self.txt_player = QLineEdit()
        self.cmb_align = QComboBox()
        self.cmb_deity = QComboBox()
        self._populate_element_combo(self.cmb_align, "Alignment", allow_none=True)
        self._populate_element_combo(self.cmb_deity, "Deity", allow_none=True)
        self.cmb_align.currentIndexChanged.connect(self._on_align_deity_changed)
        self.cmb_deity.currentIndexChanged.connect(self._on_align_deity_changed)

        self.txt_gender = QLineEdit()
        self.txt_faith = QLineEdit()
        self.txt_age = QLineEdit()
        self.txt_height = QLineEdit()
        self.txt_weight = QLineEdit()
        self.txt_eyes = QLineEdit()
        self.txt_skin = QLineEdit()
        self.txt_hair = QLineEdit()

        fields = [
            ("Character Name:", self.txt_name, 0, 0),
            ("Player Name:", self.txt_player, 0, 2),
            ("Alignment:", self.cmb_align, 1, 0),
            ("Deity:", self.cmb_deity, 1, 2),
            ("Gender:", self.txt_gender, 2, 0),
            ("Faith:", self.txt_faith, 2, 2),
            ("Age:", self.txt_age, 3, 0),
            ("Height:", self.txt_height, 3, 2),
            ("Weight:", self.txt_weight, 4, 0),
            ("Eyes:", self.txt_eyes, 4, 2),
            ("Skin:", self.txt_skin, 5, 0),
            ("Hair:", self.txt_hair, 5, 2),
        ]
        for label, widget, r, c in fields:
            form.addWidget(QLabel(label), r, c)
            form.addWidget(widget, r, c + 1)
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._on_notes_changed)

        outer_details.addLayout(form, 1)
        layout.addWidget(details_box)

        bg_box = QGroupBox("Backstory")
        bg_l = QVBoxLayout(bg_box)
        self.txt_backstory = QPlainTextEdit()
        self.txt_backstory.textChanged.connect(self._on_notes_changed)
        bg_l.addWidget(self.txt_backstory)
        layout.addWidget(bg_box, 1)

        notes_box = QGroupBox("Session Notes")
        n_l = QVBoxLayout(notes_box)
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.textChanged.connect(self._on_notes_changed)
        n_l.addWidget(self.txt_notes)
        layout.addWidget(notes_box, 1)
        return tab

    def _populate_element_combo(
        self, combo: QComboBox, element_type: str, allow_none: bool = False
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        if allow_none:
            combo.addItem("— None —", "")
        for el in self.repo.of_type(element_type):
            combo.addItem(el.name, el.id)
        combo.blockSignals(False)

    # ------------------------------------------------------------------
    # State <-> UI Synchronization
    # ------------------------------------------------------------------
    def _recalculate_and_refresh(self) -> None:
        self.computed = self.engine.evaluate(self.state)
        self._updating = True
        try:
            self._sync_sidebar()
            self._sync_overview_and_selectors()
            self._sync_choices_tab()
            self._sync_abilities_tab()
            self._sync_skills_features_tab()
            self._sync_equipment_tab()
            self._sync_spells_tab()
            self._sync_notes_tab()
        finally:
            self._updating = False

    def _sync_sidebar(self) -> None:
        race_el = self.repo.get(self.state.race_id)
        class_el = self.repo.get(self.state.class_id)
        sub = f"Lv {self.state.level} {race_el.name if race_el else ''} {class_el.name if class_el else ''}".strip()
        self.lbl_char_name.setText(self.state.name or "New Adventurer")
        self.lbl_char_sub.setText(sub)
        self.lbl_top_name.setText(self.state.name or "New Adventurer")
        self.lbl_top_sub.setText(sub)
        self.lbl_top_ruleset.setText(self.state.ruleset or "5e")

        pix = pixmap_from_portrait(self.state.portrait_base64, self.state.portrait_path, size=64)
        if pix:
            self.lbl_rail_portrait.setPixmap(pix)
            self.lbl_rail_portrait.show()
            self.btn_rail_portrait.hide()
        else:
            self.lbl_rail_portrait.hide()
            self.btn_rail_portrait.show()

        c = self.computed
        self.stat_labels["hp"].setText(str(c.max_hp))
        self.stat_labels["ac"].setText(str(c.armor_class))
        self.stat_labels["init"].setText(_fmt_mod(c.initiative))
        self.stat_labels["speed"].setText(f"{c.speed} ft")
        self.stat_labels["prof"].setText(f"+{c.proficiency_bonus}")
        self.stat_labels["pp"].setText(str(c.passive_perception))

        for ab in ABILITIES:
            tot = c.ability_totals[ab]
            mod = _fmt_mod(c.ability_modifiers[ab])
            self.sidebar_ab_labels[ab].setText(f"{tot} ({mod})")

        if c.spellcasting:
            sc = c.spellcasting
            slots_txt = ", ".join(f"L{k}:{v}" for k, v in sorted(sc.slots.items())) or "Cantrips"
            self.lbl_rail_spell_title.setText(f"Spellcasting ({sc.ability[:3].upper()})")
            self.lbl_rail_spell_body.setText(
                f"Save DC: {sc.save_dc}  •  Attack: {_fmt_mod(sc.attack_bonus)}\nSlots: {slots_txt}"
            )
            self.spell_rail_card.show()
        else:
            self.spell_rail_card.hide()

    def _set_combo_by_data(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

    def _sync_overview_and_selectors(self) -> None:
        is_55e = self.state.ruleset == "5.5e"
        self.tab_race.set_title("Species" if is_55e else "Race")
        self.nav_buttons[1].setText("Species" if is_55e else "Race")
        self.bg_asi_group.setVisible(is_55e)

        bg_el = self.repo.get(self.state.background_id)
        allowed = get_55e_background_abilities(bg_el)
        self.lbl_bg_asi_allowed.setText(
            f"Allowed abilities: {', '.join(ABILITY_ABBR[a] for a in allowed)}"
        )
        self.cmb_asi_plus2.blockSignals(True)
        self.cmb_asi_plus1.blockSignals(True)
        self.cmb_asi_plus2.clear()
        self.cmb_asi_plus1.clear()
        for ab in allowed:
            self.cmb_asi_plus2.addItem(ab.capitalize(), ab)
            self.cmb_asi_plus1.addItem(ab.capitalize(), ab)

        is_111 = list(self.state.background_asi.values()).count(1) == 3
        self.btn_asi_21.setObjectName("" if is_111 else "PrimaryBtn")
        self.btn_asi_111.setObjectName("PrimaryBtn" if is_111 else "")
        self.btn_asi_21.style().unpolish(self.btn_asi_21)
        self.btn_asi_21.style().polish(self.btn_asi_21)
        self.btn_asi_111.style().unpolish(self.btn_asi_111)
        self.btn_asi_111.style().polish(self.btn_asi_111)
        self.cmb_asi_plus2.setEnabled(not is_111)
        self.cmb_asi_plus1.setEnabled(not is_111)

        if not is_111:
            ab2 = next((k for k, v in self.state.background_asi.items() if v == 2 and k in allowed), allowed[0])
            ab1 = next((k for k, v in self.state.background_asi.items() if v == 1 and k in allowed and k != ab2), allowed[1])
            self._set_combo_by_data(self.cmb_asi_plus2, ab2)
            self._set_combo_by_data(self.cmb_asi_plus1, ab1)
        self.cmb_asi_plus2.blockSignals(False)
        self.cmb_asi_plus1.blockSignals(False)
        asi_txt = ", ".join(f"{ABILITY_ABBR[k]} +{v}" for k, v in self.state.background_asi.items() if v)
        self.lbl_bg_asi_summary.setText(f"Active bonuses: {asi_txt or 'None'}")

        self.txt_overview_name.setText(self.state.name)
        self._set_combo_by_data(self.cmb_ruleset, self.state.ruleset or "5e")
        self.spn_level.setValue(self.state.level)
        self.lbl_overview_level.setText(f"Level {self.state.level}")
        if hasattr(self, "spn_xp"):
            self.spn_xp.setValue(self.state.xp)

        self.tab_race.sync_selected(self.state.race_id)
        self.tab_class.sync_selected(self.state.class_id)
        self.tab_background.sync_selected(self.state.background_id)

        race_el = self.repo.get(self.state.race_id)
        class_el = self.repo.get(self.state.class_id)

        self.btn_card_race.setText(
            f"1. {'Species' if is_55e else 'Race'}\n\n"
            + (f"✓ {race_el.name}" if race_el else "Not selected — click to choose")
        )
        self.btn_card_class.setText(
            "2. Class\n\n"
            + (f"✓ Level {self.state.level} {class_el.name}" if class_el else "Not selected — click to choose")
        )
        self.btn_card_bg.setText(
            "3. Background\n\n"
            + (f"✓ {bg_el.name}" if bg_el else "Not selected — click to choose")
        )
        self.btn_card_abilities.setText(
            "5. Ability Scores\n\n"
            + " | ".join(f"{ABILITY_ABBR[a]} {self.computed.ability_totals[a]}" for a in ABILITIES)
        )
        self.btn_card_spells.setText(
            "6. Equipment & Spells\n\n"
            f"{len(self.state.inventory)} items • {len(self.state.known_spells)} spells"
        )

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _sync_choices_tab(self) -> None:
        self._clear_layout(self.selections_layout)
        self._clear_layout(self.tab_race.choices_layout)
        self._clear_layout(self.tab_class.choices_layout)
        self._clear_layout(self.tab_background.choices_layout)

        pending_total = 0
        for active_sel in self.computed.active_selections:
            chosen = self.state.selections.get(active_sel.key, [])
            filled = sum(1 for i in range(active_sel.rule.number) if i < len(chosen) and chosen[i])
            if not active_sel.rule.optional and filled < active_sel.rule.number:
                pending_total += active_sel.rule.number - filled
            self._add_selection_widget(active_sel, filled, self.selections_layout)

            # Mirror scoped choices into Race / Class / Background tabs
            src_el = self.repo.get(active_sel.source_element_id)
            if active_sel.source_element_id == self.state.race_id or (src_el and src_el.type in ("Race", "Sub Race", "Racial Trait")):
                self._add_selection_widget(active_sel, filled, self.tab_race.choices_layout)
            elif active_sel.source_element_id == self.state.class_id or (src_el and src_el.type in ("Class", "Archetype", "Class Feature", "Archetype Feature")):
                self._add_selection_widget(active_sel, filled, self.tab_class.choices_layout)
            elif active_sel.source_element_id == self.state.background_id or (src_el and src_el.type in ("Background", "Background Feature")):
                self._add_selection_widget(active_sel, filled, self.tab_background.choices_layout)

        if pending_total > 0:
            self.lbl_choices_pending.setText(f"{pending_total} choice(s) remaining")
            self.btn_card_choices.setText(f"4. Choices & Feats\n\n• {pending_total} choice(s) pending — click to resolve")
        else:
            self.lbl_choices_pending.setText("All required choices selected ✓")
            self.btn_card_choices.setText("4. Choices & Feats\n\n✓ All required choices resolved")

    def _add_selection_widget(
        self,
        active_sel: ActiveSelection,
        filled: int,
        target_layout: QVBoxLayout,
    ) -> None:
        is_complete = filled >= active_sel.rule.number or active_sel.rule.optional
        card = QFrame()
        card.setObjectName("ChoiceCard" if is_complete else "ChoiceCardPending")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(10, 8, 10, 8)
        vbox.setSpacing(6)

        hdr = QHBoxLayout()
        lbl_title = QLabel(
            f"<b>{active_sel.rule.name}</b> <span style='color:#94a3b8;'>({active_sel.source_element_name})</span>"
        )
        status_color = "#4ade80" if filled >= active_sel.rule.number else "#facc15"
        status_text = (
            f"✓ {filled}/{active_sel.rule.number}"
            if filled >= active_sel.rule.number
            else f"• {filled}/{active_sel.rule.number}"
        )
        lbl_status = QLabel(status_text)
        lbl_status.setStyleSheet(f"color:{status_color}; font-weight:bold; font-size:8.5pt;")
        hdr.addWidget(lbl_title, 1)
        hdr.addWidget(lbl_status)
        vbox.addLayout(hdr)

        chosen = self.state.selections.get(active_sel.key, [])
        all_granted_ids = {el.id for el in self.computed.granted_elements}
        other_sel_ids: set[str] = set()
        for skey, svals in self.state.selections.items():
            if skey != active_sel.key:
                for sv in svals:
                    if sv:
                        other_sel_ids.add(sv)

        for slot_idx in range(active_sel.rule.number):
            cmb = QComboBox()
            cmb.addItem("— Choose —", "")
            current_val = chosen[slot_idx] if slot_idx < len(chosen) else ""
            same_sel_other = {
                chosen[i]
                for i in range(active_sel.rule.number)
                if i != slot_idx and i < len(chosen) and chosen[i]
            }
            taken_ids = set(same_sel_other)
            if active_sel.rule.type != "List":
                taken_ids |= all_granted_ids
                taken_ids |= other_sel_ids
            taken_ids.discard(current_val)

            seen_opts: set[str] = set()
            for opt_id, opt_name in active_sel.options:
                if opt_id in taken_ids or opt_id in seen_opts:
                    continue
                seen_opts.add(opt_id)
                cmb.addItem(opt_name, opt_id)
            if current_val:
                idx = cmb.findData(current_val)
                if idx >= 0:
                    cmb.setCurrentIndex(idx)

            def make_handler(skey: str, sidx: int, count: int, combo_ref: QComboBox):
                def _on_changed(_idx: int) -> None:
                    if self._updating:
                        return
                    val = combo_ref.currentData() or ""
                    lst = list(self.state.selections.get(skey, [""] * count))
                    while len(lst) < count:
                        lst.append("")
                    if val and any(i != sidx and v == val for i, v in enumerate(lst)):
                        return
                    lst[sidx] = val
                    self.state.selections[skey] = lst
                    self._mark_dirty()
                    if val and val in self.repo.by_id:
                        self._show_element_description(self.repo.by_id[val], self.choice_desc_browser)
                    self._recalculate_and_refresh()

                return _on_changed

            cmb.currentIndexChanged.connect(
                make_handler(active_sel.key, slot_idx, active_sel.rule.number, cmb)
            )
            vbox.addWidget(cmb)

        target_layout.addWidget(card)

    def _sync_abilities_tab(self) -> None:
        used_pts = 0
        valid_pb = True
        for ab in ABILITIES:
            base = self.state.abilities.get(ab, 10)
            self.ab_spinboxes[ab].setValue(base)
            bonus = self.computed.ability_bonuses[ab]
            tot = self.computed.ability_totals[ab]
            mod = self.computed.ability_modifiers[ab]
            self.ab_bonus_labels[ab].setText(_fmt_mod(bonus))
            self.ab_total_labels[ab].setText(str(tot))
            self.ab_mod_labels[ab].setText(_fmt_mod(mod))
            if base in POINT_BUY_COSTS:
                used_pts += POINT_BUY_COSTS[base]
            else:
                valid_pb = False

        if valid_pb:
            self.lbl_point_buy.setText(f"Point Buy: {used_pts} / 27 used")
        else:
            self.lbl_point_buy.setText("Point Buy: Custom / Rolled scores")

    def _sync_skills_features_tab(self) -> None:
        for row, ab in enumerate(ABILITIES):
            sv = self.computed.saving_throws[ab]
            prof_it = QTableWidgetItem("●" if sv.proficient else "○")
            prof_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bonus_it = QTableWidgetItem(_fmt_mod(sv.bonus))
            bonus_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_saves.setItem(row, 0, QTableWidgetItem(ab.capitalize()))
            self.tbl_saves.setItem(row, 1, prof_it)
            self.tbl_saves.setItem(row, 2, bonus_it)

        for row, (skill_name, sk) in enumerate(self.computed.skills.items()):
            mark = "◆ (2x)" if sk.expertise else ("●" if sk.proficient else "○")
            attr_it = QTableWidgetItem(ABILITY_ABBR[sk.ability])
            attr_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            prof_it = QTableWidgetItem(mark)
            prof_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bonus_it = QTableWidgetItem(_fmt_mod(sk.bonus))
            bonus_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_skills.setItem(row, 0, QTableWidgetItem(skill_name))
            self.tbl_skills.setItem(row, 1, attr_it)
            self.tbl_skills.setItem(row, 2, prof_it)
            self.tbl_skills.setItem(row, 3, bonus_it)

        self.lst_features.clear()
        for el in self.computed.granted_elements:
            if el.type in ("Level", "Grants", "Support"):
                continue
            item = QListWidgetItem(f"[{el.type}] {el.name}")
            item.setData(Qt.ItemDataRole.UserRole, el.id)
            self.lst_features.addItem(item)

    def _max_attuned_items(self) -> int:
        class_el = self.repo.get(self.state.class_id)
        if class_el and "artificer" in class_el.name.lower():
            if self.state.level >= 18:
                return 6
            if self.state.level >= 14:
                return 5
            if self.state.level >= 10:
                return 4
        return 3

    def _on_attunement_rule_toggled(self, checked: int) -> None:
        self.config.enforce_attunement = bool(checked)
        save_config(self.config, self.config_path)
        self._sync_equipment_tab()

    def _sync_equipment_tab(self) -> None:
        for coin, spn in self.cur_spins.items():
            spn.setValue(self.state.currency.get(coin, 0))
        self.lbl_total_weight.setText(f"Total Weight: {self.computed.total_weight:.1f} lb")

        max_att = self._max_attuned_items()
        cur_att = sum(1 for it in self.state.inventory if it.attuned)
        if hasattr(self, "chk_enforce_attunement"):
            self.chk_enforce_attunement.blockSignals(True)
            self.chk_enforce_attunement.setChecked(self.config.enforce_attunement)
            self.chk_enforce_attunement.blockSignals(False)
            self.chk_enforce_attunement.setText(
                f"Enforce Magic Item Attunement Rules (max {max_att})"
            )
            self.lbl_attunement.setText(
                f"Attuned: {cur_att} / {max_att}"
                if self.config.enforce_attunement
                else f"Attuned: {cur_att} (Unlimited)"
            )

        self.tbl_inventory.setRowCount(len(self.state.inventory))
        for row, inv in enumerate(self.state.inventory):
            self.tbl_inventory.setItem(row, 0, QTableWidgetItem(inv.name))
            self.tbl_inventory.setItem(row, 1, QTableWidgetItem(inv.category or "Item"))

            qty_spin = QSpinBox()
            qty_spin.setRange(1, 9999)
            qty_spin.setValue(inv.quantity)

            def make_qty_handler(r: int):
                def _on_qty(val: int) -> None:
                    if self._updating or r >= len(self.state.inventory):
                        return
                    self.state.inventory[r].quantity = val
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_qty

            qty_spin.valueChanged.connect(make_qty_handler(row))
            self.tbl_inventory.setCellWidget(row, 2, qty_spin)

            chk = QCheckBox()
            chk.setChecked(inv.equipped)

            def make_eq_handler(r: int):
                def _on_eq(checked: int) -> None:
                    if self._updating or r >= len(self.state.inventory):
                        return
                    self.state.inventory[r].equipped = bool(checked)
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_eq

            chk.stateChanged.connect(make_eq_handler(row))
            self.tbl_inventory.setCellWidget(row, 3, chk)

            chk_att = QCheckBox()
            chk_att.setChecked(inv.attuned)

            def make_att_handler(r: int, cb_ref: QCheckBox):
                def _on_att(checked: int) -> None:
                    if self._updating or r >= len(self.state.inventory):
                        return
                    want = bool(checked)
                    if want and self.config.enforce_attunement:
                        limit = self._max_attuned_items()
                        others = sum(
                            1 for idx, it in enumerate(self.state.inventory)
                            if idx != r and it.attuned
                        )
                        if others >= limit:
                            self._updating = True
                            cb_ref.setChecked(False)
                            self._updating = False
                            QMessageBox.information(
                                self,
                                "Attunement Limit Reached",
                                f"You can only attune to {limit} magic item(s) at a time under D&D attunement rules.\n"
                                "Uncheck another attuned item or disable 'Enforce Magic Item Attunement Rules'.",
                            )
                            return
                    self.state.inventory[r].attuned = want
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_att

            chk_att.stateChanged.connect(make_att_handler(row, chk_att))
            self.tbl_inventory.setCellWidget(row, 4, chk_att)

            self.tbl_inventory.setItem(
                row, 5, QTableWidgetItem(f"{inv.weight * inv.quantity:.1f} lb")
            )

    def _spell_counts(self) -> tuple[int, int, list[str]]:
        granted = self.computed.spellcasting.granted_spell_ids if self.computed.spellcasting else []
        combined = list(dict.fromkeys([*granted, *self.state.known_spells]))
        cantrips = 0
        leveled = 0
        for sid in combined:
            el = self.repo.get(sid)
            lvl = el.setters.get("level", "0") if el else "0"
            if lvl == "0":
                cantrips += 1
            else:
                leveled += 1
        return cantrips, leveled, combined

    def _sync_spells_tab(self) -> None:
        self.chk_manual_spells.setChecked(self.state.allow_extra_spells)
        sc = self.computed.spellcasting
        cantrip_cnt, leveled_cnt, combined = self._spell_counts()
        if sc:
            slots_txt = ", ".join(f"L{k}: {v}" for k, v in sorted(sc.slots.items())) or "Cantrips"
            self.lbl_spellcasting_header.setText(
                f"{sc.caster_name} ({sc.ability}) | Save DC: {sc.save_dc} | "
                f"Attack: {_fmt_mod(sc.attack_bonus)} | Slots: {slots_txt}"
            )
            parts = [f"Cantrips: {cantrip_cnt} / {sc.max_cantrips}"]
            if sc.max_known_spells is not None:
                parts.append(f"Spells Known/Book: {leveled_cnt} / {sc.max_known_spells}")
            else:
                parts.append(f"Spells Added: {leveled_cnt} (All class spells available)")
            if sc.max_prepared_spells is not None:
                parts.append(f"Prepared: {len(self.state.prepared_spells)} / {sc.max_prepared_spells}")
            parts.append(f"Max Slot Level: {sc.max_spell_level}")
            if self.state.allow_extra_spells:
                parts.append("[Manual Override Active]")
            self.lbl_spell_limits.setText("  •  ".join(parts))
        else:
            self.lbl_spellcasting_header.setText(
                "Spellcasting: None active for current class/level"
            )
            if self.state.allow_extra_spells:
                self.lbl_spell_limits.setText(
                    f"Manual Override Active — {len(combined)} spell(s) added"
                )
            else:
                self.lbl_spell_limits.setText(
                    "Select a spellcasting class or enable 'Allow manual extra spells' to add spells."
                )

        self.tbl_spells.setRowCount(len(combined))
        prepared_set = set(self.state.prepared_spells)
        granted_set = set(sc.granted_spell_ids if sc else [])
        for row, sid in enumerate(combined):
            el = self.repo.get(sid)
            suffix = " [Class]" if sid in granted_set and sid not in self.state.known_spells else ""
            name_item = QTableWidgetItem(f"{el.name if el else sid}{suffix}")
            name_item.setData(Qt.ItemDataRole.UserRole, sid)
            lvl = el.setters.get("level", "0") if el else "?"
            self.tbl_spells.setItem(row, 0, name_item)
            self.tbl_spells.setItem(row, 1, QTableWidgetItem(lvl))

            chk = QCheckBox()
            chk.setChecked(sid in prepared_set)

            def make_prep_handler(spell_id: str, chk_ref: QCheckBox):
                def _on_prep(checked: int) -> None:
                    if self._updating:
                        return
                    if checked:
                        if (
                            not self.state.allow_extra_spells
                            and self.computed.spellcasting
                            and self.computed.spellcasting.max_prepared_spells is not None
                            and len(self.state.prepared_spells) >= self.computed.spellcasting.max_prepared_spells
                            and spell_id not in self.state.prepared_spells
                        ):
                            self._updating = True
                            chk_ref.setChecked(False)
                            self._updating = False
                            QMessageBox.information(
                                self,
                                "Prepared Spell Limit Reached",
                                f"You can prepare up to {self.computed.spellcasting.max_prepared_spells} spells. "
                                "Enable 'Allow manual extra spells' to override.",
                            )
                            return
                        if spell_id not in self.state.prepared_spells:
                            self.state.prepared_spells.append(spell_id)
                    else:
                        if spell_id in self.state.prepared_spells:
                            self.state.prepared_spells.remove(spell_id)
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_prep

            chk.stateChanged.connect(make_prep_handler(sid, chk))
            self.tbl_spells.setCellWidget(row, 2, chk)

    def _sync_notes_tab(self) -> None:
        pix = pixmap_from_portrait(self.state.portrait_base64, self.state.portrait_path, size=110)
        if pix:
            self.lbl_notes_portrait.setPixmap(pix)
        else:
            self.lbl_notes_portrait.clear()
            self.lbl_notes_portrait.setText("No Image")

        self._set_combo_by_data(self.cmb_align, self.state.alignment_id)
        self._set_combo_by_data(self.cmb_deity, self.state.deity_id)
        self.txt_name.setText(self.state.name)
        self.txt_player.setText(self.state.player_name)
        self.txt_gender.setText(self.state.gender)
        self.txt_faith.setText(self.state.faith)
        self.txt_age.setText(self.state.age)
        self.txt_height.setText(self.state.height)
        self.txt_weight.setText(self.state.weight)
        self.txt_eyes.setText(self.state.eyes)
        self.txt_skin.setText(self.state.skin)
        self.txt_hair.setText(self.state.hair)
        if self.txt_backstory.toPlainText() != self.state.backstory:
            self.txt_backstory.setPlainText(self.state.backstory)
        if self.txt_notes.toPlainText() != self.state.notes:
            self.txt_notes.setPlainText(self.state.notes)

    # ------------------------------------------------------------------
    # Event Handlers & Programmatic Helpers
    # ------------------------------------------------------------------
    def _show_element_description(self, el: Element, browser: QTextBrowser) -> None:
        body = el.description_html or el.sheet_description or "<p>No description available.</p>"
        html_doc = f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>{el.type} — {el.source}</p>{body}"
        browser.setHtml(html_doc)

    def select_race_by_id(self, race_id: str) -> None:
        self.state.race_id = race_id
        self._mark_dirty()
        self._recalculate_and_refresh()

    def select_class_by_id(self, class_id: str) -> None:
        self.state.class_id = class_id
        self._mark_dirty()
        self._recalculate_and_refresh()

    def select_background_by_id(self, background_id: str) -> None:
        self.state.background_id = background_id
        if self.state.ruleset == "5.5e" and background_id:
            allowed = get_55e_background_abilities(self.repo.get(background_id))
            if not self.state.background_asi or any(k not in allowed for k in self.state.background_asi):
                self.state.background_asi = {allowed[0]: 2, allowed[1]: 1}
        elif not background_id:
            self.state.background_asi = {}
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_overview_name_changed(self, text: str) -> None:
        if self._updating:
            return
        self.state.name = text
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_ruleset_changed(self) -> None:
        if self._updating:
            return
        self.state.ruleset = self.cmb_ruleset.currentData() or "5e"
        if self.state.ruleset == "5.5e" and self.state.background_id and not self.state.background_asi:
            allowed = get_55e_background_abilities(self.repo.get(self.state.background_id))
            self.state.background_asi = {allowed[0]: 2, allowed[1]: 1}
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_level_changed(self) -> None:
        if self._updating:
            return
        self.state.level = self.spn_level.value()
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_xp_changed(self, val: int) -> None:
        if self._updating:
            return
        self.state.xp = int(val)
        self._mark_dirty()

    def _on_align_deity_changed(self) -> None:
        if self._updating:
            return
        self.state.alignment_id = self.cmb_align.currentData() or ""
        self.state.deity_id = self.cmb_deity.currentData() or ""
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _set_bg_asi_mode(self, mode: str) -> None:
        allowed = get_55e_background_abilities(self.repo.get(self.state.background_id))
        if mode == "111":
            self.state.background_asi = {ab: 1 for ab in allowed}
        else:
            self.state.background_asi = {allowed[0]: 2, allowed[1]: 1}
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_bg_asi_combo_changed(self) -> None:
        if self._updating:
            return
        allowed = get_55e_background_abilities(self.repo.get(self.state.background_id))
        ab2 = self.cmb_asi_plus2.currentData() or allowed[0]
        ab1 = self.cmb_asi_plus1.currentData() or allowed[1]
        if ab1 == ab2:
            ab1 = next((a for a in allowed if a != ab2), allowed[1])
        self.state.background_asi = {ab2: 2, ab1: 1}
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_ability_changed(self) -> None:
        if self._updating:
            return
        for ab, spn in self.ab_spinboxes.items():
            self.state.abilities[ab] = spn.value()
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _apply_standard_array(self) -> None:
        for ab, score in zip(ABILITIES, [15, 14, 13, 12, 10, 8]):
            self.state.abilities[ab] = score
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _roll_abilities(self) -> None:
        for ab in ABILITIES:
            rolls = sorted(random.randint(1, 6) for _ in range(4))
            self.state.abilities[ab] = sum(rolls[1:])
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _refresh_feat_browser(self) -> None:
        q = self.txt_feat_search.text()
        feats = self.repo.search(q, ["Feat"])[:250]
        self.lst_feats_browser.clear()
        for el in feats:
            it = QListWidgetItem(el.name)
            it.setData(Qt.ItemDataRole.UserRole, el.id)
            self.lst_feats_browser.addItem(it)

    def _on_feat_browser_selected(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        el = self.repo.get(current.data(Qt.ItemDataRole.UserRole) or "")
        if el:
            self._show_element_description(el, self.choice_desc_browser)

    def _on_feature_selected(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        eid = current.data(Qt.ItemDataRole.UserRole)
        el = self.repo.get(eid)
        if el:
            self._show_element_description(el, self.feat_desc_browser)

    def _on_currency_changed(self) -> None:
        if self._updating:
            return
        for coin, spn in self.cur_spins.items():
            self.state.currency[coin] = spn.value()
        self._mark_dirty()

    def _make_equip_type_badge(self, el_type: str) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Type icon colors intentionally avoid Rarity colors (Green/Blue/Purple/Gold/Red)
        if el_type == "Magic Item":
            badge = QLabel()
            badge.setFixedSize(26, 26)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setToolTip(el_type)
            badge.setPixmap(_make_magic_sparkles_pixmap("#f472b6", 17))
            badge.setStyleSheet(
                "background-color:#331829; border:1.5px solid #f472b6; border-radius:13px;"
            )
            hl.addWidget(badge)
            return wrap

        icon_map = {
            "Weapon": ("⚔", "#e2e8f0", "#292524", "#a8a29e"),
            "Armor": ("🛡", "#67e8f9", "#162c36", "#22d3ee"),
            "Item": ("●", "#9ca3af", "#1f2937", "#6b7280"),
        }
        glyph, fg, bg, border = icon_map.get(el_type, ("●", "#9ca3af", "#1f2937", "#6b7280"))
        badge = QLabel(glyph)
        badge.setFixedSize(26, 26)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setToolTip(el_type)
        badge.setStyleSheet(
            f"background-color:{bg}; color:{fg}; border:1.5px solid {border}; "
            "border-radius:13px; font-size:10.5pt; font-weight:bold;"
        )
        hl.addWidget(badge)
        return wrap

    def _make_equip_rarity_badge(self, el: Element) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        _rank, r_letter, r_label, r_fg, r_bg = _item_rarity_info(el)
        rarity_badge = QLabel(r_letter)
        rarity_badge.setFixedSize(26, 26)
        rarity_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rarity_badge.setToolTip(f"Rarity: {r_label}")
        rarity_badge.setStyleSheet(
            f"background-color:{r_bg}; color:{r_fg}; border:1.5px solid {r_fg}; "
            "border-radius:13px; font-size:9.5pt; font-weight:bold;"
        )
        hl.addWidget(rarity_badge)
        return wrap

    def _on_equip_preview(
        self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1
    ) -> None:
        if row < 0 or row >= self.tbl_equip_catalog.rowCount():
            return
        name_item = self.tbl_equip_catalog.item(row, 1)
        eid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
        el = self.repo.get(eid or "")
        if el:
            w = parse_weight_lb(el)
            cost = el.setters.get("cost", "")
            cur = el.setters.get("currency", "")
            cost_txt = f"{cost} {cur}".strip() if cost else "—"
            _rank, _r_letter, r_label, _rfg, _rbg = _item_rarity_info(el)
            extra = f" | Rarity: {r_label} | Cost: {cost_txt} | Weight: {w:.1f} lb"
            if el.setters.get("armorClass"):
                extra += f" | AC: {el.setters['armorClass']}"
            if el.setters.get("damage"):
                extra += f" | Damage: {el.setters['damage']} {el.setters.get('damage_type', '')}".rstrip()
            body = el.description_html or el.sheet_description or "<p>No description available.</p>"
            self.equip_desc_browser.setHtml(
                f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>{el.type} — {el.source}{extra}</p>{body}"
            )

    def _on_equip_header_clicked(self, col: int) -> None:
        if col == self._equip_sort_col:
            self._equip_sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._equip_sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._equip_sort_col = col
            self._equip_sort_order = Qt.SortOrder.AscendingOrder
        self.tbl_equip_catalog.horizontalHeader().setSortIndicator(
            self._equip_sort_col, self._equip_sort_order
        )
        self._refresh_equip_catalog()

    @staticmethod
    def _matches_equip_category(el: Element, category_filter: str) -> bool:
        if not category_filter or category_filter == "All Categories":
            return True
        blob = " ".join([
            el.name,
            el.type,
            el.setters.get("category", ""),
            el.setters.get("type", ""),
            el.setters.get("slot", ""),
            " ".join(el.supports),
        ]).lower()
        if category_filter == "Consumables":
            if el.setters.get("consumable", "").lower() == "true":
                return True
            return any(
                kw in blob
                for kw in (
                    "consumable", "potion", "scroll", "elixir", "poison", "oil",
                    "ammunition", "arrow", "bolt", "ration", "torch", "alchemist",
                    "acid", "antitoxin", "holy water", "dust", "bead", "feather token",
                )
            )
        if category_filter == "Potions":
            return any(kw in blob for kw in ("potion", "elixir", "oil", "philter"))
        if category_filter == "Scrolls":
            return "scroll" in blob
        if category_filter == "Adventuring Gear":
            return "adventuring gear" in blob or (el.type == "Item" and "tool" not in blob and "ammo" not in blob)
        if category_filter == "Tools":
            return any(kw in blob for kw in ("tool", "kit", "musical instrument", "gaming set", "artisan"))
        if category_filter == "Ammunition":
            return any(kw in blob for kw in ("ammunition", "arrow", "bolt", "sling bullet", "blowgun needle"))
        if category_filter == "Wondrous Items":
            return "wondrous" in blob
        if category_filter == "Rings, Rods & Staves":
            return any(kw in blob for kw in ("ring", "rod", "staff", "wand"))
        return True

    def _refresh_equip_catalog(self) -> None:
        query = self.txt_equip_search.text()
        cat = self.cmb_equip_type.currentText()
        sub_cat = self.cmb_equip_category.currentText() if hasattr(self, "cmb_equip_category") else "All Categories"
        rarity_filter = self.cmb_equip_rarity.currentText() if hasattr(self, "cmb_equip_rarity") else "All Rarities"
        types = ["Weapon", "Armor", "Item", "Magic Item"] if cat == "All" else [cat]
        results = self.repo.search(query, types)
        if sub_cat != "All Categories":
            results = [e for e in results if self._matches_equip_category(e, sub_cat)]
        if rarity_filter != "All Rarities":
            results = [e for e in results if _item_rarity_info(e)[2].lower() == rarity_filter.lower()]
        reverse = self._equip_sort_order == Qt.SortOrder.DescendingOrder
        if self._equip_sort_col == 0:
            results.sort(key=lambda e: (e.type.lower(), e.name.lower()), reverse=reverse)
        elif self._equip_sort_col == 2:
            results.sort(key=lambda e: (_item_rarity_info(e)[0], e.name.lower()), reverse=reverse)
        elif self._equip_sort_col == 3:
            results.sort(key=lambda e: (parse_weight_lb(e), e.name.lower()), reverse=reverse)
        elif self._equip_sort_col == 4:
            results.sort(key=lambda e: (_item_cost_gp(e), e.name.lower()), reverse=reverse)
        else:
            results.sort(key=lambda e: e.name.lower(), reverse=reverse)

        shown = results[:300]
        self.tbl_equip_catalog.setRowCount(len(shown))
        for row, el in enumerate(shown):
            self.tbl_equip_catalog.setCellWidget(row, 0, self._make_equip_type_badge(el.type))
            name_item = QTableWidgetItem(el.name)
            name_item.setData(Qt.ItemDataRole.UserRole, el.id)
            self.tbl_equip_catalog.setItem(row, 1, name_item)
            self.tbl_equip_catalog.setCellWidget(row, 2, self._make_equip_rarity_badge(el))

            w = parse_weight_lb(el)
            w_item = QTableWidgetItem(f"{w:.1f} lb" if w > 0 else "—")
            w_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_equip_catalog.setItem(row, 3, w_item)

            cost = el.setters.get("cost", "")
            cur = el.setters.get("currency", "")
            c_item = QTableWidgetItem(f"{cost} {cur}".strip() if cost else "—")
            c_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_equip_catalog.setItem(row, 4, c_item)

    def _open_magic_gear_dialog(self) -> None:
        initial_el: Optional[Element] = None
        row = self.tbl_equip_catalog.currentRow()
        if row >= 0:
            name_item = self.tbl_equip_catalog.item(row, 1)
            eid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            cand = self.repo.get(eid) if eid else None
            if cand is not None and cand.type in ("Armor", "Weapon"):
                initial_el = cand
        dlg = MagicGearDialog(self.repo, initial_element=initial_el, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            inv_item = dlg.build_inventory_item()
            if inv_item is not None:
                self.state.inventory.append(inv_item)
                self._mark_dirty()
                self._recalculate_and_refresh()

    def _add_selected_equipment(self) -> None:
        row = self.tbl_equip_catalog.currentRow()
        if row < 0:
            return
        name_item = self.tbl_equip_catalog.item(row, 1)
        eid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        el = self.repo.get(eid) if eid else None
        if el is None:
            return
        self.state.inventory.append(
            InventoryItem(
                element_id=el.id,
                name=el.name,
                quantity=1,
                equipped=(el.type in ("Armor", "Weapon")),
                weight=parse_weight_lb(el),
                category=el.type,
            )
        )
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _remove_selected_inventory(self) -> None:
        row = self.tbl_inventory.currentRow()
        if 0 <= row < len(self.state.inventory):
            self.state.inventory.pop(row)
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _make_spell_level_badge(self, lvl: str) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        dot = QLabel(str(lvl))
        dot.setFixedSize(26, 26)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setToolTip("Cantrip" if str(lvl) == "0" else f"Level {lvl}")
        dot.setStyleSheet(
            f"background-color:{bg}; color:{fg}; border:1.5px solid {fg}; "
            "border-radius:13px; font-size:9.5pt; font-weight:bold;"
        )
        hl.addWidget(dot)
        return wrap

    def _on_spell_header_clicked(self, col: int) -> None:
        if col == self._spell_sort_col:
            self._spell_sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._spell_sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._spell_sort_col = col
            self._spell_sort_order = Qt.SortOrder.AscendingOrder
        self.tbl_spell_catalog.horizontalHeader().setSortIndicator(
            self._spell_sort_col, self._spell_sort_order
        )
        self._refresh_spell_catalog()

    def _refresh_spell_catalog(self) -> None:
        query = self.txt_spell_search.text()
        lvl_filter = self.cmb_spell_level.currentData() or ""
        school_filter = self.cmb_spell_school.currentData() or "" if hasattr(self, "cmb_spell_school") else ""
        prop_filter = self.cmb_spell_prop.currentData() or "" if hasattr(self, "cmb_spell_prop") else ""
        spells = self.repo.search(query, ["Spell"])
        if lvl_filter:
            spells = [el for el in spells if str(el.setters.get("level", "0")) == lvl_filter]
        if school_filter:
            spells = [
                el for el in spells
                if el.setters.get("school", "").strip().lower() == school_filter
                or school_filter in " ".join(el.supports).lower()
            ]
        if prop_filter == "ritual":
            spells = [
                el for el in spells
                if el.setters.get("isRitual", "").strip().lower() == "true"
                or "ritual" in " ".join(el.supports).lower()
            ]
        elif prop_filter == "concentration":
            spells = [
                el for el in spells
                if el.setters.get("isConcentration", "").strip().lower() == "true"
                or "concentration" in el.setters.get("duration", "").lower()
                or "concentration" in " ".join(el.supports).lower()
            ]

        def _spell_lvl_num(el: Element) -> int:
            raw = str(el.setters.get("level", "0")).strip()
            return int(raw) if raw.isdigit() else 0

        reverse = self._spell_sort_order == Qt.SortOrder.DescendingOrder
        if self._spell_sort_col == 1:
            spells.sort(key=lambda e: (_spell_lvl_num(e), e.name.lower()), reverse=reverse)
        else:
            spells.sort(key=lambda e: (e.name.lower(), _spell_lvl_num(e)), reverse=reverse)

        shown = spells[:350]
        self.tbl_spell_catalog.setRowCount(len(shown))
        for row, el in enumerate(shown):
            lvl = str(el.setters.get("level", "0"))
            name_item = QTableWidgetItem(el.name)
            name_item.setData(Qt.ItemDataRole.UserRole, el.id)
            self.tbl_spell_catalog.setItem(row, 0, name_item)
            self.tbl_spell_catalog.setCellWidget(row, 1, self._make_spell_level_badge(lvl))

    def _on_spell_preview(
        self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1
    ) -> None:
        if row < 0 or row >= self.tbl_spell_catalog.rowCount():
            return
        name_item = self.tbl_spell_catalog.item(row, 0)
        sid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        el = self.repo.get(sid) if sid else None
        if el:
            self._show_element_description(el, self.spell_desc_browser)

    def _on_known_spell_selected(self, row: int, _col: int) -> None:
        if 0 <= row < self.tbl_spells.rowCount():
            item = self.tbl_spells.item(row, 0)
            if item:
                sid = item.data(Qt.ItemDataRole.UserRole)
                el = self.repo.get(sid)
                if el:
                    self._show_element_description(el, self.spell_desc_browser)

    def _on_manual_spells_toggled(self, checked: int) -> None:
        if self._updating:
            return
        self.state.allow_extra_spells = bool(checked)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _add_selected_spell(self) -> None:
        row = self.tbl_spell_catalog.currentRow()
        if row < 0:
            return
        name_item = self.tbl_spell_catalog.item(row, 0)
        sid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        if not sid:
            return
        cantrip_cnt, leveled_cnt, combined = self._spell_counts()
        if sid in combined:
            return

        if not self.state.allow_extra_spells:
            sc = self.computed.spellcasting
            if sc is None:
                QMessageBox.information(
                    self,
                    "Spellcasting Not Active",
                    "Select a spellcasting class first, or enable 'Allow manual extra spells (override limits)'.",
                )
                return
            el = self.repo.get(sid)
            lvl_str = el.setters.get("level", "0") if el else "0"
            lvl = int(lvl_str) if lvl_str.isdigit() else 0
            if lvl > sc.max_spell_level:
                QMessageBox.information(
                    self,
                    "Spell Level Too High",
                    f"{el.name if el else sid} is level {lvl}, but your max spell slot level is {sc.max_spell_level}. "
                    "Enable 'Allow manual extra spells' to override.",
                )
                return
            if lvl == 0 and cantrip_cnt >= sc.max_cantrips:
                QMessageBox.information(
                    self,
                    "Cantrip Limit Reached",
                    f"You already have {cantrip_cnt} / {sc.max_cantrips} cantrips. "
                    "Enable 'Allow manual extra spells' to override.",
                )
                return
            if lvl > 0 and sc.max_known_spells is not None and leveled_cnt >= sc.max_known_spells:
                QMessageBox.information(
                    self,
                    "Spell Limit Reached",
                    f"You already have {leveled_cnt} / {sc.max_known_spells} leveled spells. "
                    "Enable 'Allow manual extra spells' to override.",
                )
                return

        self.state.known_spells.append(sid)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _remove_selected_spell(self) -> None:
        row = self.tbl_spells.currentRow()
        if 0 <= row < self.tbl_spells.rowCount():
            item = self.tbl_spells.item(row, 0)
            sid = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not sid:
                return
            if sid in self.state.known_spells:
                self.state.known_spells.remove(sid)
            if sid in self.state.prepared_spells:
                self.state.prepared_spells.remove(sid)
            # Also clear from any Spell <select> choice if it came from a class feature
            for skey, chosen in list(self.state.selections.items()):
                if sid in chosen:
                    self.state.selections[skey] = ["" if c == sid else c for c in chosen]
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _on_notes_changed(self) -> None:
        if self._updating:
            return
        self.state.name = self.txt_name.text()
        self.state.player_name = self.txt_player.text()
        self.state.gender = self.txt_gender.text()
        self.state.faith = self.txt_faith.text()
        self.state.age = self.txt_age.text()
        self.state.height = self.txt_height.text()
        self.state.weight = self.txt_weight.text()
        self.state.eyes = self.txt_eyes.text()
        self.state.skin = self.txt_skin.text()
        self.state.hair = self.txt_hair.text()
        self.state.backstory = self.txt_backstory.toPlainText()
        self.state.notes = self.txt_notes.toPlainText()
        self.lbl_char_name.setText(self.state.name or "New Adventurer")
        self.lbl_top_name.setText(self.state.name or "New Adventurer")
        self.txt_overview_name.setText(self.state.name)
        self._mark_dirty()

    def _pick_character_portrait(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Character Portrait",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if not path:
            return
        self.state.portrait_path = path
        self.state.portrait_base64 = encode_portrait_file(Path(path))
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _clear_character_portrait(self) -> None:
        self.state.portrait_path = ""
        self.state.portrait_base64 = ""
        self._mark_dirty()
        self._recalculate_and_refresh()

    # ------------------------------------------------------------------
    # Library & GitHub Actions
    # ------------------------------------------------------------------
    def _characters_dir(self) -> Path:
        return Path(self.config.characters_dir)

    def _save_config(self) -> None:
        save_config(self.config, self.config_path)

    def refresh_library(self) -> None:
        folder = self._characters_dir()
        folder.mkdir(parents=True, exist_ok=True)
        summaries = scan_characters_folder(folder, set(self.config.favorites))
        self.select_view.set_header_info(
            folder_path=str(folder),
            element_count=len(self.repo.by_id),
            dup_count=len(self.repo.duplicates),
            index_count=len(self.config.installed_indexes),
        )
        self.select_view.set_characters(summaries)

    def _change_characters_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Characters Folder", str(self._characters_dir())
        )
        if chosen:
            self.config.characters_dir = chosen
            self._save_config()
            self.refresh_library()

    def _toggle_favorite(self, filename: str) -> None:
        if filename in self.config.favorites:
            self.config.favorites.remove(filename)
        else:
            self.config.favorites.append(filename)
        self._save_config()
        self.refresh_library()

    def _duplicate_library_char(self, path: Path) -> None:
        try:
            duplicate_character(path)
            self.refresh_library()
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", str(exc))

    def _delete_library_char(self, path: Path) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Character",
            f"Delete {path.name} from {path.parent}?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_character(path)
            self.refresh_library()

    def _confirm_missing_fields_before_pdf(
        self, state: CharacterState, computed: ComputedCharacter
    ) -> bool:
        missing = validate_character_for_pdf(state, computed, self.repo)
        if not missing:
            return True
        bullet_list = "\n".join(f"• {m}" for m in missing)
        reply = QMessageBox.warning(
            self,
            "Incomplete Character Sheet",
            f"The following fields are missing or incomplete:\n\n{bullet_list}\n\nExport PDF anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _export_pdf_for_path(self, char_path: Path) -> None:
        try:
            st = load_dnd5e(char_path, self.repo)
            comp = self.engine.evaluate(st)
            if not self._confirm_missing_fields_before_pdf(st, comp):
                return
            out_path, _ = QFileDialog.getSaveFileName(
                self, "Export Character Sheet PDF", f"{st.name or 'character'}.pdf", "PDF Files (*.pdf)"
            )
            if out_path:
                if not out_path.endswith(".pdf"):
                    out_path += ".pdf"
                export_character_pdf(
                    st, comp, self.repo, Path(out_path), templates_dir=self.templates_dir
                )
                self.statusBar().showMessage(f"Exported PDF to {out_path}")
        except Exception as exc:
            QMessageBox.critical(self, "PDF Export Failed", str(exc))

    def _find_character_name_conflict(
        self, name: str, exclude_path: Optional[Path] = None
    ) -> Optional[Path]:
        """Return an existing .dnd5e file path if another character already uses this name or filename."""
        folder = self._characters_dir()
        if not folder.is_dir():
            return None
        exclude_res = exclude_path.resolve() if exclude_path is not None else None
        candidate = folder / _safe_filename(name)
        if candidate.exists() and (exclude_res is None or candidate.resolve() != exclude_res):
            return candidate
        norm = (name or "").strip().lower()
        if norm:
            for summary in scan_characters_folder(folder):
                if exclude_res is not None and summary.path.resolve() == exclude_res:
                    continue
                if summary.name.strip().lower() == norm:
                    return summary.path
        return None

    def import_dnd5e_to_library(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import .dnd5e Character", "", "Aurora Character (*.dnd5e);;All Files (*)"
        )
        if not path:
            return
        src = Path(path)
        dest_dir = self._characters_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if src.resolve() != dest.resolve():
            if dest.exists():
                stem = src.stem
                idx = 2
                while (dest_dir / f"{stem}_{idx}{src.suffix}").exists():
                    idx += 1
                dest = dest_dir / f"{stem}_{idx}{src.suffix}"
            shutil.copy2(src, dest)
        self.refresh_library()
        self.open_character_file(dest)

    def new_character_with_dialog(self) -> None:
        if not self.confirm_leave_character():
            return
        dlg = NewCharacterDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        chosen_name = dlg.selected_name()
        conflict = self._find_character_name_conflict(chosen_name)
        if conflict is not None:
            QMessageBox.warning(
                self,
                "Character Name Already Exists",
                f"A character named '{chosen_name}' already exists ({conflict.name}).\n"
                "Please choose a unique character name to avoid overwriting it.",
            )
            return
        self.current_file = None
        # Nothing pre-selected on creation
        self.state = CharacterState(
            name=chosen_name,
            ruleset=dlg.selected_ruleset(),
            portrait_path=dlg.portrait_path,
            portrait_base64=dlg.portrait_base64,
        )
        self._dirty = True
        self._recalculate_and_refresh()
        self._switch_builder_tab(0)
        self.show_builder()

    def new_character(self) -> None:
        if not self.confirm_leave_character():
            return
        self.current_file = None
        self.state = CharacterState()
        self._dirty = True
        self._recalculate_and_refresh()
        self._switch_builder_tab(0)
        self.show_builder()

    def open_dialog(self) -> None:
        if not self.confirm_leave_character():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Aurora Character", str(self._characters_dir()), "Aurora Character (*.dnd5e);;All Files (*)"
        )
        if path:
            self.open_character_file(Path(path))

    def open_character_file(self, path: Path) -> None:
        try:
            self.state = load_dnd5e(path, self.repo)
            self.current_file = path
            self._dirty = False
            self._recalculate_and_refresh()
            self._switch_builder_tab(0)
            self.show_builder()
            self.statusBar().showMessage(f"Opened {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", f"Could not load {path}:\n{exc}")

    def save_character(self) -> bool:
        if self.current_file is None:
            folder = self._characters_dir()
            folder.mkdir(parents=True, exist_ok=True)
            conflict = self._find_character_name_conflict(self.state.name)
            if conflict is not None:
                QMessageBox.warning(
                    self,
                    "Duplicate Character Name",
                    f"Cannot save: a character named '{self.state.name}' already exists ({conflict.name}).\n"
                    "Please rename your character or use Save As with a different filename.",
                )
                return False
            target_file = folder / _safe_filename(self.state.name)
        else:
            conflict = self._find_character_name_conflict(self.state.name, exclude_path=self.current_file)
            if conflict is not None:
                QMessageBox.warning(
                    self,
                    "Duplicate Character Name",
                    f"Another character named '{self.state.name}' already exists ({conflict.name}).\n"
                    "Please choose a unique character name before saving.",
                )
                return False
            target_file = self.current_file
        try:
            save_dnd5e(self.state, self.repo, self.computed, target_file)
            self.current_file = target_file
            self._dirty = False
            self.refresh_library()
            self.statusBar().showMessage(f"Saved {self.current_file}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return False

    def save_character_as(self) -> None:
        default_path = str(self._characters_dir() / _safe_filename(self.state.name))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Aurora Character", default_path, "Aurora Character (*.dnd5e)"
        )
        if path:
            if not path.endswith(".dnd5e"):
                path += ".dnd5e"
            target = Path(path)
            if target.exists() and (self.current_file is None or target.resolve() != self.current_file.resolve()):
                QMessageBox.warning(
                    self,
                    "File Already Exists",
                    f"Cannot overwrite existing character file '{target.name}'. Please pick a different filename.",
                )
                return
            self.current_file = target
            self.save_character()

    def export_pdf_dialog(self) -> None:
        if not self._confirm_missing_fields_before_pdf(self.state, self.computed):
            return
        default_name = f"{self.state.name or 'character'}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Character Sheet PDF", default_name, "PDF Files (*.pdf)"
        )
        if path:
            if not path.endswith(".pdf"):
                path += ".pdf"
            try:
                export_character_pdf(
                    self.state,
                    self.computed,
                    self.repo,
                    Path(path),
                    templates_dir=self.templates_dir,
                )
                self.statusBar().showMessage(f"Exported PDF to {path}")
            except Exception as exc:
                QMessageBox.critical(self, "PDF Export Failed", str(exc))

    def reload_repository(self) -> None:
        self.repo.clear()
        self.repo.load_directory(self.data_dir)
        if self.custom_dir.is_dir():
            self.repo.load_directory(self.custom_dir)
        for cdir in self.config.custom_dirs:
            self.repo.load_directory(Path(cdir))

        self.tab_race.refresh_list()
        self.tab_class.refresh_list()
        self.tab_background.refresh_list()
        self._populate_element_combo(self.cmb_align, "Alignment", allow_none=True)
        self._populate_element_combo(self.cmb_deity, "Deity", allow_none=True)
        self._refresh_feat_browser()
        self._refresh_equip_catalog()
        self._refresh_spell_catalog()
        self._recalculate_and_refresh()
        self.refresh_library()
        self.github_view.set_duplicate_count(len(self.repo.duplicates))
        self._update_status_summary()

    def _update_status_summary(self) -> None:
        self.statusBar().showMessage(
            f"Loaded {len(self.repo.by_id)} elements ({self.repo.file_count} XML files, {len(self.repo.duplicates)} duplicates detected)"
        )

    def _on_github_content_changed(self, installed: list[dict]) -> None:
        self.config.installed_indexes = installed
        if installed:
            self.config.auto_imported_official = True
        self._save_config()
        self.reload_repository()

    def _trigger_auto_official_sync(self) -> None:
        self.statusBar().showMessage("Syncing official Aurora & Aurora Legacy content from GitHub…")
        self.github_view.start_official_sync()

    def show_duplicates_dialog(self) -> None:
        dlg = DuplicateReportDialog(self.repo.duplicates, self)
        dlg.exec()

    def import_custom_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Custom Aurora XML Folder")
        if folder:
            if folder not in self.config.custom_dirs:
                self.config.custom_dirs.append(folder)
                self._save_config()
            self.reload_repository()
            self.statusBar().showMessage(f"Imported custom XML folder: {folder}")

    def reextract_msi_data(self) -> None:
        msi = self.msi_path
        if msi is None or not msi.is_file():
            chosen, _ = QFileDialog.getOpenFileName(
                self, "Select Aurora Setup.msi", "", "Windows Installer (*.msi)"
            )
            if not chosen:
                return
            msi = Path(chosen)
            self.msi_path = msi
        try:
            extract_msi_assets(msi, self.data_dir, self.templates_dir)
            self.reload_repository()
        except Exception as exc:
            QMessageBox.critical(self, "Extraction Failed", str(exc))
