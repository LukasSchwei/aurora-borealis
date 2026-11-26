"""Details, Portrait, Appearance & Notes tab mixin."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...paths import get_os_downloads_dir
from ...persistence import encode_portrait_file
from ..dialogs import pixmap_from_portrait


class NotesTabMixin:
    def _build_tab_notes(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        details_box = QGroupBox("Character Details, Alignment, Deity && Portrait")
        outer_details = QHBoxLayout(details_box)

        port_col = QVBoxLayout()
        self.lbl_notes_portrait = QLabel("No Image")
        self.lbl_notes_portrait.setObjectName("PortraitFrame")
        self.lbl_notes_portrait.setFixedSize(110, 110)
        self.lbl_notes_portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_choose_p = QPushButton("Choose Portrait")
        btn_choose_p.clicked.connect(self._pick_character_portrait)
        btn_clear_p = QPushButton("Clear Portrait")
        btn_clear_p.clicked.connect(self._clear_character_portrait)
        port_col.addWidget(self.lbl_notes_portrait)
        port_col.addWidget(btn_choose_p)
        port_col.addWidget(btn_clear_p)
        port_col.addStretch()
        outer_details.addLayout(port_col)

        form = QGridLayout()
        self.txt_name = QLineEdit()
        self.txt_player = QLineEdit()
        self.cmb_align = QComboBox()
        self.cmb_deity = QComboBox()
        self._populate_element_combo(self.cmb_align, "Alignment", allow_none=True)
        self._populate_element_combo(self.cmb_deity, "Deity", allow_none=True)
        self.cmb_align.currentIndexChanged.connect(self._on_align_deity_changed)
        self.cmb_deity.currentIndexChanged.connect(self._on_align_deity_changed)

        self.txt_gender = QLineEdit()
        self.txt_faith = QLineEdit()
        self.txt_age = QLineEdit()
        self.txt_height = QLineEdit()
        self.txt_weight = QLineEdit()
        self.txt_eyes = QLineEdit()
        self.txt_skin = QLineEdit()
        self.txt_hair = QLineEdit()

        fields = [
            ("Character Name:", self.txt_name, 0, 0),
            ("Player Name:", self.txt_player, 0, 2),
            ("Alignment:", self.cmb_align, 1, 0),
            ("Deity:", self.cmb_deity, 1, 2),
            ("Gender:", self.txt_gender, 2, 0),
            ("Faith:", self.txt_faith, 2, 2),
            ("Age:", self.txt_age, 3, 0),
            ("Height:", self.txt_height, 3, 2),
            ("Weight:", self.txt_weight, 4, 0),
            ("Eyes:", self.txt_eyes, 4, 2),
            ("Skin:", self.txt_skin, 5, 0),
            ("Hair:", self.txt_hair, 5, 2),
        ]
        for label, widget, r, c in fields:
            form.addWidget(QLabel(label), r, c)
            form.addWidget(widget, r, c + 1)
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._on_notes_changed)

        outer_details.addLayout(form, 1)
        layout.addWidget(details_box)

        bg_box = QGroupBox("Backstory")
        bg_l = QVBoxLayout(bg_box)
        self.txt_backstory = QPlainTextEdit()
        self.txt_backstory.textChanged.connect(self._on_notes_changed)
        bg_l.addWidget(self.txt_backstory)
        layout.addWidget(bg_box, 1)

        notes_box = QGroupBox("Session Notes")
        n_l = QVBoxLayout(notes_box)
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.textChanged.connect(self._on_notes_changed)
        n_l.addWidget(self.txt_notes)
        layout.addWidget(notes_box, 1)
        return tab

    def _sync_notes_tab(self) -> None:
        pix = pixmap_from_portrait(self.state.portrait_base64, self.state.portrait_path, size=110)
        if pix:
            self.lbl_notes_portrait.setPixmap(pix)
        else:
            self.lbl_notes_portrait.clear()
            self.lbl_notes_portrait.setText("No Image")

        self._set_combo_by_data(self.cmb_align, self.state.alignment_id)
        self._set_combo_by_data(self.cmb_deity, self.state.deity_id)
        self.txt_name.setText(self.state.name)
        self.txt_player.setText(self.state.player_name)
        self.txt_gender.setText(self.state.gender)
        self.txt_faith.setText(self.state.faith)
        self.txt_age.setText(self.state.age)
        self.txt_height.setText(self.state.height)
        self.txt_weight.setText(self.state.weight)
        self.txt_eyes.setText(self.state.eyes)
        self.txt_skin.setText(self.state.skin)
        self.txt_hair.setText(self.state.hair)
        if self.txt_backstory.toPlainText() != self.state.backstory:
            self.txt_backstory.setPlainText(self.state.backstory)
        if self.txt_notes.toPlainText() != self.state.notes:
            self.txt_notes.setPlainText(self.state.notes)

    def _on_align_deity_changed(self) -> None:
        if self._updating:
            return
        self.state.alignment_id = self.cmb_align.currentData() or ""
        self.state.deity_id = self.cmb_deity.currentData() or ""
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _on_notes_changed(self) -> None:
        if self._updating:
            return
        self.state.name = self.txt_name.text()
        self.state.player_name = self.txt_player.text()
        self.state.gender = self.txt_gender.text()
        self.state.faith = self.txt_faith.text()
        self.state.age = self.txt_age.text()
        self.state.height = self.txt_height.text()
        self.state.weight = self.txt_weight.text()
        self.state.eyes = self.txt_eyes.text()
        self.state.skin = self.txt_skin.text()
        self.state.hair = self.txt_hair.text()
        self.state.backstory = self.txt_backstory.toPlainText()
        self.state.notes = self.txt_notes.toPlainText()
        self.lbl_char_name.setText(self.state.name or "New Adventurer")
        self.lbl_top_name.setText(self.state.name or "New Adventurer")
        self.title_bar.set_breadcrumb(self.state.name or "New Adventurer")
        self._updating = True
        try:
            self.txt_overview_name.setText(self.state.name)
        finally:
            self._updating = False
        self._mark_dirty()

    def _pick_character_portrait(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Character Portrait",
            str(get_os_downloads_dir()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if not path:
            return
        self.state.portrait_path = path
        self.state.portrait_base64 = encode_portrait_file(Path(path))
        self._mark_dirty()
        self._recalculate_and_refresh()

    def _clear_character_portrait(self) -> None:
        self.state.portrait_path = ""
        self.state.portrait_base64 = ""
        self._mark_dirty()
        self._recalculate_and_refresh()
