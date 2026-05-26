"""
tests/test_storage_sync.py — Tests for synchronous StorageManager methods
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pathlib import Path
from datetime import datetime
from storage.storage_manager import StorageManager, stage_to_category
from storage.models import Project, Message, ChatMeta


@pytest.fixture
def storage(tmp_path):
    s = StorageManager(str(tmp_path / "test.db"))
    s.init_sync()
    return s


def test_init_creates_db(tmp_path):
    s = StorageManager(str(tmp_path / "new.db"))
    s.init_sync()
    assert Path(s._db_path).exists()


def test_save_and_get_project_sync(storage):
    p = Project(project_id="p1", title="Test", task_type="code", description="desc")
    storage.save_project_sync(p)
    # Verify via list
    projects = storage.list_projects_sync()
    assert any(x.project_id == "p1" for x in projects)


def test_list_projects_sync_empty(storage):
    assert storage.list_projects_sync() == []


def test_create_and_list_chats_sync(storage):
    p = Project(project_id="p2", title="T", task_type="code", description="")
    storage.save_project_sync(p)
    chat_id = storage.create_chat_sync("Chat 1", "p2", "code_block_generation")
    assert chat_id

    chats = storage.list_chats_sync("p2")
    assert len(chats) == 1
    assert chats[0].stage_category == "code"
    assert chats[0].project_id == "p2"


def test_save_and_get_message_sync(storage):
    p = Project(project_id="p3", title="T", task_type="code", description="")
    storage.save_project_sync(p)
    chat_id = storage.create_chat_sync("Chat", "p3", "unit_tests")

    msg = Message(role="user", content="Hello world", stage="unit_tests")
    storage.save_message_sync(chat_id, msg)

    history = storage.get_chat_history_sync(chat_id)
    assert len(history) == 1
    assert history[0].content == "Hello world"
    assert history[0].role == "user"


def test_save_assistant_message_sync(storage):
    p = Project(project_id="p4", title="T", task_type="bot", description="")
    storage.save_project_sync(p)
    chat_id = storage.create_chat_sync("Chat", "p4", "code_block_generation")

    for role, content in [("user", "prompt"), ("assistant", "response code here")]:
        storage.save_message_sync(chat_id, Message(role=role, content=content, stage="code_block_generation"))

    history = storage.get_chat_history_sync(chat_id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"
    assert "response" in history[1].content


def test_rename_chat_sync(storage):
    p = Project(project_id="p5", title="T", task_type="code", description="")
    storage.save_project_sync(p)
    chat_id = storage.create_chat_sync("Old Name", "p5")
    storage.rename_chat_sync(chat_id, "New Name")

    chats = storage.list_chats_sync("p5")
    assert chats[0].title == "New Name"


def test_delete_chat_sync(storage):
    p = Project(project_id="p6", title="T", task_type="code", description="")
    storage.save_project_sync(p)
    chat_id = storage.create_chat_sync("To Delete", "p6")
    storage.save_message_sync(chat_id, Message(role="user", content="msg", stage=""))
    storage.delete_chat_sync(chat_id)

    chats = storage.list_chats_sync("p6")
    assert len(chats) == 0
    history = storage.get_chat_history_sync(chat_id)
    assert len(history) == 0


def test_update_project_status_sync(storage):
    p = Project(project_id="p7", title="T", task_type="code", description="")
    storage.save_project_sync(p)
    storage.update_project_status_sync("p7", "done", 87)

    projects = storage.list_projects_sync()
    proj = next(x for x in projects if x.project_id == "p7")
    assert proj.status == "done"
    assert proj.critique_score == 87


def test_multiple_projects_sync(storage):
    for i in range(5):
        p = Project(project_id=f"mp{i}", title=f"P{i}", task_type="code", description="")
        storage.save_project_sync(p)

    projects = storage.list_projects_sync()
    assert len(projects) == 5


def test_message_order_preserved(storage):
    p = Project(project_id="p8", title="T", task_type="code", description="")
    storage.save_project_sync(p)
    chat_id = storage.create_chat_sync("Chat", "p8")

    messages = ["first", "second", "third", "fourth"]
    for m in messages:
        storage.save_message_sync(chat_id, Message(role="user", content=m, stage=""))

    history = storage.get_chat_history_sync(chat_id)
    assert [h.content for h in history] == messages


def test_stage_category_mapping():
    assert stage_to_category("code_block_generation") == "code"
    assert stage_to_category("unit_tests") == "tests"
    assert stage_to_category("project_critique") == "critique"
    assert stage_to_category("global_spec_and_api") == "spec"
    assert stage_to_category("unknown_stage") == "other"


def test_threadsafe_concurrent_writes(storage, tmp_path):
    """Storage должен быть потокобезопасен."""
    import threading
    p = Project(project_id="pt", title="T", task_type="code", description="")
    storage.save_project_sync(p)
    chat_id = storage.create_chat_sync("Chat", "pt")

    errors = []
    def write_messages(n):
        try:
            for i in range(n):
                storage.save_message_sync(
                    chat_id,
                    Message(role="user", content=f"msg_{threading.current_thread().name}_{i}", stage="")
                )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_messages, args=(5,)) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert errors == [], f"Thread errors: {errors}"
    history = storage.get_chat_history_sync(chat_id)
    assert len(history) == 20  # 4 threads × 5 messages
