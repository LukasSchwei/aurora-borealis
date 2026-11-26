"""Attached Companions sub-tab mixin."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...companions import (
    COMPANION_TEMPLATES,
    CompanionState,
    compute_companion_stats,
    create_companion_from_template,
    export_companion_pdf,
    load_dndcomp,
    render_companion_sheet_html,
    save_dndcomp,
)
from ...paths import get_os_downloads_dir


class CompanionsTabMixin:
    def _build_companions_subtab(self) -> QWidget:
        comp_w = QWidget()
        cw_l = QVBoxLayout(comp_w)
        cmp_top = QHBoxLayout()
        self.cmb_companion_tpl = QComboBox()
        for k, tpl in COMPANION_TEMPLATES.items():
            self.cmb_companion_tpl.addItem(tpl["name"], k)
        self.btn_add_companion = QPushButton("+ Add Companion")
        self.btn_add_companion.setObjectName("PrimaryBtn")
        self.btn_add_companion.clicked.connect(self._add_companion_from_template)
        self.btn_import_companion = QPushButton("Import .dndcomp")
        self.btn_import_companion.clicked.connect(self._import_companion_to_character)
        cmp_top.addWidget(self.cmb_companion_tpl, 1)
        cmp_top.addWidget(self.btn_add_companion)
        cmp_top.addWidget(self.btn_import_companion)
        cw_l.addLayout(cmp_top)

        self.chk_override_companions = QCheckBox("Allow all companion templates (manual override)")
        self.chk_override_companions.stateChanged.connect(self._on_companion_override_toggled)
        cw_l.addWidget(self.chk_override_companions)

        self.lst_char_companions = QListWidget()
        self.lst_char_companions.currentRowChanged.connect(self._on_char_companion_selected)
        cw_l.addWidget(self.lst_char_companions, 1)

        cmp_btns1 = QHBoxLayout()
        self.btn_open_companion = QPushButton("Open Companion Sheet")
        self.btn_open_companion.setObjectName("PrimaryBtn")
        self.btn_open_companion.clicked.connect(self._open_selected_attached_companion)
        self.btn_save_comp_file = QPushButton("Save as .dndcomp")
        self.btn_save_comp_file.clicked.connect(self._save_selected_companion_standalone)
        self.btn_export_comp_pdf = QPushButton("Export Companion PDF")
        self.btn_export_comp_pdf.clicked.connect(self._export_selected_companion_pdf)
        self.btn_remove_companion = QPushButton("Remove")
        self.btn_remove_companion.setObjectName("DangerBtn")
        self.btn_remove_companion.clicked.connect(self._remove_selected_companion)
        cmp_btns1.addWidget(self.btn_open_companion)
        cmp_btns1.addWidget(self.btn_export_comp_pdf)
        cmp_btns1.addStretch()
        cw_l.addLayout(cmp_btns1)

        cmp_btns2 = QHBoxLayout()
        cmp_btns2.addWidget(self.btn_save_comp_file)
        cmp_btns2.addWidget(self.btn_remove_companion)
        cmp_btns2.addStretch()
        cw_l.addLayout(cmp_btns2)

        self.companion_preview_browser = QTextBrowser()
        cw_l.addWidget(self.companion_preview_browser, 2)
        return comp_w

    def _sync_companions_tab(self) -> None:
        self.chk_override_companions.setChecked(self.state.has_override("allow_all_companions"))
        prev_row = self.lst_char_companions.currentRow()
        self.lst_char_companions.clear()
        for idx, cdict in enumerate(self.state.companions):
            comp = CompanionState.from_dict(cdict)
            stats = compute_companion_stats(comp)
            it = QListWidgetItem(
                f"{comp.name} ({comp.companion_type} • AC {stats['ac']} • HP {comp.max_hp})"
            )
            it.setData(Qt.ItemDataRole.UserRole, idx)
            self.lst_char_companions.addItem(it)
        if self.state.companions:
            target_row = prev_row if 0 <= prev_row < len(self.state.companions) else 0
            self.lst_char_companions.setCurrentRow(target_row)
            self._on_char_companion_selected(target_row)
        else:
            self.companion_preview_browser.setHtml(
                "<p>No companions attached. Choose a template above or import a <code>.dndcomp</code> file.</p>"
            )

    def _on_companion_override_toggled(self, checked: int) -> None:
        if self._updating:
            return
        self.state.set_override("allow_all_companions", bool(checked))
        self._mark_dirty()
        self._sync_companions_tab()

    def _on_char_companion_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.state.companions):
            return
        comp = CompanionState.from_dict(self.state.companions[row])
        self.companion_preview_browser.setHtml(render_companion_sheet_html(comp))

    def _add_companion_from_template(self) -> None:
        tpl_key = self.cmb_companion_tpl.currentData() or "custom"
        comp = create_companion_from_template(tpl_key, self.state, self.computed)
        self.state.companions.append(comp.to_dict())
        self._mark_dirty()
        self._sync_companions_tab()

    def _import_companion_to_character(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach Companion (.dndcomp)", str(get_os_downloads_dir()), "Companion Files (*.dndcomp);;All Files (*)"
        )
        if not path:
            return
        try:
            comp = load_dndcomp(Path(path))
            comp.owner_name = self.state.name or comp.owner_name
            comp.owner_level = self.state.level
            comp.owner_proficiency = self.computed.proficiency_bonus
            self.state.companions.append(comp.to_dict())
            self._mark_dirty()
            self._sync_companions_tab()
        except Exception as exc:
            QMessageBox.warning(self, "Import Companion Failed", str(exc))

    def _open_selected_attached_companion(self) -> None:
        row = self.lst_char_companions.currentRow()
        if row < 0 or row >= len(self.state.companions):
            return
        comp = CompanionState.from_dict(self.state.companions[row])
        self._editing_attached_companion_idx = row
        self.companion_view.set_characters_dir(self._characters_dir())
        path = Path(comp.file_path) if comp.file_path else None
        self.companion_view.load_companion(comp, path=path)
        self.screen_stack.setCurrentWidget(self.companion_view)
        self.title_bar.set_breadcrumb(f"Companion: {comp.name}")

    def _save_selected_companion_standalone(self) -> None:
        row = self.lst_char_companions.currentRow()
        if row < 0 or row >= len(self.state.companions):
            return
        comp = CompanionState.from_dict(self.state.companions[row])
        safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", comp.name or "companion").strip(" .") or "companion"
        default_path = str(get_os_downloads_dir() / f"{safe_stem}.dndcomp")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Companion (.dndcomp)", default_path, "Aurora Companion (*.dndcomp)"
        )
        if not path:
            return
        if not path.lower().endswith(".dndcomp"):
            path += ".dndcomp"
        save_dndcomp(comp, Path(path))
        comp.file_path = path
        self.state.companions[row] = comp.to_dict()
        self._mark_dirty()
        self.refresh_library()
        self._sync_companions_tab()

    def _export_selected_companion_pdf(self) -> None:
        row = self.lst_char_companions.currentRow()
        if row < 0 or row >= len(self.state.companions):
            return
        comp = CompanionState.from_dict(self.state.companions[row])
        safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", comp.name or "companion").strip(" .") or "companion"
        default_path = str(get_os_downloads_dir() / f"{safe_stem}.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Companion Sheet PDF", default_path, "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        export_companion_pdf(comp, Path(path))
        self.statusBar().showMessage(f"Exported Companion PDF to {path}")

    def _remove_selected_companion(self) -> None:
        row = self.lst_char_companions.currentRow()
        if 0 <= row < len(self.state.companions):
            self.state.companions.pop(row)
            self._mark_dirty()
            self._sync_companions_tab()
