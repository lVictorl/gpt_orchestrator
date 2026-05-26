"""
runner/project_runner.py — ProjectRunner

Запускает сгенерированный проект, его тесты и профилировщик.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RunResult:
    command:      str
    returncode:   int
    stdout:       str = ""
    stderr:       str = ""
    duration_sec: float = 0.0
    timed_out:    bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass
class TestResult:
    framework:    str = ""
    total:        int = 0
    passed:       int = 0
    failed:       int = 0
    errors:       int = 0
    skipped:      int = 0
    coverage_pct: float = 0.0
    duration_sec: float = 0.0
    output:       str = ""
    success:      bool = False

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0.0


@dataclass
class ProfileResult:
    total_time_sec:  float = 0.0
    peak_memory_mb:  float = 0.0
    hotspots:        List[Dict] = field(default_factory=list)
    recommendations: List[str]  = field(default_factory=list)
    profile_output:  str = ""


@dataclass
class ProjectRunReport:
    project_id:     str
    project_dir:    str
    run_result:     Optional[RunResult]     = None
    test_result:    Optional[TestResult]    = None
    profile_result: Optional[ProfileResult] = None
    install_ok:     bool = False
    errors:         List[str] = field(default_factory=list)
    timestamp:      str = ""

    def to_dict(self) -> dict:
        import dataclasses
        return json.loads(json.dumps(dataclasses.asdict(self), default=str))

    def to_optimization_context(self) -> str:
        """Контекст профилирования для промпта оптимизации."""
        lines = ["=== РЕЗУЛЬТАТЫ ЗАПУСКА И ПРОФИЛИРОВАНИЯ ==="]
        if self.run_result:
            r = self.run_result
            s = "OK" if r.success else f"FAIL (code {r.returncode})"
            lines.append(f"Запуск: {s} за {r.duration_sec:.1f}с")
            if not r.success and r.stderr:
                lines.append(f"Ошибка: {r.stderr[:300]}")
        if self.test_result:
            t = self.test_result
            lines.append(
                f"Тесты [{t.framework}]: {t.passed}/{t.total} OK, "
                f"покрытие {t.coverage_pct:.0f}%, {t.duration_sec:.1f}с"
            )
            if t.failed or t.errors:
                lines.append(f"Провалено: {t.failed}, ошибок: {t.errors}")
                if t.output:
                    lines.append(f"Вывод:\n{t.output[-600:]}")
        if self.profile_result:
            p = self.profile_result
            lines.append(f"Профиль: {p.total_time_sec:.2f}с, RAM {p.peak_memory_mb:.1f}MB")
            for h in p.hotspots[:5]:
                lines.append(
                    f"  • {h.get('function','?')} — {h.get('cumtime',0):.3f}с"
                )
            for rec in p.recommendations[:4]:
                lines.append(f"  💡 {rec}")
        if self.errors:
            lines.append(f"Ошибки: {'; '.join(self.errors[:2])}")
        return "\n".join(lines)


class ProjectRunner:
    TIMEOUT_INSTALL = 120
    TIMEOUT_RUN     = 30
    TIMEOUT_TESTS   = 180
    TIMEOUT_PROFILE = 60

    def __init__(self, project_dir: str, logger=None) -> None:
        self._dir = Path(project_dir)
        self._log = logger
        self._is_win = platform.system() == "Windows"

    def run_all(self, project_id: str, run_tests=True, run_profile=True) -> ProjectRunReport:
        import datetime
        report = ProjectRunReport(
            project_id=project_id,
            project_dir=str(self._dir),
            timestamp=datetime.datetime.utcnow().isoformat(),
        )
        if not self._dir.exists():
            report.errors.append(f"Dir not found: {self._dir}")
            return report

        self._info("Installing deps...")
        report.install_ok = self._install_deps(report)

        self._info("Syntax-checking project...")
        report.run_result = self._check_project(report)

        if run_tests:
            self._info("Running tests...")
            report.test_result = self._run_tests(report)

        if run_profile:
            self._info("Profiling...")
            report.profile_result = self._profile_project(report)

        return report

    def _info(self, msg: str) -> None:
        if self._log:
            try: self._log.info(f"Runner: {msg}")
            except Exception: pass

    def _install_deps(self, report: ProjectRunReport) -> bool:
        req = self._dir / "requirements.txt"
        if req.exists():
            r = self._cmd(
                [sys.executable, "-m", "pip", "install", "-r", str(req),
                 "-q", "--break-system-packages"],
                timeout=self.TIMEOUT_INSTALL,
            )
            if not r.success:
                report.errors.append(f"pip install: {r.stderr[:150]}")
            return r.success
        pkgjson = self._dir / "package.json"
        if pkgjson.exists():
            r = self._cmd(["npm", "install", "--silent"], timeout=self.TIMEOUT_INSTALL)
            return r.success
        gomod = self._dir / "go.mod"
        if gomod.exists():
            r = self._cmd(["go", "mod", "download"], timeout=self.TIMEOUT_INSTALL)
            return r.success
        return True

    def _check_project(self, report: ProjectRunReport) -> Optional[RunResult]:
        py_files = [f for f in self._dir.rglob("*.py")
                    if "__pycache__" not in str(f) and "test_" not in f.name]
        if not py_files:
            return None
        results = []
        for pf in py_files[:10]:
            r = self._cmd([sys.executable, "-m", "py_compile", str(pf)], timeout=10)
            if not r.success:
                report.errors.append(f"Syntax error in {pf.name}: {r.stderr[:100]}")
            results.append(r)
        ok_count = sum(1 for r in results if r.success)
        return RunResult(
            command="py_compile",
            returncode=0 if ok_count == len(results) else 1,
            stdout=f"{ok_count}/{len(results)} files OK",
            duration_sec=sum(r.duration_sec for r in results),
        )

    def _run_tests(self, report: ProjectRunReport) -> Optional[TestResult]:
        tests_dir = self._dir / "tests"
        if not tests_dir.exists():
            tests_dir = self._dir  # search root
        py_tests = (list(tests_dir.rglob("test_*.py")) +
                    list(tests_dir.rglob("*_test.py")))
        if py_tests:
            return self._run_pytest(tests_dir)
        if (self._dir / "go.mod").exists():
            return self._run_go_test()
        if (self._dir / "package.json").exists():
            return self._run_npm_test()
        return None

    def _run_pytest(self, tests_dir: Path) -> TestResult:
        import re
        result = TestResult(framework="pytest")
        t0 = time.monotonic()
        cmd = [sys.executable, "-m", "pytest", str(tests_dir),
               "-v", "--tb=short", "-q", "--no-header"]
        cov_cmd = cmd + ["--cov=.", "--cov-report=term-missing:skip-covered"]
        r = self._cmd(cov_cmd, timeout=self.TIMEOUT_TESTS)
        if r.returncode not in (0, 1, 2):
            r = self._cmd(cmd, timeout=self.TIMEOUT_TESTS)
        result.duration_sec = time.monotonic() - t0
        out = r.stdout + r.stderr
        result.output = out[-2000:]
        result.success = (r.returncode == 0)
        for pat, attr in [
            (r"(\d+) passed", "passed"), (r"(\d+) failed", "failed"),
            (r"(\d+) error",  "errors"), (r"(\d+) skipped", "skipped"),
        ]:
            m = re.search(pat, out, re.IGNORECASE)
            if m:
                setattr(result, attr, int(m.group(1)))
        result.total = result.passed + result.failed + result.errors + result.skipped
        m = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", out)
        if m:
            result.coverage_pct = float(m.group(1))
        return result

    def _run_go_test(self) -> TestResult:
        import re
        result = TestResult(framework="go_test")
        t0 = time.monotonic()
        r = self._cmd(["go", "test", "./...", "-v"], timeout=self.TIMEOUT_TESTS)
        result.duration_sec = time.monotonic() - t0
        result.output = (r.stdout + r.stderr)[-2000:]
        result.success = r.success
        result.passed = len(re.findall(r"--- PASS:", r.stdout))
        result.failed = len(re.findall(r"--- FAIL:", r.stdout))
        result.total = result.passed + result.failed
        return result

    def _run_npm_test(self) -> TestResult:
        result = TestResult(framework="npm")
        t0 = time.monotonic()
        r = self._cmd(["npm", "test"], timeout=self.TIMEOUT_TESTS)
        result.duration_sec = time.monotonic() - t0
        result.output = (r.stdout + r.stderr)[-2000:]
        result.success = r.success
        return result

    def _profile_project(self, report: ProjectRunReport) -> Optional[ProfileResult]:
        entry = self._find_entry()
        if not entry or entry.suffix != ".py":
            # Find largest Python file as proxy
            py_files = [f for f in self._dir.rglob("*.py")
                        if "__pycache__" not in str(f) and "test_" not in f.name]
            if not py_files:
                return None
            entry = max(py_files, key=lambda f: f.stat().st_size)
        return self._cprofile(entry)

    def _find_entry(self) -> Optional[Path]:
        for name in ["main.py", "app.py", "run.py", "bot.py",
                     "src/main.py", "src/app.py", "server.py"]:
            p = self._dir / name
            if p.exists():
                return p
        return next(self._dir.rglob("main.py"), None)

    def _cprofile(self, entry: Path) -> ProfileResult:
        import re
        result = ProfileResult()
        t0 = time.monotonic()
        script = f"""
