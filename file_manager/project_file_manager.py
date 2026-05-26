"""
file_manager/project_file_manager.py — ProjectFileManager + ReportGenerator v2

Новое:
  - Полноценный HTML-отчёт с critique score, этапами, временной шкалой
  - save_stage_files: сохраняет артефакты каждого этапа в нужную подпапку
  - Группировка: src/ code/ tests/ docs/ critique/
"""
from __future__ import annotations

import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ProjectFileManager:
    """Создаёт и управляет файловой структурой проекта."""

    BASE_DIRS = ["src", "tests", "docs", "logs", "critique"]

    # Этап → подпапка для артефактов
    STAGE_DIR_MAP: Dict[str, str] = {
        "code_block_generation":           "src",
        "optimization":                    "src",
        "refactoring":                     "src",
        "unit_tests":                      "tests",
        "deployment_commands":             "docs",
        "readme_generation":               "docs",
        "project_critique":                "critique",
        "problem_analysis":                "docs",
        "global_spec_and_api":             "docs",
        "architecture_analysis":           "docs",
    }

    def __init__(self, projects_root: str = "projects") -> None:
        self._root = Path(projects_root)
        self._root.mkdir(parents=True, exist_ok=True)

    def create_project_dir(self, project_id: str) -> Path:
        project_dir = self._root / project_id
        for d in self.BASE_DIRS:
            (project_dir / d).mkdir(parents=True, exist_ok=True)
        return project_dir

    def save_file(self, project_id: str, relative_path: str, content: str) -> Path:
        project_dir = self._root / project_id
        target = project_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def save_stage_artifact(
        self, project_id: str, stage: str, filename: str, content: str
    ) -> Path:
        """Сохранить артефакт этапа в нужную подпапку."""
        subdir = self.STAGE_DIR_MAP.get(stage, "docs")
        return self.save_file(project_id, f"{subdir}/{filename}", content)

    def get_project_dir(self, project_id: str) -> Path:
        return self._root / project_id

    def list_files(self, project_id: str) -> List[str]:
        project_dir = self._root / project_id
        if not project_dir.exists():
            return []
        return [
            str(p.relative_to(project_dir))
            for p in project_dir.rglob("*")
            if p.is_file()
        ]

    def get_structure_str(self, project_id: str) -> str:
        """Текстовое дерево файлов проекта (для вставки в промпт)."""
        files = self.list_files(project_id)
        lines = [f"projects/{project_id}/"]
        for f in sorted(files):
            depth = f.count(os.sep)
            lines.append("  " * depth + "├── " + Path(f).name)
        return "\n".join(lines)


