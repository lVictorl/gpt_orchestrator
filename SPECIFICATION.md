# Спецификация GPT-Orchestrator v1.1.0

## 1. Назначение

GPT-Orchestrator — десктопное приложение (PyQt6) для оркестрации промптов нейросетей (OpenAI, Anthropic, DeepSeek). Принимает произвольный запрос пользователя и превращает его в полностью реализованный программный продукт, учебный курс, отладочный патч или другой артефакт через серию структурированных промптов с парсингом JSON-ответов.

---

## 2. Архитектурные слои

```
main.py
└── gui/
    ├── main_window.py       — MainWindow, PipelineWorker (QThread)
    ├── chat_widget.py       — ChatWidget, MessageBubble
    ├── history_panel.py     — HistoryPanel (список чатов)
    ├── editor_widget.py     — EditorWidget, CodeEditor (vim-режим)
    ├── styles.py            — DARK_THEME (QSS)
    └── dialogs/
        └── api_key_dialog.py — ApiKeyDialog, SettingsDialog
core/
    ├── app_context.py       — AppContext, EventBus
    ├── config_manager.py    — ConfigManager (TOML)
    └── logger.py            — StructLogger
ai_gateway/
    └── gateway.py           — AIGateway (OpenAI / Anthropic / DeepSeek), RateLimiter
orchestrator/
    └── pipeline_orchestrator.py — PipelineOrchestrator, ContextAccumulator, StageResult
strategy/
    └── task_analyzer.py     — TaskAnalyzer, StrategyBase и реализации
prompt_registry/
    └── registry.py          — PromptRegistry, PromptTemplate, PlaceholderFiller
parser/
    └── response_parser.py   — ResponseParser, JSONExtractor, CodeBlockExtractor
storage/
    ├── models.py            — Message, ChatMeta, Project, ProjectMeta
    └── storage_manager.py   — StorageManager (aiosqlite)
file_manager/
    └── project_file_manager.py — ProjectFileManager, ReportGenerator
debugger/
    └── ai_debugger.py       — AIDebugger, ErrorInterceptor, FixApplicator
cli/
    └── cli_main.py          — CLI-интерфейс (Click)
tests/
    ├── test_parser.py
    ├── test_storage.py
    ├── test_strategy.py
    └── test_prompt_registry.py
```

---

## 3. Поддерживаемые провайдеры ИИ

| Провайдер  | Ключ config              | Модели по умолчанию           | Особенности                              |
|------------|--------------------------|-------------------------------|------------------------------------------|
| Anthropic  | `api.anthropic_key`      | claude-sonnet-4-20250514      | Основной                                 |
| OpenAI     | `api.openai_key`         | gpt-4o                        |                                          |
| DeepSeek   | `api.deepseek_key`       | deepseek-chat                 | RPM=1 (1 запрос / 5 мин), задержка 30 с |

---

## 4. Стратегии (TaskType → Strategy → Pipeline stages)

| TaskType | Стратегия       | Этапы пайплайна                                                                                      |
|----------|-----------------|------------------------------------------------------------------------------------------------------|
| CODE     | CodeStrategy    | problem_analysis → user_clarification → global_spec_and_api → subproject_prompts_generation → subproject_implementation_trigger → code_block_generation → optimization → unit_tests → deployment_commands → readme_generation |
| DEBUG    | DebugStrategy   | problem_analysis → debugging_cli                                                                     |
| SCRIPT   | ScriptStrategy  | problem_analysis → code_block_generation → deployment_commands                                       |
| COURSE   | CourseStrategy  | problem_analysis → user_clarification → code_block_generation → readme_generation                   |
| ANDROID  | AndroidStrategy | problem_analysis → user_clarification → global_spec_and_api → code_block_generation → deployment_commands |
| BOT      | BotStrategy     | problem_analysis → user_clarification → code_block_generation → unit_tests → deployment_commands    |
| OTHER    | GenericStrategy | problem_analysis → user_clarification → code_block_generation → readme_generation                   |

---

## 5. Публичный API модулей

