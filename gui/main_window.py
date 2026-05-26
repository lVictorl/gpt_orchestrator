"""
gui/main_window.py — MainWindow v1.8

All fixes applied:
  1. Clarification via proper Qt signal (thread-safe) - form appears correctly
  2. QFont fallback - no setPointSize <= 0 error
  3. Async generator properly closed in orchestrator
  4. Double logging removed
  5. StageSummaryBubble CSS fixed
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton,
    QSplitter, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

from core.app_context import AppContext
from core.config_manager import ConfigManager
from core.logger import StructLogger
from ai_gateway.gateway import AIGateway
from storage.storage_manager import StorageManager
from storage.models import Message, ChatMeta, Project, ProjectMeta
from orchestrator.pipeline_orchestrator import (
    PipelineOrchestrator, StageResult, StageStatus,
)
from prompt_registry.registry import PromptRegistry
from parser.response_parser import ResponseParser
from strategy.task_analyzer import TaskAnalyzer, TaskType
from file_manager.project_file_manager import ProjectFileManager, ReportGenerator

from .chat_widget import ChatWidget
from .history_panel import HistoryPanel
from .editor_widget import EditorWidget
from .pipeline_panel import PipelinePanel
from .generation_plan_widget import GenerationPlanWidget
from .styles import DARK_THEME
from .dialogs.api_key_dialog import ApiKeyDialog, SettingsDialog
from .dialogs.project_wizard import ProjectWizardDialog
from .dialogs.history_projects_dialog import HistoryProjectsDialog
from .clarification_widget import ClarificationPanel


def _app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _safe_font(size: int = 12) -> QFont:
    """Return a monospace font with guaranteed positive point size."""
    preferred = ["JetBrains Mono", "Fira Code", "Consolas", "Courier New"]
    families = QFontDatabase.families()
    for name in preferred:
        if any(name.lower() in f.lower() for f in families):
            f = QFont(name)
            f.setPointSize(max(size, 10))
            if f.pointSize() > 0:
                return f
    f = QFont()
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(max(size, 10))
    return f


# ── PipelineWorker ────────────────────────────────────────

class PipelineWorker(QThread):
    """
    Runs the async pipeline in a worker thread.
    All Qt-visible events are emitted via signals (thread-safe).
    """
    token_received          = pyqtSignal(str, str)       # stage, token
    stage_status            = pyqtSignal(str, str)        # stage, StageStatus.name
    stage_done              = pyqtSignal(str, object)     # stage, StageResult
    pipeline_done           = pyqtSignal(object)          # last StageResult
    pipeline_error          = pyqtSignal(str)
    tokens_updated = pyqtSignal(int, int, float)  # input_tokens, output_tokens, cost_usd
    # ← Thread-safe clarification signal (crosses thread boundary correctly)
    clarification_requested = pyqtSignal(list)            # list of question dicts

    def __init__(self, orchestrator: PipelineOrchestrator, task: str, strategy) -> None:
        super().__init__()
        self._orchestrator = orchestrator
        self._task = task
        self._strategy = strategy

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Wire all callbacks through signals (thread-safe)
        self._orchestrator.set_token_callback(
            lambda s, t: self.token_received.emit(s, t)
        )
        self._orchestrator.set_stage_callback(
            lambda s, st: self.stage_status.emit(s, st.name)
        )
        self._orchestrator.set_summary_callback(
            lambda s, r: self.stage_done.emit(s, r)
        )
        self._orchestrator.set_tokens_stats_callback(
            lambda tin, tout, cost: self.tokens_updated.emit(tin, tout, cost)
        )
        # Clarification: emit Qt signal instead of calling UI directly
        self._orchestrator.set_clarification_callback(
            lambda questions: self.clarification_requested.emit(questions)
        )

        try:
            last_result = None

            async def _run():
                nonlocal last_result
                async for result in self._orchestrator.run_pipeline(
                    self._task, self._strategy
                ):
                    last_result = result

            loop.run_until_complete(_run())
            self.pipeline_done.emit(last_result)
        except Exception as exc:
            self.pipeline_error.emit(str(exc))
        finally:
            # Clean up pending tasks before closing the loop
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()


# ── MainWindow ────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._init_services()
        self._setup_ui()
        self._connect_signals()
        self._load_initial_data()

    def _init_services(self) -> None:
        app_dir = _app_dir()

        self._config = ConfigManager(str(app_dir / "config.toml"))
        self._config.load()

        log_dir = app_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = StructLogger(
            log_dir=str(log_dir),
            level=self._config.get("app.log_level", "DEBUG"),
        )

        self._app_context = AppContext(config=self._config, logger=self._logger)
        self._ai_gateway  = AIGateway(self._config, logger=self._logger)
        self._task_analyzer = TaskAnalyzer()
        self._registry    = PromptRegistry(str(app_dir / "pipeline.json"))
        self._parser      = ResponseParser()

        projects_rel = self._config.get("app.projects_dir", "projects")
        self._projects_dir = str(
            Path(projects_rel) if Path(projects_rel).is_absolute()
            else app_dir / projects_rel
        )
        Path(self._projects_dir).mkdir(parents=True, exist_ok=True)

        self._file_manager = ProjectFileManager(self._projects_dir)
        self._report_gen   = ReportGenerator()

        self._db_path = str(app_dir / "data.db")
        self._storage = StorageManager(self._db_path)

        self._orchestrator: Optional[PipelineOrchestrator] = None
        self._worker: Optional[PipelineWorker] = None
        self._storage_ready = False
        self._current_project_id: Optional[str] = None
        self._current_plan_task_title: Optional[str] = None
        self._current_stream_stage: str = ""
        self._stages_report: List[dict] = []

    # ── UI ────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("🤖 GPT-Orchestrator v1.8")
        self.resize(1280, 800)
        self.setMinimumWidth(800)
        self.setStyleSheet(DARK_THEME)
        self._build_menu()

        # Apply safe font (fixes QFont::setPointSize <= 0)
        font_size = max(self._config.get("app.font_size", 12), 10)
        QApplication.instance().setFont(_safe_font(font_size))

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toolbar_frame = self._build_toolbar()
        root.addWidget(self._toolbar_frame)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)

        self._history = HistoryPanel()
        splitter.addWidget(self._history)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane{border:none}"
            "QTabBar::tab{background:#161b22;color:#8b949e;padding:8px 18px}"
            "QTabBar::tab:selected{background:#0d1117;color:#e6edf3;"
            "border-bottom:2px solid #388bfd}"
        )

        # Chat container with clarification panel
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)
        self._chat = ChatWidget()
        self._clarification_panel = ClarificationPanel()
        self._clarification_panel.answers_submitted.connect(
            self._on_clarification_answers
        )
        chat_layout.addWidget(self._chat)
        chat_layout.addWidget(self._clarification_panel)

        self._editor = EditorWidget()
        self._plan_widget = GenerationPlanWidget()
        self._tabs.addTab(chat_container,    "💬 Чат")
        self._tabs.addTab(self._editor,      "📝 Редактор")
        self._tabs.addTab(self._plan_widget, "📅 План генерации")
        splitter.addWidget(self._tabs)

        self._pipeline_panel = PipelinePanel()
        self._pipeline_panel.setMinimumWidth(300)
        splitter.addWidget(self._pipeline_panel)

        splitter.setSizes([220, 920, 320])
        root.addWidget(splitter)

        self._status_label     = QLabel("Готов")
        self._stage_label      = QLabel("")
        self._stage_label.setStyleSheet("color:#388bfd;")
        self._token_status_lbl = QLabel("Токены: 0")
        self._token_status_lbl.setStyleSheet("color:#484f58;font-size:11px;")
        self._cost_lbl = QLabel("")
        self._cost_lbl.setStyleSheet("color:#2ea043;font-size:11px;font-weight:bold;")
        self._model_lbl = QLabel("")
        self._model_lbl.setStyleSheet("color:#388bfd;font-size:10px;")

        sb = QStatusBar()
        sb.addWidget(self._status_label)
        sb.addWidget(QLabel("  "))
        sb.addWidget(self._stage_label)
        sb.addPermanentWidget(self._model_lbl)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._token_status_lbl)
        sb.addPermanentWidget(self._cost_lbl)
        self.setStatusBar(sb)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame{background:#161b22;border-bottom:1px solid #30363d;}"
        )
        # Allow toolbar to shrink horizontally with the window
        from PyQt6.QtWidgets import QSizePolicy
        bar.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Тип задачи:"))
        self._task_type_combo = QComboBox()
        self._task_type_combo.insertItem(0, "🤖 авто", None)
        for t in TaskType:
            if t != TaskType.OTHER:
                self._task_type_combo.addItem(t.value, t)
        self._task_type_combo.setCurrentIndex(0)
        self._task_type_combo.setMaximumWidth(140)
        layout.addWidget(self._task_type_combo)

        for label, slot, tip in [
            ("🧙 Мастер проекта", self._show_project_wizard, "Форма-опросник"),
            ("🏠 Главный чат",    self._go_home,             "Первый чат проекта"),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        layout.addStretch()

        provider = self._config.get("api.provider", "anthropic")
        self._provider_lbl = QLabel(f"🔌 {provider}")
        self._provider_lbl.setStyleSheet("color:#8b949e;font-size:11px;")
        layout.addWidget(self._provider_lbl)
        return bar

    def _build_menu(self) -> None:
        mb = self.menuBar()

        proj = mb.addMenu("&Проект")
        for label, shortcut, slot in [
            ("🧙 Новый проект...", "Ctrl+N", self._show_project_wizard),
            ("📚 История проектов", "",      self._show_history_projects),
        ]:
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            proj.addAction(a)
        proj.addSeparator()
        a = QAction("Выход", self)
        a.setShortcut("Ctrl+Q")
        a.triggered.connect(self.close)
        proj.addAction(a)

        view = mb.addMenu("&Вид")
        self._toggle_tb_action = QAction("🔧 Панель инструментов", self)
        self._toggle_tb_action.setShortcut("Ctrl+T")
        self._toggle_tb_action.setCheckable(True)
        self._toggle_tb_action.setChecked(True)
        self._toggle_tb_action.triggered.connect(
            lambda checked: self._toolbar_frame.setVisible(checked)
        )
        view.addAction(self._toggle_tb_action)

        sett = mb.addMenu("&Настройки")
        for label, slot in [
            ("🔑 API-ключ",  self._show_api_key_dialog),
            ("⚙️ Настройки", self._show_settings_dialog),
        ]:
            a = QAction(label, self)
            a.triggered.connect(slot)
            sett.addAction(a)

    def _connect_signals(self) -> None:
        self._chat.message_submitted.connect(self._on_task_submitted)
        self._editor.insert_to_prompt.connect(
            lambda t: self._chat._input.setPlainText(
                self._chat._input.toPlainText() + "\n\n" + t
            )
        )
        self._history.chat_selected.connect(self._on_chat_selected)
        self._history.chat_deleted.connect(self._on_chat_deleted)
        self._history.chat_renamed.connect(self._on_chat_renamed)
        self._history.new_chat_requested.connect(self._on_new_chat)
        self._history.home_requested.connect(self._go_home)
        self._plan_widget.task_run_requested.connect(self._on_plan_task_run)

    def _load_initial_data(self) -> None:
        QTimer.singleShot(150, self._init_storage_and_ui)

    def _init_storage_and_ui(self) -> None:
        try:
            self._storage.init_sync()
            self._storage_ready = True
            self._logger.info(f"Storage initialized: {self._db_path}")
        except Exception as exc:
            self._logger.error("Storage init error", exc=str(exc))
            QMessageBox.critical(self, "Ошибка БД",
                                 f"Не удалось инициализировать БД:\n{exc}")
            return

        provider = self._config.get("api.provider", "anthropic")
        model_map = {
            "anthropic": self._config.get("api.model_anthropic", "claude-sonnet-4-20250514"),
            "openai":    self._config.get("api.model_openai",    "gpt-4o"),
            "deepseek":  self._config.get("api.model_deepseek",  "deepseek-chat"),
        }
        model = model_map.get(provider, "claude-sonnet-4-20250514")

        provider = self._config.get("api.provider", "anthropic")
        model_map = {
            "anthropic": self._config.get("api.model_anthropic", "claude-sonnet-4-20250514"),
            "openai":    self._config.get("api.model_openai",    "gpt-4o"),
            "deepseek":  self._config.get("api.model_deepseek",  "deepseek-chat"),
        }
        model = model_map.get(provider, "claude-sonnet-4-20250514")
        self._model_lbl.setText(f"🤖 {model}")

        self._orchestrator = PipelineOrchestrator(
            app_context=self._app_context,
            ai_gateway=self._ai_gateway,
            storage=self._storage,
            registry=self._registry,
            parser=self._parser,
            file_manager=self._file_manager,
        )
        self._orchestrator.set_model(model)
        # NOTE: clarification_callback is set per-worker in _launch_pipeline

        self._refresh_history()

    # ── History ───────────────────────────────────────────

    def _refresh_history(self) -> None:
        if not self._storage_ready:
            return
        try:
            projects = self._storage.list_projects_sync()
            project_chats: Dict[str, List[ChatMeta]] = {}
            for p in projects:
                project_chats[p.project_id] = self._storage.list_chats_sync(p.project_id)
            all_chats = self._storage.list_chats_sync()
            orphans = [c for c in all_chats if not c.project_id]
            self._history.load_projects(projects, project_chats, orphans)
        except Exception as exc:
            self._logger.error("History refresh error", exc=str(exc))

    # ── Pipeline ──────────────────────────────────────────

    def _on_task_submitted(self, task: str) -> None:
        self._launch_pipeline(task)

    def _on_plan_task_run(self, title: str, description: str) -> None:
        self._current_plan_task_title = title
        self._launch_pipeline(f"{title}\n\n{description}")
        self._tabs.setCurrentIndex(0)

    def _launch_pipeline(self, task: str) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Занято", "Пайплайн уже выполняется.")
            return
        if not self._storage_ready or self._orchestrator is None:
            QMessageBox.warning(self, "Ошибка", "Хранилище не готово.")
            return

        has_key = any([
            self._config.get("api.anthropic_key"),
            self._config.get("api.openai_key"),
            self._config.get("api.deepseek_key"),
        ])
        if not has_key:
            if QMessageBox.question(
                self, "API-ключ не задан", "Открыть настройки?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                self._show_api_key_dialog()
            return

        chosen = self._task_type_combo.currentData()
        task_type = chosen if chosen else self._task_analyzer.analyze(task)
        strategy  = self._task_analyzer.select_strategy(task_type)

        all_stages = list(strategy.get_pipeline_stages())
        if "project_critique" not in all_stages:
            all_stages.append("project_critique")
        # Production pipeline extra stages
        extra = ["fix_errors", "fix_tests", "generate_spec", "git_commit", "project_metadata"]
        for s in extra:
            if s not in all_stages:
                all_stages.append(s)
        self._pipeline_panel.init_stages(all_stages)

        project_id = str(uuid.uuid4())
        self._current_project_id = project_id
        self._app_context.reset_project(project_id)
        self._stages_report = []

        try:
            self._storage.save_project_sync(Project(
                project_id=project_id,
                title=task[:80],
                task_type=task_type.value,
                description=task,
            ))
            self._logger.info(
                f"Project created: {project_id}",
                task_type=task_type.value,
                projects_dir=self._projects_dir,
            )
        except Exception as exc:
            self._logger.error("Project save error", exc=str(exc))

        try:
            project_dir = self._file_manager.create_project_dir(project_id)
            self._logger.info(f"Project dir: {project_dir}")
        except Exception as exc:
            self._logger.error("Project dir error", exc=str(exc))

        self._chat.set_running(True)
        self._chat.add_stage_marker(
            "pipeline",
            f"🚀 Старт [{task_type.value}] | {len(all_stages)} этапов "
            f"| {self._config.get('api.provider', 'anthropic')}\n"
            f"📁 {self._projects_dir}/{project_id}",
        )
        self._status_label.setText(f"▶ [{task_type.value}]...")
        self._current_stream_stage = ""

        self._worker = PipelineWorker(self._orchestrator, task, strategy)
        self._worker.token_received.connect(self._on_token_qt)
        self._worker.stage_status.connect(self._on_stage_status_qt)
        self._worker.stage_done.connect(self._on_stage_done_qt)
        self._worker.pipeline_done.connect(self._on_pipeline_done)
        self._worker.pipeline_error.connect(self._on_pipeline_error)
        self._worker.tokens_updated.connect(self._on_tokens_updated)
        # ← Thread-safe clarification form trigger
        self._worker.clarification_requested.connect(self._on_clarification_questions)

        self._chat._abort_btn.clicked.connect(self._orchestrator.abort)
        self._worker.start()

    # ── Signal handlers ───────────────────────────────────

    def _on_token_qt(self, stage: str, token: str) -> None:
        if self._current_stream_stage != stage:
            self._chat.finish_streaming()
            self._current_stream_stage = stage
            self._chat.start_streaming_bubble(stage)
            self._stage_label.setText(f"▶ {stage}")
        self._chat.append_token(token)
        self._pipeline_panel.on_token(stage, token)

    def _on_stage_status_qt(self, stage: str, status_name: str) -> None:
        try:
            status = StageStatus[status_name]
        except KeyError:
            status = StageStatus.DONE
        self._pipeline_panel.on_stage_status(stage, status)
        if status == StageStatus.RUNNING:
            self._stage_label.setText(f"▶ {stage}")

    def _on_stage_done_qt(self, stage: str, result: object) -> None:
        r: StageResult = result  # type: ignore

        self._chat.finish_streaming()
        self._current_stream_stage = ""
        self._pipeline_panel.on_stage_result(stage, r)

        self._chat.add_stage_summary(
            stage=stage,
            summary=r.summary or "Этап выполнен",
            confidence=r.confidence,
            status=r.status_proto,
            warnings=r.warnings,
            duration=r.duration_sec,
        )

        if r.saved_files:
            n = len(r.saved_files)
            preview = "\n".join(f"  📄 {Path(f).name}" for f in r.saved_files[:5])
            suffix = f"\n  ... и ещё {n - 5}" if n > 5 else ""
            self._chat.add_stage_marker(
                stage, f"💾 Сохранено {n} файл(ов):\n{preview}{suffix}"
            )

        if stage == "project_critique" and r.parsed_data:
            d = r.parsed_data
            self._chat.add_critique(
                score=d.get("overall_score", 0),
                compliance=d.get("compliance_percent", 0),
                summary=r.summary or "",
                grades=d.get("grades", {}),
                strengths=d.get("strengths", []),
                weaknesses=d.get("weaknesses", []),
                recommendations=d.get("recommendations", []),
            )
            if r.overall_score is not None and self._current_project_id:
                try:
                    self._storage.update_project_status_sync(
                        self._current_project_id, "done", r.overall_score
                    )
                except Exception as exc:
                    self._logger.error("Critique score save error", exc=str(exc))

        self._stages_report.append({
            "stage": stage, "status": r.status_proto,
            "confidence": r.confidence, "summary": r.summary,
            "duration_sec": r.duration_sec, "warnings": r.warnings,
        })

    def _on_tokens_updated(self, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        total = tokens_in + tokens_out
        self._token_status_lbl.setText(f"↑{tokens_in:,} ↓{tokens_out:,}")
        if cost_usd > 0:
            self._cost_lbl.setText(f"  💰 ${cost_usd:.4f}")
        # Show model info
        provider = self._config.get("api.provider", "")
        model_map = {
            "anthropic": self._config.get("api.model_anthropic", "claude-sonnet-4"),
            "openai":    self._config.get("api.model_openai",    "gpt-4o"),
            "deepseek":  self._config.get("api.model_deepseek",  "deepseek-chat"),
        }
        model = model_map.get(provider, "")
        self._model_lbl.setText(f"🤖 {model}")
        self._pipeline_panel.update_token_count(total)

    def _on_pipeline_done(self, last_result: object) -> None:
        r: Optional[StageResult] = last_result  # type: ignore

        self._chat.set_running(False)
        self._pipeline_panel.on_pipeline_done()
        self._status_label.setText("✅ Генерация завершена")
        self._stage_label.setText("")

        try:
            self._chat._abort_btn.clicked.disconnect()
        except Exception:
            pass

        score = r.overall_score if r else None
        if self._current_plan_task_title:
            self._plan_widget.mark_task_done(self._current_plan_task_title, score)
            self._current_plan_task_title = None

        self._generate_report()
        QTimer.singleShot(400, self._refresh_history)

    def _on_pipeline_error(self, error: str) -> None:
        self._chat.set_running(False)
        self._pipeline_panel.on_pipeline_error()
        self._status_label.setText("❌ Ошибка")
        self._stage_label.setText("")
        self._chat.add_stage_marker("error", f"❌ {error}")
        try:
            self._chat._abort_btn.clicked.disconnect()
        except Exception:
            pass

    def _generate_report(self) -> None:
        if not self._current_project_id:
            return
        try:
            project_dir = self._file_manager.get_project_dir(self._current_project_id)
            out = str(project_dir / "report.html")
            critique_data = next(
                (s for s in self._stages_report if s["stage"] == "project_critique"), None
            )
            self._report_gen.generate(
                project_id=self._current_project_id,
                title=f"Проект {self._current_project_id[:8]}",
                stages_data=self._stages_report,
                output_path=out,
                critique_data=critique_data,
            )
            self._chat.add_stage_marker("report", f"📊 Отчёт: {out}")
        except Exception as exc:
            self._logger.error("Report error", exc=str(exc))

    # ── Clarification (thread-safe via Qt signal) ─────────

    def _on_clarification_questions(self, questions: list) -> None:
        """
        Called in the MAIN THREAD via Qt signal.
        Shows the clarification form to the user.
        The worker thread is blocked on threading.Event.wait().
        """
        if not questions:
            # No questions — unblock worker immediately
            if self._orchestrator:
                self._orchestrator.provide_user_answers({})
            return

        self._tabs.setCurrentIndex(0)

        # Show notification in chat
        self._chat.add_stage_marker(
            "user_clarification",
            f"❓ ИИ задал {len(questions)} уточняющих вопросов.\n"
            "Заполните форму ниже и нажмите «Отправить ответы»."
        )

        # Show the clarification form panel
        self._clarification_panel.show_questions(questions)
        self._status_label.setText("⏸ Ожидание ваших ответов на уточнения...")

    def _on_clarification_answers(self, answers: dict) -> None:
        """User submitted answers — unblock the worker thread."""
        if self._orchestrator:
            self._orchestrator.provide_user_answers(answers)
        self._status_label.setText("▶ Продолжение генерации...")

        if answers:
            lines = "\n".join(
                f"• Q{i+1}: {v}" for i, v in enumerate(answers.values()) if v
            )
            self._chat.add_stage_marker(
                "user_clarification", f"✅ Ответы отправлены:\n{lines}"
            )

    # ── Chat ──────────────────────────────────────────────

    def _on_chat_selected(self, chat_id: str) -> None:
        if not chat_id or not self._storage_ready:
            return
        try:
            messages = self._storage.get_chat_history_sync(chat_id)
        except Exception as exc:
            self._logger.error("Chat load error", exc=str(exc))
            messages = []

        self._chat.clear_messages()
        if not messages:
            self._chat.add_stage_marker("empty", "💬 Чат пуст")
        else:
            for msg in messages:
                if msg.role == "system":
                    self._chat.add_stage_marker(msg.stage or "system", msg.content)
                else:
                    self._chat.add_message(msg.role, msg.content, msg.stage, msg.timestamp)
        self._tabs.setCurrentIndex(0)

    def _on_chat_deleted(self, chat_id: str) -> None:
        if not self._storage_ready:
            return
        try:
            self._storage.delete_chat_sync(chat_id)
        except Exception as exc:
            self._logger.error("Chat delete error", exc=str(exc))
        self._history.remove_chat(chat_id)

    def _on_chat_renamed(self, chat_id: str, new_title: str) -> None:
        if not self._storage_ready:
            return
        try:
            self._storage.rename_chat_sync(chat_id, new_title)
        except Exception as exc:
            self._logger.error("Chat rename error", exc=str(exc))
        self._history.rename_chat(chat_id, new_title)

    def _on_new_chat(self) -> None:
        if not self._storage_ready:
            return
        try:
            self._storage.create_chat_sync("Новый чат", self._current_project_id or "")
            QTimer.singleShot(100, self._refresh_history)
        except Exception as exc:
            self._logger.error("Chat create error", exc=str(exc))

    def _go_home(self) -> None:
        first = self._history._first_chat_id
        if first:
            self._on_chat_selected(first)
            self._history.select_chat(first)
        else:
            self._chat.clear_messages()
            self._pipeline_panel.reset()

    # ── Dialogs ───────────────────────────────────────────

    def _show_project_wizard(self) -> None:
        dlg = ProjectWizardDialog(parent=self)
        if dlg.exec():
            self._chat._input.setPlainText(dlg.build_task_prompt())
            self._tabs.setCurrentIndex(0)

    def _show_history_projects(self) -> None:
        if not self._storage_ready:
            return
        dlg = HistoryProjectsDialog(
            storage=self._storage,
            projects_root=self._projects_dir,
            parent=self,
        )
        dlg.file_open_requested.connect(self._editor.open_file)
        dlg.exec()

    def _show_api_key_dialog(self) -> None:
        provider = self._config.get("api.provider", "anthropic")
        key_map = {
            "openai":    "api.openai_key",
            "anthropic": "api.anthropic_key",
            "deepseek":  "api.deepseek_key",
        }
        current_key = self._config.get(key_map.get(provider, "api.anthropic_key"), "")
        dlg = ApiKeyDialog(
            current_key=current_key,
            provider=provider,
            ai_gateway=self._ai_gateway,
            parent=self,
        )
        if dlg.exec():
            self._ai_gateway.set_api_key(dlg.api_key, dlg.provider)
            self._config.set(key_map.get(dlg.provider, "api.anthropic_key"), dlg.api_key)
            try:
                self._config.save()
            except Exception:
                pass
            self._provider_lbl.setText(f"🔌 {dlg.provider}")
            self._status_label.setText("✅ API-ключ сохранён")

    def _show_settings_dialog(self) -> None:
        SettingsDialog(self._config, parent=self).exec()

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            if self._orchestrator:
                self._orchestrator.abort()
            self._worker.quit()
            self._worker.wait(3000)
        try:
            self._config.save()
        except Exception:
            pass
        event.accept()
