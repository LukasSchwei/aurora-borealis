"""Dialogs and portrait helpers for Aurora Borealis."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..models import DuplicateEntry
from ..persistence import encode_portrait_file


def pixmap_from_portrait(
    portrait_base64: str,
    portrait_path: str = "",
    size: int = 64,
) -> Optional[QPixmap]:
    """Build a scaled QPixmap from base64 portrait data or fallback file path."""
    pix = QPixmap()
    if portrait_base64:
        try:
            raw = base64.b64decode(portrait_base64)
            pix.loadFromData(raw)
        except Exception:
            pix = QPixmap()
    if pix.isNull() and portrait_path and Path(portrait_path).is_file():
        pix.load(portrait_path)
    if pix.isNull():
        return None
    return pix.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )


class NewCharacterDialog(QDialog):
    """Modal dialog for creating a new character with 5e/5.5e ruleset and portrait."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create New Character")
        self.setMinimumWidth(440)
        self.portrait_path = ""
        self.portrait_base64 = ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.txt_name = QLineEdit("New Adventurer")
        self.txt_name.selectAll()
        form.addRow("Character Name:", self.txt_name)

        # Ruleset selection (5e vs 5.5e)
        rs_box = QVBoxLayout()
        self.rad_5e = QRadioButton("D&D 5e (2014) — Classic racial ability bonuses & feats")
        self.rad_55e = QRadioButton("D&D 5.5e (2024 Revised) — Background ASI (+2/+1) & Origin Feat")
        self.rad_5e.setChecked(True)
        self._rs_group = QButtonGroup(self)
        self._rs_group.addButton(self.rad_5e)
        self._rs_group.addButton(self.rad_55e)
        rs_box.addWidget(self.rad_5e)
        rs_box.addWidget(self.rad_55e)
        form.addRow("Ruleset:", rs_box)

        # Portrait picker + preview
        port_row = QHBoxLayout()
        self.lbl_preview = QLabel("No Image")
        self.lbl_preview.setObjectName("PortraitFrame")
        self.lbl_preview.setFixedSize(72, 72)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_col = QVBoxLayout()
        btn_pick = QPushButton("Choose Portrait…")
        btn_pick.clicked.connect(self._pick_portrait)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_portrait)
        btn_col.addWidget(btn_pick)
        btn_col.addWidget(btn_clear)
        btn_col.addStretch()

        port_row.addWidget(self.lbl_preview)
        port_row.addLayout(btn_col)
        port_row.addStretch()
        form.addRow("Portrait:", port_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_portrait(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Character Portrait",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if not path:
            return
        self.portrait_path = path
        self.portrait_base64 = encode_portrait_file(Path(path))
        pix = pixmap_from_portrait(self.portrait_base64, self.portrait_path, size=72)
        if pix:
            self.lbl_preview.setPixmap(pix)

    def _clear_portrait(self) -> None:
        self.portrait_path = ""
        self.portrait_base64 = ""
        self.lbl_preview.clear()
        self.lbl_preview.setText("No Image")

    def selected_name(self) -> str:
        return self.txt_name.text().strip() or "New Adventurer"

    def selected_ruleset(self) -> str:
        return "5.5e" if self.rad_55e.isChecked() else "5e"


class DuplicateReportDialog(QDialog):
    """Displays duplicate elements detected when loading Aurora XML sources."""

    def __init__(self, duplicates: list[DuplicateEntry], parent=None) -> None:
        super().__init__(parent)
        self.duplicates = duplicates
        self.setWindowTitle(f"Duplicate Content Check ({len(duplicates)} found)")
        self.resize(860, 480)

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        summary = QLabel(
            f"Detected {len(duplicates)} duplicate element entries across loaded XML files. "
            "Higher-priority sources (e.g., official books over SRD) are kept automatically."
        )
        summary.setWordWrap(True)
        top_row.addWidget(summary, 1)

        self.cmb_type = QComboBox()
        self.cmb_type.addItem("All Types", "")
        for t in sorted({d.element_type for d in duplicates}):
            self.cmb_type.addItem(t, t)
        self.cmb_type.currentIndexChanged.connect(self._populate)
        top_row.addWidget(self.cmb_type)
        layout.addLayout(top_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Kind", "Type", "Name", "Kept Source", "Duplicate Source"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._populate()

    def _populate(self) -> None:
        filter_type = self.cmb_type.currentData() or ""
        rows = [
            d
            for d in self.duplicates
            if not filter_type or d.element_type == filter_type
        ]
        self.table.setRowCount(len(rows))
        for r, d in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(d.kind.upper()))
            self.table.setItem(r, 1, QTableWidgetItem(d.element_type))
            self.table.setItem(r, 2, QTableWidgetItem(d.name))
            self.table.setItem(r, 3, QTableWidgetItem(d.kept_source or "—"))
            self.table.setItem(r, 4, QTableWidgetItem(d.duplicate_source or "—"))
