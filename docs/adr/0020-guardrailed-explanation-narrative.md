# ADR-0020: Guardrailed LLM explanation narrative (PIP + discrepancy findings only)

- **Status:** Accepted
- **Date:** 2026-07-11

## Context
Blueprint §9: "the LLM only (i) parses messy input text into structured medication entries and
(ii) writes explanations grounded strictly in rule outputs, with guardrails against adding facts...
a post-generation check verifies the narrative introduces no drug facts, severities, or
recommendations absent from the rule output; anything ungrounded is stripped and flagged." Phase 1
and 2's `explanation` fields (DDI, renal) are already deterministic strings — DDInter's own
description, or an f-string built from computed CrCl/eGFR values — with no LLM in the loop at all,
so they are grounded by construction and carry no fabrication risk to guard against.

Beers/STOPP/START rationale text (`pip_criteria.rationale`) and the discrepancy diff are also
already deterministic and shown as-is via the existing `explanation` field, unchanged. What's new
in Phase 3 is an optional plain-language rendering on top — and that is exactly where an LLM
narrative could introduce an ungrounded fact, which is what the guardrail specified in the
blueprint exists to catch.

## Decision

**Scope the guardrailed narrative to PIP and discrepancy findings only, additive to `explanation`.**
Every finding keeps its deterministic `explanation` field untouched — that remains the source of
truth shown by default. A new, nullable `narrative` field is added to `PipFindingEvent` and
`DiscrepancyFindingEvent` only. Retrofitting it onto Phase 1/2's interaction/renal findings was
considered and rejected: those explanations have no LLM-introduced risk to mitigate, and doing so
would force every already-shipped, already-CI-green Phase 1/2 test to be rewritten for zero safety
benefit — the opposite of "never rewrite already-working code."

**One batched call, not one per finding.** After PIP + discrepancy findings are computed for a
request, `app/medication/explanation_guardrail.py` makes at most one additional LLM call: given the
full list of findings' structured rule-output objects (drug names, severity, rule_id, rationale/
recommendation, provenance) as JSON, the model returns a same-length, same-order JSON array of
one-to-two-sentence narratives. This bounds LLM calls per request (parse + optional previous-list
parse + one narrate call) regardless of how many findings exist, consistent with the existing
`LLMCallBudget`.

**The grounding check is deterministic, not a second LLM call.** For each returned narrative,
`check_narrative_grounded()` verifies, against that finding's own rule-output object plus the full
set of medication names known to this analysis (the only vocabulary the narrative is allowed to
reference):
1. No medication name appears in the narrative other than ones belonging to this finding.
2. No number appears in the narrative that isn't present (as a string) somewhere in the finding's
   own rule-output values.
3. No severity word (major/moderate/minor/severe/critical/life-threatening/etc.) appears unless it
   matches the finding's actual severity.
4. No clinical-directive phrase (stop/start/increase/decrease/double/switch, etc.) appears unless
   that exact phrase already occurs in the finding's own `explanation`/`recommendation` text.
A narrative failing any check is discarded (`narrative = null`); the deterministic `explanation` is
still shown. Failure is a normal, expected outcome (not an error) — the request never fails because
a narrative was rejected.

**Degrades silently when no provider is available or the budget is exhausted.** Unlike the parsing
call (whose failure means "no medications at all," and properly propagates as `provider_unavailable`
per ADR-0006), a failed narrate call only means "no prose gloss this time" — the deterministic
findings, which are the actual safety data, are already computed and persisted. `NoProviderAvailable
Error` / `LLMCallBudgetExceededError` are caught locally around the narrate step only.

## Consequences
- Zero behavioral change to Phase 1/2 request/response shapes or tests.
- The grounding check's drug-name-vocabulary approach only catches cross-attribution to a *known*
  drug (one already present in this analysis); a wholly invented drug name not in that vocabulary
  would not be caught by check (1) alone — checks (2)-(4) still catch the more common failure modes
  (invented numbers, upgraded severity, invented directives). Documented limitation, not a silent
  gap.

## Alternatives considered
- **LLM self-critique (ask the same/another call to verify its own narrative):** non-deterministic,
  not golden-testable, and still trusts an LLM to police an LLM — rejected in favor of a rule-based
  checker whose behavior is exhaustively unit-testable.
- **Apply the guardrail to all four finding types:** rejected per above — no benefit for
  already-deterministic explanations, large unnecessary blast radius on shipped tests.
