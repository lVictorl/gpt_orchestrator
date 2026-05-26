"""
gui/chat_widget.py — ChatWidget v2

Исправления:
  - Информативные пузырьки: summary, confidence, duration, token count
  - StageSummaryBubble для итогов этапа
  - CritiqueBubble для финального анализа
  - Стриминг работает корректно (нет дублирования)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
)


# ─────────────── MessageBubble ────────────────────────────

class MessageBubble(QFrame):
    def __init__(
        self,
        role: str,
        content: str,
        stage: str = "",
        timestamp: Optional[datetime] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._role = role
        self._content = content
        self._stage = stage
        self._ts = timestamp or datetime.now()
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 3, 8, 3)

        if self._role == "system":
            label = QLabel(f"  {self._content}")
            label.setWordWrap(True)
            label.setStyleSheet(
                "color: #8b949e; font-size: 11px; padding: 4px 12px; "
                "background: #161b22; border-left: 3px solid #30363d; border-top-left-radius:0px;border-top-right-radius:6px;border-bottom-right-radius:6px;border-bottom-left-radius:0px"
            )
            outer.addWidget(label)
            return

        bubble = QFrame()
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        bubble_layout.setSpacing(4)

        # Метаданные сверху
        meta_row = QHBoxLayout()
        if self._stage:
            stage_lbl = QLabel(f"[{self._stage}]")
            stage_lbl.setStyleSheet("color: #388bfd; font-size: 10px;")
            meta_row.addWidget(stage_lbl)
        meta_row.addStretch()
        ts_lbl = QLabel(self._ts.strftime("%H:%M:%S"))
        ts_lbl.setStyleSheet("color: #484f58; font-size: 10px;")
        meta_row.addWidget(ts_lbl)
        copy_btn = QPushButton("⎘")
        copy_btn.setFixedSize(20, 20)
        copy_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#484f58;border:none;font-size:11px}"
            "QPushButton:hover{color:#c9d1d9}"
        )
        copy_btn.clicked.connect(self._copy_content)
        meta_row.addWidget(copy_btn)
        bubble_layout.addLayout(meta_row)

        # Текст
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._text_edit.setPlainText(self._content)

        if self._role == "user":
            bubble.setStyleSheet(
                "QFrame{background:#1c4a8f;border-top-left-radius:12px;border-top-right-radius:12px;border-bottom-right-radius:2px;border-bottom-left-radius:12px}"
            )
            self._text_edit.setStyleSheet(
                "QTextEdit{background:transparent;color:#e6edf3;border:none;font-size:13px}"
            )
        else:
            bubble.setStyleSheet(
                "QFrame{background:#161b22;border:1px solid #30363d;border-top-left-radius:12px;border-top-right-radius:12px;border-bottom-right-radius:12px;border-bottom-left-radius:2px}"
            )
            self._text_edit.setStyleSheet(
                "QTextEdit{background:transparent;color:#c9d1d9;border:none;font-size:13px}"
            )

        bubble_layout.addWidget(self._text_edit)
        bubble.setMaximumWidth(760)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        if self._role == "user":
            outer.addStretch()
            outer.addWidget(bubble)
        else:
            outer.addWidget(bubble)
            outer.addStretch()

    def append_text(self, text: str) -> None:
        self._content += text
        if hasattr(self, "_text_edit"):
            cursor = self._text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertText(text)
            self._text_edit.ensureCursorVisible()

    def _copy_content(self) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._content)


class StageSummaryBubble(QFrame):
    """Информативный блок итогов этапа пайплайна."""

    def __init__(
        self,
        stage: str,
        summary: str,
        confidence: str = "HIGH",
        status: str = "OK",
        warnings: list | None = None,
        duration: float = 0.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stageSummary")
        conf_icon = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(confidence, "⚪")
        status_icon = {"OK": "✅", "WARN": "⚠️", "ERROR": "❌", "PARTIAL": "🔶"}.get(status, "")
        color = {
            "OK": "#1a3a1a",
            "WARN": "#3a2e00",
            "ERROR": "#2a0d0d",
            "PARTIAL": "#2a2000",
        }.get(status, "#161b22")
        border = {"OK": "#2ea043", "WARN": "#d29922", "ERROR": "#da3633", "PARTIAL": "#e3b341"}.get(status, "#30363d")

        self.setStyleSheet(
            f"QFrame#stageSummary{{"
            f"background:{color};"
            f"border-left:4px solid {border};"
            "padding:2px;"
            "margin:2px 8px;"
            "border-top-left-radius:0px;"
            "border-top-right-radius:4px;"
            "border-bottom-right-radius:4px;"
            "border-bottom-left-radius:0px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)

        # Заголовок
        header = QHBoxLayout()
        stage_labels = {
            "problem_analysis": "📋 Анализ задачи",
            "user_clarification": "❓ Уточнение",
            "architecture_analysis": "🏛 Архитектура",
            "project_plan": "📅 План",
            "global_spec_and_api": "📐 Спецификация",
            "subproject_prompts_generation": "🧩 Промпты",
            "subproject_implementation_trigger": "⚡ Запуск реализации",
            "code_block_generation": "💻 Код",
            "optimization": "⚙️ Оптимизация",
            "unit_tests": "🧪 Тесты",
            "refactoring": "♻️ Рефакторинг",
            "deployment_commands": "🚀 Деплой",
            "debugging_cli": "🐛 Отладка",
            "readme_generation": "📖 README",
            "project_critique": "🔍 Критика проекта",
        }
        stage_lbl = QLabel(f"{status_icon} {stage_labels.get(stage, stage)}")
        stage_lbl.setStyleSheet("color:#e6edf3;font-weight:bold;font-size:12px")
        header.addWidget(stage_lbl)
        header.addStretch()
        header.addWidget(QLabel(f"{conf_icon}"))
        if duration > 0:
            dur_lbl = QLabel(f" {duration:.1f}с")
            dur_lbl.setStyleSheet("color:#484f58;font-size:10px")
            header.addWidget(dur_lbl)
        layout.addLayout(header)

        # Summary
        if summary:
            sum_lbl = QLabel(summary)
            sum_lbl.setWordWrap(True)
            sum_lbl.setStyleSheet("color:#8b949e;font-size:12px")
            layout.addWidget(sum_lbl)

        # Warnings
        if warnings:
            for w in warnings:
                w_lbl = QLabel(f"⚠️ {w}")
                w_lbl.setWordWrap(True)
                w_lbl.setStyleSheet("color:#d29922;font-size:11px")
                layout.addWidget(w_lbl)


class CritiqueBubble(QFrame):
    """Визуальный блок итогового отчёта критики проекта."""

    def __init__(
        self,
        score: int,
        compliance: int,
        summary: str,
        grades: dict,
        strengths: list,
        weaknesses: list,
        recommendations: list,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("critiqueBubble")
        score_color = "#2ea043" if score >= 70 else "#d29922" if score >= 50 else "#da3633"
        self.setStyleSheet(
            f"QFrame#critiqueBubble{{background:#0d1117;border:2px solid {score_color};"
            "border-radius:10px;padding:4px;margin:8px;}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Заголовок
        title = QLabel("🔍 ФИНАЛЬНАЯ КРИТИКА ПРОЕКТА")
        title.setStyleSheet(f"color:{score_color};font-size:15px;font-weight:bold;")
        layout.addWidget(title)

        # Общий балл
        score_row = QHBoxLayout()
        score_lbl = QLabel(str(score))
        score_lbl.setStyleSheet(f"color:{score_color};font-size:40px;font-weight:bold;")
        score_row.addWidget(score_lbl)
        score_row.addWidget(QLabel("/100"))
        score_row.addSpacing(16)
        comp_lbl = QLabel(f"✅ Соответствие заданию: {compliance}%")
        comp_lbl.setStyleSheet("color:#8b949e;font-size:13px;")
        score_row.addWidget(comp_lbl)
        score_row.addStretch()
        layout.addLayout(score_row)

        # Вердикт
        summary_lbl = QLabel(summary)
        summary_lbl.setWordWrap(True)
        summary_lbl.setStyleSheet("color:#c9d1d9;font-size:13px;font-style:italic;")
        layout.addWidget(summary_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#30363d")
        layout.addWidget(sep)

        # Оценки
        if grades:
            grades_lbl = QLabel("Оценки по критериям:")
            grades_lbl.setStyleSheet("color:#8b949e;font-size:11px;")
            layout.addWidget(grades_lbl)
            grade_names = {
                "architecture": "Архитектура",
                "code_quality": "Код",
                "test_coverage": "Тесты",
                "documentation": "Документация",
                "security": "Безопасность",
                "performance": "Производительность",
                "completeness": "Полнота",
            }
            for key, name in grade_names.items():
                val = grades.get(key, 0)
                bar_color = "#2ea043" if val >= 7 else "#d29922" if val >= 4 else "#da3633"
                filled = "█" * val + "░" * (10 - val)
                row = QLabel(f"  {name:22s} [{filled}] {val}/10")
                row.setStyleSheet(
                    f"color:{bar_color};font-size:11px;font-family:monospace;"
                )
                layout.addWidget(row)

        # Сильные стороны
        if strengths:
            s_lbl = QLabel("✅ Сильные стороны:")
            s_lbl.setStyleSheet("color:#2ea043;font-size:12px;font-weight:bold;")
            layout.addWidget(s_lbl)
            for s in strengths[:4]:
                layout.addWidget(QLabel(f"  • {s}"))

        # Слабые стороны
        if weaknesses:
            w_lbl = QLabel("⚠️ Слабые стороны:")
            w_lbl.setStyleSheet("color:#d29922;font-size:12px;font-weight:bold;")
            layout.addWidget(w_lbl)
            for w in weaknesses[:4]:
                layout.addWidget(QLabel(f"  • {w}"))

        # Рекомендации
        if recommendations:
            r_lbl = QLabel("💡 Рекомендации:")
            r_lbl.setStyleSheet("color:#388bfd;font-size:12px;font-weight:bold;")
            layout.addWidget(r_lbl)
            for r in recommendations[:4]:
                layout.addWidget(QLabel(f"  → {r}"))


# ─────────────── ChatWidget ───────────────────────────────

class ChatWidget(QWidget):
    message_submitted = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._bubbles: list = []
        self._streaming_bubble: Optional[MessageBubble] = None
        self._streaming_stage: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._messages_widget = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._messages_layout.setSpacing(2)
        self._messages_layout.setContentsMargins(8, 8, 8, 8)
        self._messages_layout.addStretch()

        self._scroll.setWidget(self._messages_widget)
        layout.addWidget(self._scroll, stretch=1)

        # Поле ввода
        input_frame = QFrame()
        input_frame.setStyleSheet(
            "QFrame{background:#161b22;border-top:1px solid #30363d;}"
        )
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(8)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText(
            "Опишите задачу... (Enter — отправить, Shift+Enter — новая строка)"
        )
        self._input.setMaximumHeight(120)
        self._input.setMinimumHeight(60)
        self._input.keyPressEvent = self._input_key_press

        btn_row = QHBoxLayout()
        self._char_counter = QLabel("0 символов")
        self._char_counter.setStyleSheet("color:#484f58;font-size:11px;")
        self._input.textChanged.connect(
            lambda: self._char_counter.setText(f"{len(self._input.toPlainText())} символов")
        )

        self._send_btn = QPushButton("▶ Запустить")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.clicked.connect(self._on_send)
        self._send_btn.setFixedWidth(130)

        self._abort_btn = QPushButton("⏹ Стоп")
        self._abort_btn.setObjectName("abortBtn")
        self._abort_btn.setVisible(False)
        self._abort_btn.setFixedWidth(80)

        btn_row.addWidget(self._char_counter)
        btn_row.addStretch()
        btn_row.addWidget(self._abort_btn)
        btn_row.addWidget(self._send_btn)

        input_layout.addWidget(self._input)
        input_layout.addLayout(btn_row)
        layout.addWidget(input_frame)

    # ── Public API ─────────────────────────────────────────

    def add_message(
        self,
        role: str,
        content: str,
        stage: str = "",
        timestamp: Optional[datetime] = None,
    ) -> MessageBubble:
        bubble = MessageBubble(role, content, stage, timestamp)
        self._insert_widget(bubble)
        self._bubbles.append(bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)
        return bubble

    def add_stage_marker(self, stage: str, label: str) -> None:
        bubble = MessageBubble("system", label, stage)
        self._insert_widget(bubble)
        self._bubbles.append(bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_stage_summary(
        self,
        stage: str,
        summary: str,
        confidence: str = "HIGH",
        status: str = "OK",
        warnings: list | None = None,
        duration: float = 0.0,
    ) -> None:
        """Добавить информативную плашку итогов этапа."""
        bubble = StageSummaryBubble(stage, summary, confidence, status, warnings, duration)
        self._insert_widget(bubble)
        self._bubbles.append(bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_critique(
        self,
        score: int,
        compliance: int,
        summary: str,
        grades: dict,
        strengths: list,
        weaknesses: list,
        recommendations: list,
    ) -> None:
        """Добавить блок финальной критики проекта."""
        bubble = CritiqueBubble(
            score, compliance, summary, grades, strengths, weaknesses, recommendations
        )
        self._insert_widget(bubble)
        self._bubbles.append(bubble)
        QTimer.singleShot(100, self._scroll_to_bottom)

    def start_streaming_bubble(self, stage: str = "") -> MessageBubble:
        if self._streaming_bubble and self._streaming_stage == stage:
            return self._streaming_bubble
        self.finish_streaming()
        bubble = self.add_message("assistant", "", stage)
        self._streaming_bubble = bubble
        self._streaming_stage = stage
        return bubble

    def append_token(self, token: str) -> None:
        if self._streaming_bubble:
            self._streaming_bubble.append_text(token)
            QTimer.singleShot(0, self._scroll_to_bottom)

    def finish_streaming(self) -> None:
        self._streaming_bubble = None
        self._streaming_stage = ""

    def clear_messages(self) -> None:
        for b in self._bubbles:
            b.deleteLater()
        self._bubbles.clear()
        self._streaming_bubble = None
        self._streaming_stage = ""

    def set_running(self, running: bool) -> None:
        self._send_btn.setVisible(not running)
        self._abort_btn.setVisible(running)
        self._input.setReadOnly(running)

    # ── Internal ──────────────────────────────────────────

    def _insert_widget(self, widget: QWidget) -> None:
        pos = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(pos, widget)

    def _on_send(self) -> None:
        text = self._input.toPlainText().strip()
        if text:
            self.add_message("user", text)
            self._input.clear()
            self.message_submitted.emit(text)

    def _input_key_press(self, event) -> None:
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self._on_send()
        else:
            QPlainTextEdit.keyPressEvent(self._input, event)

    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
