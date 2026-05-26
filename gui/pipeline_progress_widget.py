"""
gui/pipeline_progress_widget.py — PipelineProgressWidget

Информативная панель прогресса генерации: показывает все этапы,
текущий статус, уверенность ИИ, предупреждения, время и краткий итог.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from orchestrator.pipeline_orchestrator import StageResult, StageStatus


# ─────────────────────────── StageRow ────────────────────

class StageRow(QFrame):
    """Одна строка этапа в списке прогресса."""

    COLORS = {
        StageStatus.PENDING:  ("#484f58", "─"),
        StageStatus.RUNNING:  ("#79c0ff", "⟳"),
        StageStatus.DONE:     ("#3fb950", "✅"),
        StageStatus.ERROR:    ("#f85149", "❌"),
        StageStatus.SKIPPED:  ("#6e7681", "⏭"),
        StageStatus.CRITIQUE: ("#d29922", "🔍"),
    }

    STATUS_LABELS = {
        StageStatus.PENDING:  "Ожидает",
        StageStatus.RUNNING:  "Выполняется...",
        StageStatus.DONE:     "Завершён",
        StageStatus.ERROR:    "Ошибка",
        StageStatus.SKIPPED:  "Пропущен",
        StageStatus.CRITIQUE: "Анализ",
    }

    def __init__(self, stage: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self._stage = stage
        self._status = StageStatus.PENDING
        self._started: Optional[datetime] = None
        self._finished: Optional[datetime] = None
        self._setup_ui(label)

    def _setup_ui(self, label: str) -> None:
        self.setFixedHeight(52)
        self.setStyleSheet(
            "QFrame { background: #161b22; border-radius: 6px; border: 1px solid #21262d; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Иконка статуса
        self._icon = QLabel("─")
        self._icon.setFixedWidth(20)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet("font-size: 14px;")
        layout.addWidget(self._icon)

        # Название этапа
        info = QVBoxLayout()
        info.setSpacing(1)
        self._name_label = QLabel(label)
        self._name_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #c9d1d9;")
        self._status_label = QLabel("Ожидает")
        self._status_label.setStyleSheet("font-size: 10px; color: #484f58;")
        info.addWidget(self._name_label)
        info.addWidget(self._status_label)
        layout.addLayout(info, stretch=1)

        # Уверенность ИИ
        self._confidence_label = QLabel("")
        self._confidence_label.setFixedWidth(28)
        self._confidence_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._confidence_label.setToolTip("Уверенность ИИ: 🟢HIGH / 🟡MEDIUM / 🔴LOW")
        layout.addWidget(self._confidence_label)

        # Время
        self._time_label = QLabel("")
        self._time_label.setFixedWidth(52)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._time_label.setStyleSheet("font-size: 10px; color: #484f58;")
        layout.addWidget(self._time_label)

    def set_status(self, status: StageStatus, result: Optional[StageResult] = None) -> None:
        self._status = status
        color, icon = self.COLORS.get(status, ("#484f58", "─"))
        status_text = self.STATUS_LABELS.get(status, "")

        if status == StageStatus.RUNNING:
            self._started = datetime.now()
            self.setStyleSheet(
                "QFrame { background: #1c2a3a; border-radius: 6px; border: 1px solid #388bfd; }"
            )
            self._name_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #79c0ff;")
        elif status == StageStatus.DONE:
            self._finished = datetime.now()
            self.setStyleSheet(
                "QFrame { background: #0f1f12; border-radius: 6px; border: 1px solid #238636; }"
            )
            self._name_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #3fb950;")
        elif status == StageStatus.ERROR:
            self.setStyleSheet(
                "QFrame { background: #2d1212; border-radius: 6px; border: 1px solid #f85149; }"
            )
            self._name_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #f85149;")
        elif status == StageStatus.CRITIQUE:
            self.setStyleSheet(
                "QFrame { background: #1e1a0a; border-radius: 6px; border: 1px solid #d29922; }"
            )
            self._name_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #d29922;")

        self._icon.setText(icon)
        self._icon.setStyleSheet(f"font-size: 14px; color: {color};")

        if result:
            # Итог этапа
            summary = result.summary or ""
            if result.warnings:
                summary += f" ⚠️{len(result.warnings)}"
            self._status_label.setText(summary[:80] if summary else status_text)
            self._status_label.setStyleSheet(f"font-size: 10px; color: {color};")
            # Уверенность
            self._confidence_label.setText(result.confidence_emoji())
            # Время
            if result.duration_sec > 0:
                self._time_label.setText(f"{result.duration_sec:.1f}s")
        else:
            self._status_label.setText(status_text)
            self._status_label.setStyleSheet("font-size: 10px; color: #484f58;")

    def set_running_tick(self, seconds: int) -> None:
        """Обновить счётчик времени во время выполнения."""
        if self._status == StageStatus.RUNNING:
            self._time_label.setText(f"{seconds}s…")


# ─────────────────────── PipelineProgressWidget ──────────

class PipelineProgressWidget(QFrame):
    """
    Полная панель прогресса пайплайна.
    Отображает:
      - Список этапов со статусами
      - Общий прогресс-бар
      - Текущее действие + краткий итог
      - Счётчик токенов и времени
      - Предупреждения
    """

    abort_requested = pyqtSignal()

    _STAGE_LABELS: dict[str, str] = {
        "problem_analysis":                 "🔍 Анализ задачи",
        "user_clarification":               "❓ Уточнение требований",
        "global_spec_and_api":              "📐 Глобальная спецификация",
        "subproject_prompts_generation":    "🗺 Генерация подпроектов",
        "subproject_implementation_trigger":"⚡ Запуск реализации",
        "code_block_generation":            "💻 Генерация кода",
        "optimization":                     "⚡ Оптимизация",
        "unit_tests":                       "🧪 Unit-тесты",
        "deployment_commands":              "🚀 Команды деплоя",
        "readme_generation":                "📝 README",
        "debugging_cli":                    "🐛 Отладка",
        "project_critique":                 "🔍 Анализ и критика",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: Dict[str, StageRow] = {}
        self._stages_order: List[str] = []
        self._start_time: Optional[datetime] = None
        self._token_count = 0
        self._tick_seconds = 0
        self._current_stage: Optional[str] = None
        self._setup_ui()
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)

    def _setup_ui(self) -> None:
        self.setStyleSheet("QFrame { background: #0d1117; border-right: 1px solid #21262d; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)

        # Заголовок
        header = QHBoxLayout()
        title = QLabel("📊 Прогресс генерации")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #e6edf3;")
        header.addWidget(title)
        header.addStretch()
        self._abort_btn = QPushButton("⏹ Стоп")
        self._abort_btn.setObjectName("abortBtn")
        self._abort_btn.setFixedSize(70, 26)
        self._abort_btn.setVisible(False)
        self._abort_btn.clicked.connect(self.abort_requested)
        header.addWidget(self._abort_btn)
        layout.addLayout(header)

        # Общий прогресс-бар
        self._overall_bar = QProgressBar()
        self._overall_bar.setFixedHeight(6)
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setTextVisible(False)
        layout.addWidget(self._overall_bar)

        # Статус строка
        self._status_label = QLabel("Ожидание запуска...")
        self._status_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Счётчики
        counters = QHBoxLayout()
        self._token_label = QLabel("🔤 0 токенов")
        self._token_label.setStyleSheet("font-size: 10px; color: #484f58;")
        self._time_label = QLabel("⏱ 0:00")
        self._time_label.setStyleSheet("font-size: 10px; color: #484f58;")
        counters.addWidget(self._token_label)
        counters.addStretch()
        counters.addWidget(self._time_label)
        layout.addLayout(counters)

        # Разделитель
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("border: 1px solid #21262d;")
        layout.addWidget(line)

        # Прокручиваемый список этапов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._stages_widget = QWidget()
        self._stages_layout = QVBoxLayout(self._stages_widget)
        self._stages_layout.setContentsMargins(0, 0, 0, 0)
        self._stages_layout.setSpacing(4)
        self._stages_layout.addStretch()
        scroll.setWidget(self._stages_widget)
        layout.addWidget(scroll, stretch=1)

        # Предупреждения
        self._warnings_label = QLabel("")
        self._warnings_label.setStyleSheet(
            "color: #d29922; font-size: 10px; background: #1e1a0a; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setVisible(False)
        layout.addWidget(self._warnings_label)

        # Итог / скор критики
        self._result_label = QLabel("")
        self._result_label.setStyleSheet(
            "font-size: 11px; color: #e6edf3; background: #161b22; "
            "border-radius: 4px; padding: 6px 10px;"
        )
        self._result_label.setWordWrap(True)
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)

    # ── Public API ─────────────────────────────────────────

    def init_stages(self, stages: List[str]) -> None:
        """Инициализировать список этапов до начала генерации."""
        self._stages_order = list(stages)
        self._rows.clear()

        # Удалить старые строки
        while self._stages_layout.count() > 1:
            item = self._stages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for s in stages:
            label = self._STAGE_LABELS.get(s, s.replace("_", " ").title())
            row = StageRow(s, label)
            self._rows[s] = row
            idx = self._stages_layout.count() - 1
            self._stages_layout.insertWidget(idx, row)

        self._overall_bar.setValue(0)
        self._warnings_label.setVisible(False)
        self._result_label.setVisible(False)

    def set_stage_status(self, stage: str, status: StageStatus, result: Optional[StageResult] = None) -> None:
        row = self._rows.get(stage)
        if row:
            row.set_status(status, result)

        if status == StageStatus.RUNNING:
            self._current_stage = stage
            label = self._STAGE_LABELS.get(stage, stage)
            self._status_label.setText(f"⟳ {label}...")
            self._status_label.setStyleSheet("color: #79c0ff; font-size: 11px;")
            self._tick_seconds = 0

        elif status in (StageStatus.DONE, StageStatus.ERROR, StageStatus.CRITIQUE):
            done = sum(
                1 for s in self._stages_order
                if self._rows.get(s) and self._rows[s]._status in
                   (StageStatus.DONE, StageStatus.ERROR, StageStatus.SKIPPED, StageStatus.CRITIQUE)
            )
            total = len(self._stages_order)
            pct = int(done / total * 100) if total else 0
            self._overall_bar.setValue(pct)

            if result:
                # Показать предупреждения
                if result.warnings:
                    self._warnings_label.setText(
                        "⚠️ " + " | ".join(result.warnings[:3])
                    )
                    self._warnings_label.setVisible(True)
                else:
                    self._warnings_label.setVisible(False)

                if status == StageStatus.DONE:
                    label = self._STAGE_LABELS.get(stage, stage)
                    confidence = result.confidence_emoji()
                    self._status_label.setText(
                        f"✅ {label} {confidence} — {result.summary[:70]}"
                    )
                    self._status_label.setStyleSheet("color: #3fb950; font-size: 11px;")

                # Критика — показать скор
                if stage == "project_critique" and result.overall_score is not None:
                    score = result.overall_score
                    color = "#3fb950" if score >= 75 else "#d29922" if score >= 50 else "#f85149"
                    self._result_label.setText(
                        f"🔍 Финальная оценка: <b style='color:{color};'>{score}/100</b>  "
                        f"Соответствие: {result.parsed_data.get('compliance_percent', '?')}%"
                    )
                    self._result_label.setVisible(True)

    def add_tokens(self, count: int) -> None:
        self._token_count += count
        self._token_label.setText(f"🔤 ~{self._token_count} токенов")

    def start(self) -> None:
        self._start_time = datetime.now()
        self._token_count = 0
        self._tick_seconds = 0
        self._tick_timer.start()
        self._abort_btn.setVisible(True)

    def stop(self) -> None:
        self._tick_timer.stop()
        self._abort_btn.setVisible(False)
        if self._start_time:
            elapsed = (datetime.now() - self._start_time).seconds
            m, s = divmod(elapsed, 60)
            self._time_label.setText(f"⏱ {m}:{s:02d}")

    def reset(self) -> None:
        self._token_count = 0
        self._tick_seconds = 0
        self._status_label.setText("Ожидание запуска...")
        self._status_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._overall_bar.setValue(0)
        self._warnings_label.setVisible(False)
        self._result_label.setVisible(False)
        self._abort_btn.setVisible(False)

    # ── Internal ──────────────────────────────────────────

    def _on_tick(self) -> None:
        self._tick_seconds += 1
        if self._current_stage and self._current_stage in self._rows:
            self._rows[self._current_stage].set_running_tick(self._tick_seconds)
        if self._start_time:
            elapsed = (datetime.now() - self._start_time).seconds
            m, s = divmod(elapsed, 60)
            self._time_label.setText(f"⏱ {m}:{s:02d}")
