"""tests/test_storage_v2.py — Тесты StorageManager v2"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
import pytest
from storage.storage_manager import StorageManager, stage_to_category
from storage.models import Project, Message


@pytest.fixture
async def storage(tmp_path):
    db = str(tmp_path / "test.db")
    s = StorageManager(db)
    await s.init()
    yield s
    await s.close()


def test_stage_to_category():
    assert stage_to_category("unit_tests") == "tests"
    assert stage_to_category("project_critique") == "critique"
    assert stage_to_category("code_block_generation") == "code"
    assert stage_to_category("global_spec_and_api") == "spec"
    assert stage_to_category("deployment_commands") == "other"


@pytest.mark.asyncio
async def test_save_and_get_project(storage):
    p = Project(project_id="p1", title="Test", task_type="code", description="desc")
    await storage.save_project(p)
    got = await storage.get_project("p1")
    assert got.title == "Test"
    assert got.task_type == "code"


@pytest.mark.asyncio
async def test_list_projects_empty(storage):
    projects = await storage.list_projects()
    assert projects == []


@pytest.mark.asyncio
async def test_create_chat_with_stage_category(storage):
    chat_id = await storage.create_chat("Unit Tests Chat", "p1", stage="unit_tests")
    chats = await storage.list_chats("p1")
    assert len(chats) == 1
    assert chats[0].stage_category == "tests"


@pytest.mark.asyncio
async def test_get_chat_history_ordered(storage):
    chat_id = await storage.create_chat("Chat", "p1")
    from datetime import datetime
    msgs = [
        Message(role="user", content="Hello", stage="q1"),
        Message(role="assistant", content="World", stage="q1"),
    ]
    for m in msgs:
        await storage.save_message(chat_id, m)
    history = await storage.get_chat_history(chat_id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"


@pytest.mark.asyncio
async def test_update_project_status_with_score(storage):
    p = Project(project_id="p2", title="T2", task_type="bot", description="")
    await storage.save_project(p)
    await storage.update_project_status("p2", "done", critique_score=85)
    got = await storage.get_project("p2")
    assert got.status == "done"
    assert got.critique_score == 85


@pytest.mark.asyncio
async def test_delete_project_cascades(storage):
    p = Project(project_id="p3", title="Del", task_type="code", description="")
    await storage.save_project(p)
    chat_id = await storage.create_chat("Chat", "p3")
    msg = Message(role="user", content="hi", stage="")
    await storage.save_message(chat_id, msg)
    await storage.delete_project("p3")
    got = await storage.get_project("p3")
    assert got is None
    history = await storage.get_chat_history(chat_id)
    assert history == []


@pytest.mark.asyncio
async def test_get_project_with_chats(storage):
    p = Project(project_id="p4", title="P4", task_type="code", description="")
    await storage.save_project(p)
    await storage.create_chat("C1", "p4", "code_block_generation")
    await storage.create_chat("C2", "p4", "unit_tests")
    project, chats = await storage.get_project_with_chats("p4")
    assert project.project_id == "p4"
    assert len(chats) == 2
    categories = {c.stage_category for c in chats}
    assert "code" in categories
    assert "tests" in categories
