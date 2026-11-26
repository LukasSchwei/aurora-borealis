"""Library management, File/PDF/Bundle I/O, Sources, Homebrew, and Build Planner mixin."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ...bundle import BUNDLE_EXTENSION, export_character_bundle, import_character_bundle
from ...companions import create_companion_from_template, export_companion_pdf, load_dndcomp
from ...config import save_config
from ...extractor import extract_msi_assets
from ...library import delete_character, duplicate_character, scan_characters_folder
from ...models import CharacterState, ComputedCharacter
from ...paths import get_os_downloads_dir
from ...pdf_export import export_character_pdf, validate_character_for_pdf
from ...persistence import default_character_extension, load_dnd5e, save_dnd5e
from ..dialogs import DuplicateReportDialog, NewCharacterDialog
from ..homebrew_editor import HomebrewEditorDialog
from ..planner_dialog import BuildPlannerDialog
from ..widgets.item_icons import _safe_filename


class LibraryIOMixin:
    def _characters_dir(self) -> Path:
        return Path(self.config.characters_dir)

    def _save_config(self) -> None:
        save_config(self.config, self.config_path)

    def refresh_library(self) -> None:
        folder = self._characters_dir()
        folder.mkdir(parents=True, exist_ok=True)
        self.companion_view.set_characters_dir(folder)
        summaries = scan_characters_folder(folder, set(self.config.favorites))
        self.select_view.set_header_info(
            folder_path=str(folder),
            element_count=len(self.repo.by_id),
            dup_count=len(self.repo.duplicates),
            index_count=len(self.config.installed_indexes),
        )
        self.select_view.set_characters(summaries)

    def _change_characters_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Characters Folder", str(self._characters_dir())
        )
        if chosen:
            self.config.characters_dir = chosen
            self._save_config()
            self.companion_view.set_characters_dir(Path(chosen))
            self.refresh_library()

    def _toggle_favorite(self, filename: str) -> None:
        if filename in self.config.favorites:
            self.config.favorites.remove(filename)
        else:
            self.config.favorites.append(filename)
        self._save_config()
        self.refresh_library()

    def _duplicate_library_char(self, path: Path) -> None:
        try:
            duplicate_character(path)
            self.refresh_library()
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", str(exc))

    def _delete_library_char(self, path: Path) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Character",
            f"Delete {path.name} from {path.parent}?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_character(path)
            self.refresh_library()

    def _confirm_missing_fields_before_pdf(
        self, state: CharacterState, computed: ComputedCharacter
    ) -> bool:
        missing = validate_character_for_pdf(state, computed, self.repo)
        if not missing:
            return True
        bullet_list = "\n".join(f"• {m}" for m in missing)
        reply = QMessageBox.warning(
            self,
            "Incomplete Character Sheet",
            f"The following fields are missing or incomplete:\n\n{bullet_list}\n\nExport PDF anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _export_pdf_for_path(self, char_path: Path) -> None:
        try:
            st = load_dnd5e(char_path, self.repo)
            comp = self.engine.evaluate(st)
            if not self._confirm_missing_fields_before_pdf(st, comp):
                return
            safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", st.name or "character").strip(" .") or "character"
            out_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Character Sheet PDF",
                str(get_os_downloads_dir() / f"{safe_stem}.pdf"),
                "PDF Files (*.pdf)",
            )
            if out_path:
                if not out_path.lower().endswith(".pdf"):
                    out_path += ".pdf"
                export_character_pdf(
                    st, comp, self.repo, Path(out_path), templates_dir=self.templates_dir
                )
                self.statusBar().showMessage(f"Exported PDF to {out_path}")
        except Exception as exc:
            QMessageBox.critical(self, "PDF Export Failed", str(exc))

    def _find_character_name_conflict(
        self, name: str, exclude_path: Optional[Path] = None
    ) -> Optional[Path]:
        folder = self._characters_dir()
        if not folder.is_dir():
            return None
        exclude_res = exclude_path.resolve() if exclude_path is not None else None
        for rs in ("5e", "5.5e"):
            candidate = folder / _safe_filename(name, rs)
            if candidate.exists() and (exclude_res is None or candidate.resolve() != exclude_res):
                return candidate
        norm = (name or "").strip().lower()
        if norm:
            for summary in scan_characters_folder(folder):
                if getattr(summary, "entry_kind", "character") != "character":
                    continue
                if exclude_res is not None and summary.path.resolve() == exclude_res:
                    continue
                if summary.name.strip().lower() == norm:
                    return summary.path
        return None

    def import_bundle_file(self, bundle_path: Path) -> Path:
        res = import_character_bundle(bundle_path, self._characters_dir(), self.custom_dir)
        if res.get("xml_paths"):
            self.reload_repository()
        self.refresh_library()
        char_path = res["character_path"]
        self.statusBar().showMessage(
            f"Imported bundle: {char_path.name} ({len(res['companion_paths'])} companion(s), {len(res['xml_paths'])} custom XML(s))"
        )
        return char_path

    def export_bundle_dialog(self) -> None:
        safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", self.state.name or "character").strip(" .") or "character"
        default_name = str(get_os_downloads_dir() / f"{safe_stem}{BUNDLE_EXTENSION}")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Portable Character Bundle",
            default_name,
            f"Aurora Bundle (*{BUNDLE_EXTENSION});;ZIP Archive (*.zip)",
        )
        if not path:
            return
        if not path.lower().endswith((BUNDLE_EXTENSION, ".zip")):
            path += BUNDLE_EXTENSION
        custom_dirs = [self.custom_dir, *(Path(d) for d in self.config.custom_dirs)]
        try:
            manifest = export_character_bundle(
                self.state, self.computed, self.repo, Path(path), custom_dirs=custom_dirs
            )
            self.statusBar().showMessage(
                f"Exported bundle to {path} ({len(manifest['companions'])} companion(s), {len(manifest['custom_xml'])} custom XML(s))"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Bundle Export Failed", str(exc))

    def import_dnd5e_to_library(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Aurora File (.dnd5e / .dnd55e / .dndcomp / .aurorapack)",
            str(get_os_downloads_dir()),
            f"Aurora Files (*.dnd5e *.dnd55e *.dndcomp *{BUNDLE_EXTENSION});;All Files (*)",
        )
        if not path:
            return
        src = Path(path)
        if src.suffix.lower() in (BUNDLE_EXTENSION, ".zip"):
            try:
                char_path = self.import_bundle_file(src)
                self.open_character_file(char_path)
            except Exception as exc:
                QMessageBox.critical(self, "Bundle Import Failed", str(exc))
            return

        dest_dir = self._characters_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if src.resolve() != dest.resolve():
            if dest.exists():
                stem = src.stem
                idx = 2
                while (dest_dir / f"{stem}_{idx}{src.suffix}").exists():
                    idx += 1
                dest = dest_dir / f"{stem}_{idx}{src.suffix}"
            shutil.copy2(src, dest)
        self.refresh_library()
        if dest.suffix.lower() == ".dndcomp":
            self.open_companion_file(dest)
        else:
            self.open_character_file(dest)

    def new_character_with_dialog(self) -> None:
        if not self.confirm_leave_character():
            return
        dlg = NewCharacterDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        chosen_name = dlg.selected_name()
        conflict = self._find_character_name_conflict(chosen_name)
        if conflict is not None:
            QMessageBox.warning(
                self,
                "Character Name Already Exists",
                f"A character named '{chosen_name}' already exists ({conflict.name}).\n"
                "Please choose a unique character name to avoid overwriting it.",
            )
            return
        self.current_file = None
        self.state = CharacterState(
            name=chosen_name,
            ruleset=dlg.selected_ruleset(),
            portrait_path=dlg.portrait_path,
            portrait_base64=dlg.portrait_base64,
        )
        self._choices_sig = None
        self._dirty = True
        self._recalculate_and_refresh()
        self._switch_builder_tab(0)
        self.show_builder()

    def new_character(self) -> None:
        if not self.confirm_leave_character():
            return
        self.current_file = None
        self.state = CharacterState()
        self._choices_sig = None
        self._dirty = True
        self._recalculate_and_refresh()
        self._switch_builder_tab(0)
        self.show_builder()

    def new_companion(self) -> None:
        if not self.confirm_leave_character():
            return
        self._editing_attached_companion_idx = None
        comp = create_companion_from_template("wolf_companion")
        comp.name = "New Companion"
        self.companion_view.set_characters_dir(self._characters_dir())
        self.companion_view.load_companion(comp, path=None)
        self.screen_stack.setCurrentWidget(self.companion_view)
        self.title_bar.set_breadcrumb("Companion: New Companion")

    def open_companion_file(self, path: Path) -> None:
        if not self.confirm_leave_character():
            return
        try:
            comp = load_dndcomp(path)
            self._editing_attached_companion_idx = None
            self.companion_view.set_characters_dir(self._characters_dir())
            self.companion_view.load_companion(comp, path=path)
            self.screen_stack.setCurrentWidget(self.companion_view)
            self.title_bar.set_breadcrumb(f"Companion: {comp.name}")
            self.statusBar().showMessage(f"Opened companion {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Open Companion Failed", f"Could not load {path}:\n{exc}")

    def _on_companion_saved(self, path: Path) -> None:
        if self._editing_attached_companion_idx is not None:
            idx = self._editing_attached_companion_idx
            if 0 <= idx < len(self.state.companions):
                self.companion_view.comp.file_path = str(path)
                self.state.companions[idx] = self.companion_view.comp.to_dict()
                self._mark_dirty()
                self._sync_companions_tab()
        self.refresh_library()

    def _on_companion_back(self) -> None:
        if self._editing_attached_companion_idx is not None:
            idx = self._editing_attached_companion_idx
            self._editing_attached_companion_idx = None
            if 0 <= idx < len(self.state.companions):
                self.state.companions[idx] = self.companion_view.comp.to_dict()
                self._mark_dirty()
                self._sync_companions_tab()
            self.show_builder()
            return
        self.show_character_select()

    def _export_companion_pdf_for_path(self, path: Path) -> None:
        try:
            comp = load_dndcomp(path)
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))
            return
        safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", comp.name or "companion").strip(" .") or "companion"
        default_name = str(get_os_downloads_dir() / f"{safe_stem}.pdf")
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export Companion Sheet PDF", default_name, "PDF Files (*.pdf)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"
        export_companion_pdf(comp, Path(out_path))
        self.statusBar().showMessage(f"Exported Companion PDF to {out_path}")

    def open_dialog(self) -> None:
        if not self.confirm_leave_character():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Aurora File",
            str(get_os_downloads_dir()),
            f"Aurora Files (*.dnd5e *.dnd55e *.dndcomp *{BUNDLE_EXTENSION});;All Files (*)",
        )
        if path:
            p = Path(path)
            if p.suffix.lower() in (BUNDLE_EXTENSION, ".zip"):
                char_path = self.import_bundle_file(p)
                self.open_character_file(char_path)
            elif p.suffix.lower() == ".dndcomp":
                self.open_companion_file(p)
            else:
                self.open_character_file(p)

    def open_character_file(self, path: Path) -> None:
        try:
            p = Path(path)
            if p.suffix.lower() in (BUNDLE_EXTENSION, ".zip"):
                p = self.import_bundle_file(p)
            self.state = load_dnd5e(p, self.repo)
            self.current_file = p
            self._choices_sig = None
            self._equip_catalog_sig = None
            self._spell_catalog_sig = None
            self._dirty = False
            self._recalculate_and_refresh()
            self._switch_builder_tab(0)
            self.show_builder()
            self.statusBar().showMessage(f"Opened {p}")
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", f"Could not load {path}:\n{exc}")

    def save_character(self) -> bool:
        if self.current_file is None:
            folder = self._characters_dir()
            folder.mkdir(parents=True, exist_ok=True)
            conflict = self._find_character_name_conflict(self.state.name)
            if conflict is not None:
                QMessageBox.warning(
                    self,
                    "Duplicate Character Name",
                    f"Cannot save: a character named '{self.state.name}' already exists ({conflict.name}).\n"
                    "Please rename your character or use Save As with a different filename.",
                )
                return False
            target_file = folder / _safe_filename(self.state.name, self.state.ruleset)
        else:
            conflict = self._find_character_name_conflict(self.state.name, exclude_path=self.current_file)
            if conflict is not None:
                QMessageBox.warning(
                    self,
                    "Duplicate Character Name",
                    f"Another character named '{self.state.name}' already exists ({conflict.name}).\n"
                    "Please choose a unique character name before saving.",
                )
                return False
            target_file = self.current_file
        try:
            save_dnd5e(self.state, self.repo, self.computed, target_file)
            self.current_file = target_file
            self._dirty = False
            self.refresh_library()
            self.statusBar().showMessage(f"Saved {self.current_file}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return False

    def save_character_as(self) -> None:
        ext = default_character_extension(self.state.ruleset)
        default_path = str(get_os_downloads_dir() / _safe_filename(self.state.name, self.state.ruleset))
        filt = (
            "Aurora 5.5e Character (*.dnd55e);;Aurora 5e Character (*.dnd5e)"
            if ext == ".dnd55e"
            else "Aurora 5e Character (*.dnd5e);;Aurora 5.5e Character (*.dnd55e)"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Save Aurora Character", default_path, filt)
        if path:
            low = path.lower()
            if not (low.endswith(".dnd5e") or low.endswith(".dnd55e")):
                path += ext
            target = Path(path)
            if target.exists() and (self.current_file is None or target.resolve() != self.current_file.resolve()):
                QMessageBox.warning(
                    self,
                    "File Already Exists",
                    f"Cannot overwrite existing character file '{target.name}'. Please pick a different filename.",
                )
                return
            self.current_file = target
            self.save_character()

    def export_pdf_dialog(self) -> None:
        if not self._confirm_missing_fields_before_pdf(self.state, self.computed):
            return
        safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", self.state.name or "character").strip(" .") or "character"
        default_name = str(get_os_downloads_dir() / f"{safe_stem}.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Character Sheet PDF", default_name, "PDF Files (*.pdf)"
        )
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            try:
                export_character_pdf(
                    self.state,
                    self.computed,
                    self.repo,
                    Path(path),
                    templates_dir=self.templates_dir,
                )
                self.statusBar().showMessage(f"Exported PDF to {path}")
            except Exception as exc:
                QMessageBox.critical(self, "PDF Export Failed", str(exc))

    def open_homebrew_editor(self) -> None:
        dlg = HomebrewEditorDialog(self.custom_dir, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.reload_repository()
            if dlg.saved_path:
                self.statusBar().showMessage(f"Saved homebrew pack {dlg.saved_path.name} and reloaded content")

    def open_build_planner(self) -> None:
        dlg = BuildPlannerDialog(self.state, self.computed, self.repo, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.state.build_plan = dlg.build_plan()
            self._choices_sig = None
            self._mark_dirty()
            self._recalculate_and_refresh()

    def reload_repository(self) -> None:
        self.repo.clear()
        self.repo.load_directory(self.data_dir)
        if self.custom_dir.is_dir():
            self.repo.load_directory(self.custom_dir)
        for cdir in self.config.custom_dirs:
            self.repo.load_directory(Path(cdir))

        self._choices_sig = None
        self._spell_catalog_sig = None
        self._equip_catalog_sig = None
        if hasattr(self, "cmb_spell_class"):
            prev_cls = self.cmb_spell_class.currentData() or ""
            self.cmb_spell_class.blockSignals(True)
            self.cmb_spell_class.clear()
            self.cmb_spell_class.addItem("All Classes", "")
            for cname in self.repo.available_spell_classes():
                self.cmb_spell_class.addItem(cname, cname.lower())
            idx = self.cmb_spell_class.findData(prev_cls)
            self.cmb_spell_class.setCurrentIndex(idx if idx >= 0 else 0)
            self.cmb_spell_class.blockSignals(False)

        self.tab_race.refresh_sources()
        self.tab_race.refresh_list()
        self.tab_class.refresh_sources()
        self.tab_class.refresh_list()
        self.tab_background.refresh_sources()
        self.tab_background.refresh_list()
        self._populate_element_combo(self.cmb_align, "Alignment", allow_none=True)
        self._populate_element_combo(self.cmb_deity, "Deity", allow_none=True)
        self._refresh_feat_browser()
        self._refresh_equip_catalog()
        self._refresh_spell_catalog()
        self._recalculate_and_refresh()
        self.refresh_library()
        self.github_view.set_duplicate_count(len(self.repo.duplicates))
        self._update_status_summary()

    def _update_status_summary(self) -> None:
        self.statusBar().showMessage(
            f"Loaded {len(self.repo.by_id)} elements ({self.repo.file_count} XML files, {len(self.repo.duplicates)} duplicates detected)"
        )

    def _on_github_content_changed(self, installed: list[dict]) -> None:
        self.config.installed_indexes = installed
        if installed:
            self.config.auto_imported_official = True
        self._save_config()
        self.reload_repository()

    def _trigger_auto_official_sync(self) -> None:
        self.statusBar().showMessage("Syncing official Aurora & Aurora Legacy content from GitHub…")
        self.github_view.start_official_sync()

    def show_duplicates_dialog(self) -> None:
        dlg = DuplicateReportDialog(self.repo.duplicates, self)
        dlg.exec()

    def import_custom_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Custom Aurora XML Folder", str(get_os_downloads_dir())
        )
        if folder:
            if folder not in self.config.custom_dirs:
                self.config.custom_dirs.append(folder)
                self._save_config()
            self.reload_repository()
            self.statusBar().showMessage(f"Imported custom XML folder: {folder}")

    def reextract_msi_data(self) -> None:
        msi = self.msi_path
        if msi is None or not msi.is_file():
            chosen, _ = QFileDialog.getOpenFileName(
                self, "Select Aurora Setup.msi", str(get_os_downloads_dir()), "Windows Installer (*.msi)"
            )
            if not chosen:
                return
            msi = Path(chosen)
            self.msi_path = msi
        try:
            extract_msi_assets(msi, self.data_dir, self.templates_dir)
            self.reload_repository()
        except Exception as exc:
            QMessageBox.critical(self, "Extraction Failed", str(exc))
