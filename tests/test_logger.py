"""tests/test_logger.py — Тесты StructLogger"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pathlib import Path
from core.logger import StructLogger


def test_logger_creates_log_file(tmp_path):
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    logger.info("test message")
    log_file = tmp_path / "gpt_orchestrator.log"
    assert log_file.exists()


def test_logger_json_format(tmp_path):
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    logger.debug("test_json_log", key1="val1", key2=42)
    log_file = tmp_path / "gpt_orchestrator.log"
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) >= 1
    record = json.loads(lines[0])
    assert "ts" in record
    assert "level" in record
    assert "msg" in record


def test_logger_ai_request(tmp_path):
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    logger.log_ai_request(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        stage="problem_analysis",
        prompt="Test prompt",
        project_id="p1",
    )
    log_file = tmp_path / "gpt_orchestrator.log"
    content = log_file.read_text()
    assert "AI_REQUEST" in content
    assert "anthropic" in content


def test_logger_ai_response(tmp_path):
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    logger.log_ai_response(
        provider="deepseek",
        stage="code_block_generation",
        response="def main(): pass",
        tokens_out=10,
        latency_sec=2.5,
        project_id="p1",
    )
    content = (tmp_path / "gpt_orchestrator.log").read_text()
    assert "AI_RESPONSE" in content
    assert "deepseek" in content


def test_logger_ai_error(tmp_path):
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    logger.log_ai_error("openai", "unit_tests", "Rate limit exceeded", "p1")
    content = (tmp_path / "gpt_orchestrator.log").read_text()
    assert "AI_ERROR" in content


def test_logger_file_saved(tmp_path):
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    logger.log_file_saved("/projects/p1/src/main.py", 1234, "code_block_generation")
    content = (tmp_path / "gpt_orchestrator.log").read_text()
    assert "FILE_SAVED" in content


def test_logger_set_project_dir(tmp_path):
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    project_dir = tmp_path / "project_001"
    project_dir.mkdir()
    logger.set_project_dir(str(project_dir))
    logger.info("project log test")
    project_log = project_dir / "logs" / "project.log"
    assert project_log.exists()
    assert "project log test" in project_log.read_text()
