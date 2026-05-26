"""
core/addon_loader.py — AddonLoader

Загружает аддоны из директории addons/.
Каждый аддон должен иметь функцию register(app_context) -> dict.
"""
from __future__ import annotations
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


class AddonLoader:
    _loaded: Dict[str, Any] = {}

    @classmethod
    def load_all(cls, app_context=None, addons_dir: Optional[str] = None) -> List[str]:
        root = Path(addons_dir) if addons_dir else Path(__file__).resolve().parent.parent / "addons"
        if not root.exists():
            return []
        loaded = []
        for item in sorted(root.iterdir()):
            if item.is_dir() and (item / "__init__.py").exists():
                try:
                    cls.load(item.name, app_context, addons_dir=str(root))
                    loaded.append(item.name)
                except Exception as exc:
                    print(f"[AddonLoader] Failed to load '{item.name}': {exc}")
            elif item.suffix == ".py" and item.name != "__init__.py":
                name = item.stem
                try:
                    cls.load(name, app_context, addons_dir=str(root))
                    loaded.append(name)
                except Exception as exc:
                    print(f"[AddonLoader] Failed to load '{name}': {exc}")
        return loaded

    @classmethod
    def load(cls, name: str, app_context=None, addons_dir: Optional[str] = None) -> dict:
        root = Path(addons_dir) if addons_dir else Path(__file__).resolve().parent.parent / "addons"
        # Try package first
        pkg_path = root / name / "__init__.py"
        mod_path = root / f"{name}.py"
        path = pkg_path if pkg_path.exists() else mod_path if mod_path.exists() else None
        if path is None:
            raise FileNotFoundError(f"Addon '{name}' not found in {root}")

        spec = importlib.util.spec_from_file_location(f"addons.{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"addons.{name}"] = module
        spec.loader.exec_module(module)

        result = {}
        if hasattr(module, "register"):
            result = module.register(app_context) or {}
            # Apply strategies
            strategies = result.get("strategies", {})
            if strategies:
                try:
                    from strategy.task_analyzer import TaskAnalyzer
                    for key, cls_ref in strategies.items():
                        TaskAnalyzer._addon_strategies = getattr(TaskAnalyzer, "_addon_strategies", {})
                        TaskAnalyzer._addon_strategies[key] = cls_ref
                except Exception:
                    pass

        cls._loaded[name] = {
            "module": module,
            "meta": getattr(module, "ADDON_META", {"name": name}),
            "exports": result,
        }
        return result

    @classmethod
    def list_loaded(cls) -> List[dict]:
        return [
            {"name": k, **v["meta"]} for k, v in cls._loaded.items()
        ]
