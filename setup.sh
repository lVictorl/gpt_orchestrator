#!/bin/bash
set -e

echo "═══════════════════════════════════════════════════"
echo "   GPT-Orchestrator — установка зависимостей"
echo "═══════════════════════════════════════════════════"

# Проверка Python 3.11+
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]); then
    echo "❌ Требуется Python 3.11+. Установлен: $PYTHON_VERSION"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION"

# Виртуальное окружение
if [ ! -d ".venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "✅ venv активирован"

# Обновление pip
pip install --quiet --upgrade pip

# Основные зависимости
echo "📥 Установка зависимостей..."
pip install --quiet \
    "PyQt6>=6.6" \
    "qasync>=0.27" \
    "openai>=1.30" \
    "anthropic>=0.28" \
    "aiosqlite>=0.20" \
    "msgpack>=1.0" \
    "zstandard>=0.22" \
    "jinja2>=3.1" \
    "structlog>=24.1" \
    "tomli-w>=1.0"

# Тестовые зависимости
pip install --quiet \
    "pytest>=8.0" \
    "pytest-asyncio>=0.23" \
    "pytest-qt>=4.4"

echo "✅ Зависимости установлены"

# Папки
mkdir -p projects templates logs
echo "✅ Папки созданы"

# Конфиг
if [ ! -f "config.toml" ]; then
    cp config.example.toml config.toml
    echo "✅ config.toml создан из config.example.toml"
    echo ""
    echo "⚠️  Не забудьте добавить API-ключ в config.toml:"
    echo "   [api]"
    echo '   anthropic_key = "sk-ant-..."'
    echo "   или запустите приложение и введите ключ через меню Настройки → API-ключ"
fi

# Тесты
echo ""
echo "🧪 Запуск тестов..."
cd "$(dirname "$0")"
python3 -m pytest tests/ -v --tb=short 2>&1 || echo "⚠️  Некоторые тесты не прошли (PyQt6 требует дисплей)"

echo ""
echo "═══════════════════════════════════════════════════"
echo "   Запуск приложения:"
echo "   source .venv/bin/activate"
echo "   python main.py"
echo "═══════════════════════════════════════════════════"

# Установка зависимостей
echo "📦 Установка зависимостей..."
pip install --quiet -r requirements.txt
echo "✅ Зависимости установлены"

# Создание config.toml если не существует
if [ ! -f "config.toml" ]; then
    cp config.example.toml config.toml
    echo "✅ config.toml создан из примера"
    echo "⚠️  Заполните API-ключи в config.toml или через GUI (Настройки → API-ключ)"
else
    echo "✅ config.toml уже существует"
fi

echo ""
echo "🚀 Запуск: python main.py"
echo "📖 Документация: см. SPECIFICATION.md"
echo "═══════════════════════════════════════════════════"
