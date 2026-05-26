"""
main.py — Точка входа GPT-Orchestrator

Исправление #2: Фоллбэк шрифта если JetBrains Mono не установлен
              (предотвращает ошибку QFont::setPointSize: Point size <= 0 (-1))
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontDatabase

from gui.main_window import MainWindow
from gui.styles import DARK_THEME


def _get_monospace_font(size: int = 12) -> QFont:
    """Выбирает шрифт с гарантированным размером > 0. Исправление #2."""
    preferred = ["JetBrains Mono", "Fira Code", "Consolas", "Courier New", "Monospace"]
    available = QFontDatabase.families()
    for name in preferred:
        if any(name.lower() in f.lower() for f in available):
            font = QFont(name, size)
            if font.pointSize() > 0:
                return font
    # Абсолютный фоллбэк — системный monospace
    font = QFont()
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(max(size, 10))
    return font


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GPT-Orchestrator")
    app.setApplicationVersion("1.7.0")
    app.setOrganizationName("GPT-Orchestrator")

    app.setStyleSheet(DARK_THEME)

    font = _get_monospace_font(12)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
