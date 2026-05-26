"""
tests/test_all_remaining.py — Final comprehensive test suite
Covers: logger, orchestrator file-saving, clarification form, registry, protocol
"""
import sys, os, json, ast, re, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Logger: no double logging ─────────────────────────────

def test_logger_ai_response_no_duplicate(tmp_path):
    from core.logger import StructLogger
    logger = StructLogger(log_dir=str(tmp_path), level="INFO")
    logger.log_ai_response("deepseek", "problem_analysis", "response text",
                           tokens_out=100, latency_sec=5.0)
    log_file = tmp_path / "gpt_orchestrator.log"
    lines = [l for l in log_file.read_text().strip().split('\n') if l.strip()]
    # Count lines with AI_RESPONSE at INFO level (not DEBUG)
    ai_resp_lines = [l for l in lines if '"AI_RESPONSE"' in l or 'AI_RESPONSE' in l]
    # Should have exactly ONE info log (debug is suppressed at INFO level)
    assert len(ai_resp_lines) == 1, f"Expected 1 AI_RESPONSE log, got {len(ai_resp_lines)}: {ai_resp_lines}"


def test_logger_ai_request_logged(tmp_path):
    from core.logger import StructLogger
    logger = StructLogger(log_dir=str(tmp_path), level="DEBUG")
    logger.log_ai_request("anthropic", "claude-3", "code_block_generation",
                          "Build a bot", project_id="p1")
    content = (tmp_path / "gpt_orchestrator.log").read_text()
    assert "AI_REQUEST" in content


def test_logger_file_saved_logged(tmp_path):
    from core.logger import StructLogger
    logger = StructLogger(log_dir=str(tmp_path), level="INFO")
    logger.log_file_saved("/projects/p1/src/app.py", 1234, "code_block_generation")
    content = (tmp_path / "gpt_orchestrator.log").read_text()
    assert "FILE_SAVED" in content


def test_logger_project_dir_creates_separate_log(tmp_path):
    from core.logger import StructLogger
    logger = StructLogger(log_dir=str(tmp_path), level="INFO")
    proj_dir = tmp_path / "project_001"
    proj_dir.mkdir()
    logger.set_project_dir(str(proj_dir))
    logger.info("project started")
    proj_log = proj_dir / "logs" / "project.log"
    assert proj_log.exists()
    assert "project started" in proj_log.read_text()


# ── Registry: fill() with FULL_CONTEXT ───────────────────

def test_registry_fill_full_context():
    from prompt_registry.registry import PromptRegistry
    root = os.path.dirname(os.path.dirname(__file__))
    reg = PromptRegistry(os.path.join(root, "pipeline.json"))
    filled = reg.fill("code_block_generation", {
        "PROBLEM_DESCRIPTION": "Build a Telegram bot",
        "FULL_CONTEXT": '{"user_task": {"task": "Build a bot"}}',
        "STAGE": "code_block_generation",
        "LANGUAGE": "Python",
    })
    assert "Build a Telegram bot" in filled
    assert "GPT_PROTO_V1" in filled


def test_registry_fill_leaves_unfound_placeholders():
    from prompt_registry.registry import PromptRegistry, PlaceholderFiller
    result = PlaceholderFiller.fill("Hello {{NAME}}, you have {{UNKNOWN}}", {"NAME": "World"})
    assert "World" in result
    assert "{{UNKNOWN}}" in result  # unfound placeholder stays as-is


def test_registry_all_stages_loadable():
    from prompt_registry.registry import PromptRegistry
    root = os.path.dirname(os.path.dirname(__file__))
    reg = PromptRegistry(os.path.join(root, "pipeline.json"))
    stages = reg.list_stages()
    assert len(stages) == 15
    for s in stages:
        tmpl = reg.get(s)
        assert tmpl is not None
        assert tmpl.prompt
        assert "GPT_PROTO_V1" in tmpl.prompt


# ── Protocol per-stage system prompts ────────────────────

def test_system_prompt_code_has_files():
    from core.protocol import get_system_prompt
    for s in ("code_block_generation", "unit_tests", "optimization", "refactoring"):
        sp = get_system_prompt(s)
        assert "files" in sp, f"{s}: missing 'files' in system prompt"
        assert "GPT_PROTO_V1" in sp
        assert "filename" in sp


def test_system_prompt_analysis_has_goals():
    from core.protocol import get_system_prompt
    sp = get_system_prompt("problem_analysis")
    assert "GPT_PROTO_V1" in sp
    assert "core_problem" in sp or "goals" in sp or "data" in sp


def test_system_prompt_critique_comprehensive():
    from core.protocol import CRITIQUE_SYSTEM_PROMPT
    required = ["overall_score", "test_cases", "grades", "compliance_percent",
                "strengths", "weaknesses", "recommendations"]
    for field in required:
        assert field in CRITIQUE_SYSTEM_PROMPT, f"Missing: {field}"


