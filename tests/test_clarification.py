"""tests/test_clarification.py — Тесты этапа уточнения"""
import sys, os, types, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
for mod in ['PyQt6','PyQt6.QtCore','PyQt6.QtWidgets','PyQt6.QtGui',
            'aiosqlite','msgpack','zstandard','structlog']:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from orchestrator.pipeline_orchestrator import PipelineOrchestrator, StageStatus


def make_orch():
    ctx = MagicMock(); ctx.project_id = "p1"; ctx.logger = None
    ai = MagicMock(); storage = MagicMock(); registry = MagicMock(); parser = MagicMock()
    from parser.response_parser import ResponseParser
    parser.parse_json = ResponseParser().parse_json
    return PipelineOrchestrator(ctx, ai, storage, registry, parser)


def test_provide_user_answers_sets_event():
    orch = make_orch()
    import asyncio
    event = asyncio.Event()
    orch._user_answer_event = event
    orch.provide_user_answers({"q1": "Python"})
    assert orch._user_answers == {"q1": "Python"}
    assert event.is_set()


def test_provide_user_answers_no_event():
    orch = make_orch()
    orch._user_answer_event = None
    orch.provide_user_answers({"q1": "answer"})
    assert orch._user_answers == {"q1": "answer"}


def test_abort_sets_event():
    orch = make_orch()
    import asyncio
    event = asyncio.Event()
    orch._user_answer_event = event
    orch.abort()
    assert orch._abort
    assert event.is_set()


def test_clarification_callback_set():
    orch = make_orch()
    calls = []
    orch.set_clarification_callback(lambda q: calls.append(q))
    assert orch._clarify_cb is not None
    orch._clarify_cb(["q1", "q2"])
    assert calls == [["q1", "q2"]]


@pytest.mark.asyncio
async def test_clarification_stage_no_questions():
    """Если вопросов нет — сразу возвращает результат."""
    orch = make_orch()
    # Mock run_stage to return empty questions
    proto_ok = json.dumps({
        "proto": "GPT_PROTO_V1", "stage": "user_clarification",
        "status": "OK", "confidence": "HIGH", "summary": "No questions",
        "data": {"questions": []}, "warnings": [], "next_stage_hint": "",
        "tokens_used": 0, "timestamp": "2025-01-01T00:00:00"
    })

    from orchestrator.pipeline_orchestrator import StageResult
    mock_result = StageResult(
        stage="user_clarification", success=True,
        parsed_data={"questions": []}, summary="No questions"
    )

    original_run_stage = orch.run_stage
    async def mock_run_stage(*args, **kwargs):
        return mock_result
    orch.run_stage = mock_run_stage

    result = await orch._run_clarification_stage(
        task="Build app", context={},
        gateway_chat_id="gid", db_chat_id="dbid",
    )
    assert result.success
    assert result.summary == "No questions"
