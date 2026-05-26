"""
gui/editor_widget.py — EditorWidget
Встроенный редактор кода с поддержкой vim-режима (через QScintilla или fallback).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class CodeEditor(QPlainTextEdit):
    """
    Редактор кода.
    Пытается использовать QScintilla; если не установлен — фоллбэк на QPlainTextEdit.
    Vim-режим реализован упрощённо через keyPressEvent.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vim_mode = False
        self._vim_command_mode = False   # True = Normal mode, False = Insert
        self._command_buf = ""
        font = QFont("JetBrains Mono", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #0d1117;"
            "  color: #e6edf3;"
            "  border: none;"
            "  selection-background-color: #264f78;"
            "}"
        )

    def set_vim_mode(self, enabled: bool) -> None:
        self._vim_mode = enabled
        if enabled:
            self._vim_command_mode = True   # Start in Normal mode

    def keyPressEvent(self, event) -> None:
        if not self._vim_mode:
            super().keyPressEvent(event)
            return
        self._handle_vim_key(event)

    def _handle_vim_key(self, event) -> None:
        key = event.key()
        text = event.text()
        mod = event.modifiers()

        if self._vim_command_mode:
            # Normal mode
            if text == "i":
                self._vim_command_mode = False
                return
            if text == "a":
                self._vim_command_mode = False
                cursor = self.textCursor()
                cursor.movePosition(cursor.MoveOperation.Right)
                self.setTextCursor(cursor)
                return
            if text == "o":
                self._vim_command_mode = False
                cursor = self.textCursor()
                cursor.movePosition(cursor.MoveOperation.EndOfLine)
                cursor.insertText("\n")
                self.setTextCursor(cursor)
                return
            if text in ("h", "j", "k", "l"):
                moves = {
                    "h": QPlainTextEdit.textCursor(self).MoveOperation.Left,
                    "l": QPlainTextEdit.textCursor(self).MoveOperation.Right,
                    "j": QPlainTextEdit.textCursor(self).MoveOperation.Down,
                    "k": QPlainTextEdit.textCursor(self).MoveOperation.Up,
                }
                from PyQt6.QtGui import QTextCursor
                cursor = self.textCursor()
                cursor.movePosition(getattr(QTextCursor.MoveOperation, text.upper() if text in "jk" else ("Left" if text == "h" else "Right")))
                self.setTextCursor(cursor)
                return
            if text == "G":
                cursor = self.textCursor()
                from PyQt6.QtGui import QTextCursor
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(cursor)
                return
            if text == "0":
                cursor = self.textCursor()
                from PyQt6.QtGui import QTextCursor
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                self.setTextCursor(cursor)
                return
            if text == "$":
                cursor = self.textCursor()
                from PyQt6.QtGui import QTextCursor
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                self.setTextCursor(cursor)
                return
            if text == "x":
                cursor = self.textCursor()
                from PyQt6.QtGui import QTextCursor
                cursor.deleteChar()
                return
        else:
            # Insert mode
            if key == Qt.Key.Key_Escape:
                self._vim_command_mode = True
                return
            super().keyPressEvent(event)


