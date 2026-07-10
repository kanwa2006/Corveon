"""Citation verification — the fabricated-citation guard (blueprint §8,
CLAUDE.md golden rule #2: "A citation must resolve to a real source ...
or it is flagged, not shown").

This codebase structurally prevents the failure blueprint describes
(an LLM inventing a plausible-looking PMID or URL): every ``EvidenceResult``
a claim can cite comes directly from a connector's parsed API response
(app/evidence/connectors/) — claim extraction and claim analysis
(app/evidence/claim_extraction.py, app/evidence/analysis.py) only ever
*select among* citations already fetched from a real source; neither one
generates new citation text. There is no code path where the LLM invents a
citation.

What this module actually verifies is narrower but real: that a connector's
parsed result is *structurally complete* enough to show a user — has both
an identifier and a URL a human could follow to check it themselves. A
connector bug (a malformed API response parsed into a title-only stub) is
still possible; this is what would catch it, and CLAUDE.md's rule applies
uniformly regardless of cause: incomplete citations are flagged, not
shown."""

from __future__ import annotations

from app.evidence.connectors.base import EvidenceResult


def is_citation_resolved(result: EvidenceResult) -> bool:
    return bool(result.identifier) and bool(result.url)
