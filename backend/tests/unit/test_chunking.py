"""Unit tests for paragraph-aware chunking (app/ingestion/chunking.py)."""

from __future__ import annotations

import pytest
from app.ingestion.chunking import chunk_pages, estimate_token_count

pytestmark = pytest.mark.unit


def test_estimate_token_count_uses_chars_per_token_heuristic() -> None:
    assert estimate_token_count("a" * 40) == 10
    assert estimate_token_count("") == 1  # never zero — an empty chunk shouldn't happen anyway
    assert estimate_token_count("hi") == 1  # rounds up to a floor of 1


def test_chunk_pages_single_short_paragraph_is_one_chunk() -> None:
    chunks = chunk_pages(["A single short paragraph."])
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].text == "A single short paragraph."
    assert chunks[0].token_count > 0


def test_chunk_pages_packs_multiple_paragraphs_until_max_chars() -> None:
    paragraphs = "\n\n".join(["word " * 20 for _ in range(5)])
    chunks = chunk_pages([paragraphs], max_chars=200, overlap_chars=20)
    assert len(chunks) > 1
    for chunk in chunks:
        # Individual paragraphs here are ~100 chars, so a packed chunk can
        # exceed max_chars by at most one paragraph's worth before splitting.
        assert len(chunk.text) <= 200 + 120


def test_chunk_pages_carries_overlap_into_next_chunk() -> None:
    para_a = "Alpha " * 30
    para_b = "Beta " * 30
    chunks = chunk_pages([f"{para_a}\n\n{para_b}"], max_chars=100, overlap_chars=30)
    assert len(chunks) >= 2
    # The tail of chunk 0 should reappear at the head of chunk 1.
    overlap_fragment = chunks[0].text[-30:]
    assert overlap_fragment in chunks[1].text


def test_chunk_pages_hard_splits_a_single_oversized_paragraph() -> None:
    huge_paragraph = "x" * 2500  # one paragraph, no blank lines at all
    chunks = chunk_pages([huge_paragraph], max_chars=1000, overlap_chars=100)
    assert len(chunks) == 3
    assert "".join(c.text for c in chunks) == huge_paragraph
    assert [c.ordinal for c in chunks] == [0, 1, 2]


def test_chunk_pages_skips_blank_pages() -> None:
    chunks = chunk_pages(["", "   ", "Real content."])
    assert len(chunks) == 1
    assert chunks[0].text == "Real content."


def test_chunk_pages_empty_input_yields_no_chunks() -> None:
    assert chunk_pages([]) == []
    assert chunk_pages(["", ""]) == []
