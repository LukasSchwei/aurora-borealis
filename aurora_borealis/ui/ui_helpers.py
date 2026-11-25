"""Cross-platform UI helpers (wheel-scroll forwarding and bounded ComboBox popups)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QWidget,
)


class _NoWheelScrollFilter(QObject):
    """Prevent hovered QComboBox / QAbstractSpinBox widgets from stealing scroll-wheel events."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() != QEvent.Type.Wheel or not isinstance(event, QWheelEvent):
            return False

        target: Optional[QWidget] = obj if isinstance(obj, QWidget) else None
        # Walk up if the wheel event lands on a QSpinBox's internal QLineEdit
        if target is not None and not isinstance(target, (QComboBox, QAbstractSpinBox)):
            parent = target.parentWidget()
            if isinstance(parent, (QComboBox, QAbstractSpinBox)):
                target = parent

        if isinstance(target, (QComboBox, QAbstractSpinBox)):
            if isinstance(target, QComboBox) and target.view().isVisible():
                return False

            scroll_area = self._find_ancestor_scroll_area(target)
            if scroll_area is not None:
                vp = scroll_area.viewport()
                local_pos = vp.mapFromGlobal(event.globalPosition().toPoint())
                forwarded = QWheelEvent(
                    local_pos,
                    event.globalPosition(),
                    event.pixelDelta(),
                    event.angleDelta(),
                    event.buttons(),
                    event.modifiers(),
                    event.phase(),
                    event.inverted(),
                    event.source(),
                )
                QApplication.sendEvent(vp, forwarded)
                event.accept()
                return True

            if not target.hasFocus():
                event.ignore()
                return True
        return False

    @staticmethod
    def _find_ancestor_scroll_area(widget: QWidget) -> Optional[QAbstractScrollArea]:
        cur = widget.parentWidget()
        while cur is not None:
            if isinstance(cur, QAbstractScrollArea):
                sb = cur.verticalScrollBar()
                if sb is not None and (sb.maximum() > sb.minimum() or cur.metaObject().className() == "QScrollArea"):
                    return cur
            cur = cur.parentWidget()
        return None


def install_global_wheel_filter(app: Optional[QApplication]) -> None:
    """Idempotently install the global wheel-scroll filter on the QApplication."""
    if app is None:
        return
    if app.property("_aurora_wheel_filter") is not None:
        return
    flt = _NoWheelScrollFilter(app)
    app.installEventFilter(flt)
    app.setProperty("_aurora_wheel_filter", flt)


class _PopupWidthFilter(QObject):
    """Ensure QComboBox popup views widen cleanly so dropdown items never elide with '...'."""

    def __init__(self, combo: QComboBox, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._combo = combo

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.Show:
            view = self._combo.view()
            if view is not None:
                needed = max(self._combo.width(), view.sizeHintForColumn(0) + 36)
                screen = self._combo.screen() or QApplication.primaryScreen()
                if screen is not None:
                    max_w = max(self._combo.width(), screen.availableGeometry().width() - 40)
                    needed = min(needed, max_w)
                view.setMinimumWidth(needed)
        return False


def configure_dropdown_combo(cmb: QComboBox, max_visible: int = 14) -> None:
    """Keep long QComboBox dropdowns bounded on-screen, non-eliding, and wheel-safe."""
    cmb.setMaxVisibleItems(max_visible)
    cmb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    cmb.setMinimumContentsLength(0)
    if cmb.objectName() == "ScaleStageCombo":
        cmb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    else:
        cmb.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
    cmb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    view = cmb.view()
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setTextElideMode(Qt.TextElideMode.ElideNone)
    if view.property("_aurora_popup_w_filter") is None:
        pf = _PopupWidthFilter(cmb, view)
        view.installEventFilter(pf)
        view.setProperty("_aurora_popup_w_filter", pf)


_FIXED_BUTTON_OBJECT_NAMES = frozenset(
    {
        "ThemeToggleBtn",
        "KdeWinBtn",
        "KdeCloseBtn",
        "StepperBtn",
        "TrashBtn",
        "FavBtn",
        "RailPortraitBtn",
        "CharPortraitBtn",
        "NewCharDashedCard",
        "OverviewCard",
    }
)


def fit_button(btn: QPushButton) -> None:
    """Ensure a QPushButton's minimum width always fits its current label text."""
    if btn.objectName() in _FIXED_BUTTON_OBJECT_NAMES:
        return
    if not btn.text().strip():
        return
    btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    btn.setMinimumWidth(0)
    btn.ensurePolished()
    btn.updateGeometry()
    btn.setMinimumWidth(btn.sizeHint().width())


def refit_buttons(root: QWidget) -> None:
    """Lightweight button width refresh used during zoom stage changes."""
    for btn in root.findChildren(QPushButton):
        fit_button(btn)


def ensure_widgets_fit(root: QWidget) -> None:
    """Size buttons, combos, tabs, and tables to fit their labels without '...' truncation."""
    for btn in root.findChildren(QPushButton):
        fit_button(btn)

    for cmb in root.findChildren(QComboBox):
        mv = cmb.maxVisibleItems()
        configure_dropdown_combo(cmb, max_visible=min(14, max(8, mv if mv > 0 else 14)))

    for tw in root.findChildren(QTabWidget):
        tw.setElideMode(Qt.TextElideMode.ElideNone)
        tw.setUsesScrollButtons(True)

    for tbl in root.findChildren(QTableWidget):
        tbl.setTextElideMode(Qt.TextElideMode.ElideNone)
        tbl.horizontalHeader().setTextElideMode(Qt.TextElideMode.ElideNone)

    for lst in root.findChildren(QListWidget):
        lst.setTextElideMode(Qt.TextElideMode.ElideNone)

    for sp in root.findChildren(QSplitter):
        sp.setChildrenCollapsible(False)