class ReportGenerator:
    """Генерирует HTML-отчёт о проекте с детальной информацией о генерации."""

    def generate(
        self,
        project_id: str,
        title: str,
        stages_data: List[dict],
        output_path: str,
        critique_data: Optional[dict] = None,
    ) -> str:
        """
        stages_data: список словарей
          {stage, status, confidence, summary, duration_sec, warnings, tokens}
        critique_data: данные этапа project_critique (grades, score, ...)
        """
        total_duration = sum(s.get("duration_sec", 0) for s in stages_data)
        total_tokens   = sum(s.get("tokens", 0) for s in stages_data)
        done_count     = sum(1 for s in stages_data if s.get("status") == "OK")
        warn_count     = sum(1 for s in stages_data if s.get("status") == "WARN")
        error_count    = sum(1 for s in stages_data if s.get("status") in ("ERROR",))

        score = critique_data.get("overall_score", "—") if critique_data else "—"
        compliance = critique_data.get("compliance_percent", "—") if critique_data else "—"

        # Score color
        if isinstance(score, int):
            score_color = "#2ea043" if score >= 70 else "#d29922" if score >= 50 else "#da3633"
        else:
            score_color = "#8b949e"

        stages_html = ""
        for s in stages_data:
            st = s.get("status", "OK")
            icon = {"OK": "✅", "WARN": "⚠️", "ERROR": "❌", "PARTIAL": "🔶"}.get(st, "❓")
            conf = s.get("confidence", "HIGH")
            conf_icon = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(conf, "")
            dur = s.get("duration_sec", 0)
            border = {"OK": "#2ea043", "WARN": "#d29922", "ERROR": "#da3633", "PARTIAL": "#e3b341"}.get(st, "#30363d")
            warnings_html = ""
            for w in s.get("warnings", []):
                warnings_html += f'<li style="color:#d29922">⚠️ {w}</li>'
            stages_html += f"""
            <div class="stage" style="border-left:4px solid {border}">
              <div class="stage-header">
                <span class="stage-icon">{icon}</span>
                <span class="stage-name">{s.get("stage","")}</span>
                <span class="stage-meta">{conf_icon} {dur:.1f}с</span>
              </div>
              <div class="stage-summary">{s.get("summary","")}</div>
              {f'<ul class="warnings">{warnings_html}</ul>' if warnings_html else ""}
            </div>"""

        # Grades bars
        grades_html = ""
        if critique_data and "grades" in critique_data:
            grades = critique_data["grades"]
            names = {
                "architecture": "Архитектура",
                "code_quality": "Качество кода",
                "test_coverage": "Тесты",
                "documentation": "Документация",
                "security": "Безопасность",
                "performance": "Производительность",
                "completeness": "Полнота",
            }
            for key, name in names.items():
                val = grades.get(key, 0)
                pct = val * 10
                bar_color = "#2ea043" if val >= 7 else "#d29922" if val >= 4 else "#da3633"
                grades_html += f"""
                <div class="grade-row">
                  <span class="grade-name">{name}</span>
                  <div class="grade-bar-wrap">
                    <div class="grade-bar" style="width:{pct}%;background:{bar_color}"></div>
                  </div>
                  <span class="grade-val">{val}/10</span>
                </div>"""

        strengths_html = ""
        weaknesses_html = ""
        recs_html = ""
        if critique_data:
            for item in critique_data.get("strengths", [])[:5]:
                strengths_html += f"<li>{item}</li>"
            for item in critique_data.get("weaknesses", [])[:5]:
                weaknesses_html += f"<li>{item}</li>"
            for item in critique_data.get("recommendations", [])[:5]:
                recs_html += f"<li>{item}</li>"

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>GPT-Orchestrator — Отчёт: {title}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'JetBrains Mono',Consolas,monospace;background:#0d1117;color:#e6edf3;padding:24px;line-height:1.6}}
  h1{{color:#79c0ff;font-size:22px;margin-bottom:4px}}
  h2{{color:#8b949e;font-size:13px;margin-bottom:24px;font-weight:normal}}
  h3{{color:#c9d1d9;font-size:14px;margin:20px 0 10px;border-bottom:1px solid #21262d;padding-bottom:6px}}
  .header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px}}
  .score-box{{background:#161b22;border:2px solid {score_color};border-radius:12px;padding:16px 24px;text-align:center}}
  .score-num{{font-size:48px;font-weight:bold;color:{score_color};line-height:1}}
  .score-label{{color:#8b949e;font-size:11px;margin-top:4px}}
  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
  .stat{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px;text-align:center}}
  .stat-num{{font-size:24px;font-weight:bold;color:#79c0ff}}
  .stat-label{{font-size:11px;color:#8b949e;margin-top:2px}}
  .stage{{background:#161b22;border-radius:6px;padding:12px 16px;margin-bottom:8px}}
  .stage-header{{display:flex;align-items:center;gap:8px;margin-bottom:4px}}
  .stage-icon{{font-size:14px}}
  .stage-name{{font-weight:bold;color:#c9d1d9;font-size:13px}}
  .stage-meta{{margin-left:auto;color:#484f58;font-size:11px}}
  .stage-summary{{color:#8b949e;font-size:12px}}
  .warnings{{margin-top:6px;padding-left:16px;font-size:11px}}
  .grade-row{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
  .grade-name{{width:160px;font-size:12px;color:#8b949e;flex-shrink:0}}
  .grade-bar-wrap{{flex:1;background:#21262d;border-radius:4px;height:10px;overflow:hidden}}
  .grade-bar{{height:100%;border-radius:4px;transition:width 0.3s}}
  .grade-val{{width:40px;text-align:right;font-size:12px;color:#c9d1d9}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
  .panel{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px}}
  .panel h4{{color:#c9d1d9;font-size:13px;margin-bottom:8px}}
  .panel ul{{list-style:none;padding:0}}
  .panel ul li{{padding:4px 0;font-size:12px;color:#8b949e;border-bottom:1px solid #21262d}}
  .panel ul li:last-child{{border-bottom:none}}
  footer{{margin-top:40px;text-align:center;color:#484f58;font-size:11px;border-top:1px solid #21262d;padding-top:16px}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🤖 GPT-Orchestrator — Отчёт о генерации</h1>
    <h2>{title}</h2>
    <div style="color:#484f58;font-size:11px">ID проекта: {project_id} &nbsp;|&nbsp; {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</div>
  </div>
  <div class="score-box">
    <div class="score-num">{score}</div>
    <div class="score-label">/100 &nbsp; оценка</div>
    <div style="color:#8b949e;font-size:11px;margin-top:4px">Соответствие: {compliance}%</div>
  </div>
</div>

<div class="stats">
  <div class="stat"><div class="stat-num">{len(stages_data)}</div><div class="stat-label">Этапов</div></div>
  <div class="stat"><div class="stat-num" style="color:#2ea043">{done_count}</div><div class="stat-label">Успешно</div></div>
  <div class="stat"><div class="stat-num" style="color:#d29922">{warn_count}</div><div class="stat-label">Предупреждений</div></div>
  <div class="stat"><div class="stat-num" style="color:#da3633">{error_count}</div><div class="stat-label">Ошибок</div></div>
</div>

<div class="stats">
  <div class="stat"><div class="stat-num">{total_duration:.0f}с</div><div class="stat-label">Общее время</div></div>
  <div class="stat"><div class="stat-num">~{total_tokens}</div><div class="stat-label">Токенов</div></div>
  <div class="stat"><div class="stat-num">{compliance}%</div><div class="stat-label">Соответствие</div></div>
  <div class="stat"><div class="stat-num">{score}</div><div class="stat-label">Финальный балл</div></div>
</div>

<h3>📋 Этапы генерации</h3>
{stages_html}

{"<h3>🔍 Критика проекта</h3><div class='panel'>" + grades_html + "</div>" if grades_html else ""}

<div class="two-col" style="margin-top:20px">
  {"<div class='panel'><h4 style='color:#2ea043'>✅ Сильные стороны</h4><ul>" + strengths_html + "</ul></div>" if strengths_html else ""}
  {"<div class='panel'><h4 style='color:#da3633'>⚠️ Слабые стороны</h4><ul>" + weaknesses_html + "</ul></div>" if weaknesses_html else ""}
</div>

{"<div class='panel' style='margin-top:20px'><h4 style='color:#388bfd'>💡 Рекомендации</h4><ul>" + recs_html + "</ul></div>" if recs_html else ""}

<footer>
  Сгенерировано GPT-Orchestrator v1.3.0 &nbsp;·&nbsp; {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
</footer>
</body>
</html>"""

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")
        return output_path
