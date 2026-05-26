"""
storage/storage_manager.py — StorageManager v3

АРХИТЕКТУРНОЕ ИСПРАВЛЕНИЕ:
  aiosqlite не позволяет использовать одно соединение из разных event loop.
  Решение: каждый вызов открывает собственное соединение через контекстный менеджер.
  Дополнительно добавлен синхронный фасад run_sync() для вызовов из Qt-потока.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import ChatMeta, Message, Project, ProjectMeta

try:
    import msgpack
    import zstandard as zstd
    _MSGPACK = True
except ImportError:
    _MSGPACK = False

STAGE_CATEGORIES: Dict[str, str] = {
    "problem_analysis":                "critique",
    "user_clarification":              "spec",
    "architecture_analysis":           "critique",
    "project_plan":                    "spec",
    "global_spec_and_api":             "spec",
    "subproject_prompts_generation":   "spec",
    "subproject_implementation_trigger": "spec",
    "code_block_generation":           "code",
    "optimization":                    "code",
    "unit_tests":                      "tests",
    "refactoring":                     "code",
    "deployment_commands":             "other",
    "debugging_cli":                   "critique",
    "readme_generation":               "other",
    "project_critique":                "critique",
}


def stage_to_category(stage: str) -> str:
    return STAGE_CATEGORIES.get(stage, "other")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id     TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    task_type      TEXT NOT NULL,
    description    TEXT,
    full_context   TEXT,
    created_at     TEXT,
    status         TEXT DEFAULT 'in_progress',
    critique_score INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id        TEXT PRIMARY KEY,
    project_id     TEXT DEFAULT '',
    title          TEXT NOT NULL,
    stage_category TEXT DEFAULT '',
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    chat_id    TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    stage      TEXT DEFAULT '',
    tokens     INTEGER DEFAULT 0,
    timestamp  TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_chats_project ON chats(project_id);
"""

_MIGRATIONS = [
    "ALTER TABLE chats ADD COLUMN stage_category TEXT DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN critique_score INTEGER DEFAULT NULL",
]


