# GPT-Orchestrator — Руководство по разработке аддонов

## Обзор архитектуры

```
gpt_orchestrator/
├── strategy/          ← Стратегии (определяют этапы пайплайна)
├── orchestrator/      ← Оркестратор (выполняет этапы)
├── prompt_registry/   ← Реестр промптов
├── gui/               ← Интерфейс
├── local_model/       ← Локальная модель для анализа
├── runner/            ← Запуск и профилирование проектов
└── addons/            ← Директория для ваших аддонов ←
```

---

## Типы аддонов

| Тип | Что делает | Точка интеграции |
|-----|-----------|-----------------|
| **Strategy** | Новый тип задачи (тип проекта) | `strategy/task_analyzer.py` |
| **Stage** | Новый этап пайплайна | `pipeline.json` + `orchestrator` |
| **Backend** | Новый провайдер ИИ | `ai_gateway/gateway.py` |
| **Analyzer** | Расширение LocalAnalyzer | `local_model/local_analyzer.py` |
| **GUI Panel** | Новая вкладка в интерфейсе | `gui/main_window.py` |
| **Runner** | Поддержка нового языка/фреймворка | `runner/project_runner.py` |

---

## 1. Аддон-стратегия (новый тип проекта)

### Шаг 1: Создать файл аддона

```python
# addons/my_strategy_addon.py
"""Аддон: генерация WordPress-плагинов."""
from strategy.task_analyzer import StrategyBase, TaskType

class WordPressPluginStrategy(StrategyBase):
    def get_pipeline_stages(self):
        return [
            "problem_analysis",
            "user_clarification",
            "global_spec_and_api",
            "code_block_generation",
            "unit_tests",
            "deployment_commands",
            "readme_generation",
            "project_critique",
        ]

    def get_prompt_overrides(self):
        return {
            "problem_analysis": (
                "Ты — WordPress-разработчик. Проанализируй запрос "
                "на создание WordPress-плагина. Верни GPT_PROTO_V1 JSON с полями: "
                "plugin_name, description, hooks_used, shortcodes, settings_page."
            ),
        }

    def get_task_type(self):
        return TaskType.OTHER  # или добавьте новый TaskType
```

### Шаг 2: Зарегистрировать в `task_analyzer.py`

```python
# В strategy/task_analyzer.py — добавить в _KEYWORDS:
TaskType.WORDPRESS: ["wordpress", "плагин для вп", "wp plugin", "wp-plugin"],

# Добавить в select_strategy():
TaskType.WORDPRESS: WordPressPluginStrategy,
```

### Шаг 3: Автозагрузка через addon_loader

```python
# В main.py или _init_storage_and_ui():
from core.addon_loader import AddonLoader
AddonLoader.load_all()  # загружает все аддоны из addons/
```

---

## 2. Аддон-этап (новый шаг пайплайна)

### Добавить в pipeline.json:

```json
{
  "stage": "security_audit",
  "category_label": "[Аудит безопасности]",
  "prompt": "Проведи аудит безопасности сгенерированного кода.\n\nКОД: {{FULL_CONTEXT}}\n\nОтвечай СТРОГО в формате GPT_PROTO_V1.\n\nПоле data:\n- vulnerabilities: [{type, severity, file, line, description, fix}]\n- owasp_checks: [{item, status, notes}]\n- security_score: 0-100\n- recommendations: []",
  "key_placeholders": ["FULL_CONTEXT"],
  "key_outputs": ["vulnerabilities", "security_score"],
  "creates_new_chat": true,
  "parse_mode": "json"
}
```

### Добавить в стратегию:

```python
class SecureCodeStrategy(CodeStrategy):
    def get_pipeline_stages(self):
        stages = super().get_pipeline_stages()
        # Вставить после unit_tests
        idx = stages.index("unit_tests")
        stages.insert(idx + 1, "security_audit")
        return stages
```

---

## 3. Аддон-провайдер ИИ

