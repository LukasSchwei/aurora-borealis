"""Main window for Aurora Borealis with 4 screens and 10-tab clickable builder."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    UI_ZOOM_STAGES,
    AppConfig,
    get_zoom_stage_index,
    load_config,
    save_config,
    snap_ui_scale,
)
from ..engine import RulesEngine
from ..loader import ContentRepository
from ..models import CharacterState, ComputedCharacter, Element
from ..paths import get_config_path, get_custom_dir, get_templates_dir
from ..platform_utils import is_windows
from .character_select import CharacterSelectView
from .companion_view import CompanionEditorView
from .github_view import GitHubContentView
from .icons import apply_button_icon, refresh_themed_icons
from .styles import get_stylesheet
from .tabs.abilities_tab import AbilitiesTabMixin
from .tabs.animal_forms_tab import AnimalFormsTabMixin
from .tabs.choices_tab import ChoicesTabMixin
from .tabs.companions_tab import CompanionsTabMixin
from .tabs.equipment_tab import EquipmentTabMixin
from .tabs.library_io import LibraryIOMixin
from .tabs.notes_tab import NotesTabMixin
from .tabs.overview_tab import OverviewTabMixin
from .tabs.sidebar import SidebarMixin
from .tabs.skills_features_tab import SkillsFeaturesTabMixin
from .tabs.spells_tab import SpellsTabMixin
from .ui_helpers import (
    configure_dropdown_combo,
    ensure_widgets_fit,
    fit_button,
    install_global_wheel_filter,
    refit_buttons,
    refresh_spinbox_margins,
    set_global_ui_scale,
)
from .widgets.catalog_selector import _CatalogSelectorTab
from .widgets.item_icons import (
    _equip_rarity_icon,
    _equip_type_icon,
    _fmt_mod,
    _item_rarity_info,
    _make_magic_sparkles_pixmap,
    _safe_filename,
    _spell_level_icon,
    _spell_school_icon,
    _spell_tags_icon,
)
from .widgets.title_bar import _WindowTitleBar

__all__ = [
    "MainWindow",
    "_CatalogSelectorTab",
    "_WindowTitleBar",
    "_equip_rarity_icon",
    "_equip_type_icon",
    "_fmt_mod",
    "_item_rarity_info",
    "_make_magic_sparkles_pixmap",
    "_safe_filename",
    "_spell_level_icon",
    "_spell_school_icon",
    "_spell_tags_icon",
]


class MainWindow(
    OverviewTabMixin,
    AbilitiesTabMixin,
    ChoicesTabMixin,
    SkillsFeaturesTabMixin,
    EquipmentTabMixin,
    SpellsTabMixin,
    NotesTabMixin,
    AnimalFormsTabMixin,
    CompanionsTabMixin,
    SidebarMixin,
    LibraryIOMixin,
    QMainWindow,
):
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
        self._choices_sig: Optional[tuple] = None
        self._spell_catalog_sig: Optional[tuple] = None
        self._equip_catalog_sig: Optional[tuple] = None
        self._last_resize_edge: Qt.Edge = Qt.Edge(0)
        self._select_view_scale_dirty: bool = False
        self._applied_scale: Optional[float] = None

        # Start new character with NOTHING pre-selected
        self.state = CharacterState()
        self.computed: ComputedCharacter = self.engine.evaluate(self.state)

        self.setWindowTitle("Aurora Borealis — D&D 5e / 5.5e Character Builder")
        win_flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if is_windows():
            win_flags |= (
                Qt.WindowType.WindowMinimizeButtonHint
                | Qt.WindowType.WindowMaximizeButtonHint
                | Qt.WindowType.WindowSystemMenuHint
            )
        self.setWindowFlags(win_flags)
        self.setMouseTracking(True)
        assets_dir = Path(__file__).resolve().parent.parent / "assets"
        self._icon_path = assets_dir / "aurora-borealis.svg"
        win_icon = assets_dir / ("aurora-borealis.ico" if is_windows() else "aurora-borealis.svg")
        if not win_icon.is_file():
            win_icon = self._icon_path
        if win_icon.is_file():
            self.setWindowIcon(QIcon(str(win_icon)))
        install_global_wheel_filter(QApplication.instance())
        self.resize(1520, 940)

        self._build_shortcuts()
        self._build_screens()
        self.config.theme = "light" if str(self.config.theme).lower() == "light" else "dark"
        if hasattr(self, "title_bar"):
            self.title_bar.set_theme_icon(self.config.theme)
        refresh_themed_icons(self, self.config.theme)
        if hasattr(self, "select_view") and hasattr(self.select_view, "set_theme"):
            self.select_view.set_theme(self.config.theme)
        self.apply_scale(self.config.ui_scale, persist=False)

        self.refresh_library()
        self.github_view.set_installed_indexes(self.config.installed_indexes)
        self.github_view.set_duplicate_count(len(self.repo.duplicates))

        if initial_file and Path(initial_file).is_file():
            init_path = Path(initial_file)
            if init_path.suffix.lower() == ".dndcomp":
                self.open_companion_file(init_path)
            else:
                self.open_character_file(init_path)
        else:
            self._recalculate_and_refresh()
            self.show_character_select()

        if auto_sync and not self.config.auto_imported_official:
            QTimer.singleShot(350, self._trigger_auto_official_sync)

    # ------------------------------------------------------------------
    # Keyboard Shortcuts (no top File/Tools menu bar) & 4-Screen Stack
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
        self.title_bar.btn_scale_minus.clicked.connect(lambda: self._step_scale_stage(-1))
        self.title_bar.btn_scale_plus.clicked.connect(lambda: self._step_scale_stage(1))
        self.title_bar.cmb_scale_stage.currentIndexChanged.connect(self._on_scale_stage_selected)
        shell_layout.addWidget(self.title_bar)

        self.screen_stack = QStackedWidget()
        shell_layout.addWidget(self.screen_stack, 1)
        self.setCentralWidget(shell)

        # Screen 0: Character Selection
        self.select_view = CharacterSelectView()
        self.select_view.open_character_requested.connect(self.open_character_file)
        self.select_view.open_companion_requested.connect(self.open_companion_file)
        self.select_view.new_character_requested.connect(self.new_character_with_dialog)
        self.select_view.new_companion_requested.connect(self.new_companion)
        self.select_view.import_dnd5e_requested.connect(self.import_dnd5e_to_library)
        self.select_view.export_pdf_requested.connect(self._export_pdf_for_path)
        self.select_view.export_companion_pdf_requested.connect(self._export_companion_pdf_for_path)
        self.select_view.duplicate_character_requested.connect(self._duplicate_library_char)
        self.select_view.delete_character_requested.connect(self._delete_library_char)
        self.select_view.toggle_favorite_requested.connect(self._toggle_favorite)
        self.select_view.change_folder_requested.connect(self._change_characters_folder)
        self.select_view.refresh_requested.connect(self.refresh_library)
        self.select_view.open_github_requested.connect(self.show_github_manager)
        self.select_view.open_homebrew_requested.connect(self.open_homebrew_editor)

        # Screen 1: GitHub & 5e.tools Content Manager
        self.github_view = GitHubContentView(self.custom_dir)
        self.github_view.back_requested.connect(self.show_character_select)
        self.github_view.import_local_folder_requested.connect(self.import_custom_folder)
        self.github_view.show_duplicates_requested.connect(self.show_duplicates_dialog)
        self.github_view.open_homebrew_requested.connect(self.open_homebrew_editor)
        self.github_view.content_changed.connect(self._on_github_content_changed)

        # Screen 2: 10-Tab Clickable Character Builder
        self.builder_view = self._build_builder_screen()

        # Screen 3: Standalone Companion Sheet & Editor (.dndcomp)
        self._editing_attached_companion_idx: Optional[int] = None
        self.companion_view = CompanionEditorView()
        self.companion_view.set_characters_dir(self._characters_dir())
        self.companion_view.back_requested.connect(self._on_companion_back)
        self.companion_view.saved.connect(self._on_companion_saved)
        self.companion_view.deleted.connect(lambda _p: self.refresh_library())

        self.screen_stack.addWidget(self.select_view)
        self.screen_stack.addWidget(self.github_view)
        self.screen_stack.addWidget(self.builder_view)
        self.screen_stack.addWidget(self.companion_view)
        ensure_widgets_fit(self)
        self._update_status_summary()

    def apply_theme(self, theme: str, persist: bool = True) -> None:
        normalized = "light" if str(theme).lower() == "light" else "dark"
        self.config.theme = normalized
        self.setStyleSheet(get_stylesheet(normalized, self.config.ui_scale))
        if hasattr(self, "title_bar"):
            self.title_bar.set_theme_icon(normalized)
        refresh_themed_icons(self, normalized)
        if hasattr(self, "select_view") and hasattr(self.select_view, "set_theme"):
            self.select_view.set_theme(normalized)
        if persist:
            save_config(self.config, self.config_path)

    def toggle_theme(self) -> None:
        next_theme = "light" if self.config.theme == "dark" else "dark"
        self.apply_theme(next_theme, persist=True)

    def _step_scale_stage(self, step: int) -> None:
        cur_idx = get_zoom_stage_index(self.config.ui_scale)
        nxt_idx = max(0, min(len(UI_ZOOM_STAGES) - 1, cur_idx + step))
        self.apply_scale(UI_ZOOM_STAGES[nxt_idx][0], persist=True)

    def _on_scale_stage_selected(self, idx: int) -> None:
        val = self.title_bar.cmb_scale_stage.itemData(idx)
        if val is not None:
            self.apply_scale(float(val), persist=True)

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

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if not self.isMaximized():
            edges = self._edge_at(event.position().toPoint())
            if edges != self._last_resize_edge:
                self._last_resize_edge = edges
                if edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif edges in (Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.Edge.LeftEdge | Qt.Edge.BottomEdge):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                elif edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                else:
                    self.unsetCursor()
        elif self._last_resize_edge:
            self._last_resize_edge = Qt.Edge(0)
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def apply_scale(self, scale: float, persist: bool = True) -> None:
        clamped = snap_ui_scale(scale)
        self.config.ui_scale = clamped
        if self._applied_scale is not None and abs(clamped - self._applied_scale) < 1e-6:
            if hasattr(self, "title_bar"):
                self.title_bar.set_scale_value(clamped)
            if persist:
                save_config(self.config, self.config_path)
            return
        self._applied_scale = clamped
        set_global_ui_scale(QApplication.instance(), clamped)
        self.setUpdatesEnabled(False)
        try:
            self.setStyleSheet(get_stylesheet(self.config.theme, clamped))
            if hasattr(self, "title_bar"):
                self.title_bar.set_scale_value(clamped)
            self._rescale_fixed_widgets(clamped)
            refresh_spinbox_margins(self, clamped)
            if hasattr(self, "select_view") and hasattr(self.select_view, "set_ui_scale"):
                if self.screen_stack.currentWidget() is self.select_view:
                    self.select_view.set_ui_scale(clamped)
                    self._select_view_scale_dirty = False
                else:
                    self._select_view_scale_dirty = True
        finally:
            self.setUpdatesEnabled(True)
        if persist:
            save_config(self.config, self.config_path)

    def _rescale_fixed_widgets(self, s: float) -> None:
        if hasattr(self, "sidebar_panel"):
            self.sidebar_panel.setMinimumWidth(round(265 * s))
            self.sidebar_panel.setMaximumWidth(round(340 * s))
        if hasattr(self, "spn_level"):
            self.spn_level.setFixedWidth(max(68, round(68 * s)))
        if hasattr(self, "ab_spinboxes"):
            ab_w = max(68, round(68 * s))
            for spn in self.ab_spinboxes.values():
                spn.setFixedWidth(ab_w)
        if hasattr(self, "spn_exhaustion"):
            self.spn_exhaustion.setFixedWidth(max(84, round(84 * s)))
        if hasattr(self, "spn_xp"):
            self.spn_xp.setFixedWidth(max(132, round(132 * s)))

        row_h = max(22, round(22 * s))
        hdr_h = max(24, round(24 * s))
        if hasattr(self, "tbl_saves"):
            sh = self.tbl_saves.horizontalHeader()
            sh.setMinimumHeight(hdr_h)
            sh.setFixedHeight(hdr_h)
            self.tbl_saves.setColumnWidth(1, round(58 * s))
            self.tbl_saves.setColumnWidth(2, round(68 * s))
            vh = self.tbl_saves.verticalHeader()
            vh.setMinimumSectionSize(row_h)
            vh.setDefaultSectionSize(row_h)
            for r in range(6):
                self.tbl_saves.setRowHeight(r, row_h)
            self.tbl_saves.setFixedHeight(hdr_h + 6 * row_h + 2 * self.tbl_saves.frameWidth() + 2)
        if hasattr(self, "tbl_skills"):
            kh = self.tbl_skills.horizontalHeader()
            kh.setMinimumHeight(hdr_h)
            kh.setFixedHeight(hdr_h)
            self.tbl_skills.setColumnWidth(1, round(54 * s))
            self.tbl_skills.setColumnWidth(2, round(66 * s))
            self.tbl_skills.setColumnWidth(3, round(68 * s))
            kvh = self.tbl_skills.verticalHeader()
            kvh.setMinimumSectionSize(row_h)
            kvh.setDefaultSectionSize(row_h)
            for r in range(18):
                self.tbl_skills.setRowHeight(r, row_h)
            self.tbl_skills.setFixedHeight(hdr_h + 18 * row_h + 2 * self.tbl_skills.frameWidth() + 2)

        if hasattr(self, "tbl_spell_catalog"):
            self.tbl_spell_catalog.verticalHeader().setDefaultSectionSize(max(30, round(34 * s)))
            self.tbl_spell_catalog.setColumnWidth(1, round(68 * s))
            self.tbl_spell_catalog.setColumnWidth(2, round(138 * s))
            self.tbl_spell_catalog.setColumnWidth(3, round(76 * s))
        if hasattr(self, "tbl_equip_catalog"):
            self.tbl_equip_catalog.verticalHeader().setDefaultSectionSize(max(32, round(36 * s)))
            self.tbl_equip_catalog.setColumnWidth(0, round(54 * s))
            self.tbl_equip_catalog.setColumnWidth(2, round(98 * s))
            self.tbl_equip_catalog.setColumnWidth(3, round(78 * s))
            self.tbl_equip_catalog.setColumnWidth(4, round(88 * s))
        if hasattr(self, "tbl_inventory"):
            inv_h = max(42, round(42 * s))
            col2_w = max(96, round(96 * s))
            for r in range(self.tbl_inventory.rowCount()):
                cw = self.tbl_inventory.cellWidget(r, 2)
                if cw is not None:
                    cw.setMinimumWidth(max(84, round(84 * s)))
                    inv_h = max(inv_h, cw.sizeHint().height() + 6)
                    col2_w = max(col2_w, cw.sizeHint().width() + 8)
            inv_vh = self.tbl_inventory.verticalHeader()
            inv_vh.setMinimumSectionSize(inv_h)
            inv_vh.setDefaultSectionSize(inv_h)
            self.tbl_inventory.setColumnWidth(2, col2_w)
            for r in range(self.tbl_inventory.rowCount()):
                self.tbl_inventory.setRowHeight(r, inv_h)
        if hasattr(self, "tbl_spells"):
            sp_h = max(34, round(34 * s))
            for r in range(self.tbl_spells.rowCount()):
                cw = self.tbl_spells.cellWidget(r, 5)
                if cw is not None:
                    sp_h = max(sp_h, cw.sizeHint().height() + 6)
            sp_vh = self.tbl_spells.verticalHeader()
            sp_vh.setMinimumSectionSize(sp_h)
            sp_vh.setDefaultSectionSize(sp_h)
            for r in range(self.tbl_spells.rowCount()):
                self.tbl_spells.setRowHeight(r, sp_h)
        if hasattr(self, "tbl_hp_rolls"):
            self.tbl_hp_rolls.setColumnWidth(0, round(50 * s))
            self.tbl_hp_rolls.setColumnWidth(2, round(62 * s))
            self.tbl_hp_rolls.setColumnWidth(3, round(196 * s))
            self.tbl_hp_rolls.setColumnWidth(4, round(62 * s))
            self.tbl_hp_rolls.setColumnWidth(5, round(72 * s))
            if self.state.hp_mode == "rolled":
                self._sync_hp_panel()
        if hasattr(self, "tab_bar_scroll"):
            self.tab_bar_scroll.setFixedHeight(max(44, round(46 * s)))
        refit_buttons(self)

    def show_character_select(self) -> None:
        if not self.confirm_leave_character():
            return
        self.refresh_library()
        if self._select_view_scale_dirty and hasattr(self.select_view, "set_ui_scale"):
            self.select_view.set_ui_scale(self.config.ui_scale)
            self._select_view_scale_dirty = False
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
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
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
    # Screen 2: 10-Tab Clickable Character Builder
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

        btn_back = QPushButton("Characters")
        apply_button_icon(btn_back, "arrow-left", size=15)
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

        self.btn_rule_overrides = QPushButton("Rule Overrides")
        apply_button_icon(self.btn_rule_overrides, "settings", size=15)
        self.btn_rule_overrides.clicked.connect(self.open_rule_overrides_dialog)
        self.btn_level_up = QPushButton("Level Up")
        apply_button_icon(self.btn_level_up, "arrow-up-circle", size=15)
        self.btn_level_up.clicked.connect(self.open_level_up_wizard)
        self.btn_planner = QPushButton("Build Planner")
        self.btn_planner.clicked.connect(self.open_build_planner)
        self.btn_homebrew = QPushButton("Homebrew")
        self.btn_homebrew.clicked.connect(self.open_homebrew_editor)
        btn_bundle = QPushButton("Export Bundle")
        btn_bundle.clicked.connect(self.export_bundle_dialog)
        btn_save = QPushButton("Save")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.clicked.connect(self.save_character)
        btn_pdf = QPushButton("Export Official PDF")
        btn_pdf.clicked.connect(self.export_pdf_dialog)
        btn_gh = QPushButton("Content (GitHub / 5e.tools)")
        btn_gh.clicked.connect(self.show_github_manager)

        tb_layout.addWidget(self.btn_rule_overrides)
        tb_layout.addWidget(self.btn_level_up)
        tb_layout.addWidget(self.btn_planner)
        tb_layout.addWidget(self.btn_homebrew)
        tb_layout.addWidget(btn_bundle)
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

        self.tab_race = _CatalogSelectorTab(
            self.repo,
            "Race",
            "Race",
            on_select_id=self.select_race_by_id,
            on_clear_id=lambda: self.select_race_by_id(""),
        )

        cls_top_widget = QWidget()
        cls_top_v = QVBoxLayout(cls_top_widget)
        cls_top_v.setContentsMargins(0, 0, 0, 0)
        cls_top_v.setSpacing(8)

        clw = QHBoxLayout()
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
        self.spn_level.setFixedWidth(68)
        self.spn_level.valueChanged.connect(self._on_level_changed)
        btn_lvl_p = QPushButton("+")
        btn_lvl_p.setObjectName("StepperBtn")
        btn_lvl_p.clicked.connect(lambda: self.spn_level.setValue(min(20, self.spn_level.value() + 1)))
        self.btn_class_level_up = QPushButton("Level Up Wizard")
        apply_button_icon(self.btn_class_level_up, "arrow-up-circle", size=15)
        self.btn_class_level_up.clicked.connect(self.open_level_up_wizard)
        clw.addWidget(btn_lvl_m)
        clw.addWidget(self.spn_level)
        clw.addWidget(btn_lvl_p)
        clw.addSpacing(8)
        clw.addWidget(self.btn_class_level_up)
        clw.addStretch()
        cls_top_v.addLayout(clw)

        self.multiclass_group = QGroupBox("Classes && Multiclassing")
        mc_v = QVBoxLayout(self.multiclass_group)
        mc_v.setContentsMargins(8, 8, 8, 8)
        mc_v.setSpacing(6)
        self.multiclass_rows_layout = QVBoxLayout()
        self.multiclass_rows_layout.setSpacing(4)
        mc_v.addLayout(self.multiclass_rows_layout)

        mc_add_row = QHBoxLayout()
        self.cmb_add_multiclass = QComboBox()
        self.btn_add_multiclass = QPushButton("+ Add Multiclass")
        self.btn_add_multiclass.clicked.connect(self._on_add_multiclass_clicked)
        mc_add_row.addWidget(self.cmb_add_multiclass, 1)
        mc_add_row.addWidget(self.btn_add_multiclass)
        mc_v.addLayout(mc_add_row)
        cls_top_v.addWidget(self.multiclass_group)

        self.tab_class = _CatalogSelectorTab(
            self.repo,
            "Class",
            "Class",
            on_select_id=self.select_class_by_id,
            on_clear_id=lambda: self.select_class_by_id(""),
            extra_top_widget=cls_top_widget,
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
        pick_row.setSpacing(6)
        lbl_p2 = QLabel("+2:")
        lbl_p2.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.cmb_asi_plus2 = QComboBox()
        configure_dropdown_combo(self.cmb_asi_plus2, max_visible=10)
        self.cmb_asi_plus2.currentIndexChanged.connect(self._on_bg_asi_combo_changed)
        lbl_p1 = QLabel("+1:")
        lbl_p1.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.cmb_asi_plus1 = QComboBox()
        configure_dropdown_combo(self.cmb_asi_plus1, max_visible=10)
        self.cmb_asi_plus1.currentIndexChanged.connect(self._on_bg_asi_combo_changed)
        pick_row.addWidget(lbl_p2)
        pick_row.addWidget(self.cmb_asi_plus2, 1)
        pick_row.addSpacing(12)
        pick_row.addWidget(lbl_p1)
        pick_row.addWidget(self.cmb_asi_plus1, 1)
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
            ("Choices && Feats", self._build_tab_choices_feats()),
            ("Skills && Features", self._build_tab_skills_features()),
            ("Equipment", self._build_tab_equipment()),
            ("Spells", self._build_tab_spells()),
            ("Details && Notes", self._build_tab_notes()),
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
        self.tab_bar_scroll = QScrollArea()
        self.tab_bar_scroll.setWidgetResizable(True)
        self.tab_bar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tab_bar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tab_bar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tab_bar_scroll.setWidget(tab_bar)
        self.tab_bar_scroll.setFixedHeight(max(44, tab_bar.sizeHint().height() + 4))
        root_layout.addWidget(self.tab_bar_scroll)

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
            fit_button(btn)

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

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _show_element_description(self, el: Element, browser: QTextBrowser) -> None:
        resolved = getattr(self.computed, "resolved_descriptions", {}).get(el.id, "")
        body = resolved or el.description_html or el.sheet_description or "<p>No description available.</p>"
        html_doc = f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>{el.type} — {el.source}</p>{body}"
        browser.setHtml(html_doc)

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

    def _set_combo_by_data(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)
