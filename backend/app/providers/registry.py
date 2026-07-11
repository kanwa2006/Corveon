"""Provider registry — priority-ordered, capability-based routing (ADR-0006).
Zero providers configured is valid; callers get ``NoProviderAvailableError``
and render the typed ``provider_unavailable`` degraded-mode result
(docs/ARCHITECTURE.md §3) rather than a hard failure.

Beyond plain priority-ordered failover, the registry also applies (CLAUDE.md
§23.1/§23.2):
- a per-provider circuit breaker (``ProviderHealthTracker``) — a provider
  that has been failing repeatedly is skipped for a cooldown window instead
  of being retried on every request;
- an optional per-provider token-bucket rate limiter, so concurrent requests
  collectively respect a provider's published RPM limit rather than each
  request getting its own private allowance;
- an optional per-request ``LLMCallBudget`` (created by the caller, e.g. the
  orchestrator) capping how many provider attempts a single request may make
  in total.

None of this changes the "absence of a provider is never an error" posture:
health/rate-limit state is only ever consulted for providers already present
in ``providers`` (i.e. already configured) — an unconfigured provider is
simply never in that dict to begin with.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.tracing import get_tracer
from app.providers.anthropic import AnthropicProvider
from app.providers.base import ChatMessage, ChatProvider, ProviderUnavailableError
from app.providers.budget import LLMCallBudget, TokenBucket
from app.providers.gemini import GeminiProvider
from app.providers.health import ProviderHealthTracker
from app.providers.metrics import PROVIDER_CALL_LATENCY, PROVIDER_CALLS
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider
from app.providers.openrouter import OpenRouterProvider

logger = get_logger(__name__)
tracer = get_tracer(__name__)


class NoProviderAvailableError(Exception):
    """No configured provider could serve the request (degraded mode)."""


class ProviderRegistry:
    def __init__(
        self,
        providers: dict[str, ChatProvider],
        priority: list[str],
        *,
        health: ProviderHealthTracker | None = None,
        token_buckets: dict[str, TokenBucket] | None = None,
    ) -> None:
        self._providers = providers
        ordered = [name for name in priority if name in providers]
        # Any configured provider missing from PROVIDER_PRIORITY still gets a
        # turn, just after the explicitly ordered ones.
        ordered += [name for name in providers if name not in ordered]
        self._priority = ordered
        self._health = health if health is not None else ProviderHealthTracker()
        self._token_buckets = token_buckets or {}

    @property
    def health(self) -> ProviderHealthTracker:
        return self._health

    @property
    def registered_provider_names(self) -> list[str]:
        return list(self._priority)

    async def stream_chat(
        self,
        *,
        messages: list[ChatMessage],
        model: str | None = None,
        budget: LLMCallBudget | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Yields ``(provider_name, text_delta)`` from the first available,
        healthy provider in priority order. Fails over only *before* any
        delta has been produced — once a provider has streamed partial
        output, a mid-stream failure is re-raised rather than spliced with a
        different provider's continuation, which would garble the response.

        ``budget``, if given, is consumed once per provider actually
        attempted (not for providers skipped due to an open circuit or an
        empty rate-limit bucket, since no call was actually made) — a
        ``LLMCallBudgetExceededError`` propagates immediately, distinct from
        ``NoProviderAvailableError``.
        """
        last_error: Exception | None = None
        for name in self._priority:
            if not self._health.is_available(name):
                PROVIDER_CALLS.labels(name, "skipped_circuit_open").inc()
                logger.info("provider_skipped_circuit_open", provider=name)
                continue

            bucket = self._token_buckets.get(name)
            if bucket is not None and not bucket.try_consume():
                PROVIDER_CALLS.labels(name, "skipped_rate_limited").inc()
                logger.info("provider_skipped_rate_limited", provider=name)
                continue

            if budget is not None:
                budget.consume()

            provider = self._providers[name]
            yielded_any = False
            started = time.monotonic()
            with tracer.start_as_current_span("provider.stream_chat") as span:
                span.set_attribute("provider.name", name)
                try:
                    async for delta in provider.stream_chat(messages=messages, model=model):
                        yielded_any = True
                        yield name, delta
                    self._health.record_success(name)
                    PROVIDER_CALLS.labels(name, "success").inc()
                    PROVIDER_CALL_LATENCY.labels(name).observe(time.monotonic() - started)
                    span.set_attribute("provider.outcome", "success")
                    logger.info(
                        "provider_call_succeeded",
                        provider=name,
                        duration_ms=round((time.monotonic() - started) * 1000),
                    )
                    return
                except ProviderUnavailableError as exc:
                    last_error = exc
                    self._health.record_failure(name)
                    PROVIDER_CALLS.labels(name, "failure").inc()
                    span.set_attribute("provider.outcome", "failure")
                    span.record_exception(exc)
                    logger.warning("provider_call_failed", provider=name, error=str(exc))
                    if yielded_any:
                        raise
                    continue
        raise NoProviderAvailableError(
            "No configured AI provider is currently reachable."
        ) from last_error