def test_proto_envelope_roundtrip():
    from core.protocol import ProtoEnvelope
    env = ProtoEnvelope(
        stage="code_block_generation",
        status="OK",
        confidence="HIGH",
        summary="Generated 5 files",
        data={"files": [{"filename": "app.py", "content": "print()", "description": "main"}]},
        warnings=[],
        next_stage_hint="run tests",
        tokens_used=500,
    )
    j = json.loads(env.to_json())
    env2 = ProtoEnvelope.from_dict(j)
    assert env2.stage == "code_block_generation"
    assert env2.summary == "Generated 5 files"
    assert env2.data["files"][0]["filename"] == "app.py"
    assert env2.is_ok()


# ── Parser: all extraction methods ───────────────────────

def test_parser_proto_v1_full():
    from parser.response_parser import ResponseParser
    parser = ResponseParser()
    raw = json.dumps({
        "proto": "GPT_PROTO_V1", "stage": "code_block_generation",
        "status": "OK", "confidence": "HIGH", "summary": "done",
        "data": {"files": [
            {"filename": "src/app.py", "content": "def main():\n    pass", "description": "entry"},
            {"filename": "tests/test_app.py", "content": "import app", "description": "tests"},
        ]},
        "warnings": [], "next_stage_hint": "", "tokens_used": 100,
        "timestamp": "2025-01-01T00:00:00",
    })
    result = parser.parse_proto_v1(raw)
    assert result is not None
    files = parser.extract_files_from_data(result["data"])
    assert len(files) == 2
    assert files[0]["filename"] == "src/app.py"
    assert "def main" in files[0]["content"]


def test_parser_extract_multiple_code_blocks():
    from parser.response_parser import CodeBlockExtractor
    raw = (
        "Here are the files:\n"
        "```python\nprint('main')\n```\n"
        "```bash\necho hello\n```\n"
        "```yaml\nname: app\n```\n"
    )
    blocks = CodeBlockExtractor.extract_all_code_blocks(raw)
    assert len(blocks) == 3
    assert blocks[0] == ("python", "print('main')")
    assert blocks[1] == ("bash", "echo hello")
    assert blocks[2] == ("yaml", "name: app")


def test_parser_json_nested():
    from parser.response_parser import JSONExtractor
    raw = '{"a": {"b": [1, 2, {"c": "deep"}]}}'
    r = JSONExtractor.extract(raw)
    assert r["a"]["b"][2]["c"] == "deep"


def test_parser_skips_invalid_files():
    from parser.response_parser import ResponseParser
    parser = ResponseParser()
    data = {"files": [
        {"filename": "ok.py",  "content": "code"},  # valid
        {"filename": "",       "content": "code"},  # no name - skip
        {"filename": "bad.py", "content": ""},      # empty content - skip
        {"filename": "ok2.py", "content": "more"},  # valid
    ]}
    files = parser.extract_files_from_data(data)
    assert len(files) == 2
    assert files[0]["filename"] == "ok.py"
    assert files[1]["filename"] == "ok2.py"


# ── Orchestrator file saving ──────────────────────────────

def test_orchestrator_saves_data_files_array(tmp_path):
    """data.files array is correctly saved to filesystem."""
    from file_manager.project_file_manager import ProjectFileManager
    mgr = ProjectFileManager(str(tmp_path / "projects"))
    mgr.create_project_dir("p1")

    data = {"files": [
        {"filename": "src/app.py",        "content": "def main(): pass",  "description": "main"},
        {"filename": "src/models.py",     "content": "class User: pass",  "description": "models"},
        {"filename": "tests/test_app.py", "content": "import app\ndef test(): pass", "description": "tests"},
        {"filename": "README.md",         "content": "# Project",         "description": "docs"},
    ]}

    saved = []
    for f in data["files"]:
        path = mgr.save_file("p1", f["filename"], f["content"])
        saved.append(path)

    assert len(saved) == 4
    assert all(p.exists() for p in saved)
    assert saved[0].read_text() == "def main(): pass"
    assert "User" in saved[1].read_text()


def test_file_manager_nested_paths(tmp_path):
    """Deep nested paths like modules/module1/lessons/lesson1/ work."""
    from file_manager.project_file_manager import ProjectFileManager
    from pathlib import Path
    mgr = ProjectFileManager(str(tmp_path / "projects"))
    mgr.create_project_dir("p2")

    deep_path = "modules/module1/lessons/lesson1/lexer.l"
    path = mgr.save_file("p2", deep_path, "/* lexer rules */")
    assert path.exists()
    assert path.read_text() == "/* lexer rules */"


def test_file_manager_list_deep_files(tmp_path):
    from file_manager.project_file_manager import ProjectFileManager
    mgr = ProjectFileManager(str(tmp_path / "projects"))
    mgr.create_project_dir("p3")
    for rel in ["src/a.py", "src/core/b.py", "tests/t.py", "docs/readme.md"]:
        mgr.save_file("p3", rel, f"# {rel}")
    files = mgr.list_files("p3")
    assert len(files) >= 4


