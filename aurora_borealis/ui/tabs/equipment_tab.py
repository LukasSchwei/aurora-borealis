"""Equipment, Currency, Containers, Starting Equipment & Weapon Mastery tab mixin (1.C)."""

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
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...config import save_config
from ...engine import is_equipment_proficient, parse_weight_lb
from ...equipment import (
    deduct_currency,
    element_cost_cp,
    format_cp,
    get_character_containers,
)
from ...models import Element, InventoryItem
from ...rules_55e import WEAPON_MASTERY_TABLE, get_weapon_mastery
from ..dialogs import (
    CustomItemDialog,
    MagicGearDialog,
    ManageContainersDialog,
    StartingEquipmentDialog,
)
from ..icons import apply_button_icon
from ..widgets.item_icons import (
    _equip_rarity_icon,
    _equip_type_icon,
    _item_cost_gp,
    _item_rarity_info,
)


class EquipmentTabMixin:
    def _build_tab_equipment(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        cur_group = QGroupBox("Currency && Encumbrance")
        cur_layout = QHBoxLayout(cur_group)
        self.cur_spins: dict[str, QSpinBox] = {}
        for coin in ("cp", "sp", "ep", "gp", "pp"):
            cur_layout.addWidget(QLabel(coin.upper() + ":"))
            spn = QSpinBox()
            spn.setRange(0, 999999)
            spn.setMinimumWidth(88)
            spn.valueChanged.connect(self._on_currency_changed)
            cur_layout.addWidget(spn)
            self.cur_spins[coin] = spn
        self.lbl_total_weight = QLabel("Total Weight: 0.0 / 150 lb (Normal)")
        self.lbl_total_weight.setObjectName("AccentText")
        cur_layout.addStretch()
        cur_layout.addWidget(self.lbl_total_weight)
        layout.addWidget(cur_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        cat_box = QGroupBox("Equipment Catalog")
        cat_layout = QVBoxLayout(cat_box)
        filter_row = QHBoxLayout()
        self.txt_equip_search = QLineEdit()
        self.txt_equip_search.setPlaceholderText("Search weapons, armor, gear, magic items…")
        self.txt_equip_search.textChanged.connect(self._refresh_equip_catalog)
        self.cmb_equip_type = QComboBox()
        self.cmb_equip_type.addItems(["All", "Weapon", "Armor", "Item", "Magic Item"])
        self.cmb_equip_type.currentIndexChanged.connect(self._refresh_equip_catalog)
        filter_row.addWidget(self.txt_equip_search, 2)
        filter_row.addWidget(self.cmb_equip_type, 1)
        cat_layout.addLayout(filter_row)

        filter_row2 = QHBoxLayout()
        self.cmb_equip_category = QComboBox()
        self.cmb_equip_category.addItems([
            "All Categories",
            "Consumables",
            "Potions",
            "Scrolls",
            "Adventuring Gear",
            "Tools",
            "Ammunition",
            "Wondrous Items",
            "Rings, Rods & Staves",
        ])
        self.cmb_equip_category.currentIndexChanged.connect(self._refresh_equip_catalog)
        self.cmb_equip_rarity = QComboBox()
        self.cmb_equip_rarity.addItems([
            "All Rarities",
            "Common",
            "Uncommon",
            "Rare",
            "Very Rare",
            "Legendary",
            "Artifact",
        ])
        self.cmb_equip_rarity.currentIndexChanged.connect(self._refresh_equip_catalog)
        self.cmb_equip_proficiency = QComboBox()
        self.cmb_equip_proficiency.addItem("All Proficiency", "all")
        self.cmb_equip_proficiency.addItem("Proficient Only", "proficient")
        self.cmb_equip_proficiency.addItem("Proficient & General Gear", "usable")
        self.cmb_equip_proficiency.addItem("Not Proficient", "not_proficient")
        self.cmb_equip_proficiency.currentIndexChanged.connect(self._refresh_equip_catalog)
        filter_row2.addWidget(self.cmb_equip_category, 1)
        filter_row2.addWidget(self.cmb_equip_rarity, 1)
        filter_row2.addWidget(self.cmb_equip_proficiency, 1)
        cat_layout.addLayout(filter_row2)

        self.tbl_equip_catalog = QTableWidget(0, 5)
        self.tbl_equip_catalog.setHorizontalHeaderLabels(["Type", "Name", "Rarity", "Weight", "Cost"])
        self.tbl_equip_catalog.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tbl_equip_catalog.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_equip_catalog.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl_equip_catalog.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_equip_catalog.verticalHeader().setVisible(False)
        self.tbl_equip_catalog.verticalHeader().setDefaultSectionSize(36)
        self.tbl_equip_catalog.setIconSize(QSize(28, 28))
        eq_hdr = self.tbl_equip_catalog.horizontalHeader()
        eq_hdr.setSectionsClickable(True)
        eq_hdr.setSortIndicatorShown(True)
        eq_hdr.setSortIndicator(self._equip_sort_col, self._equip_sort_order)
        eq_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        eq_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        eq_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        eq_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        eq_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.tbl_equip_catalog.setColumnWidth(0, 54)
        self.tbl_equip_catalog.setColumnWidth(2, 98)
        self.tbl_equip_catalog.setColumnWidth(3, 78)
        self.tbl_equip_catalog.setColumnWidth(4, 88)
        eq_hdr.sectionClicked.connect(self._on_equip_header_clicked)
        self.tbl_equip_catalog.currentCellChanged.connect(self._on_equip_preview)
        self.tbl_equip_catalog.cellDoubleClicked.connect(lambda _r, _c: self._add_selected_equipment())
        cat_layout.addWidget(self.tbl_equip_catalog)

        eq_btn_row = QHBoxLayout()
        btn_add_eq = QPushButton("Add to Inventory")
        btn_add_eq.setObjectName("PrimaryBtn")
        btn_add_eq.clicked.connect(self._add_selected_equipment)
        self.btn_buy_equip = QPushButton("Buy (Deduct Coins)")
        self.btn_buy_equip.clicked.connect(self._buy_selected_equipment)
        self.btn_magic_gear = QPushButton("Magic / Infused")
        apply_button_icon(self.btn_magic_gear, "sparkles", size=15)
        self.btn_magic_gear.clicked.connect(self._open_magic_gear_dialog)
        eq_btn_row.addWidget(btn_add_eq)
        eq_btn_row.addWidget(self.btn_buy_equip)
        eq_btn_row.addWidget(self.btn_magic_gear)
        cat_layout.addLayout(eq_btn_row)

        eq_btn_row2 = QHBoxLayout()
        self.btn_custom_item = QPushButton("+ Custom Item")
        self.btn_custom_item.clicked.connect(self._add_custom_item_dialog)
        self.btn_starting_equip = QPushButton("Starting Equipment")
        self.btn_starting_equip.clicked.connect(self._open_starting_equipment_dialog)
        self.btn_manage_containers = QPushButton("Containers")
        self.btn_manage_containers.clicked.connect(self._open_containers_dialog)
        eq_btn_row2.addWidget(self.btn_custom_item)
        eq_btn_row2.addWidget(self.btn_starting_equip)
        eq_btn_row2.addWidget(self.btn_manage_containers)
        eq_btn_row2.addStretch()
        cat_layout.addLayout(eq_btn_row2)

        right_eq = QWidget()
        right_eq_l = QVBoxLayout(right_eq)
        right_eq_l.setContentsMargins(0, 0, 0, 0)

        inv_box = QGroupBox("Character Inventory")
        inv_layout = QVBoxLayout(inv_box)

        attune_row = QHBoxLayout()
        self.chk_enforce_attunement = QCheckBox("Enforce Magic Item Attunement Rules (max 3)")
        self.chk_enforce_attunement.setChecked(self.config.enforce_attunement)
        self.chk_enforce_attunement.stateChanged.connect(self._on_attunement_rule_toggled)
        self.lbl_attunement = QLabel("Attuned: 0 / 3")
        self.lbl_attunement.setObjectName("AccentText")
        attune_row.addWidget(self.chk_enforce_attunement, 1)
        attune_row.addWidget(self.lbl_attunement)
        inv_layout.addLayout(attune_row)

        cont_filter_row = QHBoxLayout()
        cont_filter_row.addWidget(QLabel("Container Filter:"))
        self.cmb_inv_container = QComboBox()
        self.cmb_inv_container.addItem("All Containers", "")
        self.cmb_inv_container.currentIndexChanged.connect(self._sync_equipment_tab)
        cont_filter_row.addWidget(self.cmb_inv_container, 1)
        inv_layout.addLayout(cont_filter_row)

        # Keep columns 0..5 exact for backwards test compatibility; add Container & Notes at 6..7
        self.tbl_inventory = QTableWidget(0, 8)
        self.tbl_inventory.setHorizontalHeaderLabels(
            ["Item", "Type", "Qty", "Equipped", "Attuned", "Weight", "Container", "Notes / Charges"]
        )
        inv_hdr = self.tbl_inventory.horizontalHeader()
        inv_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 8):
            inv_hdr.setSectionResizeMode(
                col,
                QHeaderView.ResizeMode.Fixed if col == 2 else QHeaderView.ResizeMode.ResizeToContents,
            )
        self.tbl_inventory.setColumnWidth(2, max(96, round(96 * self.config.ui_scale)))
        inv_vh = self.tbl_inventory.verticalHeader()
        inv_vh.setVisible(False)
        inv_row_h = max(42, round(42 * self.config.ui_scale))
        inv_vh.setMinimumSectionSize(inv_row_h)
        inv_vh.setDefaultSectionSize(inv_row_h)
        self.tbl_inventory.cellDoubleClicked.connect(lambda _r, _c: self._edit_selected_inventory_item())
        inv_layout.addWidget(self.tbl_inventory)

        inv_btns = QHBoxLayout()
        self.btn_edit_inventory = QPushButton("Edit Item / Container")
        self.btn_edit_inventory.clicked.connect(self._edit_selected_inventory_item)
        btn_rem_eq = QPushButton("Remove Selected Item")
        btn_rem_eq.setObjectName("DangerBtn")
        btn_rem_eq.clicked.connect(self._remove_selected_inventory)
        inv_btns.addWidget(self.btn_edit_inventory)
        inv_btns.addWidget(btn_rem_eq)
        inv_layout.addLayout(inv_btns)

        eq_desc_box = QGroupBox("Item Details")
        eq_dl = QVBoxLayout(eq_desc_box)
        self.equip_desc_browser = QTextBrowser()
        eq_dl.addWidget(self.equip_desc_browser)

        self.mastery_55e_group = QGroupBox("5.5e Weapon Masteries")
        m55_l = QVBoxLayout(self.mastery_55e_group)
        m55_top = QHBoxLayout()
        self.lbl_mastery_limit = QLabel("Masteries: 0 / 0")
        self.lbl_mastery_limit.setObjectName("AccentText")
        self.chk_override_mastery = QCheckBox("Override mastery limit")
        self.chk_override_mastery.stateChanged.connect(self._on_mastery_override_toggled)
        m55_top.addWidget(self.lbl_mastery_limit, 1)
        m55_top.addWidget(self.chk_override_mastery)
        m55_l.addLayout(m55_top)
        m55_pick = QHBoxLayout()
        self.cmb_mastery_weapon = QComboBox()
        for wname, mprop in sorted(WEAPON_MASTERY_TABLE.items()):
            self.cmb_mastery_weapon.addItem(f"{wname.title()} ({mprop})", wname.title())
        self.btn_add_mastery = QPushButton("+ Add Mastery")
        self.btn_add_mastery.clicked.connect(self._add_weapon_mastery)
        self.btn_rem_mastery = QPushButton("Remove")
        self.btn_rem_mastery.clicked.connect(self._remove_weapon_mastery)
        m55_pick.addWidget(self.cmb_mastery_weapon, 1)
        m55_pick.addWidget(self.btn_add_mastery)
        m55_pick.addWidget(self.btn_rem_mastery)
        m55_l.addLayout(m55_pick)
        self.lbl_mastery_active = QLabel("Active Masteries: None")
        self.lbl_mastery_active.setObjectName("MutedText")
        self.lbl_mastery_active.setWordWrap(True)
        m55_l.addWidget(self.lbl_mastery_active)

        right_eq_l.addWidget(inv_box, 2)
        right_eq_l.addWidget(self.mastery_55e_group)
        right_eq_l.addWidget(eq_desc_box, 1)

        splitter.addWidget(cat_box)
        splitter.addWidget(right_eq)
        splitter.setSizes([490, 490])
        layout.addWidget(splitter, 1)
        self._refresh_equip_catalog()
        return tab

    def _max_attuned_items(self) -> int:
        for cl in self.state.normalized_classes():
            cel = self.repo.get(cl.class_id)
            if cel and "artificer" in cel.name.lower():
                if cl.level >= 18:
                    return 6
                if cl.level >= 14:
                    return 5
                if cl.level >= 10:
                    return 4
        return 3

    def _on_attunement_rule_toggled(self, checked: int) -> None:
        self.config.enforce_attunement = bool(checked)
        save_config(self.config, self.config_path)
        self._sync_equipment_tab()

    def _sync_equipment_tab(self) -> None:
        for coin, spn in self.cur_spins.items():
            spn.blockSignals(True)
            spn.setValue(self.state.currency.get(coin, 0))
            spn.blockSignals(False)
        cap = getattr(self.computed, "carrying_capacity", 150.0)
        enc_status = getattr(self.computed, "encumbrance_status", "Normal")
        self.lbl_total_weight.setText(
            f"Carried: {self.computed.total_weight:.1f} / {cap:.0f} lb ({enc_status})"
        )

        if hasattr(self, "cmb_inv_container"):
            prev_c = self.cmb_inv_container.currentData() or ""
            self.cmb_inv_container.blockSignals(True)
            self.cmb_inv_container.clear()
            self.cmb_inv_container.addItem("All Containers", "")
            for cinfo in get_character_containers(self.state):
                cname = cinfo["name"]
                suffix = " [0 lb]" if cinfo.get("ignore_weight") else ""
                self.cmb_inv_container.addItem(f"{cname}{suffix}", cname)
            idx = self.cmb_inv_container.findData(prev_c)
            self.cmb_inv_container.setCurrentIndex(idx if idx >= 0 else 0)
            self.cmb_inv_container.blockSignals(False)
            cont_filter = (self.cmb_inv_container.currentData() or "").strip().lower()
        else:
            cont_filter = ""

        max_att = self._max_attuned_items()
        cur_att = sum(1 for it in self.state.inventory if it.attuned)
        if hasattr(self, "chk_enforce_attunement"):
            self.chk_enforce_attunement.blockSignals(True)
            self.chk_enforce_attunement.setChecked(self.config.enforce_attunement)
            self.chk_enforce_attunement.blockSignals(False)
            self.chk_enforce_attunement.setText(
                f"Enforce Magic Item Attunement Rules (max {max_att})"
            )
            self.lbl_attunement.setText(
                f"Attuned: {cur_att} / {max_att}"
                if self.config.enforce_attunement
                else f"Attuned: {cur_att} (Unlimited)"
            )

        is_55e = self.state.ruleset == "5.5e"
        self.mastery_55e_group.setVisible(is_55e)
        if is_55e:
            limit = self.computed.weapon_mastery_limit
            ov_mastery = self.state.has_override("override_weapon_mastery")
            self.chk_override_mastery.setChecked(ov_mastery)
            self.lbl_mastery_limit.setText(
                f"Masteries: {len(self.state.weapon_masteries)} / {'∞ (Override)' if ov_mastery else limit}"
            )
            if self.computed.weapon_mastery_details:
                self.lbl_mastery_active.setText(
                    "Active Masteries: "
                    + ", ".join(f"{d['weapon']} ({d['mastery']})" for d in self.computed.weapon_mastery_details)
                )
            elif self.state.weapon_masteries:
                self.lbl_mastery_active.setText(
                    "Active Masteries: "
                    + ", ".join(f"{w} ({get_weapon_mastery(w) or 'Mastery'})" for w in self.state.weapon_masteries)
                )
            else:
                self.lbl_mastery_active.setText(
                    "Active Masteries: None (select a weapon above and click + Add Mastery)"
                )

        visible_items: list[tuple[int, InventoryItem]] = [
            (orig_idx, inv)
            for orig_idx, inv in enumerate(self.state.inventory)
            if not cont_filter or (inv.container or "On Person").strip().lower() == cont_filter
        ]

        self.tbl_inventory.setRowCount(len(visible_items))
        inv_row_h = max(42, round(42 * self.config.ui_scale))
        col2_w = max(96, round(96 * self.config.ui_scale))
        for row, (orig_idx, inv) in enumerate(visible_items):
            name_it = QTableWidgetItem(inv.name)
            name_it.setData(Qt.ItemDataRole.UserRole, orig_idx)
            self.tbl_inventory.setItem(row, 0, name_it)
            self.tbl_inventory.setItem(row, 1, QTableWidgetItem(inv.category or "Item"))

            qty_spin = QSpinBox()
            qty_spin.setRange(1, 9999)
            qty_spin.setMinimumWidth(max(84, round(84 * self.config.ui_scale)))
            qty_spin.setValue(inv.quantity)

            def make_qty_handler(r_idx: int):
                def _on_qty(val: int) -> None:
                    if self._updating or r_idx >= len(self.state.inventory):
                        return
                    self.state.inventory[r_idx].quantity = val
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_qty

            qty_spin.valueChanged.connect(make_qty_handler(orig_idx))
            inv_row_h = max(inv_row_h, qty_spin.sizeHint().height() + 6)
            col2_w = max(col2_w, qty_spin.sizeHint().width() + 8)
            self.tbl_inventory.setCellWidget(row, 2, qty_spin)

            chk = QCheckBox()
            chk.setChecked(inv.equipped)

            def make_eq_handler(r_idx: int):
                def _on_eq(checked: int) -> None:
                    if self._updating or r_idx >= len(self.state.inventory):
                        return
                    self.state.inventory[r_idx].equipped = bool(checked)
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_eq

            chk.stateChanged.connect(make_eq_handler(orig_idx))
            self.tbl_inventory.setCellWidget(row, 3, chk)

            chk_att = QCheckBox()
            chk_att.setChecked(inv.attuned)

            def make_att_handler(r_idx: int, cb_ref: QCheckBox):
                def _on_att(checked: int) -> None:
                    if self._updating or r_idx >= len(self.state.inventory):
                        return
                    want = bool(checked)
                    if want and self.config.enforce_attunement:
                        limit = self._max_attuned_items()
                        others = sum(
                            1 for idx, it in enumerate(self.state.inventory)
                            if idx != r_idx and it.attuned
                        )
                        if others >= limit:
                            self._updating = True
                            cb_ref.setChecked(False)
                            self._updating = False
                            QMessageBox.information(
                                self,
                                "Attunement Limit Reached",
                                f"You can only attune to {limit} magic item(s) at a time under D&D attunement rules.\n"
                                "Uncheck another attuned item or disable 'Enforce Magic Item Attunement Rules'.",
                            )
                            return
                    self.state.inventory[r_idx].attuned = want
                    self._mark_dirty()
                    self._recalculate_and_refresh()

                return _on_att

            chk_att.stateChanged.connect(make_att_handler(orig_idx, chk_att))
            self.tbl_inventory.setCellWidget(row, 4, chk_att)

            self.tbl_inventory.setItem(
                row, 5, QTableWidgetItem(f"{inv.weight * inv.quantity:.1f} lb")
            )
            self.tbl_inventory.setItem(row, 6, QTableWidgetItem(inv.container or "On Person"))
            extra_parts = []
            if inv.max_charges > 0 or inv.charges > 0:
                extra_parts.append(f"[{inv.charges}/{inv.max_charges or inv.charges} chg]")
            if inv.ignore_weight:
                extra_parts.append("[0 lb]")
            if inv.notes:
                extra_parts.append(inv.notes)
            self.tbl_inventory.setItem(row, 7, QTableWidgetItem(" ".join(extra_parts)))
        inv_vh = self.tbl_inventory.verticalHeader()
        inv_vh.setMinimumSectionSize(inv_row_h)
        inv_vh.setDefaultSectionSize(inv_row_h)
        self.tbl_inventory.setColumnWidth(2, col2_w)
        for r in range(len(visible_items)):
            self.tbl_inventory.setRowHeight(r, inv_row_h)
        self._refresh_equip_catalog()

    def _on_mastery_override_toggled(self, checked: int) -> None:
        if self._updating:
            return
        self.state.set_override("override_weapon_mastery", bool(checked))
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _add_weapon_mastery(self) -> None:
        wname = self.cmb_mastery_weapon.currentData()
        if not wname:
            return
        cur = list(self.state.weapon_masteries)
        if any(w.lower() == wname.lower() for w in cur):
            return
        limit = self.computed.weapon_mastery_limit
        if not self.state.has_override("override_weapon_mastery") and len(cur) >= limit:
            QMessageBox.information(
                self,
                "Weapon Mastery Limit Reached",
                f"Your current classes grant {limit} Weapon Mastery slot(s).\n"
                "Enable 'Override mastery limit' to add more.",
            )
            return
        cur.append(wname)
        self.state.weapon_masteries = cur
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _remove_weapon_mastery(self) -> None:
        wname = self.cmb_mastery_weapon.currentData()
        cur = [w for w in self.state.weapon_masteries if w.lower() != (wname or "").lower()]
        if len(cur) == len(self.state.weapon_masteries) and self.state.weapon_masteries:
            cur = self.state.weapon_masteries[:-1]
        if cur != self.state.weapon_masteries:
            self.state.weapon_masteries = cur
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _on_currency_changed(self) -> None:
        if self._updating:
            return
        for coin, spn in self.cur_spins.items():
            self.state.currency[coin] = spn.value()
        self._mark_dirty()

    def _on_equip_preview(
        self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1
    ) -> None:
        if row < 0 or row >= self.tbl_equip_catalog.rowCount():
            return
        name_item = self.tbl_equip_catalog.item(row, 1)
        eid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
        el = self.repo.get(eid or "")
        if el:
            w = parse_weight_lb(el)
            cost = el.setters.get("cost", "")
            cur = el.setters.get("currency", "")
            cost_txt = f"{cost} {cur}".strip() if cost else "—"
            _rank, _r_letter, r_label, _rfg, _rbg = _item_rarity_info(el)
            extra = f" | Rarity: {r_label} | Cost: {cost_txt} | Weight: {w:.1f} lb"
            if el.setters.get("armorClass"):
                extra += f" | AC: {el.setters['armorClass']}"
            if el.setters.get("damage"):
                extra += f" | Damage: {el.setters['damage']} {el.setters.get('damage_type', '')}".rstrip()
            prof_status = is_equipment_proficient(el, getattr(self, "computed", None), self.repo)
            if prof_status is True:
                extra += " | Proficiency: Proficient"
            elif prof_status is False:
                extra += " | Proficiency: Not Proficient"
            body = el.description_html or el.sheet_description or "<p>No description available.</p>"
            self.equip_desc_browser.setHtml(
                f"<h3>{el.name}</h3><p style='color:#7dd3fc;'>{el.type} — {el.source}{extra}</p>{body}"
            )

    def _on_equip_header_clicked(self, col: int) -> None:
        if col == self._equip_sort_col:
            self._equip_sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._equip_sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._equip_sort_col = col
            self._equip_sort_order = Qt.SortOrder.AscendingOrder
        self.tbl_equip_catalog.horizontalHeader().setSortIndicator(
            self._equip_sort_col, self._equip_sort_order
        )
        self._refresh_equip_catalog()

    @staticmethod
    def _matches_equip_category(el: Element, category_filter: str) -> bool:
        if not category_filter or category_filter == "All Categories":
            return True
        blob = " ".join([
            el.name,
            el.type,
            el.setters.get("category", ""),
            el.setters.get("type", ""),
            el.setters.get("slot", ""),
            " ".join(el.supports),
        ]).lower()
        if category_filter == "Consumables":
            if el.setters.get("consumable", "").lower() == "true":
                return True
            return any(
                kw in blob
                for kw in (
                    "consumable", "potion", "scroll", "elixir", "poison", "oil",
                    "ammunition", "arrow", "bolt", "ration", "torch", "alchemist",
                    "acid", "antitoxin", "holy water", "dust", "bead", "feather token",
                )
            )
        if category_filter == "Potions":
            return any(kw in blob for kw in ("potion", "elixir", "oil", "philter"))
        if category_filter == "Scrolls":
            return "scroll" in blob
        if category_filter == "Adventuring Gear":
            return "adventuring gear" in blob or (el.type == "Item" and "tool" not in blob and "ammo" not in blob)
        if category_filter == "Tools":
            return any(kw in blob for kw in ("tool", "kit", "musical instrument", "gaming set", "artisan"))
        if category_filter == "Ammunition":
            return any(kw in blob for kw in ("ammunition", "arrow", "bolt", "sling bullet", "blowgun needle"))
        if category_filter == "Wondrous Items":
            return "wondrous" in blob
        if category_filter == "Rings, Rods & Staves":
            return any(kw in blob for kw in ("ring", "rod", "staff", "wand"))
        return True

    def _refresh_equip_catalog(self) -> None:
        query = self.txt_equip_search.text()
        cat = self.cmb_equip_type.currentText()
        sub_cat = self.cmb_equip_category.currentText() if hasattr(self, "cmb_equip_category") else "All Categories"
        rarity_filter = self.cmb_equip_rarity.currentText() if hasattr(self, "cmb_equip_rarity") else "All Rarities"
        prof_filter = self.cmb_equip_proficiency.currentData() if hasattr(self, "cmb_equip_proficiency") else "all"
        types = ["Weapon", "Armor", "Item", "Magic Item"] if cat == "All" else [cat]
        results = self.repo.search(query, types)
        if sub_cat != "All Categories":
            results = [e for e in results if self._matches_equip_category(e, sub_cat)]
        if rarity_filter != "All Rarities":
            results = [e for e in results if _item_rarity_info(e)[2].lower() == rarity_filter.lower()]
        computed_now = getattr(self, "computed", None)
        if prof_filter and prof_filter != "all" and computed_now is not None:
            if prof_filter == "proficient":
                results = [e for e in results if is_equipment_proficient(e, computed_now, self.repo) is True]
            elif prof_filter == "usable":
                results = [e for e in results if is_equipment_proficient(e, computed_now, self.repo) is not False]
            elif prof_filter == "not_proficient":
                results = [e for e in results if is_equipment_proficient(e, computed_now, self.repo) is False]
        reverse = self._equip_sort_order == Qt.SortOrder.DescendingOrder
        if self._equip_sort_col == 0:
            results.sort(key=lambda e: (e.type.lower(), e.name.lower()), reverse=reverse)
        elif self._equip_sort_col == 2:
            results.sort(key=lambda e: (_item_rarity_info(e)[0], e.name.lower()), reverse=reverse)
        elif self._equip_sort_col == 3:
            results.sort(key=lambda e: (parse_weight_lb(e), e.name.lower()), reverse=reverse)
        elif self._equip_sort_col == 4:
            results.sort(key=lambda e: (_item_cost_gp(e), e.name.lower()), reverse=reverse)
        else:
            results.sort(key=lambda e: e.name.lower(), reverse=reverse)

        self.tbl_equip_catalog.setUpdatesEnabled(False)
        shown = results[:300]
        equip_sig = tuple((e.id, self._equip_sort_col, int(self._equip_sort_order.value)) for e in shown)
        if equip_sig != self._equip_catalog_sig:
            self._equip_catalog_sig = equip_sig
            self.tbl_equip_catalog.setRowCount(len(shown))
            for row, el in enumerate(shown):
                type_item = QTableWidgetItem(_equip_type_icon(el.type), "")
                type_item.setToolTip(el.type)
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_equip_catalog.setItem(row, 0, type_item)

                name_item = QTableWidgetItem(el.name)
                name_item.setData(Qt.ItemDataRole.UserRole, el.id)
                self.tbl_equip_catalog.setItem(row, 1, name_item)

                _rank, r_letter, r_label, r_fg, r_bg = _item_rarity_info(el)
                r_item = QTableWidgetItem(_equip_rarity_icon(r_letter, r_fg, r_bg), "")
                r_item.setToolTip(r_label)
                r_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_equip_catalog.setItem(row, 2, r_item)

                w = parse_weight_lb(el)
                w_item = QTableWidgetItem(f"{w:.1f} lb" if w > 0 else "—")
                w_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tbl_equip_catalog.setItem(row, 3, w_item)

                cost = el.setters.get("cost", "")
                cur = el.setters.get("currency", "")
                c_item = QTableWidgetItem(f"{cost} {cur}".strip() if cost else "—")
                c_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tbl_equip_catalog.setItem(row, 4, c_item)
        self.tbl_equip_catalog.setUpdatesEnabled(True)

    def _open_magic_gear_dialog(self) -> None:
        initial_el: Optional[Element] = None
        row = self.tbl_equip_catalog.currentRow()
        if row >= 0:
            name_item = self.tbl_equip_catalog.item(row, 1)
            eid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            cand = self.repo.get(eid) if eid else None
            if cand is not None and cand.type in ("Armor", "Weapon"):
                initial_el = cand
        dlg = MagicGearDialog(self.repo, initial_element=initial_el, computed=getattr(self, "computed", None), parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            inv_item = dlg.build_inventory_item()
            if inv_item is not None:
                self.state.inventory.append(inv_item)
                self._mark_dirty()
                self._recalculate_and_refresh()

    def _selected_catalog_equipment(self) -> Optional[Element]:
        row = self.tbl_equip_catalog.currentRow()
        if row < 0:
            return None
        name_item = self.tbl_equip_catalog.item(row, 1)
        eid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        return self.repo.get(eid) if eid else None

    def _add_selected_equipment(self) -> None:
        el = self._selected_catalog_equipment()
        if el is None:
            return
        self.state.inventory.append(
            InventoryItem(
                element_id=el.id,
                name=el.name,
                quantity=1,
                equipped=(el.type in ("Armor", "Weapon")),
                weight=parse_weight_lb(el),
                category=el.type,
                container="On Person" if el.type in ("Armor", "Weapon") else "Backpack",
            )
        )
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _buy_selected_equipment(self) -> None:
        el = self._selected_catalog_equipment()
        if el is None:
            return
        cost_cp = element_cost_cp(el)
        if cost_cp > 0:
            ok, new_cur = deduct_currency(self.state.currency, cost_cp)
            if not ok:
                QMessageBox.warning(
                    self,
                    "Insufficient Funds",
                    f"{el.name} costs {format_cp(cost_cp)}, which exceeds your current coins.",
                )
                return
            self.state.currency = new_cur
        self.state.inventory.append(
            InventoryItem(
                element_id=el.id,
                name=el.name,
                quantity=1,
                equipped=(el.type in ("Armor", "Weapon")),
                weight=parse_weight_lb(el),
                category=el.type,
                container="On Person" if el.type in ("Armor", "Weapon") else "Backpack",
            )
        )
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _add_custom_item_dialog(self) -> None:
        dlg = CustomItemDialog(get_character_containers(self.state), parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.state.inventory.append(dlg.build_item())
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _edit_selected_inventory_item(self) -> None:
        row = self.tbl_inventory.currentRow()
        if row < 0 or row >= self.tbl_inventory.rowCount():
            return
        name_it = self.tbl_inventory.item(row, 0)
        orig_idx = name_it.data(Qt.ItemDataRole.UserRole) if name_it else row
        if not isinstance(orig_idx, int) or not (0 <= orig_idx < len(self.state.inventory)):
            return
        dlg = CustomItemDialog(
            get_character_containers(self.state),
            initial_item=self.state.inventory[orig_idx],
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.state.inventory[orig_idx] = dlg.build_item()
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _open_containers_dialog(self) -> None:
        dlg = ManageContainersDialog(self.state, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.state.containers = dlg.containers()
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _open_starting_equipment_dialog(self) -> None:
        dlg = StartingEquipmentDialog(self.state, self.repo, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            items, gold_gp, replace = dlg.selected_result()
            if replace:
                self.state.inventory.clear()
            self.state.inventory.extend(items)
            if gold_gp > 0:
                self.state.currency["gp"] = self.state.currency.get("gp", 0) + gold_gp
            self._mark_dirty()
            self._recalculate_and_refresh()

    def _remove_selected_inventory(self) -> None:
        row = self.tbl_inventory.currentRow()
        if 0 <= row < self.tbl_inventory.rowCount():
            name_it = self.tbl_inventory.item(row, 0)
            orig_idx = name_it.data(Qt.ItemDataRole.UserRole) if name_it else row
            if isinstance(orig_idx, int) and 0 <= orig_idx < len(self.state.inventory):
                self.state.inventory.pop(orig_idx)
                self._mark_dirty()
                self._recalculate_and_refresh()
