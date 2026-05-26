"""tests/test_protocol.py — Тесты единого протокола GPT_PROTO_V1"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from core.protocol import ProtoEnvelope, ProtoStatus, Confidence


def make_envelope(**kwargs):
    defaults = dict(
        proto="GPT_PROTO_V1",
        stage="test_stage",
        status="OK",
        confidence="HIGH",
        summary="Test summary",
        data={"key": "value"},
        warnings=[],
        next_stage_hint="",
        tokens_used=0,
        timestamp="2025-01-01T00:00:00",
    )
    defaults.update(kwargs)
    return ProtoEnvelope(**defaults)


def test_envelope_is_ok():
    e = make_envelope(status="OK")
    assert e.is_ok()

def test_envelope_warn_is_ok():
    e = make_envelope(status="WARN")
    assert e.is_ok()

def test_envelope_error_not_ok():
    e = make_envelope(status="ERROR")
    assert not e.is_ok()

def test_envelope_partial_is_ok():
    e = make_envelope(status="PARTIAL")
    assert e.is_ok()

def test_envelope_has_warnings():
    e = make_envelope(warnings=["Watch out"])
    assert e.has_warnings()

def test_envelope_no_warnings():
    e = make_envelope(warnings=[])
    assert not e.has_warnings()

def test_confidence_emoji():
    assert make_envelope(confidence="HIGH").confidence_emoji() == "🟢"
    assert make_envelope(confidence="MEDIUM").confidence_emoji() == "🟡"
    assert make_envelope(confidence="LOW").confidence_emoji() == "🔴"

def test_status_emoji():
    assert make_envelope(status="OK").status_emoji() == "✅"
    assert make_envelope(status="WARN").status_emoji() == "⚠️"
    assert make_envelope(status="ERROR").status_emoji() == "❌"
    assert make_envelope(status="PARTIAL").status_emoji() == "🔶"

def test_to_json_is_valid():
    e = make_envelope()
    parsed = json.loads(e.to_json())
    assert parsed["proto"] == "GPT_PROTO_V1"
    assert parsed["stage"] == "test_stage"

def test_from_dict_roundtrip():
    e = make_envelope(summary="Hello world")
    d = json.loads(e.to_json())
    e2 = ProtoEnvelope.from_dict(d)
    assert e2.summary == "Hello world"
    assert e2.stage == "test_stage"

def test_from_dict_ignores_extra_keys():
    d = {
        "proto": "GPT_PROTO_V1",
        "stage": "s",
        "status": "OK",
        "confidence": "HIGH",
        "summary": "x",
        "data": {},
        "warnings": [],
        "next_stage_hint": "",
        "tokens_used": 0,
        "timestamp": "2025-01-01T00:00:00",
        "extra_unknown_key": "ignored",
    }
    e = ProtoEnvelope.from_dict(d)
    assert e.stage == "s"

def test_protocol_system_prompt_contains_proto():
    from core.protocol import PROTOCOL_SYSTEM_PROMPT
    assert "GPT_PROTO_V1" in PROTOCOL_SYSTEM_PROMPT
    assert "status" in PROTOCOL_SYSTEM_PROMPT
    assert "confidence" in PROTOCOL_SYSTEM_PROMPT

def test_critique_prompt_contains_score():
    from core.protocol import CRITIQUE_SYSTEM_PROMPT
    assert "overall_score" in CRITIQUE_SYSTEM_PROMPT
    assert "grades" in CRITIQUE_SYSTEM_PROMPT
    assert "compliance_percent" in CRITIQUE_SYSTEM_PROMPT
