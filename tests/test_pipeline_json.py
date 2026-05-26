"""tests/test_pipeline_json.py — Валидация pipeline.json"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pathlib import Path


def load_pipeline():
    path = Path(os.path.dirname(os.path.dirname(__file__))) / "pipeline.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_pipeline_valid_json():
    data = load_pipeline()
    assert "stages" in data
    assert len(data["stages"]) > 0

def test_all_stages_have_required_fields():
    data = load_pipeline()
    required = ["stage", "prompt", "parse_mode"]
    for s in data["stages"]:
        for field in required:
            assert field in s, f"Stage {s.get('stage','?')} missing '{field}'"

def test_all_stages_unique():
    data = load_pipeline()
    names = [s["stage"] for s in data["stages"]]
    assert len(names) == len(set(names)), f"Duplicate stage names: {[n for n in names if names.count(n) > 1]}"

def test_code_stages_have_full_context():
    """Code stages должны иметь FULL_CONTEXT placeholder."""
    data = load_pipeline()
    code_stages = {
        "code_block_generation", "optimization", "unit_tests",
        "refactoring", "deployment_commands", "readme_generation"
    }
    for s in data["stages"]:
        if s["stage"] in code_stages:
            assert "{{FULL_CONTEXT}}" in s["prompt"], \
                f"Code stage '{s['stage']}' missing {{{{FULL_CONTEXT}}}}"

def test_critique_stage_has_test_cases():
    data = load_pipeline()
    critique = next(s for s in data["stages"] if s["stage"] == "project_critique")
    assert "test_cases" in critique["prompt"]
    assert "TC-001" in critique["prompt"]

def test_all_stages_mention_proto_v1():
    """Все промпты должны требовать GPT_PROTO_V1."""
    data = load_pipeline()
    for s in data["stages"]:
        assert "GPT_PROTO_V1" in s["prompt"], \
            f"Stage '{s['stage']}' prompt doesn't mention GPT_PROTO_V1"

def test_parse_mode_valid_values():
    data = load_pipeline()
    valid = {"json", "raw_code", "raw_script", "raw_readme"}
    for s in data["stages"]:
        assert s["parse_mode"] in valid, \
            f"Stage '{s['stage']}' has invalid parse_mode '{s['parse_mode']}'"

def test_code_stages_have_files_field_instruction():
    """Code stages должны требовать поле files в data."""
    data = load_pipeline()
    code_stages = {"code_block_generation", "optimization", "unit_tests"}
    for s in data["stages"]:
        if s["stage"] in code_stages:
            assert "files" in s["prompt"], \
                f"Stage '{s['stage']}' doesn't mention 'files' field"
