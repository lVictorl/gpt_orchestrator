"""
gui/dialogs/project_wizard.py — ProjectWizardDialog

Исправление #9: форма-опросник для пользователя с предзаполненными рекомендациями.
Пользователю нужно заполнить только:
  - название проекта
  - суть проекта
  - ключевые особенности
  - технологии/языки
  - целевая ОС
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)


class ProjectWizardDialog(QDialog):
    """
    Форма-опросник для создания нового проекта.
    Предзаполнена рекомендациями — пользователю достаточно указать суть.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🧙 Мастер создания проекта")
        self.setMinimumWidth(560)
        self.setMinimumHeight(500)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        hint = QLabel(
            "Заполните поля ниже. Рекомендованные значения уже предустановлены — "
            "вы можете изменить их при необходимости."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(hint)

        # ── Основные данные ──
        main_group = QGroupBox("Основные данные")
        main_form = QFormLayout(main_group)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Например: Todo Manager Bot")
        main_form.addRow("Название проекта *:", self._name_edit)

        self._description_edit = QPlainTextEdit()
        self._description_edit.setPlaceholderText(
            "Опишите суть проекта: что он должен делать, какую проблему решать."
        )
        self._description_edit.setMaximumHeight(100)
        main_form.addRow("Суть проекта *:", self._description_edit)

        self._features_edit = QPlainTextEdit()
        self._features_edit.setPlaceholderText(
            "Ключевые особенности: аутентификация, REST API, уведомления, и т.д."
        )
        self._features_edit.setMaximumHeight(80)
        main_form.addRow("Ключевые особенности:", self._features_edit)

        layout.addWidget(main_group)

        # ── Технологии ──
        tech_group = QGroupBox("Технологии")
        tech_form = QFormLayout(tech_group)

        self._lang_combo = QComboBox()
        self._lang_combo.setEditable(True)
        self._lang_combo.addItems(["Python", "TypeScript", "Kotlin", "Java", "Go", "Rust", "C++", "JavaScript"])
        tech_form.addRow("Язык программирования:", self._lang_combo)

        self._frameworks_edit = QLineEdit()
        self._frameworks_edit.setPlaceholderText("FastAPI, SQLAlchemy, PyQt6, ...")
        self._frameworks_edit.setText("FastAPI, SQLAlchemy, Pydantic")
        tech_form.addRow("Фреймворки / библиотеки:", self._frameworks_edit)

        self._db_combo = QComboBox()
        self._db_combo.addItems(["SQLite", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Нет"])
        tech_form.addRow("База данных:", self._db_combo)

        self._os_combo = QComboBox()
        self._os_combo.addItems(["Linux", "Windows", "macOS", "Кроссплатформенный", "Android"])
        tech_form.addRow("Целевая ОС:", self._os_combo)

        layout.addWidget(tech_group)

        # ── Дополнительно ──
        extra_group = QGroupBox("Дополнительные требования")
        extra_form = QFormLayout(extra_group)

        self._extra_edit = QPlainTextEdit()
        self._extra_edit.setPlaceholderText(
            "Любые дополнительные технические или бизнес-требования..."
        )
        self._extra_edit.setMaximumHeight(70)
        self._extra_edit.setPlainText(
            "- Покрытие Unit-тестами >= 80%\n"
            "- Документация на русском\n"
            "- Поддержка Docker"
        )
        extra_form.addRow("Требования:", self._extra_edit)

        layout.addWidget(extra_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        if not self._name_edit.text().strip():
            self._name_edit.setPlaceholderText("⚠️ Обязательное поле!")
            return
        if not self._description_edit.toPlainText().strip():
            return
        self.accept()

    def build_task_prompt(self) -> str:
        """Формирует текст задачи для передачи в пайплайн."""
        lines = [
            f"Проект: {self._name_edit.text().strip()}",
            f"\nСуть: {self._description_edit.toPlainText().strip()}",
        ]
        features = self._features_edit.toPlainText().strip()
        if features:
            lines.append(f"\nКлючевые особенности:\n{features}")
        lines.append(f"\nЯзык: {self._lang_combo.currentText()}")
        lines.append(f"Фреймворки: {self._frameworks_edit.text()}")
        lines.append(f"База данных: {self._db_combo.currentText()}")
        lines.append(f"Целевая ОС: {self._os_combo.currentText()}")
        extra = self._extra_edit.toPlainText().strip()
        if extra:
            lines.append(f"\nДополнительные требования:\n{extra}")
        return "\n".join(lines)

    @property
    def project_name(self) -> str:
        return self._name_edit.text().strip()