class EditorTab(QWidget):
    """Вкладка редактора — один файл."""
    insert_to_prompt = pyqtSignal(str)

    def __init__(self, file_path: Optional[str] = None, content: str = "", parent=None) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self._modified = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)

        self._path_label = QLabel(file_path or "Новый файл")
        self._path_label.setStyleSheet("color: #8b949e; font-size: 11px;")

        self._vim_label = QLabel()
        self._vim_label.setStyleSheet("color: #388bfd; font-size: 11px; font-weight: bold;")

        save_btn = QPushButton("💾")
        save_btn.setFixedSize(28, 28)
        save_btn.setToolTip("Сохранить")
        save_btn.clicked.connect(self._save_file)

        insert_btn = QPushButton("📋→")
        insert_btn.setFixedSize(36, 28)
        insert_btn.setToolTip("Вставить содержимое в запрос")
        insert_btn.clicked.connect(self._insert_to_prompt)

        toolbar.addWidget(self._path_label)
        toolbar.addStretch()
        toolbar.addWidget(self._vim_label)
        toolbar.addWidget(save_btn)
        toolbar.addWidget(insert_btn)

        self._editor = CodeEditor()
        self._editor.setPlainText(content)
        self._editor.textChanged.connect(lambda: setattr(self, "_modified", True))

        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet("QFrame { background: #161b22; border-bottom: 1px solid #30363d; }")
        toolbar_frame.setLayout(toolbar)

        layout.addWidget(toolbar_frame)
        layout.addWidget(self._editor)

    def set_vim_mode(self, enabled: bool) -> None:
        self._editor.set_vim_mode(enabled)
        if enabled:
            self._editor._vim_command_mode = True
        self._vim_label.setText("VIM" if enabled else "")

    def get_content(self) -> str:
        return self._editor.toPlainText()

    def set_content(self, content: str) -> None:
        self._editor.setPlainText(content)
        self._modified = False

    def _save_file(self) -> None:
        if not self.file_path:
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл")
            if not path:
                return
            self.file_path = path
            self._path_label.setText(path)
        Path(self.file_path).write_text(self._editor.toPlainText(), encoding="utf-8")
        self._modified = False

    def _insert_to_prompt(self) -> None:
        self.insert_to_prompt.emit(self._editor.toPlainText())


class EditorWidget(QWidget):
    """Правая панель: редактор с вкладками."""

    insert_to_prompt = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vim_mode = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(12, 6, 12, 6)
        title = QLabel("📝 Редактор")
        title.setStyleSheet("color: #8b949e; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;")

        self._vim_toggle = QPushButton("VIM OFF")
        self._vim_toggle.setFixedWidth(80)
        self._vim_toggle.setStyleSheet(
            "QPushButton { background: #21262d; color: #8b949e; border: 1px solid #30363d; "
            "border-radius: 4px; font-size: 10px; padding: 3px 8px; }"
            "QPushButton:checked { background: #1c4a8f; color: #79c0ff; border-color: #388bfd; }"
        )
        self._vim_toggle.setCheckable(True)
        self._vim_toggle.toggled.connect(self._toggle_vim)

        new_tab_btn = QPushButton("+")
        new_tab_btn.setFixedWidth(28)
        new_tab_btn.setToolTip("Новая вкладка")
        new_tab_btn.clicked.connect(lambda: self.open_file())

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._vim_toggle)
        header.addWidget(new_tab_btn)

        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background: #161b22; border-bottom: 1px solid #30363d; }")
        header_frame.setLayout(header)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)

        layout.addWidget(header_frame)
        layout.addWidget(self._tabs)

        # Открыть пустую вкладку
        self.open_file(content="# Новый файл\n")

    # ── Public API ─────────────────────────────────────────

    def open_file(self, file_path: Optional[str] = None, content: str = "") -> None:
        if file_path and Path(file_path).exists():
            content = Path(file_path).read_text(encoding="utf-8")
        tab = EditorTab(file_path, content)
        tab.set_vim_mode(self._vim_mode)
        tab.insert_to_prompt.connect(self.insert_to_prompt.emit)
        title = Path(file_path).name if file_path else "Новый файл"
        self._tabs.addTab(tab, title)
        self._tabs.setCurrentIndex(self._tabs.count() - 1)

    def open_project_files(self, project_dir: str) -> None:
        project_path = Path(project_dir)
        for f in sorted(project_path.rglob("*"))[:20]:   # Лимит 20 файлов
            if f.is_file() and f.suffix in (".py", ".json", ".toml", ".md", ".txt", ".sh", ".html"):
                self.open_file(str(f))

    def get_current_content(self) -> str:
        tab = self._tabs.currentWidget()
        return tab.get_content() if isinstance(tab, EditorTab) else ""

    # ── Internal ──────────────────────────────────────────

    def _toggle_vim(self, checked: bool) -> None:
        self._vim_mode = checked
        self._vim_toggle.setText("VIM ON" if checked else "VIM OFF")
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab.set_vim_mode(checked)

    def _close_tab(self, index: int) -> None:
        if self._tabs.count() > 1:
            self._tabs.removeTab(index)
