"""Abilities tab mixin."""

from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...models import ABILITIES
from ..widgets.item_icons import _fmt_mod

POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}


class AbilitiesTabMixin:
    def _build_tab_abilities(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        btn_row = QHBoxLayout()
        btn_std = QPushButton("Apply Standard Array (15, 14, 13, 12, 10, 8)")
        btn_std.clicked.connect(self._apply_standard_array)
        btn_roll = QPushButton("Roll 4d6 Drop Lowest")
        btn_roll.clicked.connect(self._roll_abilities)
        self.lbl_point_buy = QLabel("Point Buy: 27 / 27 used")
        self.lbl_point_buy.setObjectName("AccentText")
        btn_row.addWidget(btn_std)
        btn_row.addWidget(btn_roll)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_point_buy)
        layout.addLayout(btn_row)

        ov_row = QHBoxLayout()
        self.chk_override_point_buy = QCheckBox("Override Point Buy (allow custom / rolled scores)")
        self.chk_override_point_buy.stateChanged.connect(self._on_ability_overrides_toggled)
        self.chk_override_asi_cap = QCheckBox("Allow Ability Scores Above 20")
        self.chk_override_asi_cap.stateChanged.connect(self._on_ability_overrides_toggled)
        ov_row.addWidget(self.chk_override_point_buy)
        ov_row.addSpacing(12)
        ov_row.addWidget(self.chk_override_asi_cap)
        ov_row.addStretch()
        layout.addLayout(ov_row)

        grid_box = QGroupBox("Ability Scores")
        grid = QGridLayout(grid_box)
        headers = ["Ability", "Base Score", "Bonus", "Total", "Modifier"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setObjectName("SectionHeading")
            grid.addWidget(lbl, 0, col)

        self.ab_spinboxes: dict[str, QSpinBox] = {}
        self.ab_minus_btns: dict[str, QPushButton] = {}
        self.ab_plus_btns: dict[str, QPushButton] = {}
        self.ab_bonus_labels: dict[str, QLabel] = {}
        self.ab_total_labels: dict[str, QLabel] = {}
        self.ab_mod_labels: dict[str, QLabel] = {}

        for row, ab in enumerate(ABILITIES, start=1):
            grid.addWidget(QLabel(ab.capitalize()), row, 0)
            ctrl_box = QHBoxLayout()
            btn_m = QPushButton("-")
            btn_m.setObjectName("StepperBtn")
            spn = QSpinBox()
            spn.setObjectName("StepperSpin")
            spn.setRange(8, 15)
            spn.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spn.setFixedWidth(68)
            spn.valueChanged.connect(self._on_ability_changed)
            btn_p = QPushButton("+")
            btn_p.setObjectName("StepperBtn")
            btn_m.clicked.connect(lambda _=False, a=ab: self._step_ability(a, -1))
            btn_p.clicked.connect(lambda _=False, a=ab: self._step_ability(a, 1))
            ctrl_box.addWidget(btn_m)
            ctrl_box.addWidget(spn)
            ctrl_box.addWidget(btn_p)
            ctrl_box.addStretch()
            grid.addLayout(ctrl_box, row, 1)

            b_lbl = QLabel("+0")
            t_lbl = QLabel("10")
            m_lbl = QLabel("+0")
            t_lbl.setStyleSheet("font-weight:bold; background:transparent;")
            m_lbl.setObjectName("AccentText")
            grid.addWidget(b_lbl, row, 2)
            grid.addWidget(t_lbl, row, 3)
            grid.addWidget(m_lbl, row, 4)

            self.ab_spinboxes[ab] = spn
            self.ab_minus_btns[ab] = btn_m
            self.ab_plus_btns[ab] = btn_p
            self.ab_bonus_labels[ab] = b_lbl
            self.ab_total_labels[ab] = t_lbl
            self.ab_mod_labels[ab] = m_lbl

        layout.addWidget(grid_box)
        layout.addStretch()
        return tab

    def _is_point_buy_enforced(self) -> bool:
        return not (
            self.state.has_override("override_point_buy")
            or self.state.has_override("override_asi_cap")
        )

    def _sync_abilities_tab(self) -> None:
        asi_cap_ov = self.state.has_override("override_asi_cap")
        pb_enforced = self._is_point_buy_enforced()
        self.chk_override_point_buy.setChecked(self.state.has_override("override_point_buy"))
        self.chk_override_asi_cap.setChecked(asi_cap_ov)

        used_pts = 0
        valid_pb = True
        for ab in ABILITIES:
            base = int(self.state.abilities.get(ab, 10))
            if base in POINT_BUY_COSTS:
                used_pts += POINT_BUY_COSTS[base]
            else:
                valid_pb = False

        max_unrestricted = 30 if asi_cap_ov else 20
        for ab in ABILITIES:
            base = int(self.state.abilities.get(ab, 10))
            spn = self.ab_spinboxes[ab]
            if pb_enforced and valid_pb:
                other_pts = used_pts - POINT_BUY_COSTS.get(base, 0)
                max_for_ab = base
                for cand in range(8, 16):
                    if other_pts + POINT_BUY_COSTS[cand] <= 27:
                        max_for_ab = cand
                min_for_ab = min(8, base)
                spn.setRange(min_for_ab, max(max_for_ab, base))
                self.ab_minus_btns[ab].setEnabled(base > min_for_ab)
                self.ab_plus_btns[ab].setEnabled(base < max_for_ab)
            else:
                spn.setRange(3, max_unrestricted)
                self.ab_minus_btns[ab].setEnabled(base > 3)
                self.ab_plus_btns[ab].setEnabled(base < max_unrestricted)

            spn.setValue(base)
            bonus = self.computed.ability_bonuses[ab]
            tot = self.computed.ability_totals[ab]
            mod = self.computed.ability_modifiers[ab]
            self.ab_bonus_labels[ab].setText(_fmt_mod(bonus))
            self.ab_total_labels[ab].setText(str(tot))
            self.ab_mod_labels[ab].setText(_fmt_mod(mod))

        if pb_enforced and valid_pb:
            rem = 27 - used_pts
            self.lbl_point_buy.setText(f"Point Buy: {used_pts} / 27 used ({rem} left)")
        elif valid_pb:
            self.lbl_point_buy.setText(f"Point Buy: {used_pts} / 27 (Override Active)")
        else:
            self.lbl_point_buy.setText("Point Buy: Custom / Rolled (Override Active)")

    def _step_ability(self, ab: str, delta: int) -> None:
        spn = self.ab_spinboxes[ab]
        spn.setValue(max(spn.minimum(), min(spn.maximum(), spn.value() + delta)))

    def _on_ability_overrides_toggled(self) -> None:
        if self._updating:
            return
        self.state.set_override("override_point_buy", self.chk_override_point_buy.isChecked())
        self.state.set_override("override_asi_cap", self.chk_override_asi_cap.isChecked())
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_ability_changed(self) -> None:
        if self._updating:
            return
        pb_enforced = self._is_point_buy_enforced()
        candidate = {ab: spn.value() for ab, spn in self.ab_spinboxes.items()}
        if pb_enforced:
            if all(v in POINT_BUY_COSTS for v in candidate.values()):
                cost = sum(POINT_BUY_COSTS[v] for v in candidate.values())
                if cost > 27:
                    self._sync_abilities_tab()
                    return
            else:
                self._sync_abilities_tab()
                return
        for ab, val in candidate.items():
            self.state.abilities[ab] = val
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _apply_standard_array(self) -> None:
        for ab, score in zip(ABILITIES, [15, 14, 13, 12, 10, 8]):
            self.state.abilities[ab] = score
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _roll_abilities(self) -> None:
        if self._is_point_buy_enforced():
            reply = QMessageBox.question(
                self,
                "Point Buy Enforced",
                "Point Buy is enforced by default. Enable 'Override Point Buy' to roll 4d6 Drop Lowest?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.state.set_override("override_point_buy", True)
        for ab in ABILITIES:
            rolls = sorted(random.randint(1, 6) for _ in range(4))
            self.state.abilities[ab] = sum(rolls[1:])
        self._mark_dirty()
        self._recalculate_and_refresh()
