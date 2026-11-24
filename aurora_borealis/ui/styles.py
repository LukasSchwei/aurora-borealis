"""Modern dark stylesheet for Aurora Borealis."""

DARK_STYLESHEET = """
QMainWindow, QWidget, QDialog {
    background-color: #0f141d;
    color: #e6edf5;
    font-family: "Inter", "Noto Sans", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QMenuBar {
    background-color: #141b26;
    border-bottom: 1px solid #243044;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #233248;
    border-radius: 4px;
}
QMenu {
    background-color: #161f2d;
    border: 1px solid #2b3950;
}
QMenu::item:selected {
    background-color: #2c4a6e;
}
QFrame#TopNavBar {
    background-color: #141b26;
    border-bottom: 1px solid #243044;
}
QFrame#SubBar {
    background-color: #121822;
    border-bottom: 1px solid #243044;
}
QFrame#SidebarCard, QFrame#CharCard, QFrame#ChoiceCard {
    background-color: #151d2a;
    border: 1px solid #243247;
    border-radius: 10px;
}
QFrame#CharCard:hover {
    border-color: #4fd1c5;
}
QFrame#ChoiceCardPending {
    background-color: #151d2a;
    border: 1px solid #d69e2e;
    border-radius: 10px;
}
QPushButton#NewCharDashedCard {
    background-color: #111722;
    border: 2px dashed #2c3c55;
    border-radius: 10px;
    color: #cbd5e1;
    padding: 18px;
}
QPushButton#NewCharDashedCard:hover {
    border-color: #4fd1c5;
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #243247;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 12px;
    font-weight: bold;
    color: #7dd3fc;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTableWidget {
    background-color: #0b1017;
    border: 1px solid #28364b;
    border-radius: 6px;
    padding: 5px 8px;
    color: #e6edf5;
    selection-background-color: #2c5282;
}
QTableWidget {
    padding: 0px;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QPushButton {
    background-color: #182334;
    color: #e6edf5;
    border: 1px solid #2b3b54;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #203047;
    border-color: #4fd1c5;
}
QPushButton:pressed {
    background-color: #131c29;
}
QPushButton#PrimaryBtn {
    background-color: #2b6cb0;
    border: 1px solid #3b82f6;
    color: #ffffff;
}
QPushButton#PrimaryBtn:hover {
    background-color: #3182ce;
    border-color: #7dd3fc;
}
QPushButton#DangerBtn {
    background-color: #2c171c;
    border: 1px solid #7f1d1d;
    color: #fca5a5;
}
QPushButton#DangerBtn:hover {
    background-color: #451a22;
    border-color: #ef4444;
}
QPushButton#StepperBtn {
    padding: 0px;
    font-size: 13pt;
    font-weight: bold;
    min-width: 30px;
    max-width: 30px;
    min-height: 28px;
    max-height: 28px;
}
QPushButton#NavTabBtn {
    background-color: transparent;
    border: 1px solid transparent;
    color: #94a3b8;
    padding: 6px 12px;
    border-radius: 6px;
}
QPushButton#NavTabBtn:hover {
    color: #ffffff;
    background-color: #1c2738;
}
QPushButton#NavTabBtn[active="true"] {
    background-color: #2b6cb0;
    color: #ffffff;
    border-color: #3b82f6;
}
QHeaderView::section {
    background-color: #17202e;
    color: #9bb0c9;
    border: none;
    border-bottom: 1px solid #26344a;
    padding: 2px 6px;
    font-weight: bold;
}
QTableWidget::item {
    padding: 0px 6px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QLabel#StatValue {
    font-size: 15pt;
    font-weight: bold;
    color: #4fd1c5;
}
QLabel#StatLabel {
    font-size: 8.5pt;
    color: #94a3b8;
}
QLabel#CharTitle {
    font-size: 13.5pt;
    font-weight: bold;
    color: #ffffff;
}
QLabel#CharSubtitle {
    font-size: 9.5pt;
    color: #7dd3fc;
}
QLabel#RulesetPill {
    background-color: #1e3a5f;
    color: #7dd3fc;
    border: 1px solid #2f5585;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 8.5pt;
    font-weight: bold;
}
QLabel#PortraitFrame {
    background-color: #0b1017;
    border: 1px solid #2c3c55;
    border-radius: 10px;
    color: #7dd3fc;
    font-weight: bold;
}
"""