```python
# addons/groq_backend.py
"""Аддон: Groq API (llama3 с очень быстрым инференсом)."""
from ai_gateway.gateway import AIGateway, RateLimiter

class GroqProvider:
    """Groq совместим с OpenAI API."""
    
    BASE_URL = "https://api.groq.com/openai/v1"
    
    @staticmethod
    def create_client(api_key: str):
        import openai
        return openai.AsyncOpenAI(api_key=api_key, base_url=GroqProvider.BASE_URL)
    
    @staticmethod
    def default_model() -> str:
        return "llama-3.3-70b-versatile"  # или "mixtral-8x7b-32768"


# Регистрация в config.example.toml:
# [api]
# provider = "groq"
# groq_key = "gsk_..."
# model_groq = "llama-3.3-70b-versatile"
```

Добавить в `AIGateway._init_client()`:

```python
elif provider == "groq":
    from addons.groq_backend import GroqProvider
    key = self._config.get("api.groq_key", "")
    self._client = GroqProvider.create_client(key) if key else None
    self._rate_limiter = RateLimiter(self._config.get("api.rpm", 30))
```

---

## 4. Аддон для LocalAnalyzer

```python
# addons/custom_analyzer.py
"""Аддон: кастомный анализатор промптов."""
from local_model.local_analyzer import LocalAnalyzer, AnalysisResult, RuleBasedAnalyzer
import re, time

class DomainSpecificAnalyzer:
    """Анализатор с правилами для конкретной предметной области."""
    
    DOMAIN_RULES = {
        "fintech": [
            (r"\bплатёж\b", "payment transaction"),
            (r"\bкошелёк\b", "digital wallet"),
        ],
        "medtech": [
            (r"\bпациент\b", "patient record"),
            (r"\bдиагноз\b", "medical diagnosis"),
        ],
    }
    
    def __init__(self, domain: str = "general"):
        self._domain = domain
        self._rule = RuleBasedAnalyzer()
    
    def analyze(self, prompt: str, stage: str = "") -> AnalysisResult:
        result = self._rule.analyze(prompt, stage)
        rules = self.DOMAIN_RULES.get(self._domain, [])
        for pat, rep in rules:
            corrected = re.sub(pat, rep, result.corrected_prompt, flags=re.IGNORECASE)
            if corrected != result.corrected_prompt:
                result.corrected_prompt = corrected
                result.improvements.append(f"Domain term [{self._domain}]: {rep}")
        return result


# Использование:
# analyzer = LocalAnalyzer()
# analyzer._active = DomainSpecificAnalyzer(domain="fintech")
```

---

## 5. GUI-аддон (новая вкладка)

```python
# addons/analytics_tab.py
"""Аддон: вкладка аналитики проектов."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal

class AnalyticsTab(QWidget):
    """Отображает статистику по всем проектам."""
    
    def __init__(self, storage, parent=None):
        super().__init__(parent)
        self._storage = storage
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("📊 Аналитика проектов"))
        # ... ваш UI код ...
    
    def refresh(self):
        projects = self._storage.list_projects_sync()
        # ... обновить виджеты ...


# Подключение в main_window.py:
# from addons.analytics_tab import AnalyticsTab
# analytics = AnalyticsTab(self._storage)
# self._tabs.addTab(analytics, "📊 Аналитика")
```

---

## 6. Runner-аддон (поддержка нового языка)

```python
# addons/rust_runner.py
"""Аддон: запуск и тестирование Rust-проектов."""
from runner.project_runner import ProjectRunner, TestResult, RunResult
import time

class RustRunner:
    """Расширение ProjectRunner для Rust (cargo)."""
    
    def __init__(self, project_dir: str, logger=None):
        self._dir = __import__("pathlib").Path(project_dir)
        self._base = ProjectRunner(project_dir, logger)
    
    def run_tests(self) -> TestResult:
        result = TestResult(framework="cargo_test")
        t0 = time.monotonic()
        r = self._base._cmd(["cargo", "test", "--", "--test-threads=4"], timeout=120)
        result.duration_sec = time.monotonic() - t0
        result.output = (r.stdout + r.stderr)[-2000:]
        result.success = r.success
        import re
        result.passed = len(re.findall(r"test .+ \.\.\. ok", r.stdout))
        result.failed = len(re.findall(r"test .+ FAILED", r.stdout))
        result.total = result.passed + result.failed
        return result
    
    def build_release(self) -> RunResult:
        return self._base._cmd(["cargo", "build", "--release"], timeout=300)
```

