"""
storage/models.py — Модели данных

Расширено: ProjectChat (связь чата с проектом и категорией этапа)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Message:
    role:       Literal["user", "assistant", "system"]
    content:    str
    timestamp:  datetime = field(default_factory=datetime.utcnow)
    stage:      str = ""
    tokens:     int = 0
    message_id: str = ""


@dataclass
class ChatMeta:
    chat_id:       str
    title:         str
    project_id:    str      = ""
    stage_category: str     = ""   # "analysis"|"tests"|"critique"|"code"|"spec"|""
    created_at:    datetime = field(default_factory=datetime.utcnow)
    message_count: int      = 0


@dataclass
class ProjectMeta:
    project_id: str
    title:      str
    task_type:  str
    created_at: datetime = field(default_factory=datetime.utcnow)
    status:     str = "in_progress"
    critique_score: Optional[int] = None


@dataclass
class Project:
    project_id:   str
    title:        str
    task_type:    str
    description:  str
    full_context: dict    = field(default_factory=dict)
    created_at:   datetime = field(default_factory=datetime.utcnow)
    status:       str     = "in_progress"
    critique_score: Optional[int] = None