def _maybe_register_rpm_limit(
    token_buckets: dict[str, TokenBucket], name: str, rpm_limit: int | None
) -> None:
    if rpm_limit is not None:
        token_buckets[name] = TokenBucket(capacity=rpm_limit, refill_rate_per_second=rpm_limit / 60)


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    providers: dict[str, ChatProvider] = {}
    token_buckets: dict[str, TokenBucket] = {}

    # ollama_only (ADR-0024) is a stronger guarantee than simply leaving keys
    # blank: a cloud provider is never registered even if its key is set, so
    # an operator's leftover .env value can't silently re-enable one.
    if not settings.is_ollama_only:
        if settings.gemini_api_key_pool:
            providers["gemini"] = GeminiProvider(
                api_keys=settings.gemini_api_key_pool,
                default_model=settings.GEMINI_DEFAULT_MODEL,
            )
            _maybe_register_rpm_limit(token_buckets, "gemini", settings.GEMINI_RPM_LIMIT)

        if settings.anthropic_api_key_pool:
            providers["anthropic"] = AnthropicProvider(
                api_keys=settings.anthropic_api_key_pool,
                default_model=settings.ANTHROPIC_DEFAULT_MODEL,
            )
            _maybe_register_rpm_limit(token_buckets, "anthropic", settings.ANTHROPIC_RPM_LIMIT)

        if settings.openai_api_key_pool:
            providers["openai"] = OpenAIProvider(
                api_keys=settings.openai_api_key_pool,
                default_model=settings.OPENAI_DEFAULT_MODEL,
            )
            _maybe_register_rpm_limit(token_buckets, "openai", settings.OPENAI_RPM_LIMIT)

        if settings.openrouter_api_key_pool:
            providers["openrouter"] = OpenRouterProvider(
                api_keys=settings.openrouter_api_key_pool,
                default_model=settings.OPENROUTER_DEFAULT_MODEL,
            )
            _maybe_register_rpm_limit(token_buckets, "openrouter", settings.OPENROUTER_RPM_LIMIT)

    # Ollama is registered optimistically — an unreachable local Ollama
    # raises ProviderUnavailableError at call time like any other provider
    # failure; there is no separate "not configured" state for it.
    providers["ollama"] = OllamaProvider(
        base_url=settings.OLLAMA_BASE_URL,
        default_model=settings.OLLAMA_DEFAULT_MODEL,
    )
    _maybe_register_rpm_limit(token_buckets, "ollama", settings.OLLAMA_RPM_LIMIT)

    health = ProviderHealthTracker(
        failure_threshold=settings.PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        cooldown_seconds=settings.PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    )
    return ProviderRegistry(
        providers, settings.provider_priority_list, health=health, token_buckets=token_buckets
    )
