"""
tests/test_prompt_registry.py — Тесты PromptRegistry
"""
import json
import pytest
import tempfile
import os
from prompt_registry.registry import PromptRegistry, PlaceholderFiller, PromptTemplate


class TestPlaceholderFiller:
    def test_basic_fill(self):
        result = PlaceholderFiller.fill("Hello {{NAME}}!", {"NAME": "World"})
        assert result == "Hello World!"

    def test_multiple_placeholders(self):
        result = PlaceholderFiller.fill("{{A}} and {{B}}", {"A": "foo", "B": "bar"})
        assert result == "foo and bar"

    def test_missing_placeholder_stays(self):
        result = PlaceholderFiller.fill("{{MISSING}}", {})
        assert result == "{{MISSING}}"

    def test_find_placeholders(self):
        placeholders = PlaceholderFiller.find_placeholders("{{A}} {{B}} {{A}}")
        assert set(placeholders) == {"A", "B"}


class TestPromptRegistry:
    def setup_method(self):
        """Создаём временный pipeline.json для тестов."""
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        data = {
            "version": "2.0",
            "stages": [
                {
                    "stage": "test_stage",
                    "category_label": "[Test]",
                    "prompt": "Hello {{NAME}}, your task: {{TASK}}",
                    "key_placeholders": ["NAME", "TASK"],
                    "key_outputs": ["result"],
                    "creates_new_chat": False,
                    "parse_mode": "json",
                }
            ],
        }
        json.dump(data, self._tmp)
        self._tmp.close()
        self._registry = PromptRegistry(self._tmp.name)

    def teardown_method(self):
        os.unlink(self._tmp.name)

    def test_get_stage(self):
        tmpl = self._registry.get("test_stage")
        assert tmpl is not None
        assert tmpl.stage == "test_stage"
        assert tmpl.category_label == "[Test]"

    def test_fill_prompt(self):
        filled = self._registry.fill("test_stage", {"NAME": "Alice", "TASK": "do it"})
        assert "Alice" in filled
        assert "do it" in filled

    def test_list_stages(self):
        stages = self._registry.list_stages()
        assert "test_stage" in stages

    def test_missing_stage_raises(self):
        with pytest.raises(KeyError):
            self._registry.fill("nonexistent_stage", {})
