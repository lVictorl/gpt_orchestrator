"""
gui/generation_plan_widget.py — GenerationPlanWidget

Вкладка «План генерации» — список проектов для генерации
на день / неделю / месяц / год с управлением задачами.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from enum import Enum
from typing import List, Optional
from pathlib import Path

from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)


# ── Модель задачи плана ──────────────────────────────────

class PlanPeriod(Enum):
    DAY   = "day"
    WEEK  = "week"
    MONTH = "month"
    YEAR  = "year"


class PlanTaskStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    CANCELLED = "cancelled"


# Абсолютный путь от директории приложения
_APP_DIR = Path(__file__).resolve().parent.parent
PLAN_FILE = _APP_DIR / "generation_plan.json" 


class PlanTask:
    def __init__(
        self,
        task_id: str,
        title: str,
        description: str,
        task_type: str,
        period: str,
        planned_date: str,
        status: str = "pending",
        created_at: str = "",
        completed_at: str = "",
        critique_score: Optional[int] = None,
    ) -> None:
        self.task_id       = task_id
        self.title         = title
        self.description   = description
        self.task_type     = task_type
        self.period        = period
        self.planned_date  = planned_date
        self.status        = status
        self.created_at    = created_at or datetime.utcnow().isoformat()
        self.completed_at  = completed_at
        self.critique_score = critique_score

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "PlanTask":
        return cls(**{k: v for k, v in d.items() if k in cls.__init__.__code__.co_varnames})


class PlanStorage:
    """Хранение плана в JSON-файле."""

    def __init__(self, path: Path = PLAN_FILE) -> None:
        self._path = path

    def load(self) -> List[PlanTask]:
        if not self._path.exists():
            return []
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            return [PlanTask.from_dict(d) for d in data]
        except Exception:
            return []

    def save(self, tasks: List[PlanTask]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in tasks], f, ensure_ascii=False, indent=2)


# ── Диалог добавления задачи ─────────────────────────────

class AddPlanTaskDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("➕ Новая задача в план")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        from PyQt6.QtWidgets import QFormLayout
        form = QFormLayout()

        self._title = QLineEdit()
        self._title.setPlaceholderText("Краткое название проекта")
        form.addRow("Название *:", self._title)

        self._description = QPlainTextEdit()
        self._description.setPlaceholderText("Подробное описание задачи для генерации")
        self._description.setMaximumHeight(100)
        form.addRow("Описание *:", self._description)

        self._task_type = QComboBox()
        self._task_type.addItems(["code", "bot", "android", "course", "script", "debug", "addon", "other"])
        form.addRow("Тип задачи:", self._task_type)

        self._period = QComboBox()
        self._period.addItems(["day", "week", "month", "year"])
        self._period.currentTextChanged.connect(self._on_period_changed)
        form.addRow("Период:", self._period)

        self._date = QDateEdit()
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd.MM.yyyy")
        form.addRow("Запланировать на:", self._date)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_period_changed(self, period: str) -> None:
        today = QDate.currentDate()
        if period == "day":
            self._date.setDate(today)
        elif period == "week":
            self._date.setDate(today.addDays(7))
        elif period == "month":
            self._date.setDate(today.addMonths(1))
        elif period == "year":
            self._date.setDate(today.addYears(1))

    def _accept(self) -> None:
        if not self._title.text().strip() or not self._description.toPlainText().strip():
            return
        self.accept()

    def build_task(self) -> PlanTask:
        import uuid
        return PlanTask(
            task_id     = str(uuid.uuid4()),
            title       = self._title.text().strip(),
            description = self._description.toPlainText().strip(),
            task_type   = self._task_type.currentText(),
            period      = self._period.currentText(),
            planned_date = self._date.date().toString("yyyy-MM-dd"),
        )


# ── Карточка задачи ──────────────────────────────────────

class TaskCard(QFrame):
    run_requested    = pyqtSignal(PlanTask)
    delete_requested = pyqtSignal(str)
    done_toggled     = pyqtSignal(str, bool)

    def __init__(self, task: PlanTask, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.setObjectName("taskCard")
        self._setup_ui()

    def _setup_ui(self) -> None:
        status_colors = {
            "pending":   ("#1c3a5e", "#388bfd"),
            "running":   ("#1a3a1a", "#2ea043"),
            "done":      ("#1a3a1a", "#2ea043"),
            "cancelled": ("#2a1a1a", "#da3633"),
        }
        bg, border = status_colors.get(self.task.status, ("#161b22", "#30363d"))
        self.setStyleSheet(
            f"QFrame#taskCard {{ background: {bg}; border: 1px solid {border}; "
            "border-radius: 8px; padding: 4px; margin: 3px 0; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Заголовок
        top = QHBoxLayout()
        status_icon = {"pending": "⏳", "running": "🔄", "done": "✅", "cancelled": "❌"}.get(
            self.task.status, "❓"
        )
        title_lbl = QLabel(f"{status_icon} {self.task.title}")
        title_lbl.setStyleSheet("color: #e6edf3; font-weight: bold; font-size: 13px;")
        top.addWidget(title_lbl)
        top.addStretch()

        type_lbl = QLabel(f"[{self.task.task_type}]")
        type_lbl.setStyleSheet("color: #388bfd; font-size: 11px;")
        top.addWidget(type_lbl)

        layout.addLayout(top)

        # Описание
        desc_lbl = QLabel(self.task.description[:200] + ("..." if len(self.task.description) > 200 else ""))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(desc_lbl)

        # Метаданные
        meta_row = QHBoxLayout()
        date_lbl = QLabel(f"📅 {self.task.planned_date}")
        date_lbl.setStyleSheet("color: #484f58; font-size: 11px;")
        meta_row.addWidget(date_lbl)

        if self.task.critique_score is not None:
            score_color = "#2ea043" if self.task.critique_score >= 70 else "#f0a030"
            score_lbl = QLabel(f"🔍 {self.task.critique_score}/100")
            score_lbl.setStyleSheet(f"color: {score_color}; font-size: 11px;")
            meta_row.addWidget(score_lbl)

        meta_row.addStretch()

        # Кнопки
        if self.task.status == "pending":
            run_btn = QPushButton("▶ Запустить")
            run_btn.setFixedWidth(100)
            run_btn.setStyleSheet(
                "QPushButton { background: #1c4a8f; color: #e6edf3; border-radius: 4px; padding: 3px 8px; }"
                "QPushButton:hover { background: #388bfd; }"
            )
            run_btn.clicked.connect(lambda: self.run_requested.emit(self.task))
            meta_row.addWidget(run_btn)

        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(32)
        del_btn.setStyleSheet("QPushButton { background: transparent; color: #da3633; border: none; font-size: 13px; }")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.task.task_id))
        meta_row.addWidget(del_btn)

        layout.addLayout(meta_row)


# ── Основной виджет плана ─────────────────────────────────

class GenerationPlanWidget(QWidget):
    """
    Вкладка «План генерации».
    Четыре под-вкладки: день / неделя / месяц / год.
    """

    task_run_requested = pyqtSignal(str, str)  # title, description -> запустить пайплайн

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._storage = PlanStorage()
        self._tasks: List[PlanTask] = []
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Заголовок
        header = QFrame()
        header.setStyleSheet("QFrame { background: #161b22; border-bottom: 1px solid #30363d; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)

        title = QLabel("📅 План генерации проектов")
        title.setStyleSheet("color: #c9d1d9; font-size: 14px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        add_btn = QPushButton("➕ Добавить задачу")
        add_btn.clicked.connect(self._add_task)
        header_layout.addWidget(add_btn)

        clear_done_btn = QPushButton("🧹 Очистить выполненные")
        clear_done_btn.setStyleSheet("QPushButton { color: #8b949e; }")
        clear_done_btn.clicked.connect(self._clear_done)
        header_layout.addWidget(clear_done_btn)

        layout.addWidget(header)

        # Сводка
        self._summary_bar = QFrame()
        self._summary_bar.setStyleSheet("QFrame { background: #0d1117; border-bottom: 1px solid #21262d; }")
        summary_layout = QHBoxLayout(self._summary_bar)
        summary_layout.setContentsMargins(16, 6, 16, 6)

        self._stat_labels: dict[str, QLabel] = {}
        for period, label in [("day", "Сегодня"), ("week", "Неделя"), ("month", "Месяц"), ("year", "Год")]:
            lbl = QLabel(f"{label}: 0")
            lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
            self._stat_labels[period] = lbl
            summary_layout.addWidget(lbl)
            if period != "year":
                sep = QLabel("  |  ")
                sep.setStyleSheet("color: #30363d;")
                summary_layout.addWidget(sep)

        summary_layout.addStretch()
        layout.addWidget(self._summary_bar)

        # Вкладки периодов
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; }"
            "QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 20px; border: none; }"
            "QTabBar::tab:selected { background: #0d1117; color: #e6edf3; border-bottom: 2px solid #388bfd; }"
        )

        self._period_lists: dict[str, QVBoxLayout] = {}
        period_icons = {"day": "📆 Сегодня", "week": "📅 Неделя", "month": "🗓 Месяц", "year": "📊 Год"}

        for period, tab_title in period_icons.items():
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(8, 8, 8, 8)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            container_layout.setSpacing(4)

            scroll.setWidget(container)
            tab_layout.addWidget(scroll)
            self._tabs.addTab(tab, tab_title)
            self._period_lists[period] = container_layout

        layout.addWidget(self._tabs)

    # ── Логика ────────────────────────────────────────────

    def _load(self) -> None:
        self._tasks = self._storage.load()
        self._refresh_all()

    def _save(self) -> None:
        self._storage.save(self._tasks)

    def _refresh_all(self) -> None:
        # Очистить все списки
        for period, container_layout in self._period_lists.items():
            while container_layout.count():
                item = container_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        today = date.today()
        week_end = today + timedelta(days=7)
        month_end = today + timedelta(days=30)
        year_end = today + timedelta(days=365)

        counts = {p: 0 for p in ["day", "week", "month", "year"]}

        for task in self._tasks:
            try:
                task_date = date.fromisoformat(task.planned_date)
            except ValueError:
                task_date = today

            # Определить в какие периоды входит
            periods_to_show = []
            if task_date == today:
                periods_to_show.append("day")
            if task_date <= week_end:
                periods_to_show.append("week")
            if task_date <= month_end:
                periods_to_show.append("month")
            if task_date <= year_end:
                periods_to_show.append("year")

            for period in periods_to_show:
                counts[period] += 1
                card = TaskCard(task)
                card.run_requested.connect(self._on_run_task)
                card.delete_requested.connect(self._on_delete_task)
                self._period_lists[period].addWidget(card)

        # Пустые вкладки
        for period, layout in self._period_lists.items():
            if layout.count() == 0:
                empty_lbl = QLabel(f"Нет задач для этого периода.\nНажмите «➕ Добавить задачу».")
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_lbl.setStyleSheet("color: #484f58; font-size: 13px; padding: 40px;")
                layout.addWidget(empty_lbl)

        # Обновить счётчики
        for period, lbl in self._stat_labels.items():
            period_labels = {"day": "Сегодня", "week": "Неделя", "month": "Месяц", "year": "Год"}
            done = sum(1 for t in self._tasks
                       if t.status == "done" and t.period == period)
            total = counts[period]
            lbl.setText(f"{period_labels[period]}: {done}/{total}")
            lbl.setStyleSheet(
                f"color: {'#2ea043' if done == total and total > 0 else '#8b949e'}; font-size: 12px;"
            )

    def _add_task(self) -> None:
        dlg = AddPlanTaskDialog(self)
        if dlg.exec():
            task = dlg.build_task()
            self._tasks.append(task)
            self._save()
            self._refresh_all()

    def _on_run_task(self, task: PlanTask) -> None:
        task.status = "running"
        self._save()
        self.task_run_requested.emit(task.title, task.description)
        self._refresh_all()

    def _on_delete_task(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.task_id != task_id]
        self._save()
        self._refresh_all()

    def _clear_done(self) -> None:
        self._tasks = [t for t in self._tasks if t.status != "done"]
        self._save()
        self._refresh_all()

    def mark_task_done(self, title: str, score: Optional[int] = None) -> None:
        """Вызывается из MainWindow после завершения пайплайна."""
        for task in self._tasks:
            if task.title == title and task.status == "running":
                task.status = "done"
                task.completed_at = datetime.utcnow().isoformat()
                task.critique_score = score
                break
        self._save()
        self._refresh_all()
