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
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..engine import parse_weight_lb
from ..loader import ContentRepository
from ..models import DuplicateEntry, Element, InventoryItem
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


_ARMOR_TEMPLATES: list[tuple[str, int]] = [
    ("Magic Armor / Shield (+1)", 1),
    ("Magic Armor / Shield (+2)", 2),
    ("Magic Armor / Shield (+3)", 3),
    ("Artificer Infusion: Enhanced Defense (+1 AC)", 1),
    ("Artificer Infusion: Enhanced Defense Lv 10+ (+2 AC)", 2),
    ("Artificer Infusion: Repulsion Shield (+1 AC)", 1),
    ("Artificer Infusion: Resistant Armor", 0),
    ("Artificer Infusion: Armor of Magical Strength", 0),
    ("Adamantine Armor", 0),
    ("Mithral Armor", 0),
    ("Armor of Gleaming", 0),
    ("Cast-Off Armor", 0),
    ("Mariner's Armor", 0),
    ("Mizzium Armor", 0),
    ("Sentinel Shield", 0),
    ("Custom Enchantment / Infusion", 0),
]

_WEAPON_TEMPLATES: list[tuple[str, int]] = [
    ("Magic Weapon (+1)", 1),
    ("Magic Weapon (+2)", 2),
    ("Magic Weapon (+3)", 3),
    ("Artificer Infusion: Enhanced Weapon (+1)", 1),
    ("Artificer Infusion: Enhanced Weapon Lv 10+ (+2)", 2),
    ("Artificer Infusion: Repeating Shot (+1)", 1),
    ("Artificer Infusion: Returning Weapon (+1)", 1),
    ("Artificer Infusion: Radiant Weapon (+1)", 1),
    ("Silvered Weapon", 0),
    ("Adamantine Weapon", 0),
    ("Vicious Weapon", 0),
    ("Weapon of Warning", 0),
    ("Flame Tongue", 0),
    ("Frost Brand", 0),
    ("Moon-Touched Weapon", 0),
    ("Custom Enchantment / Infusion", 0),
]


class MagicGearDialog(QDialog):
    """Create a magic / Artificer-infused variant of any Armor, Shield, or Weapon."""

    def __init__(
        self,
        repo: ContentRepository,
        initial_element: Optional[Element] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self._selected_base: Optional[Element] = None
        self.setWindowTitle("Create Magic / Infused Armor or Weapon")
        self.setMinimumSize(620, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top_filter = QHBoxLayout()
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems(["All (Armor & Weapons)", "Armor", "Weapon"])
        if initial_element and initial_element.type in ("Armor", "Weapon"):
            self.cmb_kind.setCurrentText(initial_element.type)
        self.cmb_kind.currentIndexChanged.connect(self._refresh_base_list)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search base armor, shield, or weapon…")
        self.txt_search.textChanged.connect(self._refresh_base_list)
        top_filter.addWidget(self.cmb_kind, 1)
        top_filter.addWidget(self.txt_search, 2)
        layout.addLayout(top_filter)

        self.lst_base = QListWidget()
        self.lst_base.currentItemChanged.connect(self._on_base_changed)
        layout.addWidget(self.lst_base, 1)

        form = QFormLayout()
        self.cmb_template = QComboBox()
        self.cmb_template.currentIndexChanged.connect(self._on_template_changed)
        form.addRow("Magic / Infusion:", self.cmb_template)

        self.spn_bonus = QSpinBox()
        self.spn_bonus.setRange(0, 3)
        self.spn_bonus.setPrefix("+")
        self.spn_bonus.valueChanged.connect(self._update_preview_name)
        form.addRow("Magic Bonus:", self.spn_bonus)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Resulting item name…")
        form.addRow("Item Name:", self.txt_name)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add to Inventory")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_base_list(initial_id=initial_element.id if initial_element else "")

    def _refresh_base_list(self, _idx: int = 0, initial_id: str = "") -> None:
        q = self.txt_search.text().strip()
        kind = self.cmb_kind.currentText()
        types = ["Armor", "Weapon"] if kind.startswith("All") else [kind]
        items = self.repo.search(q, types)
        items.sort(key=lambda e: (e.type, e.name.lower()))
        self.lst_base.clear()
        target_row = 0
        for i, el in enumerate(items[:400]):
            it = QListWidgetItem(f"[{el.type}] {el.name}")
            it.setData(Qt.ItemDataRole.UserRole, el.id)
            self.lst_base.addItem(it)
            if initial_id and el.id == initial_id:
                target_row = i
        if self.lst_base.count() > 0:
            self.lst_base.setCurrentRow(target_row)

    def _on_base_changed(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            self._selected_base = None
            return
        eid = current.data(Qt.ItemDataRole.UserRole) or ""
        self._selected_base = self.repo.get(eid)
        if self._selected_base is None:
            return
        templates = _ARMOR_TEMPLATES if self._selected_base.type == "Armor" else _WEAPON_TEMPLATES
        self.cmb_template.blockSignals(True)
        self.cmb_template.clear()
        for label, bonus in templates:
            self.cmb_template.addItem(label, bonus)
        self.cmb_template.blockSignals(False)
        self._on_template_changed(0)

    def _on_template_changed(self, _idx: int) -> None:
        bonus = self.cmb_template.currentData()
        if bonus is not None:
            self.spn_bonus.blockSignals(True)
            self.spn_bonus.setValue(int(bonus))
            self.spn_bonus.blockSignals(False)
        self._update_preview_name()

    def _update_preview_name(self) -> None:
        if self._selected_base is None:
            return
        base_name = self._selected_base.name
        tpl_label = self.cmb_template.currentText()
        bonus = self.spn_bonus.value()
        short = tpl_label.replace("Artificer Infusion: ", "").split("(")[0].strip()
        if short in ("Magic Armor / Shield", "Magic Weapon"):
            self.txt_name.setText(f"{base_name} (+{bonus})" if bonus > 0 else base_name)
        elif short == "Custom Enchantment / Infusion":
            self.txt_name.setText(f"Magic {base_name} (+{bonus})" if bonus > 0 else f"Magic {base_name}")
        else:
            suffix = f" +{bonus}" if bonus > 0 else ""
            self.txt_name.setText(f"{base_name} ({short}{suffix})")

    def build_inventory_item(self) -> Optional[InventoryItem]:
        if self._selected_base is None:
            return None
        el = self._selected_base
        name = self.txt_name.text().strip() or el.name
        return InventoryItem(
            element_id=el.id,
            name=name,
            quantity=1,
            equipped=True,
            weight=parse_weight_lb(el),
            category=el.type,
            magic_bonus=self.spn_bonus.value(),
            enchantment=self.cmb_template.currentText(),
        )
