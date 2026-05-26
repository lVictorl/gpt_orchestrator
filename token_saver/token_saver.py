"""
token_saver/token_saver.py — TokenSaver

Исправление #11: Система экономии токенов без потери качества генерации.
Подключается к основному проекту через стандартный API.

Методы:
  - compress_context: убирает дублирующиеся части из FULL_CONTEXT
  - summarize_stage: суммаризирует длинный ответ этапа
  - select_minimal_context: выбирает только нужные для этапа поля контекста
"""
from __future__ import annotations

import json
import re
from typing import Any


# Максимальный размер контекста на этап (символы)
_MAX_CONTEXT_CHARS = 8000

# Поля, необходимые для каждого этапа
_STAGE_CONTEXT_KEYS: dict[str, list[str]] = {
    "user_clarification": ["user_task", "problem_analysis"],
    "global_spec_and_api": ["user_task", "problem_analysis", "user_clarification"],
    "subproject_prompts_generation": ["global_spec_and_api"],
    "subproject_implementation_trigger": ["global_spec_and_api", "subproject_prompts_generation"],
    "code_block_generation": ["global_spec_and_api", "subproject_prompts_generation"],
    "optimization": ["code_block_generation"],
    "unit_tests": ["code_block_generation", "global_spec_and_api"],
    "deployment_commands": ["global_spec_and_api", "code_block_generation"],
    "readme_generation": ["user_task", "global_spec_and_api"],
    "debugging_cli": ["user_task"],
}


class TokenSaver:
    """Уменьшает объём контекста, передаваемого в промпты."""

    def compress_context(self, full_context: dict) -> dict:
        """
        Убирает дублирующиеся и избыточные данные из full_context.
        Возвращает сжатый словарь.
        """
        compressed: dict[str, Any] = {}
        seen_texts: set[str] = set()

        for stage, data in full_context.items():
            if isinstance(data, dict):
                clean: dict = {}
                for k, v in data.items():
                    text = str(v)
                    if text not in seen_texts and len(text) > 5:
                        seen_texts.add(text)
                        # Обрезать очень длинные значения
                        clean[k] = text[:2000] if len(text) > 2000 else v
                compressed[stage] = clean
            else:
                compressed[stage] = data

        return compressed

    def select_minimal_context(self, stage: str, full_context: dict) -> dict:
        """
        Для данного этапа выбирает только необходимые ключи контекста.
        Уменьшает размер промпта.
        """
        needed_keys = _STAGE_CONTEXT_KEYS.get(stage)
        if not needed_keys:
            return full_context  # неизвестный этап — отдаём всё

        minimal = {k: full_context[k] for k in needed_keys if k in full_context}
        return minimal

    def summarize_stage_result(self, stage: str, raw_response: str) -> str:
        """
        Если ответ очень длинный — создаём краткое резюме для передачи далее.
        Применяется только к этапам с большим выводом.
        """
        if len(raw_response) <= _MAX_CONTEXT_CHARS:
            return raw_response
        # Взять первые и последние части (самые информативные)
        head = raw_response[:_MAX_CONTEXT_CHARS // 2]
        tail = raw_response[-((_MAX_CONTEXT_CHARS // 2) - 50):]
        return f"{head}\n\n[... сокращено ...]\n\n{tail}"

    def context_to_compact_str(self, context: dict) -> str:
        """Сериализует контекст в компактный JSON (без лишних пробелов)."""
        return json.dumps(context, ensure_ascii=False, separators=(",", ":"))

    def estimate_tokens(self, text: str) -> int:
        """Грубая оценка числа токенов (1 токен ≈ 4 символа)."""
        return len(text) // 4
