"""Skills, Saving Throws, Senses, Resistances, Sheet Actions, and Features tab mixin."""

from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..ui_helpers import configure_dropdown_combo
from ..widgets.item_icons import _fmt_mod
from ...models import ABILITIES, ABILITY_ABBR


class SkillsFeaturesTabMixin:
    def _build_tab_skills_features(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        row_h = 22
        header_h = 24
        saves_group = QGroupBox("Saving Throws")
        saves_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        saves_layout = QVBoxLayout(saves_group)
        saves_layout.setContentsMargins(6, 6, 6, 6)
        self.tbl_saves = QTableWidget(6, 3)
        self.tbl_saves.setHorizontalHeaderLabels(["Ability", "Prof", "Bonus"])
        saves_hdr = self.tbl_saves.horizontalHeader()
        saves_hdr.setMinimumHeight(header_h)
        saves_hdr.setFixedHeight(header_h)
        saves_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        saves_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        saves_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tbl_saves.setColumnWidth(1, 48)
        self.tbl_saves.setColumnWidth(2, 58)
        self.tbl_saves.verticalHeader().setVisible(False)
        self.tbl_saves.verticalHeader().setMinimumSectionSize(row_h)
        self.tbl_saves.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tbl_saves.verticalHeader().setDefaultSectionSize(row_h)
        for r in range(6):
            self.tbl_saves.setRowHeight(r, row_h)
        self.tbl_saves.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_saves.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_saves.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_saves.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tbl_saves.setFixedHeight(header_h + 6 * row_h + 2 * self.tbl_saves.frameWidth() + 2)
        self.tbl_saves.cellClicked.connect(self._on_save_cell_clicked)
        saves_layout.addWidget(self.tbl_saves)
        left_layout.addWidget(saves_group)

        skills_group = QGroupBox("Skills")
        skills_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        skills_layout = QVBoxLayout(skills_group)
        skills_layout.setContentsMargins(6, 6, 6, 6)
        self.tbl_skills = QTableWidget(18, 4)
        self.tbl_skills.setHorizontalHeaderLabels(["Skill", "Attr", "Prof", "Bonus"])
        skills_hdr = self.tbl_skills.horizontalHeader()
        skills_hdr.setMinimumHeight(header_h)
        skills_hdr.setFixedHeight(header_h)
        skills_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        skills_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        skills_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        skills_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tbl_skills.setColumnWidth(1, 48)
        self.tbl_skills.setColumnWidth(2, 56)
        self.tbl_skills.setColumnWidth(3, 58)
        self.tbl_skills.verticalHeader().setVisible(False)
        self.tbl_skills.verticalHeader().setMinimumSectionSize(row_h)
        self.tbl_skills.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tbl_skills.verticalHeader().setDefaultSectionSize(row_h)
        for r in range(18):
            self.tbl_skills.setRowHeight(r, row_h)
        self.tbl_skills.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_skills.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_skills.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_skills.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tbl_skills.setFixedHeight(header_h + 18 * row_h + 2 * self.tbl_skills.frameWidth() + 2)
        self.tbl_skills.cellClicked.connect(self._on_skill_cell_clicked)
        skills_layout.addWidget(self.tbl_skills)
        left_layout.addWidget(skills_group)

        self.lbl_passives_summary = QLabel("Passives — Perc: 10 | Inv: 10 | Ins: 10")
        self.lbl_passives_summary.setObjectName("AccentText")
        self.lbl_passives_summary.setWordWrap(True)
        left_layout.addWidget(self.lbl_passives_summary)
        left_layout.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.tab6_right_tabs = QTabWidget()
        self.tab6_right_tabs.setElideMode(Qt.TextElideMode.ElideNone)

        feat_group = QWidget()
        feat_layout = QVBoxLayout(feat_group)
        prof_ov_hdr = QHBoxLayout()
        self.chk_override_proficiencies = QCheckBox(
            "Override Proficiencies (click Save / Skill Prof column, or add below)"
        )
        self.chk_override_proficiencies.stateChanged.connect(self._on_proficiency_override_toggled)
        prof_ov_hdr.addWidget(self.chk_override_proficiencies)
        feat_layout.addLayout(prof_ov_hdr)

        self.manual_prof_bar = QWidget()
        mp_row = QHBoxLayout(self.manual_prof_bar)
        mp_row.setContentsMargins(0, 0, 0, 0)
        self.cmb_manual_prof = QComboBox()
        self.cmb_manual_prof.setEditable(True)
        for p_opt in (
            "Light Armor",
            "Medium Armor",
            "Heavy Armor",
            "Shields",
            "Simple Weapons",
            "Martial Weapons",
            "Thieves' Tools",
            "Herbalism Kit",
            "Disguise Kit",
            "Poisoner's Kit",
        ):
            self.cmb_manual_prof.addItem(p_opt)
        configure_dropdown_combo(self.cmb_manual_prof, max_visible=12)
        btn_add_mp = QPushButton("+ Add Prof")
        btn_add_mp.clicked.connect(self._add_manual_proficiency)
        btn_rem_mp = QPushButton("Remove")
        btn_rem_mp.clicked.connect(self._remove_manual_proficiency)
        mp_row.addWidget(self.cmb_manual_prof, 1)
        mp_row.addWidget(btn_add_mp)
        mp_row.addWidget(btn_rem_mp)
        feat_layout.addWidget(self.manual_prof_bar)

        self.lst_features = QListWidget()
        self.lst_features.currentItemChanged.connect(self._on_feature_selected)
        feat_layout.addWidget(self.lst_features, 1)
        self.feat_desc_browser = QTextBrowser()
        feat_layout.addWidget(self.feat_desc_browser, 1)
        self.tab6_right_tabs.addTab(feat_group, "Features, Proficiencies && Languages")

        # Sub-tab: Senses, Speeds, Defenses & Sheet Actions (1.F)
        traits_w = QWidget()
        tw_l = QVBoxLayout(traits_w)
        self.traits_summary_browser = QTextBrowser()
        tw_l.addWidget(self.traits_summary_browser)
        self.tab6_right_tabs.addTab(traits_w, "Traits, Senses && Actions")

        # Sub-tab: Animal Forms / Wild Shape
        self.tab6_right_tabs.addTab(self._build_animal_forms_subtab(), "Animal Forms")

        # Sub-tab: Companions
        self.tab6_right_tabs.addTab(self._build_companions_subtab(), "Companions")

        right_layout.addWidget(self.tab6_right_tabs)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([460, 620])
        layout.addWidget(splitter)
        return tab

    def _sync_skills_features_tab(self) -> None:
        ov_profs = self.state.has_override("override_proficiencies")
        self.chk_override_proficiencies.setChecked(ov_profs)
        self.manual_prof_bar.setVisible(ov_profs)

        for row, ab in enumerate(ABILITIES):
            sv = self.computed.saving_throws[ab]
            prof_it = QTableWidgetItem("●" if sv.proficient else "○")
            prof_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if ov_profs:
                prof_it.setToolTip("Click to toggle Saving Throw proficiency override")
            bonus_it = QTableWidgetItem(_fmt_mod(sv.bonus))
            bonus_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_saves.setItem(row, 0, QTableWidgetItem(ab.capitalize()))
            self.tbl_saves.setItem(row, 1, prof_it)
            self.tbl_saves.setItem(row, 2, bonus_it)

        for row, (skill_name, sk) in enumerate(self.computed.skills.items()):
            mark = "◆ (2x)" if sk.expertise else ("●" if sk.proficient else "○")
            attr_it = QTableWidgetItem(ABILITY_ABBR[sk.ability])
            attr_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            prof_it = QTableWidgetItem(mark)
            prof_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if ov_profs:
                prof_it.setToolTip("Click to cycle manual override: None → Proficient → Expertise")
            bonus_it = QTableWidgetItem(_fmt_mod(sk.bonus))
            bonus_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_skills.setItem(row, 0, QTableWidgetItem(skill_name))
            self.tbl_skills.setItem(row, 1, attr_it)
            self.tbl_skills.setItem(row, 2, prof_it)
            self.tbl_skills.setItem(row, 3, bonus_it)

        c = self.computed
        if hasattr(self, "lbl_passives_summary"):
            self.lbl_passives_summary.setText(
                f"Passives — Perception: {c.passive_perception}  •  "
                f"Investigation: {c.passive_investigation}  •  "
                f"Insight: {c.passive_insight}"
            )

        self.lst_features.setUpdatesEnabled(False)
        self.lst_features.clear()
        for el in c.granted_elements:
            if el.type in ("Level", "Grants", "Support"):
                continue
            item = QListWidgetItem(f"[{el.type}] {el.name}")
            item.setData(Qt.ItemDataRole.UserRole, el.id)
            self.lst_features.addItem(item)
        if ov_profs:
            for mp in self.state.manual_proficiencies:
                item = QListWidgetItem(f"[Manual Proficiency] {mp}")
                item.setData(Qt.ItemDataRole.UserRole, f"manual_prof::{mp}")
                self.lst_features.addItem(item)
        self.lst_features.setUpdatesEnabled(True)

        if hasattr(self, "traits_summary_browser"):
            self.traits_summary_browser.setHtml(self._render_traits_senses_html())

        self._sync_animal_forms_tab()
        self._sync_companions_tab()

    def _render_traits_senses_html(self) -> str:
        c = self.computed
        spd_parts = [f"<b>{k.title()}:</b> {v} ft." for k, v in c.speeds.items()] or [f"<b>Walk:</b> {c.speed} ft."]
        sns_parts = [f"<b>{k.title()}:</b> {v} ft." for k, v in c.senses.items()] or ["None"]
        actions_html = "".join(
            f"<p><b>{html.escape(sa.name)}</b>"
            + (f" <span style='color:#34d399;'>[{html.escape(sa.action)}]</span>" if sa.action else "")
            + (f" <span style='color:#fbbf24;'>({html.escape(sa.usage)})</span>" if sa.usage else "")
            + (f"<br/>{sa.description}" if sa.description else "")
            + "</p>"
            for sa in c.sheet_actions
        ) or "<p style='color:#94a3b8;'>No active sheet actions detected.</p>"
        return f"""
        <h3>Speeds &amp; Senses</h3>
        <p><b>Speeds:</b> {' | '.join(spd_parts)}</p>
        <p><b>Senses:</b> {' | '.join(sns_parts)}</p>
        <p><b>Passives:</b> Perception {c.passive_perception} | Investigation {c.passive_investigation} | Insight {c.passive_insight}</p>
        <h3>Defenses &amp; Traits</h3>
        <p><b>Damage Resistances:</b> {html.escape(', '.join(c.damage_resistances) or 'None')}</p>
        <p><b>Damage Immunities:</b> {html.escape(', '.join(c.damage_immunities) or 'None')}</p>
        <p><b>Damage Vulnerabilities:</b> {html.escape(', '.join(c.damage_vulnerabilities) or 'None')}</p>
        <p><b>Condition Immunities:</b> {html.escape(', '.join(c.condition_immunities) or 'None')}</p>
        <h3>Sheet Actions &amp; Limited Uses</h3>
        {actions_html}
        """

    def _on_proficiency_override_toggled(self, checked: int) -> None:
        if self._updating:
            return
        self.state.set_override("override_proficiencies", bool(checked))
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_save_cell_clicked(self, row: int, col: int) -> None:
        if not self.state.has_override("override_proficiencies") or col != 1 or not (0 <= row < len(ABILITIES)):
            return
        ab = ABILITIES[row]
        cur = list(self.state.manual_save_profs)
        if ab in cur:
            cur.remove(ab)
        else:
            cur.append(ab)
        self.state.manual_save_profs = cur
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_skill_cell_clicked(self, row: int, col: int) -> None:
        if not self.state.has_override("override_proficiencies") or col != 2:
            return
        item = self.tbl_skills.item(row, 0)
        if item is None:
            return
        skill_name = item.text()
        if skill_name in self.state.manual_skill_expertise:
            self.state.manual_skill_expertise.remove(skill_name)
        elif skill_name in self.state.manual_skill_profs:
            self.state.manual_skill_profs.remove(skill_name)
            self.state.manual_skill_expertise.append(skill_name)
        else:
            self.state.manual_skill_profs.append(skill_name)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _add_manual_proficiency(self) -> None:
        txt = self.cmb_manual_prof.currentText().strip()
        if not txt or txt in self.state.manual_proficiencies:
            return
        self.state.set_override("override_proficiencies", True)
        self.state.manual_proficiencies.append(txt)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _remove_manual_proficiency(self) -> None:
        cur_item = self.lst_features.currentItem()
        data = cur_item.data(Qt.ItemDataRole.UserRole) if cur_item else ""
        if isinstance(data, str) and data.startswith("manual_prof::"):
            target = data.split("::", 1)[1]
            if target in self.state.manual_proficiencies:
                self.state.manual_proficiencies.remove(target)
                self._mark_dirty()
                self._recalculate_and_refresh()
                return
        txt = self.cmb_manual_prof.currentText().strip()
        if txt in self.state.manual_proficiencies:
            self.state.manual_proficiencies.remove(txt)
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _on_feature_selected(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        eid = current.data(Qt.ItemDataRole.UserRole)
        el = self.repo.get(eid)
        if el:
            self._show_element_description(el, self.feat_desc_browser)
