"""Shared helper for parsing JSON out of an LLM's text response — mirrors
app/evidence/_llm_json.py's identical, tiny helper; duplicated rather than
imported cross-domain so app/medication has no dependency on app/evidence's
internals."""

from __future__ import annotations

import re

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def strip_code_fences(raw: str) -> str:
    return _CODE_FENCE_RE.sub("", raw).strip()
