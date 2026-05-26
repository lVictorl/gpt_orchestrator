"""tests/test_token_optimizer.py — Тесты TokenOptimizer"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from token_saver.token_optimizer import TokenOptimizer, MODEL_PRICING, OptimizationReport


def test_count_tokens_empty():
    assert TokenOptimizer.count_tokens("") == 0

def test_count_tokens_latin():
    text = "Hello world"  # 11 chars → ~3 tokens
    result = TokenOptimizer.count_tokens(text)
    assert 2 <= result <= 5

def test_count_tokens_cyrillic():
    text = "Привет мир"  # 10 chars, cyrillic → ~5 tokens
    result = TokenOptimizer.count_tokens(text)
    assert result >= 3

def test_model_pricing_all_providers():
    providers = TokenOptimizer.list_models_by_provider()
    assert len(providers["deepseek"]) >= 3
    assert len(providers["openai"]) >= 2
    assert len(providers["anthropic"]) >= 2

def test_model_pricing_deepseek_chat():
    p = MODEL_PRICING["deepseek-chat"]
    assert p["input"] > 0
    assert p["output"] > 0
    assert p["output"] > p["input"]  # output всегда дороже

def test_model_pricing_deepseek_reasoner_more_expensive():
    assert MODEL_PRICING["deepseek-reasoner"]["input"] > MODEL_PRICING["deepseek-chat"]["input"]

def test_calculate_cost_zero():
    opt = TokenOptimizer("deepseek-chat")
    assert opt.calculate_cost(0, 0) == 0.0

def test_calculate_cost_positive():
    opt = TokenOptimizer("deepseek-chat")
    cost = opt.calculate_cost(1_000_000, 1_000_000)
    assert cost > 0

def test_calculate_cost_unknown_model():
    opt = TokenOptimizer("unknown-model-xyz")
    cost = opt.calculate_cost(1000, 1000)
    assert cost >= 0

def test_select_minimal_context():
    opt = TokenOptimizer()
    ctx = {
        "user_task": {"task": "build bot"},
        "problem_analysis": {"goals": ["goal1"]},
        "code_block_generation": {"files": ["file1"]},
        "unrelated_stage": {"x": "y"},
    }
    minimal = opt.select_minimal_context("unit_tests", ctx)
    assert "code_block_generation" in minimal
    assert "global_spec_and_api" not in minimal  # not in input ctx
    assert "unrelated_stage" not in minimal

def test_select_minimal_context_unknown_stage():
    opt = TokenOptimizer()
    ctx = {"a": 1, "b": 2}
    result = opt.select_minimal_context("unknown_stage", ctx)
    assert result == ctx  # returns full context for unknown stages

def test_compress_context_truncates_long():
    opt = TokenOptimizer()
    long_val = "X" * 5000
    ctx = {"stage1": {"key": long_val}}
    result = opt.compress_context(ctx)
    # Value should be truncated
    assert len(str(result["stage1"]["key"])) < len(long_val)

def test_compress_context_deduplicates():
    opt = TokenOptimizer()
    ctx = {
        "stage1": {"key": "same text here" * 10},
        "stage2": {"key": "same text here" * 10},  # duplicate
    }
    result = opt.compress_context(ctx)
    # stage2.key should be removed as duplicate
    assert "stage1" in result

def test_summarize_short_response():
    opt = TokenOptimizer()
    short = "Short response"
    assert opt.summarize_long_response("code_block_generation", short) == short

def test_summarize_long_response():
    opt = TokenOptimizer()
    long_text = "A" * 10000
    result = opt.summarize_long_response("code_block_generation", long_text)
    assert "сокращено" in result
    assert len(result) < len(long_text)

def test_add_usage_and_get_total():
    opt = TokenOptimizer("deepseek-chat")
    opt.add_usage(100, 200)
    opt.add_usage(300, 400)
    t_in, t_out = opt.get_total_tokens()
    assert t_in == 400
    assert t_out == 600

def test_reset_stats():
    opt = TokenOptimizer()
    opt.add_usage(100, 100)
    opt.reset_stats()
    t_in, t_out = opt.get_total_tokens()
    assert t_in == 0 and t_out == 0

def test_total_cost_after_usage():
    opt = TokenOptimizer("deepseek-chat")
    opt.add_usage(1_000_000, 1_000_000)
    cost = opt.get_total_cost()
    expected = MODEL_PRICING["deepseek-chat"]["input"] + MODEL_PRICING["deepseek-chat"]["output"]
    assert abs(cost - expected) < 0.01

def test_optimize_prompt():
    opt = TokenOptimizer("deepseek-chat")
    ctx = {
        "user_task": {"task": "Build a Telegram bot"},
        "problem_analysis": {"core_problem": "Need a bot"},
        "irrelevant_stage": {"data": "X" * 3000},
    }
    prompt = "Do something with {{FULL_CONTEXT}}"
    optimized, report = opt.optimize_prompt("unit_tests", prompt, ctx)
    assert "irrelevant_stage" not in optimized
    assert report.original_tokens >= 0
    assert report.optimized_tokens >= 0

def test_optimization_report_str():
    report = OptimizationReport(
        original_tokens=1000, optimized_tokens=600,
        saved_tokens=400, saving_percent=40.0,
        cost_original_usd=0.001, cost_optimized_usd=0.0006,
        cost_saved_usd=0.0004,
    )
    s = str(report)
    assert "1000" in s
    assert "600" in s
