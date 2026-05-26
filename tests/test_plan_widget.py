"""tests/test_plan_widget.py — Тесты GenerationPlanWidget и PlanStorage"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import date
from gui.generation_plan_widget import PlanTask, PlanStorage


def make_task(tid="t1", period="day", status="pending"):
    return PlanTask(
        task_id=tid,
        title="Test Project",
        description="Do something",
        task_type="code",
        period=period,
        planned_date=date.today().isoformat(),
        status=status,
    )


def test_plan_task_to_dict():
    task = make_task()
    d = task.to_dict()
    assert d["task_id"] == "t1"
    assert d["title"] == "Test Project"
    assert d["status"] == "pending"


def test_plan_task_from_dict():
    task = make_task()
    d = task.to_dict()
    task2 = PlanTask.from_dict(d)
    assert task2.task_id == task.task_id
    assert task2.title == task.title


def test_plan_storage_save_and_load(tmp_path):
    path = tmp_path / "plan.json"
    storage = PlanStorage(path)
    tasks = [make_task("t1"), make_task("t2", period="week")]
    storage.save(tasks)
    loaded = storage.load()
    assert len(loaded) == 2
    assert loaded[0].task_id == "t1"


def test_plan_storage_empty(tmp_path):
    path = tmp_path / "plan.json"
    storage = PlanStorage(path)
    assert storage.load() == []


def test_plan_storage_invalid_json(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("NOT_JSON")
    storage = PlanStorage(path)
    assert storage.load() == []  # graceful fallback


def test_plan_task_done_status():
    task = make_task(status="done")
    assert task.status == "done"


def test_plan_task_critique_score():
    task = make_task()
    task.critique_score = 87
    d = task.to_dict()
    assert d["critique_score"] == 87
