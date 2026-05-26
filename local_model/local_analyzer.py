"""
local_model/local_analyzer.py — LocalAnalyzer

Локальная лёгкая модель для анализа и коррекции запросов ПЕРЕД отправкой в ИИ.
Backends (автовыбор):
  1. Ollama — если запущен (qwen2.5:0.5b, gemma2:2b, ...)
  2. Rule-based — всегда работает, без зависимостей
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class AnalysisResult:
    original_prompt:    str
    corrected_prompt:   str
    improvements:       List[str] = field(default_factory=list)
    tokens_saved:       int = 0
    original_tokens:    int = 0
    corrected_tokens:   int = 0
    backend_used:       str = "rule_based"
    confidence:         float = 1.0
    processing_time_ms: float = 0.0

    @property
    def was_modified(self) -> bool:
        return self.corrected_prompt.strip() != self.original_prompt.strip()

    @property
    def savings_percent(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return self.tokens_saved / self.original_tokens * 100

    @staticmethod
    def count_tokens(text: str) -> int:
        if not text:
            return 0
        latin = sum(1 for c in text if ord(c) < 256)
        cyrillic = len(text) - latin
        return max(1, latin // 4 + cyrillic // 2)


# ── Rule-based (no dependencies) ──────────────────────────

class RuleBasedAnalyzer:
    _REDUNDANT = [
        (r"пожалуйста,?\s*", ""),
        (r"будь добр,?\s*", ""),
        (r"если можно,?\s*", ""),
        (r"мне нужно чтобы\s*", ""),
        (r"\bplease,?\s*", ""),
        (r"could you\s+please\s*", ""),
        (r"я хочу чтобы ты\s*", ""),
        (r"\bты должен\s*", ""),
        (r"\bcan you\s*", ""),
    ]
    _TECH = [
        (r"\bпитон[аеуёои]?\b", "Python"),
        (r"\bджанго\b", "Django"),
        (r"\bфастапи\b", "FastAPI"),
        (r"\bтелеграм[а-яё]?\b", "Telegram"),
        (r"\bдокер[а-яё]?\b", "Docker"),
        (r"\bапи\b", "API"),
        (r"\bбэкенд[а-яё]?\b", "backend"),
        (r"\bфронтенд[а-яё]?\b", "frontend"),
        (r"\bреакт[а-яё]?\b", "React"),
        (r"\bвуе\b", "Vue"),
        (r"\bпостгрес[а-яё]?\b", "PostgreSQL"),
        (r"\bмонго[а-яё]?\b", "MongoDB"),
        (r"\bредис[а-яё]?\b", "Redis"),
    ]

    def analyze(self, prompt: str, stage: str = "") -> AnalysisResult:
        t0 = time.monotonic()
        orig_tokens = AnalysisResult.count_tokens(prompt)
        corrected = prompt
        improvements: List[str] = []

        for pat, rep in self._REDUNDANT:
            new = re.sub(pat, rep, corrected, flags=re.IGNORECASE)
            if new != corrected:
                improvements.append("Удалены вежливые вставки")
                corrected = new

        for pat, rep in self._TECH:
            new = re.sub(pat, rep, corrected, flags=re.IGNORECASE)
            if new != corrected:
                improvements.append(f"Нормализован термин: {rep}")
                corrected = new

        corrected, dups = self._dedup(corrected)
        if dups:
            improvements.append(f"Удалено {dups} дублирующихся предложений")

        corrected = re.sub(r"\n{3,}", "\n\n", corrected)
        corrected = re.sub(r" {2,}", " ", corrected).strip()

        corr_tokens = AnalysisResult.count_tokens(corrected)
        ms = (time.monotonic() - t0) * 1000
        return AnalysisResult(
            original_prompt=prompt,
            corrected_prompt=corrected,
            improvements=improvements,
            tokens_saved=max(0, orig_tokens - corr_tokens),
            original_tokens=orig_tokens,
            corrected_tokens=corr_tokens,
            backend_used="rule_based",
            confidence=0.85,
            processing_time_ms=ms,
        )

    @staticmethod
    def _dedup(text: str) -> Tuple[str, int]:
        parts = re.split(r"(?<=[.!?])\s+", text)
        seen: set[str] = set()
        unique: List[str] = []
        dups = 0
        for s in parts:
            k = re.sub(r"\s+", " ", s.strip().lower())[:80]
            if k and k not in seen:
                seen.add(k)
                unique.append(s)
            elif k:
                dups += 1
        return " ".join(unique), dups


# ── Ollama backend ─────────────────────────────────────────

class OllamaAnalyzer:
    PREFERRED = [
        "qwen2.5:0.5b",
        "qwen2.5:1.5b",
        "gemma2:2b",
        "llama3.2:1b",
        "phi3.5:mini",
        "mistral:7b",
    ]

    def __init__(self) -> None:
        self._model: Optional[str] = None
        self._available = self._detect()

    def _detect(self) -> bool:
        try:
            import urllib.request, json
            resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            data = json.loads(resp.read())
            installed = {m["name"] for m in data.get("models", [])}
            for m in self.PREFERRED:
                if m in installed:
                    self._model = m
                    return True
            if installed:
                self._model = sorted(installed)[0]
                return True
        except Exception:
            pass
        return False

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def model_name(self) -> str:
        return self._model or "none"

    def analyze(self, prompt: str, stage: str = "") -> AnalysisResult:
        import json, urllib.request
        t0 = time.monotonic()
        orig_tokens = AnalysisResult.count_tokens(prompt)

        system = (
            "You are a prompt optimizer for an AI code generation system. "
            "Improve the user prompt: remove redundant politeness, normalize tech terms, "
            "remove duplicates, keep all functional requirements. "
            "Respond ONLY with valid JSON: "
            "{\"corrected\": \"<improved text>\", "
            "\"improvements\": [\"change 1\", ...], "
            "\"confidence\": 0.0}"
        )
        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": "Optimize:\n\n" + prompt[:1500]},
            ],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        }).encode()

        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=30)
            raw = json.loads(resp.read())["message"]["content"].strip()
            parsed = json.loads(raw)
            corrected = parsed.get("corrected", prompt)
            corr_tokens = AnalysisResult.count_tokens(corrected)
            ms = (time.monotonic() - t0) * 1000
            return AnalysisResult(
                original_prompt=prompt,
                corrected_prompt=corrected,
                improvements=parsed.get("improvements", []),
                tokens_saved=max(0, orig_tokens - corr_tokens),
                original_tokens=orig_tokens,
                corrected_tokens=corr_tokens,
                backend_used=f"ollama:{self._model}",
                confidence=float(parsed.get("confidence", 0.8)),
                processing_time_ms=ms,
            )
        except Exception as exc:
            r = RuleBasedAnalyzer().analyze(prompt, stage)
            r.improvements.append(f"ollama error: {str(exc)[:60]}")
            return r


# ── Facade ────────────────────────────────────────────────

class LocalAnalyzer:
    """
    Автоматически выбирает лучший backend.
    Никогда не поднимает исключений.
    """

    def __init__(
        self,
        llama_model_path: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._rule = RuleBasedAnalyzer()
        self._active = self._rule
        self._backend = "rule_based"

        if not enabled:
            return

        try:
            ol = OllamaAnalyzer()
            if ol.is_available:
                self._active = ol
                self._backend = f"ollama:{ol.model_name}"
                return
        except Exception:
            pass

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_ml_backend(self) -> bool:
        return self._backend.startswith("ollama")

    def analyze(self, prompt: str, stage: str = "") -> AnalysisResult:
        if not self._enabled:
            t = AnalysisResult.count_tokens(prompt)
            return AnalysisResult(
                original_prompt=prompt, corrected_prompt=prompt,
                original_tokens=t, corrected_tokens=t, backend_used="disabled",
            )
        try:
            return self._active.analyze(prompt, stage)
        except Exception as exc:
            r = self._rule.analyze(prompt, stage)
            r.improvements.append(f"backend error, fallback: {str(exc)[:40]}")
            return r

    def analyze_and_log(
        self, prompt: str, stage: str = "", logger=None
    ) -> AnalysisResult:
        result = self.analyze(prompt, stage)
        if logger and result.was_modified:
            try:
                logger.info(
                    f"LocalAnalyzer [{self._backend}] stage={stage} "
                    f"saved={result.tokens_saved}tok ({result.savings_percent:.1f}%)"
                )
            except Exception:
                pass
        return result
