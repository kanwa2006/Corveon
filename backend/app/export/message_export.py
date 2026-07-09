"""Message export — Markdown (lossless UTF-8) and PDF renderers for a single
message, preserving its citations and routing metadata (docs/API.md — Export;
CLAUDE.md Month 1 roadmap). Synchronous: a single message renders in
milliseconds, well under what would justify an ARQ job — docs/API.md
documents this endpoint as returning `200` file, not `202` + job, confirming
synchronous intent.

PDF uses fpdf2's core Helvetica font, which only covers Latin-1. Rather than
ship a bundled Unicode TTF (a new binary repo asset) or silently mangle
out-of-range characters into something that reads as valid-but-wrong — a real
concern for clinical text — a small transliteration table (micro sign,
degree, plus-minus, en/em dash, smart quotes, ellipsis) covers the common
cases and anything else becomes a visible ``[?]`` placeholder. Markdown
export has no such limitation (raw UTF-8) and is the fully-faithful format;
PDF is the "premium readable rendering" with that one explicit, documented
trade-off.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fpdf import FPDF, XPos, YPos

from app.data.models.message import Message, MessageRole

# Keyed by unicode escape (not the literal glyph) so this reads unambiguously
# in any editor/diff — see the module docstring for why this table exists.
_TRANSLITERATIONS = {
    "µ": "mc",  # micro sign, as in "mcg"
    "°": "deg",  # degree sign
    "±": "+/-",  # plus-minus
    "–": "-",  # en dash  # noqa: RUF001
    "—": "--",  # em dash
    "‘": "'",  # left single quote  # noqa: RUF001
    "’": "'",  # right single quote  # noqa: RUF001
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "…": "...",  # ellipsis
}


class ExportFormat(StrEnum):
    MARKDOWN = "md"
    PDF = "pdf"


def _role_label(role: MessageRole) -> str:
    return "Assistant" if role == MessageRole.ASSISTANT else "User"


def _citations(routing_trace: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not routing_trace:
        return []
    chunks = routing_trace.get("retrieved_chunks")
    return chunks if isinstance(chunks, list) else []


def _citation_line(citation: dict[str, Any]) -> str:
    filename = citation.get("document_filename", "document")
    ordinal = citation.get("ordinal")
    similarity = citation.get("similarity")
    excerpt = f"excerpt {ordinal + 1}" if isinstance(ordinal, int) else "excerpt"
    score = f" (similarity {similarity:.2f})" if isinstance(similarity, int | float) else ""
    return f"{filename}, {excerpt}{score}"


def _trace_metadata(routing_trace: dict[str, Any] | None) -> str:
    trace = routing_trace or {}
    keys = ("path", "provider", "status")
    return ", ".join(f"{key}: {trace[key]}" for key in keys if trace.get(key))


def render_markdown(*, chat_title: str, message: Message) -> bytes:
    timestamp = message.created_at.isoformat()
    lines = [
        f"# {chat_title}",
        "",
        f"**{_role_label(message.role)}** · {timestamp}",
    ]

    metadata = _trace_metadata(message.routing_trace)
    if metadata:
        lines.append(f"*{metadata}*")

    lines.extend(["", message.content])

    citations = _citations(message.routing_trace)
    if citations:
        lines.extend(["", "## Sources"])
        lines.extend(f"- {_citation_line(c)}" for c in citations)

    return ("\n".join(lines) + "\n").encode("utf-8")


def _pdf_safe_text(text: str) -> str:
    for source, replacement in _TRANSLITERATIONS.items():
        text = text.replace(source, replacement)
    return "".join(char if ord(char) < 256 else "[?]" for char in text)


def _write_paragraph(pdf: FPDF, height: float, text: str) -> None:
    # fpdf2's multi_cell leaves the cursor at the end of the last line by
    # default (near the right margin), not back at the left margin — the
    # *next* multi_cell call then computes almost zero available width and
    # raises FPDFException. Every call in this module must reset explicitly.
    pdf.multi_cell(0, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def render_pdf(*, chat_title: str, message: Message) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("helvetica", "B", 16)
    _write_paragraph(pdf, 10, _pdf_safe_text(chat_title))

    meta_line = f"{_role_label(message.role)} - {message.created_at.isoformat()}"
    metadata = _trace_metadata(message.routing_trace)
    if metadata:
        meta_line += f" ({metadata})"
    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    _write_paragraph(pdf, 6, _pdf_safe_text(meta_line))
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("helvetica", size=11)
    _write_paragraph(pdf, 6, _pdf_safe_text(message.content))

    citations = _citations(message.routing_trace)
    if citations:
        pdf.ln(6)
        pdf.set_font("helvetica", "B", 12)
        _write_paragraph(pdf, 8, "Sources")
        pdf.set_font("helvetica", size=10)
        for citation in citations:
            _write_paragraph(pdf, 6, _pdf_safe_text(f"- {_citation_line(citation)}"))

    return bytes(pdf.output())


def render(
    *, export_format: ExportFormat, chat_title: str, message: Message
) -> tuple[bytes, str, str]:
    """Returns ``(file_bytes, media_type, filename)``."""
    if export_format == ExportFormat.MARKDOWN:
        data = render_markdown(chat_title=chat_title, message=message)
        return data, "text/markdown", f"{message.id}.md"
    data = render_pdf(chat_title=chat_title, message=message)
    return data, "application/pdf", f"{message.id}.pdf"
