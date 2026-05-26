"""
token_saver/token_optimizer.py — TokenOptimizer

Полноценный сервис оптимизации токенов:
  - Подсчёт токенов по тикенизатору (approx 4 chars = 1 token)
  - Сжатие контекста: только нужные поля для каждого этапа
  - Дедупликация: убирает повторяющиеся блоки текста
  - Суммаризация длинных ответов предыдущих этапов
  - Расчёт стоимости по модели (DeepSeek, OpenAI, Anthropic)
  - Отчёт об экономии
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Прайс-лист моделей (USD за 1M токенов) ──────────────

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # DeepSeek
    "deepseek-chat":         {"input": 0.27,   "output": 1.10},
    "deepseek-coder":        {"input": 0.27,   "output": 1.10},
    "deepseek-reasoner":     {"input": 0.55,   "output": 2.19},
    "deepseek-v3":           {"input": 0.27,   "output": 1.10},
    "deepseek-r1":           {"input": 0.55,   "output": 2.19},
    "deepseek-r1-zero":      {"input": 0.55,   "output": 2.19},
    # OpenAI
    "gpt-4o":                {"input": 2.50,   "output": 10.00},
    "gpt-4o-mini":           {"input": 0.15,   "output": 0.60},
    "gpt-4-turbo":           {"input": 10.00,  "output": 30.00},
    "gpt-3.5-turbo":         {"input": 0.50,   "output": 1.50},
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514":   {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5-20251001":{"input": 0.80, "output": 4.00},
    "claude-haiku-3-5-20241022":{"input": 0.80, "output": 4.00},
}

# Только нужные ключи контекста для каждого этапа
_STAGE_CONTEXT_KEYS: Dict[str, List[str]] = {
    "user_clarification":              ["user_task", "problem_analysis"],
    "architecture_analysis":           ["user_task", "problem_analysis", "user_clarification"],
    "project_plan":                    ["user_task", "problem_analysis", "user_clarification", "architecture_analysis"],
    "global_spec_and_api":             ["user_task", "user_clarification", "architecture_analysis", "project_plan"],
    "subproject_prompts_generation":   ["global_spec_and_api"],
    "subproject_implementation_trigger": ["global_spec_and_api", "subproject_prompts_generation"],
    "code_block_generation":           ["global_spec_and_api", "subproject_prompts_generation",
                                        "subproject_implementation_trigger"],
    "optimization":                    ["code_block_generation"],
    "unit_tests":                      ["code_block_generation", "global_spec_and_api"],
    "refactoring":                     ["code_block_generation", "optimization"],
    "deployment_commands":             ["global_spec_and_api", "code_block_generation"],
    "readme_generation":               ["user_task", "global_spec_and_api"],
    "debugging_cli":                   ["user_task"],
    "project_critique":                ["user_task", "global_spec_and_api",
                                        "code_block_generation", "unit_tests"],
}

_MAX_VALUE_CHARS    = 1500   # макс символов на одно поле контекста
_MAX_CONTEXT_CHARS  = 6000   # макс символов всего контекста


@dataclass
class OptimizationReport:
    original_tokens:  int   = 0
    optimized_tokens: int   = 0
    saved_tokens:     int   = 0
    saving_percent:   float = 0.0
    cost_original_usd:  float = 0.0
    cost_optimized_usd: float = 0.0
    cost_saved_usd:     float = 0.0
    techniques_applied: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"Токены: {self.original_tokens} → {self.optimized_tokens} "
            f"(-{self.saved_tokens}, -{self.saving_percent:.1f}%) | "
            f"Экономия: ${self.cost_saved_usd:.4f}"
        )


class TokenOptimizer:
    """
    Сервис оптимизации запросов по токенам.
    Применяется к каждому промпту перед отправкой в ИИ.
    """

    def __init__(self, model: str = "deepseek-chat") -> None:
        self._model = model
        self._total_input_tokens  = 0
        self._total_output_tokens = 0

    def set_model(self, model: str) -> None:
        self._model = model

    # ── Основной метод ─────────────────────────────────────

    def optimize_prompt(
        self, stage: str, prompt: str, full_context: dict
    ) -> Tuple[str, OptimizationReport]:
        """
        Оптимизировать промпт для этапа.
        Возвращает (оптимизированный_промпт, отчёт).
        """
        techniques: List[str] = []
        original_tokens = self.count_tokens(prompt)

        # 1. Выбрать минимальный контекст для этапа
        minimal_ctx = self.select_minimal_context(stage, full_context)
        if len(minimal_ctx) < len(full_context):
            techniques.append("minimal_context")

        # 2. Сжать значения контекста
        compressed_ctx = self.compress_context(minimal_ctx)
        if compressed_ctx != minimal_ctx:
            techniques.append("value_truncation")

        # 3. Подставить оптимизированный контекст в промпт
        ctx_json = json.dumps(compressed_ctx, ensure_ascii=False, separators=(",", ":"))
        optimized = re.sub(
            r'\{\{FULL_CONTEXT\}\}',
            ctx_json,
            prompt
        )

        # 4. Дедупликация текста
        deduped = self._deduplicate(optimized)
        if len(deduped) < len(optimized):
            techniques.append("deduplication")
            optimized = deduped

        # 5. Нормализация пробелов
        normalized = self._normalize_whitespace(optimized)
        if len(normalized) < len(optimized):
            techniques.append("whitespace_normalization")
            optimized = normalized

        optimized_tokens = self.count_tokens(optimized)
        report = self._build_report(original_tokens, optimized_tokens, techniques)
        return optimized, report

    def optimize_context_string(
        self, stage: str, full_context: dict
    ) -> Tuple[str, OptimizationReport]:
        """
        Оптимизировать FULL_CONTEXT JSON-строку.
        Используется при подстановке в промпты.
        """
        original_str = json.dumps(full_context, ensure_ascii=False)
        original_tokens = self.count_tokens(original_str)

        minimal  = self.select_minimal_context(stage, full_context)
        compressed = self.compress_context(minimal)
        result_str = json.dumps(compressed, ensure_ascii=False, separators=(",", ":"))

        optimized_tokens = self.count_tokens(result_str)
        techniques = ["minimal_context", "value_truncation", "compact_json"]
        report = self._build_report(original_tokens, optimized_tokens, techniques)
        return result_str, report

    # ── Методы оптимизации ──────────────────────────────────

    def select_minimal_context(self, stage: str, full_context: dict) -> dict:
        """Выбрать только нужные ключи контекста для данного этапа."""
        needed = _STAGE_CONTEXT_KEYS.get(stage)
        if not needed:
            return full_context
        return {k: full_context[k] for k in needed if k in full_context}

    def compress_context(self, context: dict) -> dict:
        """Обрезать длинные значения, убрать дублирование."""
        compressed: Dict[str, Any] = {}
        seen_hashes: set = set()

        for stage_key, data in context.items():
            if isinstance(data, dict):
                clean: Dict[str, Any] = {}
                for k, v in data.items():
                    text = str(v)
                    text_hash = hash(text[:200])
                    if text_hash in seen_hashes:
                        continue
                    seen_hashes.add(text_hash)
                    if len(text) > _MAX_VALUE_CHARS:
                        # Оставить начало и конец — самые информативные части
                        half = _MAX_VALUE_CHARS // 2
                        text = text[:half] + "…" + text[-half:]
                    clean[k] = text if isinstance(v, str) else v
                compressed[stage_key] = clean
            else:
                compressed[stage_key] = data

        # Если всё равно слишком большой — обрезать старые этапы
        total_chars = len(json.dumps(compressed, ensure_ascii=False))
        if total_chars > _MAX_CONTEXT_CHARS:
            keys = list(compressed.keys())
            while (
                len(json.dumps(compressed, ensure_ascii=False)) > _MAX_CONTEXT_CHARS
                and len(keys) > 1
            ):
                oldest = keys.pop(0)
                compressed.pop(oldest, None)

        return compressed

    def summarize_long_response(self, stage: str, raw: str) -> str:
        """Суммаризировать длинный ответ для передачи в следующий этап."""
        if len(raw) <= _MAX_VALUE_CHARS * 2:
            return raw
        half = _MAX_VALUE_CHARS
        return raw[:half] + f"\n[...сокращено {len(raw) - half*2} символов...]\n" + raw[-half:]

    def _deduplicate(self, text: str) -> str:
        """Убрать повторяющиеся абзацы."""
        paragraphs = text.split("\n\n")
        seen: set = set()
        result: List[str] = []
        for para in paragraphs:
            key = para.strip()[:100]
            if key and key not in seen:
                seen.add(key)
                result.append(para)
        return "\n\n".join(result)

    def _normalize_whitespace(self, text: str) -> str:
        """Убрать тройные переносы строк, лишние пробелы."""
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    # ── Подсчёт токенов ────────────────────────────────────

    @staticmethod
    def count_tokens(text: str) -> int:
        """
        Приблизительный подсчёт токенов.
        Правило: ~4 символа = 1 токен для латиницы,
                 ~2 символа = 1 токен для кириллицы.
        """
        if not text:
            return 0
        latin_chars   = sum(1 for c in text if ord(c) < 256)
        cyrillic_chars = len(text) - latin_chars
        return max(1, (latin_chars // 4) + (cyrillic_chars // 2))

    @staticmethod
    def count_tokens_precise(text: str) -> int:
        """Попытка использовать tiktoken если доступен."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            return TokenOptimizer.count_tokens(text)

    # ── Стоимость ──────────────────────────────────────────

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: Optional[str] = None
    ) -> float:
        """Рассчитать стоимость запроса в USD."""
        m = model or self._model
        pricing = MODEL_PRICING.get(m)
        if not pricing:
            # Неизвестная модель — использовать среднее
            pricing = {"input": 1.0, "output": 3.0}
        input_cost  = input_tokens  / 1_000_000 * pricing["input"]
        output_cost = output_tokens / 1_000_000 * pricing["output"]
        return input_cost + output_cost

    def get_model_pricing(self, model: Optional[str] = None) -> Dict[str, float]:
        """Получить прайс для модели."""
        m = model or self._model
        return MODEL_PRICING.get(m, {"input": 0.0, "output": 0.0})

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Накопить статистику использования."""
        self._total_input_tokens  += input_tokens
        self._total_output_tokens += output_tokens

    def get_total_cost(self) -> float:
        return self.calculate_cost(
            self._total_input_tokens, self._total_output_tokens
        )

    def get_total_tokens(self) -> Tuple[int, int]:
        return self._total_input_tokens, self._total_output_tokens

    def reset_stats(self) -> None:
        self._total_input_tokens  = 0
        self._total_output_tokens = 0

    # ── Helpers ────────────────────────────────────────────

    def _build_report(
        self, original: int, optimized: int, techniques: List[str]
    ) -> OptimizationReport:
        saved = max(0, original - optimized)
        pct   = (saved / original * 100) if original > 0 else 0.0
        cost_orig = self.calculate_cost(original, 0)
        cost_opt  = self.calculate_cost(optimized, 0)
        return OptimizationReport(
            original_tokens=original,
            optimized_tokens=optimized,
            saved_tokens=saved,
            saving_percent=pct,
            cost_original_usd=cost_orig,
            cost_optimized_usd=cost_opt,
            cost_saved_usd=max(0.0, cost_orig - cost_opt),
            techniques_applied=techniques,
        )

    @staticmethod
    def list_models_by_provider() -> Dict[str, List[Dict]]:
        """Список всех моделей с ценами, сгруппированных по провайдеру."""
        providers: Dict[str, List[Dict]] = {
            "deepseek": [], "openai": [], "anthropic": []
        }
        for model, pricing in MODEL_PRICING.items():
            if "deepseek" in model:
                providers["deepseek"].append({
                    "model": model,
                    "input_per_1m":  pricing["input"],
                    "output_per_1m": pricing["output"],
                })
            elif "gpt" in model:
                providers["openai"].append({
                    "model": model,
                    "input_per_1m":  pricing["input"],
                    "output_per_1m": pricing["output"],
                })
            elif "claude" in model:
                providers["anthropic"].append({
                    "model": model,
                    "input_per_1m":  pricing["input"],
                    "output_per_1m": pricing["output"],
                })
        return providers
