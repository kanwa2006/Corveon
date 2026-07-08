"""Ollama adapter — httpx against the local Ollama REST API. The implicit
local default when reachable (ADR-0006); a connection failure means "not
reachable right now", handled identically to any other provider failure —
never a special-cased warning."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import ChatMessage, ChatProvider, ProviderUnavailableError


class OllamaProvider(ChatProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        default_model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        # Injectable only so tests can substitute httpx.MockTransport
        # (ADR-0006: "testable with fakes").
        self._transport = transport

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        body = {
            "model": model or self._default_model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "stream": True,
        }
        url = f"{self._base_url}/api/chat"
        try:
            async with (
                httpx.AsyncClient(timeout=120.0, transport=self._transport) as client,
                client.stream("POST", url, json=body) as response,
            ):
                if response.status_code >= 400:
                    raise ProviderUnavailableError(f"Ollama returned HTTP {response.status_code}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    text = chunk.get("message", {}).get("content")
                    if text:
                        yield text
                    if chunk.get("done"):
                        return
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Ollama unreachable: {exc}") from exc
