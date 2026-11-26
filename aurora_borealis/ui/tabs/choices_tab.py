"""Choices & Feats tab mixin."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...engine import (
    effective_selection_slot_count,
    get_synthetic_asi_element,
    is_synthetic_asi_id,
    selection_filled_count,
)
from ...models import ActiveSelection
from ..icons import apply_button_icon
from ..ui_helpers import configure_dropdown_combo, ensure_widgets_fit


class ChoicesTabMixin:
    def _build_tab_choices_feats(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        sel_group = QGroupBox("All Character Choices")
        sel_outer = QVBoxLayout(sel_group)
        self.lbl_choices_pending = QLabel("")
        self.lbl_choices_pending.setObjectName("WarnText")
        sel_outer.addWidget(self.lbl_choices_pending)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.selections_scroll = scroll
        self.selections_container = QWidget()
        self.selections_layout = QVBoxLayout(self.selections_container)
        self.selections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.selections_container)
        sel_outer.addWidget(scroll)

        right = QGroupBox("Feat Browser && Description Inspector")
        rl = QVBoxLayout(right)
        self.txt_feat_search = QLineEdit()
        self.txt_feat_search.setPlaceholderText("Search feats…")
        self.txt_feat_search.textChanged.connect(self._refresh_feat_browser)
        rl.addWidget(self.txt_feat_search)
        self.lst_feats_browser = QListWidget()
        self.lst_feats_browser.currentItemChanged.connect(self._on_feat_browser_selected)
        rl.addWidget(self.lst_feats_browser, 1)
        self.choice_desc_browser = QTextBrowser()
        self.choice_desc_browser.setOpenExternalLinks(True)
        rl.addWidget(self.choice_desc_browser, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(sel_group)
        splitter.addWidget(right)
        splitter.setSizes([540, 480])
        layout.addWidget(splitter)
        self._refresh_feat_browser()
        return tab

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _sync_choices_tab(self) -> None:
        self._refresh_feat_browser()
        choices_sig = (
            self.state.ruleset,
            self.state.level,
            self.state.race_id,
            self.state.class_id,
            self.state.background_id,
            tuple((c.class_id, c.level) for c in self.state.normalized_classes()),
            tuple((k, tuple(v)) for k, v in sorted(self.state.selections.items())),
            tuple((k, v) for k, v in sorted(self.state.rule_overrides.items()) if v),
            tuple(
                (s.key, s.source_element_id, s.rule.type, s.rule.number, s.rule.level, tuple(s.options))
                for s in self.computed.active_selections
            ),
            tuple(
                effective_selection_slot_count(s, self.state, self.computed)
                for s in self.computed.active_selections
            ),
            tuple(sorted(e.id for e in self.computed.granted_elements if e.type not in ("Level", "Grants", "Support"))),
            len(self.repo.by_id),
        )
        if choices_sig == self._choices_sig:
            return
        self._choices_sig = choices_sig

        scroll_areas = [
            self.selections_scroll,
            self.tab_race.choices_scroll,
            self.tab_class.choices_scroll,
            self.tab_background.choices_scroll,
        ]
        saved_scroll_vals = [sa.verticalScrollBar().value() for sa in scroll_areas]
        containers = [
            self.selections_container,
            self.tab_race.choices_container,
            self.tab_class.choices_container,
            self.tab_background.choices_container,
        ]
        for c in containers:
            c.setUpdatesEnabled(False)

        self._clear_layout(self.selections_layout)
        self._clear_layout(self.tab_race.choices_layout)
        self._clear_layout(self.tab_class.choices_layout)
        self._clear_layout(self.tab_background.choices_layout)

        pending_total = 0
        active_class_ids = {c.class_id for c in self.state.normalized_classes()}
        for active_sel in self.computed.active_selections:
            eff_num = effective_selection_slot_count(active_sel, self.state, self.computed)
            filled = selection_filled_count(active_sel, self.state, eff_num)
            if not active_sel.rule.optional and filled < eff_num:
                pending_total += eff_num - filled
            self._add_selection_widget(active_sel, filled, eff_num, self.selections_layout)

            src_el = self.repo.get(active_sel.source_element_id)
            if active_sel.source_element_id == self.state.race_id or (src_el and src_el.type in ("Race", "Sub Race", "Racial Trait")):
                self._add_selection_widget(active_sel, filled, eff_num, self.tab_race.choices_layout)
            elif active_sel.source_element_id in active_class_ids or (src_el and src_el.type in ("Class", "Archetype", "Class Feature", "Archetype Feature")):
                self._add_selection_widget(active_sel, filled, eff_num, self.tab_class.choices_layout)
            elif active_sel.source_element_id == self.state.background_id or (src_el and src_el.type in ("Background", "Background Feature")):
                self._add_selection_widget(active_sel, filled, eff_num, self.tab_background.choices_layout)

        for c in containers:
            ensure_widgets_fit(c)
            c.setUpdatesEnabled(True)

        def _restore_scrolls() -> None:
            for sa, pos in zip(scroll_areas, saved_scroll_vals):
                sb = sa.verticalScrollBar()
                sb.setValue(min(pos, sb.maximum()))

        _restore_scrolls()
        QTimer.singleShot(0, _restore_scrolls)

        if pending_total > 0:
            self.lbl_choices_pending.setText(f"{pending_total} choice(s) remaining")
            self.btn_card_choices.setText(f"4. Choices && Feats\n\n{pending_total} choice(s) pending — click to resolve")
            apply_button_icon(self.btn_card_choices, "warning", theme=self.config.theme, size=18, fixed_color="#f59e0b")
        else:
            self.lbl_choices_pending.setText("All required choices selected")
            self.btn_card_choices.setText("4. Choices && Feats\n\nAll required choices resolved")
            apply_button_icon(self.btn_card_choices, "check", theme=self.config.theme, size=18, fixed_color="#34d399")

    def _add_selection_widget(
        self,
        active_sel: ActiveSelection,
        filled: int,
        eff_num: int,
        target_layout: QVBoxLayout,
    ) -> None:
        is_complete = filled >= eff_num or active_sel.rule.optional
        card = QFrame()
        card.setObjectName("ChoiceCard" if is_complete else "ChoiceCardPending")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(10, 8, 10, 8)
        vbox.setSpacing(6)

        hdr = QHBoxLayout()
        lbl_title = QLabel(
            f"<b>{active_sel.rule.name}</b> <span style='color:#94a3b8;'>({active_sel.source_element_name})</span>"
        )
        lbl_title.setWordWrap(True)
        status_color = "#4ade80" if filled >= eff_num else "#facc15"
        status_text = (
            f"✓ {filled}/{eff_num}"
            if filled >= eff_num
            else f"• {filled}/{eff_num}"
        )
        lbl_status = QLabel(status_text)
        lbl_status.setStyleSheet(f"color:{status_color}; font-weight:bold;")
        hdr.addWidget(lbl_title, 1)
        hdr.addWidget(lbl_status)
        vbox.addLayout(hdr)

        if eff_num == 0:
            lbl_empty = QLabel("All available options are already granted.")
            lbl_empty.setObjectName("MutedText")
            vbox.addWidget(lbl_empty)
            target_layout.addWidget(card)
            return

        chosen = list(self.state.selections.get(active_sel.key, []))
        slot_vals = list(chosen[:eff_num])
        if any(chosen[eff_num:]):
            compacted = [v for v in chosen if v]
            slot_vals = (compacted + [""] * eff_num)[:eff_num]
        else:
            while len(slot_vals) < eff_num:
                slot_vals.append("")

        all_granted_ids = {el.id for el in self.computed.granted_elements}
        other_sel_ids: set[str] = set()
        for skey, svals in self.state.selections.items():
            if skey != active_sel.key:
                for sv in svals:
                    if sv:
                        other_sel_ids.add(sv)

        for slot_idx in range(eff_num):
            cmb = QComboBox()
            configure_dropdown_combo(cmb, max_visible=14)
            cmb.addItem("— Choose —", "")
            current_val = slot_vals[slot_idx]
            same_sel_other = {
                slot_vals[i]
                for i in range(eff_num)
                if i != slot_idx and slot_vals[i]
            }
            taken_ids = set(same_sel_other)
            if active_sel.rule.type != "List":
                taken_ids |= all_granted_ids
                taken_ids |= other_sel_ids
            taken_ids.discard(current_val)

            seen_opts: set[str] = set()
            for opt_id, opt_name in active_sel.options:
                if (not is_synthetic_asi_id(opt_id) and opt_id in taken_ids) or opt_id in seen_opts:
                    continue
                seen_opts.add(opt_id)
                cmb.addItem(opt_name, opt_id)
            if current_val:
                idx = cmb.findData(current_val)
                if idx >= 0:
                    cmb.setCurrentIndex(idx)

            def make_handler(skey: str, sidx: int, count: int, combo_ref: QComboBox, seed_vals: list[str]):
                def _on_changed(_idx: int) -> None:
                    if self._updating:
                        return
                    val = combo_ref.currentData() or ""
                    lst = list(seed_vals)
                    raw_lst = self.state.selections.get(skey, [])
                    if len(raw_lst) >= count and not any(raw_lst[count:]):
                        lst = list(raw_lst[:count])
                    while len(lst) < count:
                        lst.append("")
                    if val and not is_synthetic_asi_id(val) and any(i != sidx and v == val for i, v in enumerate(lst)):
                        return
                    lst[sidx] = val
                    self.state.selections[skey] = lst
                    self._mark_dirty()
                    if val:
                        desc_el = self.repo.by_id.get(val) or get_synthetic_asi_element(val)
                        if desc_el is not None:
                            self._show_element_description(desc_el, self.choice_desc_browser)
                    self._recalculate_and_refresh()

                return _on_changed

            cmb.currentIndexChanged.connect(
                make_handler(active_sel.key, slot_idx, eff_num, cmb, slot_vals)
            )
            vbox.addWidget(cmb)

        target_layout.addWidget(card)

    def _refresh_feat_browser(self) -> None:
        q = self.txt_feat_search.text()
        feats = self.repo.search(q, ["Feat"])[:250]
        self.lst_feats_browser.clear()
        for el in feats:
            it = QListWidgetItem(el.name)
            it.setData(Qt.ItemDataRole.UserRole, el.id)
            self.lst_feats_browser.addItem(it)

    def _on_feat_browser_selected(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        el = self.repo.get(current.data(Qt.ItemDataRole.UserRole) or "")
        if el:
            self._show_element_description(el, self.choice_desc_browser)
