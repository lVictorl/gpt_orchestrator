"""
ai_gateway/gateway.py — AIGateway v1.5

Исправления:
  - Полное логирование КАЖДОГО запроса/ответа через StructLogger
  - DeepSeek: ждём только если предыдущий запрос был < 62 с назад
  - ping() для проверки соединения
  - Метод send_message логирует промпт, ответ, латентность
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional

from storage.models import ChatMeta, Message


# ─────────────── Rate limiters ──────────────────────────

class RateLimiter:
    def __init__(self, requests_per_minute: int = 20) -> None:
        self._rpm = max(requests_per_minute, 1)
        self._tokens = float(self._rpm)
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            self._tokens = min(
                self._rpm,
                self._tokens + (now - self._last_refill) * (self._rpm / 60.0)
            )
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            await asyncio.sleep(0.5)


class DeepSeekRateLimiter:
    """1 RPM — пауза ТОЛЬКО если предыдущий запрос был недавно."""
    _MIN_INTERVAL = 62.0  # секунды

    def __init__(self) -> None:
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._last_request > 0:
                elapsed = now - self._last_request
                wait = self._MIN_INTERVAL - elapsed
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_request = time.monotonic()


# ─────────────── AIGateway ──────────────────────────────

class AIGateway:
    PROVIDERS = ("openai", "anthropic", "deepseek")

    def __init__(self, config: "ConfigManager", logger=None) -> None:  # noqa: F821
        self._config = config
        self._logger = logger
        self._chats: dict[str, list[dict]] = {}
        self._client = None
        self._provider: str = ""
        self._rate_limiter: RateLimiter | DeepSeekRateLimiter | None = None
        self._init_client()

    def _log(self, method: str, *args, **kwargs) -> None:
        if self._logger and hasattr(self._logger, method):
            getattr(self._logger, method)(*args, **kwargs)

    def _init_client(self) -> None:
        provider = self._config.get("api.provider", "anthropic")
        self._provider = provider

        if provider == "openai":
            try:
                import openai
                key = self._config.get("api.openai_key", "")
                self._client = openai.AsyncOpenAI(api_key=key) if key else None
            except ImportError:
                self._client = None
            self._rate_limiter = RateLimiter(self._config.get("api.rpm", 20))

        elif provider == "anthropic":
            try:
                import anthropic
                key = self._config.get("api.anthropic_key", "")
                self._client = anthropic.AsyncAnthropic(api_key=key) if key else None
            except ImportError:
                self._client = None
            self._rate_limiter = RateLimiter(self._config.get("api.rpm", 20))

        elif provider == "deepseek":
            try:
                import openai
                key = self._config.get("api.deepseek_key", "")
                self._client = (
                    openai.AsyncOpenAI(
                        api_key=key,
                        base_url="https://api.deepseek.com/v1",
                    ) if key else None
                )
            except ImportError:
                self._client = None
            self._rate_limiter = DeepSeekRateLimiter()
        else:
            self._client = None
            self._rate_limiter = RateLimiter()

    def set_api_key(self, key: str, provider: str | None = None) -> None:
        if provider:
            self._config.set("api.provider", provider)
        key_map = {
            "openai":    "api.openai_key",
            "anthropic": "api.anthropic_key",
            "deepseek":  "api.deepseek_key",
        }
        prov = provider or self._provider
        self._config.set(key_map.get(prov, "api.anthropic_key"), key)
        self._init_client()

    def set_logger(self, logger) -> None:
        self._logger = logger

    async def ping(self) -> tuple[bool, str]:
        if self._client is None:
            return False, "Клиент не инициализирован. Проверьте API-ключ."
        try:
            if self._provider == "anthropic":
                import anthropic
                msg = await self._client.messages.create(
                    model=self._config.get("api.model_anthropic", "claude-sonnet-4-20250514"),
                    max_tokens=8,
                    messages=[{"role": "user", "content": "ping"}],
                )
                return True, f"✅ Anthropic OK (модель: {msg.model})"
            elif self._provider in ("openai", "deepseek"):
                model = (
                    self._config.get("api.model_deepseek", "deepseek-chat")
                    if self._provider == "deepseek"
                    else self._config.get("api.model_openai", "gpt-4o")
                )
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=8,
                )
                return True, f"✅ {self._provider.capitalize()} OK (модель: {resp.model})"
            return False, "Неизвестный провайдер"
        except Exception as exc:
            err = str(exc)
            if "401" in err or "Unauthorized" in err or "invalid" in err.lower():
                return False, f"❌ Неверный API-ключ: {err[:120]}"
            if "429" in err:
                return False, f"⚠️ Rate limit: {err[:120]}"
            return False, f"❌ {err[:200]}"

    # ── Chat management ────────────────────────────────────

    async def create_chat(self, title: str) -> str:
        import uuid
        chat_id = str(uuid.uuid4())
        self._chats[chat_id] = []
        return chat_id

    async def read_chat(self, chat_id: str) -> List[Message]:
        from datetime import datetime
        return [
            Message(role=m["role"], content=m["content"], timestamp=datetime.utcnow())
            for m in self._chats.get(chat_id, [])
        ]

    async def delete_chat(self, chat_id: str) -> None:
        self._chats.pop(chat_id, None)

    async def rename_chat(self, chat_id: str, title: str) -> None:
        pass

    async def list_chats(self) -> List[ChatMeta]:
        from datetime import datetime
        return [
            ChatMeta(chat_id=cid, title=f"Chat {cid[:8]}", created_at=datetime.utcnow())
            for cid in self._chats
        ]

    def load_history(self, chat_id: str, messages: List[Message]) -> None:
        self._chats[chat_id] = [
            {"role": m.role, "content": m.content} for m in messages
        ]

    # ── Messaging ─────────────────────────────────────────

    async def send_message(
        self,
        chat_id: str,
        prompt: str,
        system: str = "",
        stage: str = "",
        project_id: str = "",
    ) -> AsyncIterator[str]:
        """Отправляет сообщение, логирует запрос и ответ."""
        model = self._get_model()
        start = time.monotonic()

        # Лог запроса
        self._log(
            "log_ai_request",
            provider=self._provider,
            model=model,
            stage=stage,
            prompt=prompt,
            system=system,
            project_id=project_id,
        )

        # Rate limit
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        if chat_id not in self._chats:
            self._chats[chat_id] = []
        self._chats[chat_id].append({"role": "user", "content": prompt})

        full_response = ""
        error_occurred = None

        try:
            if self._client is None:
                demo = f"[DEMO — нет API-ключа] stage={stage} prompt_len={len(prompt)}"
                for ch in demo:
                    yield ch
                    full_response += ch
            elif self._provider == "openai":
                async for chunk in self._stream_openai(chat_id, system):
                    yield chunk
                    full_response += chunk
            elif self._provider == "deepseek":
                async for chunk in self._stream_deepseek(chat_id, system):
                    yield chunk
                    full_response += chunk
            else:
                async for chunk in self._stream_anthropic(chat_id, system):
                    yield chunk
                    full_response += chunk
        except Exception as exc:
            error_occurred = exc
            self._log(
                "log_ai_error",
                provider=self._provider,
                stage=stage,
                error=str(exc),
                project_id=project_id,
            )
            raise

        latency = time.monotonic() - start
        self._chats[chat_id].append({"role": "assistant", "content": full_response})

        # Лог ответа
        self._log(
            "log_ai_response",
            provider=self._provider,
            stage=stage,
            response=full_response,
            tokens_out=len(full_response.split()),  # приблизительно
            latency_sec=latency,
            project_id=project_id,
        )

    def _get_model(self) -> str:
        if self._provider == "anthropic":
            return self._config.get("api.model_anthropic", "claude-sonnet-4-20250514")
        if self._provider == "deepseek":
            return self._config.get("api.model_deepseek", "deepseek-chat")
        return self._config.get("api.model_openai", "gpt-4o")

    async def _stream_openai(self, chat_id: str, system: str) -> AsyncIterator[str]:
        model = self._config.get("api.model_openai", "gpt-4o")
        max_tokens = self._config.get("api.max_tokens", 8192)
        messages = self._chats[chat_id].copy()
        if system:
            messages = [{"role": "system", "content": system}] + messages
        stream = await self._client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def _stream_deepseek(self, chat_id: str, system: str) -> AsyncIterator[str]:
        model = self._config.get("api.model_deepseek", "deepseek-chat")
        max_tokens = self._config.get("api.max_tokens", 8192)
        messages = self._chats[chat_id].copy()
        if system:
            messages = [{"role": "system", "content": system}] + messages
        stream = await self._client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def _stream_anthropic(self, chat_id: str, system: str) -> AsyncIterator[str]:
        model = self._config.get("api.model_anthropic", "claude-sonnet-4-20250514")
        max_tokens = self._config.get("api.max_tokens", 8192)
        messages = self._chats[chat_id].copy()
        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