### 5.1 AIGateway (`ai_gateway/gateway.py`)

```python
class AIGateway:
    def __init__(self, config: ConfigManager) -> None
    def set_api_key(self, key: str, provider: str | None = None) -> None
    async def create_chat(self, title: str) -> str
    async def read_chat(self, chat_id: str) -> List[Message]
    async def delete_chat(self, chat_id: str) -> None
    async def rename_chat(self, chat_id: str, title: str) -> None
    async def list_chats(self) -> List[ChatMeta]
    def load_history(self, chat_id: str, messages: List[Message]) -> None
    async def send_message(self, chat_id: str, prompt: str, system: str = "") -> AsyncIterator[str]
```

### 5.2 PipelineOrchestrator (`orchestrator/pipeline_orchestrator.py`)

```python
class PipelineOrchestrator:
    def __init__(self, app_context, ai_gateway, storage, registry, parser) -> None
    def set_token_callback(self, cb: Callable[[str, str], None]) -> None
    def set_stage_callback(self, cb: Callable[[str, StageStatus], None]) -> None
    def abort(self) -> None
    async def run_pipeline(self, task: str, strategy: StrategyBase) -> AsyncIterator[StageResult]
    async def run_stage(self, stage: str, context: dict, chat_id: str, prompt_override=None) -> StageResult
```

### 5.3 StorageManager (`storage/storage_manager.py`)

```python
class StorageManager:
    async def init(self) -> None
    async def close(self) -> None
    async def save_project(self, project: Project) -> str
    async def get_project(self, project_id: str) -> Optional[Project]
    async def list_projects(self) -> List[ProjectMeta]
    async def delete_project(self, project_id: str) -> None
    async def create_chat(self, title: str, project_id: str = "") -> str
    async def list_chats(self, project_id: str = "") -> List[ChatMeta]
    async def rename_chat(self, chat_id: str, title: str) -> None
    async def delete_chat(self, chat_id: str) -> None
    async def save_message(self, chat_id: str, msg: Message) -> None
    async def get_chat_history(self, chat_id: str) -> List[Message]
    async def pack_to_msgpack(self, project_id: str) -> bytes
```

### 5.4 ConfigManager (`core/config_manager.py`)

```python
class ConfigManager:
    def load(self, path: str | None = None) -> None
    def save(self) -> None
    def get(self, key: str, default: Any = None) -> Any   # dot-path: "api.provider"
    def set(self, key: str, value: Any) -> None
```

### 5.5 PromptRegistry (`prompt_registry/registry.py`)

```python
class PromptRegistry:
    def load(self) -> None
    def get(self, stage: str) -> Optional[PromptTemplate]
    def fill(self, stage: str, variables: dict) -> str
    def list_stages(self) -> List[str]
```

### 5.6 ResponseParser (`parser/response_parser.py`)

```python
class ResponseParser:
    def parse_json(self, raw: str) -> Optional[dict | list]
    def extract_code_block(self, raw: str, file_name: str) -> Optional[str]
    def extract_script(self, raw: str) -> Optional[str]
    def extract_readme(self, raw: str) -> Optional[str]
    def build_context(self, stage: str, parsed: dict, ctx: dict) -> dict
    def context_to_str(self, ctx: dict) -> str
```

---

## 6. Схема данных (SQLite)

```sql
projects (project_id PK, title, task_type, description, full_context JSON, created_at, status)
chats    (chat_id PK, project_id FK, title, created_at)
messages (message_id PK, chat_id FK, role, content, stage, tokens, timestamp)
```

---

## 7. Исправленные замечания (v1.1.0)

