"""tests/test_project_runner.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from pathlib import Path
from runner.project_runner import (
    ProjectRunner, ProjectRunReport, RunResult,
    TestResult, ProfileResult
)


@pytest.fixture
def simple_project(tmp_path):
    """Create a simple Python project for testing."""
    # Create project structure
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()

    (tmp_path / "src" / "app.py").write_text(
        "def add(a, b):\n    return a + b\n\n"
        "def multiply(a, b):\n    return a * b\n"
    )
    (tmp_path / "tests" / "test_app.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"
        "from app import add, multiply\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n"
        "def test_multiply():\n    assert multiply(3, 4) == 12\n"
    )
    (tmp_path / "requirements.txt").write_text("# no deps\n")
    (tmp_path / "main.py").write_text(
        "from src.app import add\nif __name__ == '__main__':\n    print(add(1,2))\n"
    )
    return tmp_path


@pytest.fixture
def failing_project(tmp_path):
    """Project with syntax error."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "main.py").write_text("def broken(\n    pass\n")  # syntax error
    (tmp_path / "tests" / "test_fail.py").write_text(
        "def test_always_fails():\n    assert False, 'intentional'\n"
    )
    return tmp_path


def test_run_result_success():
    r = RunResult("cmd", 0, "ok", "", 1.0)
    assert r.success

def test_run_result_fail():
    r = RunResult("cmd", 1, "", "error", 0.5)
    assert not r.success

def test_run_result_timeout():
    r = RunResult("cmd", -1, "", "timeout", 30.0, timed_out=True)
    assert not r.success
    assert r.timed_out

def test_test_result_pass_rate_zero():
    t = TestResult(total=0)
    assert t.pass_rate == 0.0

def test_test_result_pass_rate():
    t = TestResult(total=10, passed=8)
    assert t.pass_rate == 80.0

def test_profile_result_empty():
    p = ProfileResult()
    assert p.total_time_sec == 0.0
    assert p.hotspots == []

def test_project_runner_nonexistent_dir():
    runner = ProjectRunner("/nonexistent/path/xyz")
    report = runner.run_all("test_id", run_tests=True, run_profile=True)
    assert not report.install_ok or len(report.errors) > 0

def test_project_runner_simple_project(simple_project):
    runner = ProjectRunner(str(simple_project))
    report = runner.run_all("test_id", run_tests=True, run_profile=True)
    assert isinstance(report, ProjectRunReport)
    assert report.project_dir == str(simple_project)
    # install_ok may fail if pip not available - that's OK
    # run_result should be set (syntax check)
    assert report.run_result is not None

def test_project_runner_syntax_check_ok(simple_project):
    runner = ProjectRunner(str(simple_project))
    result = runner._check_project(runner.run_all.__self__ if False else
                                   ProjectRunReport("t", str(simple_project)))
    # Can't call private easily - just test via run_all
    report = runner.run_all("t", run_tests=False, run_profile=False)
    if report.run_result:
        # Should succeed - no syntax errors
        assert "OK" in report.run_result.stdout or report.run_result.success

def test_project_runner_failing_project(failing_project):
    runner = ProjectRunner(str(failing_project))
    report = runner.run_all("fail_id", run_tests=False, run_profile=False)
    # Syntax error should be caught
    if report.run_result:
        assert not report.run_result.success or len(report.errors) > 0

def test_project_run_report_to_dict(simple_project):
    report = ProjectRunReport(
        project_id="p1",
        project_dir=str(simple_project),
        install_ok=True,
        run_result=RunResult("cmd", 0, "ok", "", 0.5),
    )
    d = report.to_dict()
    assert d["project_id"] == "p1"
    assert d["install_ok"] is True

def test_project_run_report_optimization_context():
    r = ProjectRunReport(project_id="p1", project_dir="/tmp/p1")
    r.test_result = TestResult(
        framework="pytest", total=5, passed=4, failed=1,
        coverage_pct=75.0, duration_sec=2.3
    )
    r.profile_result = ProfileResult(
        total_time_sec=1.5, peak_memory_mb=32.0,
        hotspots=[{"function": "slow_func", "cumtime": 0.8, "calls": 100}],
        recommendations=["Optimize slow_func"]
    )
    ctx = r.to_optimization_context()
    assert "pytest" in ctx
    assert "4/5" in ctx
    assert "75" in ctx
    assert "slow_func" in ctx
    assert "Optimize slow_func" in ctx

def test_profile_parse_output():
    runner = ProjectRunner("/tmp")
    sample = """   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    1.234    1.234 /app/main.py:10(slow_function)
      100    0.500    0.005    0.500    0.005 /app/utils.py:25(compute)
"""
    hotspots = runner._parse_profile(sample)
    assert len(hotspots) >= 1
    assert hotspots[0]["function"] == "slow_function"
    assert abs(hotspots[0]["cumtime"] - 1.234) < 0.001

def test_make_recommendations_slow_func():
    runner = ProjectRunner("/tmp")
    hotspots = [
        {"function": "process_data", "cumtime": 2.5, "calls": 1000},
    ]
    recs = runner._make_recommendations(hotspots)
    assert any("2.50" in r or "process_data" in r for r in recs)

def test_make_recommendations_sleep():
    runner = ProjectRunner("/tmp")
    hotspots = [{"function": "time.sleep", "cumtime": 3.0, "calls": 10}]
    recs = runner._make_recommendations(hotspots)
    assert any("sleep" in r.lower() or "async" in r.lower() for r in recs)

def test_find_entry_point(simple_project):
    runner = ProjectRunner(str(simple_project))
    entry = runner._find_entry()
    assert entry is not None
    assert entry.name == "main.py"
