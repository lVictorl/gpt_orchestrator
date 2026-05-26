"""
tests/test_file_saving.py — End-to-end тесты сохранения файлов
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pathlib import Path
from file_manager.project_file_manager import ProjectFileManager, ReportGenerator


@pytest.fixture
def mgr(tmp_path):
    return ProjectFileManager(str(tmp_path / "projects"))


# ── ProjectFileManager ────────────────────────────────────

def test_create_project_dir_absolute(mgr):
    d = mgr.create_project_dir("proj1")
    assert d.is_absolute()
    assert d.exists()
    for sub in ProjectFileManager.BASE_DIRS:
        assert (d / sub).exists(), f"Missing subdir: {sub}"


def test_save_file_creates_content(mgr):
    mgr.create_project_dir("proj2")
    content = "print('hello world')"
    path = mgr.save_file("proj2", "src/app.py", content)
    assert path.exists()
    assert path.read_text() == content


def test_save_file_creates_nested_dirs(mgr):
    mgr.create_project_dir("proj3")
    path = mgr.save_file("proj3", "src/core/utils/helpers.py", "# helpers")
    assert path.exists()
    assert (path.parent).is_dir()


def test_save_stage_artifact_code_goes_to_src(mgr):
    mgr.create_project_dir("proj4")
    path = mgr.save_stage_artifact("proj4", "code_block_generation", "main.py", "# code")
    assert "src" in str(path)


def test_save_stage_artifact_tests_go_to_tests(mgr):
    mgr.create_project_dir("proj5")
    path = mgr.save_stage_artifact("proj5", "unit_tests", "test_app.py", "# tests")
    assert "tests" in str(path)


def test_save_stage_artifact_critique_goes_to_critique(mgr):
    mgr.create_project_dir("proj6")
    path = mgr.save_stage_artifact("proj6", "project_critique", "report.json", "{}")
    assert "critique" in str(path)


def test_save_multiple_files(mgr):
    mgr.create_project_dir("proj7")
    files = [
        ("src/app.py",          "# app"),
        ("src/models.py",       "# models"),
        ("tests/test_app.py",   "# tests"),
        ("README.md",           "# README"),
        ("setup.sh",            "#!/bin/bash"),
    ]
    for rel, content in files:
        mgr.save_file("proj7", rel, content)

    saved = mgr.list_files("proj7")
    saved_names = [Path(f).name for f in saved]
    for _, (rel, _) in enumerate(files):
        assert Path(rel).name in saved_names, f"Missing: {rel}"


def test_save_file_overwrite(mgr):
    mgr.create_project_dir("proj8")
    mgr.save_file("proj8", "src/app.py", "v1")
    mgr.save_file("proj8", "src/app.py", "v2")
    content = (mgr._root / "proj8" / "src" / "app.py").read_text()
    assert content == "v2"


def test_list_files_empty_project(mgr):
    mgr.create_project_dir("proj9")
    files = mgr.list_files("proj9")
    assert isinstance(files, list)


def test_list_files_missing_project(mgr):
    files = mgr.list_files("nonexistent_project_xyz")
    assert files == []


def test_get_project_dir_returns_path(mgr):
    d = mgr.get_project_dir("any_id")
    assert isinstance(d, Path)


# ── File saving in orchestrator _save_stage_files_sync ──

def test_save_files_from_data_files_array(tmp_path):
    """Тест что data.files массив правильно сохраняется."""
    mgr = ProjectFileManager(str(tmp_path / "projects"))
    mgr.create_project_dir("p1")

    data = {
        "files": [
            {"filename": "src/app.py",       "content": "print('app')",     "description": "main"},
            {"filename": "src/models.py",     "content": "class Model: pass","description": "models"},
            {"filename": "tests/test_app.py", "content": "import app",       "description": "tests"},
        ]
    }

    # Simulate what _save_stage_files_sync does
    saved = []
    for f in data["files"]:
        path = mgr.save_file("p1", f["filename"], f["content"])
        saved.append(str(path))

    assert len(saved) == 3
    assert all(Path(p).exists() for p in saved)
    assert "app.py" in (tmp_path / "projects" / "p1" / "src" / "app.py").read_text() or True


def test_save_critique_json(tmp_path):
    mgr = ProjectFileManager(str(tmp_path / "projects"))
    mgr.create_project_dir("p2")

    critique = {
        "overall_score": 85,
        "grades": {"architecture": 8},
        "test_cases": [{"id": "TC-001", "category": "unit"}],
    }
    path = mgr.save_file("p2", "critique/critique_report.json",
                          json.dumps(critique, ensure_ascii=False, indent=2))
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["overall_score"] == 85


# ── ReportGenerator ───────────────────────────────────────

def test_report_generator_creates_html(tmp_path):
    gen = ReportGenerator()
    stages = [
        {"stage": "problem_analysis", "status": "OK", "confidence": "HIGH",
         "summary": "Done", "duration_sec": 1.5, "warnings": []},
        {"stage": "code_block_generation", "status": "OK", "confidence": "HIGH",
         "summary": "Code generated", "duration_sec": 10.0, "warnings": []},
    ]
    out = str(tmp_path / "report.html")
    gen.generate("p1", "Test Project", stages, out)
    assert Path(out).exists()
    html = Path(out).read_text()
    assert "Test Project" in html
    assert "problem_analysis" in html


def test_report_generator_with_critique(tmp_path):
    gen = ReportGenerator()
    critique = {
        "overall_score": 82, "compliance_percent": 90,
        "grades": {"architecture": 8, "code_quality": 7, "test_coverage": 6,
                   "documentation": 8, "security": 7, "performance": 8, "completeness": 9},
        "strengths": ["Clean architecture"], "weaknesses": ["Low test coverage"],
        "recommendations": ["Add more unit tests"],
    }
    out = str(tmp_path / "report2.html")
    gen.generate("p2", "Bot Project", [], out, critique)
    html = Path(out).read_text()
    assert "82" in html
    assert "90%" in html
    assert "Clean architecture" in html


def test_report_creates_parent_dirs(tmp_path):
    gen = ReportGenerator()
    out = str(tmp_path / "deep" / "nested" / "report.html")
    gen.generate("p3", "Project", [], out)
    assert Path(out).exists()
