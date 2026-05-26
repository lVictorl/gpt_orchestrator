"""
parser/response_parser.py — ResponseParser v2

Улучшения:
  - Надёжное извлечение JSON даже если ответ начинается с текста
  - Поддержка GPT_PROTO_V1 первым делом
  - Извлечение множества файлов из data.files
  - Fallback-парсинг: markdown блоки, SCRIPT_START/END, FILE_START/END
"""
from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple


class JSONExtractor:
    """Извлекает валидный JSON из сырого текста с несколькими стратегиями."""

    @staticmethod
    def extract(raw: str) -> Optional[dict | list]:
        if not raw:
            return None

        # Стратегия 1: убрать markdown ```json ... ``` и попробовать напрямую
        stripped = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
        try:
            result = json.loads(stripped)
            return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Стратегия 2: найти первый { или [ и извлечь до парного }
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            extracted = JSONExtractor._extract_balanced(stripped, start_char, end_char)
            if extracted is not None:
                return extracted

        # Стратегия 3: искать в оригинальном тексте (не stripped)
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            extracted = JSONExtractor._extract_balanced(raw, start_char, end_char)
            if extracted is not None:
                return extracted

        return None

    @staticmethod
    def _extract_balanced(text: str, start_char: str, end_char: str) -> Optional[dict | list]:
        idx = text.find(start_char)
        if idx == -1:
            return None

        depth = 0
        in_string = False
        escape = False
        end_idx = -1

        for i, ch in enumerate(text[idx:], start=idx):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break

        if end_idx == -1:
            return None

        candidate = text[idx: end_idx + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            # Попытка исправить экранирование
            try:
                fixed = candidate.replace('\n', '\\n').replace('\t', '\\t')
                return json.loads(fixed)
            except Exception:
                return None


class CodeBlockExtractor:
    """Извлекает блоки кода из ответа ИИ."""

    @staticmethod
    def extract_by_filename(raw: str, file_name: str) -> Optional[str]:
        pattern = rf"FILE_START:{re.escape(file_name)}\s*(.*?)\s*FILE_END:{re.escape(file_name)}"
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            return m.group(1).strip()
        m2 = re.search(r"```[\w]*\n?(.*?)```", raw, re.DOTALL)
        return m2.group(1).strip() if m2 else raw.strip() or None

    @staticmethod
    def extract_script(raw: str) -> Optional[str]:
        m = re.search(r"SCRIPT_START\s*(.*?)\s*SCRIPT_END", raw, re.DOTALL)
        if m:
            return m.group(1).strip()
        m2 = re.search(r"```(?:bash|sh|shell)\s*(.*?)```", raw, re.DOTALL)
        return m2.group(1).strip() if m2 else None

    @staticmethod
    def extract_readme(raw: str) -> Optional[str]:
        m = re.search(r"README_START\s*(.*?)\s*README_END", raw, re.DOTALL)
        if m:
            return m.group(1).strip()
        m2 = re.search(r"```(?:markdown|md)\s*(.*?)```", raw, re.DOTALL)
        return m2.group(1).strip() if m2 else None

    @staticmethod
    def extract_any_code(raw: str) -> Optional[str]:
        m = re.search(r"```[\w]*\n?(.*?)```", raw, re.DOTALL)
        return m.group(1).strip() if m else raw.strip()

    @staticmethod
    def extract_all_code_blocks(raw: str) -> List[Tuple[str, str]]:
        """Возвращает список (lang, code) для всех markdown блоков."""
        pattern = r"```(\w*)\n?(.*?)```"
        matches = re.findall(pattern, raw, re.DOTALL)
        return [(lang.strip(), code.strip()) for lang, code in matches if code.strip()]


class ResponseParser:
    """Фасад: объединяет JSON и code-extraction."""

    def __init__(self) -> None:
        self._json = JSONExtractor()
        self._code = CodeBlockExtractor()

    def parse_json(self, raw: str) -> Optional[dict | list]:
        return self._json.extract(raw)

    def parse_proto_v1(self, raw: str) -> Optional[dict]:
        """Извлечь и валидировать GPT_PROTO_V1 конверт."""
        result = self._json.extract(raw)
        if isinstance(result, dict) and result.get("proto") == "GPT_PROTO_V1":
            return result
        return None

    def extract_files_from_data(self, data: dict) -> List[dict]:
        """
        Извлечь список файлов из data.files.
        Возвращает [{'filename': str, 'content': str, 'description': str}].
        """
        files = data.get("files", [])
        if not isinstance(files, list):
            return []
        result = []
        for f in files:
            if not isinstance(f, dict):
                continue
            filename = str(f.get("filename", "")).strip()
            content  = str(f.get("content", "")).strip()
            if filename and content:
                result.append({
                    "filename":    filename,
                    "content":     content,
                    "description": str(f.get("description", "")),
                })
        return result

    def extract_code_block(self, raw: str, file_name: str) -> Optional[str]:
        return self._code.extract_by_filename(raw, file_name)

    def extract_script(self, raw: str) -> Optional[str]:
        return self._code.extract_script(raw)

    def extract_readme(self, raw: str) -> Optional[str]:
        return self._code.extract_readme(raw)

    def extract_all_code_blocks(self, raw: str) -> List[Tuple[str, str]]:
        return self._code.extract_all_code_blocks(raw)

    def build_context(self, stage: str, parsed: dict, ctx: dict) -> dict:
        ctx[stage] = parsed
        return ctx

    def context_to_str(self, ctx: dict) -> str:
        return json.dumps(ctx, ensure_ascii=False, indent=2)

    def context_to_compact(self, ctx: dict) -> str:
        return json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
