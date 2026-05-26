"""
cli/cli_main.py — CLI-интерфейс GPT-Orchestrator

Исправление #13: приложение поддерживает CLI через Click.

Использование:
    python -m cli.cli_main run "Создай Telegram-бота"
    python -m cli.cli_main run "..." --provider deepseek
    python -m cli.cli_main history
    python -m cli.cli_main config set api.provider deepseek
    python -m cli.cli_main config get api.provider
"""
from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import click

from core.config_manager import ConfigManager
from core.logger import StructLogger
from core.app_context import AppContext
from ai_gateway.gateway import AIGateway
from storage.storage_manager import StorageManager
from orchestrator.pipeline_orchestrator import PipelineOrchestrator, StageStatus
from prompt_registry.registry import PromptRegistry
from parser.response_parser import ResponseParser
from strategy.task_analyzer import TaskAnalyzer


def _build_services(provider: str | None = None):
    config = ConfigManager("config.toml")
    config.load()
    if provider:
        config.set("api.provider", provider)
    logger = StructLogger(level=config.get("app.log_level", "INFO"))
    app_context = AppContext(config=config, logger=logger)
    gateway = AIGateway(config)
    storage = StorageManager("data.db")
    registry = PromptRegistry("pipeline.json")
    parser = ResponseParser()
    return config, logger, app_context, gateway, storage, registry, parser


@click.group()
def cli():
    """GPT-Orchestrator — оркестрация промптов ИИ из командной строки."""
    pass


@cli.command()
@click.argument("task")
@click.option("--provider", "-p", default=None,
              type=click.Choice(["anthropic", "openai", "deepseek"]),
              help="Провайдер ИИ")
@click.option("--strategy", "-s", default=None,
              help="Принудительно выбрать стратегию (code/debug/bot/android/...)")
def run(task: str, provider: str | None, strategy: str | None):
    """Запустить пайплайн для TASK."""
    config, logger, app_ctx, gateway, storage, registry, parser = _build_services(provider)

    analyzer = TaskAnalyzer()
    task_type = analyzer.analyze(task)

    if strategy:
        from strategy.task_analyzer import (
            CodeStrategy, DebugStrategy, BotStrategy,
            AndroidStrategy, CourseStrategy, ScriptStrategy, GenericStrategy,
        )
        strategy_map = {
            "code": CodeStrategy,
            "debug": DebugStrategy,
            "bot": BotStrategy,
            "android": AndroidStrategy,
            "course": CourseStrategy,
            "script": ScriptStrategy,
        }
        strat = strategy_map.get(strategy, GenericStrategy)()
    else:
        strat = analyzer.select_strategy(task_type)

    click.echo(f"🚀 Задача: {task}")
    click.echo(f"📋 Тип: {task_type.value}  |  Стратегия: {type(strat).__name__}")
    click.echo(f"🔌 Провайдер: {config.get('api.provider')}")
    click.echo("─" * 60)

    orchestrator = PipelineOrchestrator(
        app_context=app_ctx,
        ai_gateway=gateway,
        storage=storage,
        registry=registry,
        parser=parser,
    )

    def on_token(stage: str, token: str):
        click.echo(token, nl=False)

    def on_stage(stage: str, status: StageStatus):
        if status == StageStatus.RUNNING:
            click.echo(f"\n\n▶ [{stage}]")
        elif status == StageStatus.DONE:
            click.echo(f"\n✅ Этап завершён: {stage}")
        elif status == StageStatus.ERROR:
            click.echo(f"\n❌ Ошибка: {stage}", err=True)

    orchestrator.set_token_callback(on_token)
    orchestrator.set_stage_callback(on_stage)

    async def _run():
        await storage.init()
        import uuid
        app_ctx.reset_project(str(uuid.uuid4()))
        async for result in orchestrator.run_pipeline(task, strat):
            pass
        await storage.close()

    asyncio.run(_run())
    click.echo("\n\n✅ Пайплайн завершён.")


@cli.command()
def history():
    """Показать историю проектов."""
    async def _list():
        storage = StorageManager("data.db")
        await storage.init()
        projects = await storage.list_projects()
        if not projects:
            click.echo("История пуста.")
        else:
            click.echo(f"{'ID':<10} {'Тип':<12} {'Статус':<12} {'Название'}")
            click.echo("─" * 60)
            for p in projects:
                click.echo(
                    f"{p.project_id[:8]:<10} {p.task_type:<12} {p.status:<12} {p.title}"
                )
        await storage.close()

    asyncio.run(_list())


@cli.group()
def config():
    """Управление конфигурацией."""
    pass


@config.command("get")
@click.argument("key")
def config_get(key: str):
    """Получить значение конфига (dot-path: api.provider)."""
    cfg = ConfigManager("config.toml")
    cfg.load()
    value = cfg.get(key)
    if value is None:
        click.echo(f"Ключ '{key}' не найден.", err=True)
    else:
        click.echo(f"{key} = {value}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Установить значение конфига."""
    cfg = ConfigManager("config.toml")
    cfg.load()
    # Попытаться преобразовать тип
    parsed: object = value
    if value.lower() in ("true", "false"):
        parsed = value.lower() == "true"
    elif value.isdigit():
        parsed = int(value)
    else:
        try:
            parsed = float(value)
        except ValueError:
            parsed = value
    cfg.set(key, parsed)
    try:
        cfg.save()
        click.echo(f"✅ {key} = {parsed}")
    except Exception as exc:
        click.echo(f"❌ Ошибка сохранения: {exc}", err=True)


if __name__ == "__main__":
    cli()
