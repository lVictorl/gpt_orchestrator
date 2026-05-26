"""
tests/test_parser.py — Тесты ResponseParser
"""
import pytest
from parser.response_parser import JSONExtractor, CodeBlockExtractor, ResponseParser


class TestJSONExtractor:
    def test_simple_dict(self):
        raw = '{"core_problem": "test", "goals": ["g1"]}'
        result = JSONExtractor.extract(raw)
        assert result == {"core_problem": "test", "goals": ["g1"]}

    def test_with_preamble(self):
        raw = 'Here is your JSON:\n```json\n{"key": "value"}\n```'
        result = JSONExtractor.extract(raw)
        assert result == {"key": "value"}

    def test_array(self):
        raw = '[{"a": 1}, {"b": 2}]'
        result = JSONExtractor.extract(raw)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_nested(self):
        raw = '{"outer": {"inner": [1, 2, 3]}}'
        result = JSONExtractor.extract(raw)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_invalid_returns_none(self):
        raw = "no json here at all"
        assert JSONExtractor.extract(raw) is None

    def test_with_text_around(self):
        raw = 'Sure! {"result": "ok"} Done.'
        result = JSONExtractor.extract(raw)
        assert result == {"result": "ok"}


class TestCodeBlockExtractor:
    def test_file_markers(self):
        raw = "FILE_START:main.py\nprint('hello')\nFILE_END:main.py"
        result = CodeBlockExtractor.extract_by_filename(raw, "main.py")
        assert result == "print('hello')"

    def test_script_markers(self):
        raw = "SCRIPT_START\n#!/bin/bash\necho hello\nSCRIPT_END"
        result = CodeBlockExtractor.extract_script(raw)
        assert "#!/bin/bash" in result

    def test_readme_markers(self):
        raw = "README_START\n# My Project\nSome text\nREADME_END"
        result = CodeBlockExtractor.extract_readme(raw)
        assert "# My Project" in result

    def test_markdown_fallback(self):
        raw = "```python\ndef hello():\n    pass\n```"
        result = CodeBlockExtractor.extract_by_filename(raw, "test.py")
        assert "def hello" in result


class TestResponseParser:
    def test_parse_json(self):
        parser = ResponseParser()
        result = parser.parse_json('{"stage": "test", "success": true}')
        assert result["stage"] == "test"

    def test_build_context(self):
        parser = ResponseParser()
        ctx = {}
        new_ctx = parser.build_context("stage1", {"data": 1}, ctx)
        assert new_ctx["stage1"]["data"] == 1

    def test_context_to_str(self):
        parser = ResponseParser()
        ctx = {"stage1": {"key": "val"}}
        s = parser.context_to_str(ctx)
        import json
        parsed = json.loads(s)
        assert parsed["stage1"]["key"] == "val"
