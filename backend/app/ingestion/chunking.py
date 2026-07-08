"""Paragraph-aware chunking (docs/ARCHITECTURE.md §3, §9). Token counts are an
approximation (~4 chars/token, the common English-text heuristic) used only
for bookkeeping/telemetry — never a clinical claim."""

from __future__ import annotations

from dataclasses import dataclass

MAX_CHUNK_CHARS = 1000
OVERLAP_CHARS = 150
_CHARS_PER_TOKEN_ESTIMATE = 4


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    text: str
    token_count: int


def estimate_token_count(text: str) -> int:
    return max(1, round(len(text) / _CHARS_PER_TOKEN_ESTIMATE))


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def chunk_pages(
    pages: list[str],
    *,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[Chunk]:
    """Greedily packs blank-line-separated paragraphs into ~max_chars windows,
    carrying a small trailing overlap into the next chunk so a fact split
    across a boundary still has surrounding context on both sides. A single
    paragraph longer than max_chars is hard-split (no overlap) as a fallback."""
    paragraphs = [p.strip() for page in pages for p in page.split("\n\n") if p.strip()]

    texts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                texts.append(current)
                current = ""
            texts.extend(_hard_split(paragraph, max_chars))
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars and current:
            texts.append(current)
            overlap = current[-overlap_chars:] if overlap_chars else ""
            current = f"{overlap}\n\n{paragraph}" if overlap else paragraph
        else:
            current = candidate

    if current.strip():
        texts.append(current)

    return [
        Chunk(ordinal=i, text=text.strip(), token_count=estimate_token_count(text))
        for i, text in enumerate(texts)
    ]
