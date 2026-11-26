"""Animal Forms / Wild Shape sub-tab mixin."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from ...animal_forms import (
    all_animal_forms,
    animal_form_to_dict,
    compute_animal_form_access,
    compute_transformed_stats,
    find_animal_form,
    is_form_eligible,
    render_animal_form_html,
)
from ..dialogs import CustomAnimalFormDialog


class AnimalFormsTabMixin:
    def _build_animal_forms_subtab(self) -> QWidget:
        forms_w = QWidget()
        fw_l = QVBoxLayout(forms_w)
        af_hdr = QHBoxLayout()
        self.lbl_animal_access = QLabel("Wild Shape / Animal Forms")
        self.lbl_animal_access.setObjectName("AccentText")
        self.lbl_animal_access.setWordWrap(True)
        self.chk_override_animal_forms = QCheckBox("Allow all animal forms (manual override)")
        self.chk_override_animal_forms.stateChanged.connect(self._on_animal_override_toggled)
        af_hdr.addWidget(self.lbl_animal_access, 1)
        af_hdr.addWidget(self.chk_override_animal_forms)
        fw_l.addLayout(af_hdr)

        af_filter = QHBoxLayout()
        self.txt_animal_search = QLineEdit()
        self.txt_animal_search.setPlaceholderText("Search beast / elemental forms…")
        self.txt_animal_search.textChanged.connect(self._refresh_animal_forms_table)
        self.cmb_animal_cr = QComboBox()
        self.cmb_animal_cr.addItem("Eligible Forms Only", "eligible")
        self.cmb_animal_cr.addItem("All Forms", "all")
        self.cmb_animal_cr.currentIndexChanged.connect(self._refresh_animal_forms_table)
        af_filter.addWidget(self.txt_animal_search, 2)
        af_filter.addWidget(self.cmb_animal_cr, 1)
        fw_l.addLayout(af_filter)

        af_split = QSplitter(Qt.Orientation.Vertical)
        self.tbl_animal_forms = QTableWidget(0, 4)
        self.tbl_animal_forms.setHorizontalHeaderLabels(["Form", "CR", "Speed", "Status"])
        self.tbl_animal_forms.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_animal_forms.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_animal_forms.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_animal_forms.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_animal_forms.verticalHeader().setVisible(False)
        self.tbl_animal_forms.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_animal_forms.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_animal_forms.currentCellChanged.connect(self._on_animal_form_selected)
        af_split.addWidget(self.tbl_animal_forms)

        af_btns = QHBoxLayout()
        self.btn_add_animal_form = QPushButton("+ Add Known Form")
        self.btn_add_animal_form.setObjectName("PrimaryBtn")
        self.btn_add_animal_form.clicked.connect(self._add_selected_animal_form)
        self.btn_rem_animal_form = QPushButton("Remove Form")
        self.btn_rem_animal_form.clicked.connect(self._remove_selected_animal_form)
        self.btn_toggle_active_form = QPushButton("Activate / Revert Wild Shape")
        self.btn_toggle_active_form.clicked.connect(self._toggle_active_animal_form)
        af_btns.addWidget(self.btn_add_animal_form)
        af_btns.addWidget(self.btn_rem_animal_form)
        af_btns.addWidget(self.btn_toggle_active_form)
        af_btns.addStretch()
        fw_l.addLayout(af_btns)

        af_custom_btns = QHBoxLayout()
        self.btn_custom_animal_form = QPushButton("+ Custom Form")
        self.btn_custom_animal_form.clicked.connect(self._create_custom_animal_form)
        self.btn_edit_custom_animal_form = QPushButton("Edit Custom")
        self.btn_edit_custom_animal_form.clicked.connect(self._edit_selected_custom_animal_form)
        af_custom_btns.addWidget(self.btn_custom_animal_form)
        af_custom_btns.addWidget(self.btn_edit_custom_animal_form)
        af_custom_btns.addStretch()
        fw_l.addLayout(af_custom_btns)

        self.lbl_known_animal_forms = QLabel("Known / Saved Forms: None")
        self.lbl_known_animal_forms.setObjectName("MutedText")
        self.lbl_known_animal_forms.setWordWrap(True)
        fw_l.addWidget(self.lbl_known_animal_forms)

        self.animal_form_browser = QTextBrowser()
        af_split.addWidget(self.animal_form_browser)
        af_split.setSizes([220, 220])
        fw_l.addWidget(af_split, 1)
        return forms_w

    def _custom_animal_form_ids(self) -> set[str]:
        return {
            str(d.get("id") or "").strip()
            for d in self.state.custom_animal_forms
            if isinstance(d, dict) and str(d.get("id") or "").strip()
        }

    def _sync_animal_forms_tab(self) -> None:
        access = compute_animal_form_access(self.state, self.computed, self.repo)
        ov_all = self.state.has_override("allow_all_animal_forms")
        self.chk_override_animal_forms.setChecked(ov_all)
        known_names = [
            (f.name if (f := find_animal_form(fid, self.state)) is not None else fid)
            for fid in self.state.animal_forms
        ]
        active_form = (
            find_animal_form(self.state.active_animal_form_id, self.state)
            if self.state.active_animal_form_id
            else None
        )
        active_name = active_form.name if active_form is not None else ""
        summary = access.source_summary
        if active_name:
            summary += f"  •  ACTIVE FORM: {active_name}"
        self.lbl_animal_access.setText(summary)
        known_txt = ", ".join(known_names) if known_names else "None"
        if access.known_forms_limit is not None:
            self.lbl_known_animal_forms.setText(
                f"Known / Saved Forms ({len(known_names)} / {access.known_forms_limit}): {known_txt}"
            )
        else:
            self.lbl_known_animal_forms.setText(f"Known / Saved Forms: {known_txt}")
        self._refresh_animal_forms_table()

    def _refresh_animal_forms_table(self) -> None:
        access = compute_animal_form_access(self.state, self.computed, self.repo)
        ov_all = self.state.has_override("allow_all_animal_forms")
        query = self.txt_animal_search.text().strip().lower()
        mode = self.cmb_animal_cr.currentData() or "eligible"
        custom_ids = self._custom_animal_form_ids()
        known_set = set(self.state.animal_forms)
        rows = []
        for form in all_animal_forms(self.state):
            is_custom = form.id in custom_ids
            if is_custom:
                eligible, reason = True, "Custom Animal Form"
            else:
                eligible, reason = is_form_eligible(form, access, override_all=ov_all)
            if mode == "eligible" and not eligible and not is_custom and form.id not in known_set:
                continue
            if (
                query
                and query not in form.name.lower()
                and query not in form.category.lower()
                and query not in form.creature_type.lower()
            ):
                continue
            rows.append((form, eligible, reason, is_custom))

        self.tbl_animal_forms.setUpdatesEnabled(False)
        self.tbl_animal_forms.setRowCount(len(rows))
        for r, (form, eligible, reason, is_custom) in enumerate(rows):
            n_it = QTableWidgetItem(form.name)
            n_it.setData(Qt.ItemDataRole.UserRole, form.id)
            n_it.setToolTip(reason)
            c_it = QTableWidgetItem(form.cr_label)
            c_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            s_it = QTableWidgetItem(form.speed)
            status_parts = []
            if form.id == self.state.active_animal_form_id:
                status_parts.append("ACTIVE")
            if is_custom:
                status_parts.append("Custom")
            if form.id in known_set:
                status_parts.append("Known")
            elif eligible and not is_custom:
                status_parts.append("Eligible")
            elif not is_custom:
                status_parts.append("Locked")
            st_it = QTableWidgetItem(" • ".join(status_parts))
            st_it.setToolTip(reason)
            self.tbl_animal_forms.setItem(r, 0, n_it)
            self.tbl_animal_forms.setItem(r, 1, c_it)
            self.tbl_animal_forms.setItem(r, 2, s_it)
            self.tbl_animal_forms.setItem(r, 3, st_it)
        self.tbl_animal_forms.setUpdatesEnabled(True)
        if rows and self.tbl_animal_forms.currentRow() < 0:
            self.tbl_animal_forms.selectRow(0)

    def _on_animal_override_toggled(self, checked: int) -> None:
        if self._updating:
            return
        self.state.set_override("allow_all_animal_forms", bool(checked))
        self._mark_dirty()
        self._sync_animal_forms_tab()

    def _selected_animal_form_id(self) -> str:
        row = self.tbl_animal_forms.currentRow()
        if row < 0:
            return ""
        item = self.tbl_animal_forms.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) or "" if item else ""

    def _select_animal_form_row_by_id(self, fid: str) -> None:
        for r in range(self.tbl_animal_forms.rowCount()):
            it = self.tbl_animal_forms.item(r, 0)
            if it and it.data(Qt.ItemDataRole.UserRole) == fid:
                self.tbl_animal_forms.selectRow(r)
                self._on_animal_form_selected(r, 0)
                return

    def _on_animal_form_selected(
        self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1
    ) -> None:
        if row < 0:
            return
        fid = self._selected_animal_form_id()
        form = find_animal_form(fid, self.state)
        if form is None:
            return
        access = compute_animal_form_access(self.state, self.computed, self.repo)
        transformed = compute_transformed_stats(form, self.state, self.computed, access)
        self.animal_form_browser.setHtml(render_animal_form_html(form, transformed))

    def _create_custom_animal_form(self) -> None:
        existing = {f.id for f in all_animal_forms(self.state)}
        dlg = CustomAnimalFormDialog(existing_ids=existing, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        form = dlg.build_animal_form()
        self.state.custom_animal_forms.append(animal_form_to_dict(form))
        if dlg.chk_add_known.isChecked() and form.id not in self.state.animal_forms:
            self.state.animal_forms.append(form.id)
        self._mark_dirty()
        self._sync_animal_forms_tab()
        self._select_animal_form_row_by_id(form.id)

    def _edit_selected_custom_animal_form(self) -> None:
        fid = self._selected_animal_form_id()
        if not fid:
            return
        if fid not in self._custom_animal_form_ids():
            QMessageBox.information(
                self,
                "Built-In Form",
                "Only custom animal forms can be edited directly. Click '+ Custom Form' to create a new custom variant.",
            )
            return
        cur_form = find_animal_form(fid, self.state)
        dlg = CustomAnimalFormDialog(initial_form=cur_form, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        updated = dlg.build_animal_form()
        updated_dict = animal_form_to_dict(updated)
        replaced = False
        for i, raw in enumerate(self.state.custom_animal_forms):
            if isinstance(raw, dict) and str(raw.get("id") or "").strip() == fid:
                self.state.custom_animal_forms[i] = updated_dict
                replaced = True
                break
        if not replaced:
            self.state.custom_animal_forms.append(updated_dict)
        if dlg.chk_add_known.isChecked() and updated.id not in self.state.animal_forms:
            self.state.animal_forms.append(updated.id)
        self._mark_dirty()
        self._sync_animal_forms_tab()
        self._select_animal_form_row_by_id(updated.id)

    def _add_selected_animal_form(self) -> None:
        fid = self._selected_animal_form_id()
        form = find_animal_form(fid, self.state)
        if form is None or fid in self.state.animal_forms:
            return
        is_custom = fid in self._custom_animal_form_ids()
        access = compute_animal_form_access(self.state, self.computed, self.repo)
        ov_all = self.state.has_override("allow_all_animal_forms")
        if not is_custom:
            eligible, reason = is_form_eligible(form, access, override_all=ov_all)
            if not eligible:
                QMessageBox.information(
                    self,
                    "Form Not Eligible",
                    f"{form.name} is restricted: {reason}\nEnable 'Allow all animal forms (manual override)' to add it anyway.",
                )
                return
            if (
                not ov_all
                and access.known_forms_limit is not None
                and len(self.state.animal_forms) >= access.known_forms_limit
            ):
                QMessageBox.information(
                    self,
                    "Known Forms Limit Reached",
                    f"5.5e Druid Known Forms limit ({access.known_forms_limit}) reached.\n"
                    "Remove a form or enable 'Allow all animal forms (manual override)'.",
                )
                return
        self.state.animal_forms.append(fid)
        self._mark_dirty()
        self._sync_animal_forms_tab()

    def _remove_selected_animal_form(self) -> None:
        fid = self._selected_animal_form_id()
        changed = False
        if fid in self.state.animal_forms:
            self.state.animal_forms.remove(fid)
            changed = True
        if fid and fid in self._custom_animal_form_ids():
            self.state.custom_animal_forms = [
                d
                for d in self.state.custom_animal_forms
                if not (isinstance(d, dict) and str(d.get("id") or "").strip() == fid)
            ]
            changed = True
        if changed:
            if self.state.active_animal_form_id == fid:
                self.state.active_animal_form_id = ""
            self._mark_dirty()
            self._sync_animal_forms_tab()

    def _toggle_active_animal_form(self) -> None:
        fid = self._selected_animal_form_id()
        if not fid:
            return
        if self.state.active_animal_form_id == fid:
            self.state.active_animal_form_id = ""
        else:
            form = find_animal_form(fid, self.state)
            is_custom = fid in self._custom_animal_form_ids()
            access = compute_animal_form_access(self.state, self.computed, self.repo)
            ov_all = self.state.has_override("allow_all_animal_forms")
            if not is_custom:
                eligible, reason = is_form_eligible(form, access, override_all=ov_all) if form else (False, "Unknown form")
                if not eligible and fid not in self.state.animal_forms:
                    QMessageBox.information(self, "Form Restricted", reason)
                    return
            self.state.active_animal_form_id = fid
            if fid not in self.state.animal_forms:
                self.state.animal_forms.append(fid)
        self._mark_dirty()
        self._sync_animal_forms_tab()
