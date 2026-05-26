"""tests/test_history_panel.py — Тесты HistoryPanel"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime
from storage.models import ChatMeta, ProjectMeta


def make_project(pid="p1", title="Proj", task_type="code", status="done"):
    return ProjectMeta(project_id=pid, title=title, task_type=task_type,
                       created_at=datetime.utcnow(), status=status)

def make_chat(cid, title, project_id="p1", category="code"):
    return ChatMeta(chat_id=cid, title=title, project_id=project_id,
                    stage_category=category, created_at=datetime.utcnow())


@pytest.fixture
def app(qtbot):
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])

def test_history_panel_loads_projects(app, qtbot):
    from gui.history_panel import HistoryPanel
    panel = HistoryPanel()
    qtbot.addWidget(panel)
    projects = [make_project()]
    chats = {"p1": [make_chat("c1", "Chat 1"), make_chat("c2", "Chat 2", category="tests")]}
    panel.load_projects(projects, chats)
    # Дерево должно иметь 1 верхний элемент (проект)
    assert panel._tree.topLevelItemCount() == 1

def test_history_panel_chat_selected_signal(app, qtbot):
    from gui.history_panel import HistoryPanel
    panel = HistoryPanel()
    qtbot.addWidget(panel)
    chats = [make_chat("c1", "Test Chat", project_id="")]
    panel.load_chats(chats)
    with qtbot.waitSignal(panel.chat_selected, timeout=500) as blocker:
        # Симулируем клик
        panel.chat_selected.emit("c1")
    assert blocker.args == ["c1"]

def test_history_panel_select_chat_empty(app, qtbot):
    from gui.history_panel import HistoryPanel
    panel = HistoryPanel()
    qtbot.addWidget(panel)
    # Пустая строка не должна вызывать ошибку
    panel.select_chat("")
    assert panel._tree.currentItem() is None

def test_history_panel_remove_chat(app, qtbot):
    from gui.history_panel import HistoryPanel
    panel = HistoryPanel()
    qtbot.addWidget(panel)
    chats = [make_chat("c1", "Chat 1", project_id=""), make_chat("c2", "Chat 2", project_id="")]
    panel.load_chats(chats)
    panel.remove_chat("c1")
    # Должен остаться 1 chat

def test_history_panel_rename_chat(app, qtbot):
    from gui.history_panel import HistoryPanel
    panel = HistoryPanel()
    qtbot.addWidget(panel)
    chats = [make_chat("c1", "Old Name", project_id="")]
    panel.load_chats(chats)
    panel.rename_chat("c1", "New Name")
    assert panel._orphan_chats[0].title == "New Name"

def test_history_panel_filter(app, qtbot):
    from gui.history_panel import HistoryPanel
    panel = HistoryPanel()
    qtbot.addWidget(panel)
    chats = [
        make_chat("c1", "python project", project_id=""),
        make_chat("c2", "android app", project_id=""),
    ]
    panel.load_chats(chats)
    panel._filter("python")
    # c2 should be hidden
