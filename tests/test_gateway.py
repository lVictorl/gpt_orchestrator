"""
tests/test_gateway.py — Тесты AIGateway и DeepSeekRateLimiter (исправление #5).
"""
from __future__ import annotations

import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import MagicMock, AsyncMock

from ai_gateway.gateway import AIGateway, DeepSeekRateLimiter, RateLimiter
from core.config_manager import ConfigManager


def make_config(**overrides):
    cfg = MagicMock()
    defaults = {
        "api.provider": "anthropic",
        "api.openai_key": "",
        "api.anthropic_key": "",
        "api.deepseek_key": "",
        "api.model_openai": "gpt-4o",
        "api.model_anthropic": "claude-sonnet-4-20250514",
        "api.model_deepseek": "deepseek-chat",
        "api.max_tokens": 1024,
        "api.rpm": 10,
    }
    defaults.update(overrides)
    cfg.get = lambda key, default=None: defaults.get(key, default)
    cfg.set = MagicMock()
    return cfg


@pytest.mark.asyncio
async def test_create_and_list_chats():
    cfg = make_config()
    gw = AIGateway(cfg)
    chat_id = await gw.create_chat("Test")
    assert chat_id
    chats = await gw.list_chats()
    assert any(c.chat_id == chat_id for c in chats)


@pytest.mark.asyncio
async def test_delete_chat():
    cfg = make_config()
    gw = AIGateway(cfg)
    chat_id = await gw.create_chat("Del")
    await gw.delete_chat(chat_id)
    chats = await gw.list_chats()
    assert not any(c.chat_id == chat_id for c in chats)


@pytest.mark.asyncio
async def test_demo_mode_no_key():
    """Без ключа — demo-режим, не падает."""
    cfg = make_config()
    gw = AIGateway(cfg)
    chat_id = await gw.create_chat("Demo")
    result = ""
    async for token in gw.send_message(chat_id, "hello"):
        result += token
    assert "DEMO" in result


@pytest.mark.asyncio
async def test_deepseek_rate_limiter_post_wait(monkeypatch):
    """DeepSeekRateLimiter.post_response_wait вызывается после ответа."""
    waited = []

    async def fake_sleep(t):
        waited.append(t)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    rl = DeepSeekRateLimiter()
    await rl.post_response_wait()
    assert DeepSeekRateLimiter._POST_RESPONSE_WAIT in waited


def test_set_api_key_deepseek():
    cfg = make_config(**{"api.provider": "deepseek"})
    gw = AIGateway(cfg)
    gw.set_api_key("ds-test-key", "deepseek")
    cfg.set.assert_called()


def test_providers_list():
    assert "deepseek" in AIGateway.PROVIDERS
    assert "openai" in AIGateway.PROVIDERS
    assert "anthropic" in AIGateway.PROVIDERS
