"""Unit tests for PDF parsing (app/ingestion/parsing.py). Test PDFs are
generated in-memory with PyMuPDF itself rather than checked-in binary
fixtures — genuinely parseable, no fixture-drift risk."""

from __future__ import annotations

import fitz
import pytest
from app.ingestion.parsing import (
    MAX_PAGE_COUNT,
    DocumentParseError,
    DocumentTooLargeError,
    parse_pdf,
)

pytestmark = pytest.mark.unit


def _make_pdf(page_texts: list[str], *, encrypt: bool = False) -> bytes:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data: bytes = (
        doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner-secret",
            user_pw="user-secret",  # a user password is what actually gates opening the file
        )
        if encrypt
        else doc.tobytes()
    )
    doc.close()
    return data


def test_parse_pdf_extracts_text_and_page_count() -> None:
    pdf_bytes = _make_pdf(["First page text.", "Second page text."])
    parsed = parse_pdf(pdf_bytes)
    assert parsed.page_count == 2
    assert "First page text." in parsed.pages[0]
    assert "Second page text." in parsed.pages[1]


def test_parse_pdf_rejects_non_pdf_bytes() -> None:
    with pytest.raises(DocumentParseError):
        parse_pdf(b"this is not a pdf at all")


def test_parse_pdf_rejects_encrypted_pdf() -> None:
    encrypted = _make_pdf(["secret"], encrypt=True)
    with pytest.raises(DocumentParseError, match="password-protected"):
        parse_pdf(encrypted)


def test_parse_pdf_rejects_documents_over_page_cap() -> None:
    pdf_bytes = _make_pdf(["page"] * (MAX_PAGE_COUNT + 1))
    with pytest.raises(DocumentTooLargeError):
        parse_pdf(pdf_bytes)
