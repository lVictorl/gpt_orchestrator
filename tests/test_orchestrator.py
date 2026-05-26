"""
tests/test_orchestrator.py — Тесты PipelineOrchestrator
"""
import sys, os, types, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Mock external deps
for mod in ['PyQt6','PyQt6.QtCore','PyQt6.QtWidgets','PyQt6.QtGui',
            'aiosqlite','msgpack','zstandard','structlog']:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from orchestrator.pipeline_orchestrator import (
    PipelineOrchestrator, StageResult, StageStatus, ContextAccumulator
)
from core.protocol import ProtoEnvelope


# ── ContextAccumulator ────────────────────────────────────

def test_context_accumulator_add_and_get():
    acc = ContextAccumulator()
    acc.add("stage1", {"key": "value"})
    acc.add("stage2", {"key2": "value2"})
    ctx = acc.get()
    assert ctx["stage1"]["key"] == "value"
    assert ctx["stage2"]["key2"] == "value2"

def test_context_accumulator_reset():
    acc = ContextAccumulator()
    acc.add("s", {"x": 1})
    acc.reset()
    assert acc.get() == {}

def test_context_accumulator_compact_json():
    import json
    acc = ContextAccumulator()
    acc.add("s", {"a": 1})
    result = acc.to_compact_json()
    parsed = json.loads(result)
    assert parsed["s"]["a"] == 1


# ── StageResult ───────────────────────────────────────────

def test_stage_result_duration():
    r = StageResult(
        stage="test",
        success=True,
        started_at=datetime(2025, 1, 1, 0, 0, 0),
        finished_at=datetime(2025, 1, 1, 0, 0, 5),
    )
    assert r.duration_sec == 5.0

def test_stage_result_no_duration():
    r = StageResult(stage="test", success=True)
    assert r.duration_sec == 0.0

def test_stage_result_emojis():
    r = StageResult(stage="s", success=True, confidence="HIGH", status_proto="OK")
    assert r.confidence_emoji() == "🟢"
    assert r.status_emoji() == "✅"

def test_stage_result_error_emojis():
    r = StageResult(stage="s", success=False, confidence="LOW", status_proto="ERROR")
    assert r.confidence_emoji() == "🔴"
    assert r.status_emoji() == "❌"


# ── Proto parsing in orchestrator ─────────────────────────

def make_orchestrator():
    ctx = MagicMock()
    ctx.project_id = "test_project"
    ai = MagicMock()
    storage = MagicMock()
    registry = MagicMock()
    parser_obj = MagicMock()

    # parser mock
    from parser.response_parser import ResponseParser
    real_parser = ResponseParser()
    parser_obj.parse_json = real_parser.parse_json

    return PipelineOrchestrator(ctx, ai, storage, registry, parser_obj)


def test_parse_proto_valid_envelope():
    import json
    orch = make_orchestrator()
    raw = json.dumps({
        "proto": "GPT_PROTO_V1",
        "stage": "problem_analysis",
        "status": "OK",
        "confidence": "HIGH",
        "summary": "Task analyzed",
        "data": {"core_problem": "Build app"},
        "warnings": [],
        "next_stage_hint": "proceed",
        "tokens_used": 100,
        "timestamp": "2025-01-01T00:00:00",
    })
    result = orch._parse_proto_response(
        raw, "problem_analysis", "chat1",
        datetime.utcnow(), datetime.utcnow()
    )
    assert result.success
    assert result.status_proto == "OK"
    assert result.summary == "Task analyzed"
    assert result.parsed_data["core_problem"] == "Build app"


def test_parse_proto_fallback_non_json():
    orch = make_orchestrator()
    raw = "This is a plain text response without JSON"
    result = orch._parse_proto_response(
        raw, "some_stage", "chat1",
        datetime.utcnow(), datetime.utcnow()
    )
    # Fallback → success=True (ответ получен)
    assert result.success
    assert result.status_proto == "OK"
    assert "MEDIUM" == result.confidence


def test_parse_proto_error_status():
    import json
    orch = make_orchestrator()
    raw = json.dumps({
        "proto": "GPT_PROTO_V1",
        "stage": "code_block_generation",
        "status": "ERROR",
        "confidence": "LOW",
        "summary": "Failed to generate",
        "data": {"error": "context too long"},
        "warnings": [],
        "next_stage_hint": "",
        "tokens_used": 0,
        "timestamp": "2025-01-01T00:00:00",
    })
    result = orch._parse_proto_response(
        raw, "code_block_generation", "c1",
        datetime.utcnow(), datetime.utcnow()
    )
    assert not result.success
    assert result.status_proto == "ERROR"
    assert result.error == "context too long"


def test_parse_proto_warn_is_success():
    import json
    orch = make_orchestrator()
    raw = json.dumps({
        "proto": "GPT_PROTO_V1",
        "stage": "unit_tests",
        "status": "WARN",
        "confidence": "MEDIUM",
        "summary": "Tests generated with warnings",
        "data": {"tests": "..."},
        "warnings": ["coverage < 80%"],
        "next_stage_hint": "",
        "tokens_used": 50,
        "timestamp": "2025-01-01T00:00:00",
    })
    result = orch._parse_proto_response(
        raw, "unit_tests", "c1",
        datetime.utcnow(), datetime.utcnow()
    )
    assert result.success  # WARN = success
    assert result.warnings == ["coverage < 80%"]


def test_callbacks_are_set():
    orch = make_orchestrator()
    token_calls = []
    stage_calls = []
    orch.set_token_callback(lambda s, t: token_calls.append((s, t)))
    orch.set_stage_callback(lambda s, st: stage_calls.append((s, st)))
    assert orch._token_cb is not None
    assert orch._stage_cb is not None

    # Test _set_status triggers callback
    orch._set_status("test_stage", StageStatus.RUNNING)
    assert len(stage_calls) == 1
    assert stage_calls[0] == ("test_stage", StageStatus.RUNNING)


def test_abort_flag():
    orch = make_orchestrator()
    assert not orch._abort
    orch.abort()
    assert orch._abort


def test_build_critique_prompt():
    orch = make_orchestrator()
    ctx = {
        "PROBLEM_DESCRIPTION": "Build a bot",
        "FULL_CONTEXT": '{"stage1": "data"}',
    }
    prompt = orch._build_critique_prompt(ctx)
    assert "Build a bot" in prompt
    assert "compliance_percent" in prompt
