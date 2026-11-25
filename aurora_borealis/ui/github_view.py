"""GitHub & 5e.tools Additional Content Manager view (.index / .xml / 5e.tools JSON)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..fivetools_importer import import_5etools_directory, import_5etools_from_github
from ..github_importer import (
    IndexRecord,
    install_from_url,
    install_official_aurora_content,
    remove_index,
    update_index,
)
from ..paths import get_os_downloads_dir
from .icons import apply_button_icon


class GitHubWorker(QThread):
    """Runs GitHub .index / .xml and 5e.tools downloads off the UI thread."""

    log_line = Signal(str)
    finished_records = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        mode: str,
        custom_root: Path,
        url: str = "",
        local_dir: Optional[Path] = None,
        records: Optional[list[IndexRecord]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode  # "single", "official", "update_all", "5etools_github", "5etools_local"
        self.custom_root = Path(custom_root)
        self.url = url
        self.local_dir = local_dir
        self.records = records or []

    def run(self) -> None:
        try:
            out: list[IndexRecord] = []
            if self.mode == "single":
                rec = install_from_url(
                    self.url,
                    self.custom_root,
                    progress_cb=self.log_line.emit,
                    exclude_third_party=True,
                )
                out.append(rec)
            elif self.mode == "official":
                out = install_official_aurora_content(
                    self.custom_root,
                    progress_cb=self.log_line.emit,
                )
            elif self.mode == "update_all":
                for r in self.records:
                    if r.slug == "5etools":
                        continue
                    updated = update_index(
                        r,
                        self.custom_root,
                        progress_cb=self.log_line.emit,
                        exclude_third_party=True,
                    )
                    out.append(updated)
            elif self.mode == "5etools_github":
                out.append(
                    import_5etools_from_github(
                        self.custom_root,
                        progress_cb=self.log_line.emit,
                    )
                )
            elif self.mode == "5etools_local" and self.local_dir is not None:
                out.append(
                    import_5etools_directory(
                        self.local_dir,
                        self.custom_root,
                        progress_cb=self.log_line.emit,
                    )
                )
            self.finished_records.emit(out)
        except Exception as exc:
            self.failed.emit(str(exc))


class GitHubContentView(QWidget):
    """Screen 2: GitHub .index / .xml & 5e.tools manager + duplicate inspector."""

    back_requested = Signal()
    import_local_folder_requested = Signal()
    show_duplicates_requested = Signal()
    content_changed = Signal(list)  # list[dict] installed_indexes

    def __init__(self, custom_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.custom_root = Path(custom_root)
        self._records: list[IndexRecord] = []
        self._worker: Optional[GitHubWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top Bar
        top_bar = QFrame()
        top_bar.setObjectName("TopNavBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 12, 18, 12)

        btn_back = QPushButton("Back")
        apply_button_icon(btn_back, "arrow-left", size=15)
        btn_back.clicked.connect(self.back_requested.emit)
        title_col = QVBoxLayout()
        lbl_t = QLabel("Additional Content — GitHub & 5e.tools Manager")
        lbl_t.setObjectName("TitleText")
        lbl_sub = QLabel(
            "Imports Aurora Legacy (.index/.xml, excluding 3rd-party) and 5e.tools JSON datasets."
        )
        lbl_sub.setObjectName("MutedText")
        title_col.addWidget(lbl_t)
        title_col.addWidget(lbl_sub)

        self.btn_dups = QPushButton("Duplicates (0)")
        self.btn_dups.clicked.connect(self.show_duplicates_requested.emit)

        btn_local = QPushButton("Import Local XML Folder")
        btn_local.clicked.connect(self.import_local_folder_requested.emit)

        self.btn_official = QPushButton("Sync Official Aurora Legacy")
        self.btn_official.clicked.connect(self.start_official_sync)

        self.btn_update_all = QPushButton("Check All for Updates")
        self.btn_update_all.setObjectName("PrimaryBtn")
        apply_button_icon(self.btn_update_all, "refresh", size=15)
        self.btn_update_all.clicked.connect(self.start_update_all)

        top_layout.addWidget(btn_back)
        top_layout.addLayout(title_col, 1)
        top_layout.addWidget(self.btn_dups)
        top_layout.addWidget(btn_local)
        top_layout.addWidget(self.btn_official)
        top_layout.addWidget(self.btn_update_all)
        root.addWidget(top_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(12)

        # Aurora GitHub URL Fetch Box
        fetch_card = QFrame()
        fetch_card.setObjectName("SidebarCard")
        fc_layout = QVBoxLayout(fetch_card)
        fc_layout.setContentsMargins(14, 12, 14, 12)
        fc_layout.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<b>Add Aurora GitHub .index or .xml URL</b>"))
        hdr.addStretch()
        hint = QLabel("Auto-converts github.com/.../blob/... → raw.githubusercontent.com")
        hint.setObjectName("MutedText")
        hdr.addWidget(hint)
        fc_layout.addLayout(hdr)

        url_row = QHBoxLayout()
        self.txt_url = QLineEdit(
            "https://raw.githubusercontent.com/AuroraLegacy/elements/master/core.index"
        )
        self.btn_download = QPushButton("Download && Install")
        self.btn_download.setObjectName("PrimaryBtn")
        self.btn_download.clicked.connect(self._on_download_clicked)
        url_row.addWidget(self.txt_url, 1)
        url_row.addWidget(self.btn_download)
        fc_layout.addLayout(url_row)

        # 5e.tools Importer Row
        ft_card = QFrame()
        ft_card.setObjectName("SidebarCard")
        ft_layout = QHBoxLayout(ft_card)
        ft_layout.setContentsMargins(14, 12, 14, 12)
        ft_info = QVBoxLayout()
        ft_info.addWidget(QLabel("<b>5e.tools JSON Data Importer</b>"))
        ft_sub = QLabel(
            "Converts 5e.tools data (races, backgrounds, feats, spells, classes, items) into Aurora XML."
        )
        ft_sub.setObjectName("MutedText")
        ft_info.addWidget(ft_sub)
        ft_layout.addLayout(ft_info, 1)

        self.btn_5etools_gh = QPushButton("Download 5e.tools Data (GitHub)")
        self.btn_5etools_gh.setObjectName("PrimaryBtn")
        self.btn_5etools_gh.clicked.connect(self.start_5etools_github)
        self.btn_5etools_local = QPushButton("Import Local 5e.tools Folder")
        self.btn_5etools_local.clicked.connect(self.start_5etools_local)
        ft_layout.addWidget(self.btn_5etools_gh)
        ft_layout.addWidget(self.btn_5etools_local)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(92)
        self.txt_log.setPlainText(
            "Ready. Paste an Aurora .index/.xml URL, sync Official Aurora Legacy, or import 5e.tools JSON data."
        )
        fc_layout.addWidget(self.txt_log)
        body_layout.addWidget(fetch_card)
        body_layout.addWidget(ft_card)

        # Installed Table
        tbl_hdr = QHBoxLayout()
        tbl_hdr.addWidget(QLabel("<b>Installed Content Sources</b>"))
        tbl_hdr.addStretch()
        lbl_loc = QLabel(f"Stored in {self.custom_root}")
        lbl_loc.setObjectName("MutedText")
        tbl_hdr.addWidget(lbl_loc)
        body_layout.addLayout(tbl_hdr)

        self.tbl_indexes = QTableWidget(0, 5)
        self.tbl_indexes.setHorizontalHeaderLabels(
            ["Source Name", "URL / Path", "Version", "XML Files", "Actions"]
        )
        hdr = self.tbl_indexes.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.tbl_indexes.verticalHeader().setVisible(False)
        self.tbl_indexes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        body_layout.addWidget(self.tbl_indexes, 1)

        root.addWidget(body, 1)

    def set_duplicate_count(self, count: int) -> None:
        self.btn_dups.setText(f"Duplicates ({count})")

    def set_installed_indexes(self, raw_list: list[dict]) -> None:
        self._records = []
        for item in raw_list:
            try:
                self._records.append(
                    IndexRecord(
                        slug=str(item.get("slug", "")),
                        name=str(item.get("name", "")),
                        url=str(item.get("url", "")),
                        version=str(item.get("version", "1.0")),
                        author=str(item.get("author", "")),
                        description=str(item.get("description", "")),
                        local_dir=str(item.get("local_dir", "")),
                        file_count=int(item.get("file_count", 0)),
                        updated_at=str(item.get("updated_at", "")),
                    )
                )
            except Exception:
                continue
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.tbl_indexes.setRowCount(len(self._records))
        max_action_w = 150
        for r, rec in enumerate(self._records):
            self.tbl_indexes.setItem(r, 0, QTableWidgetItem(rec.name))
            self.tbl_indexes.setItem(r, 1, QTableWidgetItem(rec.url))
            self.tbl_indexes.setItem(r, 2, QTableWidgetItem(rec.version))
            self.tbl_indexes.setItem(r, 3, QTableWidgetItem(f"{rec.file_count} files"))

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(6, 4, 6, 4)
            al.setSpacing(6)
            btn_upd = QPushButton("Update")
            btn_upd.clicked.connect(lambda _=False, idx=r: self._update_single(idx))
            btn_rem = QPushButton("Remove")
            btn_rem.setObjectName("DangerBtn")
            btn_rem.clicked.connect(lambda _=False, idx=r: self._remove_single(idx))
            al.addWidget(btn_upd)
            al.addWidget(btn_rem)
            actions.adjustSize()
            hint = actions.sizeHint()
            max_action_w = max(max_action_w, hint.width() + 12)
            self.tbl_indexes.setRowHeight(r, max(42, hint.height() + 6))
            self.tbl_indexes.setCellWidget(r, 4, actions)
        self.tbl_indexes.setColumnWidth(4, max_action_w)

    def _set_busy(self, busy: bool) -> None:
        for btn in (
            self.btn_download,
            self.btn_official,
            self.btn_update_all,
            self.btn_5etools_gh,
            self.btn_5etools_local,
        ):
            btn.setEnabled(not busy)

    def append_log(self, msg: str) -> None:
        self.txt_log.appendPlainText(msg)

    def _on_download_clicked(self) -> None:
        url = self.txt_url.text().strip()
        if url:
            self._run_worker("single", url=url)

    def start_official_sync(self) -> None:
        self._run_worker("official")

    def start_update_all(self) -> None:
        if not self._records:
            self.append_log("No installed GitHub indexes to update.")
            return
        self._run_worker("update_all", records=list(self._records))

    def start_5etools_github(self) -> None:
        self._run_worker("5etools_github")

    def start_5etools_local(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select 5e.tools data/ Folder", str(get_os_downloads_dir())
        )
        if folder:
            self._run_worker("5etools_local", local_dir=Path(folder))

    def _update_single(self, row: int) -> None:
        if 0 <= row < len(self._records):
            rec = self._records[row]
            if rec.slug == "5etools":
                if Path(rec.url).is_dir():
                    self._run_worker("5etools_local", local_dir=Path(rec.url))
                else:
                    self._run_worker("5etools_github")
            else:
                self._run_worker("single", url=rec.url)

    def _remove_single(self, row: int) -> None:
        if 0 <= row < len(self._records):
            rec = self._records.pop(row)
            remove_index(rec)
            self._refresh_table()
            self.append_log(f"Removed '{rec.name}'")
            self.content_changed.emit([asdict(r) for r in self._records])

    def _run_worker(
        self,
        mode: str,
        url: str = "",
        local_dir: Optional[Path] = None,
        records: Optional[list[IndexRecord]] = None,
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._set_busy(True)
        self.txt_log.clear()
        self._worker = GitHubWorker(
            mode=mode,
            custom_root=self.custom_root,
            url=url,
            local_dir=local_dir,
            records=records,
            parent=self,
        )
        self._worker.log_line.connect(self.append_log)
        self._worker.finished_records.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def _on_worker_finished(self, new_records: list) -> None:
        self._set_busy(False)
        by_key = {r.slug or r.url: r for r in self._records}
        for rec in new_records:
            by_key[rec.slug or rec.url] = rec
        self._records = list(by_key.values())
        self._refresh_table()
        self.content_changed.emit([asdict(r) for r in self._records])

    def _on_worker_failed(self, err: str) -> None:
        self._set_busy(False)
        self.append_log(f"ERROR: {err}")
        QMessageBox.warning(self, "Content Sync Failed", f"Could not fetch content:\n{err}")
