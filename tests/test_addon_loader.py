"""tests/test_addon_loader.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from pathlib import Path
from core.addon_loader import AddonLoader


def make_addon(tmp_path: Path, name: str, content: str) -> Path:
    addon_dir = tmp_path / name
    addon_dir.mkdir(exist_ok=True)
    (addon_dir / "__init__.py").write_text(content)
    return addon_dir


def test_load_simple_addon(tmp_path):
    make_addon(tmp_path, "test_addon", '''
ADDON_META = {"name": "Test Addon", "version": "1.0.0"}

def register(app_context=None):
    return {"strategies": {}}
''')
    result = AddonLoader.load("test_addon", addons_dir=str(tmp_path))
    assert isinstance(result, dict)


def test_load_nonexistent_addon(tmp_path):
    with pytest.raises(FileNotFoundError):
        AddonLoader.load("nonexistent_addon", addons_dir=str(tmp_path))


def test_load_all_finds_addons(tmp_path):
    for name in ("addon_a", "addon_b", "addon_c"):
        make_addon(tmp_path, name, f'''
ADDON_META = {{"name": "{name}"}}
def register(app_context=None): return {{}}
''')
    loaded = AddonLoader.load_all(addons_dir=str(tmp_path))
    assert len(loaded) == 3
    assert "addon_a" in loaded
    assert "addon_b" in loaded


def test_load_all_empty_dir(tmp_path):
    loaded = AddonLoader.load_all(addons_dir=str(tmp_path))
    assert loaded == []


def test_load_all_nonexistent_dir():
    loaded = AddonLoader.load_all(addons_dir="/nonexistent/path")
    assert loaded == []


def test_addon_registers_strategy(tmp_path):
    make_addon(tmp_path, "my_strategy", '''
from strategy.task_analyzer import StrategyBase

class MyCustomStrategy(StrategyBase):
    def get_pipeline_stages(self): return ["problem_analysis"]
    def get_prompt_overrides(self): return {}

ADDON_META = {"name": "My Strategy"}
def register(app_context=None):
    return {"strategies": {"my_task": MyCustomStrategy}}
''')
    result = AddonLoader.load("my_strategy", addons_dir=str(tmp_path))
    assert "strategies" in result
    assert "my_task" in result["strategies"]


def test_addon_without_register(tmp_path):
    make_addon(tmp_path, "no_register", '''
ADDON_META = {"name": "No Register"}
# no register() function
''')
    # Should not raise
    result = AddonLoader.load("no_register", addons_dir=str(tmp_path))
    assert result == {}


def test_list_loaded_addons(tmp_path):
    AddonLoader._loaded.clear()
    make_addon(tmp_path, "list_test", '''
ADDON_META = {"name": "List Test", "version": "2.0"}
def register(app_context=None): return {}
''')
    AddonLoader.load("list_test", addons_dir=str(tmp_path))
    listing = AddonLoader.list_loaded()
    assert any(a["name"] == "List Test" for a in listing)


def test_addon_as_single_file(tmp_path):
    (tmp_path / "file_addon.py").write_text('''
ADDON_META = {"name": "File Addon"}
def register(app_context=None): return {"test": True}
''')
    result = AddonLoader.load("file_addon", addons_dir=str(tmp_path))
    assert result.get("test") is True


def test_broken_addon_doesnt_crash_load_all(tmp_path):
    make_addon(tmp_path, "broken", "this is not valid python !!!")
    make_addon(tmp_path, "good", '''
ADDON_META = {"name": "Good"}
def register(app_context=None): return {}
''')
    # load_all should continue past broken addon
    loaded = AddonLoader.load_all(addons_dir=str(tmp_path))
    assert "good" in loaded
    assert "broken" not in loaded
