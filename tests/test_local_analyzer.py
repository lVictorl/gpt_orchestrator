"""tests/test_local_analyzer.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from local_model.local_analyzer import (
    LocalAnalyzer, RuleBasedAnalyzer, AnalysisResult
)


def test_count_tokens_empty():
    assert AnalysisResult.count_tokens("") == 0

def test_count_tokens_positive():
    assert AnalysisResult.count_tokens("hello world") > 0

def test_count_tokens_cyrillic_heavier():
    en = AnalysisResult.count_tokens("hello world this is english")
    ru = AnalysisResult.count_tokens("привет мир это русский текст")
    assert ru >= en

def test_analysis_result_was_modified():
    r = AnalysisResult("original", "different")
    assert r.was_modified

def test_analysis_result_not_modified():
    r = AnalysisResult("same", "same")
    assert not r.was_modified

def test_analysis_result_savings_percent():
    r = AnalysisResult("orig", "corr", original_tokens=100, corrected_tokens=80, tokens_saved=20)
    assert abs(r.savings_percent - 20.0) < 0.01

def test_rule_based_removes_politeness():
    analyzer = RuleBasedAnalyzer()
    result = analyzer.analyze("пожалуйста, создай телеграм бота для записи клиентов")
    assert "пожалуйста" not in result.corrected_prompt.lower()

def test_rule_based_normalizes_tech_terms():
    analyzer = RuleBasedAnalyzer()
    result = analyzer.analyze("напиши бэкенд на питоне с апи")
    assert "Python" in result.corrected_prompt or "backend" in result.corrected_prompt

def test_rule_based_deduplication():
    analyzer = RuleBasedAnalyzer()
    text = "Создай бота. Создай бота. Добавь кнопки."
    result = analyzer.analyze(text)
    assert result.corrected_prompt.count("Создай бота") <= 1

def test_rule_based_returns_analysis_result():
    analyzer = RuleBasedAnalyzer()
    result = analyzer.analyze("build a telegram bot")
    assert isinstance(result, AnalysisResult)
    assert result.backend_used == "rule_based"
    assert result.original_tokens > 0
    assert result.processing_time_ms >= 0

def test_local_analyzer_fallback_to_rule():
    analyzer = LocalAnalyzer(enabled=True)
    assert "rule_based" in analyzer.backend or "ollama" in analyzer.backend

def test_local_analyzer_disabled():
    analyzer = LocalAnalyzer(enabled=False)
    result = analyzer.analyze("build something")
    assert result.corrected_prompt == "build something"
    assert result.backend_used == "disabled"

def test_local_analyzer_never_raises():
    analyzer = LocalAnalyzer(enabled=True)
    # Should not raise even with weird input
    for prompt in ["", "   ", "!@#$%", "a" * 5000, None.__class__.__name__]:
        result = analyzer.analyze(prompt)
        assert isinstance(result, AnalysisResult)

def test_local_analyzer_analyze_and_log_no_logger():
    analyzer = LocalAnalyzer(enabled=True)
    result = analyzer.analyze_and_log("build a bot", "code_block_generation", logger=None)
    assert isinstance(result, AnalysisResult)
