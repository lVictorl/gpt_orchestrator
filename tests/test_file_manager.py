"""tests/test_file_manager.py — Тесты ProjectFileManager и ReportGenerator"""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import tempfile
from pathlib import Path
from file_manager.project_file_manager import ProjectFileManager, ReportGenerator


@pytest.fixture
def tmp_manager(tmp_path):
    return ProjectFileManager(str(tmp_path / "projects"))


def test_create_project_dir(tmp_manager):
    d = tmp_manager.create_project_dir("p001")
    assert d.exists()
    for subdir in ProjectFileManager.BASE_DIRS:
        assert (d / subdir).exists()


def test_save_file(tmp_manager):
    tmp_manager.create_project_dir("p002")
    path = tmp_manager.save_file("p002", "src/main.py", "print('hello')")
    assert path.exists()
    assert path.read_text() == "print('hello')"


def test_save_stage_artifact_code(tmp_manager):
    tmp_manager.create_project_dir("p003")
    path = tmp_manager.save_stage_artifact("p003", "code_block_generation", "app.py", "# code")
    assert "src" in str(path)
    assert path.exists()


def test_save_stage_artifact_tests(tmp_manager):
    tmp_manager.create_project_dir("p004")
    path = tmp_manager.save_stage_artifact("p004", "unit_tests", "test_app.py", "# tests")
    assert "tests" in str(path)


def test_save_stage_artifact_critique(tmp_manager):
    tmp_manager.create_project_dir("p005")
    path = tmp_manager.save_stage_artifact("p005", "project_critique", "critique.json", "{}")
    assert "critique" in str(path)


def test_list_files(tmp_manager):
    tmp_manager.create_project_dir("p006")
    tmp_manager.save_file("p006", "src/a.py", "a")
    tmp_manager.save_file("p006", "tests/b.py", "b")
    files = tmp_manager.list_files("p006")
    assert any("a.py" in f for f in files)
    assert any("b.py" in f for f in files)


def test_list_files_missing_project(tmp_manager):
    files = tmp_manager.list_files("nonexistent")
    assert files == []


def test_get_structure_str(tmp_manager):
    tmp_manager.create_project_dir("p007")
    tmp_manager.save_file("p007", "src/main.py", "code")
    s = tmp_manager.get_structure_str("p007")
    assert "p007" in s


def test_report_generator(tmp_path):
    gen = ReportGenerator()
    stages = [
        {"stage": "problem_analysis", "status": "OK", "confidence": "HIGH",
         "summary": "Analyzed", "duration_sec": 2.3, "warnings": []},
        {"stage": "code_block_generation", "status": "OK", "confidence": "HIGH",
         "summary": "Code generated", "duration_sec": 15.0, "warnings": []},
    ]
    critique = {
        "overall_score": 82,
        "compliance_percent": 90,
        "grades": {"architecture": 8, "code_quality": 7, "test_coverage": 6,
                   "documentation": 8, "security": 7, "performance": 8, "completeness": 9},
        "strengths": ["Clean code", "Good docs"],
        "weaknesses": ["Low test coverage"],
        "recommendations": ["Add more tests"],
    }
    output = str(tmp_path / "report.html")
    result = gen.generate("p1", "Test Project", stages, output, critique)
    assert Path(result).exists()
    html = Path(result).read_text()
    assert "82" in html
    assert "Test Project" in html
    assert "90%" in html


def test_report_generator_no_critique(tmp_path):
    gen = ReportGenerator()
    output = str(tmp_path / "report2.html")
    result = gen.generate("p2", "Project 2", [], output)
    assert Path(result).exists()
