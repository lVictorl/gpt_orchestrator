"""
tests/test_fixes.py — Tests for all fixes from log analysis
"""
import sys, os, json, ast
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── 1. CSS border-radius is single-value in Python strings ──

def test_no_multivalue_borderradius_chat_widget():
    """No multi-value border-radius in chat_widget.py (Qt doesn't support it)."""
    import re
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'gui', 'chat_widget.py')).read()
    # Match patterns like "border-radius: 4px 6px" (2+ values)
    pattern = re.compile(r'border-radius:\s*[\d.]+\w*\s+[\d.]+', re.IGNORECASE)
    matches = pattern.findall(src)
    assert matches == [], f"Multi-value border-radius found: {matches}"


def test_no_multivalue_borderradius_pipeline_panel():
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'gui', 'pipeline_panel.py')).read()
    import re
    pattern = re.compile(r'border-radius:\s*[\d.]+\w*\s+[\d.]+', re.IGNORECASE)
    matches = pattern.findall(src)
    assert matches == [], f"Multi-value border-radius: {matches}"


# ── 2. All Python files have valid syntax ──────────────────

def test_all_files_syntax():
    root = os.path.dirname(os.path.dirname(__file__))
    errors = []
    for dirpath, _, files in os.walk(root):
        if '__pycache__' in dirpath:
            continue
        for fn in files:
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dirpath, fn)
            try:
                ast.parse(open(path, encoding='utf-8').read())
            except SyntaxError as e:
                errors.append(f"{fn}: line {e.lineno}: {e.msg}")
    assert errors == [], "Syntax errors:\n" + "\n".join(errors)


# ── 3. Pipeline JSON integrity ─────────────────────────────

def test_pipeline_all_stages_have_proto_v1():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pipeline.json')
    data = json.load(open(path))
    for s in data['stages']:
        assert 'GPT_PROTO_V1' in s['prompt'], \
            f"Stage '{s['stage']}' missing GPT_PROTO_V1"


def test_pipeline_code_stages_have_files():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pipeline.json')
    data = json.load(open(path))
    code_stages = {'code_block_generation', 'unit_tests', 'optimization', 'deployment_commands'}
    for s in data['stages']:
        if s['stage'] in code_stages:
            assert 'files' in s['prompt'], \
                f"Code stage '{s['stage']}' missing 'files' instruction"


def test_pipeline_15_stages():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pipeline.json')
    data = json.load(open(path))
    assert len(data['stages']) == 15


def test_pipeline_critique_has_test_cases():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pipeline.json')
    data = json.load(open(path))
    critique = next(s for s in data['stages'] if s['stage'] == 'project_critique')
    assert 'test_cases' in critique['prompt']
    assert 'TC-001' in critique['prompt']


# ── 4. Protocol per-stage prompts ─────────────────────────

def test_protocol_system_prompts_contain_stage_data():
    from core.protocol import get_system_prompt
    # Code stages must have 'files' in their prompt
    for stage in ('code_block_generation', 'unit_tests', 'optimization'):
        sp = get_system_prompt(stage)
        assert 'files' in sp, f"Stage {stage} system prompt missing 'files'"
        assert 'GPT_PROTO_V1' in sp

    # Analysis stages must have analysis-style data
    for stage in ('problem_analysis', 'user_clarification'):
        sp = get_system_prompt(stage)
        assert 'GPT_PROTO_V1' in sp
        assert 'data' in sp


def test_protocol_critique_has_test_cases_and_grades():
    from core.protocol import CRITIQUE_SYSTEM_PROMPT
    assert 'test_cases' in CRITIQUE_SYSTEM_PROMPT
    assert 'overall_score' in CRITIQUE_SYSTEM_PROMPT
    assert 'grades' in CRITIQUE_SYSTEM_PROMPT
    assert 'compliance_percent' in CRITIQUE_SYSTEM_PROMPT


# ── 5. Token optimizer ────────────────────────────────────

def test_token_optimizer_deepseek_models_pricing():
    from token_saver.token_optimizer import MODEL_PRICING
    deepseek_models = [m for m in MODEL_PRICING if 'deepseek' in m]
    assert len(deepseek_models) >= 4
    # All must have positive prices
    for m in deepseek_models:
        assert MODEL_PRICING[m]['input'] > 0
        assert MODEL_PRICING[m]['output'] >= MODEL_PRICING[m]['input']


def test_token_optimizer_count_realistic():
    from token_saver.token_optimizer import TokenOptimizer
    # "Hello world" ~ 2 tokens in GPT tokenizer
    t = TokenOptimizer.count_tokens("Hello world")
    assert 1 <= t <= 5

    # Empty
    assert TokenOptimizer.count_tokens("") == 0

    # Long text
    long = "word " * 1000
    t_long = TokenOptimizer.count_tokens(long)
    assert t_long > 100


