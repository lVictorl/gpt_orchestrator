"""
gui/pipeline_panel.py — PipelinePanel

Информативная панель прогресса пайплайна.
Показывает:
  - Дерево всех этапов с иконками статусов
  - Для каждого завершённого этапа: summary, confidence, warnings, duration
  - Финальный critique score с оценками по критериям
  - Живой счётчик токенов
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar,
    QScrollArea, QSizePolicy, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from orchestrator.pipeline_orchestrator import StageResult, StageStatus


# ── Иконки статусов ────────────────────────────────────────

_STATUS_ICON = {
    StageStatus.PENDING:  "⬜",
    StageStatus.RUNNING:  "🔄",
    StageStatus.DONE:     "✅",
    StageStatus.ERROR:    "❌",
    StageStatus.SKIPPED:  "⏭️",
    StageStatus.CRITIQUE: "🔍",
}

_CONF_ICON = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}

_STAGE_LABELS = {
    "problem_analysis":                "📋 Анализ задачи",
    "user_clarification":              "❓ Уточнение требований",
    "architecture_analysis":           "🏛 Архитектура",
    "project_plan":                    "📅 План проекта",
    "global_spec_and_api":             "📐 Глобальная спецификация",
    "subproject_prompts_generation":   "🧩 Генерация промптов",
    "subproject_implementation_trigger":"⚡ Запуск реализации",
    "code_block_generation":           "💻 Генерация кода",
    "fix_errors":                      "🔧 Исправление ошибок",
    "fix_tests":                       "🩹 Исправление тестов",
    "optimization":                    "⚙️ Оптимизация",
    "unit_tests":                      "🧪 Тесты",
    "refactoring":                     "♻️ Рефакторинг",
    "deployment_commands":             "🚀 Деплой",
    "debugging_cli":                   "🐛 Отладка",
    "readme_generation":               "📖 README",
    "generate_spec":                   "📄 Спецификация",
    "git_commit":                      "📦 Git коммит",
    "project_metadata":                "🗂 Метаданные проекта",
    "project_critique":                "🔍 Критика проекта",
}


class StageRow(QFrame):
    """Строка одного этапа в дереве пайплайна."""

    def __init__(self, stage: str, parent=None) -> None:
        super().__init__(parent)
        self.stage = stage
        self._status = StageStatus.PENDING
        self._result: Optional[StageResult] = None
        self._expanded = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("stageRow")
        self.setStyleSheet(
            "QFrame#stageRow { background: #161b22; border: 1px solid #21262d; "
            "border-radius: 6px; margin: 2px 0; }"
        )
        main = QVBoxLayout(self)
        main.setContentsMargins(10, 6, 10, 6)
        main.setSpacing(4)

        # Заголовок строки
        header = QHBoxLayout()
        self._icon_lbl = QLabel("⬜")
        self._icon_lbl.setFixedWidth(22)
        self._name_lbl = QLabel(_STAGE_LABELS.get(self.stage, self.stage))
        self._name_lbl.setStyleSheet("color: #c9d1d9; font-weight: bold;")

        self._conf_lbl = QLabel("")
        self._conf_lbl.setFixedWidth(20)

        self._dur_lbl  = QLabel("")
        self._dur_lbl.setStyleSheet("color: #484f58; font-size: 11px;")

        self._expand_btn = QToolButton()
        self._expand_btn.setText("▶")
        self._expand_btn.setStyleSheet(
            "QToolButton { background: transparent; color: #484f58; border: none; font-size: 10px; }"
        )
        self._expand_btn.setVisible(False)
        self._expand_btn.clicked.connect(self._toggle_expand)

        header.addWidget(self._icon_lbl)
        header.addWidget(self._name_lbl)
        header.addStretch()
        header.addWidget(self._conf_lbl)
        header.addWidget(self._dur_lbl)
        header.addWidget(self._expand_btn)
        main.addLayout(header)

        # Блок деталей (скрыт по умолчанию)
        self._detail_frame = QFrame()
        self._detail_frame.setVisible(False)
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(22, 0, 0, 4)
        detail_layout.setSpacing(3)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        detail_layout.addWidget(self._summary_lbl)

        self._warnings_lbl = QLabel("")
        self._warnings_lbl.setWordWrap(True)
        self._warnings_lbl.setStyleSheet("color: #f0a030; font-size: 11px;")
        self._warnings_lbl.setVisible(False)
        detail_layout.addWidget(self._warnings_lbl)

        main.addWidget(self._detail_frame)

    def set_status(self, status: StageStatus) -> None:
        self._status = status
        self._icon_lbl.setText(_STATUS_ICON.get(status, "❓"))
        if status == StageStatus.RUNNING:
            self.setStyleSheet(
                "QFrame#stageRow { background: #0d2137; border: 1px solid #388bfd; "
                "border-radius: 6px; margin: 2px 0; }"
            )
        elif status in (StageStatus.DONE, StageStatus.CRITIQUE):
            self.setStyleSheet(
                "QFrame#stageRow { background: #0d1f12; border: 1px solid #2ea043; "
                "border-radius: 6px; margin: 2px 0; }"
            )
        elif status == StageStatus.FIXING:
            self.setStyleSheet(
                "QFrame#stageRow { background: #1f1a00; border: 1px solid #d29922; "
                "border-radius: 6px; margin: 2px 0; }"
            )
        elif status == StageStatus.ERROR:
            self.setStyleSheet(
                "QFrame#stageRow { background: #1f0d0d; border: 1px solid #da3633; "
                "border-radius: 6px; margin: 2px 0; }"
            )

    def set_result(self, result: StageResult) -> None:
        self._result = result
        self._conf_lbl.setText(_CONF_ICON.get(result.confidence, ""))
        self._dur_lbl.setText(f"{result.duration_sec:.1f}с")

        if result.summary:
            self._summary_lbl.setText(result.summary)
            self._expand_btn.setVisible(True)

        if result.warnings:
            self._warnings_lbl.setText("⚠️ " + " | ".join(result.warnings))
            self._warnings_lbl.setVisible(True)
            self._expand_btn.setVisible(True)

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        self._detail_frame.setVisible(self._expanded)
        self._expand_btn.setText("▼" if self._expanded else "▶")


class CritiqueWidget(QFrame):
    """Виджет финального анализа проекта с оценками по критериям."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("critiqueWidget")
        self.setStyleSheet(
            "QFrame#critiqueWidget { background: #0d1117; border: 2px solid #388bfd; "
            "border-radius: 10px; padding: 8px; }"
        )
        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("🔍 Финальный анализ проекта")
        title.setStyleSheet("color: #388bfd; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # Общий балл
        score_row = QHBoxLayout()
        self._score_lbl = QLabel("—")
        self._score_lbl.setStyleSheet(
            "color: #2ea043; font-size: 28px; font-weight: bold;"
        )
        self._compliance_lbl = QLabel("")
        self._compliance_lbl.setStyleSheet("color: #c9d1d9; font-size: 13px;")
        score_row.addWidget(self._score_lbl)
        score_row.addWidget(QLabel("/100"))
        score_row.addSpacing(20)
        score_row.addWidget(self._compliance_lbl)
        score_row.addStretch()
        layout.addLayout(score_row)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(self._summary_lbl)

        # Решётка оценок
        grades_label = QLabel("Оценки по критериям:")
        grades_label.setStyleSheet("color: #c9d1d9; font-size: 12px;")
        layout.addWidget(grades_label)

        self._grades_widget = QWidget()
        grades_layout = QVBoxLayout(self._grades_widget)
        grades_layout.setSpacing(4)
        grades_layout.setContentsMargins(0, 0, 0, 0)

        self._grade_bars: Dict[str, tuple] = {}  # (QProgressBar, QLabel)
        _criteria = [
            ("architecture",  "Архитектура"),
            ("code_quality",  "Качество кода"),
            ("test_coverage", "Тесты"),
            ("documentation", "Документация"),
            ("security",      "Безопасность"),
            ("performance",   "Производительность"),
            ("completeness",  "Полнота реализации"),
        ]
        for key, label in _criteria:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(180)
            lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
            bar = QProgressBar()
            bar.setRange(0, 10)
            bar.setValue(0)
            bar.setFixedHeight(14)
            bar.setStyleSheet(
                "QProgressBar { background: #21262d; border-radius: 4px; text-align: center; }"
                "QProgressBar::chunk { background: #2ea043; border-radius: 4px; }"
            )
            val_lbl = QLabel("0/10")
            val_lbl.setFixedWidth(35)
            val_lbl.setStyleSheet("color: #c9d1d9; font-size: 11px;")
            row.addWidget(lbl)
            row.addWidget(bar)
            row.addWidget(val_lbl)
            grades_layout.addLayout(row)
            self._grade_bars[key] = (bar, val_lbl)

        layout.addWidget(self._grades_widget)

        # Рекомендации
        self._recommendations_lbl = QLabel("")
        self._recommendations_lbl.setWordWrap(True)
        self._recommendations_lbl.setStyleSheet("color: #c9d1d9; font-size: 11px;")
        layout.addWidget(self._recommendations_lbl)

    def populate(self, result: StageResult) -> None:
        self.setVisible(True)
        data = result.parsed_data

        score = data.get("overall_score", 0)
        color = "#2ea043" if score >= 70 else "#f0a030" if score >= 50 else "#da3633"
        self._score_lbl.setText(str(score))
        self._score_lbl.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: bold;")

        compliance = data.get("compliance_percent", 0)
        self._compliance_lbl.setText(f"Соответствие заданию: {compliance}%")
        self._summary_lbl.setText(result.summary)

        grades = data.get("grades", {})
        for key, (bar, val_lbl) in self._grade_bars.items():
            v = grades.get(key, 0)
            bar.setValue(v)
            val_lbl.setText(f"{v}/10")
            chunk_color = "#2ea043" if v >= 7 else "#f0a030" if v >= 4 else "#da3633"
            bar.setStyleSheet(
                "QProgressBar { background: #21262d; border-radius: 4px; }"
                f"QProgressBar::chunk {{ background: {chunk_color}; border-radius: 4px; }}"
            )

        recs = data.get("recommendations", [])
        if recs:
            self._recommendations_lbl.setText(
                "💡 Рекомендации:\n" + "\n".join(f"• {r}" for r in recs[:5])
            )

        critical = data.get("critical_issues", [])
        if critical:
            issues_text = "❗ Критические проблемы:\n" + "\n".join(f"• {i}" for i in critical)
            issues_lbl = QLabel(issues_text)
            issues_lbl.setWordWrap(True)
            issues_lbl.setStyleSheet("color: #da3633; font-size: 11px;")
            self.layout().addWidget(issues_lbl)


class PipelinePanel(QWidget):
    """
    Боковая панель с подробным прогрессом пайплайна.
    Показывает все этапы, их статусы и детали в реальном времени.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stage_rows: Dict[str, StageRow] = {}
        self._token_count = 0
        self._total_stages = 0
        self._current_stage = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Заголовок
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: #161b22; border-bottom: 1px solid #30363d; }"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(6)

        title = QLabel("📊 Прогресс генерации")
        title.setStyleSheet("color: #c9d1d9; font-size: 13px; font-weight: bold;")
        header_layout.addWidget(title)

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setFixedHeight(8)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.setStyleSheet(
            "QProgressBar { background: #21262d; border-radius: 4px; }"
            "QProgressBar::chunk { background: #388bfd; border-radius: 4px; }"
        )
        header_layout.addWidget(self._overall_bar)

        stats_row = QHBoxLayout()
        self._stage_counter_lbl = QLabel("0 / 0 этапов")
        self._stage_counter_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._token_lbl = QLabel("0 токенов")
        self._token_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._elapsed_lbl = QLabel("")
        self._elapsed_lbl.setStyleSheet("color: #484f58; font-size: 11px;")
        stats_row.addWidget(self._stage_counter_lbl)
        stats_row.addStretch()
        stats_row.addWidget(self._token_lbl)
        header_layout.addLayout(stats_row)
        header_layout.addWidget(self._elapsed_lbl)

        layout.addWidget(header)

        # Скролл с этапами
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #0d1117; }")

        self._stages_container = QWidget()
        self._stages_layout = QVBoxLayout(self._stages_container)
        self._stages_layout.setContentsMargins(8, 8, 8, 8)
        self._stages_layout.setSpacing(2)
        self._stages_layout.addStretch()

        scroll.setWidget(self._stages_container)
        layout.addWidget(scroll, stretch=1)

        # Critique widget
        self._critique_widget = CritiqueWidget()
        layout.addWidget(self._critique_widget)

        # Таймер прошедшего времени
        self._start_time: Optional[datetime] = None
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_elapsed)

    # ── Public API ─────────────────────────────────────────

    def init_stages(self, stages: list[str]) -> None:
        """Инициализировать список этапов до начала генерации."""
        # Очистить
        for row in self._stage_rows.values():
            row.deleteLater()
        self._stage_rows.clear()

        self._total_stages = len(stages)
        self._token_count = 0
        self._current_stage = 0
        self._overall_bar.setValue(0)
        self._stage_counter_lbl.setText(f"0 / {self._total_stages} этапов")
        self._critique_widget.setVisible(False)
        self._start_time = datetime.utcnow()
        self._timer.start(1000)

        # Добавить строки
        insert_pos = self._stages_layout.count() - 1
        for stage in stages:
            row = StageRow(stage)
            self._stages_layout.insertWidget(insert_pos, row)
            self._stage_rows[stage] = row
            insert_pos += 1

    def on_stage_status(self, stage: str, status: StageStatus) -> None:
        if stage in self._stage_rows:
            self._stage_rows[stage].set_status(status)
        if status == StageStatus.RUNNING:
            self._current_stage = list(self._stage_rows.keys()).index(stage) + 1
            self._update_progress()

    def on_stage_result(self, stage: str, result: StageResult) -> None:
        if stage in self._stage_rows:
            self._stage_rows[stage].set_result(result)
        self._update_progress()
        if stage == "project_critique":
            self._critique_widget.populate(result)
            self._timer.stop()

    def on_token(self, stage: str, token: str) -> None:
        self._token_count += 1
        if self._token_count % 10 == 0:
            self._token_lbl.setText(f"~{self._token_count} токенов")

    def on_pipeline_done(self) -> None:
        self._overall_bar.setValue(100)
        self._overall_bar.setStyleSheet(
            "QProgressBar { background: #21262d; border-radius: 4px; }"
            "QProgressBar::chunk { background: #2ea043; border-radius: 4px; }"
        )
        self._stage_counter_lbl.setText(f"{self._total_stages} / {self._total_stages} этапов ✅")
        self._timer.stop()

    def on_pipeline_error(self) -> None:
        self._timer.stop()

    def update_token_count(self, total_tokens: int) -> None:
        """Обновить счётчик токенов реальными данными из оркестратора."""
        self._token_count = total_tokens
        self._token_lbl.setText(f"~{total_tokens:,} токенов")

    def reset(self) -> None:
        for row in self._stage_rows.values():
            row.deleteLater()
        self._stage_rows.clear()
        self._token_count = 0
        self._overall_bar.setValue(0)
        self._stage_counter_lbl.setText("0 / 0 этапов")
        self._token_lbl.setText("0 токенов")
        self._elapsed_lbl.setText("")
        self._critique_widget.setVisible(False)

    # ── Internals ─────────────────────────────────────────

    def _update_progress(self) -> None:
        done = sum(
            1 for row in self._stage_rows.values()
            if row._status in (StageStatus.DONE, StageStatus.ERROR, StageStatus.CRITIQUE)
        )
        total = self._total_stages
        pct = int(done / total * 100) if total else 0
        self._overall_bar.setValue(pct)
        self._stage_counter_lbl.setText(f"{done} / {total} этапов")

    def _update_elapsed(self) -> None:
        if self._start_time:
            delta = datetime.utcnow() - self._start_time
            m, s = divmod(int(delta.total_seconds()), 60)
            self._elapsed_lbl.setText(f"⏱ {m:02d}:{s:02d}")
