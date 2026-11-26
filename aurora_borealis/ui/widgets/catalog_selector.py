"""Reusable clickable catalog selector tab with source filter and scoped choices."""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...loader import ContentRepository
from ...models import Element


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

        filter_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(f"Search {title.lower()}…")
        self.txt_search.textChanged.connect(self.refresh_list)
        self.cmb_source = QComboBox()
        self.cmb_source.addItem("All Sources", "")
        self.cmb_source.currentIndexChanged.connect(self.refresh_list)
        filter_row.addWidget(self.txt_search, 2)
        filter_row.addWidget(self.cmb_source, 1)
        left_l.addLayout(filter_row)

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
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.choices_scroll = scroll
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

        self.refresh_sources()
        self.refresh_list()

    def set_title(self, title: str) -> None:
        self.title = title
        self.choices_group.setTitle(f"{title} Choices")
        self.txt_search.setPlaceholderText(f"Search {title.lower()}…")

    def refresh_sources(self) -> None:
        prev = self.cmb_source.currentData() or ""
        sources = sorted(
            {
                (el.source or "").strip()
                for el in self.repo.of_type(self.element_type)
                if (el.source or "").strip()
            }
        )
        self.cmb_source.blockSignals(True)
        self.cmb_source.clear()
        self.cmb_source.addItem("All Sources", "")
        for s in sources:
            self.cmb_source.addItem(s, s)
        idx = self.cmb_source.findData(prev)
        self.cmb_source.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_source.blockSignals(False)

    def refresh_list(self) -> None:
        q = self.txt_search.text()
        src_filter = (self.cmb_source.currentData() or "").strip().lower()
        items = self.repo.search(q, [self.element_type])
        if src_filter:
            items = [el for el in items if (el.source or "").strip().lower() == src_filter]
        self.lst_items.blockSignals(True)
        self.lst_items.clear()
        for el in items:
            prefix = "✓ " if el.id == self._current_selected_id else ""
            it = QListWidgetItem(f"{prefix}{el.name}")
            it.setData(Qt.ItemDataRole.UserRole, el.id)
            if el.source:
                it.setToolTip(f"{el.name} ({el.source})")
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
            self.desc_browser.setHtml(
                f"<p>No {self.title.lower()} selected yet. Click one on the left to inspect and select it.</p>"
            )

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
