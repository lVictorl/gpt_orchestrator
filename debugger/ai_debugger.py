"""
debugger/ai_debugger.py — AIDebugger v2

Улучшения:
  - Использует GPT_PROTO_V1 протокол
  - Использует get_system_prompt для системного промпта
  - FixApplicator обновляет файлы через ProjectFileManager
  - Полное логирование через StructLogger
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ai_gateway.gateway import AIGateway
from core.app_context import AppContext
from core.protocol import get_system_prompt
from parser.response_parser import ResponseParser
from prompt_registry.registry import PromptRegistry


@dataclass
class AppError:
    message:          str
    traceback:        str
    context_snapshot: dict
    command:          str = ""
    code_snippet:     str = ""
    file_path:        str = ""


@dataclass
class FixResult:
    diagnosis:      str
    fix_type:       str
    corrected_code: Optional[str]
    file_path:      Optional[str]
    instructions:   str
    prevention:     str = ""
    success:        bool = False


class ErrorInterceptor:
    @staticmethod
    def capture(
        exc: Exception,
        context_snapshot: dict,
        command: str = "",
        file_path: str = "",
    ) -> AppError:
        tb = traceback.format_exc()
        code_snippet = ""
        if file_path and Path(file_path).exists():
            try:
                code_snippet = Path(file_path).read_text(encoding="utf-8")[:3000]
            except Exception:
                pass
        return AppError(
            message=str(exc),
            traceback=tb,
            context_snapshot=context_snapshot,
            command=command,
            code_snippet=code_snippet,
            file_path=file_path,
        )


class FixApplicator:
    @staticmethod
    def apply(fix: FixResult, project_path: str) -> bool:
        if not fix.corrected_code or not fix.file_path:
            return False
        target = Path(project_path) / fix.file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(fix.corrected_code, encoding="utf-8")
            return True
        except Exception:
            return False

    @staticmethod
    def apply_via_manager(fix: FixResult, project_id: str, file_manager) -> bool:
        if not fix.corrected_code or not fix.file_path:
            return False
        try:
            file_manager.save_file(project_id, fix.file_path, fix.corrected_code)
            return True
        except Exception:
            return False


class AIDebugger:
    def __init__(
        self,
        app_context: AppContext,
        ai_gateway:  AIGateway,
        registry:    PromptRegistry,
        parser:      ResponseParser,
    ) -> None:
        self._ctx      = app_context
        self._ai       = ai_gateway
        self._registry = registry
        self._parser   = parser

    def _log(self, method: str, *args, **kwargs) -> None:
        logger = getattr(self._ctx, "logger", None)
        if logger and hasattr(logger, method):
            try:
                getattr(logger, method)(*args, **kwargs)
            except Exception:
                pass

    async def handle_error(
        self, error: AppError, context: AppContext
    ) -> FixResult:
        import json
        chat_id = await self._ai.create_chat("[debugging]")

        variables = {
            "PROJECT_CONTEXT": json.dumps(
                context.full_context, ensure_ascii=False
            )[:4000],
            "COMMAND":       error.command or "N/A",
            "ERROR_MESSAGE": f"{error.message}\n\n{error.traceback}",
            "CODE_SNIPPET":  error.code_snippet or "N/A",
            "FULL_CONTEXT":  json.dumps(context.full_context, ensure_ascii=False)[:2000],
        }

        prompt = self._registry.fill("debugging_cli", variables)
        system = get_system_prompt("debugging_cli")

        self._log("log_ai_request",
                  provider=getattr(self._ai, "_provider", ""),
                  model=getattr(self._ai, "_get_model", lambda: "")(),
                  stage="debugging_cli",
                  prompt=prompt,
                  project_id=context.project_id)

        raw = ""
        try:
            async for token in self._ai.send_message(
                chat_id, prompt, system=system,
                stage="debugging_cli", project_id=context.project_id,
            ):
                raw += token
        except Exception as exc:
            self._log("log_ai_error", provider="", stage="debugging_cli", error=str(exc))
            return FixResult(
                diagnosis=f"Ошибка запроса к ИИ: {exc}",
                fix_type="api_error",
                corrected_code=None,
                file_path=None,
                instructions="Проверьте соединение и API-ключ",
            )

        self._log("log_ai_response",
                  provider=getattr(self._ai, "_provider", ""),
                  stage="debugging_cli",
                  response=raw)

        # Парсинг ответа
        parsed = self._parser.parse_proto_v1(raw)
        if parsed:
            data = parsed.get("data", {})
        else:
            data = self._parser.parse_json(raw)
            if not isinstance(data, dict):
                data = {"diagnosis": raw[:500], "instructions": raw}

        return FixResult(
            diagnosis=data.get("diagnosis", "Анализ недоступен"),
            fix_type=data.get("fix_type", "other"),
            corrected_code=data.get("corrected_code"),
            file_path=data.get("file_path"),
            instructions=data.get("instructions", ""),
            prevention=data.get("prevention", ""),
            success=bool(data.get("corrected_code")),
        )

    async def apply_fix(self, fix: FixResult, project_path: str) -> bool:
        return FixApplicator.apply(fix, project_path)
