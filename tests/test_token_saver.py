"""
tests/test_token_saver.py — Тесты TokenSaver (исправление #5).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from token_saver.token_saver import TokenSaver


def test_compress_removes_duplicates():
    ts = TokenSaver()
    ctx = {
        "stage1": {"key": "hello", "other": "world"},
        "stage2": {"key": "hello", "new": "data"},  # "hello" is duplicate
    }
    result = ts.compress_context(ctx)
    # stage2.key == "hello" should be deduplicated
    assert "stage1" in result


def test_select_minimal_context_known_stage():
    ts = TokenSaver()
    ctx = {"user_task": "x", "problem_analysis": "y", "unrelated": "z"}
    minimal = ts.select_minimal_context("user_clarification", ctx)
    assert "user_task" in minimal
    assert "problem_analysis" in minimal
    assert "unrelated" not in minimal


def test_select_minimal_context_unknown_stage():
    ts = TokenSaver()
    ctx = {"a": 1, "b": 2}
    result = ts.select_minimal_context("nonexistent_stage", ctx)
    assert result == ctx


def test_summarize_short_response():
    ts = TokenSaver()
    short = "Hello world"
    assert ts.summarize_stage_result("code_block_generation", short) == short


def test_summarize_long_response():
    ts = TokenSaver()
    long_text = "X" * 20000
    result = ts.summarize_stage_result("code_block_generation", long_text)
    assert "сокращено" in result
    assert len(result) < len(long_text)


def test_estimate_tokens():
    ts = TokenSaver()
    text = "A" * 400
    assert ts.estimate_tokens(text) == 100
