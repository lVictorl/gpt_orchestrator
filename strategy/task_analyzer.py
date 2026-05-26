"""
strategy/task_analyzer.py — TaskAnalyzer + стратегии

Исправления:
  - #8  Добавлены новые TaskType: ANDROID, BOT, ADDON, ADVERTISING
  - #22 Добавлены стратегии: AndroidStrategy, BotStrategy, AddonStrategy,
        AdvertisingStrategy, AutomationStrategy
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List


# ─────────────── TaskType ────────────────────────────────

class TaskType(Enum):
    CODE = "code"
    COURSE = "course"
    BOOK = "book"
    REPORT = "report"
    DEBUG = "debug"
    SCRIPT = "script"
    ANDROID = "android"
    BOT = "bot"
    ADDON = "addon"
    ADVERTISING = "advertising"
    AUTOMATION = "automation"
    OTHER = "other"


# ─────────────── StrategyBase ───────────────────────────

class StrategyBase(ABC):
    @abstractmethod
    def get_pipeline_stages(self) -> List[str]: ...

    @abstractmethod
    def get_prompt_overrides(self) -> Dict[str, str]: ...

    def get_task_type(self) -> TaskType:
        return TaskType.OTHER


# ─────────────── Stage sets ─────────────────────────────

_BASE_STAGES = [
    "problem_analysis",
    "user_clarification",
]

_FULL_CODE_STAGES = _BASE_STAGES + [
    "global_spec_and_api",
    "subproject_prompts_generation",
    "subproject_implementation_trigger",
    "code_block_generation",
    "optimization",
    "unit_tests",
    "deployment_commands",
    "readme_generation",
]

_SIMPLE_CODE_STAGES = _BASE_STAGES + [
    "code_block_generation",
    "unit_tests",
    "readme_generation",
]

_DEBUG_STAGES = [
    "problem_analysis",
    "debugging_cli",
]


# ─────────────── Concrete strategies ────────────────────

class CodeStrategy(StrategyBase):
    """Полный цикл разработки программного продукта."""
    def get_pipeline_stages(self) -> List[str]:
        return _FULL_CODE_STAGES

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {}

    def get_task_type(self) -> TaskType:
        return TaskType.CODE


class CourseStrategy(StrategyBase):
    """Создание учебного курса."""
    def get_pipeline_stages(self) -> List[str]:
        return _BASE_STAGES + ["code_block_generation", "readme_generation"]

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {
            "problem_analysis": (
                "Ты — методолог онлайн-курсов. Проанализируй запрос на создание учебного курса "
                "и выдели: цель курса, целевую аудиторию, количество модулей, формат подачи."
            ),
        }

    def get_task_type(self) -> TaskType:
        return TaskType.COURSE


class DebugStrategy(StrategyBase):
    """Отладка существующего приложения."""
    def get_pipeline_stages(self) -> List[str]:
        return _DEBUG_STAGES

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {}

    def get_task_type(self) -> TaskType:
        return TaskType.DEBUG


class ScriptStrategy(StrategyBase):
    """Генерация скриптов bash/powershell."""
    def get_pipeline_stages(self) -> List[str]:
        return [
            "problem_analysis",
            "code_block_generation",
            "deployment_commands",
        ]

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {}

    def get_task_type(self) -> TaskType:
        return TaskType.SCRIPT


class AndroidStrategy(StrategyBase):
    """Создание Android-приложения (дополнение шаблона). Исправление #22."""
    def get_pipeline_stages(self) -> List[str]:
        return _BASE_STAGES + [
            "global_spec_and_api",
            "code_block_generation",
            "unit_tests",
            "deployment_commands",
            "readme_generation",
        ]

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {
            "problem_analysis": (
                "Ты — Android-разработчик. Проанализируй запрос на создание Android-приложения. "
                "Определи: минимальную версию API, UI-фреймворк (Jetpack Compose / XML), "
                "необходимые разрешения, ключевые экраны и функции."
            ),
        }

    def get_task_type(self) -> TaskType:
        return TaskType.ANDROID


class BotStrategy(StrategyBase):
    """Создание Telegram-бота или другого чат-бота. Исправление #22."""
    def get_pipeline_stages(self) -> List[str]:
        return _BASE_STAGES + [
            "code_block_generation",
            "unit_tests",
            "deployment_commands",
            "readme_generation",
        ]

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {
            "problem_analysis": (
                "Ты — разработчик чат-ботов. Проанализируй запрос на создание бота. "
                "Определи: платформу (Telegram/Discord/VK), команды и сценарии взаимодействия, "
                "интеграции с внешними сервисами, механизм хранения данных."
            ),
        }

    def get_task_type(self) -> TaskType:
        return TaskType.BOT


