"""
orchestrator/pipeline_orchestrator.py — PipelineOrchestrator v2.0 PRODUCTION

Full pipeline:
  1. problem_analysis → user_clarification → architecture → spec → subprojects
  2. code_block_generation → save real files
  3. run_project (CLI) → if errors → fix_errors (loop max 3)
  4. unit_tests → run_tests → if failures → fix_tests (loop max 3)
  5. profile → optimization with profiling data
  6. readme → project_critique
  7. generate_spec → git_commit → project_metadata

File saving: extracts REAL code from GPT_PROTO_V1 data.files, never saves JSON as code.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Callable, Dict, List, Optional

from ai_gateway.gateway import AIGateway
from core.app_context import AppContext
from core.protocol import get_system_prompt
from local_model.local_analyzer import LocalAnalyzer
from parser.response_parser import ResponseParser, CodeBlockExtractor
from prompt_registry.registry import PromptRegistry
from runner.project_runner import ProjectRunner, ProjectRunReport
from storage.models import Message
from storage.storage_manager import StorageManager
from strategy.task_analyzer import StrategyBase
from token_saver.token_optimizer import TokenOptimizer


# ── Enums ─────────────────────────────────────────────────

class StageStatus(Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    ERROR    = "error"
    SKIPPED  = "skipped"
    CRITIQUE = "critique"
    WAITING  = "waiting"
    FIXING   = "fixing"


_CODE_STAGES = frozenset({
    "code_block_generation", "optimization", "unit_tests",
    "refactoring", "deployment_commands", "readme_generation",
    "fix_errors", "fix_tests",
})

MAX_FIX_ATTEMPTS = 3


# ── Dataclasses ───────────────────────────────────────────

@dataclass
class StageResult:
    stage:          str
    success:        bool
    parsed_data:    dict            = field(default_factory=dict)
    raw_response:   str             = ""
    error:          Optional[str]   = None
    chat_id:        str             = ""
    summary:        str             = ""
    confidence:     str             = "HIGH"
    warnings:       list            = field(default_factory=list)
    status_proto:   str             = "OK"
    overall_score:  Optional[int]   = None
    test_cases:     list            = field(default_factory=list)
    saved_files:    list            = field(default_factory=list)
    tokens_in:      int             = 0
    tokens_out:     int             = 0
    started_at:     Optional[datetime] = None
    finished_at:    Optional[datetime] = None

    @property
    def duration_sec(self) -> float:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0

    def confidence_emoji(self) -> str:
        return {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(self.confidence, "⚪")

    def status_emoji(self) -> str:
        return {"OK": "✅", "WARN": "⚠️", "ERROR": "❌", "PARTIAL": "🔶"}.get(
            self.status_proto, "❓"
        )


class ContextAccumulator:
    def __init__(self) -> None:
        self._ctx: dict = {}

    def add(self, stage: str, data: dict) -> None:
        self._ctx[stage] = data

    def get(self) -> dict:
        return dict(self._ctx)

    def to_compact_json(self) -> str:
        return json.dumps(self._ctx, ensure_ascii=False, separators=(",", ":"))

    def reset(self) -> None:
        self._ctx = {}


# ── Main Orchestrator ──────────────────────────────────────

class PipelineOrchestrator:
    """Production pipeline orchestrator. Runs the full cycle including
    code execution, test verification, profiling, and git commit."""

    def __init__(
        self,
        app_context:  AppContext,
        ai_gateway:   AIGateway,
        storage:      StorageManager,
        registry:     PromptRegistry,
        parser:       ResponseParser,
        file_manager=None,
    ) -> None:
        self._ctx          = app_context
        self._ai           = ai_gateway
        self._storage      = storage
        self._registry     = registry
        self._parser       = parser
        self._file_manager = file_manager
        self._accumulator  = ContextAccumulator()
        self._optimizer    = TokenOptimizer()
        self._local        = LocalAnalyzer(enabled=True)
        self._run_report:  Optional[ProjectRunReport] = None
        self._stage_statuses: Dict[str, StageStatus] = {}
        self._abort        = False

        # Callbacks
        self._token_cb:    Optional[Callable] = None
        self._stage_cb:    Optional[Callable] = None
        self._summary_cb:  Optional[Callable] = None
        self._progress_cb: Optional[Callable] = None
        self._clarify_cb:  Optional[Callable] = None
        self._tokens_cb:   Optional[Callable] = None

        # Clarification sync
        self._user_answer_event: Optional[threading.Event] = None
        self._user_answers:      Optional[dict]            = None

    def set_token_callback(self, cb):    self._token_cb    = cb
    def set_stage_callback(self, cb):    self._stage_cb    = cb
    def set_summary_callback(self, cb):  self._summary_cb  = cb
    def set_progress_callback(self, cb): self._progress_cb = cb
    def set_clarification_callback(self, cb): self._clarify_cb = cb
    def set_tokens_stats_callback(self, cb):  self._tokens_cb  = cb

    def provide_user_answers(self, answers: dict) -> None:
        self._user_answers = answers
        if self._user_answer_event:
            self._user_answer_event.set()

    def abort(self) -> None:
        self._abort = True
        if self._user_answer_event:
            self._user_answer_event.set()

    def set_model(self, model: str) -> None:
        self._optimizer.set_model(model)

    def get_stage_status(self, stage: str) -> StageStatus:
        return self._stage_statuses.get(stage, StageStatus.PENDING)

    def _log(self, method: str, *args, **kwargs) -> None:
        logger = getattr(self._ctx, "logger", None)
        if logger and hasattr(logger, method):
            try: getattr(logger, method)(*args, **kwargs)
            except Exception: pass

    # ── Main pipeline ──────────────────────────────────────

    async def run_pipeline(
        self, task: str, strategy: StrategyBase
    ) -> AsyncIterator[StageResult]:
        self._abort = False
        self._accumulator.reset()
        self._optimizer.reset_stats()
        self._user_answers = None

        stages = list(strategy.get_pipeline_stages())
        if "project_critique" not in stages:
            stages.append("project_critique")
        overrides = strategy.get_prompt_overrides()

        project_id = self._ctx.project_id
        self._accumulator.add("user_task", {"task": task})

        if self._file_manager and project_id:
            try:
                project_dir = self._file_manager.create_project_dir(project_id)
                logger = getattr(self._ctx, "logger", None)
                if logger:
                    logger.set_project_dir(str(project_dir))
                    logger.info("Pipeline started", project_id=project_id,
                                stages=len(stages))
            except Exception: pass

        gw_chat_id = ""
        total = len(stages)

        for idx, stage in enumerate(stages):
            if self._abort:
                self._set_status(stage, StageStatus.SKIPPED)
                continue

            if self._progress_cb:
                self._progress_cb(idx, total)

            tmpl = self._registry.get(stage)
            if not tmpl and stage not in ("project_critique",):
                self._set_status(stage, StageStatus.SKIPPED)
                continue

            self._set_status(stage, StageStatus.RUNNING)
            self._log("info", f"Stage started: {stage}")

            if not gw_chat_id or (tmpl and tmpl.creates_new_chat):
                gw_chat_id = await self._ai.create_chat(f"[{stage}]")

            db_chat_id = self._storage.create_chat_sync(
                f"[{stage}]", project_id, stage
            )

            opt_ctx, _ = self._optimizer.optimize_context_string(
                stage, self._accumulator.get()
            )
            profiling_ctx = (
                self._accumulator.get()
                    .get("profiling_report", {})
                    .get("context", "Профилирование не выполнялось")
            )
            ctx_vars = {
                "FULL_CONTEXT":        opt_ctx,
                "PROBLEM_DESCRIPTION": task,
                "STAGE":               stage,
                "LANGUAGE":            (self._accumulator.get()
                                        .get("user_clarification", {})
                                        .get("language", "Python")),
                "PROFILING_CONTEXT":   profiling_ctx,
            }

            # Special stages
            if stage == "user_clarification":
                result = await self._run_clarification_stage(
                    task, ctx_vars, gw_chat_id, db_chat_id, overrides.get(stage)
                )
            else:
                result = await self._run_single_stage(
                    stage, ctx_vars, gw_chat_id, db_chat_id, overrides.get(stage)
                )

            # Save files
            if result.parsed_data or result.raw_response:
                saved = self._extract_and_save_files(
                    stage, result.parsed_data, result.raw_response, project_id
                )
                result.saved_files = saved

            # After code generation: run → fix errors → tests → fix tests → profile
            if stage == "code_block_generation" and result.success:
                async for fix_result in self._post_code_pipeline(
                    task, project_id, gw_chat_id, ctx_vars
                ):
                    self._accumulator.add(fix_result.stage, fix_result.parsed_data)
                    self._ctx.accumulate(fix_result.stage, fix_result.parsed_data)
                    if self._summary_cb:
                        self._summary_cb(fix_result.stage, fix_result)
                    yield fix_result

            # After readme: generate spec, git commit, metadata
            if stage == "readme_generation" and result.success:
                async for post_result in self._post_readme_pipeline(
                    task, project_id, gw_chat_id, ctx_vars
                ):
                    yield post_result

            # Accumulate
            if result.success and result.parsed_data:
                self._accumulator.add(stage, result.parsed_data)
                self._ctx.accumulate(stage, result.parsed_data)

            # Token stats
            self._optimizer.add_usage(result.tokens_in, result.tokens_out)
            tin, tout = self._optimizer.get_total_tokens()
            if self._tokens_cb:
                self._tokens_cb(tin, tout, self._optimizer.get_total_cost())

            final = (StageStatus.CRITIQUE if stage == "project_critique"
                     else StageStatus.DONE if result.success
                     else StageStatus.ERROR)
            self._set_status(stage, final)
            self._log("info", f"Stage {stage}: {final.name}, {result.duration_sec:.1f}s")

            if self._summary_cb:
                self._summary_cb(stage, result)

            yield result

        if self._progress_cb:
            self._progress_cb(total, total)

    # ── Post-code pipeline ─────────────────────────────────

    async def _post_code_pipeline(
        self, task: str, project_id: str, gw_chat_id: str, ctx_vars: dict
    ) -> AsyncIterator[StageResult]:
        """Run → fix errors → tests → fix tests → profile."""
        project_dir = str(
            self._file_manager.get_project_dir(project_id)
        ) if self._file_manager else ""

        # ── 1. Run project, fix errors ─────────────────────
        run_ok = False
        for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
            self._log("info", f"Running project (attempt {attempt})")
            run_report = await self._run_project_async(project_dir)

            if run_report.run_result and run_report.run_result.success:
                run_ok = True
                self._log("info", "Project runs OK")
                break

            # Errors found → ask AI to fix
            error_text = ""
            if run_report.run_result:
                error_text = (run_report.run_result.stderr or "")[:1500]
            if run_report.errors:
                error_text += "\n" + "; ".join(run_report.errors[:3])

            self._log("info", f"Run errors, fixing (attempt {attempt}): {error_text[:100]}")
            self._set_status("fix_errors", StageStatus.FIXING)

            fix_ctx = {**ctx_vars, "ERROR_OUTPUT": error_text,
                       "FIX_ATTEMPT": str(attempt)}
            db = self._storage.create_chat_sync("[fix_errors]", project_id, "fix_errors")
            fix_result = await self._run_single_stage(
                "fix_errors", fix_ctx, gw_chat_id, db, self._FIX_ERRORS_PROMPT
            )
            if fix_result.saved_files or fix_result.parsed_data:
                saved = self._extract_and_save_files(
                    "fix_errors", fix_result.parsed_data,
                    fix_result.raw_response, project_id
                )
                fix_result.saved_files = saved
            self._set_status("fix_errors", StageStatus.DONE if fix_result.success else StageStatus.ERROR)
            yield fix_result

        # ── 2. Run tests, fix failures ─────────────────────
        tests_ok = False
        for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
            self._log("info", f"Running tests (attempt {attempt})")
            test_report = await self._run_project_async(project_dir, tests_only=True)

            tr = test_report.test_result
            if tr and tr.success and tr.failed == 0:
                tests_ok = True
                self._log("info", f"Tests OK: {tr.passed}/{tr.total}")
                break

            # Test failures → fix
            fail_text = ""
            if tr:
                fail_text = f"{tr.failed}/{tr.total} failed\n{tr.output[-1000:]}"
            self._log("info", f"Test failures, fixing: {fail_text[:100]}")
            self._set_status("fix_tests", StageStatus.FIXING)

            fix_ctx = {**ctx_vars, "TEST_OUTPUT": fail_text, "FIX_ATTEMPT": str(attempt)}
            db = self._storage.create_chat_sync("[fix_tests]", project_id, "fix_tests")
            fix_result = await self._run_single_stage(
                "fix_tests", fix_ctx, gw_chat_id, db, self._FIX_TESTS_PROMPT
            )
            saved = self._extract_and_save_files(
                "fix_tests", fix_result.parsed_data,
                fix_result.raw_response, project_id
            )
            fix_result.saved_files = saved
            self._set_status("fix_tests", StageStatus.DONE if fix_result.success else StageStatus.ERROR)
            yield fix_result

        # ── 3. Profile and inject context ──────────────────
        self._log("info", "Profiling project...")
        profile_report = await self._run_project_async(project_dir, profile_only=True)
        profiling_ctx = profile_report.to_optimization_context()
        self._accumulator.add("profiling_report", {
            "context":      profiling_ctx,
            "test_pass_rate": profile_report.test_result.pass_rate if profile_report.test_result else 0,
            "coverage_pct":   profile_report.test_result.coverage_pct if profile_report.test_result else 0,
        })
        # Save profiling JSON
        if self._file_manager:
            try:
                self._file_manager.save_file(
                    project_id, "docs/profiling_report.json",
                    json.dumps(profile_report.to_dict(), ensure_ascii=False, indent=2)
                )
            except Exception: pass
        self._log("info", "Profiling done")

    # ── Post-readme pipeline ────────────────────────────────

    async def _post_readme_pipeline(
        self, task: str, project_id: str, gw_chat_id: str, ctx_vars: dict
    ) -> AsyncIterator[StageResult]:
        """After readme: generate spec, git commit, project metadata."""
        project_dir = str(
            self._file_manager.get_project_dir(project_id)
        ) if self._file_manager else ""

        # ── Generate SPECIFICATION.md ──────────────────────
        self._set_status("generate_spec", StageStatus.RUNNING)
        db = self._storage.create_chat_sync("[generate_spec]", project_id, "spec")
        spec_result = await self._run_single_stage(
            "generate_spec", ctx_vars, gw_chat_id, db, self._SPEC_PROMPT
        )
        spec_content = self._extract_markdown(spec_result.raw_response, "SPECIFICATION")
        if spec_content and self._file_manager:
            self._file_manager.save_file(project_id, "SPECIFICATION.md", spec_content)
            spec_result.saved_files.append(str(
                self._file_manager.get_project_dir(project_id) / "SPECIFICATION.md"
            ))
        self._set_status("generate_spec", StageStatus.DONE)
        yield spec_result

        # ── Git commit ─────────────────────────────────────
        self._set_status("git_commit", StageStatus.RUNNING)
        git_result = await self._do_git_commit(project_dir, task)
        self._set_status("git_commit", StageStatus.DONE if git_result.success else StageStatus.ERROR)
        yield git_result

        # ── Project metadata ───────────────────────────────
        self._set_status("project_metadata", StageStatus.RUNNING)
        meta_result = await self._generate_project_metadata(project_id, task)
        self._set_status("project_metadata", StageStatus.DONE)
        yield meta_result

    # ── Single stage execution ─────────────────────────────

    async def _run_single_stage(
        self,
        stage:          str,
        context:        dict,
        gw_chat_id:     str,
        db_chat_id:     str = "",
        prompt_override: Optional[str] = None,
    ) -> StageResult:
        started = datetime.now(timezone.utc)

        system = get_system_prompt(stage)

        if stage == "project_critique":
            prompt = self._build_critique_prompt(context)
        elif prompt_override:
            prompt = prompt_override
        else:
            tmpl = self._registry.get(stage)
            if not tmpl:
                return StageResult(
                    stage=stage, success=False,
                    error=f"Stage '{stage}' not in registry",
                    started_at=started, finished_at=datetime.now(timezone.utc)
                )
            prompt = self._registry.fill(stage, context)

        # Apply local analyzer
        analysis = self._local.analyze(prompt, stage)
        if analysis.was_modified and analysis.savings_percent > 0.5:
            prompt = analysis.corrected_prompt
            self._log("info",
                f"LocalAnalyzer saved {analysis.tokens_saved}tok "
                f"({analysis.savings_percent:.1f}%) stage={stage}"
            )

        tokens_in = TokenOptimizer.count_tokens(prompt + system)

        if db_chat_id:
            try:
                self._storage.save_message_sync(
                    db_chat_id, Message(role="user", content=prompt, stage=stage)
                )
            except Exception: pass

        raw_response = ""
        project_id = getattr(self._ctx, "project_id", "")
        try:
            gen = self._ai.send_message(
                gw_chat_id, prompt, system=system,
                stage=stage, project_id=project_id
            )
            try:
                async for token in gen:
                    raw_response += token
                    if self._token_cb:
                        self._token_cb(stage, token)
            finally:
                try: await gen.aclose()
                except Exception: pass
        except Exception as exc:
            finished = datetime.now(timezone.utc)
            if db_chat_id:
                try:
                    self._storage.save_message_sync(
                        db_chat_id,
                        Message(role="assistant", content=f"[ERROR] {exc}", stage=stage)
                    )
                except Exception: pass
            return StageResult(
                stage=stage, success=False, raw_response=raw_response,
                error=str(exc), chat_id=db_chat_id, status_proto="ERROR",
                summary=f"Error: {str(exc)[:120]}",
                tokens_in=tokens_in,
                started_at=started, finished_at=finished
            )

        tokens_out = TokenOptimizer.count_tokens(raw_response)
        if db_chat_id:
            try:
                self._storage.save_message_sync(
                    db_chat_id,
                    Message(role="assistant", content=raw_response, stage=stage)
                )
            except Exception: pass

        finished = datetime.now(timezone.utc)
        result = self._parse_response(raw_response, stage, db_chat_id, started, finished)
        result.tokens_in  = tokens_in
        result.tokens_out = tokens_out
        return result

    # ── Clarification ──────────────────────────────────────

    async def _run_clarification_stage(
        self, task, context, gw_chat_id, db_chat_id, prompt_override
    ) -> StageResult:
        started = datetime.now(timezone.utc)
        q_result = await self._run_single_stage(
            "user_clarification", context, gw_chat_id, db_chat_id, prompt_override
        )
        questions = q_result.parsed_data.get("questions", []) if q_result.parsed_data else []
        if not questions:
            return q_result

        self._set_status("user_clarification", StageStatus.WAITING)
        if self._clarify_cb:
            self._clarify_cb(questions)

        self._user_answer_event = threading.Event()
        self._user_answer_event.wait(timeout=600)
        self._user_answer_event = None

        if self._abort:
            return StageResult(stage="user_clarification", success=False,
                               error="Aborted", started_at=started,
                               finished_at=datetime.now(timezone.utc))

        answers = self._user_answers or {}
        answers_text = "\n".join(
            f"Q: {q.get('question','')}\nA: {answers.get(q.get('id',''), q.get('default',''))}"
            for q in questions
        )
        final_prompt = (
            f"Task: {task}\n\nUser answers:\n{answers_text}\n\n"
            "Do FINAL analysis with these answers. Return GPT_PROTO_V1 JSON with: "
            "language, frameworks, target_os, key_features, constraints."
        )
        final = await self._run_single_stage(
            "user_clarification", context, gw_chat_id, db_chat_id, final_prompt
        )
        final.started_at = started
        return final

    # ── File extraction & saving ───────────────────────────

    def _extract_and_save_files(
        self, stage: str, data: dict, raw_response: str, project_id: str
    ) -> List[str]:
        """
        Extract real code files from GPT_PROTO_V1 response.
        Three levels of fallback. Never saves JSON as code.
        """
        if not self._file_manager or not project_id:
            return []

        saved: List[str] = []

        # Unwrap nested proto if needed
        actual = data
        if isinstance(data, dict) and data.get("proto") == "GPT_PROTO_V1":
            actual = data.get("data", data)

        # ── Level 1: data.files array ──────────────────────
        files_list = actual.get("files", []) if isinstance(actual, dict) else []
        if isinstance(files_list, list):
            for fi in files_list:
                if not isinstance(fi, dict):
                    continue
                filename = str(fi.get("filename", "")).strip().strip("/\\")
                content  = fi.get("content", "")
                # If content is nested JSON/dict, serialize it properly
                if isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False, indent=2)
                content = str(content).strip()
                if not filename or not content:
                    continue
                # Skip if content looks like a JSON envelope (not real code)
                if self._is_json_envelope(content):
                    self._log("warning", f"Skipping JSON envelope in {filename}")
                    continue
                filename = self._fix_filename(filename, stage)
                try:
                    path = self._file_manager.save_file(project_id, filename, content)
                    saved.append(str(path))
                    self._log("log_file_saved",
                               path=str(path), size_bytes=len(content.encode()), stage=stage)
                except Exception as e:
                    self._log("error", f"Save failed ({filename}): {e}")

        # ── Level 2: inline code/script/readme fields ──────
        if not saved and isinstance(actual, dict):
            for field_key, default_path in [
                ("code",   f"src/{stage.replace('_generation','')}.py"),
                ("script", "setup.sh"),
                ("readme", "README.md"),
            ]:
                val = str(actual.get(field_key, "")).strip()
                if val and not self._is_json_envelope(val):
                    default_path = self._fix_filename(default_path, stage)
                    try:
                        path = self._file_manager.save_file(project_id, default_path, val)
                        saved.append(str(path))
                        self._log("log_file_saved",
                                   path=str(path), size_bytes=len(val.encode()), stage=stage)
                    except Exception: pass

        # ── Level 3: extract code blocks from raw response ─
        if not saved and raw_response and stage in _CODE_STAGES:
            blocks = CodeBlockExtractor.extract_all_code_blocks(raw_response)
            ext_defaults = {
                "code_block_generation": "src/main",
                "unit_tests":            "tests/test_main",
                "optimization":          "src/optimized",
                "refactoring":           "src/refactored",
                "deployment_commands":   "setup",
                "readme_generation":     "README",
                "fix_errors":            "src/fixed",
                "fix_tests":             "tests/fixed_tests",
            }
            lang_ext = {
                "python":"py","py":"py","javascript":"js","js":"js",
                "typescript":"ts","ts":"ts","bash":"sh","sh":"sh",
                "shell":"sh","go":"go","rust":"rs","c":"c","cpp":"cpp",
                "markdown":"md","md":"md","yaml":"yml","json":"json",
                "dockerfile":"dockerfile","makefile":"Makefile","":"py",
            }
            base = ext_defaults.get(stage, f"docs/{stage}")
            for idx, (lang, code) in enumerate(blocks):
                if not code.strip():
                    continue
                ext = lang_ext.get(lang.lower(), "txt")
                suffix = f"_{idx}" if idx > 0 else ""
                fname = f"{base}{suffix}.{ext}"
                try:
                    path = self._file_manager.save_file(project_id, fname, code)
                    saved.append(str(path))
                    self._log("log_file_saved",
                               path=str(path), size_bytes=len(code.encode()),
                               stage=f"{stage}(block)")
                except Exception: pass

            # Last resort: save raw but try to extract from JSON first
            if not saved:
                code = self._extract_code_from_json_response(raw_response)
                if code:
                    fname_map = {
                        "code_block_generation": "src/generated.py",
                        "unit_tests":            "tests/test_generated.py",
                        "optimization":          "src/optimized.py",
                        "fix_errors":            "src/fixed.py",
                        "fix_tests":             "tests/fixed_tests.py",
                        "deployment_commands":   "setup.sh",
                        "readme_generation":     "README.md",
                    }
                    fname = fname_map.get(stage, f"docs/{stage}_output.txt")
                    try:
                        path = self._file_manager.save_file(project_id, fname, code)
                        saved.append(str(path))
                        self._log("log_file_saved", path=str(path),
                                   size_bytes=len(code.encode()), stage=f"{stage}(extracted)")
                    except Exception: pass

        # Save critique JSON separately
        if stage == "project_critique" and actual:
            try:
                path = self._file_manager.save_file(
                    project_id, "critique/critique_report.json",
                    json.dumps(actual, ensure_ascii=False, indent=2)
                )
                saved.append(str(path))
            except Exception: pass

        if saved:
            self._log("info", f"Saved {len(saved)} files for stage {stage}")
        return saved

    def _is_json_envelope(self, text: str) -> bool:
        """Check if text is a GPT_PROTO_V1 JSON envelope rather than real code."""
        stripped = text.strip()
        if len(stripped) < 10:
            return False
        if stripped.startswith("{") and '"proto"' in stripped[:100]:
            try:
                d = json.loads(stripped)
                if d.get("proto") == "GPT_PROTO_V1":
                    return True
            except Exception:
                pass
        return False

    def _extract_code_from_json_response(self, raw: str) -> Optional[str]:
        """Try to extract actual code from a JSON response."""
        try:
            d = json.loads(raw.strip())
            if isinstance(d, dict):
                inner = d.get("data", d)
                if isinstance(inner, dict):
                    # Try files[0].content
                    files = inner.get("files", [])
                    if files and isinstance(files[0], dict):
                        content = files[0].get("content", "")
                        if isinstance(content, str) and len(content) > 5:
                            return content
                    # Try direct code field
                    for key in ("code", "content", "script", "text"):
                        val = inner.get(key, "")
                        if isinstance(val, str) and len(val) > 5:
                            return val
        except Exception:
            pass
        return None

    def _fix_filename(self, filename: str, stage: str) -> str:
        """Ensure filename has correct extension, fix path separators."""
        filename = filename.replace("\\", "/").strip("/")
        p = Path(filename)
        if p.suffix:
            return filename
        stage_ext = {
            "code_block_generation": ".py", "unit_tests": ".py",
            "optimization": ".py", "refactoring": ".py",
            "deployment_commands": ".sh", "readme_generation": ".md",
            "fix_errors": ".py", "fix_tests": ".py",
        }
        return filename + stage_ext.get(stage, ".txt")

    # ── Run project async ──────────────────────────────────

    async def _run_project_async(
        self, project_dir: str, tests_only=False, profile_only=False
    ) -> ProjectRunReport:
        """Run ProjectRunner in executor to avoid blocking event loop."""
        loop = asyncio.get_event_loop()
        project_id = getattr(self._ctx, "project_id", "")
        runner = ProjectRunner(project_dir, logger=getattr(self._ctx, "logger", None))
        report = await loop.run_in_executor(
            None,
            lambda: runner.run_all(
                project_id,
                run_tests=(tests_only or not profile_only),
                run_profile=profile_only or not tests_only,
            )
        )
        return report

    # ── Git commit ─────────────────────────────────────────

    async def _do_git_commit(self, project_dir: str, task: str) -> StageResult:
        started = datetime.now(timezone.utc)
        saved_files = []
        try:
            cmds = [
                ["git", "init"],
                ["git", "config", "user.email", "gpt-orchestrator@local"],
                ["git", "config", "user.name", "GPT-Orchestrator"],
                ["git", "add", "."],
                ["git", "commit", "-m",
                 f"feat: initial generation\n\nTask: {task[:200]}\n\nGenerated by GPT-Orchestrator"],
            ]
            for cmd in cmds:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    cwd=project_dir, timeout=30
                )
                if result.returncode != 0 and "nothing to commit" not in result.stdout:
                    if cmd[1] != "init" and "already initialized" not in result.stderr:
                        self._log("warning", f"git {cmd[1]} failed: {result.stderr[:100]}")

            # Read commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=project_dir, timeout=10
            )
            commit_hash = hash_result.stdout.strip()[:12]

            commit_file = str(Path(project_dir) / ".git_info.json")
            with open(commit_file, "w") as f:
                json.dump({"commit": commit_hash, "task": task[:200]}, f)
            saved_files.append(commit_file)

            return StageResult(
                stage="git_commit", success=True,
                summary=f"Git commit: {commit_hash}",
                saved_files=saved_files,
                started_at=started, finished_at=datetime.now(timezone.utc)
            )
        except Exception as exc:
            return StageResult(
                stage="git_commit", success=False, error=str(exc),
                summary=f"Git commit failed: {exc}",
                started_at=started, finished_at=datetime.now(timezone.utc)
            )

    # ── Project metadata ───────────────────────────────────

    async def _generate_project_metadata(
        self, project_id: str, task: str
    ) -> StageResult:
        """Generate PROJECT_METADATA.json for future modifications."""
        started = datetime.now(timezone.utc)
        saved_files = []
        try:
            ctx = self._accumulator.get()
            files = []
            if self._file_manager:
                files = self._file_manager.list_files(project_id)

            spec_data   = ctx.get("global_spec_and_api", {})
            arch_data   = ctx.get("architecture_analysis", {})
            critique    = ctx.get("project_critique", {})
            profiling   = ctx.get("profiling_report", {})
            task_type   = ctx.get("user_task", {})

            metadata = {
                "schema_version":  "1.0",
                "project_id":      project_id,
                "task":            task,
                "task_type":       str(task_type),
                "generated_at":    datetime.now(timezone.utc).isoformat(),
                "generator":       "GPT-Orchestrator v2.0",
                "architecture": {
                    "type":       arch_data.get("architecture_type", ""),
                    "tech_stack": spec_data.get("tech_stack", {}),
                    "modules":    arch_data.get("modules", []),
                },
                "api": {
                    "endpoints":    spec_data.get("api_endpoints", []),
                    "data_models":  spec_data.get("data_models", []),
                    "env_vars":     spec_data.get("environment_variables", []),
                },
                "files": [
                    {
                        "path":        f,
                        "type":        Path(f).suffix,
                        "module":      Path(f).parts[0] if Path(f).parts else "",
                        "description": self._guess_file_description(f),
                    }
                    for f in files
                ],
                "quality": {
                    "critique_score": critique.get("overall_score"),
                    "grades":         critique.get("grades", {}),
                    "test_coverage":  profiling.get("coverage_pct", 0),
                    "test_pass_rate": profiling.get("test_pass_rate", 0),
                },
                "extension_instructions": (
                    "To extend this project:\n"
                    "1. Load this metadata file\n"
                    "2. Describe the extension in natural language\n"
                    "3. GPT-Orchestrator will read the existing structure and generate compatible code\n"
                    "4. Example prompt: 'Add user authentication to this project (see metadata)'"
                ),
                "modification_context": {
                    "full_spec":  spec_data,
                    "entry_points": spec_data.get("directory_structure", []),
                    "dependencies": spec_data.get("tech_stack", {}).get("dependencies", []),
                },
            }

            meta_path = str(
                self._file_manager.get_project_dir(project_id) / "PROJECT_METADATA.json"
            )
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            saved_files.append(meta_path)
            self._log("log_file_saved", path=meta_path,
                       size_bytes=Path(meta_path).stat().st_size, stage="project_metadata")

            return StageResult(
                stage="project_metadata", success=True,
                summary=f"Metadata: {len(files)} files, {len(metadata['api']['endpoints'])} endpoints",
                saved_files=saved_files,
                started_at=started, finished_at=datetime.now(timezone.utc)
            )
        except Exception as exc:
            return StageResult(
                stage="project_metadata", success=False, error=str(exc),
                summary=f"Metadata error: {exc}",
                started_at=started, finished_at=datetime.now(timezone.utc)
            )

    def _guess_file_description(self, filepath: str) -> str:
        p = Path(filepath)
        name = p.stem.lower()
        descriptions = {
            "main": "Entry point", "app": "Application core",
            "models": "Data models", "views": "Request handlers",
            "routes": "URL routing", "config": "Configuration",
            "settings": "Application settings", "utils": "Utilities",
            "helpers": "Helper functions", "db": "Database layer",
            "auth": "Authentication", "test": "Tests",
            "setup": "Setup/deployment script", "readme": "Documentation",
            "requirements": "Python dependencies", "dockerfile": "Docker config",
            "makefile": "Build automation",
        }
        for key, desc in descriptions.items():
            if key in name:
                return desc
        return p.suffix.lstrip(".").upper() + " file"

    def _extract_markdown(self, raw: str, section: str) -> Optional[str]:
        """Extract markdown content from response."""
        # Try to extract ```markdown block
        m = re.search(r"```(?:markdown|md)?\s*\n?(.*?)```", raw, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Try to extract from JSON response
        try:
            d = json.loads(raw.strip())
            inner = d.get("data", d) if isinstance(d, dict) else {}
            for key in ("content", "readme", "spec", "text"):
                val = inner.get(key, "") if isinstance(inner, dict) else ""
                if isinstance(val, str) and len(val) > 50:
                    return val
            files = inner.get("files", []) if isinstance(inner, dict) else []
            for fi in files:
                if isinstance(fi, dict) and ".md" in fi.get("filename", ""):
                    return fi.get("content", "")
        except Exception:
            pass
        # Return raw if it looks like markdown
        if raw.strip().startswith("#") or "##" in raw:
            return raw.strip()
        return raw.strip() if len(raw.strip()) > 50 else None

    # ── Response parsing ───────────────────────────────────

    def _parse_response(
        self, raw: str, stage: str, chat_id: str,
        started: datetime, finished: datetime
    ) -> StageResult:
        from core.protocol import ProtoEnvelope
        envelope = None

        try:
            d = json.loads(raw.strip())
            if isinstance(d, dict) and d.get("proto") == "GPT_PROTO_V1":
                envelope = ProtoEnvelope.from_dict(d)
        except Exception: pass

        if envelope is None:
            extracted = self._parser.parse_json(raw)
            if isinstance(extracted, dict) and extracted.get("proto") == "GPT_PROTO_V1":
                try: envelope = ProtoEnvelope.from_dict(extracted)
                except Exception: pass

        if envelope is None:
            j = self._parser.parse_json(raw)
            parsed = j if isinstance(j, dict) else {"raw": raw}
            return StageResult(
                stage=stage, success=True, parsed_data=parsed,
                raw_response=raw, chat_id=chat_id,
                summary="Response received", confidence="MEDIUM", status_proto="OK",
                started_at=started, finished_at=finished,
            )

        score = envelope.data.get("overall_score") if stage == "project_critique" else None
        return StageResult(
            stage=stage, success=envelope.is_ok(),
            parsed_data=envelope.data, raw_response=raw, chat_id=chat_id,
            summary=envelope.summary, confidence=envelope.confidence,
            warnings=envelope.warnings, status_proto=envelope.status,
            overall_score=score,
            test_cases=envelope.data.get("test_cases", []),
            error=envelope.data.get("error") if not envelope.is_ok() else None,
            started_at=started, finished_at=finished,
        )

    def _build_critique_prompt(self, context: dict) -> str:
        task = context.get("PROBLEM_DESCRIPTION", "")
        full_ctx = context.get("FULL_CONTEXT", "{}")
        return (
            f"Analyze the generated project.\n\nTASK:\n{task}\n\n"
            f"CONTEXT:\n{full_ctx}\n\n"
            "Generate minimum 5 test cases. Assess compliance_percent."
        )

    def _set_status(self, stage: str, status: StageStatus) -> None:
        self._stage_statuses[stage] = status
        if self._stage_cb:
            try: self._stage_cb(stage, status)
            except Exception: pass

    # ── Fix prompts ────────────────────────────────────────

    _FIX_ERRORS_PROMPT = """\