import cProfile, pstats, io, sys
sys.path.insert(0, r'{self._dir}')
pr = cProfile.Profile()
pr.enable()
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location('m', r'{entry}')
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        try: spec.loader.exec_module(mod)
        except (SystemExit, KeyboardInterrupt, Exception): pass
finally:
    pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s)
ps.sort_stats('cumulative')
ps.print_stats(25)
print(s.getvalue())
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script)
            tmp = f.name
        try:
            r = self._cmd([sys.executable, tmp], timeout=self.TIMEOUT_PROFILE)
            result.total_time_sec = time.monotonic() - t0
            result.profile_output = r.stdout[:3000]
            result.hotspots = self._parse_profile(r.stdout)
            result.recommendations = self._make_recommendations(result.hotspots)
        finally:
            try: os.unlink(tmp)
            except Exception: pass

        # Memory via /proc
        try:
            txt = Path("/proc/self/status").read_text()
            for line in txt.split("\n"):
                if line.startswith("VmRSS:"):
                    result.peak_memory_mb = int(line.split()[1]) / 1024
                    break
        except Exception:
            result.peak_memory_mb = entry.stat().st_size * 50 / 1_048_576
        return result

    def _parse_profile(self, output: str) -> List[Dict]:
        import re
        hotspots = []
        pat = re.compile(
            r"\s*(\d+/?\d*)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(.+):(\d+)\((.+)\)"
        )
        for line in output.split("\n"):
            m = pat.search(line)
            if m and "{" not in m.group(8):
                try:
                    hotspots.append({
                        "calls":    int(m.group(1).split("/")[0]),
                        "tottime":  float(m.group(2)),
                        "cumtime":  float(m.group(4)),
                        "file":     m.group(6),
                        "line":     int(m.group(7)),
                        "function": m.group(8),
                    })
                except (ValueError, IndexError):
                    continue
            if len(hotspots) >= 20:
                break
        return hotspots

    def _make_recommendations(self, hotspots: List[Dict]) -> List[str]:
        recs = []
        for h in hotspots[:5]:
            fn, ct = h.get("function", ""), h.get("cumtime", 0)
            if ct > 1.0:
                recs.append(f"'{fn}' занимает {ct:.2f}с — кэшируйте или оптимизируйте алгоритм")
            if "sleep" in fn.lower():
                recs.append(f"'{fn}': sleep() → asyncio.sleep() для async-кода")
            if any(k in fn.lower() for k in ("read", "write", "open")) and ct > 0.1:
                recs.append(f"'{fn}': медленный I/O — используйте буферизацию или async I/O")
        if sum(h.get("cumtime", 0) for h in hotspots[:3]) > 5.0:
            recs.append("Суммарное время >5с — рассмотрите asyncio или multiprocessing")
        return recs

    def _cmd(self, cmd: List[str], timeout: int = 60) -> RunResult:
        t0 = time.monotonic()
        try:
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONUNBUFFERED": "1"}
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=str(self._dir), env=env,
            )
            return RunResult(
                command=" ".join(str(c) for c in cmd),
                returncode=proc.returncode,
                stdout=proc.stdout[:4000],
                stderr=proc.stderr[:2000],
                duration_sec=time.monotonic() - t0,
            )
        except subprocess.TimeoutExpired:
            return RunResult(" ".join(str(c) for c in cmd), -1,
                             stderr=f"Timeout {timeout}s",
                             duration_sec=timeout, timed_out=True)
        except Exception as exc:
            return RunResult(" ".join(str(c) for c in cmd), -2,
                             stderr=str(exc)[:200],
                             duration_sec=time.monotonic() - t0)
