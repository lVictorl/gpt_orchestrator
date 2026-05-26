"""
gui/dialogs/history_projects_dialog.py — HistoryProjectsDialog

Исправления:
  - #2  «История проектов» теперь открывает реальный диалог
  - #16 Двойной клик на файл открывает его в редакторе
"""
from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from storage.models import ProjectMeta


class HistoryProjectsDialog(QDialog):
    """
    Диалог истории проектов.
    Слева — список проектов, справа — файлы проекта.
    Двойной клик → открыть файл (#16).
    """

    file_open_requested = pyqtSignal(str)   # путь к файлу

    def __init__(self, storage, projects_root: str = "projects", parent=None) -> None:
        super().__init__(parent)
        self._storage = storage
        self._projects_root = Path(projects_root)
        self.setWindowTitle("📚 История проектов")
        self.setMinimumSize(800, 500)
        self.setModal(True)
        self._setup_ui()
        self._load_projects()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая: список проектов
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Проекты:"))
        self._project_list = QListWidget()
        self._project_list.currentItemChanged.connect(self._on_project_selected)
        left_layout.addWidget(self._project_list)
        splitter.addWidget(left)

        # Правая: файлы проекта
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Файлы проекта (двойной клик — открыть):"))
        self._file_tree = QTreeWidget()
        self._file_tree.setHeaderLabel("Файл")
        self._file_tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        right_layout.addWidget(self._file_tree)

        btn_row = QHBoxLayout()
        open_html_btn = QPushButton("🌐 Открыть отчёт")
        open_html_btn.clicked.connect(self._open_report)
        btn_row.addWidget(open_html_btn)

        open_folder_btn = QPushButton("📁 Открыть папку")
        open_folder_btn.setToolTip("Открыть папку проекта в файловом проводнике")
        open_folder_btn.clicked.connect(self._open_project_folder)
        btn_row.addWidget(open_folder_btn)

        btn_row.addStretch()
        right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([280, 520])

        layout.addWidget(splitter)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_projects(self) -> None:
        try:
            projects = self._storage.list_projects_sync()
        except Exception:
            projects = []

        self._project_list.clear()
        for p in projects:
            item = QListWidgetItem(
                f"{p.project_id[:8]} | {p.task_type} | {p.title or 'Без названия'}"
            )
            item.setData(Qt.ItemDataRole.UserRole, p.project_id)
            self._project_list.addItem(item)

    def _on_project_selected(self, item: QListWidgetItem | None, _=None) -> None:
        if not item:
            return
        project_id = item.data(Qt.ItemDataRole.UserRole)
        self._populate_files(project_id)

    def _populate_files(self, project_id: str) -> None:
        self._file_tree.clear()
        project_dir = self._projects_root / project_id
        if not project_dir.exists():
            root_item = QTreeWidgetItem(["(папка проекта не найдена)"])
            self._file_tree.addTopLevelItem(root_item)
            return

        def add_dir(parent, path: Path):
            for child in sorted(path.iterdir()):
                if child.is_dir():
                    dir_item = QTreeWidgetItem([child.name + "/"])
                    parent.addChild(dir_item)
                    add_dir(dir_item, child)
                else:
                    file_item = QTreeWidgetItem([child.name])
                    file_item.setData(0, Qt.ItemDataRole.UserRole, str(child))
                    parent.addChild(file_item)

        root_item = QTreeWidgetItem([str(project_dir)])
        root_item.setData(0, Qt.ItemDataRole.UserRole, str(project_dir))
        self._file_tree.addTopLevelItem(root_item)
        add_dir(root_item, project_dir)
        root_item.setExpanded(True)

    def _on_file_double_clicked(self, item: QTreeWidgetItem, _: int) -> None:
        """Двойной клик — открыть файл (#16)."""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and Path(path).is_file():
            self.file_open_requested.emit(path)
            self.accept()

    def _open_report(self) -> None:
        """Открыть HTML-отчёт в браузере."""
        current = self._project_list.currentItem()
        if not current:
            return
        project_id = current.data(Qt.ItemDataRole.UserRole)
        report = self._projects_root / project_id / "report.html"
        if report.exists():
            webbrowser.open(f"file://{report.resolve()}")

    def _open_project_folder(self) -> None:
        """Открыть папку проекта в файловом проводнике системы."""
        current = self._project_list.currentItem()
        if not current:
            return
        project_id = current.data(Qt.ItemDataRole.UserRole)
        project_dir = self._projects_root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        import subprocess, sys as _sys
        path_str = str(project_dir.resolve())
        try:
            if _sys.platform == "win32":
                subprocess.Popen(["explorer", path_str])
            elif _sys.platform == "darwin":
                subprocess.Popen(["open", path_str])
            else:
                # Linux: try xdg-open, then nautilus, then dolphin
                for cmd in ["xdg-open", "nautilus", "dolphin", "thunar", "nemo"]:
                    try:
                        subprocess.Popen([cmd, path_str])
                        break
                    except FileNotFoundError:
                        continue
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Ошибка",
                f"Не удалось открыть папку:\n{path_str}\n\nОшибка: {exc}"
            )

    def current_project_id(self) -> Optional[str]:
        item = self._project_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None
