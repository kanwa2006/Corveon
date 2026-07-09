"""Unit tests for message export rendering (app/export/message_export.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.data.models.message import Message, MessageRole
from app.export.message_export import ExportFormat, render, render_markdown, render_pdf

pytestmark = pytest.mark.unit


def _message(
    *, role: MessageRole = MessageRole.ASSISTANT, routing_trace: dict | None = None
) -> Message:
    message = Message(
        chat_id=uuid.uuid4(),
        role=role,
        content="Metformin is a first-line treatment for type 2 diabetes.",
        routing_trace=routing_trace,
    )
    message.id = uuid.uuid4()
    message.created_at = datetime(2026, 7, 8, 12, 0, 0, tzinfo=UTC)
    return message


_TRACE_WITH_CITATION = {
    "path": "rag_grounded",
    "provider": "gemini",
    "status": "ok",
    "retrieved_chunks": [
        {
            "document_filename": "guideline.pdf",
            "ordinal": 2,
            "similarity": 0.874,
        }
    ],
}


def test_render_markdown_includes_title_role_and_content() -> None:
    data = render_markdown(chat_title="Renal Dosing", message=_message())
    text = data.decode("utf-8")
    assert "# Renal Dosing" in text
    assert "**Assistant**" in text
    assert "Metformin is a first-line treatment for type 2 diabetes." in text


def test_render_markdown_includes_routing_metadata_and_citations() -> None:
    data = render_markdown(chat_title="Chat", message=_message(routing_trace=_TRACE_WITH_CITATION))
    text = data.decode("utf-8")
    assert "path: rag_grounded" in text
    assert "provider: gemini" in text
    assert "## Sources" in text
    assert "guideline.pdf, excerpt 3 (similarity 0.87)" in text


def test_render_markdown_omits_sources_section_when_no_citations() -> None:
    data = render_markdown(chat_title="Chat", message=_message())
    assert "## Sources" not in data.decode("utf-8")


def test_render_pdf_produces_a_valid_pdf() -> None:
    message = _message(routing_trace=_TRACE_WITH_CITATION)
    data = render_pdf(chat_title="Renal Dosing", message=message)
    assert data.startswith(b"%PDF-")
    assert len(data) > 200


def test_render_pdf_transliterates_out_of_range_unicode() -> None:
    message = _message()
    message.content = "Dose: 5µg ± 1°C — do not exceed."
    data = render_pdf(chat_title="Chat", message=message)
    assert data.startswith(b"%PDF-")  # doesn't raise despite non-Latin-1 input


def test_render_dispatches_markdown_and_pdf() -> None:
    md_bytes, md_type, md_name = render(
        export_format=ExportFormat.MARKDOWN, chat_title="Chat", message=_message()
    )
    assert md_type == "text/markdown"
    assert md_name.endswith(".md")
    assert md_bytes.startswith(b"# Chat")

    pdf_bytes, pdf_type, pdf_name = render(
        export_format=ExportFormat.PDF, chat_title="Chat", message=_message()
    )
    assert pdf_type == "application/pdf"
    assert pdf_name.endswith(".pdf")
    assert pdf_bytes.startswith(b"%PDF-")
