"""PDF parsing (docs/ARCHITECTURE.md §3, §9). Text-based extraction via
PyMuPDF. OCR for scanned pages is out of scope for this slice — Month 1
roadmap item ("Multi-format ingestion ... + OCR"); a page with no
extractable text yields an empty string here, not an error."""

from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF

# PDF-bomb defense (docs/SECURITY.md: "image/PDF-bomb limits"). A legitimate
# clinical document is not thousands of pages; this bounds worst-case parse
# time/memory for a maliciously crafted upload.
MAX_PAGE_COUNT = 500


class DocumentParseError(Exception):
    """The file could not be parsed as a PDF (corrupt/encrypted/not a PDF)."""


class DocumentTooLargeError(Exception):
    """The PDF exceeds MAX_PAGE_COUNT — a PDF-bomb defense."""


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    page_count: int
    pages: list[str]


def parse_pdf(data: bytes) -> ParsedDocument:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF's own error types vary by failure mode
        raise DocumentParseError(f"Could not open PDF: {exc}") from exc

    try:
        if doc.is_encrypted:
            raise DocumentParseError("PDF is password-protected.")
        if doc.page_count > MAX_PAGE_COUNT:
            raise DocumentTooLargeError(
                f"PDF has {doc.page_count} pages, exceeding the {MAX_PAGE_COUNT}-page limit."
            )
        pages = [page.get_text() for page in doc]
        return ParsedDocument(page_count=doc.page_count, pages=pages)
    finally:
        doc.close()
