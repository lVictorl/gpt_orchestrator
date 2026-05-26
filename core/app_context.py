"""
core/app_context.py — AppContext и EventBus
Глобальное состояние приложения и шина событий.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


# ─────────────────────── EventBus ───────────────────────

class EventBus:
    """Простая синхронно-асинхронная шина событий."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable) -> None:
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable) -> None:
        self._handlers[event] = [h for h in self._handlers[event] if h is not handler]

    def publish(self, event: str, data: Any = None) -> None:
        for handler in list(self._handlers.get(event, [])):
            try:
                if asyncio.iscoroutinefunction(handler):
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(handler(data))
                    else:
                        loop.run_until_complete(handler(data))
                else:
                    handler(data)
            except Exception as exc:
                logging.getLogger(__name__).error(
                    "EventBus handler error event=%s exc=%s", event, exc
                )


# ─────────────────────── AppContext ───────────────────────

@dataclass
class AppContext:
    """Глобальный контейнер состояния приложения."""

    project_id: str = ""
    full_context: dict = field(default_factory=dict)
    config: Any = None          # ConfigManager, ставится снаружи
    logger: Any = None          # StructLogger, ставится снаружи
    event_bus: EventBus = field(default_factory=EventBus)

    # Текущий активный chat_id для пайплайна
    active_chat_id: str = ""

    def reset_project(self, project_id: str) -> None:
        """Сброс контекста при старте нового проекта."""
        self.project_id = project_id
        self.full_context = {}
        self.active_chat_id = ""

    def accumulate(self, stage: str, data: dict) -> None:
        """Добавить результат этапа в full_context."""
        self.full_context[stage] = data
        if self.event_bus:
            self.event_bus.publish("context_updated", {"stage": stage})
