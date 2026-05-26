"""
gui/clarification_widget.py — ClarificationPanel v2

Shows a wizard-style form for user clarification questions.
Appears inline below the chat when AI asks clarifying questions.
Designed to match the style of ProjectWizardDialog.
"""
from __future__ import annotations

from typing import Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)


class QuestionField(QWidget):
    """Single question with its answer field."""

    def __init__(self, question: dict, index: int, parent=None) -> None:
        super().__init__(parent)
        self._question = question
        self._qid = question.get("id", f"q{index}")
        self._setup_ui(index)

    def _setup_ui(self, index: int) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(4)

        # Question label
        q_text = self._question.get("question", "")
        hint   = self._question.get("hint", "")

        q_row = QHBoxLayout()
        num = QLabel(f"{index + 1}.")
        num.setFixedWidth(28)
        num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        num.setStyleSheet(
            "color:#388bfd; font-weight:bold; font-size:12px; padding-top:2px;"
        )
        q_row.addWidget(num)

        q_lbl = QLabel(q_text)
        q_lbl.setWordWrap(True)
        q_lbl.setStyleSheet("color:#e6edf3; font-size:13px; font-weight:bold;")
        q_row.addWidget(q_lbl, stretch=1)
        layout.addLayout(q_row)

        if hint:
            h_lbl = QLabel(f"💡 {hint}")
            h_lbl.setWordWrap(True)
            h_lbl.setStyleSheet(
                "color:#8b949e; font-size:11px; padding-left:34px;"
            )
            layout.addWidget(h_lbl)

        # Answer input
        default = self._question.get("default", "")
        options = self._question.get("options", [])

        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(34, 0, 0, 0)
        input_layout.setSpacing(4)

        if options:
            # Option buttons + text field
            opts_row = QHBoxLayout()
            self._answer = QLineEdit()
            self._answer.setText(default or (options[0] if options else ""))
            self._answer.setStyleSheet(
                "QLineEdit{"
                "background:#0d1117; color:#e6edf3;"
                "border:1px solid #30363d; border-radius:4px;"
                "padding:6px 10px; font-size:13px;"
                "}"
                "QLineEdit:focus{border-color:#388bfd;}"
            )
            for opt in options:
                btn = QPushButton(opt)
                btn.setFixedHeight(28)
                btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                btn.setStyleSheet(
                    "QPushButton{"
                    "background:#21262d; color:#c9d1d9;"
                    "border:1px solid #30363d; border-radius:4px; padding:2px 8px;"
                    "}"
                    "QPushButton:hover{background:#388bfd; color:#fff; border-color:#388bfd;}"
                )
                btn.clicked.connect(lambda _, o=opt: self._answer.setText(o))
                opts_row.addWidget(btn)
            opts_row.addStretch()
            input_layout.addLayout(opts_row)
            input_layout.addWidget(self._answer)
        else:
            self._answer = QLineEdit()
            if default:
                self._answer.setText(default)
            self._answer.setPlaceholderText("Введите ответ...")
            self._answer.setStyleSheet(
                "QLineEdit{"
                "background:#0d1117; color:#e6edf3;"
                "border:1px solid #30363d; border-radius:4px;"
                "padding:6px 10px; font-size:13px;"
                "}"
                "QLineEdit:focus{border-color:#388bfd;}"
            )
            input_layout.addWidget(self._answer)

        layout.addWidget(input_container)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color:#21262d; max-height:1px; margin-top:4px;")
        layout.addWidget(sep)

    @property
    def question_id(self) -> str:
        return self._qid

    @property
    def answer(self) -> str:
        return self._answer.text().strip()


class ClarificationPanel(QWidget):
    """
    Inline clarification form embedded below the chat.
    Shown when the AI generates clarifying questions.
    Hidden after the user submits answers.
    """

    answers_submitted = pyqtSignal(dict)  # {question_id: answer}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fields: List[QuestionField] = []
        self._setup_ui()
        self.setVisible(False)
        self.setMaximumHeight(500)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setStyleSheet(
            "QFrame{background:#0d2137; border-top:2px solid #388bfd; padding:0;}"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)

        icon_lbl = QLabel("❓")
        icon_lbl.setStyleSheet("font-size:18px;")
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title = QLabel("Уточняющие вопросы от ИИ")
        title.setStyleSheet("color:#388bfd; font-size:14px; font-weight:bold;")
        subtitle = QLabel(
            "Ответьте на вопросы ниже — это поможет создать более точный результат. "
            "Генерация продолжится после отправки ответов."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#8b949e; font-size:11px;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col, stretch=1)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(
            "color:#388bfd; font-size:11px; font-weight:bold;"
            "background:#0a1929; border-radius:10px; padding:2px 8px;"
        )
        header_layout.addWidget(self._count_lbl)
        layout.addWidget(header)

        # Scrollable question area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:#0d1117;}")

        self._container = QWidget()
        self._container.setStyleSheet("background:#0d1117;")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(16, 12, 16, 8)
        self._container_layout.setSpacing(0)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

        # Footer with buttons
        footer = QFrame()
        footer.setStyleSheet(
            "QFrame{background:#161b22; border-top:1px solid #30363d;}"
        )
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.setSpacing(10)

        self._submit_btn = QPushButton("✅  Отправить ответы и продолжить")
        self._submit_btn.setStyleSheet(
            "QPushButton{"
            "background:#1a4a1a; color:#2ea043;"
            "border:1px solid #2ea043; border-radius:6px;"
            "padding:8px 24px; font-weight:bold; font-size:13px;"
            "}"
            "QPushButton:hover{background:#2ea043; color:#fff;}"
        )
        self._submit_btn.clicked.connect(self._submit)

        skip_btn = QPushButton("⏭  Пропустить")
        skip_btn.setStyleSheet(
            "QPushButton{color:#484f58; border:none; padding:8px 12px;}"
            "QPushButton:hover{color:#8b949e;}"
        )
        skip_btn.clicked.connect(self._skip)

        footer_layout.addWidget(self._submit_btn)
        footer_layout.addWidget(skip_btn)
        footer_layout.addStretch()
        layout.addWidget(footer)

    # ── Public API ─────────────────────────────────────────

    def show_questions(self, questions: List[dict]) -> None:
        """Display questions and make panel visible."""
        # Clear old fields
        for field in self._fields:
            field.deleteLater()
        self._fields.clear()

        # Add new fields
        for i, q in enumerate(questions):
            field = QuestionField(q, i, self._container)
            self._container_layout.addWidget(field)
            self._fields.append(field)

        n = len(questions)
        self._count_lbl.setText(f"{n} вопрос{'а' if 2 <= n <= 4 else 'ов' if n >= 5 else ''}")
        self.setVisible(True)
        self._submit_btn.setEnabled(True)

    # ── Internal ───────────────────────────────────────────

    def _submit(self) -> None:
        answers = {f.question_id: f.answer for f in self._fields}
        self._submit_btn.setEnabled(False)
        self.answers_submitted.emit(answers)
        self.setVisible(False)

    def _skip(self) -> None:
        self.answers_submitted.emit({})
        self.setVisible(False)