def test_token_optimizer_reset():
    from token_saver.token_optimizer import TokenOptimizer
    opt = TokenOptimizer()
    opt.add_usage(1000, 2000)
    opt.reset_stats()
    t_in, t_out = opt.get_total_tokens()
    assert t_in == 0 and t_out == 0


# ── 6. Storage sync - all methods exist ───────────────────

def test_storage_has_all_sync_methods():
    from storage.storage_manager import StorageManager
    s = StorageManager(":memory:")
    methods = [
        'init_sync', 'save_project_sync', 'list_projects_sync',
        'create_chat_sync', 'list_chats_sync', 'rename_chat_sync',
        'delete_chat_sync', 'save_message_sync', 'get_chat_history_sync',
        'update_project_status_sync',
    ]
    for m in methods:
        assert hasattr(s, m), f"Missing method: {m}"


def test_storage_stage_category():
    from storage.storage_manager import stage_to_category
    cases = {
        'code_block_generation': 'code',
        'optimization': 'code',
        'unit_tests': 'tests',
        'project_critique': 'critique',
        'problem_analysis': 'critique',
        'global_spec_and_api': 'spec',
        'architecture_analysis': 'spec',
        'deployment_commands': 'other',
        'readme_generation': 'other',
    }
    for stage, expected in cases.items():
        result = stage_to_category(stage)
        assert result == expected, f"{stage}: expected {expected}, got {result}"


# ── 7. Parser - extracts files correctly ──────────────────

def test_parser_extract_files_valid():
    from parser.response_parser import ResponseParser
    parser = ResponseParser()
    data = {
        "files": [
            {"filename": "src/app.py", "content": "print('hello')", "description": "main"},
            {"filename": "tests/test_app.py", "content": "import app", "description": "tests"},
            {"filename": "README.md", "content": "# Title", "description": "docs"},
        ]
    }
    files = parser.extract_files_from_data(data)
    assert len(files) == 3
    assert files[0]['filename'] == 'src/app.py'
    assert files[1]['content'] == 'import app'


def test_parser_extract_files_skips_empty_content():
    from parser.response_parser import ResponseParser
    parser = ResponseParser()
    data = {"files": [
        {"filename": "app.py", "content": ""},     # empty - skip
        {"filename": "test.py", "content": "# ok"}, # valid
        {"filename": "", "content": "code"},         # no filename - skip
    ]}
    files = parser.extract_files_from_data(data)
    assert len(files) == 1
    assert files[0]['filename'] == 'test.py'


def test_parser_extract_code_blocks():
    from parser.response_parser import CodeBlockExtractor
    raw = "```python\nprint('hello')\n```\n\n```bash\necho world\n```"
    blocks = CodeBlockExtractor.extract_all_code_blocks(raw)
    assert len(blocks) == 2
    assert blocks[0] == ('python', "print('hello')")
    assert blocks[1] == ('bash', 'echo world')


def test_parser_json_from_markdown():
    from parser.response_parser import JSONExtractor
    raw = '```json\n{"proto": "GPT_PROTO_V1", "stage": "test"}\n```'
    result = JSONExtractor.extract(raw)
    assert result is not None
    assert result['proto'] == 'GPT_PROTO_V1'


def test_parser_json_from_text_with_preamble():
    from parser.response_parser import JSONExtractor
    raw = 'Here is my analysis:\n{"key": "value", "num": 42}\nDone.'
    result = JSONExtractor.extract(raw)
    assert result == {"key": "value", "num": 42}


# ── 8. File manager paths are absolute ────────────────────

def test_file_manager_absolute_paths():
    import tempfile
    from file_manager.project_file_manager import ProjectFileManager
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        abs_root = os.path.join(td, 'projects')
        mgr = ProjectFileManager(abs_root)
        d = mgr.create_project_dir('test_proj')
        assert d.is_absolute(), f"Expected absolute path, got: {d}"
        assert d.exists()


def test_file_manager_saves_to_correct_subdirs():
    import tempfile
    from file_manager.project_file_manager import ProjectFileManager
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        mgr = ProjectFileManager(os.path.join(td, 'projects'))
        mgr.create_project_dir('p1')
        p = mgr.save_stage_artifact('p1', 'code_block_generation', 'app.py', '# code')
        assert 'src' in str(p)
        p2 = mgr.save_stage_artifact('p1', 'unit_tests', 'test.py', '# test')
        assert 'tests' in str(p2)
        p3 = mgr.save_stage_artifact('p1', 'project_critique', 'report.json', '{}')
        assert 'critique' in str(p3)
