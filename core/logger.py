"""
core/logger.py — StructLogger v2

Новое:
  - Полное логирование взаимодействия с ИИ (промпт, ответ, токены, latency)
  - set_project_dir: лог проекта пишется в projects/{id}/logs/
  - log_ai_request / log_ai_response / log_ai_error — отдельные методы
  - Форматирование: JSON-строки в файл, читаемый вывод в консоль
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class StructLogger:
    """Структурированный логгер с поддержкой AI-трейсинга."""

    def __init__(
        self,
        name: str = "gpt_orchestrator",
        log_dir: str = "logs",
        level: str = "DEBUG",   # DEBUG чтобы фиксировать всё
        max_bytes: int = 20 * 1024 * 1024,
        backup_count: int = 10,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._name = name

        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.upper(), logging.DEBUG))
        self._logger.propagate = False

        if not self._logger.handlers:
            # Консольный хэндлер (читаемый)
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            ch.setFormatter(self._console_formatter())
            self._logger.addHandler(ch)

            # Файловый хэндлер (JSON, всё включая DEBUG)
            self._add_file_handler(self._log_dir / f"{name}.log", max_bytes, backup_count)

    def _add_file_handler(self, path: Path, max_bytes: int, backup_count: int) -> None:
        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(self._json_formatter())
        self._logger.addHandler(fh)

    # ── Основные методы ────────────────────────────────────

    def debug(self, msg: str, **kw: Any) -> None:
        self._logger.debug(self._fmt(msg, kw))

    def info(self, msg: str, **kw: Any) -> None:
        self._logger.info(self._fmt(msg, kw))

    def warning(self, msg: str, **kw: Any) -> None:
        self._logger.warning(self._fmt(msg, kw))

    def error(self, msg: str, **kw: Any) -> None:
        self._logger.error(self._fmt(msg, kw))

    # ── AI-трейсинг ───────────────────────────────────────

    def log_ai_request(
        self,
        provider: str,
        model: str,
        stage: str,
        prompt: str,
        system: str = "",
        project_id: str = "",
    ) -> None:
        """Логирует исходящий запрос к ИИ полностью."""
        self._logger.debug(self._fmt("AI_REQUEST", {
            "provider":   provider,
            "model":      model,
            "stage":      stage,
            "project_id": project_id,
            "prompt_len": len(prompt),
            "system_len": len(system),
            "prompt":     prompt[:2000],   # первые 2000 символов
            "system":     system[:500],
        }))

    def log_ai_response(
        self,
        provider: str,
        stage: str,
        response: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_sec: float = 0.0,
        project_id: str = "",
    ) -> None:
        """Логирует полный ответ ИИ. Пишет ОДНУ строку в INFO (консоль + файл)."""
        # Single INFO line visible in console and all log files
        self._logger.info(self._fmt("AI_RESPONSE", {
            "provider":     provider,
            "stage":        stage,
            "project_id":   project_id,
            "response_len": len(response),
            "tokens_in":    tokens_in,
            "tokens_out":   tokens_out,
            "latency_sec":  round(latency_sec, 3),
        }))
        # Full response text only in DEBUG (file only, not console)
        if len(response) > 0:
            self._logger.debug(
                f"AI_RESPONSE_FULL stage={stage} response={response[:2000]!r}"
            )

    def log_ai_error(
        self,
        provider: str,
        stage: str,
        error: str,
        project_id: str = "",
    ) -> None:
        """Логирует ошибку взаимодействия с ИИ."""
        self._logger.error(self._fmt("AI_ERROR", {
            "provider":   provider,
            "stage":      stage,
            "project_id": project_id,
            "error":      error,
        }))

    def log_file_saved(self, path: str, size_bytes: int, stage: str = "") -> None:
        self.info(f"FILE_SAVED | path={path} size={size_bytes}b stage={stage}")

    def log_stage(self, stage: str, status: str, duration_sec: float = 0.0) -> None:
        self.info(
            f"STAGE {status.upper()} | stage={stage} duration={duration_sec:.1f}s"
        )

    def set_project_dir(self, project_dir: str) -> None:
        """Добавить файловый лог в папку проекта."""
        p = Path(project_dir) / "logs"
        p.mkdir(parents=True, exist_ok=True)
        log_file = p / "project.log"
        self._add_file_handler(log_file, 20 * 1024 * 1024, 5)
        self.info(f"Project log started", path=str(log_file))

    # ── Formatters ────────────────────────────────────────

    @staticmethod
    def _fmt(msg: str, kw: dict) -> str:
        if not kw:
            return msg
        extra = " | ".join(f"{k}={v!r}" for k, v in kw.items())
        return f"{msg} | {extra}"

    @staticmethod
    def _console_formatter() -> logging.Formatter:
        return logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )

    @staticmethod
    def _json_formatter() -> logging.Formatter:
        class _JSON(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return json.dumps(
                    {
                        "ts":    datetime.now(timezone.utc).isoformat(),
                        "level": record.levelname,
                        "msg":   record.getMessage(),
                    },
                    ensure_ascii=False,
                )
        return _JSON()
