"""Visual Homebrew XML Editor Dialog (GUI -> Aurora XML) (3.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..homebrew import (
    HOMEBREW_ELEMENT_TYPES,
    build_homebrew_element,
    list_homebrew_files,
    make_homebrew_id,
    parse_homebrew_file_to_specs,
    save_homebrew_pack,
    serialize_homebrew_elements,
    validate_homebrew_xml,
)
from .ui_helpers import ensure_widgets_fit


class HomebrewEditorDialog(QDialog):
    """GUI wizard & XML validator for creating Aurora XML homebrew packs."""

    def __init__(self, custom_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.custom_dir = Path(custom_dir)
        self.saved_path: Optional[Path] = None
        self._specs: list[dict] = []
        self._current_idx: int = -1
        self._syncing = False

        self.setWindowTitle("Visual Homebrew XML Editor")
        self.setMinimumSize(940, 640)
        self._build_ui()
        self._add_new_element()
        ensure_widgets_fit(self)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Pack File:"))
        self.txt_filename = QLineEdit("my_homebrew")
        self.txt_filename.setPlaceholderText("filename (saved as custom/homebrew/<name>.xml)")
        self.cmb_existing = QComboBox()
        self.cmb_existing.addItem("— Load Existing Pack —", "")
        for p in list_homebrew_files(self.custom_dir):
            self.cmb_existing.addItem(p.name, str(p))
        btn_load = QPushButton("Load")
        btn_load.clicked.connect(self._load_selected_pack)
        top_bar.addWidget(self.txt_filename, 1)
        top_bar.addWidget(self.cmb_existing, 1)
        top_bar.addWidget(btn_load)
        root.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Elements in this pack
        left_w = QWidget()
        ll = QVBoxLayout(left_w)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("<b>Pack Elements</b>"))
        self.lst_elements = QListWidget()
        self.lst_elements.currentRowChanged.connect(self._on_row_selected)
        ll.addWidget(self.lst_elements, 1)
        l_btns = QHBoxLayout()
        btn_add = QPushButton("+ New")
        btn_add.clicked.connect(self._add_new_element)
        btn_del = QPushButton("Remove")
        btn_del.clicked.connect(self._remove_current_element)
        l_btns.addWidget(btn_add)
        l_btns.addWidget(btn_del)
        ll.addLayout(l_btns)
        splitter.addWidget(left_w)

        # Middle: Structured Form
        mid_w = QWidget()
        ml = QVBoxLayout(mid_w)
        ml.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(list(HOMEBREW_ELEMENT_TYPES))
        self.cmb_type.currentIndexChanged.connect(self._on_form_edited)
        self.txt_name = QLineEdit()
        self.txt_name.textChanged.connect(self._on_form_edited)
        self.txt_source = QLineEdit("Homebrew")
        self.txt_source.textChanged.connect(self._on_form_edited)
        self.txt_id = QLineEdit()
        self.txt_id.setPlaceholderText("Auto-generated if left blank")
        self.txt_id.textChanged.connect(self._on_form_edited)
        self.txt_supports = QLineEdit()
        self.txt_supports.setPlaceholderText("e.g. Wizard, Ritual  or  Fighter (for Archetype)")
        self.txt_supports.textChanged.connect(self._on_form_edited)
        form.addRow("Element Type:", self.cmb_type)
        form.addRow("Name:", self.txt_name)
        form.addRow("Source:", self.txt_source)
        form.addRow("Element ID:", self.txt_id)
        form.addRow("Supports:", self.txt_supports)
        ml.addLayout(form)

        # Type-specific quick setters
        set_grp = QGroupBox("Type Properties / Setters")
        sf = QFormLayout(set_grp)
        row_sp = QHBoxLayout()
        self.spn_spell_lvl = QSpinBox()
        self.spn_spell_lvl.setRange(0, 9)
        self.spn_spell_lvl.valueChanged.connect(self._on_form_edited)
        self.cmb_spell_school = QComboBox()
        self.cmb_spell_school.addItems(
            ["Evocation", "Abjuration", "Conjuration", "Divination", "Enchantment", "Illusion", "Necromancy", "Transmutation"]
        )
        self.cmb_spell_school.currentIndexChanged.connect(self._on_form_edited)
        self.chk_ritual = QCheckBox("Ritual")
        self.chk_ritual.stateChanged.connect(self._on_form_edited)
        row_sp.addWidget(QLabel("Spell Lv:"))
        row_sp.addWidget(self.spn_spell_lvl)
        row_sp.addWidget(self.cmb_spell_school)
        row_sp.addWidget(self.chk_ritual)
        self._spell_row_w = QWidget()
        self._spell_row_w.setLayout(row_sp)
        sf.addRow("Spell:", self._spell_row_w)

        row_eq = QHBoxLayout()
        self.txt_damage = QLineEdit()
        self.txt_damage.setPlaceholderText("e.g. 1d8")
        self.txt_damage.textChanged.connect(self._on_form_edited)
        self.txt_ac = QLineEdit()
        self.txt_ac.setPlaceholderText("AC e.g. 15")
        self.txt_ac.textChanged.connect(self._on_form_edited)
        self.cmb_rarity = QComboBox()
        self.cmb_rarity.addItems(["", "Common", "Uncommon", "Rare", "Very Rare", "Legendary", "Artifact"])
        self.cmb_rarity.currentIndexChanged.connect(self._on_form_edited)
        row_eq.addWidget(QLabel("Dmg:"))
        row_eq.addWidget(self.txt_damage)
        row_eq.addWidget(QLabel("AC:"))
        row_eq.addWidget(self.txt_ac)
        row_eq.addWidget(self.cmb_rarity)
        self._equip_row_w = QWidget()
        self._equip_row_w.setLayout(row_eq)
        sf.addRow("Item Stats:", self._equip_row_w)

        row_stat = QHBoxLayout()
        self.cmb_stat_name = QComboBox()
        self.cmb_stat_name.setEditable(True)
        self.cmb_stat_name.addItems(["", "ac:misc", "initiative", "innate speed", "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma", "hp"])
        self.cmb_stat_name.currentTextChanged.connect(self._on_form_edited)
        self.txt_stat_val = QLineEdit()
        self.txt_stat_val.setPlaceholderText("Value e.g. 2 or 30")
        self.txt_stat_val.textChanged.connect(self._on_form_edited)
        row_stat.addWidget(self.cmb_stat_name, 1)
        row_stat.addWidget(self.txt_stat_val, 1)
        sf.addRow("Stat Bonus:", row_stat)
        ml.addWidget(set_grp)

        ml.addWidget(QLabel("Description:"))
        self.txt_desc = QPlainTextEdit()
        self.txt_desc.setPlaceholderText("Describe the race, feat, spell, subclass, or item…")
        self.txt_desc.textChanged.connect(self._on_form_edited)
        ml.addWidget(self.txt_desc, 1)

        row_sheet = QHBoxLayout()
        self.cmb_sheet_action = QComboBox()
        self.cmb_sheet_action.addItems(["", "Action", "Bonus Action", "Reaction", "Special"])
        self.cmb_sheet_action.currentIndexChanged.connect(self._on_form_edited)
        self.txt_sheet_usage = QLineEdit()
        self.txt_sheet_usage.setPlaceholderText("Usage e.g. 1/Short Rest")
        self.txt_sheet_usage.textChanged.connect(self._on_form_edited)
        row_sheet.addWidget(QLabel("Action:"))
        row_sheet.addWidget(self.cmb_sheet_action)
        row_sheet.addWidget(QLabel("Usage:"))
        row_sheet.addWidget(self.txt_sheet_usage, 1)
        ml.addLayout(row_sheet)
        splitter.addWidget(mid_w)

        # Right: Live XML Preview & Validation
        right_w = QWidget()
        rl = QVBoxLayout(right_w)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("<b>Generated Aurora XML (Editable)</b>"))
        self.txt_xml = QPlainTextEdit()
        rl.addWidget(self.txt_xml, 1)
        self.lbl_valid = QLabel("Ready")
        self.lbl_valid.setWordWrap(True)
        rl.addWidget(self.lbl_valid)
        btn_validate = QPushButton("Validate XML")
        btn_validate.clicked.connect(self._validate_current)
        rl.addWidget(btn_validate)
        splitter.addWidget(right_w)

        splitter.setSizes([190, 400, 350])
        root.addWidget(splitter, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save && Reload Content")
        buttons.accepted.connect(self._on_save_clicked)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_new_element(self) -> None:
        self._specs.append(
            {
                "type": "Feat",
                "name": f"Custom Element {len(self._specs) + 1}",
                "source": "Homebrew",
                "id": "",
                "supports": "",
                "description": "",
                "sheet_action": "",
                "sheet_usage": "",
                "setters": {},
                "stats": [],
            }
        )
        self._refresh_list(select_row=len(self._specs) - 1)

    def _remove_current_element(self) -> None:
        if 0 <= self._current_idx < len(self._specs) and len(self._specs) > 1:
            self._specs.pop(self._current_idx)
            self._refresh_list(select_row=max(0, self._current_idx - 1))

    def _refresh_list(self, select_row: int = 0) -> None:
        self.lst_elements.blockSignals(True)
        self.lst_elements.clear()
        for sp in self._specs:
            self.lst_elements.addItem(f"[{sp.get('type', 'Feat')}] {sp.get('name', 'Unnamed')}")
        self.lst_elements.blockSignals(False)
        if self._specs:
            r = max(0, min(select_row, len(self._specs) - 1))
            self.lst_elements.setCurrentRow(r)
            self._on_row_selected(r)

    def _on_row_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._specs):
            return
        self._current_idx = row
        sp = self._specs[row]
        self._syncing = True
        try:
            self.cmb_type.setCurrentText(sp.get("type", "Feat"))
            self.txt_name.setText(sp.get("name", ""))
            self.txt_source.setText(sp.get("source", "Homebrew"))
            self.txt_id.setText(sp.get("id", ""))
            self.txt_supports.setText(sp.get("supports", ""))
            self.txt_desc.setPlainText(sp.get("description", ""))
            self.cmb_sheet_action.setCurrentText(sp.get("sheet_action", ""))
            self.txt_sheet_usage.setText(sp.get("sheet_usage", ""))

            setters = sp.get("setters") or {}
            lvl_raw = str(setters.get("level", "0"))
            self.spn_spell_lvl.setValue(int(lvl_raw) if lvl_raw.isdigit() else 0)
            if setters.get("school"):
                self.cmb_spell_school.setCurrentText(str(setters["school"]))
            self.chk_ritual.setChecked(str(setters.get("isRitual", "")).lower() == "true")
            self.txt_damage.setText(str(setters.get("damage", "")))
            self.txt_ac.setText(str(setters.get("armorClass", "")))
            self.cmb_rarity.setCurrentText(str(setters.get("rarity", "")))

            stats = sp.get("stats") or []
            if stats and isinstance(stats[0], dict):
                self.cmb_stat_name.setCurrentText(str(stats[0].get("name", "")))
                self.txt_stat_val.setText(str(stats[0].get("value", "")))
            else:
                self.cmb_stat_name.setCurrentText("")
                self.txt_stat_val.setText("")

            self._update_visibility()
        finally:
            self._syncing = False
        self._rebuild_xml_preview()

    def _update_visibility(self) -> None:
        et = self.cmb_type.currentText()
        self._spell_row_w.setVisible(et == "Spell")
        self._equip_row_w.setVisible(et in ("Weapon", "Armor", "Magic Item"))

    def _on_form_edited(self) -> None:
        if self._syncing or not (0 <= self._current_idx < len(self._specs)):
            return
        self._update_visibility()
        et = self.cmb_type.currentText()
        name = self.txt_name.text().strip() or "Custom Element"
        src = self.txt_source.text().strip() or "Homebrew"
        eid = self.txt_id.text().strip() or make_homebrew_id(et, name, src)

        setters: dict = {}
        if et == "Spell":
            setters["level"] = str(self.spn_spell_lvl.value())
            setters["school"] = self.cmb_spell_school.currentText()
            setters["isRitual"] = "true" if self.chk_ritual.isChecked() else "false"
        if et in ("Weapon", "Armor", "Magic Item"):
            if self.txt_damage.text().strip():
                setters["damage"] = self.txt_damage.text().strip()
            if self.txt_ac.text().strip():
                setters["armorClass"] = self.txt_ac.text().strip()
            if self.cmb_rarity.currentText():
                setters["rarity"] = self.cmb_rarity.currentText()

        stats = []
        st_name = self.cmb_stat_name.currentText().strip()
        st_val = self.txt_stat_val.text().strip()
        if st_name and st_val:
            stats.append({"name": st_name, "value": st_val})

        self._specs[self._current_idx] = {
            "type": et,
            "name": name,
            "source": src,
            "id": eid,
            "supports": self.txt_supports.text().strip(),
            "description": self.txt_desc.toPlainText(),
            "sheet_action": self.cmb_sheet_action.currentText(),
            "sheet_usage": self.txt_sheet_usage.text().strip(),
            "setters": setters,
            "stats": stats,
        }
        cur_item = self.lst_elements.item(self._current_idx)
        if cur_item is not None:
            cur_item.setText(f"[{et}] {name}")
        self._rebuild_xml_preview()

    def _rebuild_xml_preview(self) -> None:
        nodes = [build_homebrew_element(sp) for sp in self._specs]
        self.txt_xml.setPlainText(serialize_homebrew_elements(nodes))
        self._validate_current()

    def _validate_current(self) -> bool:
        ok, errs = validate_homebrew_xml(self.txt_xml.toPlainText())
        if ok:
            self.lbl_valid.setText(f"✓ Valid Aurora XML ({len(self._specs)} element(s))")
            self.lbl_valid.setStyleSheet("color:#4ade80; font-weight:bold;")
        else:
            self.lbl_valid.setText("✗ " + "; ".join(errs))
            self.lbl_valid.setStyleSheet("color:#f87171; font-weight:bold;")
        return ok

    def _load_selected_pack(self) -> None:
        raw_p = self.cmb_existing.currentData() or ""
        if not raw_p:
            return
        p = Path(raw_p)
        if not p.is_file():
            return
        specs = parse_homebrew_file_to_specs(p)
        if specs:
            self._specs = specs
            self.txt_filename.setText(p.stem)
            self._refresh_list(select_row=0)

    def _on_save_clicked(self) -> None:
        xml_text = self.txt_xml.toPlainText()
        ok, errs = validate_homebrew_xml(xml_text)
        if not ok:
            QMessageBox.warning(self, "Invalid Homebrew XML", "\n".join(errs))
            return
        fname = self.txt_filename.text().strip() or "my_homebrew"
        try:
            self.saved_path = save_homebrew_pack(xml_text, self.custom_dir, fname)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
