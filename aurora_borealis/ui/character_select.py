"""Character Selection screen backed by a configurable folder."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
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


class _ClickableCard(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CharacterSelectView(QWidget):
    """Screen 1: Folder-based character selection grid."""

    open_character_requested = Signal(Path)
    new_character_requested = Signal()
    import_dnd5e_requested = Signal()
    export_pdf_requested = Signal(Path)
    duplicate_character_requested = Signal(Path)
    delete_character_requested = Signal(Path)
    toggle_favorite_requested = Signal(str)
    change_folder_requested = Signal()
    refresh_requested = Signal()
    open_github_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._summaries: list[CharacterSummary] = []
        self._filter_mode = "all"  # "all" or "fav"
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

        badge = QLabel("AB")
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            "background-color:#2b6cb0; color:#ffffff; border-radius:8px; font-weight:bold;"
        )
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_title = QLabel("Aurora Borealis")
        lbl_title.setStyleSheet("font-size:12pt; font-weight:bold; color:#ffffff;")
        self.lbl_content_stats = QLabel("Character Library")
        self.lbl_content_stats.setStyleSheet("font-size:8.5pt; color:#94a3b8;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(self.lbl_content_stats)

        top_layout.addWidget(badge)
        top_layout.addLayout(title_box)
        top_layout.addStretch()

        self.btn_github = QPushButton("Additional Content (GitHub)")
        self.btn_github.clicked.connect(self.open_github_requested.emit)
        btn_import = QPushButton("Import .dnd5e")
        btn_import.clicked.connect(self.import_dnd5e_requested.emit)
        btn_new = QPushButton("+ New Character")
        btn_new.setObjectName("PrimaryBtn")
        btn_new.clicked.connect(self.new_character_requested.emit)

        top_layout.addWidget(self.btn_github)
        top_layout.addWidget(btn_import)
        top_layout.addWidget(btn_new)
        root.addWidget(top_bar)

        # Folder & Filter Bar
        sub_bar = QFrame()
        sub_bar.setObjectName("SubBar")
        sub_layout = QHBoxLayout(sub_bar)
        sub_layout.setContentsMargins(18, 10, 18, 10)

        sub_layout.addWidget(QLabel("Characters Folder:"))
        self.lbl_folder = QLabel("")
        self.lbl_folder.setStyleSheet(
            "background-color:#0b1017; border:1px solid #28364b; border-radius:5px; "
            "padding:4px 8px; color:#7dd3fc; font-family:monospace;"
        )
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

        sub_layout.addWidget(self.txt_search)
        sub_layout.addWidget(self.btn_all)
        sub_layout.addWidget(self.btn_fav)
        root.addWidget(sub_bar)

        # Scrollable Character Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(18, 18, 18, 18)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.grid_host)
        root.addWidget(scroll, 1)

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

    def set_characters(self, summaries: list[CharacterSummary]) -> None:
        self._summaries = list(summaries)
        fav_count = sum(1 for s in summaries if s.favorite)
        self.btn_all.setText(f"All ({len(summaries)})")
        self.btn_fav.setText(f"★ Favorites ({fav_count})")
        self._render_cards()

    def _set_filter(self, mode: str) -> None:
        self._filter_mode = mode
        self.btn_all.setObjectName("PrimaryBtn" if mode == "all" else "")
        self.btn_fav.setObjectName("PrimaryBtn" if mode == "fav" else "")
        self.btn_all.style().unpolish(self.btn_all)
        self.btn_all.style().polish(self.btn_all)
        self.btn_fav.style().unpolish(self.btn_fav)
        self.btn_fav.style().polish(self.btn_fav)
        self._render_cards()

    def _render_cards(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        q = self.txt_search.text().strip().lower()
        filtered: list[CharacterSummary] = []
        for s in self._summaries:
            if self._filter_mode == "fav" and not s.favorite:
                continue
            if q and q not in f"{s.name} {s.race} {s.class_name} {s.background} {s.ruleset}".lower():
                continue
            filtered.append(s)

        cols = 3
        for idx, summary in enumerate(filtered):
            r, c = divmod(idx, cols)
            self.grid.addWidget(self._make_card(summary), r, c)

        # Dashed "+ Create New Character" card at the end
        r_new, c_new = divmod(len(filtered), cols)
        new_btn = QPushButton("+\n\nCreate New Character\nChoose 5e / 5.5e & Portrait")
        new_btn.setObjectName("NewCharDashedCard")
        new_btn.setMinimumSize(310, 185)
        new_btn.clicked.connect(self.new_character_requested.emit)
        self.grid.addWidget(new_btn, r_new, c_new)

    def _make_card(self, s: CharacterSummary) -> QFrame:
        card = _ClickableCard()
        card.setObjectName("CharCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.clicked.connect(lambda: self.open_character_requested.emit(s.path))
        card.setMinimumWidth(310)
        card.setMinimumHeight(185)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(14, 14, 14, 12)
        vbox.setSpacing(10)

        # Top row: portrait + title + favorite + ruleset pill
        top = QHBoxLayout()
        portrait_lbl = QLabel()
        portrait_lbl.setObjectName("PortraitFrame")
        portrait_lbl.setFixedSize(48, 48)
        portrait_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = pixmap_from_portrait(s.portrait_base64, s.portrait_path, size=48)
        if pix:
            portrait_lbl.setPixmap(pix)
        else:
            initials = (s.name[:2] or "AB").upper()
            portrait_lbl.setText(initials)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        lbl_name = QLabel(s.name)
        lbl_name.setStyleSheet("font-weight:bold; font-size:11pt; color:#ffffff;")
        subtitle = f"Lv {s.level} {s.race or '—'} {s.class_name or '—'}".strip()
        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet("font-size:9pt; color:#94a3b8;")
        info_col.addWidget(lbl_name)
        info_col.addWidget(lbl_sub)

        pill = QLabel(s.ruleset or "5e")
        pill.setObjectName("RulesetPill")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_fav = QPushButton("★" if s.favorite else "☆")
        btn_fav.setFixedSize(28, 28)
        btn_fav.setStyleSheet(
            f"color:{'#facc15' if s.favorite else '#64748b'}; border:none; background:transparent; font-size:13pt;"
        )
        btn_fav.clicked.connect(lambda: self.toggle_favorite_requested.emit(s.filename))

        top.addWidget(portrait_lbl)
        top.addLayout(info_col, 1)
        top.addWidget(pill)
        top.addWidget(btn_fav)
        vbox.addLayout(top)

        # Stat pills row
        stats_row = QHBoxLayout()
        for label, val in (
            ("HP", str(s.hp or "—")),
            ("AC", str(s.ac)),
            ("SPD", f"{s.speed}"),
        ):
            box = QLabel(f"<span style='color:#94a3b8;'>{label}</span> <b>{val}</b>")
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setStyleSheet(
                "background-color:#0f141d; border:1px solid #243247; border-radius:6px; padding:4px;"
            )
            stats_row.addWidget(box)
        vbox.addLayout(stats_row)

        # Footer row
        footer = QHBoxLayout()
        lbl_file = QLabel(s.filename)
        lbl_file.setStyleSheet("font-size:8.5pt; color:#64748b; font-family:monospace;")
        footer.addWidget(lbl_file, 1)

        btn_open = QPushButton("Open")
        btn_open.setObjectName("PrimaryBtn")
        btn_open.clicked.connect(lambda: self.open_character_requested.emit(s.path))

        btn_pdf = QPushButton("PDF")
        btn_pdf.clicked.connect(lambda: self.export_pdf_requested.emit(s.path))

        btn_dup = QPushButton("Copy")
        btn_dup.clicked.connect(lambda: self.duplicate_character_requested.emit(s.path))

        btn_del = QPushButton("✕")
        btn_del.setObjectName("DangerBtn")
        btn_del.setFixedWidth(30)
        btn_del.clicked.connect(lambda: self.delete_character_requested.emit(s.path))

        footer.addWidget(btn_open)
        footer.addWidget(btn_pdf)
        footer.addWidget(btn_dup)
        footer.addWidget(btn_del)
        vbox.addLayout(footer)
        return card
