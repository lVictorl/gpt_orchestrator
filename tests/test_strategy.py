"""
tests/test_strategy.py — Тесты TaskAnalyzer и стратегий
"""
import pytest
from strategy.task_analyzer import TaskAnalyzer, TaskType, CodeStrategy, DebugStrategy, ScriptStrategy


class TestTaskAnalyzer:
    def setup_method(self):
        self._analyzer = TaskAnalyzer()

    def test_detect_code(self):
        task = "Разработай приложение для управления задачами"
        t = self._analyzer.analyze(task)
        assert t == TaskType.CODE

    def test_detect_debug(self):
        task = "Есть ошибка в коде: traceback: ValueError"
        t = self._analyzer.analyze(task)
        assert t == TaskType.DEBUG

    def test_detect_script(self):
        task = "Напиши bash скрипт для автоматизации деплоя"
        t = self._analyzer.analyze(task)
        assert t == TaskType.SCRIPT

    def test_detect_course(self):
        task = "Создай учебный курс по Python"
        t = self._analyzer.analyze(task)
        assert t == TaskType.COURSE

    def test_select_strategy_code(self):
        strategy = self._analyzer.select_strategy(TaskType.CODE)
        assert isinstance(strategy, CodeStrategy)
        stages = strategy.get_pipeline_stages()
        assert "code_block_generation" in stages
        assert "problem_analysis" in stages

    def test_select_strategy_debug(self):
        strategy = self._analyzer.select_strategy(TaskType.DEBUG)
        assert isinstance(strategy, DebugStrategy)
        assert "debugging_cli" in strategy.get_pipeline_stages()

    def test_select_strategy_script(self):
        strategy = self._analyzer.select_strategy(TaskType.SCRIPT)
        assert isinstance(strategy, ScriptStrategy)

    def test_strategy_has_prompt_overrides(self):
        strategy = self._analyzer.select_strategy(TaskType.CODE)
        overrides = strategy.get_prompt_overrides()
        assert isinstance(overrides, dict)