---

## 7. Структура аддона (стандарт)

```
addons/
├── __init__.py
├── my_addon/
│   ├── __init__.py          ← экспортирует register()
│   ├── strategy.py          ← стратегия (опционально)
│   ├── stages.py            ← новые этапы (опционально)
│   ├── ui.py                ← UI компоненты (опционально)
│   └── README.md            ← документация аддона
```

### Стандартный интерфейс аддона (`__init__.py`):

```python
"""
my_addon — Описание аддона.
Версия: 1.0.0
Автор: Ваше имя
"""
from .strategy import MyStrategy

ADDON_META = {
    "name":        "My Addon",
    "version":     "1.0.0",
    "author":      "Your Name",
    "description": "Что делает аддон",
    "requires":    ["gpt_orchestrator>=1.8"],
}

def register(app_context) -> dict:
    """
    Вызывается при загрузке аддона.
    app_context: AppContext (доступ к config, logger, storage)
    Возвращает словарь регистрируемых объектов.
    """
    return {
        "strategies": {
            "my_task_type": MyStrategy,
        },
        "pipeline_stages": [
            # Новые этапы добавятся в pipeline.json автоматически
        ],
    }
```

---

## 8. AddonLoader

```python
# core/addon_loader.py (уже включён)
from core.addon_loader import AddonLoader

# Загрузить все аддоны из ./addons/
AddonLoader.load_all(app_context)

# Загрузить конкретный аддон
AddonLoader.load("my_addon", app_context)
```

---

## Примеры готовых аддонов

| Аддон | Описание | Файл |
|-------|----------|------|
| `groq_backend` | Groq API (llama3, mixtral) | `addons/groq_backend.py` |
| `wordpress_strategy` | WordPress плагины | `addons/wordpress_strategy.py` |
| `security_audit` | OWASP-аудит кода | pipeline.json stage |
| `rust_runner` | Запуск Rust/cargo | `addons/rust_runner.py` |
| `domain_analyzer` | Предметный анализатор | `addons/domain_analyzer.py` |

---

## Быстрый старт: минимальный аддон за 5 минут

```python
# addons/hello_addon/__init__.py
from strategy.task_analyzer import StrategyBase, TaskType

class DataScienceStrategy(StrategyBase):
    def get_pipeline_stages(self):
        return [
            "problem_analysis",
            "user_clarification", 
            "code_block_generation",
            "unit_tests",
            "readme_generation",
            "project_critique",
        ]
    
    def get_prompt_overrides(self):
        return {
            "problem_analysis": (
                "Ты — Data Scientist. Проанализируй задачу машинного обучения. "
                "Определи: тип задачи (классификация/регрессия/кластеризация), "
                "входные данные, метрики качества, библиотеки (pandas/sklearn/pytorch). "
                "Верни GPT_PROTO_V1 JSON."
            )
        }
    
    def get_task_type(self):
        return TaskType.OTHER

ADDON_META = {"name": "Data Science", "version": "1.0.0"}

def register(app_context=None):
    return {"strategies": {"data_science": DataScienceStrategy}}
```

Теперь зарегистрируйте в `strategy/task_analyzer.py`:
```python
# В _KEYWORDS добавьте:
TaskType.OTHER: ["data science", "ml", "машинное обучение", "нейросеть", ...],
# В select_strategy добавьте условие
```

**Готово!** Тип задачи `data_science` автоматически распознаётся.