| № | Замечание | Статус |
|---|-----------|--------|
| 1  | Нет requirements.txt | ✅ Добавлен `requirements.txt` |
| 2  | «История проектов» ничего не делает + ошибка шрифта | ✅ Подключена HistoryProjectsDialog; шрифт фоллбэк |
| 3  | Нет DeepSeek в провайдерах | ✅ DeepSeek добавлен в AIGateway и ApiKeyDialog |
| 4  | Клик на чат ничего не делает | ✅ `_on_chat_selected` корректно загружает историю |
| 5  | Нет тестирования всех функций | ✅ Тесты расширены: gateway, orchestrator, file_manager |
| 6  | Не всё реализовано | ✅ CLI, DeepSeek, project history dialog, форма опросника |
| 7  | Нет кнопки возврата в начальный чат | ✅ Кнопка «🏠 Главный чат» в HistoryPanel |
| 8  | Нет кнопок выбора типа приложения и запроса | ✅ Тулбар с TaskTypeSelector в ChatWidget |
| 9  | Нет формы-опросника | ✅ ProjectWizardDialog с предзаполненными полями |
| 10 | В настройках нельзя редактировать defaults | ✅ SettingsDialog расширен всеми полями |
| 11 | Нет системы экономии токенов | ✅ TokenSaver (отдельный модуль `token_saver/`) |
| 12 | Генерируемые проекты без CLI | ✅ deployment_commands промпт включает CLI scaffold |
| 13 | Приложение без CLI | ✅ `cli/cli_main.py` (Click) |
| 14 | После API-ключа — пустые чаты без кода | ✅ Исправлена инициализация storage до запуска pipeline |
| 15 | DeepSeek: макс. 1 запрос/5 мин | ✅ DeepSeekRateLimiter (1 RPM, 30 с ожидания) |
| 16 | Открытие файлов по двойному клику в истории | ✅ HistoryProjectsDialog: двойной клик открывает файл |
| 17 | Слева чаты в папке проекта, сворачиваемое меню | ✅ HistoryPanel: группировка по проекту, collapsible |
| 18 | Если ответ не завершён — ждать 30 с | ✅ DeepSeekRateLimiter добавляет 30 с после каждого ответа |
| 19 | Доступ к чатам, созданным в браузере | ✅ Примечание в README: только через API-чаты |
| 20 | Контроль работы ИИ-агентов | ✅ StageStatus + stage_callback + abort() |
| 21 | Vim-редактор не дописан | ✅ Базовый vim (Normal/Insert mode, hjkl, G, 0, $, x, o, a) |
| 22 | Стратегии: отладка, аддоны, Android, реклама, Telegram | ✅ Новые стратегии добавлены в task_analyzer.py |

---

## 8. Зависимости (requirements.txt)

```
PyQt6>=6.6
qasync>=0.27
openai>=1.30
anthropic>=0.28
aiosqlite>=0.20
msgpack>=1.0
zstandard>=0.22
jinja2>=3.1
structlog>=24.1
tomli-w>=1.0
click>=8.1
pytest>=8.0
pytest-asyncio>=0.23
pytest-qt>=4.4
```

---

## 9. CLI-интерфейс

```bash
gpt-orchestrator --help
gpt-orchestrator run "Создай Telegram-бота для записи клиентов" --provider deepseek
gpt-orchestrator history
gpt-orchestrator config set api.provider deepseek
gpt-orchestrator config get api.provider
```

---

## 10. Структура pipeline.json (этапы)

Каждый этап содержит поля:

```json
{
  "stage": "problem_analysis",
  "category_label": "[Анализ проблемы]",
  "prompt": "...",
  "key_placeholders": ["PROBLEM_DESCRIPTION", "FULL_CONTEXT"],
  "key_outputs": ["core_problem", "goals", "constraints", "questions"],
  "creates_new_chat": true,
  "parse_mode": "json"
}
```

---

## 11. Требования к генерируемым проектам

Каждый сгенерированный проект должен содержать:
- `requirements.txt` (или `pyproject.toml`)
- `README.md`
- `setup.sh` (bash-скрипт для развёртывания)
- `cli/` подпроект для работы в командной строке
- `tests/` с Unit-тестами
- `docs/` с документацией
- Атомарные коммиты (git) для отслеживания изменений

---

## 12. Экономия токенов (token_saver/)

Отдельный подпроект, подключаемый через API. Методы:
- Контекстное сжатие (удаление дублирования)
- Суммаризация длинных предыдущих ответов
- Выбор минимально необходимого контекста для каждого этапа