The generated code has runtime errors. Fix them.

CURRENT CODE CONTEXT: {{FULL_CONTEXT}}

ERROR OUTPUT:
{{ERROR_OUTPUT}}

Fix attempt: {{FIX_ATTEMPT}}

Return GPT_PROTO_V1 JSON with data.files containing COMPLETE fixed files.
Focus only on files that have errors. Include full file content.
"""

    _FIX_TESTS_PROMPT = """\
Some tests are failing. Fix the code or the tests to make all tests pass.

CURRENT CODE CONTEXT: {{FULL_CONTEXT}}

TEST OUTPUT:
{{TEST_OUTPUT}}

Fix attempt: {{FIX_ATTEMPT}}

Return GPT_PROTO_V1 JSON with data.files containing COMPLETE fixed files.
"""

    _SPEC_PROMPT = """\
Generate a comprehensive SPECIFICATION.md for this project.

PROJECT CONTEXT: {{FULL_CONTEXT}}
TASK: {{PROBLEM_DESCRIPTION}}

Return GPT_PROTO_V1 JSON with data.files containing:
[{"filename": "SPECIFICATION.md", "content": "# Project Title\\n...", "description": "Technical specification"}]

The spec must include: Overview, Architecture, API Reference, Data Models,
Setup Instructions, Development Guide, Environment Variables.
"""
