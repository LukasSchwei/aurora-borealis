"""Spells catalog, Spellbook/Prepared filter, Multiclass preparation, and Spell Swap mixin (2.4)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...engine import (
    is_spell_castable_for_character,
    is_spell_concentration,
    is_spell_eligible_for_caster,
    is_spell_ritual,
    spell_classes,
    spell_school,
)
from ...models import ABILITY_ABBR, ClassSpellcasting, Element
from ..dialogs import SpellSwapDialog
from ..widgets.item_icons import (
    _fmt_mod,
    _spell_level_icon,
    _spell_school_icon,
    _spell_tags_icon,
)


class SpellsTabMixin:
    def _build_tab_spells(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        hdr_row = QHBoxLayout()
        self.lbl_spellcasting_header = QLabel("Spellcasting: None active for current class/level")
        self.lbl_spellcasting_header.setObjectName("TitleText")
        self.chk_manual_spells = QCheckBox("Allow manual extra spells (override limits)")
        self.chk_manual_spells.setChecked(False)
        self.chk_manual_spells.stateChanged.connect(self._on_manual_spells_toggled)
        hdr_row.addWidget(self.lbl_spellcasting_header, 1)
        hdr_row.addWidget(self.chk_manual_spells)
        layout.addLayout(hdr_row)

        self.lbl_spell_limits = QLabel("")
        self.lbl_spell_limits.setObjectName("AccentText")
        layout.addWidget(self.lbl_spell_limits)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        cat_box = QGroupBox("Spell Catalog")
        cat_layout = QVBoxLayout(cat_box)
        f_row = QHBoxLayout()
        self.txt_spell_search = QLineEdit()
        self.txt_spell_search.setPlaceholderText("Search spells…")
        self.txt_spell_search.textChanged.connect(self._refresh_spell_catalog)
        self.cmb_spell_caster = QComboBox()
        self.cmb_spell_caster.addItem("All Spells", "__all__")
        self.cmb_spell_caster.currentIndexChanged.connect(self._refresh_spell_catalog)
        self.cmb_spell_level = QComboBox()
        self.cmb_spell_level.addItem("All Levels", "")
        self.cmb_spell_level.addItem("Cantrip (0)", "0")
        for lvl in range(1, 10):
            self.cmb_spell_level.addItem(f"Level {lvl}", str(lvl))
        self.cmb_spell_level.currentIndexChanged.connect(self._refresh_spell_catalog)
        f_row.addWidget(self.txt_spell_search, 2)
        f_row.addWidget(self.cmb_spell_caster, 1)
        f_row.addWidget(self.cmb_spell_level, 1)
        cat_layout.addLayout(f_row)

        f_row2 = QHBoxLayout()
        self.cmb_spell_class = QComboBox()
        self.cmb_spell_class.addItem("All Classes", "")
        for cname in self.repo.available_spell_classes():
            self.cmb_spell_class.addItem(cname, cname.lower())
        self.cmb_spell_class.currentIndexChanged.connect(self._refresh_spell_catalog)
        self.cmb_spell_school = QComboBox()
        self.cmb_spell_school.addItem("All Schools", "")
        for school in (
            "Abjuration",
            "Conjuration",
            "Divination",
            "Enchantment",
            "Evocation",
            "Illusion",
            "Necromancy",
            "Transmutation",
        ):
            self.cmb_spell_school.addItem(school, school.lower())
        self.cmb_spell_school.currentIndexChanged.connect(self._refresh_spell_catalog)
        self.cmb_spell_prop = QComboBox()
        self.cmb_spell_prop.addItem("All Tags", "")
        self.cmb_spell_prop.addItem("Ritual", "ritual")
        self.cmb_spell_prop.addItem("Concentration", "concentration")
        self.cmb_spell_prop.currentIndexChanged.connect(self._refresh_spell_catalog)
        self.cmb_spell_proficiency = QComboBox()
        self.cmb_spell_proficiency.addItem("All Availability", "all")
        self.cmb_spell_proficiency.addItem("Proficient / Castable Only", "castable")
        self.cmb_spell_proficiency.addItem("Class List (Any Level)", "class_list")
        self.cmb_spell_proficiency.addItem("Not Castable", "not_castable")
        self.cmb_spell_proficiency.currentIndexChanged.connect(self._refresh_spell_catalog)
        f_row2.addWidget(self.cmb_spell_class, 1)
        f_row2.addWidget(self.cmb_spell_school, 1)
        f_row2.addWidget(self.cmb_spell_prop, 1)
        f_row2.addWidget(self.cmb_spell_proficiency, 1)
        cat_layout.addLayout(f_row2)

        self.tbl_spell_catalog = QTableWidget(0, 4)
        self.tbl_spell_catalog.setHorizontalHeaderLabels(["Name", "Level", "School", "R / C"])
        self.tbl_spell_catalog.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_spell_catalog.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl_spell_catalog.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_spell_catalog.verticalHeader().setVisible(False)
        self.tbl_spell_catalog.verticalHeader().setDefaultSectionSize(34)
        self.tbl_spell_catalog.setIconSize(QSize(48, 26))
        sp_hdr = self.tbl_spell_catalog.horizontalHeader()
        sp_hdr.setSectionsClickable(True)
        sp_hdr.setSortIndicatorShown(True)
        sp_hdr.setSortIndicator(self._spell_sort_col, self._spell_sort_order)
        sp_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        sp_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        sp_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        sp_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tbl_spell_catalog.setColumnWidth(1, 68)
        self.tbl_spell_catalog.setColumnWidth(2, 138)
        self.tbl_spell_catalog.setColumnWidth(3, 76)
        sp_hdr.sectionClicked.connect(self._on_spell_header_clicked)
        self.tbl_spell_catalog.currentCellChanged.connect(self._on_spell_preview)
        self.tbl_spell_catalog.cellDoubleClicked.connect(lambda _r, _c: self._add_selected_spell())
        cat_layout.addWidget(self.tbl_spell_catalog)
        btn_add_sp = QPushButton("Learn / Add Spell")
        btn_add_sp.setObjectName("PrimaryBtn")
        btn_add_sp.clicked.connect(self._add_selected_spell)
        cat_layout.addWidget(btn_add_sp)

        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        known_box = QGroupBox("Known, Spellbook && Prepared Spells")
        known_layout = QVBoxLayout(known_box)

        known_filter_row = QHBoxLayout()
        known_filter_row.addWidget(QLabel("View Filter:"))
        self.cmb_known_spell_filter = QComboBox()
        self.cmb_known_spell_filter.addItem("All Known / Added", "all")
        self.cmb_known_spell_filter.addItem("Prepared Only", "prepared")
        self.cmb_known_spell_filter.addItem("Always Prepared", "always_prepared")
        self.cmb_known_spell_filter.addItem("Spellbook / Unprepared", "spellbook")
        self.cmb_known_spell_filter.addItem("Rituals Only", "ritual")
        self.cmb_known_spell_filter.currentIndexChanged.connect(self._sync_spells_tab)
        known_filter_row.addWidget(self.cmb_known_spell_filter, 1)
        known_layout.addLayout(known_filter_row)

        # Keep columnCount == 6 for full test & UI compatibility
        self.tbl_spells = QTableWidget(0, 6)
        self.tbl_spells.setHorizontalHeaderLabels(["Spell", "Level", "School", "R / C", "Source / Status", "Prepared"])
        self.tbl_spells.setIconSize(QSize(48, 26))
        self.tbl_spells.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_spells.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_spells.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_spells.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_spells.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_spells.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        sp_vh = self.tbl_spells.verticalHeader()
        sp_vh.setVisible(False)
        sp_vh.setDefaultSectionSize(max(34, round(34 * self.config.ui_scale)))
        self.tbl_spells.currentCellChanged.connect(self._on_known_spell_selected)
        known_layout.addWidget(self.tbl_spells)

        sp_btn_row = QHBoxLayout()
        self.btn_swap_spell = QPushButton("Swap Spell")
        self.btn_swap_spell.clicked.connect(self._swap_selected_spell)
        btn_rem_sp = QPushButton("Remove Selected Spell")
        btn_rem_sp.setObjectName("DangerBtn")
        btn_rem_sp.clicked.connect(self._remove_selected_spell)
        sp_btn_row.addWidget(self.btn_swap_spell)
        sp_btn_row.addWidget(btn_rem_sp)
        known_layout.addLayout(sp_btn_row)

        desc_box = QGroupBox("Spell Description")
        desc_layout = QVBoxLayout(desc_box)
        self.spell_desc_browser = QTextBrowser()
        desc_layout.addWidget(self.spell_desc_browser)

        right_layout.addWidget(known_box, 1)
        right_layout.addWidget(desc_box, 1)

        splitter.addWidget(cat_box)
        splitter.addWidget(right_box)
        splitter.setSizes([420, 560])
        layout.addWidget(splitter, 1)
        self._refresh_spell_catalog()
        return tab

    def _spell_counts(self) -> tuple[int, int, list[str]]:
        granted = self.computed.spellcasting.granted_spell_ids if self.computed.spellcasting else []
        combined = list(dict.fromkeys([*granted, *self.state.known_spells]))
        cantrips = 0
        leveled = 0
        for sid in combined:
            el = self.repo.get(sid)
            lvl = el.setters.get("level", "0") if el else "0"
            if lvl == "0":
                cantrips += 1
            else:
                leveled += 1
        return cantrips, leveled, combined

    def _prepared_count_for_caster(self, caster: ClassSpellcasting, always_prep_set: set[str]) -> int:
        sc = self.computed.spellcasting
        if not sc or len(sc.casters) <= 1:
            return sum(1 for sid in self.state.prepared_spells if sid not in always_prep_set)
        cnt = 0
        for sid in self.state.prepared_spells:
            if sid in always_prep_set:
                continue
            src_cid = self.state.spell_sources.get(sid, "")
            if src_cid == caster.source_class_id:
                cnt += 1
            elif not src_cid:
                sel = self.repo.get(sid)
                if sel and is_spell_eligible_for_caster(sel, caster):
                    cnt += 1
        return cnt

    def _sync_spells_tab(self) -> None:
        self.chk_manual_spells.setChecked(self.state.has_override("allow_extra_spells"))
        sc = self.computed.spellcasting
        cantrip_cnt, leveled_cnt, combined = self._spell_counts()

        prev_filter = self.cmb_spell_caster.currentData() or "__eligible__"
        self.cmb_spell_caster.blockSignals(True)
        self.cmb_spell_caster.clear()
        if sc and sc.casters:
            self.cmb_spell_caster.addItem("Eligible Class / Subclass Spells", "__eligible__")
            for caster in sc.casters:
                sub_tag = f" ({caster.subclass_name})" if caster.subclass_name else ""
                self.cmb_spell_caster.addItem(
                    f"{caster.source_class_name}{sub_tag} List",
                    f"caster::{caster.source_class_id}",
                )
            self.cmb_spell_caster.addItem("All Spells", "__all__")
            idx = self.cmb_spell_caster.findData(prev_filter)
            self.cmb_spell_caster.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.cmb_spell_caster.addItem("All Spells", "__all__")
            self.cmb_spell_caster.setCurrentIndex(0)
        self.cmb_spell_caster.blockSignals(False)
        self._refresh_spell_catalog()

        if sc:
            slots_txt = ", ".join(f"L{k}: {v}" for k, v in sorted(sc.slots.items())) or "Cantrips"
            if sc.pact_slots and sc.slots != sc.pact_slots:
                pact_txt = ", ".join(f"L{k}: {v}" for k, v in sorted(sc.pact_slots.items()))
                slots_txt = f"{slots_txt}  |  Pact Magic: {pact_txt}"
            if len(sc.casters) > 1:
                caster_hdrs = " / ".join(
                    f"{c.source_class_name} ({ABILITY_ABBR.get(c.ability.lower(), c.ability[:3].upper())} DC {c.save_dc}, {_fmt_mod(c.attack_bonus)})"
                    for c in sc.casters
                )
                mc_tag = f" [MC Caster Lv {sc.multiclass_caster_level}]" if sc.multiclass_caster_level else ""
                self.lbl_spellcasting_header.setText(
                    f"{caster_hdrs}{mc_tag}  |  Slots: {slots_txt}"
                )
            else:
                self.lbl_spellcasting_header.setText(
                    f"{sc.caster_name} ({sc.ability}) | Save DC: {sc.save_dc} | "
                    f"Attack: {_fmt_mod(sc.attack_bonus)} | Slots: {slots_txt}"
                )

            always_prep_set = set(sc.always_prepared_spell_ids)
            parts = [f"Cantrips: {cantrip_cnt} / {sc.max_cantrips}"]
            if sc.max_known_spells is not None:
                parts.append(f"Spells Known/Book: {leveled_cnt} / {sc.max_known_spells}")
            else:
                parts.append(f"Spells Added: {leveled_cnt} (All class spells available)")
            if len(sc.casters) > 1:
                prep_parts = []
                for c in sc.casters:
                    if c.max_prepared_spells is not None:
                        pcnt = self._prepared_count_for_caster(c, always_prep_set)
                        prep_parts.append(f"{c.source_class_name}: {pcnt}/{c.max_prepared_spells}")
                if prep_parts:
                    parts.append("Prepared [" + ", ".join(prep_parts) + "]")
            elif sc.max_prepared_spells is not None:
                manual_prep_cnt = sum(
                    1 for sid in self.state.prepared_spells if sid not in always_prep_set
                )
                parts.append(f"Prepared: {manual_prep_cnt} / {sc.max_prepared_spells}")
            parts.append(f"Max Slot Level: {sc.max_spell_level}")
            if self.state.allow_extra_spells:
                parts.append("[Manual Override Active]")
            self.lbl_spell_limits.setText("  •  ".join(parts))
        else:
            self.lbl_spellcasting_header.setText(
                "Spellcasting: None active for current class/level"
            )
            if self.state.allow_extra_spells:
                self.lbl_spell_limits.setText(
                    f"Manual Override Active — {len(combined)} spell(s) added"
                )
            else:
                self.lbl_spell_limits.setText(
                    "Select a spellcasting class or enable 'Allow manual extra spells' to add spells."
                )

        prepared_set = set(self.state.prepared_spells)
        granted_set = set(sc.granted_spell_ids if sc else [])
        always_prep_set = set(sc.always_prepared_spell_ids if sc else [])

        known_filter = (
            self.cmb_known_spell_filter.currentData()
            if hasattr(self, "cmb_known_spell_filter")
            else "all"
        )
        shown_ids: list[str] = []
        for sid in combined:
            el = self.repo.get(sid)
            is_ap = sid in always_prep_set
            is_pr = is_ap or (sid in prepared_set)
            if known_filter == "prepared" and not is_pr:
                continue
            if known_filter == "always_prepared" and not is_ap:
                continue
            if known_filter == "spellbook" and is_pr:
                continue
            if known_filter == "ritual" and not (el and is_spell_ritual(el)):
                continue
            shown_ids.append(sid)

        self.tbl_spells.setUpdatesEnabled(False)
        self.tbl_spells.setRowCount(len(shown_ids))

        for row, sid in enumerate(shown_ids):
            el = self.repo.get(sid)
            name_item = QTableWidgetItem(el.name if el else sid)
            name_item.setData(Qt.ItemDataRole.UserRole, sid)
            lvl = str(el.setters.get("level", "0")) if el else "?"
            lvl_item = QTableWidgetItem(_spell_level_icon(lvl), "Cantrip" if lvl == "0" else f"Lv {lvl}")
            school = spell_school(el) if el else ""
            school_item = QTableWidgetItem(
                _spell_school_icon(school), school.title() if school else "—"
            )
            is_rit = is_spell_ritual(el) if el else False
            is_conc = is_spell_concentration(el) if el else False
            tags_txt = "/".join(p for p in ("R" if is_rit else "", "C" if is_conc else "") if p)
            tags_item = QTableWidgetItem(_spell_tags_icon(is_rit, is_conc), tags_txt)
            tags_item.setToolTip(
                ", ".join(p for p in ("Ritual" if is_rit else "", "Concentration" if is_conc else "") if p)
                or "Standard"
            )
            self.tbl_spells.setItem(row, 0, name_item)
            self.tbl_spells.setItem(row, 1, lvl_item)
            self.tbl_spells.setItem(row, 2, school_item)
            self.tbl_spells.setItem(row, 3, tags_item)

            src_cid = self.state.spell_sources.get(sid, "")
            src_el = self.repo.get(src_cid) if src_cid else None
            if sid in always_prep_set:
                src_label = "Subclass [Always Prepared]"
            else:
                base_src = (
                    src_el.name
                    if src_el is not None
                    else (
                        "Class / Feature"
                        if (sid in granted_set and sid not in self.state.known_spells)
                        else (
                            sc.casters[0].source_class_name
                            if (sc and len(sc.casters) == 1)
                            else "Manual"
                        )
                    )
                )
                status_tag = "[Prepared]" if sid in prepared_set else ("[Spellbook]" if lvl != "0" else "[Cantrip]")
                src_label = f"{base_src} {status_tag}"
            self.tbl_spells.setItem(row, 4, QTableWidgetItem(src_label))

            chk = QCheckBox()
            if sid in always_prep_set:
                chk.setChecked(True)
                chk.setEnabled(False)
                chk.setToolTip("Always prepared by subclass feature (does not count against prepared limit)")
            else:
                chk.setChecked(sid in prepared_set)

            def make_prep_handler(spell_id: str, chk_ref: QCheckBox):
                def _on_prep(checked: int) -> None:
                    if self._updating:
                        return
                    if checked:
                        sc_now = self.computed.spellcasting
                        ap_set = set(sc_now.always_prepared_spell_ids if sc_now else [])
                        if not self.state.has_override("allow_extra_spells") and sc_now:
                            src_cid_now = self.state.spell_sources.get(spell_id, "")
                            target_c = next(
                                (c for c in sc_now.casters if c.source_class_id == src_cid_now),
                                None,
                            )
                            if target_c is not None and target_c.max_prepared_spells is not None:
                                c_prep_cnt = self._prepared_count_for_caster(target_c, ap_set)
                                if c_prep_cnt >= target_c.max_prepared_spells and spell_id not in self.state.prepared_spells:
                                    self._updating = True
                                    chk_ref.setChecked(False)
                                    self._updating = False
                                    QMessageBox.information(
                                        self,
                                        "Prepared Spell Limit Reached",
                                        f"{target_c.source_class_name} can prepare up to {target_c.max_prepared_spells} spells.\n"
                                        "Enable 'Allow manual extra spells' to override.",
                                    )
                                    return
                            else:
                                manual_prep_cnt = sum(
                                    1 for s in self.state.prepared_spells if s not in ap_set
                                )
                                if (
                                    sc_now.max_prepared_spells is not None
                                    and manual_prep_cnt >= sc_now.max_prepared_spells
                                    and spell_id not in self.state.prepared_spells
                                ):
                                    self._updating = True
                                    chk_ref.setChecked(False)
                                    self._updating = False
                                    QMessageBox.information(
                                        self,
                                        "Prepared Spell Limit Reached",
                                        f"You can prepare up to {sc_now.max_prepared_spells} spells. "
                                        "Enable 'Allow manual extra spells' to override.",
                                    )
                                    return
                        if spell_id not in self.state.prepared_spells:
                            self.state.prepared_spells.append(spell_id)
                    else:
                        if spell_id in self.state.prepared_spells:
                            self.state.prepared_spells.remove(spell_id)
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_prep

            if sid not in always_prep_set:
                chk.stateChanged.connect(make_prep_handler(sid, chk))
            self.tbl_spells.setCellWidget(row, 5, chk)
        sp_row_h = max(34, round(34 * self.config.ui_scale))
        for r in range(self.tbl_spells.rowCount()):
            w = self.tbl_spells.cellWidget(r, 5)
            if w is not None:
                sp_row_h = max(sp_row_h, w.sizeHint().height() + 6)
        sp_vh = self.tbl_spells.verticalHeader()
        sp_vh.setMinimumSectionSize(sp_row_h)
        sp_vh.setDefaultSectionSize(sp_row_h)
        for r in range(self.tbl_spells.rowCount()):
            self.tbl_spells.setRowHeight(r, sp_row_h)
        self.tbl_spells.setUpdatesEnabled(True)

    def _on_spell_header_clicked(self, col: int) -> None:
        if col == self._spell_sort_col:
            self._spell_sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._spell_sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._spell_sort_col = col
            self._spell_sort_order = Qt.SortOrder.AscendingOrder
        self.tbl_spell_catalog.horizontalHeader().setSortIndicator(
            self._spell_sort_col, self._spell_sort_order
        )
        self._refresh_spell_catalog()

    def _refresh_spell_catalog(self) -> None:
        query = self.txt_spell_search.text()
        lvl_filter = self.cmb_spell_level.currentData() or ""
        class_filter = self.cmb_spell_class.currentData() or "" if hasattr(self, "cmb_spell_class") else ""
        school_filter = self.cmb_spell_school.currentData() or "" if hasattr(self, "cmb_spell_school") else ""
        prop_filter = self.cmb_spell_prop.currentData() or "" if hasattr(self, "cmb_spell_prop") else ""
        prof_filter = self.cmb_spell_proficiency.currentData() or "all" if hasattr(self, "cmb_spell_proficiency") else "all"
        caster_filter = self.cmb_spell_caster.currentData() if hasattr(self, "cmb_spell_caster") else "__all__"
        spells = self.repo.search(query, ["Spell"])

        sc = getattr(self, "computed", None).spellcasting if getattr(self, "computed", None) is not None else None
        target_c: Optional[ClassSpellcasting] = None
        if sc and sc.casters and caster_filter and caster_filter.startswith("caster::"):
            target_cid = caster_filter.split("::", 1)[1]
            target_c = next((c for c in sc.casters if c.source_class_id == target_cid), None)

        if sc and sc.casters and caster_filter and caster_filter != "__all__":
            if caster_filter == "__eligible__":
                spells = [
                    el
                    for el in spells
                    if any(is_spell_eligible_for_caster(el, c) for c in sc.casters)
                ]
            elif target_c is not None:
                spells = [el for el in spells if is_spell_eligible_for_caster(el, target_c)]

        computed_now = getattr(self, "computed", None)
        if prof_filter and prof_filter != "all" and computed_now is not None:
            if prof_filter == "castable":
                spells = [el for el in spells if is_spell_castable_for_character(el, computed_now, target_c)]
            elif prof_filter == "class_list":
                granted_set = {e.id for e in computed_now.granted_elements}
                if sc and sc.casters:
                    check_casters = [target_c] if target_c is not None else sc.casters
                    spells = [
                        el
                        for el in spells
                        if el.id in granted_set
                        or el.id in sc.granted_spell_ids
                        or el.id in sc.always_prepared_spell_ids
                        or any(is_spell_eligible_for_caster(el, c) for c in check_casters)
                    ]
                else:
                    spells = [el for el in spells if el.id in granted_set]
            elif prof_filter == "not_castable":
                spells = [el for el in spells if not is_spell_castable_for_character(el, computed_now, target_c)]

        if class_filter:
            cf_lower = class_filter.lower()
            spells = [el for el in spells if any(c.lower() == cf_lower for c in spell_classes(el))]
        if lvl_filter:
            spells = [el for el in spells if str(el.setters.get("level", "0")) == lvl_filter]
        if school_filter:
            spells = [el for el in spells if spell_school(el).lower() == school_filter]
        if prop_filter == "ritual":
            spells = [el for el in spells if is_spell_ritual(el)]
        elif prop_filter == "concentration":
            spells = [el for el in spells if is_spell_concentration(el)]

        def _spell_lvl_num(el: Element) -> int:
            raw = str(el.setters.get("level", "0")).strip()
            return int(raw) if raw.isdigit() else 0

        reverse = self._spell_sort_order == Qt.SortOrder.DescendingOrder
        if self._spell_sort_col == 1:
            spells.sort(key=lambda e: (_spell_lvl_num(e), e.name.lower()), reverse=reverse)
        elif self._spell_sort_col == 2:
            spells.sort(key=lambda e: (spell_school(e), e.name.lower()), reverse=reverse)
        elif self._spell_sort_col == 3:
            spells.sort(
                key=lambda e: (
                    (2 if is_spell_ritual(e) else 0) + (1 if is_spell_concentration(e) else 0),
                    e.name.lower(),
                ),
                reverse=reverse,
            )
        else:
            spells.sort(key=lambda e: (e.name.lower(), _spell_lvl_num(e)), reverse=reverse)

        shown = spells[:350]
        spell_sig = tuple((e.id, self._spell_sort_col, int(self._spell_sort_order.value)) for e in shown)
        if spell_sig == self._spell_catalog_sig:
            return
        self._spell_catalog_sig = spell_sig

        self.tbl_spell_catalog.setUpdatesEnabled(False)
        self.tbl_spell_catalog.setRowCount(len(shown))
        for row, el in enumerate(shown):
            lvl = str(el.setters.get("level", "0"))
            name_item = QTableWidgetItem(el.name)
            name_item.setData(Qt.ItemDataRole.UserRole, el.id)
            self.tbl_spell_catalog.setItem(row, 0, name_item)

            lvl_item = QTableWidgetItem(_spell_level_icon(lvl), "")
            lvl_item.setToolTip("Cantrip" if lvl == "0" else f"Level {lvl}")
            lvl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_spell_catalog.setItem(row, 1, lvl_item)

            school = spell_school(el)
            school_label = school.title() if school else "—"
            school_item = QTableWidgetItem(_spell_school_icon(school), school_label)
            school_item.setToolTip(f"School: {school_label}")
            self.tbl_spell_catalog.setItem(row, 2, school_item)

            is_rit = is_spell_ritual(el)
            is_conc = is_spell_concentration(el)
            tag_item = QTableWidgetItem(_spell_tags_icon(is_rit, is_conc), "")
            tag_tips = [p for p in ("Ritual" if is_rit else "", "Concentration" if is_conc else "") if p]
            tag_item.setToolTip(", ".join(tag_tips) if tag_tips else "Standard")
            tag_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_spell_catalog.setItem(row, 3, tag_item)
        self.tbl_spell_catalog.setUpdatesEnabled(True)

    def _on_spell_preview(
        self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1
    ) -> None:
        if row < 0 or row >= self.tbl_spell_catalog.rowCount():
            return
        name_item = self.tbl_spell_catalog.item(row, 0)
        sid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        el = self.repo.get(sid) if sid else None
        if el:
            self._show_element_description(el, self.spell_desc_browser)

    def _on_known_spell_selected(self, row: int, _col: int) -> None:
        if 0 <= row < self.tbl_spells.rowCount():
            item = self.tbl_spells.item(row, 0)
            if item:
                sid = item.data(Qt.ItemDataRole.UserRole)
                el = self.repo.get(sid)
                if el:
                    self._show_element_description(el, self.spell_desc_browser)

    def _on_manual_spells_toggled(self, checked: int) -> None:
        if self._updating:
            return
        self.state.set_override("allow_extra_spells", bool(checked))
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _add_selected_spell(self) -> None:
        row = self.tbl_spell_catalog.currentRow()
        if row < 0:
            return
        name_item = self.tbl_spell_catalog.item(row, 0)
        sid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        if not sid:
            return
        cantrip_cnt, leveled_cnt, combined = self._spell_counts()
        if sid in combined:
            return

        if not self.state.allow_extra_spells:
            sc = self.computed.spellcasting
            if sc is None:
                QMessageBox.information(
                    self,
                    "Spellcasting Not Active",
                    "Select a spellcasting class first, or enable 'Allow manual extra spells (override limits)'.",
                )
                return
            el = self.repo.get(sid)
            lvl_str = el.setters.get("level", "0") if el else "0"
            lvl = int(lvl_str) if lvl_str.isdigit() else 0

            caster_filter = self.cmb_spell_caster.currentData() if hasattr(self, "cmb_spell_caster") else "__eligible__"
            target_caster: Optional[ClassSpellcasting] = None
            if caster_filter and str(caster_filter).startswith("caster::"):
                tcid = str(caster_filter).split("::", 1)[1]
                target_caster = next((c for c in sc.casters if c.source_class_id == tcid), None)
            if target_caster is None and el is not None:
                eligible = [c for c in sc.casters if is_spell_eligible_for_caster(el, c)]
                if sc.casters and not eligible:
                    QMessageBox.information(
                        self,
                        "Spell Not on Class List",
                        f"{el.name} is not on your active class or subclass spell list(s). "
                        "Enable 'Allow manual extra spells' to override.",
                    )
                    return
                target_caster = max(eligible, key=lambda c: c.max_spell_level) if eligible else (sc.casters[0] if sc.casters else None)

            max_lvl_allowed = target_caster.max_spell_level if target_caster else sc.max_spell_level
            if lvl > max_lvl_allowed:
                QMessageBox.information(
                    self,
                    "Spell Level Too High",
                    f"{el.name if el else sid} is level {lvl}, but your max spell level for "
                    f"{target_caster.source_class_name if target_caster else sc.caster_name} is {max_lvl_allowed}. "
                    "Enable 'Allow manual extra spells' to override.",
                )
                return
            if lvl == 0 and cantrip_cnt >= sc.max_cantrips:
                QMessageBox.information(
                    self,
                    "Cantrip Limit Reached",
                    f"You already have {cantrip_cnt} / {sc.max_cantrips} cantrips. "
                    "Enable 'Allow manual extra spells' to override.",
                )
                return
            if lvl > 0 and sc.max_known_spells is not None and leveled_cnt >= sc.max_known_spells:
                QMessageBox.information(
                    self,
                    "Spell Limit Reached",
                    f"You already have {leveled_cnt} / {sc.max_known_spells} leveled spells. "
                    "Enable 'Allow manual extra spells' to override.",
                )
                return
            if target_caster is not None and target_caster.source_class_id:
                self.state.spell_sources[sid] = target_caster.source_class_id

        self.state.known_spells.append(sid)
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _swap_selected_spell(self) -> None:
        row = self.tbl_spells.currentRow()
        if not (0 <= row < self.tbl_spells.rowCount()):
            return
        item = self.tbl_spells.item(row, 0)
        old_sid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not old_sid or old_sid not in self.state.known_spells:
            return
        old_el = self.repo.get(old_sid)
        if old_el is None:
            return
        sc = self.computed.spellcasting
        old_lvl_s = old_el.setters.get("level", "0")
        old_lvl = int(old_lvl_s) if old_lvl_s.isdigit() else 0
        existing = set(self.state.known_spells) | set(sc.granted_spell_ids if sc else [])

        src_cid = self.state.spell_sources.get(old_sid, "")
        target_c = (
            next((c for c in sc.casters if c.source_class_id == src_cid), None)
            if sc and src_cid
            else (sc.casters[0] if sc and sc.casters else None)
        )
        all_spells = self.repo.search("", ["Spell"])
        candidates: list[Element] = []
        for sp in all_spells:
            if sp.id in existing:
                continue
            lvl_s = sp.setters.get("level", "0")
            lvl = int(lvl_s) if lvl_s.isdigit() else 0
            if (old_lvl == 0 and lvl != 0) or (old_lvl > 0 and lvl == 0):
                continue
            if target_c is not None and not self.state.has_override("allow_extra_spells"):
                if lvl > target_c.max_spell_level or not is_spell_eligible_for_caster(sp, target_c):
                    continue
            candidates.append(sp)
        candidates.sort(key=lambda s: (int(s.setters.get("level", "0") or 0), s.name.lower()))
        dlg = SpellSwapDialog(old_el, candidates, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            new_sid = dlg.selected_spell_id()
            if new_sid and new_sid != old_sid:
                idx = self.state.known_spells.index(old_sid)
                self.state.known_spells[idx] = new_sid
                if old_sid in self.state.prepared_spells:
                    self.state.prepared_spells.remove(old_sid)
                    if new_sid not in self.state.prepared_spells:
                        self.state.prepared_spells.append(new_sid)
                if src_cid:
                    self.state.spell_sources[new_sid] = src_cid
                self.state.spell_sources.pop(old_sid, None)
                self._mark_dirty()
                self._recalculate_and_refresh()

    def _remove_selected_spell(self) -> None:
        row = self.tbl_spells.currentRow()
        if 0 <= row < self.tbl_spells.rowCount():
            item = self.tbl_spells.item(row, 0)
            sid = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not sid:
                return
            if sid in self.state.known_spells:
                self.state.known_spells.remove(sid)
            if sid in self.state.prepared_spells:
                self.state.prepared_spells.remove(sid)
            self.state.spell_sources.pop(sid, None)
            for skey, chosen in list(self.state.selections.items()):
                if sid in chosen:
                    self.state.selections[skey] = ["" if c == sid else c for c in chosen]
            self._mark_dirty()
            self._recalculate_and_refresh()
