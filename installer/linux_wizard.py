"""Aurora Borealis Linux Setup Wizard (Install / Repair / Uninstall).

Runs in three progressive tiers so it works on any Linux desktop or terminal:
1. PySide6 GUI Wizard (dark themed, 4-step wizard)
2. Tkinter GUI Wizard (Python stdlib fallback before PySide6 is installed)
3. Interactive Terminal CLI fallback (when no display server is available)
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional


def default_linux_install_dir(home: Optional[Path] = None) -> Path:
    """Return the standard XDG application directory for Aurora Borealis."""
    base_home = Path(home) if home is not None else Path.home()
    if home is None and os.environ.get("XDG_DATA_HOME"):
        data_home = Path(os.environ["XDG_DATA_HOME"])
    else:
        data_home = base_home / ".local" / "share"
    return data_home / "aurora-borealis" / "app"


def detect_linux_installation(home: Optional[Path] = None) -> dict[str, object]:
    """Inspect standard Linux install paths and return status metadata."""
    base_home = Path(home) if home is not None else Path.home()
    if home is None and os.environ.get("XDG_DATA_HOME"):
        data_home = Path(os.environ["XDG_DATA_HOME"])
    else:
        data_home = base_home / ".local" / "share"
    if home is None and os.environ.get("XDG_CONFIG_HOME"):
        config_home = Path(os.environ["XDG_CONFIG_HOME"])
    else:
        config_home = base_home / ".config"

    app_dir = data_home / "aurora-borealis" / "app"
    has_app = (app_dir / "aurora_borealis").is_dir()
    has_venv = (app_dir / ".venv" / "bin" / "python").is_file()
    has_launcher = (base_home / ".local" / "bin" / "aurora-borealis").is_file()
    has_desktop = (data_home / "applications" / "aurora-borealis.desktop").is_file()
    has_config = (config_home / "aurora-borealis").is_dir() or (data_home / "aurora-borealis").is_dir()
    installed = has_app or has_launcher or has_desktop

    if installed:
        parts = []
        if has_app:
            parts.append(f"app in {app_dir}")
        if has_venv:
            parts.append("Python .venv ready")
        if has_launcher:
            parts.append("CLI launcher")
        if has_desktop:
            parts.append("desktop entry")
        summary = f"Installed ({', '.join(parts)})"
    else:
        summary = "Not currently installed"

    return {
        "installed": installed,
        "install_dir": str(app_dir),
        "has_app": has_app,
        "has_venv": has_venv,
        "has_launcher": has_launcher,
        "has_desktop": has_desktop,
        "has_config": has_config,
        "summary": summary,
    }


def build_install_command(
    script_dir: Path,
    prefix: str,
    in_place: bool,
    install_system_deps: bool,
    install_desktop: bool,
    assume_yes: bool = True,
    install_aurora_legacy: bool = False,
    install_5etools: bool = False,
) -> list[str]:
    """Build the bash command list to run install-linux.sh."""
    cmd = ["bash", str(Path(script_dir) / "install-linux.sh")]
    if in_place:
        cmd.append("--in-place")
    elif prefix.strip():
        cmd.extend(["--prefix", prefix.strip()])
    if not install_system_deps:
        cmd.append("--no-system-deps")
    if not install_desktop:
        cmd.append("--no-desktop")
    if install_aurora_legacy:
        cmd.append("--install-aurora-legacy")
    if install_5etools:
        cmd.append("--install-5etools")
    if assume_yes:
        cmd.append("--yes")
    return cmd


def build_uninstall_command(
    script_dir: Path,
    prefix: str,
    purge_config: bool,
) -> list[str]:
    """Build the bash command list to run uninstall-linux.sh."""
    cmd = ["bash", str(Path(script_dir) / "uninstall-linux.sh")]
    if prefix.strip():
        cmd.extend(["--prefix", prefix.strip()])
    if purge_config:
        cmd.append("--purge-config")
    return cmd


_QT_WIZARD_STYLESHEET = """
QDialog, QWidget {
    background-color: #0e0f11;
    color: #eef0f3;
    font-family: "Inter", "Noto Sans", "Segoe UI", sans-serif;
    font-size: 10.5pt;
}
QFrame#BannerCard, QGroupBox {
    background-color: #18191d;
    border: 1px solid #2c2f36;
    border-radius: 12px;
}
QGroupBox {
    margin-top: 12px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #9aa0a6;
}
QPushButton {
    background-color: #24262c;
    color: #eef0f3;
    border: 1px solid #2c2f36;
    border-radius: 14px;
    padding: 7px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2e3139;
}
QPushButton#PrimaryBtn {
    background-color: #34d399;
    border-color: #34d399;
    color: #0e0f11;
}
QPushButton#PrimaryBtn:hover {
    background-color: #6ee7b7;
}
QPushButton#DangerBtn {
    background-color: #2a1618;
    border-color: #6b2228;
    color: #fca5a5;
}
QPushButton#StepPill {
    border-radius: 12px;
    padding: 5px 12px;
    color: #9aa0a6;
    background: transparent;
}
QPushButton#StepPill[active="true"] {
    background-color: #eef0f3;
    color: #111214;
}
QLineEdit, QPlainTextEdit {
    background-color: #121316;
    border: 1px solid #2c2f36;
    border-radius: 8px;
    padding: 6px 10px;
    color: #eef0f3;
}
QProgressBar {
    background-color: #18191d;
    border: 1px solid #2c2f36;
    border-radius: 7px;
    height: 16px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #34d399;
    border-radius: 6px;
}
"""


def build_qt_wizard_dialog(
    script_dir: Path,
    initial_action: Optional[str] = None,
    initial_prefix: Optional[str] = None,
):
    from PySide6.QtCore import QProcess, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QButtonGroup,
        QCheckBox,
        QDialog,
        QFileDialog,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QSizePolicy,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    class LinuxSetupWizardQt(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.script_dir = Path(script_dir)
            self.status_info = detect_linux_installation()
            self._action = "uninstall" if initial_action == "uninstall" else "install"
            self._process: Optional[QProcess] = None
            self._last_cmd: list[str] = []
            self._succeeded = False

            self.setWindowTitle("Aurora Borealis — Linux Setup Wizard")
            icon_path = self.script_dir / "aurora_borealis" / "assets" / "aurora-borealis.svg"
            if icon_path.is_file():
                self.setWindowIcon(QIcon(str(icon_path)))
            self.resize(800, 620)
            self.setStyleSheet(_QT_WIZARD_STYLESHEET)
            self._build_ui()
            self._ensure_buttons_fit()
            self._go_to_page(0)

        def _build_ui(self) -> None:
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(12)

            # Header + Step pills
            hdr = QFrame()
            hdr.setObjectName("BannerCard")
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(14, 10, 14, 10)
            title = QLabel("Aurora Borealis Setup Wizard (Linux)")
            title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #34d399;")
            hl.addWidget(title)
            hl.addStretch()

            self._pills: list[QPushButton] = []
            for idx, label in enumerate(("1. Action", "2. Options", "3. Progress", "4. Finish")):
                pill = QPushButton(label)
                pill.setObjectName("StepPill")
                pill.setEnabled(False)
                pill.setProperty("active", idx == 0)
                hl.addWidget(pill)
                self._pills.append(pill)
            root.addWidget(hdr)

            self.stack = QStackedWidget()
            self.stack.addWidget(self._build_page_welcome())
            self.stack.addWidget(self._build_page_options())
            self.stack.addWidget(self._build_page_progress())
            self.stack.addWidget(self._build_page_finish())
            root.addWidget(self.stack, 1)

            nav = QHBoxLayout()
            self.btn_cancel = QPushButton("Cancel")
            self.btn_cancel.clicked.connect(self.reject)
            self.btn_back = QPushButton("← Back")
            self.btn_back.clicked.connect(self._on_back)
            self.btn_next = QPushButton("Next →")
            self.btn_next.setObjectName("PrimaryBtn")
            self.btn_next.clicked.connect(self._on_next)
            self.btn_finish = QPushButton("Finish")
            self.btn_finish.setObjectName("PrimaryBtn")
            self.btn_finish.clicked.connect(self._on_finish)
            nav.addWidget(self.btn_cancel)
            nav.addStretch()
            nav.addWidget(self.btn_back)
            nav.addWidget(self.btn_next)
            nav.addWidget(self.btn_finish)
            root.addLayout(nav)

        def _build_page_welcome(self) -> QWidget:
            page = QWidget()
            vl = QVBoxLayout(page)
            vl.setSpacing(12)

            info_grp = QGroupBox("Current Installation Status")
            igl = QVBoxLayout(info_grp)
            self.lbl_status = QLabel(str(self.status_info["summary"]))
            self.lbl_status.setWordWrap(True)
            self.lbl_status.setStyleSheet("color: #7dd3fc; font-weight: 600;")
            igl.addWidget(self.lbl_status)
            vl.addWidget(info_grp)

            act_grp = QGroupBox("Choose Setup Action")
            agl = QVBoxLayout(act_grp)
            agl.setSpacing(10)
            self.act_group = QButtonGroup(self)
            self.rad_install = QRadioButton("Install / Repair Aurora Borealis")
            self.rad_uninstall = QRadioButton("Uninstall Aurora Borealis")
            self.act_group.addButton(self.rad_install)
            self.act_group.addButton(self.rad_uninstall)
            if self._action == "uninstall":
                self.rad_uninstall.setChecked(True)
            else:
                self.rad_install.setChecked(True)

            lbl_in_desc = QLabel(
                "Installs Python virtual environment (PySide6, lxml, pypdf), optional system packages (7z, qpdf), "
                "desktop menu entry, SVG icon, CLI launcher (~/.local/bin/aurora-borealis), and .dnd5e/.dnd55e/.dndcomp MIME associations."
            )
            lbl_in_desc.setWordWrap(True)
            lbl_in_desc.setStyleSheet("color: #9aa0a6; margin-left: 22px;")

            lbl_un_desc = QLabel(
                "Removes Aurora Borealis application files, virtual environment, CLI launcher, desktop shortcut, "
                "and file associations. Saved characters in ~/Documents are always kept."
            )
            lbl_un_desc.setWordWrap(True)
            lbl_un_desc.setStyleSheet("color: #9aa0a6; margin-left: 22px;")

            agl.addWidget(self.rad_install)
            agl.addWidget(lbl_in_desc)
            agl.addSpacing(6)
            agl.addWidget(self.rad_uninstall)
            agl.addWidget(lbl_un_desc)
            vl.addWidget(act_grp)
            vl.addStretch()
            return page

        def _build_page_options(self) -> QWidget:
            page = QWidget()
            vl = QVBoxLayout(page)
            self.opt_stack = QStackedWidget()

            # Install options
            in_w = QGroupBox("Installation Options")
            inl = QVBoxLayout(in_w)
            inl.setSpacing(10)
            inl.addWidget(QLabel("Target installation directory:"))
            dir_row = QHBoxLayout()
            self.txt_prefix = QLineEdit(initial_prefix or str(self.status_info["install_dir"]))
            btn_browse_in = QPushButton("Browse…")
            btn_browse_in.clicked.connect(lambda: self._pick_dir(self.txt_prefix))
            dir_row.addWidget(self.txt_prefix, 1)
            dir_row.addWidget(btn_browse_in)
            inl.addLayout(dir_row)

            self.chk_in_place = QCheckBox("Install in-place inside current folder instead of copying")
            self.chk_in_place.toggled.connect(
                lambda checked: self.txt_prefix.setEnabled(not checked)
            )
            self.chk_sys_deps = QCheckBox("Install missing system packages (python3, venv, 7z, qpdf, Qt xcb deps)")
            self.chk_sys_deps.setChecked(True)
            self.chk_desktop = QCheckBox("Install desktop shortcut, icon & .dnd5e/.dnd55e/.dndcomp file associations")
            self.chk_desktop.setChecked(True)
            inl.addWidget(self.chk_in_place)
            inl.addWidget(self.chk_sys_deps)
            inl.addWidget(self.chk_desktop)

            packs_grp = QGroupBox("D&D Content Packs (Download during Setup)")
            pgl = QVBoxLayout(packs_grp)
            pgl.setSpacing(6)
            self.chk_aurora_legacy = QCheckBox(
                "Install official Aurora Legacy content (PHB / SRD / Supplements from GitHub)"
            )
            self.chk_aurora_legacy.setChecked(True)
            self.chk_5etools = QCheckBox(
                "Install 5e.tools D&D 5e / 5.5e content (Classes, Spells, Items, Feats from GitHub)"
            )
            self.chk_5etools.setChecked(True)
            pgl.addWidget(self.chk_aurora_legacy)
            pgl.addWidget(self.chk_5etools)
            inl.addWidget(packs_grp)
            inl.addStretch()

            # Uninstall options
            un_w = QGroupBox("Uninstall Options")
            unl = QVBoxLayout(un_w)
            unl.setSpacing(10)
            unl.addWidget(QLabel("Installation directory to remove:"))
            udir_row = QHBoxLayout()
            self.txt_un_prefix = QLineEdit(initial_prefix or str(self.status_info["install_dir"]))
            btn_browse_un = QPushButton("Browse…")
            btn_browse_un.clicked.connect(lambda: self._pick_dir(self.txt_un_prefix))
            udir_row.addWidget(self.txt_un_prefix, 1)
            udir_row.addWidget(btn_browse_un)
            unl.addLayout(udir_row)

            lbl_un_warn = QLabel(
                "Removes: application files, .venv, ~/.local/bin/aurora-borealis, desktop entry, icon, and MIME package.\n"
                "Preserves: all saved characters and companions in ~/Documents."
            )
            lbl_un_warn.setWordWrap(True)
            lbl_un_warn.setStyleSheet("color: #9aa0a6;")
            unl.addWidget(lbl_un_warn)

            self.chk_purge_config = QCheckBox(
                "Also delete configuration & downloaded XML/5e.tools caches (~/.config & ~/.local/share/aurora-borealis)"
            )
            self.chk_purge_config.setChecked(False)
            unl.addWidget(self.chk_purge_config)
            unl.addStretch()

            self.opt_stack.addWidget(in_w)
            self.opt_stack.addWidget(un_w)
            vl.addWidget(self.opt_stack, 1)
            return page

        def _build_page_progress(self) -> QWidget:
            page = QWidget()
            vl = QVBoxLayout(page)
            self.lbl_prog = QLabel("Running setup task…")
            self.lbl_prog.setStyleSheet("font-weight: 600;")
            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.txt_log = QPlainTextEdit()
            self.txt_log.setReadOnly(True)
            vl.addWidget(self.lbl_prog)
            vl.addWidget(self.progress)
            vl.addWidget(self.txt_log, 1)
            return page

        def _build_page_finish(self) -> QWidget:
            page = QWidget()
            vl = QVBoxLayout(page)
            grp = QGroupBox("Setup Summary")
            gl = QVBoxLayout(grp)
            gl.setSpacing(10)
            self.lbl_finish_title = QLabel("")
            self.lbl_finish_title.setStyleSheet("font-size: 12.5pt; font-weight: 700;")
            self.lbl_finish_desc = QLabel("")
            self.lbl_finish_desc.setWordWrap(True)
            self.chk_launch = QCheckBox("Launch Aurora Borealis now")
            self.chk_launch.setChecked(True)
            gl.addWidget(self.lbl_finish_title)
            gl.addWidget(self.lbl_finish_desc)
            gl.addWidget(self.chk_launch)
            gl.addStretch()
            vl.addWidget(grp, 1)
            return page

        def _ensure_buttons_fit(self) -> None:
            for btn in self.findChildren(QPushButton):
                if btn.text().strip():
                    btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                    btn.setMinimumWidth(0)
                    btn.ensurePolished()
                    btn.setMinimumWidth(btn.sizeHint().width())

        def _pick_dir(self, target_edit: QLineEdit) -> None:
            chosen = QFileDialog.getExistingDirectory(self, "Select Installation Directory", target_edit.text())
            if chosen:
                target_edit.setText(chosen)

        def is_uninstall_selected(self) -> bool:
            return self.rad_uninstall.isChecked()

        def _go_to_page(self, idx: int) -> None:
            self.stack.setCurrentIndex(idx)
            for i, p in enumerate(self._pills):
                p.setProperty("active", i == idx)
                p.style().unpolish(p)
                p.style().polish(p)
            self.btn_back.setVisible(idx == 1)
            self.btn_next.setVisible(idx in (0, 1))
            self.btn_finish.setVisible(idx == 3)
            self.btn_cancel.setVisible(idx in (0, 1))
            if idx == 1:
                un = self.is_uninstall_selected()
                self.opt_stack.setCurrentIndex(1 if un else 0)
                self.btn_next.setText("Uninstall Now →" if un else "Install Now →")
                self.btn_next.setObjectName("DangerBtn" if un else "PrimaryBtn")
                self.btn_next.style().unpolish(self.btn_next)
                self.btn_next.style().polish(self.btn_next)
            elif idx == 0:
                self.btn_next.setText("Next →")
                self.btn_next.setObjectName("PrimaryBtn")
                self.btn_next.style().unpolish(self.btn_next)
                self.btn_next.style().polish(self.btn_next)
            self._ensure_buttons_fit()

        def _on_back(self) -> None:
            cur = self.stack.currentIndex()
            if cur == 1:
                self._go_to_page(0)

        def _on_next(self) -> None:
            cur = self.stack.currentIndex()
            if cur == 0:
                self._go_to_page(1)
            elif cur == 1:
                self._start_execution()

        def planned_command(self) -> list[str]:
            if self.is_uninstall_selected():
                return build_uninstall_command(
                    self.script_dir,
                    self.txt_un_prefix.text(),
                    self.chk_purge_config.isChecked(),
                )
            return build_install_command(
                self.script_dir,
                self.txt_prefix.text(),
                self.chk_in_place.isChecked(),
                self.chk_sys_deps.isChecked(),
                self.chk_desktop.isChecked(),
                assume_yes=True,
                install_aurora_legacy=self.chk_aurora_legacy.isChecked(),
                install_5etools=self.chk_5etools.isChecked(),
            )

        def _start_execution(self) -> None:
            self._go_to_page(2)
            self.txt_log.clear()
            self.progress.setRange(0, 0)
            un = self.is_uninstall_selected()
            if un:
                self.lbl_prog.setText("Uninstalling Aurora Borealis…")
            else:
                self.lbl_prog.setText("Installing Aurora Borealis (setting up venv, dependencies & content)…")
            cmd = self.planned_command()
            self._last_cmd = cmd
            self.txt_log.appendPlainText("$ " + shlex.join(cmd))
            proc = QProcess(self)
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            proc.readyReadStandardOutput.connect(self._on_proc_output)
            proc.finished.connect(self._on_proc_finished)
            self._process = proc
            proc.start(cmd[0], cmd[1:])

        def _on_proc_output(self) -> None:
            if self._process is None:
                return
            data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
            if data:
                self.txt_log.appendPlainText(data.rstrip())

        def _on_proc_finished(self, exit_code: int, _exit_status) -> None:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self._succeeded = exit_code == 0
            un = self.is_uninstall_selected()
            if self._succeeded:
                self.lbl_finish_title.setStyleSheet("font-size: 12.5pt; font-weight: 700; color: #34d399;")
                if un:
                    self.lbl_finish_title.setText("✓ Aurora Borealis Uninstalled")
                    self.lbl_finish_desc.setText(
                        "Application files and desktop integration were removed.\n"
                        "Your saved characters in ~/Documents remain untouched."
                    )
                    self.chk_launch.setVisible(False)
                    self.chk_launch.setChecked(False)
                else:
                    target = str(self.script_dir) if self.chk_in_place.isChecked() else self.txt_prefix.text().strip()
                    packs: list[str] = []
                    if self.chk_aurora_legacy.isChecked():
                        packs.append("Aurora Legacy")
                    if self.chk_5etools.isChecked():
                        packs.append("5e.tools")
                    pack_txt = ", ".join(packs) if packs else "On-demand in app"
                    self.lbl_finish_title.setText("✓ Aurora Borealis Installation Complete")
                    self.lbl_finish_desc.setText(
                        f"Installed in: {target}\n"
                        f"CLI command: aurora-borealis\n"
                        f"Content packs: {pack_txt}\n"
                        f"File types registered: .dnd5e, .dnd55e, .dndcomp"
                    )
                    self.chk_launch.setVisible(True)
                    self.chk_launch.setChecked(True)
            else:
                self.lbl_finish_title.setStyleSheet("font-size: 12.5pt; font-weight: 700; color: #fca5a5;")
                self.lbl_finish_title.setText(f"⚠ Setup exited with code {exit_code}")
                self.lbl_finish_desc.setText(
                    "Please check the output log or run install-linux.sh / uninstall-linux.sh in a terminal for interactive sudo prompts."
                )
                self.chk_launch.setVisible(False)
                self.chk_launch.setChecked(False)
            self._go_to_page(3)

        def _on_finish(self) -> None:
            if self._succeeded and not self.is_uninstall_selected() and self.chk_launch.isChecked():
                target = Path(str(self.script_dir) if self.chk_in_place.isChecked() else self.txt_prefix.text().strip())
                launcher = target / "aurora-borealis"
                if launcher.is_file():
                    subprocess.Popen([str(launcher)], start_new_session=True)
            self.accept()

    return LinuxSetupWizardQt()


def _launch_qt_wizard(
    script_dir: Path,
    initial_action: Optional[str],
    initial_prefix: Optional[str],
) -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    dlg = build_qt_wizard_dialog(script_dir, initial_action, initial_prefix)
    dlg.exec()
    return 0


def _launch_tk_wizard(
    script_dir: Path,
    initial_action: Optional[str],
    initial_prefix: Optional[str],
) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    status_info = detect_linux_installation()
    root = tk.Tk()
    root.title("Aurora Borealis — Linux Setup Wizard")
    root.geometry("780x580")
    root.configure(bg="#0e0f11")

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(".", background="#0e0f11", foreground="#eef0f3", fieldbackground="#18191d")
    style.configure("TLabel", background="#0e0f11", foreground="#eef0f3")
    style.configure("TRadiobutton", background="#0e0f11", foreground="#eef0f3")
    style.configure("TCheckbutton", background="#0e0f11", foreground="#eef0f3")
    style.configure("TButton", padding=6)

    action_var = tk.StringVar(value=initial_action if initial_action in ("install", "uninstall") else "install")
    prefix_var = tk.StringVar(value=initial_prefix or str(status_info["install_dir"]))
    in_place_var = tk.BooleanVar(value=False)
    sys_deps_var = tk.BooleanVar(value=True)
    desktop_var = tk.BooleanVar(value=True)
    aurora_legacy_var = tk.BooleanVar(value=True)
    fivetools_var = tk.BooleanVar(value=True)
    purge_var = tk.BooleanVar(value=False)
    launch_var = tk.BooleanVar(value=True)

    container = ttk.Frame(root, padding=16)
    container.pack(fill="both", expand=True)

    header = ttk.Label(
        container,
        text="Aurora Borealis Setup Wizard (Linux)",
        font=("Sans", 14, "bold"),
        foreground="#34d399",
    )
    header.pack(anchor="w", pady=(0, 8))

    body = ttk.Frame(container)
    body.pack(fill="both", expand=True)

    nav = ttk.Frame(container)
    nav.pack(fill="x", pady=(10, 0))

    btn_back = ttk.Button(nav, text="← Back")
    btn_next = ttk.Button(nav, text="Next →")
    btn_cancel = ttk.Button(nav, text="Cancel", command=root.destroy)
    btn_cancel.pack(side="left")
    btn_next.pack(side="right")
    btn_back.pack(side="right", padx=6)

    state = {"page": 0, "ok": False}

    def clear_body() -> None:
        for child in body.winfo_children():
            child.destroy()

    def pick_dir() -> None:
        d = filedialog.askdirectory(initialdir=prefix_var.get())
        if d:
            prefix_var.set(d)

    def show_page(idx: int) -> None:
        state["page"] = idx
        clear_body()
        if idx == 0:
            ttk.Label(body, text=f"Status: {status_info['summary']}", foreground="#7dd3fc").pack(anchor="w", pady=(0, 12))
            ttk.Radiobutton(body, text="Install / Repair Aurora Borealis", variable=action_var, value="install").pack(anchor="w", pady=4)
            ttk.Label(body, text="Creates .venv, installs PySide6/lxml/pypdf, CLI command & desktop entry.").pack(anchor="w", padx=22, pady=(0, 10))
            ttk.Radiobutton(body, text="Uninstall Aurora Borealis", variable=action_var, value="uninstall").pack(anchor="w", pady=4)
            ttk.Label(body, text="Removes app, .venv & desktop integration (keeps characters in ~/Documents).").pack(anchor="w", padx=22)
            btn_back.state(["disabled"])
            btn_next.config(text="Next →", state="normal", command=lambda: show_page(1))
        elif idx == 1:
            is_un = action_var.get() == "uninstall"
            ttk.Label(body, text="Target Directory:").pack(anchor="w")
            row = ttk.Frame(body)
            row.pack(fill="x", pady=(4, 10))
            ttk.Entry(row, textvariable=prefix_var).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse…", command=pick_dir).pack(side="left", padx=(6, 0))
            if not is_un:
                ttk.Checkbutton(body, text="Install in-place in current folder", variable=in_place_var).pack(anchor="w", pady=3)
                ttk.Checkbutton(body, text="Install missing system dependencies (apt/dnf/pacman/zypper)", variable=sys_deps_var).pack(anchor="w", pady=3)
                ttk.Checkbutton(body, text="Install desktop entry, icon & MIME associations", variable=desktop_var).pack(anchor="w", pady=3)
                ttk.Label(body, text="D&D Content Packs (Download during Setup):", foreground="#34d399").pack(anchor="w", pady=(10, 3))
                ttk.Checkbutton(body, text="Install official Aurora Legacy content (GitHub)", variable=aurora_legacy_var).pack(anchor="w", padx=14, pady=2)
                ttk.Checkbutton(body, text="Install 5e.tools D&D 5e / 5.5e content (GitHub)", variable=fivetools_var).pack(anchor="w", padx=14, pady=2)
            else:
                ttk.Label(body, text="Saved characters in ~/Documents will be preserved.").pack(anchor="w", pady=(0, 6))
                ttk.Checkbutton(body, text="Also delete config & downloaded XML caches", variable=purge_var).pack(anchor="w", pady=3)
            btn_back.state(["!disabled"])
            btn_back.config(command=lambda: show_page(0))
            btn_next.config(text=("Uninstall Now" if is_un else "Install Now"), state="normal", command=lambda: show_page(2))
        elif idx == 2:
            is_un = action_var.get() == "uninstall"
            btn_back.state(["disabled"])
            btn_next.state(["disabled"])
            ttk.Label(body, text=("Uninstalling…" if is_un else "Installing Aurora Borealis…")).pack(anchor="w", pady=(0, 6))
            pb = ttk.Progressbar(body, mode="indeterminate")
            pb.pack(fill="x", pady=(0, 8))
            pb.start(12)
            log = scrolledtext.ScrolledText(body, height=16, bg="#121316", fg="#eef0f3")
            log.pack(fill="both", expand=True)

            cmd = (
                build_uninstall_command(script_dir, prefix_var.get(), purge_var.get())
                if is_un
                else build_install_command(
                    script_dir,
                    prefix_var.get(),
                    in_place_var.get(),
                    sys_deps_var.get(),
                    desktop_var.get(),
                    assume_yes=True,
                    install_aurora_legacy=aurora_legacy_var.get(),
                    install_5etools=fivetools_var.get(),
                )
            )
            log.insert("end", "$ " + shlex.join(cmd) + "\n")

            def worker() -> None:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                assert proc.stdout is not None
                for line in proc.stdout:
                    root.after(0, lambda ln=line: (log.insert("end", ln), log.see("end")))
                rc = proc.wait()
                state["ok"] = rc == 0

                def done() -> None:
                    pb.stop()
                    show_page(3)

                root.after(0, done)

            threading.Thread(target=worker, daemon=True).start()
        elif idx == 3:
            is_un = action_var.get() == "uninstall"
            ok = state["ok"]
            msg = (
                ("✓ Uninstallation complete." if is_un else "✓ Installation complete!")
                if ok
                else "⚠ Setup failed — see log or run script in terminal."
            )
            ttk.Label(body, text=msg, font=("Sans", 12, "bold"), foreground=("#34d399" if ok else "#fca5a5")).pack(anchor="w", pady=8)
            if ok and not is_un:
                ttk.Checkbutton(body, text="Launch Aurora Borealis now", variable=launch_var).pack(anchor="w", pady=6)
            btn_back.state(["disabled"])

            def finish() -> None:
                if ok and not is_un and launch_var.get():
                    tgt = script_dir if in_place_var.get() else Path(prefix_var.get())
                    launcher = tgt / "aurora-borealis"
                    if launcher.is_file():
                        subprocess.Popen([str(launcher)], start_new_session=True)
                root.destroy()

            btn_next.config(text="Finish", state="normal", command=finish)

    show_page(0)
    root.mainloop()
    return 0


def run_cli_wizard(
    script_dir: Path,
    initial_action: Optional[str] = None,
    initial_prefix: Optional[str] = None,
    non_interactive: bool = False,
) -> int:
    """Terminal interactive Install / Uninstall wizard fallback."""
    info = detect_linux_installation()
    print("=== Aurora Borealis Linux Setup Wizard ===")
    print(f"Status: {info['summary']}")

    action = initial_action
    if not action:
        if non_interactive:
            action = "install"
        else:
            print("1) Install / Repair Aurora Borealis")
            print("2) Uninstall Aurora Borealis")
            choice = input("Choose [1/2] (default 1): ").strip()
            action = "uninstall" if choice == "2" else "install"

    prefix = initial_prefix or str(info["install_dir"])
    if action == "uninstall":
        purge = False
        if not non_interactive:
            in_p = input(f"Install folder [{prefix}]: ").strip()
            if in_p:
                prefix = in_p
            purge = input("Delete config & downloaded XML caches too? [y/N]: ").strip().lower() in ("y", "yes")
        cmd = build_uninstall_command(script_dir, prefix, purge)
    else:
        in_place = False
        sys_deps = True
        desktop = True
        aurora_legacy = True
        fivetools = True
        if not non_interactive:
            in_p = input(f"Install folder [{prefix}] (or 'in-place'): ").strip()
            if in_p == "in-place":
                in_place = True
            elif in_p:
                prefix = in_p
            sys_deps = input("Install system dependencies if missing? [Y/n]: ").strip().lower() not in ("n", "no")
            desktop = input("Install desktop shortcut & MIME associations? [Y/n]: ").strip().lower() not in ("n", "no")
            aurora_legacy = input("Install official Aurora Legacy content? [Y/n]: ").strip().lower() not in ("n", "no")
            fivetools = input("Install 5e.tools 5e/5.5e content? [Y/n]: ").strip().lower() not in ("n", "no")
        cmd = build_install_command(
            script_dir,
            prefix,
            in_place,
            sys_deps,
            desktop,
            assume_yes=non_interactive,
            install_aurora_legacy=aurora_legacy,
            install_5etools=fivetools,
        )

    print("Running:", shlex.join(cmd))
    return subprocess.run(cmd, check=False).returncode


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Aurora Borealis Linux Setup Wizard")
    parser.add_argument("--mode", choices=("install", "uninstall"), default=None)
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--cli", action="store_true", help="Force terminal wizard mode")
    parser.add_argument("--yes", action="store_true", help="Run non-interactively")
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent.parent
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    if args.cli or not has_display:
        return run_cli_wizard(script_dir, args.mode, args.prefix, non_interactive=args.yes)

    try:
        import PySide6  # noqa: F401
        return _launch_qt_wizard(script_dir, args.mode, args.prefix)
    except Exception:
        pass

    try:
        import tkinter  # noqa: F401
        return _launch_tk_wizard(script_dir, args.mode, args.prefix)
    except Exception:
        return run_cli_wizard(script_dir, args.mode, args.prefix, non_interactive=args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
