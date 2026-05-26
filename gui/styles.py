"""
gui/styles.py — DARK_THEME (QSS)

Профессиональная тёмная тема в стиле GitHub Dark.
Поддерживает все кастомные виджеты: ChatWidget, PipelinePanel,
HistoryPanel, GenerationPlanWidget.
"""

DARK_THEME = """
/* ── Основа ── */
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace;
    font-size: 13px;
}

QMainWindow {
    background-color: #0d1117;
}

/* ── Меню ── */
QMenuBar {
    background-color: #161b22;
    color: #c9d1d9;
    border-bottom: 1px solid #30363d;
    padding: 2px;
}
QMenuBar::item {
    padding: 4px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #21262d;
    color: #e6edf3;
}
QMenu {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
    color: #c9d1d9;
}
QMenu::item:selected {
    background-color: #21262d;
    color: #e6edf3;
}
QMenu::separator {
    height: 1px;
    background: #30363d;
    margin: 4px 8px;
}

/* ── Кнопки ── */
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 26px;
}
QPushButton:hover {
    background-color: #30363d;
    color: #e6edf3;
    border-color: #484f58;
}
QPushButton:pressed {
    background-color: #161b22;
    border-color: #388bfd;
}
QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
    border-color: #21262d;
}
QPushButton#sendBtn {
    background-color: #1c4a8f;
    color: #e6edf3;
    border: 1px solid #388bfd;
    font-weight: bold;
}
QPushButton#sendBtn:hover {
    background-color: #388bfd;
    color: #ffffff;
}
QPushButton#abortBtn {
    background-color: #2a0d0d;
    color: #da3633;
    border: 1px solid #da3633;
}
QPushButton#abortBtn:hover {
    background-color: #da3633;
    color: #ffffff;
}

/* ── Поля ввода ── */
QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #0d1117;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: #388bfd;
    outline: none;
}

/* ── Прокрутка ── */
QScrollArea {
    background-color: #0d1117;
    border: none;
}
QScrollBar:vertical {
    background: #0d1117;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #484f58;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #0d1117;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    border-radius: 4px;
    min-width: 24px;
}

/* ── Сплиттер ── */
QSplitter::handle {
    background-color: #21262d;
}
QSplitter::handle:hover {
    background-color: #388bfd;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}

/* ── ComboBox ── */
QComboBox {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 26px;
}
QComboBox:hover {
    border-color: #484f58;
}
QComboBox:focus {
    border-color: #388bfd;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8b949e;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    selection-background-color: #21262d;
}

/* ── TabWidget ── */
QTabWidget::pane {
    border: none;
    background-color: #0d1117;
}
QTabBar::tab {
    background-color: #161b22;
    color: #8b949e;
    padding: 8px 18px;
    border: none;
    border-right: 1px solid #21262d;
}
QTabBar::tab:selected {
    background-color: #0d1117;
    color: #e6edf3;
    border-bottom: 2px solid #388bfd;
}
QTabBar::tab:hover:!selected {
    background-color: #1c2128;
    color: #c9d1d9;
}

/* ── Прогресс-бар ── */
QProgressBar {
    background-color: #21262d;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #c9d1d9;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #388bfd;
    border-radius: 4px;
}

/* ── Статус-бар ── */
QStatusBar {
    background-color: #161b22;
    color: #8b949e;
    border-top: 1px solid #21262d;
    font-size: 11px;
}
QStatusBar::item {
    border: none;
}

/* ── GroupBox ── */
QGroupBox {
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
    color: #8b949e;
    font-size: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 12px;
    color: #8b949e;
}

/* ── CheckBox ── */
QCheckBox {
    color: #c9d1d9;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #484f58;
    border-radius: 3px;
    background-color: #0d1117;
}
QCheckBox::indicator:checked {
    background-color: #388bfd;
    border-color: #388bfd;
}

/* ── SpinBox ── */
QSpinBox, QDoubleSpinBox {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #388bfd;
}

/* ── Label ── */
QLabel {
    color: #c9d1d9;
    background: transparent;
}

/* ── DialogButtonBox ── */
QDialogButtonBox QPushButton {
    min-width: 80px;
}

/* ── TreeWidget ── */
QTreeWidget {
    background-color: #0d1117;
    border: none;
    color: #c9d1d9;
    alternate-background-color: #0d1117;
}
QTreeWidget::item {
    padding: 4px 2px;
    border-radius: 4px;
    min-height: 24px;
}
QTreeWidget::item:selected {
    background-color: #1c4a8f;
    color: #e6edf3;
}
QTreeWidget::item:hover {
    background-color: #21262d;
}
QTreeWidget::branch {
    background-color: #0d1117;
}

/* ── ListWidget ── */
QListWidget {
    background-color: #0d1117;
    border: 1px solid #21262d;
    border-radius: 6px;
    color: #c9d1d9;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
    min-height: 22px;
}
QListWidget::item:selected {
    background-color: #1c4a8f;
    color: #e6edf3;
}
QListWidget::item:hover {
    background-color: #21262d;
}

/* ── Dialogs ── */
QDialog {
    background-color: #0d1117;
}

/* ── Frame ── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {
    color: #21262d;
}

/* ── ToolButton ── */
QToolButton {
    background: transparent;
    border: none;
    color: #8b949e;
    padding: 2px;
    border-radius: 3px;
}
QToolButton:hover {
    background: #21262d;
    color: #c9d1d9;
}

/* ── InputDialog ── */
QInputDialog {
    background-color: #0d1117;
}
"""