class AddonStrategy(StrategyBase):
    """Написание аддона для GPT-Orchestrator. Исправление #22."""
    def get_pipeline_stages(self) -> List[str]:
        return _BASE_STAGES + [
            "global_spec_and_api",
            "code_block_generation",
            "unit_tests",
            "readme_generation",
        ]

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {
            "problem_analysis": (
                "Ты — архитектор расширений GPT-Orchestrator. "
                "Аддон должен соответствовать публичному API приложения. "
                "Определи: точку интеграции (новая стратегия / новый диалог / новый пайплайн-этап), "
                "необходимые интерфейсы и сигнатуры."
            ),
        }

    def get_task_type(self) -> TaskType:
        return TaskType.ADDON


class AdvertisingStrategy(StrategyBase):
    """Создание таргетированной рекламы. Исправление #22."""
    def get_pipeline_stages(self) -> List[str]:
        return _BASE_STAGES + [
            "code_block_generation",
            "readme_generation",
        ]

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {
            "problem_analysis": (
                "Ты — специалист по таргетированной рекламе. "
                "Проанализируй запрос и определи: целевую аудиторию, платформу (VK/Meta/Google), "
                "рекламный бюджет, форматы объявлений, KPI кампании."
            ),
        }

    def get_task_type(self) -> TaskType:
        return TaskType.ADVERTISING


class AutomationStrategy(StrategyBase):
    """Автоматизация — управление другими приложениями через скрипты/браузер."""
    def get_pipeline_stages(self) -> List[str]:
        return _BASE_STAGES + [
            "code_block_generation",
            "deployment_commands",
        ]

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {
            "problem_analysis": (
                "Ты — специалист по автоматизации. "
                "Определи: что именно автоматизируется, какой инструмент использовать "
                "(Selenium/Playwright/PyAutoGUI/bash), необходимые шаги."
            ),
        }

    def get_task_type(self) -> TaskType:
        return TaskType.AUTOMATION


class GenericStrategy(StrategyBase):
    def get_pipeline_stages(self) -> List[str]:
        return _SIMPLE_CODE_STAGES

    def get_prompt_overrides(self) -> Dict[str, str]:
        return {}

    def get_task_type(self) -> TaskType:
        return TaskType.OTHER


# ─────────────── TaskAnalyzer ───────────────────────────

_KEYWORDS: dict[TaskType, list[str]] = {
    TaskType.DEBUG: ["ошибка", "error", "баг", "bug", "отладка", "debug", "не работает", "traceback", "исправь"],
    TaskType.SCRIPT: ["скрипт", "script", "автоматизировать", "automate", "bash", "shell", "powershell"],
    TaskType.COURSE: ["курс", "course", "урок", "lesson", "обучение", "учебный", "stepik"],
    TaskType.BOOK: ["книга", "book", "глава", "chapter", "роман"],
    TaskType.REPORT: ["отчёт", "report", "аналитика", "analytic", "статистика"],
    TaskType.ANDROID: ["android", "apk", "kotlin", "jetpack", "мобильное приложение"],
    TaskType.BOT: ["бот", "bot", "telegram", "телеграм", "discord", "чат-бот"],
    TaskType.ADDON: ["аддон", "addon", "расширение", "плагин", "plugin", "extension"],
    TaskType.ADVERTISING: ["реклама", "advertising", "таргет", "target", "рекламная кампания", "объявление"],
    TaskType.AUTOMATION: ["автоматизация", "automation", "selenium", "playwright", "браузер автоматически"],
    TaskType.CODE: ["приложение", "app", "сайт", "website", "api", "сервис", "service", "программу", "program"],
}


class TaskAnalyzer:
    def analyze(self, task: str) -> TaskType:
        low = task.lower()
        scores: dict[TaskType, int] = {t: 0 for t in TaskType}
        for task_type, keywords in _KEYWORDS.items():
            for kw in keywords:
                if kw in low:
                    scores[task_type] += 1
        best = max(scores, key=lambda t: scores[t])
        return best if scores[best] > 0 else TaskType.CODE

    def select_strategy(self, task_type: TaskType) -> StrategyBase:
        mapping: dict[TaskType, type[StrategyBase]] = {
            TaskType.CODE: CodeStrategy,
            TaskType.COURSE: CourseStrategy,
            TaskType.BOOK: GenericStrategy,
            TaskType.REPORT: GenericStrategy,
            TaskType.DEBUG: DebugStrategy,
            TaskType.SCRIPT: ScriptStrategy,
            TaskType.ANDROID: AndroidStrategy,
            TaskType.BOT: BotStrategy,
            TaskType.ADDON: AddonStrategy,
            TaskType.ADVERTISING: AdvertisingStrategy,
            TaskType.AUTOMATION: AutomationStrategy,
            TaskType.OTHER: GenericStrategy,
        }
        return mapping.get(task_type, GenericStrategy)()
