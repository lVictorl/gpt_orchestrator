"""
prompt_registry/registry.py — PromptRegistry
Загрузка pipeline.json и подстановка плейсхолдеров.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class PromptTemplate:
    stage: str
    category_label: str
    prompt: str
    required_placeholders: List[str] = field(default_factory=list)
    key_outputs: List[str] = field(default_factory=list)
    creates_new_chat: bool = False
    parse_mode: str = "json"   # json | raw_code | raw_script | raw_readme


class PlaceholderFiller:
    """Заменяет {{KEY}} в тексте промпта."""

    @staticmethod
    def fill(template: str, variables: dict) -> str:
        def replacer(m: re.Match) -> str:
            key = m.group(1)
            val = variables.get(key, m.group(0))
            return str(val) if val is not None else m.group(0)

        return re.sub(r"\{\{(\w+)\}\}", replacer, template)

    @staticmethod
    def find_placeholders(template: str) -> List[str]:
        return re.findall(r"\{\{(\w+)\}\}", template)


class PromptRegistry:
    """Загружает pipeline.json и предоставляет промпты по stage."""

    def __init__(self, pipeline_path: str = "pipeline.json") -> None:
        self._path = Path(pipeline_path)
        self._templates: dict[str, PromptTemplate] = {}
        self._filler = PlaceholderFiller()
        self.load()

    def load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as fh:
            data = json.load(fh)
        for item in data.get("stages", []):
            stage = item["stage"]
            self._templates[stage] = PromptTemplate(
                stage=stage,
                category_label=item.get("category_label", ""),
                prompt=item.get("prompt", ""),
                required_placeholders=item.get("key_placeholders", []),
                key_outputs=item.get("key_outputs", []),
                creates_new_chat=item.get("creates_new_chat", False),
                parse_mode=item.get("parse_mode", "json"),
            )

    def get(self, stage: str) -> Optional[PromptTemplate]:
        return self._templates.get(stage)

    def fill(self, stage: str, variables: dict) -> str:
        tmpl = self.get(stage)
        if not tmpl:
            raise KeyError(f"Stage '{stage}' not found in pipeline.json")
        return self._filler.fill(tmpl.prompt, variables)

    def list_stages(self) -> List[str]:
        return list(self._templates.keys())
