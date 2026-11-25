"""Guided 5-step Level-Up Wizard with Multiclassing, Rolled HP, ASI/Feat, Spells, and Diff."""

from __future__ import annotations

import copy
import random
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
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

from ..engine import (
    RulesEngine,
    check_multiclass_prerequisites,
    effective_selection_slot_count,
    is_asi_select_rule,
    is_spell_eligible_for_caster,
    is_synthetic_asi_id,
    parse_hit_die,
    selection_filled_count,
)
from ..level_up import (
    apply_level_up_step,
    compute_character_diff,
    is_asi_level,
    render_diff_html,
)
from ..loader import ContentRepository
from ..models import ABILITIES, ABILITY_ABBR, ActiveSelection, CharacterState, ClassSpellcasting, ComputedCharacter, Element
from .icons import apply_button_icon, refresh_themed_icons
from .ui_helpers import configure_dropdown_combo, ensure_widgets_fit, install_global_wheel_filter


class LevelUpWizardDialog(QDialog):
    """5-step guided Level-Up Wizard with live Before/After diff."""

    _STEP_TITLES = [
        "1. Class && HP",
        "2. Features && Choices",
        "3. ASI / Feat",
        "4. Spells",
        "5. Review Diff",
    ]

    def __init__(
        self,
        state: CharacterState,
        repo: ContentRepository,
        engine: RulesEngine,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.engine = engine
        self._before_state = copy.deepcopy(state)
        self._before_comp: ComputedCharacter = engine.evaluate(self._before_state)
        self._draft_state: CharacterState = copy.deepcopy(state)
        self._draft_comp: ComputedCharacter = self._before_comp
        self._updating = False

        # Transient wizard selections layered cleanly over _before_state
        self._wizard_selections: dict[str, list[str]] = {}
        self._wizard_asi_mode: str = "asi"  # "asi" or "feat"
        self._wizard_asi_split: str = "2"  # "2" or "11"
        self._wizard_asi_ab_a: str = "strength"
        self._wizard_asi_ab_b: str = "constitution"
        self._wizard_feat_id: str = ""
        self._wizard_added_spells: list[str] = []
        self._wizard_removed_spells: list[str] = []
        self._wizard_prepared_spells: set[str] = set()

        self.setWindowTitle(
            f"Level-Up Wizard — {state.name or 'Adventurer'} (Lv {state.level} → {min(20, state.level + 1)})"
        )
        install_global_wheel_filter(QApplication.instance())
        self.resize(1120, 740)
        self._build_ui()
        self._init_step0_options()
        self._rebuild_draft()
        self._go_to_page(0)
        theme = "dark"
        if parent is not None and hasattr(parent, "config"):
            theme = getattr(parent.config, "theme", "dark")
        refresh_themed_icons(self, theme)
        ensure_widgets_fit(self)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Step indicator bar
        step_bar = QFrame()
        step_bar.setObjectName("SubBar")
        sb_l = QHBoxLayout(step_bar)
        sb_l.setContentsMargins(10, 8, 10, 8)
        sb_l.setSpacing(6)
        self._step_pills: list[QPushButton] = []
        for idx, title in enumerate(self._STEP_TITLES):
            btn = QPushButton(title)
            btn.setObjectName("NavTabBtn")
            btn.setProperty("active", idx == 0)
            btn.clicked.connect(lambda _=False, i=idx: self._go_to_page(i))
            sb_l.addWidget(btn)
            self._step_pills.append(btn)
        sb_l.addStretch()
        root.addWidget(step_bar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_class_hp())
        self.stack.addWidget(self._build_page_features())
        self.stack.addWidget(self._build_page_asi_feat())
        self.stack.addWidget(self._build_page_spells())
        self.stack.addWidget(self._build_page_diff())
        root.addWidget(self.stack, 1)

        # Footer buttons
        footer = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_back = QPushButton("Back")
        apply_button_icon(self.btn_back, "arrow-left", size=15)
        self.btn_back.clicked.connect(self.go_back)
        self.btn_next = QPushButton("Next")
        self.btn_next.setObjectName("PrimaryBtn")
        apply_button_icon(self.btn_next, "arrow-right", size=15)
        self.btn_next.clicked.connect(self.go_next)
        self.btn_apply = QPushButton("Apply Level Up")
        self.btn_apply.setObjectName("PrimaryBtn")
        apply_button_icon(self.btn_apply, "check", size=15)
        self.btn_apply.clicked.connect(self._on_apply)

        footer.addWidget(self.btn_cancel)
        footer.addStretch()
        footer.addWidget(self.btn_back)
        footer.addWidget(self.btn_next)
        footer.addWidget(self.btn_apply)
        root.addLayout(footer)

    # ------------------------------------------------------------------
    # Page 0: Class & HP
    # ------------------------------------------------------------------
    def _build_page_class_hp(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        cls_group = QGroupBox("Step 1 — Choose Class for This Level")
        cg_l = QVBoxLayout(cls_group)

        self._cls_mode_grp = QButtonGroup(self)
        self.rad_advance = QRadioButton("Advance an existing class")
        self.rad_multiclass = QRadioButton("Multiclass into a new class")
        self._cls_mode_grp.addButton(self.rad_advance)
        self._cls_mode_grp.addButton(self.rad_multiclass)
        self.rad_advance.setChecked(True)
        self.rad_advance.toggled.connect(self._on_class_choice_changed)

        self.cmb_existing_class = QComboBox()
        self.cmb_existing_class.currentIndexChanged.connect(self._on_class_choice_changed)

        self.cmb_new_class = QComboBox()
        self.cmb_new_class.currentIndexChanged.connect(self._on_class_choice_changed)

        self.lbl_mc_prereq = QLabel("")
        self.lbl_mc_prereq.setWordWrap(True)
        self.chk_mc_override = QCheckBox("Override multiclassing ability prerequisites")
        self.chk_mc_override.stateChanged.connect(self._on_class_choice_changed)

        cg_l.addWidget(self.rad_advance)
        cg_l.addWidget(self.cmb_existing_class)
        cg_l.addSpacing(6)
        cg_l.addWidget(self.rad_multiclass)
        cg_l.addWidget(self.cmb_new_class)
        cg_l.addWidget(self.lbl_mc_prereq)
        cg_l.addWidget(self.chk_mc_override)
        layout.addWidget(cls_group)

        hp_group = QGroupBox("Hit Points for This Level")
        hg_l = QVBoxLayout(hp_group)

        self._hp_mode_grp = QButtonGroup(self)
        self.rad_hp_avg = QRadioButton("Take Fixed Average")
        self.rad_hp_roll = QRadioButton("Roll / Enter Hit Die Result")
        self._hp_mode_grp.addButton(self.rad_hp_avg)
        self._hp_mode_grp.addButton(self.rad_hp_roll)
        if self._before_state.hp_mode == "rolled":
            self.rad_hp_roll.setChecked(True)
        else:
            self.rad_hp_avg.setChecked(True)
        self.rad_hp_avg.toggled.connect(self._on_hp_choice_changed)

        roll_row = QHBoxLayout()
        roll_row.addWidget(QLabel("Die Roll:"))
        self.spn_hp_roll = QSpinBox()
        self.spn_hp_roll.setRange(1, 12)
        self.spn_hp_roll.setFixedWidth(96)
        self.spn_hp_roll.valueChanged.connect(self._on_hp_choice_changed)
        self.btn_roll_die = QPushButton("Roll 1d8")
        apply_button_icon(self.btn_roll_die, "dice", size=15)
        self.btn_roll_die.clicked.connect(self._roll_hp_die)
        roll_row.addWidget(self.spn_hp_roll)
        roll_row.addWidget(self.btn_roll_die)
        roll_row.addStretch()

        self.lbl_hp_preview = QLabel("")
        self.lbl_hp_preview.setObjectName("AccentText")

        hg_l.addWidget(self.rad_hp_avg)
        hg_l.addWidget(self.rad_hp_roll)
        hg_l.addLayout(roll_row)
        hg_l.addWidget(self.lbl_hp_preview)
        layout.addWidget(hp_group)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # Page 1: Features & Choices
    # ------------------------------------------------------------------
    def _build_page_features(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QGroupBox("Newly Gained Features")
        ll = QVBoxLayout(left)
        self.lst_new_features = QListWidget()
        self.lst_new_features.currentItemChanged.connect(self._on_feature_preview)
        ll.addWidget(self.lst_new_features, 1)
        self.feat_desc_browser = QTextBrowser()
        self.feat_desc_browser.setOpenExternalLinks(True)
        ll.addWidget(self.feat_desc_browser, 1)

        right = QGroupBox("Subclass && Feature Choices")
        rl = QVBoxLayout(right)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.choices_scroll = scroll
        self.choices_host = QWidget()
        self.choices_layout = QVBoxLayout(self.choices_host)
        self.choices_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.choices_host)
        rl.addWidget(scroll)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([380, 620])
        layout.addWidget(splitter, 1)
        return page

    # ------------------------------------------------------------------
    # Page 2: ASI / Feat
    # ------------------------------------------------------------------
    def _build_page_asi_feat(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.lbl_asi_status = QLabel("")
        self.lbl_asi_status.setObjectName("TitleText")
        layout.addWidget(self.lbl_asi_status)

        self.asi_widget = QWidget()
        awl = QVBoxLayout(self.asi_widget)
        awl.setContentsMargins(0, 0, 0, 0)

        self._asi_mode_grp = QButtonGroup(self)
        self.rad_asi = QRadioButton("Ability Score Improvement (+2 to one ability, or +1 to two abilities)")
        self.rad_feat = QRadioButton("Choose a Feat instead of Ability Score Improvement")
        self._asi_mode_grp.addButton(self.rad_asi)
        self._asi_mode_grp.addButton(self.rad_feat)
        self.rad_asi.setChecked(True)
        self.rad_asi.toggled.connect(self._on_asi_controls_changed)

        awl.addWidget(self.rad_asi)

        self.asi_scores_box = QGroupBox("Ability Score Points")
        asbl = QVBoxLayout(self.asi_scores_box)
        split_row = QHBoxLayout()
        self._asi_split_grp = QButtonGroup(self)
        self.rad_asi_2 = QRadioButton("+2 to One Ability")
        self.rad_asi_11 = QRadioButton("+1 / +1 to Two Abilities")
        self._asi_split_grp.addButton(self.rad_asi_2)
        self._asi_split_grp.addButton(self.rad_asi_11)
        self.rad_asi_2.setChecked(True)
        self.rad_asi_2.toggled.connect(self._on_asi_controls_changed)
        split_row.addWidget(self.rad_asi_2)
        split_row.addWidget(self.rad_asi_11)
        split_row.addStretch()
        asbl.addLayout(split_row)

        combo_row = QHBoxLayout()
        self.cmb_asi_a = QComboBox()
        self.cmb_asi_b = QComboBox()
        for ab in ABILITIES:
            self.cmb_asi_a.addItem(ab.capitalize(), ab)
            self.cmb_asi_b.addItem(ab.capitalize(), ab)
        self.cmb_asi_b.setCurrentIndex(2)
        self.cmb_asi_a.currentIndexChanged.connect(self._on_asi_controls_changed)
        self.cmb_asi_b.currentIndexChanged.connect(self._on_asi_controls_changed)
        combo_row.addWidget(QLabel("Primary (+2 / +1):"))
        combo_row.addWidget(self.cmb_asi_a)
        combo_row.addSpacing(12)
        combo_row.addWidget(QLabel("Secondary (+1):"))
        combo_row.addWidget(self.cmb_asi_b)
        combo_row.addStretch()
        asbl.addLayout(combo_row)

        self.lbl_asi_preview = QLabel("")
        self.lbl_asi_preview.setObjectName("AccentText")
        asbl.addWidget(self.lbl_asi_preview)
        awl.addWidget(self.asi_scores_box)

        awl.addWidget(self.rad_feat)
        self.asi_feat_box = QGroupBox("Feat Selection")
        fbl = QVBoxLayout(self.asi_feat_box)
        self.txt_feat_search = QLineEdit()
        self.txt_feat_search.setPlaceholderText("Search feats…")
        self.txt_feat_search.textChanged.connect(self._populate_feat_list)
        fbl.addWidget(self.txt_feat_search)

        f_split = QSplitter(Qt.Orientation.Horizontal)
        self.lst_feats = QListWidget()
        self.lst_feats.currentItemChanged.connect(self._on_wizard_feat_selected)
        self.asi_feat_browser = QTextBrowser()
        self.asi_feat_browser.setOpenExternalLinks(True)
        f_split.addWidget(self.lst_feats)
        f_split.addWidget(self.asi_feat_browser)
        f_split.setSizes([340, 520])
        fbl.addWidget(f_split, 1)
        awl.addWidget(self.asi_feat_box, 1)

        layout.addWidget(self.asi_widget, 1)
        layout.addStretch()
        self._populate_feat_list()
        return page

    # ------------------------------------------------------------------
    # Page 3: Spells
    # ------------------------------------------------------------------
    def _build_page_spells(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.lbl_spell_status = QLabel("")
        self.lbl_spell_status.setObjectName("TitleText")
        self.lbl_spell_status.setWordWrap(True)
        self.chk_override_spells = QCheckBox("Override spell limits")
        self.chk_override_spells.setChecked(self._before_state.has_override("allow_extra_spells"))
        self.chk_override_spells.stateChanged.connect(lambda _v: self._rebuild_draft())
        sp_hdr_row = QHBoxLayout()
        sp_hdr_row.addWidget(self.lbl_spell_status, 1)
        sp_hdr_row.addWidget(self.chk_override_spells)
        layout.addLayout(sp_hdr_row)

        self.spells_widget = QWidget()
        swl = QVBoxLayout(self.spells_widget)
        swl.setContentsMargins(0, 0, 0, 0)

        self.lbl_spell_subinfo = QLabel("")
        self.lbl_spell_subinfo.setObjectName("AccentText")
        self.lbl_spell_subinfo.setWordWrap(True)
        swl.addWidget(self.lbl_spell_subinfo)

        # Optional XML <select type="Spell"> rules unlocked at this level
        self.spell_selects_host = QWidget()
        self.spell_selects_layout = QVBoxLayout(self.spell_selects_host)
        self.spell_selects_layout.setContentsMargins(0, 0, 0, 0)
        swl.addWidget(self.spell_selects_host)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        cat_box = QGroupBox("Eligible Class / Subclass Spells")
        cbl = QVBoxLayout(cat_box)
        self.txt_spell_search = QLineEdit()
        self.txt_spell_search.setPlaceholderText("Search eligible spells…")
        self.txt_spell_search.textChanged.connect(self._refresh_spell_catalog)
        cbl.addWidget(self.txt_spell_search)

        self.tbl_spell_catalog = QTableWidget(0, 2)
        self.tbl_spell_catalog.setHorizontalHeaderLabels(["Spell", "Lvl"])
        self.tbl_spell_catalog.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_spell_catalog.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tbl_spell_catalog.setColumnWidth(1, 50)
        self.tbl_spell_catalog.verticalHeader().setVisible(False)
        self.tbl_spell_catalog.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_spell_catalog.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_spell_catalog.currentCellChanged.connect(self._on_spell_catalog_preview)
        self.tbl_spell_catalog.cellDoubleClicked.connect(lambda _r, _c: self._add_wizard_spell())
        cbl.addWidget(self.tbl_spell_catalog, 1)

        self.btn_add_spell = QPushButton("+ Learn / Add Spell")
        self.btn_add_spell.setObjectName("PrimaryBtn")
        self.btn_add_spell.clicked.connect(self._add_wizard_spell)
        cbl.addWidget(self.btn_add_spell)

        right_box = QWidget()
        rbl = QVBoxLayout(right_box)
        rbl.setContentsMargins(0, 0, 0, 0)

        added_grp = QGroupBox("Current && Added Spells (This Class)")
        agl = QVBoxLayout(added_grp)
        self.lst_added_spells = QListWidget()
        self.lst_added_spells.currentItemChanged.connect(self._on_added_spell_preview)
        agl.addWidget(self.lst_added_spells, 1)
        self.btn_rem_spell = QPushButton("− Remove Selected Spell")
        self.btn_rem_spell.setObjectName("DangerBtn")
        self.btn_rem_spell.clicked.connect(self._remove_wizard_spell)
        agl.addWidget(self.btn_rem_spell)

        self.spell_desc_browser = QTextBrowser()
        self.spell_desc_browser.setOpenExternalLinks(True)
        rbl.addWidget(added_grp, 1)
        rbl.addWidget(self.spell_desc_browser, 1)

        splitter.addWidget(cat_box)
        splitter.addWidget(right_box)
        splitter.setSizes([430, 480])
        swl.addWidget(splitter, 1)

        layout.addWidget(self.spells_widget, 1)
        return page

    # ------------------------------------------------------------------
    # Page 4: Review Diff
    # ------------------------------------------------------------------
    def _build_page_diff(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        grp = QGroupBox("Before → After Character Diff")
        gl = QVBoxLayout(grp)
        self.diff_browser = QTextBrowser()
        self.diff_browser.setOpenExternalLinks(True)
        gl.addWidget(self.diff_browser)
        layout.addWidget(grp, 1)
        return page

    # ------------------------------------------------------------------
    # Logic & Synchronization
    # ------------------------------------------------------------------
    def _init_step0_options(self) -> None:
        self._updating = True
        try:
            self.cmb_existing_class.clear()
            norm = self._before_state.normalized_classes()
            existing_ids = {c.class_id for c in norm}
            for cl in norm:
                cel = self.repo.get(cl.class_id)
                cname = cel.name if cel else cl.class_id
                self.cmb_existing_class.addItem(f"{cname} (Lv {cl.level} → {cl.level + 1})", cl.class_id)

            self.cmb_new_class.clear()
            for cel in self.repo.of_type("Class"):
                if cel.id not in existing_ids:
                    self.cmb_new_class.addItem(cel.name, cel.id)

            if not norm:
                self.rad_advance.setEnabled(False)
                self.cmb_existing_class.setEnabled(False)
                self.rad_multiclass.setChecked(True)
                self.rad_multiclass.setText("Select initial class")
            elif self.cmb_new_class.count() == 0:
                self.rad_multiclass.setEnabled(False)
                self.cmb_new_class.setEnabled(False)

            cid = self.current_target_class_id()
            cel = self.repo.get(cid) if cid else None
            hd_num = parse_hit_die(cel)
            self.spn_hp_roll.setRange(1, hd_num)
            self.spn_hp_roll.setValue((hd_num // 2) + 1)
        finally:
            self._updating = False

    def current_target_class_id(self) -> str:
        if self.rad_advance.isChecked() and self.cmb_existing_class.count() > 0:
            return self.cmb_existing_class.currentData() or ""
        return self.cmb_new_class.currentData() or ""

    def _target_new_class_level(self, target_cid: str) -> int:
        for cl in self._before_state.normalized_classes():
            if cl.class_id == target_cid:
                return cl.level + 1
        return 1

    def _on_class_choice_changed(self) -> None:
        if self._updating:
            return
        self._wizard_selections.clear()
        self._wizard_feat_id = ""
        self._wizard_added_spells.clear()
        self._wizard_removed_spells.clear()
        self._wizard_prepared_spells.clear()
        self._rebuild_draft()

    def _on_hp_choice_changed(self) -> None:
        if self._updating:
            return
        self._rebuild_draft()

    def _roll_hp_die(self) -> None:
        cid = self.current_target_class_id()
        hd_num = parse_hit_die(self.repo.get(cid) if cid else None)
        rolled = random.randint(1, hd_num)
        self.rad_hp_roll.setChecked(True)
        self.spn_hp_roll.setValue(rolled)

    def _rebuild_draft(self) -> None:
        target_cid = self.current_target_class_id()
        target_el = self.repo.get(target_cid) if target_cid else None
        hd_num = parse_hit_die(target_el)
        avg = (hd_num // 2) + 1

        self._updating = True
        try:
            self.spn_hp_roll.setRange(1, hd_num)
            self.btn_roll_die.setText(f"Roll 1d{hd_num}")
            is_rolled = self.rad_hp_roll.isChecked()
            self.spn_hp_roll.setEnabled(is_rolled)
            self.btn_roll_die.setEnabled(is_rolled)
            self.cmb_existing_class.setEnabled(self.rad_advance.isChecked() and self.cmb_existing_class.count() > 0)
            self.cmb_new_class.setEnabled(self.rad_multiclass.isChecked() and self.cmb_new_class.count() > 0)
        finally:
            self._updating = False

        hp_mode = "rolled" if self.rad_hp_roll.isChecked() else "average"
        hp_roll = self.spn_hp_roll.value() if hp_mode == "rolled" else None

        if target_cid:
            draft = apply_level_up_step(self._before_state, target_cid, hp_mode=hp_mode, hp_roll=hp_roll)
        else:
            draft = copy.deepcopy(self._before_state)

        for skey, svals in self._wizard_selections.items():
            draft.selections[skey] = list(svals)

        new_cls_lvl = self._target_new_class_level(target_cid)
        if target_cid and is_asi_level(target_el, new_cls_lvl):
            asi_key = f"{target_cid}::{new_cls_lvl}"
            if self._wizard_asi_mode == "feat" and self._wizard_feat_id:
                draft.level_up_feats[asi_key] = self._wizard_feat_id
                draft.level_up_asi.pop(asi_key, None)
            elif self._wizard_asi_mode == "asi":
                draft.level_up_feats.pop(asi_key, None)
                if self._wizard_asi_split == "2":
                    draft.level_up_asi[asi_key] = {self._wizard_asi_ab_a: 2}
                else:
                    ab_b = self._wizard_asi_ab_b
                    if ab_b == self._wizard_asi_ab_a:
                        ab_b = next(a for a in ABILITIES if a != self._wizard_asi_ab_a)
                    draft.level_up_asi[asi_key] = {self._wizard_asi_ab_a: 1, ab_b: 1}

        if self._wizard_removed_spells:
            rem_set = set(self._wizard_removed_spells)
            draft.known_spells = [s for s in draft.known_spells if s not in rem_set]
            draft.prepared_spells = [s for s in draft.prepared_spells if s not in rem_set]
            for sid in rem_set:
                draft.spell_sources.pop(sid, None)

        for sid in self._wizard_added_spells:
            if sid not in draft.known_spells:
                draft.known_spells.append(sid)
            if target_cid:
                draft.spell_sources[sid] = target_cid
            if sid in self._wizard_prepared_spells and sid not in draft.prepared_spells:
                draft.prepared_spells.append(sid)

        for sid in self._wizard_prepared_spells:
            if sid in draft.known_spells and sid not in draft.prepared_spells:
                draft.prepared_spells.append(sid)

        if hasattr(self, "chk_override_spells") and self.chk_override_spells.isChecked():
            draft.set_override("allow_extra_spells", True)

        self._draft_state = draft
        self._draft_comp = self.engine.evaluate(draft)

        # Update Step 0 labels
        if self.rad_multiclass.isChecked() and target_el is not None and self._before_state.normalized_classes():
            ok, msg = check_multiclass_prerequisites(self._before_state, self._before_comp, target_el, self.repo)
            self.lbl_mc_prereq.setText(("✓ " if ok else "⚠ ") + msg)
            self.lbl_mc_prereq.setStyleSheet("color:#4ade80;" if ok else "color:#facc15; font-weight:bold;")
            self.lbl_mc_prereq.show()
            self.chk_mc_override.show()
        else:
            self.lbl_mc_prereq.hide()
            self.chk_mc_override.hide()

        con_mod = self._draft_comp.ability_modifiers["constitution"]
        die_gain = hp_roll if hp_mode == "rolled" and hp_roll is not None else (hd_num if self._draft_state.level == 1 else avg)
        self.lbl_hp_preview.setText(
            f"HP gain this level: {die_gain} (1d{hd_num} {hp_mode}) + {con_mod:+d} CON = {die_gain + con_mod:+d} "
            f"(New Max HP: {self._before_comp.max_hp} → {self._draft_comp.max_hp})"
        )

        # Refresh visible step contents
        self._refresh_features_page()
        self._refresh_asi_page()
        self._refresh_spells_page()
        self._refresh_diff_page()

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _newly_unlocked_selections(self, spell_only: bool = False) -> list[ActiveSelection]:
        before_keys = {s.key for s in self._before_comp.active_selections}
        out: list[ActiveSelection] = []
        for active_sel in self._draft_comp.active_selections:
            is_spell = active_sel.rule.type == "Spell"
            if spell_only and not is_spell:
                continue
            if not spell_only and (is_spell or is_asi_select_rule(active_sel.rule)):
                continue
            eff_num = effective_selection_slot_count(active_sel, self._draft_state, self._draft_comp)
            if eff_num == 0:
                continue
            filled = selection_filled_count(active_sel, self._draft_state, eff_num)
            if active_sel.key not in before_keys or filled < eff_num:
                out.append(active_sel)
        return out

    def _render_selection_card(self, active_sel: ActiveSelection, target_layout: QVBoxLayout) -> None:
        eff_num = effective_selection_slot_count(active_sel, self._draft_state, self._draft_comp)
        filled = selection_filled_count(active_sel, self._draft_state, eff_num)
        chosen = list(self._draft_state.selections.get(active_sel.key, []))
        slot_vals = list(chosen[:eff_num])
        if any(chosen[eff_num:]):
            compacted = [v for v in chosen if v]
            slot_vals = (compacted + [""] * eff_num)[:eff_num]
        else:
            while len(slot_vals) < eff_num:
                slot_vals.append("")

        card = QFrame()
        card.setObjectName("ChoiceCard" if (filled >= eff_num or active_sel.rule.optional) else "ChoiceCardPending")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(6)
        lbl_hdr = QLabel(
            f"<b>{active_sel.rule.name}</b> <span style='color:#94a3b8;'>({active_sel.source_element_name})</span>"
        )
        lbl_hdr.setWordWrap(True)
        vl.addWidget(lbl_hdr)

        if eff_num == 0:
            lbl_done = QLabel("All available options are already granted.")
            lbl_done.setObjectName("MutedText")
            vl.addWidget(lbl_done)
            target_layout.addWidget(card)
            return

        all_granted = {e.id for e in self._draft_comp.granted_elements}
        other_sel_ids = {
            sv
            for skey, svals in self._draft_state.selections.items()
            if skey != active_sel.key
            for sv in svals
            if sv
        }
        for slot_idx in range(eff_num):
            cmb = QComboBox()
            configure_dropdown_combo(cmb, max_visible=14)
            cmb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cmb.addItem("— Choose —", "")
            cur_val = slot_vals[slot_idx]
            same_sel_other = {slot_vals[i] for i in range(eff_num) if i != slot_idx and slot_vals[i]}
            taken = set(same_sel_other)
            if active_sel.rule.type != "List":
                taken |= all_granted
                taken |= other_sel_ids
            taken.discard(cur_val)
            seen: set[str] = set()
            for opt_id, opt_name in active_sel.options:
                if (not is_synthetic_asi_id(opt_id) and opt_id in taken) or opt_id in seen:
                    continue
                seen.add(opt_id)
                cmb.addItem(opt_name, opt_id)
            if cur_val:
                idx = cmb.findData(cur_val)
                if idx >= 0:
                    cmb.setCurrentIndex(idx)

            def make_cb(skey: str, sidx: int, count: int, combo_ref: QComboBox, seed_vals: list[str]):
                def _changed(_i: int) -> None:
                    if self._updating:
                        return
                    val = combo_ref.currentData() or ""
                    lst = list(seed_vals)
                    raw_lst = self._draft_state.selections.get(skey, [])
                    if len(raw_lst) >= count and not any(raw_lst[count:]):
                        lst = list(raw_lst[:count])
                    while len(lst) < count:
                        lst.append("")
                    lst[sidx] = val
                    self._wizard_selections[skey] = lst
                    if val and val in self.repo.by_id:
                        el = self.repo.by_id[val]
                        self.feat_desc_browser.setHtml(
                            f"<h3>{el.name}</h3>{el.description_html or el.sheet_description or ''}"
                        )
                    self._rebuild_draft()

                return _changed

            cmb.currentIndexChanged.connect(make_cb(active_sel.key, slot_idx, eff_num, cmb, slot_vals))
            vl.addWidget(cmb)
        target_layout.addWidget(card)

    def _refresh_features_page(self) -> None:
        before_ids = {e.id for e in self._before_comp.granted_elements}
        new_els = [
            e
            for e in self._draft_comp.granted_elements
            if e.id not in before_ids
            and e.type in ("Class", "Archetype", "Class Feature", "Archetype Feature", "Proficiency")
        ]
        self.lst_new_features.clear()
        for el in new_els:
            it = QListWidgetItem(f"[{el.type}] {el.name}")
            it.setData(Qt.ItemDataRole.UserRole, el.id)
            self.lst_new_features.addItem(it)
        if not new_els:
            self.lst_new_features.addItem("(No automatic new features at this level)")

        saved_scroll = self.choices_scroll.verticalScrollBar().value()
        self.choices_host.setUpdatesEnabled(False)
        self._clear_layout(self.choices_layout)
        sels = self._newly_unlocked_selections(spell_only=False)
        if not sels:
            lbl = QLabel("No subclass or feature choices required at this level.")
            lbl.setObjectName("MutedText")
            self.choices_layout.addWidget(lbl)
        else:
            for active_sel in sels:
                self._render_selection_card(active_sel, self.choices_layout)
        self.choices_host.setUpdatesEnabled(True)

        def _restore_wiz_scroll() -> None:
            sb = self.choices_scroll.verticalScrollBar()
            sb.setValue(min(saved_scroll, sb.maximum()))

        _restore_wiz_scroll()
        QTimer.singleShot(0, _restore_wiz_scroll)

    def _on_feature_preview(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        eid = current.data(Qt.ItemDataRole.UserRole)
        el = self.repo.get(eid) if eid else None
        if el:
            self.feat_desc_browser.setHtml(
                f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>{el.type} — {el.source}</p>"
                f"{el.description_html or el.sheet_description or '<p>No description.</p>'}"
            )

    def _refresh_asi_page(self) -> None:
        target_cid = self.current_target_class_id()
        target_el = self.repo.get(target_cid) if target_cid else None
        new_cls_lvl = self._target_new_class_level(target_cid)
        asi_active = bool(target_cid) and is_asi_level(target_el, new_cls_lvl)

        if not asi_active:
            cname = target_el.name if target_el else "this class"
            self.lbl_asi_status.setText(f"No ASI or Feat unlocked at {cname} Level {new_cls_lvl}.")
            self.asi_widget.hide()
            return

        self.lbl_asi_status.setText(
            f"Ability Score Improvement / Feat Unlocked ({target_el.name if target_el else ''} Lv {new_cls_lvl})"
        )
        self.asi_widget.show()
        is_asi = self.rad_asi.isChecked()
        self.asi_scores_box.setVisible(is_asi)
        self.asi_feat_box.setVisible(not is_asi)
        self.cmb_asi_b.setEnabled(self.rad_asi_11.isChecked())

        if is_asi:
            ab_a = self.cmb_asi_a.currentData() or "strength"
            ab_b = self.cmb_asi_b.currentData() or "constitution"
            if self.rad_asi_2.isChecked():
                delta_txt = f"{ABILITY_ABBR[ab_a]} {self._before_comp.ability_totals[ab_a]} → {self._draft_comp.ability_totals[ab_a]}"
            else:
                delta_txt = (
                    f"{ABILITY_ABBR[ab_a]} {self._before_comp.ability_totals[ab_a]} → {self._draft_comp.ability_totals[ab_a]}  •  "
                    f"{ABILITY_ABBR[ab_b]} {self._before_comp.ability_totals[ab_b]} → {self._draft_comp.ability_totals[ab_b]}"
                )
            self.lbl_asi_preview.setText(f"Preview: {delta_txt}")

    def _on_asi_controls_changed(self) -> None:
        if self._updating:
            return
        self._wizard_asi_mode = "asi" if self.rad_asi.isChecked() else "feat"
        self._wizard_asi_split = "2" if self.rad_asi_2.isChecked() else "11"
        self._wizard_asi_ab_a = self.cmb_asi_a.currentData() or "strength"
        self._wizard_asi_ab_b = self.cmb_asi_b.currentData() or "constitution"
        self._rebuild_draft()

    def _populate_feat_list(self) -> None:
        q = self.txt_feat_search.text().strip()
        feats = self.repo.search(q, ["Feat"])
        already = {e.id for e in self._before_comp.granted_elements if e.type == "Feat"}
        self.lst_feats.clear()
        for f in feats:
            if f.id in already:
                continue
            it = QListWidgetItem(f.name)
            it.setData(Qt.ItemDataRole.UserRole, f.id)
            self.lst_feats.addItem(it)
            if f.id == self._wizard_feat_id:
                self.lst_feats.setCurrentItem(it)

    def _on_wizard_feat_selected(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        fid = current.data(Qt.ItemDataRole.UserRole) or ""
        el = self.repo.get(fid)
        if el:
            self._wizard_feat_id = fid
            self.asi_feat_browser.setHtml(
                f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>{el.source}</p>"
                f"{el.description_html or el.sheet_description or '<p>No description.</p>'}"
            )
            if self.rad_feat.isChecked():
                self._rebuild_draft()

    def _active_target_caster(self) -> Optional[ClassSpellcasting]:
        sc = self._draft_comp.spellcasting
        if not sc:
            return None
        target_cid = self.current_target_class_id()
        for c in sc.casters:
            if c.source_class_id == target_cid:
                return c
        return None

    def _wizard_spell_counts(self, caster: ClassSpellcasting) -> tuple[int, int, int]:
        """Return (cantrips, known_leveled, prepared_leveled) for this caster on the draft state."""
        sc = self._draft_comp.spellcasting
        single_caster = bool(sc and len(sc.casters) == 1)
        always_prep = set(caster.always_prepared_spell_ids)
        owned_sids: list[str] = list(caster.granted_spell_ids)
        for sid in self._draft_state.known_spells:
            src = self._draft_state.spell_sources.get(sid, "")
            if (src == caster.source_class_id or (not src and single_caster)) and sid not in owned_sids:
                owned_sids.append(sid)
        cantrips = 0
        known_leveled = 0
        for sid in owned_sids:
            el = self.repo.get(sid)
            lvl_str = el.setters.get("level", "0") if el else "0"
            if lvl_str == "0":
                cantrips += 1
            elif sid not in always_prep:
                known_leveled += 1

        prep_leveled = 0
        for sid in self._draft_state.prepared_spells:
            if sid in always_prep:
                continue
            src = self._draft_state.spell_sources.get(sid, "")
            if src == caster.source_class_id or (not src and single_caster):
                el = self.repo.get(sid)
                if not el or el.setters.get("level", "0") != "0":
                    prep_leveled += 1
        return cantrips, known_leveled, prep_leveled

    def _refresh_spells_page(self) -> None:
        caster = self._active_target_caster()
        self._clear_layout(self.spell_selects_layout)
        spell_sels = self._newly_unlocked_selections(spell_only=True)

        if caster is None and not spell_sels:
            self.lbl_spell_status.setText("This class level does not unlock spellcasting.")
            self.spells_widget.hide()
            return

        self.spells_widget.show()
        if caster is not None:
            sc = self._draft_comp.spellcasting
            c_cnt, k_cnt, p_cnt = self._wizard_spell_counts(caster)
            slot_txt = ", ".join(f"L{k}:{v}" for k, v in sorted(sc.slots.items())) if sc else ""
            if sc and sc.pact_slots:
                slot_txt += (" | " if slot_txt else "") + "Pact: " + ", ".join(
                    f"L{k}:{v}" for k, v in sorted(sc.pact_slots.items())
                )
            self.lbl_spell_status.setText(
                f"{caster.source_class_name} Spellcasting ({caster.ability}) — Slots: {slot_txt or 'Cantrips'}"
            )
            limits = [f"Max Spell Level: {caster.max_spell_level}"]
            if caster.max_cantrips:
                limits.append(f"Cantrips: {c_cnt} / {caster.max_cantrips}")
            if caster.max_known_spells is not None:
                limits.append(f"Known/Book: {k_cnt} / {caster.max_known_spells}")
            if caster.max_prepared_spells is not None:
                limits.append(f"Prepared: {p_cnt} / {caster.max_prepared_spells}")
            if self.chk_override_spells.isChecked():
                limits.append("[Limit Override Active]")
            if caster.always_prepared_spell_ids:
                names = [self.repo.get(s).name if self.repo.get(s) else s for s in caster.always_prepared_spell_ids]
                limits.append(f"Always Prepared: {', '.join(names)}")
            self.lbl_spell_subinfo.setText("  •  ".join(limits))
        else:
            self.lbl_spell_status.setText("New Spell Choices Unlocked")
            self.lbl_spell_subinfo.setText("")

        for active_sel in spell_sels:
            self._render_selection_card(active_sel, self.spell_selects_layout)

        self._refresh_spell_catalog()
        self.lst_added_spells.clear()
        added_set = set(self._wizard_added_spells)
        if caster is not None:
            sc = self._draft_comp.spellcasting
            single_caster = bool(sc and len(sc.casters) == 1)
            granted_set = set(caster.granted_spell_ids)
            always_prep = set(caster.always_prepared_spell_ids)
            known_for_caster = [
                sid
                for sid in self._draft_state.known_spells
                if (
                    self._draft_state.spell_sources.get(sid, "") == caster.source_class_id
                    or (not self._draft_state.spell_sources.get(sid, "") and single_caster)
                )
            ]
            display_sids = list(dict.fromkeys([*known_for_caster, *caster.granted_spell_ids]))
            known_set = set(known_for_caster)
        else:
            granted_set = set()
            always_prep = set()
            display_sids = list(dict.fromkeys([*self._draft_state.known_spells, *self._wizard_added_spells]))
            known_set = set(display_sids)

        def _spell_sort_key(spell_id: str) -> tuple[int, str]:
            el_s = self.repo.get(spell_id)
            lvl_s = str(el_s.setters.get("level", "0")).strip() if el_s else "0"
            lvl_n = int(lvl_s) if lvl_s.isdigit() else 0
            return (lvl_n, (el_s.name if el_s else spell_id).lower())

        display_sids.sort(key=_spell_sort_key)
        prep_set = set(self._draft_state.prepared_spells) | self._wizard_prepared_spells
        for sid in display_sids:
            el = self.repo.get(sid)
            lvl = el.setters.get("level", "0") if el else "?"
            removable = (sid in known_set) or (sid in added_set)
            tags: list[str] = []
            if sid in added_set:
                tags.append("[New]")
            if sid in always_prep:
                tags.append("[Always Prepared]")
            elif sid in prep_set:
                tags.append("[Prepared]")
            if sid in granted_set and not removable:
                tags.append("[Granted]")
            tag_str = (" " + " ".join(tags)) if tags else ""
            it = QListWidgetItem(f"{el.name if el else sid} (Lv {lvl}){tag_str}")
            it.setData(Qt.ItemDataRole.UserRole, sid)
            it.setData(Qt.ItemDataRole.UserRole + 1, removable)
            self.lst_added_spells.addItem(it)

    def _refresh_spell_catalog(self) -> None:
        caster = self._active_target_caster()
        q = self.txt_spell_search.text().strip()
        spells = self.repo.search(q, ["Spell"])
        already = set(self._draft_state.known_spells) | set(
            self._draft_comp.spellcasting.granted_spell_ids if self._draft_comp.spellcasting else []
        )
        filtered: list[Element] = []
        for sp in spells:
            if sp.id in already or sp.id in self._wizard_added_spells:
                continue
            lvl_str = str(sp.setters.get("level", "0")).strip()
            lvl = int(lvl_str) if lvl_str.isdigit() else 0
            if caster is not None:
                if lvl > caster.max_spell_level:
                    continue
                if not is_spell_eligible_for_caster(sp, caster):
                    continue
            filtered.append(sp)
        filtered.sort(key=lambda e: (int(e.setters.get("level", "0")) if str(e.setters.get("level", "0")).isdigit() else 0, e.name.lower()))
        shown = filtered[:250]
        self.tbl_spell_catalog.setRowCount(len(shown))
        for r, el in enumerate(shown):
            it = QTableWidgetItem(el.name)
            it.setData(Qt.ItemDataRole.UserRole, el.id)
            self.tbl_spell_catalog.setItem(r, 0, it)
            self.tbl_spell_catalog.setItem(r, 1, QTableWidgetItem(str(el.setters.get("level", "0"))))

    def _on_spell_catalog_preview(self, row: int, _col: int) -> None:
        if 0 <= row < self.tbl_spell_catalog.rowCount():
            it = self.tbl_spell_catalog.item(row, 0)
            el = self.repo.get(it.data(Qt.ItemDataRole.UserRole)) if it else None
            if el:
                self.spell_desc_browser.setHtml(
                    f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>Level {el.setters.get('level', '0')} • {el.setters.get('school', '')}</p>"
                    f"{el.description_html or el.sheet_description or ''}"
                )

    def _on_added_spell_preview(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        el = self.repo.get(current.data(Qt.ItemDataRole.UserRole) or "")
        if el:
            self.spell_desc_browser.setHtml(
                f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>Level {el.setters.get('level', '0')} • {el.setters.get('school', '')}</p>"
                f"{el.description_html or el.sheet_description or ''}"
            )

    def _add_wizard_spell(self) -> None:
        row = self.tbl_spell_catalog.currentRow()
        if row < 0:
            return
        it = self.tbl_spell_catalog.item(row, 0)
        sid = it.data(Qt.ItemDataRole.UserRole) if it else ""
        if not sid or sid in self._wizard_added_spells:
            return

        caster = self._active_target_caster()
        el = self.repo.get(sid)
        lvl_str = str(el.setters.get("level", "0")).strip() if el else "0"
        lvl = int(lvl_str) if lvl_str.isdigit() else 0

        if not self.chk_override_spells.isChecked() and caster is not None:
            c_cnt, k_cnt, p_cnt = self._wizard_spell_counts(caster)
            if lvl == 0 and c_cnt >= caster.max_cantrips:
                QMessageBox.information(
                    self,
                    "Cantrip Limit Reached",
                    f"You already have {c_cnt} / {caster.max_cantrips} cantrips for {caster.source_class_name}.\n"
                    "Enable 'Override spell limits' to add more.",
                )
                return
            if lvl > 0 and caster.max_known_spells is not None and k_cnt >= caster.max_known_spells:
                QMessageBox.information(
                    self,
                    "Known Spell Limit Reached",
                    f"You already know {k_cnt} / {caster.max_known_spells} leveled spells for {caster.source_class_name}.\n"
                    "Enable 'Override spell limits' to add more.",
                )
                return
            if (
                lvl > 0
                and caster.max_known_spells is None
                and caster.max_prepared_spells is not None
                and p_cnt >= caster.max_prepared_spells
            ):
                QMessageBox.information(
                    self,
                    "Prepared Spell Limit Reached",
                    f"You already have {p_cnt} / {caster.max_prepared_spells} prepared spells for {caster.source_class_name}.\n"
                    "Enable 'Override spell limits' to add more.",
                )
                return

        if sid in self._wizard_removed_spells:
            self._wizard_removed_spells.remove(sid)
            if sid not in self._before_state.known_spells and sid not in self._wizard_added_spells:
                self._wizard_added_spells.append(sid)
        else:
            self._wizard_added_spells.append(sid)
        if caster and caster.prepare and lvl > 0:
            self._wizard_prepared_spells.add(sid)
        self._rebuild_draft()

    def _remove_wizard_spell(self) -> None:
        cur = self.lst_added_spells.currentItem()
        if cur is None:
            return
        sid = cur.data(Qt.ItemDataRole.UserRole) or ""
        removable = cur.data(Qt.ItemDataRole.UserRole + 1)
        if removable is False:
            QMessageBox.information(
                self,
                "Granted Spell",
                "This spell is automatically granted by a class or subclass feature and cannot be removed manually.",
            )
            return
        if sid in self._wizard_added_spells:
            self._wizard_added_spells.remove(sid)
            self._wizard_prepared_spells.discard(sid)
        elif sid in self._before_state.known_spells:
            if sid not in self._wizard_removed_spells:
                self._wizard_removed_spells.append(sid)
            self._wizard_prepared_spells.discard(sid)
        self._rebuild_draft()

    def _refresh_diff_page(self) -> None:
        diff = compute_character_diff(
            self._before_state,
            self._before_comp,
            self._draft_state,
            self._draft_comp,
            self.repo,
            target_class_id=self.current_target_class_id(),
        )
        self.diff_browser.setHtml(render_diff_html(diff))

    def _go_to_page(self, index: int) -> None:
        idx = max(0, min(len(self._STEP_TITLES) - 1, index))
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._step_pills):
            btn.setProperty("active", i == idx)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.btn_back.setEnabled(idx > 0)
        self.btn_next.setVisible(idx < len(self._STEP_TITLES) - 1)
        self.btn_apply.setVisible(idx == len(self._STEP_TITLES) - 1)
        if idx == len(self._STEP_TITLES) - 1:
            self._refresh_diff_page()

    def go_next(self) -> None:
        cur = self.stack.currentIndex()
        if cur == 0 and self.rad_multiclass.isChecked() and self._before_state.normalized_classes():
            target_el = self.repo.get(self.current_target_class_id())
            if target_el is not None and not self.chk_mc_override.isChecked():
                ok, msg = check_multiclass_prerequisites(self._before_state, self._before_comp, target_el, self.repo)
                if not ok:
                    QMessageBox.warning(
                        self,
                        "Multiclass Prerequisites Not Met",
                        f"{msg}.\n\nCheck 'Override multiclassing ability prerequisites' to proceed anyway.",
                    )
                    return
        self._go_to_page(cur + 1)

    def go_back(self) -> None:
        self._go_to_page(self.stack.currentIndex() - 1)

    def _on_apply(self) -> None:
        self._rebuild_draft()
        self.accept()

    def result_state(self) -> CharacterState:
        return copy.deepcopy(self._draft_state)
