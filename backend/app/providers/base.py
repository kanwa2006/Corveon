"""Provider-agnostic chat-completion contract (ADR-0006). The orchestrator
depends only on this module's types and the registry — never a concrete
provider name (CLAUDE.md §5)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str


class ProviderUnavailableError(Exception):
    """Raised by a provider adapter when it cannot serve a request right now
    (unreachable, rate-limited, non-2xx). Caught by ProviderRegistry to try
    the next provider in priority order (ADR-0006) — absence/failure of one
    provider is never surfaced to the caller as an error by itself."""


class ChatProvider(ABC):
    name: str

    @abstractmethod
    def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        """Yield response text deltas for the given conversation. Raises
        ProviderUnavailableError (not a bare exception) on any failure so the
        registry can fail over deterministically."""
        raise NotImplementedError
