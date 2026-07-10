"""Shared helper for parsing JSON out of an LLM's text response — used by
both claim_extraction.py and analysis.py, which each make one LLM call
expected to return a bare JSON value and need the same tolerance for a
model wrapping it in a markdown code fence anyway."""

from __future__ import annotations

import re

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def strip_code_fences(raw: str) -> str:
    return _CODE_FENCE_RE.sub("", raw).strip()
