"""Unit tests for the provider-agnostic AI layer (app/providers/). Gemini and
Ollama adapters are tested against httpx.MockTransport — no real network
calls or API keys required (ADR-0006: "testable with fakes")."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from app.providers.base import ChatMessage, ChatProvider, ChatRole, ProviderUnavailableError
from app.providers.gemini import GeminiProvider
from app.providers.ollama import OllamaProvider
from app.providers.registry import NoProviderAvailableError, ProviderRegistry

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
