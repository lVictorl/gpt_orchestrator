"""
core/config_manager.py — ConfigManager
Управление конфигурацией через TOML.

Исправление #10: defaults включают deepseek_key и model_deepseek.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

try:
    import tomllib          # Python 3.11+
except ImportError:
    import tomli as tomllib  # pip fallback

try:
    import tomli_w
    _CAN_WRITE = True
except ImportError:
    _CAN_WRITE = False


_DEFAULTS: dict[str, Any] = {
    "api": {
        "provider": "anthropic",        # "openai" | "anthropic" | "deepseek"
        "openai_key": "",
        "anthropic_key": "",
        "deepseek_key": "",             # #3 DeepSeek
        "model_openai": "gpt-4o",
        "model_anthropic": "claude-sonnet-4-20250514",
        "model_deepseek": "deepseek-chat",  # #3
        "max_tokens": 8192,
        "temperature": 0.3,
        "request_timeout": 120,
        "rpm": 20,
    },
    "app": {
        "projects_dir": "projects",
        "log_level": "INFO",
        "theme": "dark",
        "font_size": 13,
        "vim_mode": True,
    },
}


class ConfigManager:
    """Читает/пишет config.toml; поддерживает dot-path доступ."""

    def __init__(self, path: str = "config.toml") -> None:
        self._path = Path(path)
        self._data: dict[str, Any] = {}
        self._load_defaults()

    # ── публичный API ──────────────────────────────────────

    def load(self, path: str | None = None) -> None:
        if path:
            self._path = Path(path)
        if self._path.exists():
            with open(self._path, "rb") as fh:
                loaded = tomllib.load(fh)
            self._deep_merge(self._data, loaded)

    def save(self) -> None:
        if not _CAN_WRITE:
            return
        with open(self._path, "wb") as fh:
            tomli_w.dump(self._data, fh)

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-path: config.get('api.openai_key')"""
        parts = key.split(".")
        node: Any = self._data
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                return default
            node = node[p]
        return node

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        node = self._data
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value

    # ── helpers ──────────────────────────────────────────

    def _load_defaults(self) -> None:
        self._data = copy.deepcopy(_DEFAULTS)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConfigManager._deep_merge(base[k], v)
            else:
                base[k] = v
