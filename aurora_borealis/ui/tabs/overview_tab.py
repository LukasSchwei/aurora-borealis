"""Overview tab, HP mode panel, and multiclass management mixin."""

from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...engine import (
    check_multiclass_prerequisites,
    class_display_summary,
    level_for_xp,
    sync_xp_to_level,
    xp_for_level,
)
from ...models import ABILITIES, ABILITY_ABBR, ClassLevel
from ...rules_55e import DIVINE_ORDER_55E, PRIMAL_ORDER_55E, get_55e_background_abilities
from ..dialogs import RuleOverridesDialog
from ..icons import apply_button_icon
from ..level_up_wizard import LevelUpWizardDialog
from ..ui_helpers import fit_button
from ..widgets.item_icons import _fmt_mod


class OverviewTabMixin:
    def _build_tab_overview(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame_NoFrame())
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.overview_scroll = scroll

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        top_box = QGroupBox("Character Summary && Ruleset")
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
        lvl_row.addSpacing(12)
        self.btn_overview_level_up = QPushButton("Level Up Wizard")
        apply_button_icon(self.btn_overview_level_up, "arrow-up-circle", size=15)
        self.btn_overview_level_up.clicked.connect(self.open_level_up_wizard)
        lvl_row.addWidget(self.btn_overview_level_up)
        lvl_row.addSpacing(12)
        lvl_row.addWidget(QLabel("XP:"))
        self.spn_xp = QSpinBox()
        self.spn_xp.setRange(0, 999999)
        self.spn_xp.setSingleStep(100)
        self.spn_xp.setFixedWidth(132)
        self.spn_xp.valueChanged.connect(self._on_xp_changed)
        lvl_row.addWidget(self.spn_xp)
        lvl_row.addStretch()

        form.addRow("Character Name:", self.txt_overview_name)
        form.addRow("Ruleset:", self.cmb_ruleset)
        form.addRow("Level / XP:", lvl_row)
        layout.addWidget(top_box)

        # Hit Points Mode (Average vs Rolled / Manual)
        self.hp_group = QGroupBox("Hit Points Calculation")
        hp_v = QVBoxLayout(self.hp_group)
        hp_v.setSpacing(8)
        hp_top = QHBoxLayout()
        hp_top.addWidget(QLabel("HP Mode:"))
        self.cmb_hp_mode = QComboBox()
        self.cmb_hp_mode.addItem("Average (Fixed)", "average")
        self.cmb_hp_mode.addItem("Rolled / Manual", "rolled")
        self.cmb_hp_mode.currentIndexChanged.connect(self._on_hp_mode_changed)
        self.btn_roll_all_hp = QPushButton("Roll All HP")
        apply_button_icon(self.btn_roll_all_hp, "dice", size=15)
        self.btn_roll_all_hp.clicked.connect(self._roll_all_hp)
        self.btn_reset_avg_hp = QPushButton("Reset to Average")
        self.btn_reset_avg_hp.clicked.connect(self._reset_average_hp)
        self.lbl_hp_formula = QLabel("Max HP: 0")
        self.lbl_hp_formula.setObjectName("AccentText")
        self.lbl_hp_formula.setWordWrap(True)
        hp_top.addWidget(self.cmb_hp_mode)
        hp_top.addWidget(self.btn_roll_all_hp)
        hp_top.addWidget(self.btn_reset_avg_hp)
        hp_top.addSpacing(12)
        hp_top.addWidget(self.lbl_hp_formula, 1)
        hp_v.addLayout(hp_top)

        self.tbl_hp_rolls = QTableWidget(0, 6)
        self.tbl_hp_rolls.setHorizontalHeaderLabels(["Lvl", "Class", "Die", "Roll", "CON", "Total"])
        hp_hdr = self.tbl_hp_rolls.horizontalHeader()
        hp_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hp_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hp_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hp_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hp_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hp_hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.tbl_hp_rolls.setColumnWidth(0, 50)
        self.tbl_hp_rolls.setColumnWidth(2, 62)
        self.tbl_hp_rolls.setColumnWidth(3, 196)
        self.tbl_hp_rolls.setColumnWidth(4, 62)
        self.tbl_hp_rolls.setColumnWidth(5, 72)
        self.tbl_hp_rolls.verticalHeader().setVisible(False)
        self.tbl_hp_rolls.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_hp_rolls.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_hp_rolls.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_hp_rolls.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        hp_v.addWidget(self.tbl_hp_rolls)
        layout.addWidget(self.hp_group)

        # 5.5e Rules & Combat Status
        self.rules_55e_group = QGroupBox("5.5e (2024) Mechanics && Orders")
        r55_v = QVBoxLayout(self.rules_55e_group)
        r55_row = QHBoxLayout()
        self.chk_heroic_inspiration = QCheckBox("Heroic Inspiration")
        self.chk_heroic_inspiration.stateChanged.connect(self._on_55e_controls_changed)
        r55_row.addWidget(self.chk_heroic_inspiration)
        r55_row.addSpacing(12)
        r55_row.addWidget(QLabel("Exhaustion (0–6):"))
        self.spn_exhaustion = QSpinBox()
        self.spn_exhaustion.setRange(0, 6)
        self.spn_exhaustion.setFixedWidth(84)
        self.spn_exhaustion.valueChanged.connect(self._on_55e_controls_changed)
        r55_row.addWidget(self.spn_exhaustion)
        r55_row.addStretch()
        r55_v.addLayout(r55_row)

        r55_orders_row = QHBoxLayout()
        self.lbl_divine_order = QLabel("Divine Order:")
        self.cmb_divine_order = QComboBox()
        self.cmb_divine_order.addItem("— Choose —", "")
        for k, desc in DIVINE_ORDER_55E.items():
            self.cmb_divine_order.addItem(desc, k)
        self.cmb_divine_order.currentIndexChanged.connect(self._on_55e_controls_changed)
        r55_orders_row.addWidget(self.lbl_divine_order)
        r55_orders_row.addWidget(self.cmb_divine_order)
        r55_orders_row.addSpacing(12)

        self.lbl_primal_order = QLabel("Primal Order:")
        self.cmb_primal_order = QComboBox()
        self.cmb_primal_order.addItem("— Choose —", "")
        for k, desc in PRIMAL_ORDER_55E.items():
            self.cmb_primal_order.addItem(desc, k)
        self.cmb_primal_order.currentIndexChanged.connect(self._on_55e_controls_changed)
        r55_orders_row.addWidget(self.lbl_primal_order)
        r55_orders_row.addWidget(self.cmb_primal_order)
        r55_orders_row.addStretch()
        r55_v.addLayout(r55_orders_row)

        self.lbl_55e_notes = QLabel("")
        self.lbl_55e_notes.setObjectName("MutedText")
        self.lbl_55e_notes.setWordWrap(True)
        r55_v.addWidget(self.lbl_55e_notes)
        layout.addWidget(self.rules_55e_group)

        # Clickable Quick-Jump Step Cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(12)

        self.btn_card_race = self._make_overview_card("1. Race / Species", "Not selected — click to choose", 1)
        self.btn_card_class = self._make_overview_card("2. Class", "Not selected — click to choose", 2)
        self.btn_card_bg = self._make_overview_card("3. Background", "Not selected — click to choose", 3)
        self.btn_card_choices = self._make_overview_card("4. Choices && Feats", "0 pending choices", 5)
        self.btn_card_abilities = self._make_overview_card("5. Ability Scores", "Click to adjust scores", 4)
        self.btn_card_spells = self._make_overview_card("6. Equipment && Spells", "Click to manage gear", 7)

        cards_grid.addWidget(self.btn_card_race, 0, 0)
        cards_grid.addWidget(self.btn_card_class, 0, 1)
        cards_grid.addWidget(self.btn_card_bg, 1, 0)
        cards_grid.addWidget(self.btn_card_choices, 1, 1)
        cards_grid.addWidget(self.btn_card_abilities, 2, 0)
        cards_grid.addWidget(self.btn_card_spells, 2, 1)
        layout.addLayout(cards_grid)
        layout.addStretch()
        scroll.setWidget(tab)
        return scroll

    def _make_overview_card(self, title: str, subtitle: str, target_tab: int) -> QPushButton:
        btn = QPushButton(f"{title}\n\n{subtitle}")
        btn.setObjectName("OverviewCard")
        btn.setMinimumHeight(110)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._switch_builder_tab(target_tab))
        return btn

    def _sync_overview_and_selectors(self) -> None:
        is_55e = self.state.ruleset == "5.5e"
        self.tab_race.set_title("Species" if is_55e else "Race")
        self.nav_buttons[1].setText("Species" if is_55e else "Race")
        fit_button(self.nav_buttons[1])

        self.bg_asi_group.setVisible(is_55e)
        self.rules_55e_group.setVisible(is_55e)
        self.chk_heroic_inspiration.setChecked(bool(self.state.heroic_inspiration))
        self.spn_exhaustion.setValue(int(self.state.exhaustion_level))
        cls_names_lower = {
            (self.repo.get(cl.class_id).name.lower() if self.repo.get(cl.class_id) else "")
            for cl in self.state.normalized_classes()
        }
        has_cleric = any("cleric" in n for n in cls_names_lower) or bool(self.state.divine_order_55e)
        has_druid = any("druid" in n for n in cls_names_lower) or bool(self.state.primal_order_55e)
        self.lbl_divine_order.setVisible(has_cleric)
        self.cmb_divine_order.setVisible(has_cleric)
        self._set_combo_by_data(self.cmb_divine_order, self.state.divine_order_55e)
        self.lbl_primal_order.setVisible(has_druid)
        self.cmb_primal_order.setVisible(has_druid)
        self._set_combo_by_data(self.cmb_primal_order, self.state.primal_order_55e)
        self.lbl_55e_notes.setText(
            " • ".join(self.computed.ruleset_55e_notes)
            if self.computed.ruleset_55e_notes
            else "2024 PHB active: Lv 3 subclass standardization, Weapon Masteries, Origin Feats, Lv 19 Epic Boons, Exhaustion 0–6 (-2/level d20 & DC)."
        )
        active_ov = sum(1 for v in self.state.rule_overrides.values() if v)
        if self.state.allow_extra_spells and not self.state.rule_overrides.get("allow_extra_spells"):
            active_ov += 1
        self.btn_rule_overrides.setText(
            f"Rule Overrides ({active_ov})" if active_ov else "Rule Overrides"
        )
        fit_button(self.btn_rule_overrides)

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
            if self.spn_xp.value() != self.state.xp:
                self.spn_xp.setValue(self.state.xp)
            cur_th = xp_for_level(self.state.level)
            nxt_txt = (
                f"Next level (Lv {self.state.level + 1}): {xp_for_level(self.state.level + 1):,} XP"
                if self.state.level < 20
                else "Maximum Level reached"
            )
            self.spn_xp.setToolTip(f"Level {self.state.level}: {cur_th:,} XP • {nxt_txt}")

        self.tab_race.sync_selected(self.state.race_id)
        self.tab_class.sync_selected(self.state.class_id)
        self.tab_background.sync_selected(self.state.background_id)

        race_el = self.repo.get(self.state.race_id)
        cls_summary = class_display_summary(self.state, self.repo)

        can_level_up = self.state.level < 20
        for btn in (self.btn_level_up, self.btn_overview_level_up, self.btn_class_level_up):
            btn.setEnabled(can_level_up)

        self._sync_hp_panel()
        self._sync_multiclass_panel()

        self.btn_card_race.setText(
            f"1. {'Species' if is_55e else 'Race'}\n\n"
            + (race_el.name if race_el else "Not selected — click to choose")
        )
        if race_el:
            apply_button_icon(self.btn_card_race, "check", theme=self.config.theme, size=18, fixed_color="#34d399")
        else:
            self.btn_card_race.setIcon(QIcon())

        self.btn_card_class.setText(
            "2. Class\n\n"
            + (cls_summary if cls_summary else "Not selected — click to choose")
        )
        if cls_summary:
            apply_button_icon(self.btn_card_class, "check", theme=self.config.theme, size=18, fixed_color="#34d399")
        else:
            self.btn_card_class.setIcon(QIcon())

        self.btn_card_bg.setText(
            "3. Background\n\n"
            + (bg_el.name if bg_el else "Not selected — click to choose")
        )
        if bg_el:
            apply_button_icon(self.btn_card_bg, "check", theme=self.config.theme, size=18, fixed_color="#34d399")
        else:
            self.btn_card_bg.setIcon(QIcon())
        self.btn_card_abilities.setText(
            "5. Ability Scores\n\n"
            + " | ".join(f"{ABILITY_ABBR[a]} {self.computed.ability_totals[a]}" for a in ABILITIES)
        )
        self.btn_card_spells.setText(
            "6. Equipment && Spells\n\n"
            f"{len(self.state.inventory)} items • {len(self.state.known_spells)} spells"
        )

    def select_race_by_id(self, race_id: str) -> None:
        self.state.race_id = race_id
        self._mark_dirty()
        self._recalculate_and_refresh()

    def select_class_by_id(self, class_id: str) -> None:
        if not class_id:
            self.state.classes = []
            self.state.class_id = ""
            self.state.level_order = []
        else:
            norm = self.state.normalized_classes()
            if not norm:
                self.state.classes = [ClassLevel(class_id, max(1, min(20, int(self.state.level or 1))))]
                self.state.level_order = [class_id] * self.state.classes[0].level
            else:
                old_primary = norm[0].class_id
                norm = [cl for cl in norm if cl.class_id != class_id or cl.class_id == old_primary]
                norm[0] = ClassLevel(class_id, norm[0].level)
                self.state.classes = norm
                self.state.level_order = [class_id if c == old_primary else c for c in self.state.level_order]
            self.state.sync_from_classes()
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
        self.lbl_char_name.setText(text or "New Adventurer")
        self.lbl_top_name.setText(text or "New Adventurer")
        self.title_bar.set_breadcrumb(text or "New Adventurer")
        self._updating = True
        try:
            self.txt_name.setText(text)
        finally:
            self._updating = False
        self._mark_dirty()

    def _on_ruleset_changed(self) -> None:
        if self._updating:
            return
        self.state.ruleset = self.cmb_ruleset.currentData() or "5e"
        if self.state.ruleset == "5.5e" and self.state.background_id and not self.state.background_asi:
            allowed = get_55e_background_abilities(self.repo.get(self.state.background_id))
            self.state.background_asi = {allowed[0]: 2, allowed[1]: 1}
        self._choices_sig = None
        self._mark_dirty()
        self._recalculate_and_refresh()

    def open_rule_overrides_dialog(self) -> None:
        dlg = RuleOverridesDialog(self.state, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            overrides = dlg.selected_overrides()
            self.state.rule_overrides = {k: bool(v) for k, v in overrides.items() if v}
            self.state.allow_extra_spells = bool(overrides.get("allow_extra_spells", False))
            self._choices_sig = None
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _on_55e_controls_changed(self) -> None:
        if self._updating:
            return
        self.state.heroic_inspiration = self.chk_heroic_inspiration.isChecked()
        self.state.exhaustion_level = self.spn_exhaustion.value()
        self.state.divine_order_55e = self.cmb_divine_order.currentData() or ""
        self.state.primal_order_55e = self.cmb_primal_order.currentData() or ""
        self._choices_sig = None
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _apply_total_level(self, target_lvl: int) -> None:
        new_val = max(1, min(20, int(target_lvl or 1)))
        norm = self.state.normalized_classes()
        if not norm:
            self.state.level = new_val
        elif len(norm) == 1:
            norm[0].level = new_val
            self.state.classes = norm
            self.state.sync_from_classes()
        else:
            cur_total = sum(c.level for c in norm)
            if new_val > cur_total:
                norm[0].level += new_val - cur_total
            elif new_val < cur_total:
                to_trim = cur_total - new_val
                for cl in reversed(norm):
                    take = min(to_trim, max(0, cl.level - 1))
                    cl.level -= take
                    to_trim -= take
                    if to_trim <= 0:
                        break
            self.state.classes = norm
            self.state.sync_from_classes()

    def _on_level_changed(self) -> None:
        if self._updating:
            return
        new_val = max(1, min(20, self.spn_level.value()))
        self._apply_total_level(new_val)
        sync_xp_to_level(self.state)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _sync_hp_panel(self) -> None:
        if not hasattr(self, "cmb_hp_mode"):
            return
        self._set_combo_by_data(self.cmb_hp_mode, self.state.hp_mode or "average")
        is_rolled = self.state.hp_mode == "rolled"
        self.btn_roll_all_hp.setVisible(is_rolled)
        self.btn_reset_avg_hp.setVisible(is_rolled)
        self.tbl_hp_rolls.setVisible(is_rolled)

        con_mod = self.computed.ability_modifiers["constitution"]
        rows = self.computed.hp_breakdown
        mode_tag = "Rolled / Manual" if is_rolled else "Average (Fixed)"
        self.lbl_hp_formula.setText(
            f"Max HP: {self.computed.max_hp} ({mode_tag} • Hit Dice: {self.computed.hit_dice_summary or self.computed.hit_die} • CON {_fmt_mod(con_mod)})"
        )

        if not is_rolled:
            return

        self.tbl_hp_rolls.setRowCount(len(rows))
        max_row_h = max(42, round(42 * self.config.ui_scale))
        max_col3_w = max(196, round(196 * self.config.ui_scale))
        for r, row_data in enumerate(rows):
            lvl_i = int(row_data["level"])
            hd_num = int(row_data["hd_num"])
            die_val = int(row_data["roll"])
            self.tbl_hp_rolls.setItem(r, 0, QTableWidgetItem(str(lvl_i)))
            self.tbl_hp_rolls.setItem(r, 1, QTableWidgetItem(str(row_data["class_name"])))
            self.tbl_hp_rolls.setItem(r, 2, QTableWidgetItem(str(row_data["hit_die"])))

            cell_w = QWidget()
            cl = QHBoxLayout(cell_w)
            cl.setContentsMargins(2, 2, 2, 2)
            cl.setSpacing(4)
            spn = QSpinBox()
            spn.setRange(1, hd_num)
            spn.setValue(die_val)
            spn.setFixedWidth(max(84, round(84 * self.config.ui_scale)))
            btn_r = QPushButton(f"d{hd_num}")
            btn_r.setObjectName("CompactCardBtn")
            btn_r.setToolTip(f"Roll 1d{hd_num} for Level {lvl_i}")

            def make_roll_spin_handler(level_num: int):
                def _on_val(val: int) -> None:
                    if self._updating:
                        return
                    self.state.hp_rolls[level_num] = val
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_val

            def make_roll_btn_handler(level_num: int, die_sides: int):
                def _on_click() -> None:
                    self.state.hp_rolls[level_num] = random.randint(1, die_sides)
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_click

            spn.valueChanged.connect(make_roll_spin_handler(lvl_i))
            btn_r.clicked.connect(make_roll_btn_handler(lvl_i, hd_num))
            cl.addWidget(spn)
            cl.addWidget(btn_r)
            self.tbl_hp_rolls.setCellWidget(r, 3, cell_w)
            cell_w.ensurePolished()
            spn.ensurePolished()
            btn_r.ensurePolished()
            spn.updateGeometry()
            cell_w.updateGeometry()
            cell_h = max(max_row_h, spn.sizeHint().height() + 8, cell_w.sizeHint().height() + 6)
            max_row_h = max(max_row_h, cell_h)
            max_col3_w = max(max_col3_w, cell_w.sizeHint().width() + 12)

            self.tbl_hp_rolls.setItem(r, 4, QTableWidgetItem(_fmt_mod(int(row_data["con_mod"]))))
            self.tbl_hp_rolls.setItem(r, 5, QTableWidgetItem(str(row_data["total"])))

        hp_vh = self.tbl_hp_rolls.verticalHeader()
        hp_vh.setMinimumSectionSize(max_row_h)
        hp_vh.setDefaultSectionSize(max_row_h)
        for r in range(len(rows)):
            self.tbl_hp_rolls.setRowHeight(r, max_row_h)
        self.tbl_hp_rolls.setColumnWidth(3, max_col3_w)

        hdr_h = max(28, self.tbl_hp_rolls.horizontalHeader().sizeHint().height())
        total_h = hdr_h + len(rows) * max_row_h + 2 * self.tbl_hp_rolls.frameWidth() + 6
        self.tbl_hp_rolls.setMinimumHeight(total_h)
        self.tbl_hp_rolls.setFixedHeight(total_h)

    def _on_hp_mode_changed(self) -> None:
        if self._updating:
            return
        mode = self.cmb_hp_mode.currentData() or "average"
        self.state.hp_mode = mode
        if mode == "rolled":
            for row_data in self.computed.hp_breakdown:
                lvl_i = int(row_data["level"])
                if lvl_i not in self.state.hp_rolls:
                    self.state.hp_rolls[lvl_i] = int(row_data["roll"])
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _roll_all_hp(self) -> None:
        self.state.hp_mode = "rolled"
        for row_data in self.computed.hp_breakdown:
            lvl_i = int(row_data["level"])
            hd_num = int(row_data["hd_num"])
            self.state.hp_rolls[lvl_i] = hd_num if lvl_i == 1 else random.randint(1, hd_num)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _reset_average_hp(self) -> None:
        self.state.hp_mode = "average"
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _sync_multiclass_panel(self) -> None:
        if not hasattr(self, "multiclass_rows_layout"):
            return
        self._clear_layout(self.multiclass_rows_layout)
        norm = self.state.normalized_classes()
        active_ids = {c.class_id for c in norm}
        total_lvl = sum(c.level for c in norm)

        if not norm:
            lbl = QLabel("Select a primary class below first, then add multiclasses here.")
            lbl.setObjectName("MutedText")
            self.multiclass_rows_layout.addWidget(lbl)
        else:
            for idx, cl in enumerate(norm):
                cel = self.repo.get(cl.class_id)
                cname = cel.name if cel else cl.class_id
                hd = cel.setters.get("hd", "d8") if cel else "d8"
                row_w = QWidget()
                rl = QHBoxLayout(row_w)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(6)
                tag = " [Primary]" if idx == 0 else " [Multiclass]"
                lbl = QLabel(f"<b>{cname}</b> <span style='color:#94a3b8;'>({hd}){tag}</span>")
                rl.addWidget(lbl, 1)

                btn_m = QPushButton("-")
                btn_m.setObjectName("StepperBtn")
                btn_m.setEnabled(cl.level > 1)
                spn = QSpinBox()
                spn.setObjectName("StepperSpin")
                spn.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                spn.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spn.setFixedWidth(max(56, round(56 * self.config.ui_scale)))
                spn.setRange(1, max(1, 20 - (total_lvl - cl.level)))
                spn.setValue(cl.level)
                btn_p = QPushButton("+")
                btn_p.setObjectName("StepperBtn")
                btn_p.setEnabled(total_lvl < 20)

                def make_mc_lvl(cid: str):
                    def _chg(val: int) -> None:
                        if self._updating:
                            return
                        self.set_class_level(cid, val)

                    return _chg

                btn_m.clicked.connect(lambda _=False, cid=cl.class_id, lv=cl.level: self.set_class_level(cid, max(1, lv - 1)))
                btn_p.clicked.connect(lambda _=False, cid=cl.class_id, lv=cl.level: self.set_class_level(cid, lv + 1))
                spn.valueChanged.connect(make_mc_lvl(cl.class_id))
                rl.addWidget(btn_m)
                rl.addWidget(spn)
                rl.addWidget(btn_p)

                if idx > 0:
                    btn_rem = QPushButton("Remove")
                    btn_rem.setObjectName("DangerBtn")
                    btn_rem.clicked.connect(lambda _=False, cid=cl.class_id: self.remove_multiclass(cid))
                    rl.addWidget(btn_rem)
                self.multiclass_rows_layout.addWidget(row_w)

        self.cmb_add_multiclass.blockSignals(True)
        self.cmb_add_multiclass.clear()
        for cel in self.repo.of_type("Class"):
            if cel.id not in active_ids:
                self.cmb_add_multiclass.addItem(cel.name, cel.id)
        self.cmb_add_multiclass.blockSignals(False)
        can_add = bool(norm) and total_lvl < 20 and self.cmb_add_multiclass.count() > 0
        self.cmb_add_multiclass.setEnabled(can_add)
        self.btn_add_multiclass.setEnabled(can_add)

    def _on_add_multiclass_clicked(self) -> None:
        cid = self.cmb_add_multiclass.currentData() or ""
        if not cid:
            return
        cel = self.repo.get(cid)
        if cel is not None and self.state.normalized_classes():
            ok, msg = check_multiclass_prerequisites(self.state, self.computed, cel, self.repo)
            if not ok:
                reply = QMessageBox.warning(
                    self,
                    "Multiclass Prerequisites Not Met",
                    f"{msg}.\n\nAdd {cel.name} anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
        self.add_multiclass(cid, 1)

    def add_multiclass(self, class_id: str, level: int = 1) -> None:
        if not class_id:
            return
        norm = self.state.normalized_classes()
        total = sum(c.level for c in norm)
        avail = max(0, 20 - total)
        if avail <= 0:
            return
        add_lvl = min(max(1, level), avail)
        for cl in norm:
            if cl.class_id == class_id:
                cl.level += add_lvl
                break
        else:
            norm.append(ClassLevel(class_id, add_lvl))
        self.state.classes = norm
        if not self.state.level_order:
            self.state.level_order = self.state.normalized_level_order()
        self.state.level_order.extend([class_id] * add_lvl)
        self.state.sync_from_classes()
        sync_xp_to_level(self.state)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def remove_multiclass(self, class_id: str) -> None:
        norm = [cl for cl in self.state.normalized_classes() if cl.class_id != class_id]
        self.state.classes = norm
        self.state.level_order = [cid for cid in self.state.level_order if cid != class_id]
        self.state.sync_from_classes()
        sync_xp_to_level(self.state)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def set_class_level(self, class_id: str, level: int) -> None:
        norm = self.state.normalized_classes()
        other_sum = sum(c.level for c in norm if c.class_id != class_id)
        target_lvl = max(1, min(max(1, 20 - other_sum), int(level)))
        for cl in norm:
            if cl.class_id == class_id:
                cl.level = target_lvl
                break
        self.state.classes = norm
        self.state.sync_from_classes()
        sync_xp_to_level(self.state)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def open_level_up_wizard(self) -> None:
        if self.state.level >= 20 and self.state.normalized_classes():
            QMessageBox.information(self, "Max Level Reached", "Character is already at Level 20.")
            return
        dlg = LevelUpWizardDialog(self.state, self.repo, self.engine, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.state = dlg.result_state()
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _on_xp_changed(self, val: int) -> None:
        if self._updating:
            return
        self.state.xp = max(0, int(val))
        target_lvl = level_for_xp(self.state.xp)
        self._mark_dirty()
        if target_lvl != self.state.level:
            self._apply_total_level(target_lvl)
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


def QFrame_NoFrame():
    from PySide6.QtWidgets import QFrame

    return QFrame.Shape.NoFrame
