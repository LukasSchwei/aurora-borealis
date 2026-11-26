"""Custom integrated window title bar with zoom stage selector & theme toggle."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
)

from ...config import UI_ZOOM_STAGES, get_zoom_stage_index
from ..icons import apply_button_icon, refresh_themed_icons, svg_icon, svg_pixmap
from ..ui_helpers import configure_dropdown_combo


def _make_kde_win_icon(kind: str, color_hex: str, size: int = 16) -> QIcon:
    """Render consistent SVG window control icons across Linux and Windows."""
    valid_kind = kind if kind in ("minimize", "maximize", "restore", "close") else "close"
    return svg_icon(f"window-{valid_kind}", color_hex, size)


class _WindowTitleBar(QFrame):
    """Custom integrated window bar with SVG window controls, 5-stage zoom selector & theme toggle."""

    def __init__(self, parent_win: QMainWindow, icon_path: Path) -> None:
        super().__init__(parent_win)
        self._win = parent_win
        self._drag_pos = None
        self._theme = "dark"
        self.setObjectName("WindowTitleBar")
        self.setFixedHeight(34)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(10, 0, 0, 0)
        hl.setSpacing(6)

        self.lbl_logo = QLabel()
        self.lbl_logo.setFixedSize(18, 18)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo.setToolTip("Aurora Borealis")
        self._refresh_logo_pixmap()
        hl.addWidget(self.lbl_logo)
        hl.addStretch()

        self.btn_scale_minus = QPushButton("")
        self.btn_scale_minus.setObjectName("StepperBtn")
        self.btn_scale_minus.setToolTip("Previous Zoom Stage")
        self.btn_scale_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_button_icon(self.btn_scale_minus, "minus", theme="dark", size=13)

        self.cmb_scale_stage = QComboBox()
        self.cmb_scale_stage.setObjectName("ScaleStageCombo")
        self.cmb_scale_stage.setToolTip("Select UI Zoom Stage")
        for val, name in UI_ZOOM_STAGES:
            self.cmb_scale_stage.addItem(f"{name} ({round(val * 100)}%)", val)
        configure_dropdown_combo(self.cmb_scale_stage, max_visible=len(UI_ZOOM_STAGES))
        self.cmb_scale_stage.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.cmb_scale_stage.setFixedWidth(150)

        self.btn_scale_plus = QPushButton("")
        self.btn_scale_plus.setObjectName("StepperBtn")
        self.btn_scale_plus.setToolTip("Next Zoom Stage")
        self.btn_scale_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_button_icon(self.btn_scale_plus, "plus", theme="dark", size=13)

        hl.addWidget(self.btn_scale_minus)
        hl.addWidget(self.cmb_scale_stage)
        hl.addWidget(self.btn_scale_plus)

        self.btn_theme = QPushButton("")
        self.btn_theme.setObjectName("ThemeToggleBtn")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.setToolTip("Switch to Light Mode")
        apply_button_icon(self.btn_theme, "sun", theme="dark", size=15)
        hl.addWidget(self.btn_theme)

        self.btn_min = QPushButton()
        self.btn_min.setObjectName("KdeWinBtn")
        self.btn_min.setToolTip("Minimize")
        self.btn_min.setIconSize(QSize(14, 14))
        self.btn_min.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.btn_min.setCursor(Qt.CursorShape.ArrowCursor)
        self.btn_min.clicked.connect(self._win.showMinimized)

        self.btn_max = QPushButton()
        self.btn_max.setObjectName("KdeWinBtn")
        self.btn_max.setToolTip("Maximize / Restore")
        self.btn_max.setIconSize(QSize(14, 14))
        self.btn_max.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.btn_max.setCursor(Qt.CursorShape.ArrowCursor)
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("KdeCloseBtn")
        self.btn_close.setToolTip("Close")
        self.btn_close.setIconSize(QSize(14, 14))
        self.btn_close.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.btn_close.setCursor(Qt.CursorShape.ArrowCursor)
        self.btn_close.clicked.connect(self._win.close)

        win_btns = QHBoxLayout()
        win_btns.setContentsMargins(0, 0, 0, 0)
        win_btns.setSpacing(0)
        win_btns.addWidget(self.btn_min)
        win_btns.addWidget(self.btn_max)
        win_btns.addWidget(self.btn_close)

        hl.addSpacing(4)
        hl.addLayout(win_btns)
        self._refresh_kde_icons()

    def _refresh_logo_pixmap(self) -> None:
        logo_color = "#6b7280" if self._theme == "light" else "#5b616b"
        self.lbl_logo.setPixmap(svg_pixmap("aurora-logo-subtle", logo_color, 18))

    def _refresh_kde_icons(self) -> None:
        fg = "#1f1f1f" if self._theme == "light" else "#e2e5ea"
        self.btn_min.setIcon(_make_kde_win_icon("minimize", fg, 14))
        self.btn_max.setIcon(_make_kde_win_icon("restore" if self._win.isMaximized() else "maximize", fg, 14))
        self.btn_close.setIcon(_make_kde_win_icon("close", fg, 14))

    def set_theme_icon(self, theme: str) -> None:
        self._theme = "light" if theme == "light" else "dark"
        if self._theme == "light":
            apply_button_icon(self.btn_theme, "moon", theme="light", size=15)
            self.btn_theme.setToolTip("Switch to Dark Mode")
        else:
            apply_button_icon(self.btn_theme, "sun", theme="dark", size=15)
            self.btn_theme.setToolTip("Switch to Light Mode")
        refresh_themed_icons(self, self._theme)
        self._refresh_logo_pixmap()
        self._refresh_kde_icons()

    def set_scale_value(self, scale: float) -> None:
        idx = get_zoom_stage_index(scale)
        s = UI_ZOOM_STAGES[idx][0]
        self.setFixedHeight(max(30, round(34 * s)))
        self.cmb_scale_stage.blockSignals(True)
        self.cmb_scale_stage.setCurrentIndex(idx)
        self.cmb_scale_stage.blockSignals(False)
        self.cmb_scale_stage.setFixedWidth(max(134, round(150 * s)))
        self.btn_scale_minus.setEnabled(idx > 0)
        self.btn_scale_plus.setEnabled(idx < len(UI_ZOOM_STAGES) - 1)

    def set_breadcrumb(self, text: str) -> None:
        self.lbl_logo.setToolTip(f"Aurora Borealis — {text}" if text else "Aurora Borealis")

    def _toggle_maximize(self) -> None:
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self._refresh_kde_icons()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            wh = self._win.windowHandle()
            if wh is not None and wh.startSystemMove():
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self._win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
