"""Level 1-20 Build Planner Dialog (3.6)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..loader import ContentRepository
from ..models import CharacterState, ComputedCharacter
from ..planner import generate_default_plan, summarize_build_plan
from .ui_helpers import ensure_widgets_fit


class BuildPlannerDialog(QDialog):
    """Dialog for Level 1-20 character progression planning."""

    def __init__(
        self,
        state: CharacterState,
        computed: ComputedCharacter,
        repo: ContentRepository,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.computed = computed
        self.repo = repo
        self._plan: list[dict] = generate_default_plan(state, repo)
        self._populating = False

        self.setWindowTitle("Build Planner (Lv 1–20)")
        self.setMinimumSize(920, 600)
        self._build_ui()
        self._populate_plan_table()
        self._refresh_plan_summary()
        ensure_widgets_fit(self)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.lbl_plan_summary = QLabel("Projected Lv 20: —")
        self.lbl_plan_summary.setObjectName("AccentText")
        self.lbl_plan_summary.setWordWrap(True)
        btn_sync = QPushButton("Sync from Character")
        btn_sync.clicked.connect(self._sync_from_character)
        btn_autofill = QPushButton("Fill Remaining with Primary")
        btn_autofill.clicked.connect(self._autofill_remaining)
        top_row.addWidget(self.lbl_plan_summary, 1)
        top_row.addWidget(btn_sync)
        top_row.addWidget(btn_autofill)
        root.addLayout(top_row)

        self.tbl_plan = QTableWidget(20, 5)
        self.tbl_plan.setHorizontalHeaderLabels(["Lvl", "Class", "Subclass", "ASI / Feat", "Notes / Key Spells"])
        hdr = self.tbl_plan.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_plan.setColumnWidth(0, 44)
        self.tbl_plan.setColumnWidth(1, 170)
        self.tbl_plan.setColumnWidth(2, 190)
        self.tbl_plan.verticalHeader().setVisible(False)
        self.tbl_plan.itemChanged.connect(self._on_plan_item_changed)
        root.addWidget(self.tbl_plan, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save Plan")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _populate_plan_table(self) -> None:
        self._populating = True
        classes = self.state.normalized_classes()
        all_classes = self.repo.of_type("Class")
        subclasses = self.repo.of_type("Archetype")
        row_h = 40
        col1_w = 170
        col2_w = 190
        try:
            for r in range(20):
                entry = self._plan[r]
                lvl = r + 1
                lvl_it = QTableWidgetItem(str(lvl))
                lvl_it.setFlags(lvl_it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                lvl_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_plan.setItem(r, 0, lvl_it)

                cmb_cls = QComboBox()
                cmb_cls.addItem("—", "")
                for cel in all_classes:
                    cmb_cls.addItem(cel.name, cel.id)
                cur_cid = str(entry.get("class_id") or "")
                if cur_cid:
                    idx = cmb_cls.findData(cur_cid)
                    if idx >= 0:
                        cmb_cls.setCurrentIndex(idx)
                elif classes and lvl == 1:
                    idx = cmb_cls.findData(classes[0].class_id)
                    if idx >= 0:
                        cmb_cls.setCurrentIndex(idx)
                cmb_cls.currentIndexChanged.connect(
                    lambda _i, row=r, c=cmb_cls: self._on_class_combo(row, c)
                )
                row_h = max(row_h, cmb_cls.sizeHint().height() + 6)
                col1_w = max(col1_w, min(260, cmb_cls.sizeHint().width() + 12))
                self.tbl_plan.setCellWidget(r, 1, cmb_cls)

                cmb_sub = QComboBox()
                cmb_sub.addItem("—", "")
                for sel in subclasses:
                    cmb_sub.addItem(sel.name, sel.id)
                cur_sid = str(entry.get("subclass_id") or "")
                if cur_sid:
                    idx = cmb_sub.findData(cur_sid)
                    if idx >= 0:
                        cmb_sub.setCurrentIndex(idx)
                cmb_sub.currentIndexChanged.connect(
                    lambda _i, row=r, c=cmb_sub: self._on_subclass_combo(row, c)
                )
                row_h = max(row_h, cmb_sub.sizeHint().height() + 6)
                col2_w = max(col2_w, min(280, cmb_sub.sizeHint().width() + 12))
                self.tbl_plan.setCellWidget(r, 2, cmb_sub)

                self.tbl_plan.setItem(r, 3, QTableWidgetItem(str(entry.get("asi_or_feat") or "")))
                self.tbl_plan.setItem(r, 4, QTableWidgetItem(str(entry.get("notes") or "")))

            vh = self.tbl_plan.verticalHeader()
            vh.setMinimumSectionSize(row_h)
            vh.setDefaultSectionSize(row_h)
            for r in range(20):
                self.tbl_plan.setRowHeight(r, row_h)
            self.tbl_plan.setColumnWidth(1, col1_w)
            self.tbl_plan.setColumnWidth(2, col2_w)
        finally:
            self._populating = False

    def _on_class_combo(self, row: int, cmb: QComboBox) -> None:
        if self._populating:
            return
        self._plan[row]["class_id"] = cmb.currentData() or ""
        self._refresh_plan_summary()

    def _on_subclass_combo(self, row: int, cmb: QComboBox) -> None:
        if self._populating:
            return
        self._plan[row]["subclass_id"] = cmb.currentData() or ""

    def _on_plan_item_changed(self, item: QTableWidgetItem) -> None:
        if self._populating:
            return
        r = item.row()
        c = item.column()
        if c == 3:
            self._plan[r]["asi_or_feat"] = item.text().strip()
            self._refresh_plan_summary()
        elif c == 4:
            self._plan[r]["notes"] = item.text().strip()

    def _refresh_plan_summary(self) -> None:
        info = summarize_build_plan(self._plan, self.repo)
        slots_txt = ", ".join(f"L{k}:{v}" for k, v in sorted(info["projected_slots"].items())) or "None"
        self.lbl_plan_summary.setText(
            f"Projected Lv 20 Split: {info['class_split']}  •  Caster Lv: {info['caster_level']}  •  "
            f"ASI/Feats: {len(info['asi_levels'])}  •  Slots: {slots_txt}"
        )

    def _sync_from_character(self) -> None:
        temp = CharacterState(
            class_id=self.state.class_id,
            classes=list(self.state.classes),
            level=self.state.level,
            level_order=list(self.state.level_order),
            selections=dict(self.state.selections),
            level_up_asi=dict(self.state.level_up_asi),
            level_up_feats=dict(self.state.level_up_feats),
        )
        self._plan = generate_default_plan(temp, self.repo)
        self._populate_plan_table()
        self._refresh_plan_summary()

    def _autofill_remaining(self) -> None:
        primary_cid = ""
        for entry in self._plan:
            if entry.get("class_id"):
                primary_cid = str(entry["class_id"])
                break
        if not primary_cid:
            primary_cid = self.state.class_id
        if not primary_cid:
            return
        for entry in self._plan:
            if not entry.get("class_id"):
                entry["class_id"] = primary_cid
        self._populate_plan_table()
        self._refresh_plan_summary()

    def build_plan(self) -> list[dict]:
        return [dict(e) for e in self._plan]
