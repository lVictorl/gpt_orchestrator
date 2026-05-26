# 🤖 GPT-Orchestrator

> Десктопное приложение, которое превращает произвольный запрос пользователя в полностью реализованный программный продукт через оркестрацию цепочки промптов к ИИ.

---

## 🖥️ Скриншот

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🤖 GPT-Orchestrator              Проект  Настройки  Справка             │
├──────────────┬──────────────────────────────────────┬───────────────────┤
│ 💬 Чаты      │  [pipeline] ⚡ Анализ задачи         │  📝 Редактор      │
│              │                                      │                   │
│ 🔍 Поиск...  │  ┌──────────────────────────────┐   │  main.py  × app.py│
│              │  │ Разработай REST API для...   │   │                   │
│ > Чат 1      │  └──────────────────────────────┘   │  #!/usr/bin/env   │
│   Чат 2      │           ┌──────────────────────┐  │  python3          │
│   Чат 3      │           │ ✅ [problem_analysis] │  │                   │
│              │           │ {"core_problem": ...} │  │                   │
│  + Новый чат │           └──────────────────────┘  │  VIM OFF   💾  📋→│
├──────────────┴──────────────────────────────────────┴───────────────────┤
│ ✅ Этап завершён: architecture_analysis          [██████████] ~1240 токенов│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Возможности

| Функция | Описание |
|---|---|
| 🔍 **Анализатор задач** | Автоматически определяет тип задачи (код, курс, скрипт, отладка...) |
| 🔗 **Оркестратор промптов** | Управляет цепочкой из 14 этапов с передачей контекста |
| 🤖 **Двойной AI** | Поддержка OpenAI GPT-4o и Anthropic Claude через единый интерфейс |
| 🌊 **Стриминг** | Ответы ИИ отображаются токен за токеном |
| 💾 **История** | SQLite-хранилище всех чатов и проектов |
| 📝 **Vim-редактор** | Встроенный редактор кода с vim-режимом |
| 📊 **HTML-отчёты** | Автоматическая генерация отчётов Bootstrap 5 + highlight.js |
| 🔧 **AI-отладчик** | Автоматическая отправка ошибок в ИИ и применение исправлений |
| 📦 **MessagePack** | Компактный экспорт проектов |

---

## 🚀 Быстрый старт

### 1. Требования

- Python **3.11+**
- Ключ API: [Anthropic](https://console.anthropic.com) или [OpenAI](https://platform.openai.com)

### 2. Установка

```bash
git clone <repo>
cd gpt_orchestrator
chmod +x setup.sh
./setup.sh
```

### 3. Настройка API-ключа

**Вариант A** — через GUI (рекомендуется):
```
Запустить → Меню: Настройки → API-ключ → Ввести ключ
```

**Вариант B** — в `config.toml`:
```toml
[api]
provider = "anthropic"
anthropic_key = "sk-ant-..."
```

### 4. Запуск

```bash
source .venv/bin/activate
python main.py
```

---

## 🏗️ Архитектура

```
gpt_orchestrator/
├── main.py                    # Точка входа
├── pipeline.json              # Все 14 промптов системы
├── config.toml                # Конфигурация
│
├── core/                      # AppContext, EventBus, Config, Logger
├── gui/                       # PyQt6 интерфейс
│   ├── main_window.py         # Главное окно
│   ├── chat_widget.py         # Чат + MessageBubble
│   ├── history_panel.py       # Список чатов
│   ├── editor_widget.py       # Vim-редактор
│   └── dialogs/               # Диалоги настроек
│
├── orchestrator/              # PipelineOrchestrator
├── prompt_registry/           # PromptRegistry (pipeline.json)
├── ai_gateway/                # AIGateway (OpenAI + Anthropic)
├── parser/                    # ResponseParser (JSON + code blocks)
├── storage/                   # StorageManager (SQLite)
├── strategy/                  # TaskAnalyzer + стратегии
├── file_manager/              # ProjectFileManager + ReportGenerator
├── debugger/                  # AIDebugger
└── tests/                     # pytest тесты
```

### Поток данных

```
User Input
    ↓
TaskAnalyzer → выбирает стратегию (CodeStrategy / DebugStrategy / ...)
    ↓
PipelineOrchestrator → итерирует по этапам стратегии
    ↓
PromptRegistry.fill() → подставляет FULL_CONTEXT в промпт
    ↓
AIGateway.send_message() → стриминг токенов → UI
    ↓
ResponseParser.parse_json() → извлекает данные
    ↓
ContextAccumulator.add() → накапливает FULL_CONTEXT
    ↓
StorageManager.save_message() → персистентность
    ↓
EventBus → GUI обновление
```

---

## 📋 Этапы пайплайна (14 промптов)

| # | Stage | Описание |
|---|---|---|
| 1 | `problem_analysis` | Анализ задачи, цели, ограничения |
| 2 | `user_clarification` | Уточняющие вопросы к пользователю |
| 3.1 | `architecture_analysis` | Выбор архитектуры и стека |
| 3.2 | `project_plan` | Разбивка на подпроекты |
| 3.3 | `global_spec_and_api` | Проектирование публичного API |
| 3.4 | `subproject_prompts_generation` | Детальные промпты для каждого подпроекта |
| 4 | `subproject_implementation_trigger` | Запуск цикла генерации файлов |
| 5 | `code_block_generation` | Генерация кода (один файл за запрос) |
| 6 | `optimization` | Оптимизация кода |
| 7 | `unit_tests` | Модульные тесты |
| 8 | `refactoring` | Рефакторинг |
| 9 | `deployment_commands` | setup.sh / Makefile |
| 10 | `debugging_cli` | AI-отладка ошибок |
| 11 | `readme_generation` | Генерация README.md |

---

## ⚙️ Конфигурация

```toml
[api]
provider = "anthropic"              # anthropic | openai
anthropic_key = "sk-ant-..."
openai_key = "sk-..."
model_anthropic = "claude-sonnet-4-20250514"
model_openai = "gpt-4o"
max_tokens = 8192
temperature = 0.3
request_timeout = 120
rpm = 20

[app]
projects_dir = "projects"
log_level = "INFO"
vim_mode = true
font_size = 13
```

---

## 🧪 Тесты

```bash
# Все тесты
pytest tests/ -v

# Только backend (без GUI)
pytest tests/test_parser.py tests/test_storage.py tests/test_strategy.py tests/test_prompt_registry.py -v
```

---

## 📦 Упаковка (дистрибуция)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name gpt-orchestrator main.py
# Бинарник: dist/gpt-orchestrator
```

---

## 📄 Лицензия

MIT License — используйте свободно.

---

*GPT-Orchestrator v1.0.0 · Python 3.11+ · PyQt6 · OpenAI/Anthropic*
