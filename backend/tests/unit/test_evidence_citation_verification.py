"""Unit tests for the citation-resolution structural check
(app/evidence/citation_verification.py)."""

from __future__ import annotations

from datetime import date

import pytest
from app.data.models.evidence import EvidenceSourceName
from app.evidence.citation_verification import is_citation_resolved
from app.evidence.connectors.base import EvidenceResult

pytestmark = pytest.mark.unit


def _result(**overrides: object) -> EvidenceResult:
    defaults: dict[str, object] = {
        "source": EvidenceSourceName.PUBMED,
        "title": "A study",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "identifier": "12345678",
        "snippet": None,
        "published_date": date(2023, 1, 1),
    }
    defaults.update(overrides)
    return EvidenceResult(**defaults)  # type: ignore[arg-type]


def test_citation_with_identifier_and_url_is_resolved() -> None:
    assert is_citation_resolved(_result()) is True


def test_citation_missing_identifier_is_not_resolved() -> None:
    assert is_citation_resolved(_result(identifier=None)) is False


def test_citation_missing_url_is_not_resolved() -> None:
    assert is_citation_resolved(_result(url=None)) is False


def test_citation_missing_both_is_not_resolved() -> None:
    assert is_citation_resolved(_result(identifier=None, url=None)) is False


def test_uploaded_document_citation_with_identifier_but_no_url_is_resolved() -> None:
    result = _result(
        source=EvidenceSourceName.UPLOADED_DOCUMENT, url=None, identifier="chunk-id-123"
    )
    assert is_citation_resolved(result) is True


def test_uploaded_document_citation_missing_identifier_is_not_resolved() -> None:
    result = _result(source=EvidenceSourceName.UPLOADED_DOCUMENT, url=None, identifier=None)
    assert is_citation_resolved(result) is False
