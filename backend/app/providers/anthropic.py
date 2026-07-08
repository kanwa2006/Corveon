"""Anthropic adapter (ADR-0006) — httpx directly against the Messages API
(no SDK). Streams via SSE ``content_block_delta`` events; unlike the
OpenAI-shaped providers, the system prompt is a separate top-level field
and ``max_tokens`` is required — genuinely different wire format, so this
gets its own adapter rather than sharing openai_compatible.py. Rotates
across the configured key pool like Gemini's adapter."""

from __future__ import annotations

import itertools
import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import ChatMessage, ChatProvider, ChatRole, ProviderUnavailableError

_BASE_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
# Anthropic requires max_tokens on every request. This is a ceiling, not a
# target — the model still stops naturally well before this in the common
# chat-reply case.
_MAX_TOKENS = 4096


class AnthropicProvider(ChatProvider):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_keys: list[str],
        default_model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_keys:
            raise ValueError("AnthropicProvider requires at least one API key.")
        self._keys = itertools.cycle(api_keys)
        self._default_model = default_model
        # Injectable only so tests can substitute httpx.MockTransport
        # (ADR-0006: "testable with fakes").
        self._transport = transport

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        model_name = model or self._default_model
        system_parts = [m.content for m in messages if m.role == ChatRole.SYSTEM]
        conversation = [
            {"role": m.role.value, "content": m.content}
            for m in messages
            if m.role != ChatRole.SYSTEM
        ]
        body: dict[str, object] = {
            "model": model_name,
            "max_tokens": _MAX_TOKENS,
            "messages": conversation,
            "stream": True,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)

        headers = {
            "x-api-key": next(self._keys),
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            async with (
                httpx.AsyncClient(timeout=60.0, transport=self._transport) as client,
                client.stream("POST", _BASE_URL, headers=headers, json=body) as response,
            ):
                if response.status_code >= 400:
                    raise ProviderUnavailableError(
                        f"Anthropic returned HTTP {response.status_code}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").strip()
                    if not payload:
                        continue
                    chunk = json.loads(payload)
                    if chunk.get("type") != "content_block_delta":
                        continue
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text")
                        if text:
                            yield text
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Anthropic request failed: {exc}") from exc
