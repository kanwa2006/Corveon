"""Medication-Safety Engine (§9) — deterministic core; rules are source of truth.

RxNorm/RxNav normalization to RxCUI (fuzzy/typo-tolerant); drug-drug interactions
from DDInter 2.0 (pinned snapshot) with openFDA label-derived fallback (ADR-0004);
renal/dose checks via BOTH Cockcroft-Gault CrCl and 2021 race-free CKD-EPI eGFR,
flagging divergence at critical thresholds (ADR-0005); Beers 2023 + STOPP/START v3
potentially-inappropriate-prescribing screens; medication-discrepancy diff.

The LLM only parses messy input into structured entries and explains rule outputs;
a post-generation guardrail strips any drug fact/severity/recommendation absent
from the structured rule output.
"""
