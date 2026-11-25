"""Dialogs and portrait helpers for Aurora Borealis."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..animal_forms import (
    AnimalForm,
    parse_cr_label,
)
from ..engine import is_equipment_proficient, parse_weight_lb
from ..models import ABILITIES, ABILITY_ABBR, CharacterState, ComputedCharacter, Element
from ..loader import ContentRepository
from ..models import DuplicateEntry, Element, InventoryItem
from ..paths import get_os_downloads_dir
from ..persistence import encode_portrait_file
from .ui_helpers import ensure_widgets_fit


_PORTRAIT_PIXMAP_CACHE: dict[tuple[str, str, int], QPixmap] = {}


def pixmap_from_portrait(
    portrait_base64: str,
    portrait_path: str = "",
    size: int = 64,
) -> Optional[QPixmap]:
    """Build a scaled QPixmap from base64 portrait data or fallback file path (cached)."""
    b64_key = (
        hashlib.sha1(portrait_base64.encode("ascii", errors="ignore")).hexdigest()
        if portrait_base64
        else ""
    )
    cache_key = (b64_key, portrait_path or "", size)
    cached = _PORTRAIT_PIXMAP_CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached

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
    scaled = pix.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    if len(_PORTRAIT_PIXMAP_CACHE) >= 128:
        _PORTRAIT_PIXMAP_CACHE.clear()
    _PORTRAIT_PIXMAP_CACHE[cache_key] = scaled
    return scaled


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
        self.rad_5e = QRadioButton("D&&D 5e (2014) — Classic racial ability bonuses && feats")
        self.rad_55e = QRadioButton("D&&D 5.5e (2024 Revised) — Background ASI (+2/+1) && Origin Feat")
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
        btn_pick = QPushButton("Choose Portrait")
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
        ensure_widgets_fit(self)

    def _pick_portrait(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Character Portrait",
            str(get_os_downloads_dir()),
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
        ensure_widgets_fit(self)

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
        computed: Optional[ComputedCharacter] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.computed = computed
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
        self.chk_proficient_only = QCheckBox("Proficient Only")
        self.chk_proficient_only.setVisible(computed is not None)
        self.chk_proficient_only.stateChanged.connect(self._refresh_base_list)
        top_filter.addWidget(self.cmb_kind, 1)
        top_filter.addWidget(self.txt_search, 2)
        top_filter.addWidget(self.chk_proficient_only)
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
        ensure_widgets_fit(self)

        self._refresh_base_list(initial_id=initial_element.id if initial_element else "")
        ensure_widgets_fit(self)

    def _refresh_base_list(self, _idx: int = 0, initial_id: str = "") -> None:
        q = self.txt_search.text().strip()
        kind = self.cmb_kind.currentText()
        types = ["Armor", "Weapon"] if kind.startswith("All") else [kind]
        items = self.repo.search(q, types)
        if self.computed is not None and self.chk_proficient_only.isChecked():
            items = [e for e in items if is_equipment_proficient(e, self.computed, self.repo) is True]
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


RULE_OVERRIDE_SPECS: list[tuple[str, str, str]] = [
    (
        "allow_extra_spells",
        "Allow Extra / Off-List Spells",
        "Ignore class/subclass spell lists, max spell level, and known/prepared limits.",
    ),
    (
        "allow_all_animal_forms",
        "Allow All Animal Forms / Wild Shape Forms",
        "Ignore Druid level, CR, swim/fly speed, and known-form restrictions.",
    ),
    (
        "override_multiclass_prereqs",
        "Ignore Multiclassing Ability Prerequisites",
        "Allow multiclassing into or out of any class regardless of ability scores.",
    ),
    (
        "override_weapon_mastery",
        "Override 5.5e Weapon Mastery Limits",
        "Allow any class to assign any number of Weapon Masteries.",
    ),
    (
        "override_55e_subclass_level",
        "Allow Early Subclass Selection in 5.5e (Lv 1–2)",
        "Keep legacy level 1–2 subclass choices instead of standardizing to level 3.",
    ),
    (
        "override_asi_cap",
        "Allow Ability Scores Above 20",
        "Bypass the standard ability score cap of 20 during character customization.",
    ),
    (
        "override_point_buy",
        "Override Point Buy Limit (27 pts / 8–15 Base Scores)",
        "Allow rolled or custom base ability scores outside the standard 27-point Point Buy budget.",
    ),
    (
        "override_proficiencies",
        "Enable Manual Proficiency Overrides",
        "Manually toggle Saving Throw / Skill proficiencies, Expertise, and add custom Armor/Weapon/Tool proficiencies.",
    ),
    (
        "override_heavy_weapon_req",
        "Ignore 5.5e Heavy Weapon STR/DEX 13 Requirement",
        "Suppress warnings/restrictions when wielding Heavy weapons below 13 STR/DEX.",
    ),
    (
        "override_companion_limits",
        "Allow All Companion Templates",
        "Attach any companion (Beast, Steel Defender, Drake, Steed, Familiar) regardless of class.",
    ),
]


class RuleOverridesDialog(QDialog):
    """Centralized manual rule overrides dialog for the active character."""

    def __init__(self, state, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manual Rule Overrides")
        self.setMinimumWidth(560)
        self._checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Enable manual overrides to relax D&D 5e / 5.5e restrictions for this character "
            "(homebrew campaigns, magic items, or DM rulings)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grp = QGroupBox("Character Rule Overrides")
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)
        for key, label, desc in RULE_OVERRIDE_SPECS:
            chk = QCheckBox(label)
            chk.setChecked(state.has_override(key))
            chk.setStyleSheet("font-weight:bold;")
            hint = QLabel(desc)
            hint.setObjectName("MutedText")
            hint.setWordWrap(True)
            hint.setContentsMargins(22, 0, 0, 4)
            gl.addWidget(chk)
            gl.addWidget(hint)
            self._checkboxes[key] = chk
        layout.addWidget(grp)

        quick_row = QHBoxLayout()
        btn_all = QPushButton("Enable All")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton("Reset All to Rules-Legal")
        btn_none.clicked.connect(lambda: self._set_all(False))
        quick_row.addWidget(btn_all)
        quick_row.addWidget(btn_none)
        quick_row.addStretch()
        layout.addLayout(quick_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        ensure_widgets_fit(self)

    def _set_all(self, val: bool) -> None:
        for chk in self._checkboxes.values():
            chk.setChecked(val)

    def selected_overrides(self) -> dict[str, bool]:
        return {k: chk.isChecked() for k, chk in self._checkboxes.items()}


class CustomAnimalFormDialog(QDialog):
    """Dialog to create or edit a custom Animal / Wild Shape / Polymorph form."""

    def __init__(
        self,
        initial_form: Optional[AnimalForm] = None,
        existing_ids: Optional[set[str]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._initial_form = initial_form
        self._existing_ids = set(existing_ids or set())
        self.setWindowTitle(
            f"Edit Custom Animal Form — {initial_form.name}"
            if initial_form
            else "Create Custom Animal Form"
        )
        self.setMinimumSize(520, 620)

        layout = QVBoxLayout(self)
        form_l = QFormLayout()

        self.txt_name = QLineEdit(initial_form.name if initial_form else "")
        self.txt_name.setPlaceholderText("e.g. Frost Wolf, Giant Badger (Moon), Winter Stag…")
        form_l.addRow("Form Name:", self.txt_name)

        self.cmb_category = QComboBox()
        for cat in ("Beast", "Elemental", "Monstrosity", "Fey", "Custom"):
            self.cmb_category.addItem(cat, cat)
        if initial_form:
            idx = self.cmb_category.findData(initial_form.category)
            if idx >= 0:
                self.cmb_category.setCurrentIndex(idx)
        form_l.addRow("Category:", self.cmb_category)

        self.txt_creature_type = QLineEdit(initial_form.creature_type if initial_form else "Beast")
        form_l.addRow("Creature Type:", self.txt_creature_type)

        row_sz_cr = QHBoxLayout()
        self.cmb_size = QComboBox()
        for sz in ("Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"):
            self.cmb_size.addItem(sz, sz)
        self.cmb_size.setCurrentText(initial_form.size if initial_form else "Medium")
        self.cmb_cr = QComboBox()
        self.cmb_cr.setEditable(True)
        for cr_opt in ("0", "1/8", "1/4", "1/2", *(str(i) for i in range(1, 21))):
            self.cmb_cr.addItem(cr_opt)
        self.cmb_cr.setCurrentText(initial_form.cr_label if initial_form else "1/4")
        row_sz_cr.addWidget(self.cmb_size, 1)
        row_sz_cr.addWidget(QLabel("CR:"))
        row_sz_cr.addWidget(self.cmb_cr, 1)
        form_l.addRow("Size / CR:", row_sz_cr)

        row_def = QHBoxLayout()
        self.spn_ac = QSpinBox()
        self.spn_ac.setRange(1, 30)
        self.spn_ac.setValue(initial_form.ac if initial_form else 13)
        self.spn_hp = QSpinBox()
        self.spn_hp.setRange(1, 999)
        self.spn_hp.setValue(initial_form.hp if initial_form else 15)
        row_def.addWidget(QLabel("AC:"))
        row_def.addWidget(self.spn_ac)
        row_def.addWidget(QLabel("HP:"))
        row_def.addWidget(self.spn_hp)
        row_def.addStretch()
        form_l.addRow("Armor & HP:", row_def)

        row_spd = QHBoxLayout()
        self.spn_walk = QSpinBox()
        self.spn_walk.setRange(0, 200)
        self.spn_walk.setSingleStep(5)
        self.spn_walk.setValue(initial_form.walk_speed if initial_form else 40)
        self.spn_swim = QSpinBox()
        self.spn_swim.setRange(0, 200)
        self.spn_swim.setSingleStep(5)
        self.spn_swim.setValue(initial_form.swim_speed if initial_form else 0)
        self.spn_fly = QSpinBox()
        self.spn_fly.setRange(0, 200)
        self.spn_fly.setSingleStep(5)
        self.spn_fly.setValue(initial_form.fly_speed if initial_form else 0)
        row_spd.addWidget(QLabel("Walk:"))
        row_spd.addWidget(self.spn_walk)
        row_spd.addWidget(QLabel("Swim:"))
        row_spd.addWidget(self.spn_swim)
        row_spd.addWidget(QLabel("Fly:"))
        row_spd.addWidget(self.spn_fly)
        form_l.addRow("Speeds (ft.):", row_spd)

        self.txt_speed = QLineEdit(initial_form.speed if initial_form else "")
        self.txt_speed.setPlaceholderText("Optional speed override (e.g. 40 ft., climb 30 ft.) — auto-built if blank")
        form_l.addRow("Speed Display:", self.txt_speed)

        self.txt_senses = QLineEdit(initial_form.senses if initial_form else "Darkvision 60 ft., PP 12")
        form_l.addRow("Senses:", self.txt_senses)
        layout.addLayout(form_l)

        ab_box = QGroupBox("Ability Scores")
        ab_grid = QGridLayout(ab_box)
        self.ab_spins: dict[str, QSpinBox] = {}
        defaults = initial_form.abilities if initial_form else {
            "strength": 14,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 3,
            "wisdom": 12,
            "charisma": 6,
        }
        for idx, ab in enumerate(ABILITIES):
            r, c = divmod(idx, 3)
            spn = QSpinBox()
            spn.setRange(1, 30)
            spn.setValue(int(defaults.get(ab, 10)))
            ab_grid.addWidget(QLabel(f"{ABILITY_ABBR[ab]}:"), r, c * 2)
            ab_grid.addWidget(spn, r, c * 2 + 1)
            self.ab_spins[ab] = spn
        layout.addWidget(ab_box)

        layout.addWidget(QLabel("Traits (one per line):"))
        self.txt_traits = QPlainTextEdit()
        self.txt_traits.setMaximumHeight(80)
        self.txt_traits.setPlaceholderText("Pack Tactics: Advantage on attack rolls while an ally is within 5 ft.\nKeen Smell")
        if initial_form and initial_form.traits:
            self.txt_traits.setPlainText("\n".join(initial_form.traits))
        layout.addWidget(self.txt_traits)

        layout.addWidget(QLabel("Actions (one per line):"))
        self.txt_actions = QPlainTextEdit()
        self.txt_actions.setMaximumHeight(90)
        self.txt_actions.setPlaceholderText("Bite (+5 to hit, 2d6+3 piercing)\nClaws (+5 to hit, 1d8+3 slashing)")
        if initial_form and initial_form.actions:
            self.txt_actions.setPlainText("\n".join(initial_form.actions))
        layout.addWidget(self.txt_actions)

        self.chk_add_known = QCheckBox("Add directly to Known / Saved Forms")
        self.chk_add_known.setChecked(True)
        layout.addWidget(self.chk_add_known)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        ensure_widgets_fit(self)

    def _on_accept(self) -> None:
        if not self.txt_name.text().strip():
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the custom animal form.")
            return
        self.accept()

    def build_animal_form(self) -> AnimalForm:
        import re as _re

        name = self.txt_name.text().strip() or "Custom Animal Form"
        if self._initial_form is not None:
            fid = self._initial_form.id
        else:
            slug = _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "form"
            base_id = f"custom_{slug}"
            fid = base_id
            idx = 2
            while fid in self._existing_ids:
                fid = f"{base_id}_{idx}"
                idx += 1

        cr_label = self.cmb_cr.currentText().strip() or "0"
        walk = self.spn_walk.value()
        swim = self.spn_swim.value()
        fly = self.spn_fly.value()
        speed_txt = self.txt_speed.text().strip()
        if not speed_txt:
            parts = [f"{walk} ft."]
            if swim > 0:
                parts.append(f"swim {swim} ft.")
            if fly > 0:
                parts.append(f"fly {fly} ft.")
            speed_txt = ", ".join(parts)

        traits = [ln.strip() for ln in self.txt_traits.toPlainText().splitlines() if ln.strip()]
        actions = [ln.strip() for ln in self.txt_actions.toPlainText().splitlines() if ln.strip()]
        return AnimalForm(
            id=fid,
            name=name,
            cr=parse_cr_label(cr_label),
            cr_label=cr_label,
            size=self.cmb_size.currentText() or "Medium",
            creature_type=self.txt_creature_type.text().strip() or "Beast",
            ac=self.spn_ac.value(),
            hp=self.spn_hp.value(),
            speed=speed_txt,
            walk_speed=walk,
            swim_speed=swim,
            fly_speed=fly,
            abilities={ab: spn.value() for ab, spn in self.ab_spins.items()},
            senses=self.txt_senses.text().strip() or "PP 10",
            traits=traits,
            actions=actions,
            category=self.cmb_category.currentData() or "Beast",
        )
