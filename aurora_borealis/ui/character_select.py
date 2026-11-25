"""Character Selection screen backed by a configurable folder."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..library import CharacterSummary
from .dialogs import pixmap_from_portrait
from .ui_helpers import ensure_widgets_fit, fit_button


class _ClickableCard(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CharacterSelectView(QWidget):
    """Screen 1: Folder-based character selection grid."""

    open_character_requested = Signal(Path)
    open_companion_requested = Signal(Path)
    new_character_requested = Signal()
    new_companion_requested = Signal()
    import_dnd5e_requested = Signal()
    export_pdf_requested = Signal(Path)
    export_companion_pdf_requested = Signal(Path)
    duplicate_character_requested = Signal(Path)
    delete_character_requested = Signal(Path)
    toggle_favorite_requested = Signal(str)
    change_folder_requested = Signal()
    refresh_requested = Signal()
    open_github_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._summaries: list[CharacterSummary] = []
        self._filter_mode = "all"
        self._ui_scale: float = 1.0
        self._last_cols: int = 4
        self._cards: list[QWidget] = []
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._relayout_cards)
        self._trash_icon_path = Path(__file__).resolve().parent.parent / "assets" / "trash-bin.svg"  # "all" or "fav"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top Bar
        top_bar = QFrame()
        top_bar.setObjectName("TopNavBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 12, 18, 12)

        badge = QLabel()
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "aurora-borealis.svg"
        if icon_path.is_file():
            badge.setPixmap(QIcon(str(icon_path)).pixmap(34, 34))
        else:
            badge.setText("AB")
            badge.setObjectName("PortraitFrame")
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_title = QLabel("Aurora Borealis")
        lbl_title.setObjectName("TitleText")
        self.lbl_content_stats = QLabel("Character Library")
        self.lbl_content_stats.setObjectName("MutedText")
        title_box.addWidget(lbl_title)
        title_box.addWidget(self.lbl_content_stats)

        top_layout.addWidget(badge)
        top_layout.addLayout(title_box)
        top_layout.addStretch()

        self.btn_github = QPushButton("Additional Content (GitHub)")
        self.btn_github.clicked.connect(self.open_github_requested.emit)
        btn_import = QPushButton("Import .dnd5e / .dnd55e / .dndcomp")
        btn_import.clicked.connect(self.import_dnd5e_requested.emit)
        btn_new_comp = QPushButton("+ New Companion")
        btn_new_comp.clicked.connect(self.new_companion_requested.emit)
        btn_new = QPushButton("+ New Character")
        btn_new.setObjectName("PrimaryBtn")
        btn_new.clicked.connect(self.new_character_requested.emit)

        top_layout.addWidget(self.btn_github)
        top_layout.addWidget(btn_import)
        top_layout.addWidget(btn_new_comp)
        top_layout.addWidget(btn_new)
        root.addWidget(top_bar)

        # Folder & Filter Bar
        sub_bar = QFrame()
        sub_bar.setObjectName("SubBar")
        sub_layout = QHBoxLayout(sub_bar)
        sub_layout.setContentsMargins(18, 10, 18, 10)

        sub_layout.addWidget(QLabel("Characters Folder:"))
        self.lbl_folder = QLabel("")
        self.lbl_folder.setObjectName("FolderChip")
        btn_change = QPushButton("Change Folder…")
        btn_change.clicked.connect(self.change_folder_requested.emit)
        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.clicked.connect(self.refresh_requested.emit)

        sub_layout.addWidget(self.lbl_folder)
        sub_layout.addWidget(btn_change)
        sub_layout.addWidget(btn_refresh)
        sub_layout.addStretch()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search characters by name, class, race…")
        self.txt_search.setMinimumWidth(240)
        self.txt_search.textChanged.connect(self._render_cards)

        self.btn_all = QPushButton("All (0)")
        self.btn_all.setObjectName("PrimaryBtn")
        self.btn_all.clicked.connect(lambda: self._set_filter("all"))
        self.btn_fav = QPushButton("★ Favorites (0)")
        self.btn_fav.clicked.connect(lambda: self._set_filter("fav"))
        self.btn_comp = QPushButton("🐾 Companions (0)")
        self.btn_comp.clicked.connect(lambda: self._set_filter("comp"))

        sub_layout.addWidget(self.txt_search)
        sub_layout.addWidget(self.btn_all)
        sub_layout.addWidget(self.btn_fav)
        sub_layout.addWidget(self.btn_comp)
        root.addWidget(sub_bar)

        # Scrollable Character Grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(18, 18, 18, 18)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.grid_host)
        root.addWidget(self.scroll_area, 1)
        ensure_widgets_fit(self)

    def set_header_info(
        self,
        folder_path: str,
        element_count: int,
        dup_count: int,
        index_count: int,
    ) -> None:
        self.lbl_folder.setText(folder_path)
        dup_part = f" • {dup_count} duplicates" if dup_count else ""
        self.lbl_content_stats.setText(
            f"Character Library • {element_count} loaded elements{dup_part}"
        )
        self.btn_github.setText(f"Additional Content (GitHub: {index_count})")
        fit_button(self.btn_github)

    def set_characters(self, summaries: list[CharacterSummary]) -> None:
        self._summaries = list(summaries)
        fav_count = sum(1 for s in summaries if s.favorite)
        comp_count = sum(1 for s in summaries if s.entry_kind == "companion")
        self.btn_all.setText(f"All ({len(summaries)})")
        self.btn_fav.setText(f"★ Favorites ({fav_count})")
        self.btn_comp.setText(f"🐾 Companions ({comp_count})")
        fit_button(self.btn_all)
        fit_button(self.btn_fav)
        fit_button(self.btn_comp)
        self._render_cards()

    def _set_filter(self, mode: str) -> None:
        self._filter_mode = mode
        self.btn_all.setObjectName("PrimaryBtn" if mode == "all" else "")
        self.btn_fav.setObjectName("PrimaryBtn" if mode == "fav" else "")
        self.btn_comp.setObjectName("PrimaryBtn" if mode == "comp" else "")
        for btn in (self.btn_all, self.btn_fav, self.btn_comp):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._render_cards()

    def set_ui_scale(self, scale: float) -> None:
        clamped = max(0.85, min(1.5, float(scale)))
        if abs(clamped - self._ui_scale) < 1e-4:
            return
        self._ui_scale = clamped
        self._render_cards()

    def _card_size(self) -> int:
        return round(284 * self._ui_scale)

    def _compute_columns(self) -> int:
        card_sz = self._card_size()
        spacing = self.grid.horizontalSpacing()
        if spacing < 0:
            spacing = 16
        avail = max(card_sz, self.scroll_area.viewport().width() - 36)
        return max(1, (avail + spacing) // (card_sz + spacing))

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cols = self._compute_columns()
        if cols != self._last_cols:
            self._resize_timer.start()

    def _relayout_cards(self) -> None:
        cols = self._compute_columns()
        if cols == self._last_cols and self.grid.count() == len(self._cards):
            return
        self._last_cols = cols
        self.grid_host.setUpdatesEnabled(False)
        while self.grid.count():
            self.grid.takeAt(0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for idx, card in enumerate(self._cards):
            r, c = divmod(idx, cols)
            self.grid.addWidget(card, r, c)
        ensure_widgets_fit(self.grid_host)
        self.grid_host.setUpdatesEnabled(True)

    def _render_cards(self) -> None:
        self.grid_host.setUpdatesEnabled(False)
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._cards.clear()

        q = self.txt_search.text().strip().lower()
        filtered: list[CharacterSummary] = []
        for s in self._summaries:
            if self._filter_mode == "fav" and not s.favorite:
                continue
            if self._filter_mode == "comp" and s.entry_kind != "companion":
                continue
            if q and q not in f"{s.name} {s.race} {s.class_name} {s.background} {s.ruleset}".lower():
                continue
            filtered.append(s)

        card_sz = self._card_size()
        cols = self._compute_columns()
        self._last_cols = cols
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        for summary in filtered:
            self._cards.append(self._make_card(summary, card_sz))

        # Dashed "+ Create New Character" square card at the end
        new_btn = QPushButton("+\n\nNew Character\n5e / 5.5e")
        new_btn.setObjectName("NewCharDashedCard")
        new_btn.setFixedSize(card_sz, card_sz)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.new_character_requested.emit)
        self._cards.append(new_btn)

        for idx, card in enumerate(self._cards):
            r, c = divmod(idx, cols)
            self.grid.addWidget(card, r, c)
        ensure_widgets_fit(self.grid_host)
        self.grid_host.setUpdatesEnabled(True)

    def _make_card(self, s: CharacterSummary, card_sz: int) -> QFrame:
        is_comp = s.entry_kind == "companion"
        open_sig = self.open_companion_requested if is_comp else self.open_character_requested
        pdf_sig = self.export_companion_pdf_requested if is_comp else self.export_pdf_requested

        card = _ClickableCard()
        card.setObjectName("CharCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.clicked.connect(lambda: open_sig.emit(s.path))
        card.setFixedSize(card_sz, card_sz)

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(0, 0, 0, 10)
        vbox.setSpacing(6)

        # Main portrait square-ish area (~60% of the card height)
        portrait_h = round(card_sz * 0.58)
        portrait_btn = QPushButton()
        portrait_btn.setObjectName("CharPortraitBtn")
        portrait_btn.setFixedHeight(portrait_h)
        portrait_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        portrait_btn.clicked.connect(lambda: open_sig.emit(s.path))

        pix = pixmap_from_portrait(s.portrait_base64, s.portrait_path, size=card_sz)
        if pix:
            scaled = pix.scaled(
                card_sz - 2,
                portrait_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x_off = max(0, (scaled.width() - (card_sz - 2)) // 2)
            y_off = max(0, (scaled.height() - portrait_h) // 2)
            cropped = scaled.copy(x_off, y_off, card_sz - 2, portrait_h)
            portrait_btn.setIcon(QIcon(cropped))
            portrait_btn.setIconSize(QSize(card_sz - 2, portrait_h))
        else:
            initials = (s.name[:2] or "AB").upper()
            portrait_btn.setText(initials)

        # Overlay top bar inside portrait area (Ruleset pill + Favorite star)
        overlay = QHBoxLayout(portrait_btn)
        overlay.setContentsMargins(8, 8, 8, 8)
        overlay.setAlignment(Qt.AlignmentFlag.AlignTop)

        pill = QLabel(s.ruleset or "5e")
        pill.setObjectName("RulesetPill")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_fav = QPushButton("★" if s.favorite else "☆")
        btn_fav.setObjectName("FavBtn")
        btn_fav.setProperty("fav", "true" if s.favorite else "false")
        btn_fav.setFixedSize(28, 28)
        btn_fav.clicked.connect(lambda: self.toggle_favorite_requested.emit(s.filename))

        overlay.addWidget(pill)
        overlay.addStretch()
        overlay.addWidget(btn_fav)
        vbox.addWidget(portrait_btn)

        # Compact info + actions footer
        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(10, 0, 10, 0)
        body_l.setSpacing(4)

        lbl_name = QLabel(s.name)
        lbl_name.setObjectName("TitleText")
        lbl_name.setWordWrap(False)
        subtitle = f"Lv {s.level} {s.race or '—'} {s.class_name or '—'}".strip()
        lbl_sub = QLabel(subtitle)
        lbl_sub.setObjectName("MutedText")
        body_l.addWidget(lbl_name)
        body_l.addWidget(lbl_sub)

        footer = QHBoxLayout()
        footer.setSpacing(4)

        btn_open = QPushButton("Open")
        btn_open.setObjectName("PrimaryBtn")
        btn_open.clicked.connect(lambda: open_sig.emit(s.path))

        btn_pdf = QPushButton("PDF")
        btn_pdf.setObjectName("CompactCardBtn")
        btn_pdf.clicked.connect(lambda: pdf_sig.emit(s.path))

        btn_dup = QPushButton("Copy")
        btn_dup.setObjectName("CompactCardBtn")
        btn_dup.clicked.connect(lambda: self.duplicate_character_requested.emit(s.path))

        btn_del = QPushButton()
        btn_del.setObjectName("TrashBtn")
        btn_del.setToolTip("Delete Character")
        if self._trash_icon_path.is_file():
            btn_del.setIcon(QIcon(str(self._trash_icon_path)))
            icon_px = max(16, round(18 * self._ui_scale))
            btn_del.setIconSize(QSize(icon_px, icon_px))
        else:
            btn_del.setText("🗑")
        btn_del.clicked.connect(lambda: self.delete_character_requested.emit(s.path))

        footer.addWidget(btn_open, 1)
        footer.addWidget(btn_pdf)
        footer.addWidget(btn_dup)
        footer.addWidget(btn_del)
        body_l.addLayout(footer)
        vbox.addWidget(body, 1)
        return card
