"""Unit tests for shared input-validation helpers (app/core/validation.py)."""

from __future__ import annotations

import pytest
from app.core.validation import reject_nul_bytes

pytestmark = pytest.mark.unit


def test_reject_nul_bytes_passes_through_a_clean_string() -> None:
    assert reject_nul_bytes("clean value") == "clean value"


def test_reject_nul_bytes_passes_through_none() -> None:
    assert reject_nul_bytes(None) is None


def test_reject_nul_bytes_raises_on_embedded_nul() -> None:
    with pytest.raises(ValueError, match="NUL bytes"):
        reject_nul_bytes("bad\x00value")
