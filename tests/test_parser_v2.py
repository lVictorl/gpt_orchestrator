"""tests/test_parser_v2.py — Тесты ResponseParser v2"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from parser.response_parser import ResponseParser, JSONExtractor, CodeBlockExtractor


def make_proto(stage="s", status="OK", data=None):
    return json.dumps({
        "proto": "GPT_PROTO_V1", "stage": stage, "status": status,
        "confidence": "HIGH", "summary": "test", "data": data or {},
        "warnings": [], "next_stage_hint": "", "tokens_used": 0,
        "timestamp": "2025-01-01T00:00:00"
    })


# ── JSONExtractor ─────────────────────────────────────────

def test_extract_clean_json():
    raw = '{"key": "value", "num": 42}'
    result = JSONExtractor.extract(raw)
    assert result == {"key": "value", "num": 42}

def test_extract_from_markdown():
    raw = '```json\n{"key": "value"}\n```'
    result = JSONExtractor.extract(raw)
    assert result == {"key": "value"}

def test_extract_from_text_with_json():
    raw = 'Here is the result:\n{"key": "value"}\nDone.'
    result = JSONExtractor.extract(raw)
    assert result == {"key": "value"}

def test_extract_nested_json():
    raw = '{"outer": {"inner": [1, 2, 3]}}'
    result = JSONExtractor.extract(raw)
    assert result["outer"]["inner"] == [1, 2, 3]

def test_extract_none_for_invalid():
    result = JSONExtractor.extract("This is just text with no JSON")
    assert result is None

def test_extract_empty():
    assert JSONExtractor.extract("") is None

def test_extract_proto_v1():
    raw = make_proto("problem_analysis", "OK", {"core_problem": "Build bot"})
    result = JSONExtractor.extract(raw)
    assert result["proto"] == "GPT_PROTO_V1"
    assert result["data"]["core_problem"] == "Build bot"


# ── CodeBlockExtractor ────────────────────────────────────

def test_extract_script():
    raw = "SCRIPT_START\n#!/bin/bash\necho hello\nSCRIPT_END"
    result = CodeBlockExtractor.extract_script(raw)
    assert "#!/bin/bash" in result

def test_extract_script_bash_markdown():
    raw = "```bash\necho hello\n```"
    result = CodeBlockExtractor.extract_script(raw)
    assert "echo hello" in result

def test_extract_readme():
    raw = "README_START\n# My Project\nREADME_END"
    result = CodeBlockExtractor.extract_readme(raw)
    assert "# My Project" in result

def test_extract_all_code_blocks():
    raw = "```python\nprint('hello')\n```\n\n```bash\necho world\n```"
    blocks = CodeBlockExtractor.extract_all_code_blocks(raw)
    assert len(blocks) == 2
    assert blocks[0] == ("python", "print('hello')")
    assert blocks[1] == ("bash", "echo world")

def test_extract_all_code_blocks_empty():
    blocks = CodeBlockExtractor.extract_all_code_blocks("no code here")
    assert blocks == []


# ── ResponseParser ────────────────────────────────────────

def test_parse_proto_v1_valid():
    parser = ResponseParser()
    raw = make_proto("code_block_generation", "OK",
                     {"files": [{"filename": "app.py", "content": "print('hi')", "description": "main"}]})
    result = parser.parse_proto_v1(raw)
    assert result is not None
    assert result["proto"] == "GPT_PROTO_V1"

def test_parse_proto_v1_invalid():
    parser = ResponseParser()
    raw = '{"proto": "NOT_PROTO", "data": {}}'
    result = parser.parse_proto_v1(raw)
    assert result is None

def test_extract_files_from_data_valid():
    parser = ResponseParser()
    data = {
        "files": [
            {"filename": "src/app.py", "content": "print('hello')", "description": "Main"},
            {"filename": "tests/test_app.py", "content": "import app", "description": "Tests"},
        ]
    }
    files = parser.extract_files_from_data(data)
    assert len(files) == 2
    assert files[0]["filename"] == "src/app.py"
    assert files[1]["content"] == "import app"

def test_extract_files_from_data_empty():
    parser = ResponseParser()
    assert parser.extract_files_from_data({}) == []
    assert parser.extract_files_from_data({"files": []}) == []

def test_extract_files_from_data_missing_content():
    parser = ResponseParser()
    data = {"files": [{"filename": "app.py", "content": ""}]}  # empty content
    files = parser.extract_files_from_data(data)
    assert files == []  # skipped due to empty content

def test_parse_json_with_code_in_data():
    parser = ResponseParser()
    raw = make_proto("code_block_generation", "OK", {
        "files": [{"filename": "main.py", "content": "def main():\n    pass\n", "description": "entry"}]
    })
    result = parser.parse_json(raw)
    assert isinstance(result, dict)
    files = parser.extract_files_from_data(result.get("data", {}))
    assert len(files) == 1
    assert "def main" in files[0]["content"]

def test_context_to_compact():
    parser = ResponseParser()
    ctx = {"stage1": {"key": "val"}}
    compact = parser.context_to_compact(ctx)
    assert '"stage1"' in compact
    assert " " not in compact.replace('"key": "val"', '')  # compact format
