"""OpenAI adapter (ADR-0006) — httpx directly against the Chat Completions
API (no SDK). Wire format shared with OpenRouter; see openai_compatible.py."""

from __future__ import annotations

import httpx

from app.providers.openai_compatible import OpenAICompatibleProvider

_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_keys: list[str],
        default_model: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=_BASE_URL,
            api_keys=api_keys,
            default_model=default_model,
            transport=transport,
        )