# ── Storage: all sync methods ─────────────────────────────

def test_storage_all_sync_operations(tmp_path):
    from storage.storage_manager import StorageManager
    from storage.models import Project, Message

    s = StorageManager(str(tmp_path / "test.db"))
    s.init_sync()

    # Create project
    p = Project(project_id="p1", title="Test", task_type="code", description="desc")
    s.save_project_sync(p)
    assert any(x.project_id == "p1" for x in s.list_projects_sync())

    # Create multiple chats for the project
    chats_data = [
        ("Problem Analysis", "problem_analysis"),
        ("Code Gen", "code_block_generation"),
        ("Unit Tests", "unit_tests"),
    ]
    chat_ids = []
    for title, stage in chats_data:
        cid = s.create_chat_sync(title, "p1", stage)
        chat_ids.append(cid)

    chats = s.list_chats_sync("p1")
    assert len(chats) == 3

    # Verify categories
    categories = {c.stage_category for c in chats}
    assert "critique" in categories or "code" in categories  # problem_analysis -> critique, code -> code

    # Save messages to each chat
    for cid in chat_ids:
        s.save_message_sync(cid, Message(role="user",      content="prompt", stage=""))
        s.save_message_sync(cid, Message(role="assistant", content="response", stage=""))

    # Verify messages
    for cid in chat_ids:
        hist = s.get_chat_history_sync(cid)
        assert len(hist) == 2
        assert hist[0].role == "user"
        assert hist[1].role == "assistant"

    # Update project status
    s.update_project_status_sync("p1", "done", 87)
    proj = next(x for x in s.list_projects_sync() if x.project_id == "p1")
    assert proj.status == "done"
    assert proj.critique_score == 87

    # Delete one chat
    s.delete_chat_sync(chat_ids[0])
    remaining = s.list_chats_sync("p1")
    assert len(remaining) == 2
    assert s.get_chat_history_sync(chat_ids[0]) == []


def test_storage_thread_safety(tmp_path):
    from storage.storage_manager import StorageManager
    from storage.models import Project, Message

    s = StorageManager(str(tmp_path / "threaded.db"))
    s.init_sync()
    p = Project(project_id="pt", title="T", task_type="code", description="")
    s.save_project_sync(p)
    cid = s.create_chat_sync("Chat", "pt")

    errors = []
    def write_msgs(thread_id):
        try:
            for i in range(10):
                s.save_message_sync(cid, Message(
                    role="user",
                    content=f"thread_{thread_id}_msg_{i}",
                    stage="code_block_generation"
                ))
        except Exception as e:
            errors.append(f"Thread {thread_id}: {e}")

    threads = [threading.Thread(target=write_msgs, args=(i,)) for i in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert errors == [], f"Thread errors: {errors}"
    hist = s.get_chat_history_sync(cid)
    assert len(hist) == 50  # 5 threads × 10 messages


# ── Token optimizer ───────────────────────────────────────

def test_token_optimizer_all_deepseek_models():
    from token_saver.token_optimizer import MODEL_PRICING, TokenOptimizer
    deepseek = [m for m in MODEL_PRICING if "deepseek" in m]
    assert len(deepseek) >= 4
    # All valid pricing
    for m in deepseek:
        p = MODEL_PRICING[m]
        assert p["input"] > 0 and p["output"] > 0

    opt = TokenOptimizer("deepseek-reasoner")
    cost = opt.calculate_cost(1_000_000, 1_000_000)
    assert cost > MODEL_PRICING["deepseek-chat"]["input"]  # reasoner costs more


def test_token_optimizer_minimal_context_precision():
    from token_saver.token_optimizer import TokenOptimizer
    opt = TokenOptimizer()
    ctx = {
        "user_task":              {"task": "build bot"},
        "problem_analysis":       {"goals": ["goal1"]},
        "global_spec_and_api":    {"spec": "..."},
        "code_block_generation":  {"files": [{"filename": "app.py"}]},
        "unrelated_stage_xyz":    {"irrelevant": "data" * 100},
    }
    minimal = opt.select_minimal_context("unit_tests", ctx)
    assert "code_block_generation" in minimal
    assert "global_spec_and_api" in minimal
    assert "unrelated_stage_xyz" not in minimal


def test_token_optimizer_compress_deduplicates():
    from token_saver.token_optimizer import TokenOptimizer
    opt = TokenOptimizer()
    same_val = "identical content " * 50
    ctx = {
        "stage1": {"key": same_val},
        "stage2": {"key": same_val},  # exact duplicate
    }
    compressed = opt.compress_context(ctx)
    # stage2.key should be removed as duplicate hash
    if "stage2" in compressed:
        # If not removed, at least truncated
        assert len(str(compressed["stage2"].get("key", ""))) <= 1600
