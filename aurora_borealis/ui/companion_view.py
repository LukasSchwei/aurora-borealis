"""Standalone Companion Editor & Live Character Sheet View (.dndcomp & PDF export)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..companions import (
    COMPANION_TEMPLATES,
    CompanionAction,
    CompanionState,
    CompanionTrait,
    compute_companion_stats,
    create_companion_from_template,
    export_companion_pdf,
    render_companion_sheet_html,
    save_dndcomp,
)
from ..models import ABILITIES, ABILITY_ABBR, SKILLS
from ..paths import get_os_downloads_dir
from ..persistence import encode_portrait_file
from .dialogs import pixmap_from_portrait
from .icons import apply_button_icon
from .ui_helpers import ensure_widgets_fit


def _fmt_mod(val: int) -> str:
    return f"+{val}" if val >= 0 else str(val)


class CompanionEditorView(QWidget):
    """Screen 4: Standalone Companion Character Sheet & Editor (.dndcomp)."""

    back_requested = Signal()
    saved = Signal(Path)
    deleted = Signal(Path)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.comp = CompanionState()
        self.current_file: Optional[Path] = None
        self._characters_dir: Optional[Path] = None
        self._updating = False
        self._dirty = False
        self._build_ui()

    def set_characters_dir(self, folder: Path) -> None:
        self._characters_dir = Path(folder)

    def load_companion(self, comp: CompanionState, path: Optional[Path] = None) -> None:
        self.comp = comp
        self.current_file = Path(path) if path else (Path(comp.file_path) if comp.file_path else None)
        self._dirty = False
        self._sync_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("TopNavBar")
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(14, 8, 14, 8)
        btn_back = QPushButton("Characters")
        apply_button_icon(btn_back, "arrow-left", size=15)
        btn_back.clicked.connect(self.back_requested.emit)
        self.lbl_title = QLabel("Companion")
        self.lbl_title.setObjectName("TitleText")
        self.lbl_badge = QLabel("Companion")
        self.lbl_badge.setObjectName("RulesetPill")
        self.btn_save = QPushButton("Save (.dndcomp)")
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.clicked.connect(self.save_companion)
        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.clicked.connect(self.save_companion_as)
        self.btn_pdf = QPushButton("Export Companion PDF")
        self.btn_pdf.clicked.connect(self.export_pdf_dialog)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.clicked.connect(self._delete_current)

        tb.addWidget(btn_back)
        tb.addWidget(self.lbl_title)
        tb.addWidget(self.lbl_badge)
        tb.addStretch()
        tb.addWidget(self.btn_save)
        tb.addWidget(self.btn_save_as)
        tb.addWidget(self.btn_pdf)
        tb.addWidget(self.btn_delete)
        root.addWidget(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_rail())
        splitter.addWidget(self._build_right_tabs())
        splitter.setSizes([340, 1020])
        root.addWidget(splitter, 1)
        ensure_widgets_fit(self)

    def _build_left_rail(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(420)
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(10, 10, 6, 10)
        vl.setSpacing(8)

        card = QFrame()
        card.setObjectName("SidebarCard")
        cl = QHBoxLayout(card)
        self.btn_portrait = QPushButton("Add\nPhoto")
        self.btn_portrait.setObjectName("RailPortraitBtn")
        self.btn_portrait.setFixedSize(64, 64)
        self.btn_portrait.clicked.connect(self._pick_portrait)
        self.lbl_portrait = QLabel()
        self.lbl_portrait.setObjectName("PortraitFrame")
        self.lbl_portrait.setFixedSize(64, 64)
        self.lbl_portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_portrait.hide()
        ncol = QVBoxLayout()
        self.lbl_rail_name = QLabel("Companion")
        self.lbl_rail_name.setObjectName("CharTitle")
        self.lbl_rail_name.setWordWrap(True)
        self.lbl_rail_sub = QLabel("")
        self.lbl_rail_sub.setObjectName("CharSubtitle")
        self.lbl_rail_sub.setWordWrap(True)
        ncol.addWidget(self.lbl_rail_name)
        ncol.addWidget(self.lbl_rail_sub)
        cl.addWidget(self.btn_portrait)
        cl.addWidget(self.lbl_portrait)
        cl.addLayout(ncol, 1)
        vl.addWidget(card)

        stats_card = QFrame()
        stats_card.setObjectName("SidebarCard")
        sg = QGridLayout(stats_card)
        self.lbl_ac = QLabel("13")
        self.lbl_hp = QLabel("15")
        self.lbl_spd = QLabel("40 ft.")
        self.lbl_pp = QLabel("11")
        for lbl, title, r, c in (
            (self.lbl_ac, "Armor Class", 0, 0),
            (self.lbl_hp, "Max HP", 0, 1),
            (self.lbl_spd, "Speed", 1, 0),
            (self.lbl_pp, "Passive Perc.", 1, 1),
        ):
            lbl.setObjectName("StatValue")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tl = QLabel(title)
            tl.setObjectName("StatLabel")
            tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box = QVBoxLayout()
            box.addWidget(lbl)
            box.addWidget(tl)
            sg.addLayout(box, r, c)
        vl.addWidget(stats_card)

        tpl_box = QGroupBox("Template && Master Scaling")
        tl = QFormLayout(tpl_box)
        self.cmb_template = QComboBox()
        for key, tpl in COMPANION_TEMPLATES.items():
            self.cmb_template.addItem(tpl["name"], key)
        btn_apply_tpl = QPushButton("Apply Template")
        btn_apply_tpl.clicked.connect(self._apply_template)
        trow = QHBoxLayout()
        trow.addWidget(self.cmb_template, 1)
        trow.addWidget(btn_apply_tpl)
        tl.addRow("Template:", trow)

        self.txt_owner = QLineEdit()
        self.txt_owner.textChanged.connect(self._on_meta_changed)
        tl.addRow("Owner / Master:", self.txt_owner)

        self.chk_scale = QCheckBox("Scale with Owner Level && PB")
        self.chk_scale.stateChanged.connect(self._on_meta_changed)
        tl.addRow(self.chk_scale)

        self.spn_owner_lvl = QSpinBox()
        self.spn_owner_lvl.setRange(1, 20)
        self.spn_owner_lvl.valueChanged.connect(self._on_meta_changed)
        tl.addRow("Owner Level:", self.spn_owner_lvl)

        self.spn_owner_pb = QSpinBox()
        self.spn_owner_pb.setRange(2, 6)
        self.spn_owner_pb.valueChanged.connect(self._on_meta_changed)
        tl.addRow("Owner PB:", self.spn_owner_pb)

        self.spn_owner_mod = QSpinBox()
        self.spn_owner_mod.setRange(-2, 10)
        self.spn_owner_mod.valueChanged.connect(self._on_meta_changed)
        tl.addRow("Spell/Ability Mod:", self.spn_owner_mod)

        vl.addWidget(tpl_box)
        vl.addStretch()
        return panel

    def _build_right_tabs(self) -> QTabWidget:
        self.tabs = QTabWidget()

        # Tab 0: Live Character Sheet
        sheet_w = QWidget()
        sl = QVBoxLayout(sheet_w)
        self.sheet_browser = QTextBrowser()
        self.sheet_browser.setOpenExternalLinks(True)
        sl.addWidget(self.sheet_browser)
        self.tabs.addTab(sheet_w, "Character Sheet")

        # Tab 1: Stats & Defenses
        stats_scroll = QScrollArea()
        stats_scroll.setWidgetResizable(True)
        stats_host = QWidget()
        stl = QVBoxLayout(stats_host)

        id_box = QGroupBox("Identity && Combat")
        idf = QGridLayout(id_box)
        self.txt_name = QLineEdit()
        self.txt_type = QLineEdit()
        self.txt_creature_type = QLineEdit()
        self.txt_size = QLineEdit()
        self.txt_cr = QLineEdit()
        self.txt_speed = QLineEdit()
        self.txt_hit_dice = QLineEdit()
        self.spn_ac = QSpinBox()
        self.spn_ac.setRange(1, 30)
        self.spn_max_hp = QSpinBox()
        self.spn_max_hp.setRange(1, 999)
        self.spn_cur_hp = QSpinBox()
        self.spn_cur_hp.setRange(0, 999)
        self.spn_tmp_hp = QSpinBox()
        self.spn_tmp_hp.setRange(0, 999)

        fields = [
            ("Name:", self.txt_name, 0, 0),
            ("Role / Type:", self.txt_type, 0, 2),
            ("Creature Type:", self.txt_creature_type, 1, 0),
            ("Size:", self.txt_size, 1, 2),
            ("CR:", self.txt_cr, 2, 0),
            ("Speed:", self.txt_speed, 2, 2),
            ("Armor Class:", self.spn_ac, 3, 0),
            ("Max HP:", self.spn_max_hp, 3, 2),
            ("Current HP:", self.spn_cur_hp, 4, 0),
            ("Temp HP:", self.spn_tmp_hp, 4, 2),
            ("Hit Dice:", self.txt_hit_dice, 5, 0),
        ]
        for label, w, r, c in fields:
            idf.addWidget(QLabel(label), r, c)
            idf.addWidget(w, r, c + 1)
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._on_meta_changed)
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self._on_meta_changed)
        stl.addWidget(id_box)

        ab_box = QGroupBox("Ability Scores && Saving Throws")
        abl = QGridLayout(ab_box)
        self.ab_spins: dict[str, QSpinBox] = {}
        self.save_checks: dict[str, QCheckBox] = {}
        for idx, ab in enumerate(ABILITIES):
            r, c = divmod(idx, 3)
            abl.addWidget(QLabel(ABILITY_ABBR[ab]), r, c * 3)
            sp = QSpinBox()
            sp.setRange(1, 30)
            sp.valueChanged.connect(self._on_meta_changed)
            chk = QCheckBox("Save")
            chk.stateChanged.connect(self._on_meta_changed)
            abl.addWidget(sp, r, c * 3 + 1)
            abl.addWidget(chk, r, c * 3 + 2)
            self.ab_spins[ab] = sp
            self.save_checks[ab] = chk
        stl.addWidget(ab_box)

        prof_box = QGroupBox("Senses, Languages && Immunities")
        pf = QFormLayout(prof_box)
        self.txt_senses = QLineEdit()
        self.txt_languages = QLineEdit()
        self.txt_dmg_imm = QLineEdit()
        self.txt_cond_imm = QLineEdit()
        self.txt_skills = QLineEdit()
        self.txt_skills.setPlaceholderText("Comma-separated skill proficiencies, e.g. Perception, Stealth")
        for w in (self.txt_senses, self.txt_languages, self.txt_dmg_imm, self.txt_cond_imm, self.txt_skills):
            w.textChanged.connect(self._on_meta_changed)
        pf.addRow("Skills:", self.txt_skills)
        pf.addRow("Senses:", self.txt_senses)
        pf.addRow("Languages:", self.txt_languages)
        pf.addRow("Damage Immunities:", self.txt_dmg_imm)
        pf.addRow("Condition Immunities:", self.txt_cond_imm)
        stl.addWidget(prof_box)
        stl.addStretch()
        stats_scroll.setWidget(stats_host)
        self.tabs.addTab(stats_scroll, "Stats && Defenses")

        # Tab 2: Traits & Actions
        ta_w = QWidget()
        tal = QVBoxLayout(ta_w)
        tr_box = QGroupBox("Traits")
        trl = QVBoxLayout(tr_box)
        self.tbl_traits = QTableWidget(0, 2)
        self.tbl_traits.setHorizontalHeaderLabels(["Trait Name", "Description"])
        self.tbl_traits.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_traits.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_traits.verticalHeader().setVisible(False)
        self.tbl_traits.itemChanged.connect(self._on_traits_actions_edited)
        trl.addWidget(self.tbl_traits)
        tr_btns = QHBoxLayout()
        b_add_tr = QPushButton("+ Add Trait")
        b_add_tr.clicked.connect(self._add_trait_row)
        b_rem_tr = QPushButton("Remove Trait")
        b_rem_tr.clicked.connect(self._remove_trait_row)
        tr_btns.addWidget(b_add_tr)
        tr_btns.addWidget(b_rem_tr)
        tr_btns.addStretch()
        trl.addLayout(tr_btns)
        tal.addWidget(tr_box, 1)

        act_box = QGroupBox("Actions")
        acl = QVBoxLayout(act_box)
        self.tbl_actions = QTableWidget(0, 4)
        self.tbl_actions.setHorizontalHeaderLabels(["Action Name", "Attack", "Damage", "Description"])
        self.tbl_actions.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_actions.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_actions.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_actions.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_actions.verticalHeader().setVisible(False)
        self.tbl_actions.itemChanged.connect(self._on_traits_actions_edited)
        acl.addWidget(self.tbl_actions)
        ac_btns = QHBoxLayout()
        b_add_ac = QPushButton("+ Add Action")
        b_add_ac.clicked.connect(self._add_action_row)
        b_rem_ac = QPushButton("Remove Action")
        b_rem_ac.clicked.connect(self._remove_action_row)
        ac_btns.addWidget(b_add_ac)
        ac_btns.addWidget(b_rem_ac)
        ac_btns.addStretch()
        acl.addLayout(ac_btns)
        tal.addWidget(act_box, 1)
        self.tabs.addTab(ta_w, "Traits && Actions")

        # Tab 3: Notes
        notes_w = QWidget()
        nl = QVBoxLayout(notes_w)
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.textChanged.connect(self._on_meta_changed)
        nl.addWidget(self.txt_notes)
        self.tabs.addTab(notes_w, "Notes")

        return self.tabs

    def _sync_ui(self) -> None:
        self._updating = True
        try:
            c = self.comp
            stats = compute_companion_stats(c)
            self.lbl_title.setText(c.name or "New Companion")
            self.lbl_badge.setText(c.companion_type or "Companion")
            self.lbl_rail_name.setText(c.name or "New Companion")
            self.lbl_rail_sub.setText(f"{c.size} {c.creature_type} • CR {c.cr}")
            self.lbl_ac.setText(str(stats["ac"]))
            self.lbl_hp.setText(str(stats["max_hp"]))
            self.lbl_spd.setText(c.speed)
            self.lbl_pp.setText(str(stats["passive_perception"]))

            pix = pixmap_from_portrait(c.portrait_base64, c.portrait_path, size=64)
            if pix:
                self.lbl_portrait.setPixmap(pix)
                self.lbl_portrait.show()
                self.btn_portrait.hide()
            else:
                self.lbl_portrait.hide()
                self.btn_portrait.show()

            idx = self.cmb_template.findData(c.template_key)
            if idx >= 0:
                self.cmb_template.setCurrentIndex(idx)
            self.txt_owner.setText(c.owner_name)
            self.chk_scale.setChecked(c.scale_with_owner)
            self.spn_owner_lvl.setValue(max(1, min(20, c.owner_level)))
            self.spn_owner_pb.setValue(max(2, min(6, c.owner_proficiency)))
            self.spn_owner_mod.setValue(max(-2, min(10, c.owner_ability_mod)))

            self.txt_name.setText(c.name)
            self.txt_type.setText(c.companion_type)
            self.txt_creature_type.setText(c.creature_type)
            self.txt_size.setText(c.size)
            self.txt_cr.setText(c.cr)
            self.txt_speed.setText(c.speed)
            self.txt_hit_dice.setText(c.hit_dice)
            self.spn_ac.setValue(max(1, min(30, c.ac)))
            self.spn_max_hp.setValue(max(1, min(999, c.max_hp)))
            self.spn_cur_hp.setValue(max(0, min(999, c.current_hp)))
            self.spn_tmp_hp.setValue(max(0, min(999, c.temp_hp)))
            self.spn_ac.setEnabled(not c.scale_with_owner or c.template_key == "custom")
            self.spn_max_hp.setEnabled(not c.scale_with_owner or c.template_key == "custom")

            for ab in ABILITIES:
                self.ab_spins[ab].setValue(c.abilities.get(ab, 10))
                self.save_checks[ab].setChecked(ab in c.saving_throw_profs)

            self.txt_skills.setText(", ".join(c.skill_profs))
            self.txt_senses.setText(c.senses)
            self.txt_languages.setText(c.languages)
            self.txt_dmg_imm.setText(c.damage_immunities)
            self.txt_cond_imm.setText(c.condition_immunities)
            if self.txt_notes.toPlainText() != c.notes:
                self.txt_notes.setPlainText(c.notes)

            self.tbl_traits.setRowCount(len(c.traits))
            for r, tr in enumerate(c.traits):
                self.tbl_traits.setItem(r, 0, QTableWidgetItem(tr.name))
                self.tbl_traits.setItem(r, 1, QTableWidgetItem(tr.description))

            self.tbl_actions.setRowCount(len(c.actions))
            for r, act in enumerate(c.actions):
                self.tbl_actions.setItem(r, 0, QTableWidgetItem(act.name))
                self.tbl_actions.setItem(r, 1, QTableWidgetItem(act.attack_bonus))
                self.tbl_actions.setItem(r, 2, QTableWidgetItem(act.damage))
                self.tbl_actions.setItem(r, 3, QTableWidgetItem(act.description))

            self.sheet_browser.setHtml(render_companion_sheet_html(c, for_pdf=False))
        finally:
            self._updating = False

    def _on_meta_changed(self) -> None:
        if self._updating:
            return
        c = self.comp
        c.name = self.txt_name.text().strip() or "New Companion"
        c.companion_type = self.txt_type.text().strip() or "Companion"
        c.creature_type = self.txt_creature_type.text().strip() or "Beast"
        c.size = self.txt_size.text().strip() or "Medium"
        c.cr = self.txt_cr.text().strip() or "1/4"
        c.speed = self.txt_speed.text().strip() or "30 ft."
        c.hit_dice = self.txt_hit_dice.text().strip() or "1d8"
        c.owner_name = self.txt_owner.text().strip()
        c.scale_with_owner = self.chk_scale.isChecked()
        c.owner_level = self.spn_owner_lvl.value()
        c.owner_proficiency = self.spn_owner_pb.value()
        c.owner_ability_mod = self.spn_owner_mod.value()
        c.ac = self.spn_ac.value()
        c.max_hp = self.spn_max_hp.value()
        c.current_hp = self.spn_cur_hp.value()
        c.temp_hp = self.spn_tmp_hp.value()
        for ab in ABILITIES:
            c.abilities[ab] = self.ab_spins[ab].value()
        c.saving_throw_profs = [ab for ab in ABILITIES if self.save_checks[ab].isChecked()]
        valid_skills = {s.lower(): s for s, _ in SKILLS}
        c.skill_profs = [
            valid_skills.get(tok.strip().lower(), tok.strip())
            for tok in self.txt_skills.text().split(",")
            if tok.strip()
        ]
        c.senses = self.txt_senses.text().strip()
        c.languages = self.txt_languages.text().strip()
        c.damage_immunities = self.txt_dmg_imm.text().strip()
        c.condition_immunities = self.txt_cond_imm.text().strip()
        c.notes = self.txt_notes.toPlainText()
        self._dirty = True
        self._sync_ui()

    def _on_traits_actions_edited(self) -> None:
        if self._updating:
            return
        self.comp.traits = [
            CompanionTrait(
                (self.tbl_traits.item(r, 0).text() if self.tbl_traits.item(r, 0) else "").strip(),
                (self.tbl_traits.item(r, 1).text() if self.tbl_traits.item(r, 1) else "").strip(),
            )
            for r in range(self.tbl_traits.rowCount())
        ]
        self.comp.actions = [
            CompanionAction(
                (self.tbl_actions.item(r, 0).text() if self.tbl_actions.item(r, 0) else "").strip(),
                (self.tbl_actions.item(r, 1).text() if self.tbl_actions.item(r, 1) else "").strip(),
                (self.tbl_actions.item(r, 2).text() if self.tbl_actions.item(r, 2) else "").strip(),
                (self.tbl_actions.item(r, 3).text() if self.tbl_actions.item(r, 3) else "").strip(),
            )
            for r in range(self.tbl_actions.rowCount())
        ]
        self._dirty = True
        self.sheet_browser.setHtml(render_companion_sheet_html(self.comp, for_pdf=False))

    def _add_trait_row(self) -> None:
        self.comp.traits.append(CompanionTrait("New Trait", "Description…"))
        self._dirty = True
        self._sync_ui()

    def _remove_trait_row(self) -> None:
        r = self.tbl_traits.currentRow()
        if 0 <= r < len(self.comp.traits):
            self.comp.traits.pop(r)
            self._dirty = True
            self._sync_ui()

    def _add_action_row(self) -> None:
        self.comp.actions.append(CompanionAction("New Action", "+4", "1d6+2", "Melee Weapon Attack."))
        self._dirty = True
        self._sync_ui()

    def _remove_action_row(self) -> None:
        r = self.tbl_actions.currentRow()
        if 0 <= r < len(self.comp.actions):
            self.comp.actions.pop(r)
            self._dirty = True
            self._sync_ui()

    def _apply_template(self) -> None:
        key = self.cmb_template.currentData() or "custom"
        fresh = create_companion_from_template(key)
        fresh.owner_name = self.comp.owner_name
        fresh.owner_level = self.comp.owner_level
        fresh.owner_proficiency = self.comp.owner_proficiency
        fresh.owner_ability_mod = self.comp.owner_ability_mod
        fresh.portrait_path = self.comp.portrait_path
        fresh.portrait_base64 = self.comp.portrait_base64
        self.comp = fresh
        self._dirty = True
        self._sync_ui()

    def _pick_portrait(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Companion Portrait",
            str(get_os_downloads_dir()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if not path:
            return
        self.comp.portrait_path = path
        self.comp.portrait_base64 = encode_portrait_file(Path(path))
        self._dirty = True
        self._sync_ui()

    def save_companion(self) -> bool:
        if self.current_file is None:
            return self.save_companion_as()
        save_dndcomp(self.comp, self.current_file)
        self.comp.file_path = str(self.current_file)
        self._dirty = False
        self.saved.emit(self.current_file)
        return True

    def save_companion_as(self) -> bool:
        base_dir = get_os_downloads_dir()
        slug = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in (self.comp.name or "companion").lower()).strip("_") or "companion"
        default_path = str(base_dir / f"{slug}.dndcomp")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Companion (.dndcomp)", default_path, "Aurora Companion (*.dndcomp)"
        )
        if not path:
            return False
        if not path.lower().endswith(".dndcomp"):
            path += ".dndcomp"
        self.current_file = Path(path)
        return self.save_companion()

    def export_pdf_dialog(self) -> None:
        slug = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in (self.comp.name or "companion")).strip("._") or "companion"
        default_path = str(get_os_downloads_dir() / f"{slug}.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Companion Sheet PDF", default_path, "PDF Files (*.pdf)"
        )
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            export_companion_pdf(self.comp, Path(path))

    def _delete_current(self) -> None:
        if self.current_file is None or not self.current_file.is_file():
            self.back_requested.emit()
            return
        reply = QMessageBox.question(
            self, "Delete Companion", f"Delete {self.current_file.name}?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            p = self.current_file
            p.unlink(missing_ok=True)
            self.current_file = None
            self._dirty = False
            self.deleted.emit(p)
            self.back_requested.emit()
