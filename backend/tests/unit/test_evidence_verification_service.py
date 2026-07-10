"""Unit tests for the Evidence Verification pipeline
(app/evidence/verification_service.py), mocking ``ChunkRepository`` and
``EvidenceRepository`` (AsyncMock(spec=...), the same convention
test_chat_orchestrator.py uses for chunk_repo) and driving the LLM seam
through a stub ``ChatProvider`` — no real DB/network/API key required."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.data.models.evidence import (
    EvidenceSourceName,
    SourceClass,
    VerificationStatus,
)
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.repositories.evidence_repository import EvidenceRepository
from app.evidence.connectors.base import EvidenceResult
from app.evidence.registry import EvidenceConnectorRegistry
from app.evidence.verification_service import run_verification
from app.ingestion.embeddings import EmbeddingModel
from app.providers.base import ChatMessage, ChatProvider
from app.providers.budget import LLMCallBudgetExceededError
from app.providers.registry import NoProviderAvailableError, ProviderRegistry

pytestmark = pytest.mark.unit

_CHAT_ID = uuid.uuid4()
_VERIFICATION_ID = uuid.uuid4()


class _ScriptedProvider(ChatProvider):
    """Returns one scripted response per call, in order — the pipeline makes
    exactly one claim-extraction call followed by one analysis call per
    claim, so the script order matches that sequence."""

    name = "stub"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        yield self._responses.pop(0)


def _provider_registry(responses: list[str]) -> ProviderRegistry:
    return ProviderRegistry({"stub": _ScriptedProvider(responses)}, ["stub"])


class _FakeConnector:
    def __init__(self, name: EvidenceSourceName, results: list[EvidenceResult]) -> None:
        self.name = name
        self._results = results

    async def search(self, query: str, *, limit: int = 5) -> list[EvidenceResult]:
        return self._results[:limit]


def _empty_connector_registry() -> EvidenceConnectorRegistry:
    return EvidenceConnectorRegistry(
        {EvidenceSourceName.PUBMED: _FakeConnector(EvidenceSourceName.PUBMED, [])}
    )


def _connector_registry_with(result: EvidenceResult) -> EvidenceConnectorRegistry:
    return EvidenceConnectorRegistry({result.source: _FakeConnector(result.source, [result])})


def _pubmed_result(*, title: str = "A study") -> EvidenceResult:
    return EvidenceResult(
        source=EvidenceSourceName.PUBMED,
        title=title,
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        identifier="12345678",
        snippet="Metformin is first-line therapy for type 2 diabetes.",
        published_date=date(2023, 1, 1),
    )


def _empty_chunk_repo() -> ChunkRepository:
    repo = AsyncMock(spec=ChunkRepository)
    repo.has_ready_chunks.return_value = False
    return repo


def _embedding_model() -> EmbeddingModel:
    model = MagicMock(spec=EmbeddingModel)
    model.model_id = "test-model"
    model.embed_query.return_value = [0.1, 0.2, 0.3]
    return model


def _evidence_repo() -> EvidenceRepository:
    repo = AsyncMock(spec=EvidenceRepository)
    verification = MagicMock(id=_VERIFICATION_ID)
    repo.get_verification_by_id_for_chat.return_value = verification
    repo.create_claim.side_effect = lambda **kwargs: MagicMock(id=uuid.uuid4())
    repo.create_citation.side_effect = lambda **kwargs: MagicMock(id=uuid.uuid4())
    return repo


async def _run(
    *,
    provider_registry: ProviderRegistry,
    connector_registry: EvidenceConnectorRegistry,
    evidence_repo: EvidenceRepository,
    chunk_repo: ChunkRepository | None = None,
    max_llm_calls: int = 10,
) -> list:
    return [
        claim
        async for claim in run_verification(
            chat_id=_CHAT_ID,
            verification_id=_VERIFICATION_ID,
            message_text="Metformin is first-line therapy for type 2 diabetes.",
            provider_registry=provider_registry,
            connector_registry=connector_registry,
            chunk_repo=chunk_repo or _empty_chunk_repo(),
            embedding_model=_embedding_model(),
            evidence_repo=evidence_repo,
            max_llm_calls=max_llm_calls,
        )
    ]


@pytest.mark.asyncio
async def test_run_verification_raises_when_verification_row_is_missing() -> None:
    evidence_repo = AsyncMock(spec=EvidenceRepository)
    evidence_repo.get_verification_by_id_for_chat.return_value = None

    with pytest.raises(ValueError, match="not found for chat"):
        await _run(
            provider_registry=_provider_registry(["[]"]),
            connector_registry=_empty_connector_registry(),
            evidence_repo=evidence_repo,
        )


@pytest.mark.asyncio
async def test_run_verification_yields_no_claims_for_purely_conversational_text() -> None:
    evidence_repo = _evidence_repo()

    claims = await _run(
        provider_registry=_provider_registry(["[]"]),
        connector_registry=_empty_connector_registry(),
        evidence_repo=evidence_repo,
    )

    assert claims == []
    evidence_repo.update_verification_status.assert_awaited_once_with(
        evidence_repo.get_verification_by_id_for_chat.return_value,
        status=VerificationStatus.SUCCEEDED,
    )


@pytest.mark.asyncio
async def test_run_verification_classifies_a_supported_claim_as_verified_public() -> None:
    evidence_repo = _evidence_repo()
    pubmed_result = _pubmed_result()

    claims = await _run(
        provider_registry=_provider_registry(
            [
                '["Metformin is first-line therapy for type 2 diabetes."]',
                '{"stances": ["supports"], "flags": []}',
            ]
        ),
        connector_registry=_connector_registry_with(pubmed_result),
        evidence_repo=evidence_repo,
    )

    assert len(claims) == 1
    claim = claims[0]
    assert claim.source_class == SourceClass.VERIFIED_PUBLIC.value
    assert claim.confidence_score > 0
    assert len(claim.citations) == 1
    assert claim.citations[0].source == EvidenceSourceName.PUBMED
    assert claim.citations[0].supports_claim is True
    evidence_repo.create_claim.assert_awaited_once()
    evidence_repo.create_citation.assert_awaited_once()
    evidence_repo.update_verification_status.assert_awaited_once_with(
        evidence_repo.get_verification_by_id_for_chat.return_value,
        status=VerificationStatus.SUCCEEDED,
    )


@pytest.mark.asyncio
async def test_run_verification_omits_unresolved_citations_from_the_shown_list() -> None:
    evidence_repo = _evidence_repo()
    unresolved = EvidenceResult(
        source=EvidenceSourceName.PUBMED,
        title="A study with no identifier",
        url=None,
        identifier=None,
        snippet="Metformin is first-line therapy.",
        published_date=date(2023, 1, 1),
    )

    claims = await _run(
        provider_registry=_provider_registry(
            [
                '["Metformin is first-line therapy for type 2 diabetes."]',
                '{"stances": ["supports"], "flags": []}',
            ]
        ),
        connector_registry=_connector_registry_with(unresolved),
        evidence_repo=evidence_repo,
    )

    assert claims[0].citations == []
    evidence_repo.create_citation.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_verification_marks_claim_ai_reasoning_when_no_evidence_found() -> None:
    evidence_repo = _evidence_repo()

    claims = await _run(
        provider_registry=_provider_registry(
            [
                '["Metformin is first-line therapy for type 2 diabetes."]',
            ]
        ),
        connector_registry=_empty_connector_registry(),
        evidence_repo=evidence_repo,
    )

    assert len(claims) == 1
    assert claims[0].source_class == SourceClass.AI_REASONING.value
    assert claims[0].citations == []
    assert claims[0].flags[0]["type"] == "unsupported"


@pytest.mark.asyncio
async def test_run_verification_marks_verification_failed_on_no_provider_available() -> None:
    evidence_repo = _evidence_repo()
    empty_registry = ProviderRegistry({}, [])

    with pytest.raises(NoProviderAvailableError):
        await _run(
            provider_registry=empty_registry,
            connector_registry=_empty_connector_registry(),
            evidence_repo=evidence_repo,
        )

    evidence_repo.update_verification_status.assert_awaited_once()
    _, kwargs = evidence_repo.update_verification_status.await_args
    assert kwargs["status"] == VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_run_verification_marks_verification_failed_when_budget_exhausted_mid_claim() -> None:
    evidence_repo = _evidence_repo()

    with pytest.raises(LLMCallBudgetExceededError):
        await _run(
            provider_registry=_provider_registry(['["A claim.", "Another claim."]']),
            connector_registry=_connector_registry_with(_pubmed_result()),
            evidence_repo=evidence_repo,
            max_llm_calls=1,
        )

    evidence_repo.update_verification_status.assert_awaited_once()
    _, kwargs = evidence_repo.update_verification_status.await_args
    assert kwargs["status"] == VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_run_verification_includes_uploaded_document_evidence() -> None:
    evidence_repo = _evidence_repo()
    chunk_repo = AsyncMock(spec=ChunkRepository)
    chunk_repo.has_ready_chunks.return_value = True

    chunk = MagicMock(id=uuid.uuid4(), text="Metformin is first-line therapy for type 2 diabetes.")
    document = MagicMock(filename="doc.pdf")
    chunk_repo.similarity_search.return_value = [(chunk, document, 0.1)]  # similarity 0.9

    claims = await _run(
        provider_registry=_provider_registry(
            [
                '["Metformin is first-line therapy for type 2 diabetes."]',
                '{"stances": ["supports"], "flags": []}',
            ]
        ),
        connector_registry=_empty_connector_registry(),
        evidence_repo=evidence_repo,
        chunk_repo=chunk_repo,
    )

    assert len(claims) == 1
    assert claims[0].source_class == SourceClass.UPLOADED_DOCUMENT.value
    assert len(claims[0].citations) == 1
    assert claims[0].citations[0].source == EvidenceSourceName.UPLOADED_DOCUMENT
    assert claims[0].citations[0].url is None
