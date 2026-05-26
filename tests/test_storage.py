"""
tests/test_storage.py — Тесты StorageManager
"""
import asyncio
import os
import pytest
import pytest_asyncio

from storage.storage_manager import StorageManager
from storage.models import Message, Project


@pytest.fixture
def storage(tmp_path):
    db_path = str(tmp_path / "test.db")
    mgr = StorageManager(db_path)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(mgr.init())
    yield mgr, loop
    loop.run_until_complete(mgr.close())
    loop.close()


def test_save_and_get_project(storage):
    mgr, loop = storage
    project = Project(
        project_id="proj-001",
        title="Test Project",
        task_type="code",
        description="A test",
        full_context={"key": "value"},
    )
    project_id = loop.run_until_complete(mgr.save_project(project))
    assert project_id == "proj-001"

    loaded = loop.run_until_complete(mgr.get_project("proj-001"))
    assert loaded is not None
    assert loaded.title == "Test Project"
    assert loaded.full_context == {"key": "value"}


def test_list_projects(storage):
    mgr, loop = storage
    for i in range(3):
        p = Project(project_id=f"p{i}", title=f"Project {i}", task_type="code", description="")
        loop.run_until_complete(mgr.save_project(p))

    projects = loop.run_until_complete(mgr.list_projects())
    assert len(projects) == 3


def test_delete_project(storage):
    mgr, loop = storage
    p = Project(project_id="del-001", title="Delete Me", task_type="code", description="")
    loop.run_until_complete(mgr.save_project(p))
    loop.run_until_complete(mgr.delete_project("del-001"))
    result = loop.run_until_complete(mgr.get_project("del-001"))
    assert result is None


def test_chat_and_messages(storage):
    mgr, loop = storage

    chat_id = loop.run_until_complete(mgr.create_chat("Test Chat"))
    assert chat_id

    msg1 = Message(role="user", content="Hello AI")
    msg2 = Message(role="assistant", content="Hello human")
    loop.run_until_complete(mgr.save_message(chat_id, msg1))
    loop.run_until_complete(mgr.save_message(chat_id, msg2))

    history = loop.run_until_complete(mgr.get_chat_history(chat_id))
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].content == "Hello human"


def test_rename_chat(storage):
    mgr, loop = storage
    chat_id = loop.run_until_complete(mgr.create_chat("Old Name"))
    loop.run_until_complete(mgr.rename_chat(chat_id, "New Name"))
    chats = loop.run_until_complete(mgr.list_chats())
    titles = [c.title for c in chats]
    assert "New Name" in titles


def test_delete_chat(storage):
    mgr, loop = storage
    chat_id = loop.run_until_complete(mgr.create_chat("To Delete"))
    loop.run_until_complete(mgr.save_message(chat_id, Message(role="user", content="msg")))
    loop.run_until_complete(mgr.delete_chat(chat_id))
    chats = loop.run_until_complete(mgr.list_chats())
    ids = [c.chat_id for c in chats]
    assert chat_id not in ids
