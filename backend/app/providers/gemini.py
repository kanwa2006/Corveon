"""Gemini adapter (ADR-0006) — httpx directly against the Gemini REST API
(no SDK dependency, consistent with the rest of the stack being httpx-based).
Streams via ``alt=sse``. Rotates across the configured key pool so a single
free-tier key's RPM limit doesn't bottleneck every request."""

from __future__ import annotations

import itertools
import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import ChatMessage, ChatProvider, ChatRole, ProviderUnavailableError

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(ChatProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_keys: list[str],
        default_model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_keys:
            raise ValueError("GeminiProvider requires at least one API key.")
        self._keys = itertools.cycle(api_keys)
        self._default_model = default_model
        # Injectable only so tests can substitute httpx.MockTransport
        # (ADR-0006: "testable with fakes") — production always uses the
        # default (a real connection).
        self._transport = transport

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        model_name = model or self._default_model
        system_parts = [m.content for m in messages if m.role == ChatRole.SYSTEM]
        # Gemini's `contents` roles are "user"/"model", not "system"/"assistant".
        contents = [
            {
                "role": "model" if m.role == ChatRole.ASSISTANT else "user",
                "parts": [{"text": m.content}],
            }
            for m in messages
            if m.role != ChatRole.SYSTEM
        ]
        body: dict[str, object] = {"contents": contents}
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        url = f"{_BASE_URL}/models/{model_name}:streamGenerateContent"
        params = {"alt": "sse", "key": next(self._keys)}

        try:
            async with (
                httpx.AsyncClient(timeout=60.0, transport=self._transport) as client,
                client.stream("POST", url, params=params, json=body) as response,
            ):
                if response.status_code >= 400:
                    raise ProviderUnavailableError(f"Gemini returned HTTP {response.status_code}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").strip()
                    if not payload:
                        continue
                    chunk = json.loads(payload)
                    for candidate in chunk.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            text = part.get("text")
                            if text:
                                yield text
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Gemini request failed: {exc}") from exc