class StorageManager:
    """
    Потокобезопасный storage через синхронный sqlite3.
    Работает корректно из любого потока и любого event loop.
    """

    def __init__(self, db_path: str = "data.db") -> None:
        self._db_path = str(Path(db_path).resolve())
        self._lock = threading.Lock()
        self._initialized = False

    # ── Init ──────────────────────────────────────────────

    def init_sync(self) -> None:
        """Инициализировать БД (синхронно). Вызывать один раз при старте."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            for sql in _MIGRATIONS:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.commit()
        self._initialized = True

    async def init(self) -> None:
        """Async-совместимая обёртка для инициализации."""
        await asyncio.get_event_loop().run_in_executor(None, self.init_sync)

    async def close(self) -> None:
        pass  # нет постоянного соединения

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _exec(self, fn):
        """Выполнить синхронную функцию с соединением, потокобезопасно."""
        with self._lock:
            with self._connect() as conn:
                return fn(conn)

    async def _aexec(self, fn):
        """Выполнить в executor чтобы не блокировать event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._exec(fn))

    # ── Projects ──────────────────────────────────────────

    async def save_project(self, project: Project) -> str:
        if not project.project_id:
            project.project_id = str(uuid.uuid4())
        p = project

        def _fn(conn):
            conn.execute(
                """INSERT OR REPLACE INTO projects
                   (project_id,title,task_type,description,full_context,created_at,status,critique_score)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (p.project_id, p.title, p.task_type, p.description,
                 json.dumps(p.full_context, ensure_ascii=False),
                 p.created_at.isoformat(), p.status, p.critique_score)
            )
            conn.commit()
            return p.project_id

        return await self._aexec(_fn)

    def save_project_sync(self, project: Project) -> str:
        if not project.project_id:
            project.project_id = str(uuid.uuid4())
        p = project

        def _fn(conn):
            conn.execute(
                """INSERT OR REPLACE INTO projects
                   (project_id,title,task_type,description,full_context,created_at,status,critique_score)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (p.project_id, p.title, p.task_type, p.description,
                 json.dumps(p.full_context, ensure_ascii=False),
                 p.created_at.isoformat(), p.status, p.critique_score)
            )
            conn.commit()
            return p.project_id

        return self._exec(_fn)

    async def get_project(self, project_id: str) -> Optional[Project]:
        def _fn(conn):
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
            return dict(row) if row else None

        row = await self._aexec(_fn)
        if not row:
            return None
        return Project(
            project_id=row["project_id"], title=row["title"],
            task_type=row["task_type"], description=row["description"] or "",
            full_context=json.loads(row["full_context"] or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"], critique_score=row["critique_score"],
        )

    async def list_projects(self) -> List[ProjectMeta]:
        def _fn(conn):
            rows = conn.execute(
                "SELECT project_id,title,task_type,created_at,status,critique_score "
                "FROM projects ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

        rows = await self._aexec(_fn)
        return [
            ProjectMeta(
                project_id=r["project_id"], title=r["title"],
                task_type=r["task_type"],
                created_at=datetime.fromisoformat(r["created_at"]),
                status=r["status"], critique_score=r["critique_score"],
            )
            for r in rows
        ]

    def list_projects_sync(self) -> List[ProjectMeta]:
        def _fn(conn):
            rows = conn.execute(
                "SELECT project_id,title,task_type,created_at,status,critique_score "
                "FROM projects ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

        rows = self._exec(_fn)
        return [
            ProjectMeta(
                project_id=r["project_id"], title=r["title"],
                task_type=r["task_type"],
                created_at=datetime.fromisoformat(r["created_at"]),
                status=r["status"], critique_score=r["critique_score"],
            )
            for r in rows
        ]

    async def delete_project(self, project_id: str) -> None:
        chats = await self.list_chats(project_id)
        for chat in chats:
            await self.delete_chat(chat.chat_id)

        def _fn(conn):
            conn.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
            conn.commit()

        await self._aexec(_fn)

    async def update_project_status(
        self, project_id: str, status: str, critique_score: Optional[int] = None
    ) -> None:
        def _fn(conn):
            if critique_score is not None:
                conn.execute(
                    "UPDATE projects SET status=?,critique_score=? WHERE project_id=?",
                    (status, critique_score, project_id)
                )
            else:
                conn.execute(
                    "UPDATE projects SET status=? WHERE project_id=?",
                    (status, project_id)
                )
            conn.commit()

        await self._aexec(_fn)

    def update_project_status_sync(
        self, project_id: str, status: str, critique_score: Optional[int] = None
    ) -> None:
        def _fn(conn):
            if critique_score is not None:
                conn.execute(
                    "UPDATE projects SET status=?,critique_score=? WHERE project_id=?",
                    (status, critique_score, project_id)
                )
            else:
                conn.execute(
                    "UPDATE projects SET status=? WHERE project_id=?",
                    (status, project_id)
                )
            conn.commit()

        self._exec(_fn)

    # ── Chats ─────────────────────────────────────────────

    async def create_chat(
        self, title: str, project_id: str = "", stage: str = ""
    ) -> str:
        chat_id = str(uuid.uuid4())
        category = stage_to_category(stage) if stage else ""
        now = datetime.utcnow().isoformat()

        def _fn(conn):
            conn.execute(
                "INSERT INTO chats (chat_id,project_id,title,stage_category,created_at) "
                "VALUES (?,?,?,?,?)",
                (chat_id, project_id, title, category, now)
            )
            conn.commit()
            return chat_id

        return await self._aexec(_fn)

    def create_chat_sync(
        self, title: str, project_id: str = "", stage: str = ""
    ) -> str:
        chat_id = str(uuid.uuid4())
        category = stage_to_category(stage) if stage else ""
        now = datetime.utcnow().isoformat()

        def _fn(conn):
            conn.execute(
                "INSERT INTO chats (chat_id,project_id,title,stage_category,created_at) "
                "VALUES (?,?,?,?,?)",
                (chat_id, project_id, title, category, now)
            )
            conn.commit()
            return chat_id

        return self._exec(_fn)

    async def list_chats(self, project_id: str = "") -> List[ChatMeta]:
        def _fn(conn):
            if project_id:
                rows = conn.execute(
                    "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.chat_id) as cnt "
                    "FROM chats c WHERE c.project_id=? ORDER BY c.created_at ASC",
                    (project_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.chat_id) as cnt "
                    "FROM chats c ORDER BY c.created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

        rows = await self._aexec(_fn)
        return [
            ChatMeta(
                chat_id=r["chat_id"], title=r["title"],
                project_id=r["project_id"] or "",
                stage_category=r["stage_category"] or "",
                created_at=datetime.fromisoformat(r["created_at"]),
                message_count=r.get("cnt", 0),
            )
            for r in rows
        ]

    def list_chats_sync(self, project_id: str = "") -> List[ChatMeta]:
        def _fn(conn):
            if project_id:
                rows = conn.execute(
                    "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.chat_id) as cnt "
                    "FROM chats c WHERE c.project_id=? ORDER BY c.created_at ASC",
                    (project_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.chat_id) as cnt "
                    "FROM chats c ORDER BY c.created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

        rows = self._exec(_fn)
        return [
            ChatMeta(
                chat_id=r["chat_id"], title=r["title"],
                project_id=r["project_id"] or "",
                stage_category=r["stage_category"] or "",
                created_at=datetime.fromisoformat(r["created_at"]),
                message_count=r.get("cnt", 0),
            )
            for r in rows
        ]

    async def rename_chat(self, chat_id: str, title: str) -> None:
        def _fn(conn):
            conn.execute("UPDATE chats SET title=? WHERE chat_id=?", (title, chat_id))
            conn.commit()
        await self._aexec(_fn)

    def rename_chat_sync(self, chat_id: str, title: str) -> None:
        def _fn(conn):
            conn.execute("UPDATE chats SET title=? WHERE chat_id=?", (title, chat_id))
            conn.commit()
        self._exec(_fn)

    async def delete_chat(self, chat_id: str) -> None:
        def _fn(conn):
            conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
            conn.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
            conn.commit()
        await self._aexec(_fn)

    def delete_chat_sync(self, chat_id: str) -> None:
        def _fn(conn):
            conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
            conn.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
            conn.commit()
        self._exec(_fn)

    # ── Messages ──────────────────────────────────────────

    async def save_message(self, chat_id: str, msg: Message) -> None:
        if not msg.message_id:
            msg.message_id = str(uuid.uuid4())

        def _fn(conn):
            conn.execute(
                "INSERT OR REPLACE INTO messages "
                "(message_id,chat_id,role,content,stage,tokens,timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (msg.message_id, chat_id, msg.role, msg.content,
                 msg.stage, msg.tokens, msg.timestamp.isoformat())
            )
            conn.commit()

        await self._aexec(_fn)

    def save_message_sync(self, chat_id: str, msg: Message) -> None:
        if not msg.message_id:
            msg.message_id = str(uuid.uuid4())

        def _fn(conn):
            conn.execute(
                "INSERT OR REPLACE INTO messages "
                "(message_id,chat_id,role,content,stage,tokens,timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (msg.message_id, chat_id, msg.role, msg.content,
                 msg.stage, msg.tokens, msg.timestamp.isoformat())
            )
            conn.commit()

        self._exec(_fn)

    async def get_chat_history(self, chat_id: str) -> List[Message]:
        def _fn(conn):
            rows = conn.execute(
                "SELECT * FROM messages WHERE chat_id=? ORDER BY timestamp ASC",
                (chat_id,)
            ).fetchall()
            return [dict(r) for r in rows]

        rows = await self._aexec(_fn)
        return [
            Message(
                message_id=r["message_id"], role=r["role"],
                content=r["content"], stage=r["stage"],
                tokens=r["tokens"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in rows
        ]

    def get_chat_history_sync(self, chat_id: str) -> List[Message]:
        def _fn(conn):
            rows = conn.execute(
                "SELECT * FROM messages WHERE chat_id=? ORDER BY timestamp ASC",
                (chat_id,)
            ).fetchall()
            return [dict(r) for r in rows]

        rows = self._exec(_fn)
        return [
            Message(
                message_id=r["message_id"], role=r["role"],
                content=r["content"], stage=r["stage"],
                tokens=r["tokens"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in rows
        ]

    async def get_project_with_chats(
        self, project_id: str
    ) -> tuple[Optional[Project], List[ChatMeta]]:
        project = await self.get_project(project_id)
        chats = await self.list_chats(project_id)
        return project, chats
