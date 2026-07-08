"""Provider registry — priority-ordered, capability-based routing (ADR-0006).
Zero providers configured is valid; callers get ``NoProviderAvailableError``
and render the typed ``provider_unavailable`` degraded-mode result
(docs/ARCHITECTURE.md §3) rather than a hard failure."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.config import Settings
from app.providers.base import ChatMessage, ChatProvider, ProviderUnavailableError
from app.providers.gemini import GeminiProvider
from app.providers.ollama import OllamaProvider


class NoProviderAvailableError(Exception):
    """No configured provider could serve the request (degraded mode)."""


class ProviderRegistry:
    def __init__(self, providers: dict[str, ChatProvider], priority: list[str]) -> None:
        self._providers = providers
        ordered = [name for name in priority if name in providers]
        # Any configured provider missing from PROVIDER_PRIORITY still gets a
        # turn, just after the explicitly ordered ones.
        ordered += [name for name in providers if name not in ordered]
        self._priority = ordered

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[tuple[str, str]]:
        """Yields ``(provider_name, text_delta)`` from the first healthy
        provider in priority order. Fails over only *before* any delta has
        been produced — once a provider has streamed partial output, a
        mid-stream failure is re-raised rather than spliced with a different
        provider's continuation, which would garble the response."""
        last_error: Exception | None = None
        for name in self._priority:
            provider = self._providers[name]
            yielded_any = False
            try:
                async for delta in provider.stream_chat(messages=messages, model=model):
                    yielded_any = True
                    yield name, delta
                return
            except ProviderUnavailableError as exc:
                last_error = exc
                if yielded_any:
                    raise
                continue
        raise NoProviderAvailableError(
            "No configured AI provider is currently reachable."
        ) from last_error


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    providers: dict[str, ChatProvider] = {}
    if settings.gemini_api_key_pool:
        providers["gemini"] = GeminiProvider(
            api_keys=settings.gemini_api_key_pool,
            default_model=settings.GEMINI_DEFAULT_MODEL,
        )
    # Ollama is registered optimistically — an unreachable local Ollama
    # raises ProviderUnavailableError at call time like any other provider
    # failure; there is no separate "not configured" state for it.
    providers["ollama"] = OllamaProvider(
        base_url=settings.OLLAMA_BASE_URL,
        default_model=settings.OLLAMA_DEFAULT_MODEL,
    )
    return ProviderRegistry(providers, settings.provider_priority_list)
