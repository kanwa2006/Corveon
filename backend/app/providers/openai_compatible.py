"""Shared implementation for OpenAI Chat-Completions-compatible providers.

OpenAI itself and OpenRouter deliberately expose the same wire shape
(``POST {base_url}/chat/completions``, ``Authorization: Bearer``, SSE
``data:`` lines terminated by ``data: [DONE]``) — one adapter per *wire
protocol* rather than per vendor avoids duplicating identical SSE-parsing
logic for what is, byte-for-byte, the same API shape (ADR-0006)."""

from __future__ import annotations

import itertools
import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import ChatMessage, ChatProvider, ProviderUnavailableError


class OpenAICompatibleProvider(ChatProvider):
    """Base for any provider exposing an OpenAI-shaped
    ``POST {base_url}/chat/completions`` streaming endpoint. Subclasses set
    ``name`` and pass their own ``base_url``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_keys: list[str],
        default_model: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_keys:
            raise ValueError(f"{type(self).__name__} requires at least one API key.")
        self._base_url = base_url.rstrip("/")
        self._keys = itertools.cycle(api_keys)
        self._default_model = default_model
        # Injectable only so tests can substitute httpx.MockTransport
        # (ADR-0006: "testable with fakes").
        self._transport = transport

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        model_name = model or self._default_model
        if not model_name:
            # No per-call model and no configured default — nothing to call.
            # Not a hard error: the registry treats this like any other
            # provider-unavailable outcome and fails over.
            raise ProviderUnavailableError(
                f"{self.name}: no model specified and no default model configured."
            )
        body = {
            "model": model_name,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "stream": True,
        }
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {next(self._keys)}"}
        try:
            async with (
                httpx.AsyncClient(timeout=60.0, transport=self._transport) as client,
                client.stream("POST", url, headers=headers, json=body) as response,
            ):
                if response.status_code >= 400:
                    raise ProviderUnavailableError(
                        f"{self.name} returned HTTP {response.status_code}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").strip()
                    if not payload or payload == "[DONE]":
                        continue
                    chunk = json.loads(payload)
                    for choice in chunk.get("choices", []):
                        text = choice.get("delta", {}).get("content")
                        if text:
                            yield text
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"{self.name} request failed: {exc}") from exc
