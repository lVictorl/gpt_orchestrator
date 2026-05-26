"""
core/protocol.py — Единый протокол GPT_PROTO_V1 v2

Добавлено:
  - Явные примеры для каждого типа этапа
  - STRICT_JSON_RULES — жёсткие правила на форматирование
  - build_stage_prompt() — генерирует системный промпт под конкретный этап
  - Шаблоны data-полей для каждого типа этапа
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class ProtoStatus(Enum):
    OK      = "OK"
    WARN    = "WARN"
    ERROR   = "ERROR"
    PARTIAL = "PARTIAL"


class Confidence(Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


@dataclass
class ProtoEnvelope:
    proto:           str  = "GPT_PROTO_V1"
    stage:           str  = ""
    status:          str  = "OK"
    confidence:      str  = "HIGH"
    summary:         str  = ""
    data:            dict = field(default_factory=dict)
    warnings:        list = field(default_factory=list)
    next_stage_hint: str  = ""
    tokens_used:     int  = 0
    timestamp:       str  = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "ProtoEnvelope":
        valid = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in valid})

    def is_ok(self) -> bool:
        return self.status in ("OK", "WARN", "PARTIAL")

    def has_warnings(self) -> bool:
        return bool(self.warnings) or self.status == "WARN"

    def confidence_emoji(self) -> str:
        return {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(self.confidence, "⚪")

    def status_emoji(self) -> str:
        return {"OK": "✅", "WARN": "⚠️", "ERROR": "❌", "PARTIAL": "🔶"}.get(
            self.status, "❓"
        )


# ── Жёсткие правила JSON-ответа ──────────────────────────

_STRICT_JSON_RULES = """\
КРИТИЧЕСКИЕ ПРАВИЛА ОТВЕТА:
1. Отвечай ТОЛЬКО валидным JSON. Никакого текста до или после JSON.
2. НЕ используй markdown-блоки (``` json, ```). Только чистый JSON.
3. Все строки в JSON должны быть корректно экранированы (\\n, \\", \\\\).
4. Не включай комментарии в JSON.
5. Поле "proto" ВСЕГДА равно "GPT_PROTO_V1".
6. Поле "stage" — точное имя текущего этапа.
7. Поле "data" содержит реальные данные, а не заглушки.
8. Если не можешь выполнить задачу — верни status="ERROR" с описанием в data.error.
"""

# ── Шаблоны data для каждого типа этапа ──────────────────

_DATA_TEMPLATES: Dict[str, str] = {
    "analysis": """\
    "data": {
      "core_problem": "<суть проблемы>",
      "goals": ["<цель 1>", "<цель 2>"],
      "constraints": ["<ограничение>"],
      "tech_stack": {"language": "Python", "frameworks": []},
      "questions": [{"id": "q1", "question": "<вопрос>", "default": "<ответ по умолчанию>"}]
    }""",

    "spec": """\
    "data": {
      "architecture_type": "monolith|microservices|serverless",
      "tech_stack": {"backend": "", "frontend": "", "database": "", "devops": ""},
      "modules": [{"name": "", "responsibility": "", "api_endpoints": []}],
      "dependencies": ["package==version"]
    }""",

    "code": """\
    "data": {
      "files": [
        {
          "filename": "src/module_name.py",
          "content": "<полный код файла>",
          "description": "<назначение файла>"
        }
      ],
      "dependencies": ["package==version"],
      "notes": "<заметки об имплементации>"
    }""",

    "tests": """\
    "data": {
      "files": [
        {
          "filename": "tests/test_module.py",
          "content": "<полный код тестов>",
          "description": "Unit/integration тесты для module_name"
        }
      ],
      "coverage_target": 80,
      "test_framework": "pytest"
    }""",

    "critique": """\
    "data": {
      "overall_score": <0-100>,
      "compliance_percent": <0-100>,
      "grades": {
        "architecture": <0-10>, "code_quality": <0-10>, "test_coverage": <0-10>,
        "documentation": <0-10>, "security": <0-10>, "performance": <0-10>,
        "completeness": <0-10>
      },
      "test_cases": [
        {
          "id": "TC-001",
          "category": "unit|integration|e2e|security|performance",
          "description": "<что тестируется>",
          "preconditions": "<предусловия>",
          "steps": ["<шаг 1>", "<шаг 2>"],
          "expected_result": "<ожидаемый результат>",
          "priority": "critical|high|medium|low"
        }
      ],
      "strengths": ["<+>"],
      "weaknesses": ["<->"],
      "critical_issues": ["<!>"],
      "recommendations": ["<↗>"],
      "missing_features": ["<?>"]
    }""",

    "script": """\
    "data": {
      "files": [
        {
          "filename": "setup.sh",
          "content": "#!/bin/bash\\n<полный скрипт>",
          "description": "Скрипт установки и деплоя"
        }
      ],
      "requirements": ["<зависимость>"]
    }""",
}


def build_stage_system_prompt(stage: str) -> str:
    """Генерирует системный промпт под конкретный этап."""
    if stage == "project_critique":
        data_template = _DATA_TEMPLATES["critique"]
    elif stage in ("code_block_generation", "optimization", "refactoring"):
        data_template = _DATA_TEMPLATES["code"]
    elif stage in ("unit_tests",):
        data_template = _DATA_TEMPLATES["tests"]
    elif stage in ("deployment_commands",):
        data_template = _DATA_TEMPLATES["script"]
    elif stage in ("global_spec_and_api", "architecture_analysis", "project_plan"):
        data_template = _DATA_TEMPLATES["spec"]
    else:
        data_template = _DATA_TEMPLATES["analysis"]

    return f"""\
Ты — AI-агент в системе GPT-Orchestrator. Текущий этап: {stage}.

{_STRICT_JSON_RULES}

ФОРМАТ ОТВЕТА для этапа "{stage}":
{{
  "proto": "GPT_PROTO_V1",
  "stage": "{stage}",
  "status": "OK",
  "confidence": "HIGH",
  "summary": "<краткий итог 1-2 предложения>",
{data_template},
  "warnings": [],
  "next_stage_hint": "<что важно для следующего этапа>",
  "tokens_used": 0,
  "timestamp": "<ISO8601>"
}}

Для этапа "{stage}" поле "data" должно содержать реальные данные, не заглушки.
Код в "content" должен быть ПОЛНЫМ и РАБОЧИМ — не сокращай его.
"""


# ── Системные промпты для быстрого использования ─────────

def get_system_prompt(stage: str) -> str:
    """Получить системный промпт для этапа."""
    return build_stage_system_prompt(stage)


# Алиасы для обратной совместимости
PROTOCOL_SYSTEM_PROMPT = build_stage_system_prompt("problem_analysis")
PROTOCOL_CODE_SYSTEM   = build_stage_system_prompt("code_block_generation")
CRITIQUE_SYSTEM_PROMPT = build_stage_system_prompt("project_critique")
