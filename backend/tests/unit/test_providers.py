"""Unit tests for the provider-agnostic AI layer (app/providers/). Gemini and
Ollama adapters are tested against httpx.MockTransport — no real network
calls or API keys required (ADR-0006: "testable with fakes")."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.config import Settings
from app.providers.anthropic import AnthropicProvider
from app.providers.base import ChatMessage, ChatProvider, ChatRole, ProviderUnavailableError
from app.providers.budget import LLMCallBudget, LLMCallBudgetExceededError, TokenBucket
from app.providers.gemini import GeminiProvider
from app.providers.health import ProviderHealthTracker
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider
from app.providers.openrouter import OpenRouterProvider
from app.providers.registry import (
    NoProviderAvailableError,
    ProviderRegistry,
    build_provider_registry,
)

pytestmark = pytest.mark.unit

_A_MESSAGE = [ChatMessage(role=ChatRole.USER, content="hi")]


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


# ── Gemini ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gemini_provider_streams_text_deltas() -> None:
    body = b"\n".join(
        [
            b'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}}]}',
            b"",
            b'data: {"candidates":[{"content":{"parts":[{"text":" world"}]}}]}',
            b"",
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    provider = GeminiProvider(
        api_keys=["fake-key"], default_model="gemini-2.5-flash-lite", transport=_transport(handler)
    )
    deltas = [d async for d in provider.stream_chat(messages=_A_MESSAGE)]
    assert deltas == ["Hello", " world"]


@pytest.mark.asyncio
async def test_gemini_provider_raises_provider_unavailable_on_http_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"")

    provider = GeminiProvider(
        api_keys=["fake-key"], default_model="m", transport=_transport(handler)
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass


@pytest.mark.asyncio
async def test_gemini_provider_rotates_through_key_pool() -> None:
    seen_keys: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.url.params["key"])
        return httpx.Response(200, content=b"")

    provider = GeminiProvider(
        api_keys=["key1", "key2"], default_model="m", transport=_transport(handler)
    )
    for _ in range(3):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass
    assert seen_keys == ["key1", "key2", "key1"]


def test_gemini_provider_rejects_empty_key_pool() -> None:
    with pytest.raises(ValueError, match="at least one API key"):
        GeminiProvider(api_keys=[], default_model="m")


@pytest.mark.asyncio
async def test_gemini_provider_extracts_system_instruction_separately() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, content=b"")

    provider = GeminiProvider(api_keys=["k"], default_model="m", transport=_transport(handler))
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="Be concise."),
        ChatMessage(role=ChatRole.USER, content="hi"),
    ]
    async for _ in provider.stream_chat(messages=messages):
        pass

    body = json.loads(captured["body"])  # type: ignore[arg-type]
    assert body["systemInstruction"]["parts"][0]["text"] == "Be concise."
    assert all(part["role"] != "system" for part in body["contents"])


# ── Ollama ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ollama_provider_streams_text_deltas() -> None:
    body = b"\n".join(
        [
            b'{"message":{"content":"Hello"},"done":false}',
            b'{"message":{"content":" world"},"done":false}',
            b'{"message":{"content":""},"done":true}',
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    provider = OllamaProvider(
        base_url="http://fake-ollama", default_model="llama3.1", transport=_transport(handler)
    )
    deltas = [d async for d in provider.stream_chat(messages=_A_MESSAGE)]
    assert deltas == ["Hello", " world"]


@pytest.mark.asyncio
async def test_ollama_provider_raises_provider_unavailable_on_connection_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaProvider(
        base_url="http://fake-ollama", default_model="m", transport=_transport(handler)
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass


@pytest.mark.asyncio
async def test_ollama_provider_raises_provider_unavailable_on_http_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"")

    provider = OllamaProvider(
        base_url="http://fake-ollama", default_model="m", transport=_transport(handler)
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass


# ── Anthropic ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_provider_streams_text_deltas() -> None:
    body = b"\n".join(
        [
            b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}',
            b"",
            b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}',
            b"",
            b'data: {"type":"message_stop"}',
            b"",
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    provider = AnthropicProvider(
        api_keys=["fake-key"], default_model="claude-sonnet-5", transport=_transport(handler)
    )
    deltas = [d async for d in provider.stream_chat(messages=_A_MESSAGE)]
    assert deltas == ["Hello", " world"]


@pytest.mark.asyncio
async def test_anthropic_provider_raises_provider_unavailable_on_http_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(529, content=b"")

    provider = AnthropicProvider(
        api_keys=["fake-key"], default_model="m", transport=_transport(handler)
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass


def test_anthropic_provider_rejects_empty_key_pool() -> None:
    with pytest.raises(ValueError, match="at least one API key"):
        AnthropicProvider(api_keys=[], default_model="m")


@pytest.mark.asyncio
async def test_anthropic_provider_sends_system_as_top_level_field() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        captured["headers"] = request.headers
        return httpx.Response(200, content=b"")

    provider = AnthropicProvider(api_keys=["k"], default_model="m", transport=_transport(handler))
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="Be concise."),
        ChatMessage(role=ChatRole.USER, content="hi"),
    ]
    async for _ in provider.stream_chat(messages=messages):
        pass

    body = json.loads(captured["body"])  # type: ignore[arg-type]
    assert body["system"] == "Be concise."
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["max_tokens"] > 0
    headers = captured["headers"]
    assert headers["x-api-key"] == "k"  # type: ignore[index]
    assert headers["anthropic-version"]  # type: ignore[index]


# ── OpenAI / OpenRouter (shared OpenAI-compatible wire format) ────────────


@pytest.mark.parametrize("provider_cls", [OpenAIProvider, OpenRouterProvider])
@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_text_deltas(
    provider_cls: type[OpenAIProvider] | type[OpenRouterProvider],
) -> None:
    body = b"\n".join(
        [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b"",
            b'data: {"choices":[{"delta":{"content":" world"}}]}',
            b"",
            b"data: [DONE]",
            b"",
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    provider = provider_cls(
        api_keys=["fake-key"], default_model="a-model", transport=_transport(handler)
    )
    deltas = [d async for d in provider.stream_chat(messages=_A_MESSAGE)]
    assert deltas == ["Hello", " world"]


@pytest.mark.parametrize("provider_cls", [OpenAIProvider, OpenRouterProvider])
@pytest.mark.asyncio
async def test_openai_compatible_provider_raises_provider_unavailable_on_http_error(
    provider_cls: type[OpenAIProvider] | type[OpenRouterProvider],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"")

    provider = provider_cls(api_keys=["fake-key"], default_model="m", transport=_transport(handler))
    with pytest.raises(ProviderUnavailableError):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass


@pytest.mark.parametrize("provider_cls", [OpenAIProvider, OpenRouterProvider])
def test_openai_compatible_provider_rejects_empty_key_pool(
    provider_cls: type[OpenAIProvider] | type[OpenRouterProvider],
) -> None:
    with pytest.raises(ValueError, match="at least one API key"):
        provider_cls(api_keys=[], default_model="m")


@pytest.mark.asyncio
async def test_openai_compatible_provider_raises_when_no_model_configured() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    provider = OpenAIProvider(api_keys=["k"], default_model=None, transport=_transport(handler))
    with pytest.raises(ProviderUnavailableError, match="no model specified"):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass


@pytest.mark.asyncio
async def test_openai_compatible_provider_rotates_through_key_pool() -> None:
    seen_auth: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers["Authorization"])
        return httpx.Response(200, content=b"")

    provider = OpenAIProvider(
        api_keys=["key1", "key2"], default_model="m", transport=_transport(handler)
    )
    for _ in range(3):
        async for _ in provider.stream_chat(messages=_A_MESSAGE):
            pass
    assert seen_auth == ["Bearer key1", "Bearer key2", "Bearer key1"]


# ── Registry ─────────────────────────────────────────────────────────────


class _FakeProvider(ChatProvider):
    def __init__(
        self,
        name: str,
        deltas: list[str],
        *,
        fail_after_yielding: bool = False,
        always_fail: bool = False,
    ) -> None:
        self.name = name
        self._deltas = deltas
        self._fail_after_yielding = fail_after_yielding
        self._always_fail = always_fail

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        if self._always_fail:
            raise ProviderUnavailableError(f"{self.name} down")
        for delta in self._deltas:
            yield delta
        if self._fail_after_yielding:
            raise ProviderUnavailableError(f"{self.name} dropped mid-stream")


@pytest.mark.asyncio
async def test_registry_uses_first_provider_in_priority_order() -> None:
    registry = ProviderRegistry(
        {"a": _FakeProvider("a", ["x"]), "b": _FakeProvider("b", ["y"])}, ["a", "b"]
    )
    results = [r async for r in registry.stream_chat(messages=_A_MESSAGE)]
    assert results == [("a", "x")]


@pytest.mark.asyncio
async def test_registry_fails_over_before_any_delta_is_yielded() -> None:
    registry = ProviderRegistry(
        {"a": _FakeProvider("a", [], always_fail=True), "b": _FakeProvider("b", ["y"])},
        ["a", "b"],
    )
    results = [r async for r in registry.stream_chat(messages=_A_MESSAGE)]
    assert results == [("b", "y")]


@pytest.mark.asyncio
async def test_registry_does_not_fail_over_after_partial_output() -> None:
    """A mid-stream failure must not splice in a different provider's
    continuation — that would garble the response (see registry.py)."""
    registry = ProviderRegistry(
        {
            "a": _FakeProvider("a", ["partial"], fail_after_yielding=True),
            "b": _FakeProvider("b", ["y"]),
        },
        ["a", "b"],
    )
    collected: list[tuple[str, str]] = []
    with pytest.raises(ProviderUnavailableError):
        async for item in registry.stream_chat(messages=_A_MESSAGE):
            collected.append(item)
    assert collected == [("a", "partial")]


@pytest.mark.asyncio
async def test_registry_raises_no_provider_available_when_all_fail() -> None:
    registry = ProviderRegistry({"a": _FakeProvider("a", [], always_fail=True)}, ["a"])
    with pytest.raises(NoProviderAvailableError):
        async for _ in registry.stream_chat(messages=_A_MESSAGE):
            pass


@pytest.mark.asyncio
async def test_registry_appends_unlisted_providers_after_priority_order() -> None:
    # "c" isn't in the priority list at all; it should still get a turn once
    # both explicitly-ordered providers ("b" then "a", per priority) fail.
    registry = ProviderRegistry(
        {
            "a": _FakeProvider("a", [], always_fail=True),
            "b": _FakeProvider("b", [], always_fail=True),
            "c": _FakeProvider("c", ["z"]),
        },
        ["b", "a"],
    )
    results = [r async for r in registry.stream_chat(messages=_A_MESSAGE)]
    assert results == [("c", "z")]


# ── Registry x health / budget / rate-limit integration ────────────────────


@pytest.mark.asyncio
async def test_registry_skips_a_provider_whose_circuit_is_open() -> None:
    health = ProviderHealthTracker(failure_threshold=1)
    health.record_failure("a")  # opens "a"'s circuit before any call is made
    registry = ProviderRegistry(
        {"a": _FakeProvider("a", ["x"]), "b": _FakeProvider("b", ["y"])},
        ["a", "b"],
        health=health,
    )
    results = [r async for r in registry.stream_chat(messages=_A_MESSAGE)]
    assert results == [("b", "y")]


@pytest.mark.asyncio
async def test_registry_records_failure_against_health_tracker() -> None:
    health = ProviderHealthTracker(failure_threshold=2)
    registry = ProviderRegistry(
        {"a": _FakeProvider("a", [], always_fail=True), "b": _FakeProvider("b", ["y"])},
        ["a", "b"],
        health=health,
    )
    async for _ in registry.stream_chat(messages=_A_MESSAGE):
        pass
    assert health.snapshot()["a"]["consecutive_failures"] == 1


@pytest.mark.asyncio
async def test_registry_records_success_against_health_tracker() -> None:
    health = ProviderHealthTracker(failure_threshold=1)
    health.record_failure("a")  # would normally open the circuit...
    health.record_success("a")  # ...but a success clears it again
    registry = ProviderRegistry({"a": _FakeProvider("a", ["x"])}, ["a"], health=health)
    results = [r async for r in registry.stream_chat(messages=_A_MESSAGE)]
    assert results == [("a", "x")]


@pytest.mark.asyncio
async def test_registry_skips_a_provider_whose_token_bucket_is_empty() -> None:
    empty_bucket = TokenBucket(capacity=1, refill_rate_per_second=0)
    empty_bucket.try_consume()  # drain it before the registry ever calls it
    registry = ProviderRegistry(
        {"a": _FakeProvider("a", ["x"]), "b": _FakeProvider("b", ["y"])},
        ["a", "b"],
        token_buckets={"a": empty_bucket},
    )
    results = [r async for r in registry.stream_chat(messages=_A_MESSAGE)]
    assert results == [("b", "y")]


@pytest.mark.asyncio
async def test_registry_consumes_budget_only_for_providers_actually_attempted() -> None:
    health = ProviderHealthTracker(failure_threshold=1)
    health.record_failure("skipped")  # circuit-open: never actually attempted
    registry = ProviderRegistry(
        {"skipped": _FakeProvider("skipped", ["x"]), "b": _FakeProvider("b", ["y"])},
        ["skipped", "b"],
        health=health,
    )
    budget = LLMCallBudget(max_calls=1)
    results = [r async for r in registry.stream_chat(messages=_A_MESSAGE, budget=budget)]
    assert results == [("b", "y")]
    assert budget.calls_made == 1


@pytest.mark.asyncio
async def test_registry_propagates_budget_exceeded_before_trying_a_provider() -> None:
    registry = ProviderRegistry({"a": _FakeProvider("a", ["x"])}, ["a"])
    exhausted_budget = LLMCallBudget(max_calls=0)
    with pytest.raises(LLMCallBudgetExceededError):
        async for _ in registry.stream_chat(messages=_A_MESSAGE, budget=exhausted_budget):
            pass


# ── build_provider_registry / ollama_only (ADR-0024) ──────────────────────


def _settings_with_every_cloud_key_set(**overrides: object) -> Settings:
    return Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        GEMINI_API_KEYS="gemini-key",
        ANTHROPIC_API_KEYS="anthropic-key",
        OPENAI_API_KEYS="openai-key",
        OPENROUTER_API_KEYS="openrouter-key",
        **overrides,  # type: ignore[arg-type]
    )


def test_build_provider_registry_registers_every_configured_cloud_provider() -> None:
    registry = build_provider_registry(_settings_with_every_cloud_key_set())
    assert set(registry.registered_provider_names) == {
        "gemini",
        "anthropic",
        "openai",
        "openrouter",
        "ollama",
    }


def test_build_provider_registry_in_ollama_only_mode_ignores_configured_cloud_keys() -> None:
    # ollama_only is a stronger guarantee than leaving keys blank: even with
    # every cloud key set, none of them is registered (ADR-0024).
    settings = _settings_with_every_cloud_key_set(DEPLOYMENT_MODE="ollama_only")
    registry = build_provider_registry(settings)
    assert registry.registered_provider_names == ["ollama"]
