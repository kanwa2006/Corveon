"""OpenRouter adapter (ADR-0006) — httpx against OpenRouter's
OpenAI-compatible endpoint (no SDK). Wire format shared with OpenAI; see
openai_compatible.py. OpenRouter's free-tier rate limit never rises with
purchased credits (§5) — see OPENROUTER_RPM_LIMIT in docs/ENVIRONMENT.md."""

from __future__ import annotations

import httpx

from app.providers.openai_compatible import OpenAICompatibleProvider

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"

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
