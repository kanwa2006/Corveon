"""Evidence Verification Engine (§8) — the flagship differentiator.

Pipeline: ingest/parse -> claim extraction -> source-class tagging -> external
evidence retrieval (openFDA, DailyMed, RxNav, PubMed/PMC, ClinicalTrials.gov,
MeSH; cache-first) -> contradiction/outdatedness/fabrication detection ->
transparent confidence scoring -> conflict handling -> provenance-annotated
output. Never assumes an uploaded document is correct; never answers confidently
on suspected misinformation. Org-trusted corpora plug in via a versioned,
access-scoped ``trusted_source`` provider interface.
"""
