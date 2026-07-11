# ADR-0019: PIP criteria (Beers 2023 + STOPP/START v3) encoding and discrepancy classification

- **Status:** Accepted
- **Date:** 2026-07-11

## Context
Medication-Safety Engine Phase 3 adds potentially-inappropriate-prescribing (PIP) screening for
older adults — AGS Beers Criteria 2023 and STOPP/START v3 (190 validated criteria: 133 STOPP +
57 START) — plus medication-discrepancy classification across two lists (blueprint §9). Both must
stay deterministic (CLAUDE.md §6: "the rules engine is the source of truth") and reuse the Phase 1
snapshot/finding infrastructure rather than introducing a parallel system.

## Decision

**PIP criteria as pinned, checksummed rows, not a bespoke format.** A new `pip_criteria` table
(FK to the existing `drug_data_snapshots`, same reproducibility/audit story as `drug_interactions`)
stores one row per criterion: `source` (`beers_2023` | `stopp_v3` | `start_v3`), `criterion_id`,
`drug_names` (JSONB list, normalized lowercase), `condition_keywords` (JSONB list, empty =
unconditional), `direction` (`avoid` | `start_consider`), `rationale`, `recommendation`,
`severity`. One loader module (`app/medication/pip_loader.py`) imports either dataset from a CSV in
the same shape `ddinter_loader.py` already established (ADR-0018) — checksum-verified, never
fetched at request time, never bundled (the real Beers 2023 and STOPP/START v3 tables are
copyrighted works of AGS / the STOPP/START authors respectively).

**Matching is a age-gated deterministic scan, not a second rules DSL.** `app/medication/
pip_screening.py` applies every criterion with `direction=avoid` (Beers' mostly-unconditional
"avoid in older adults" entries and STOPP's condition-gated ones) against the patient's current
medication list: a criterion fires when the patient is ≥65 **and** takes a listed drug **and**
(the criterion is unconditional **or** a supplied free-text condition matches a `condition_keyword`
by case-insensitive substring containment). `direction=start_consider` (START) entries invert the
check: fires when the patient is ≥65, a condition matches, and **none** of the criterion's
`drug_names` appear anywhere in the current list — an omission finding, not a drug-linked one.

**Omission findings need a nullable finding-medication link.** `medication_findings.medication_a_id`
was `NOT NULL` (Phase 1's docstring: "always populated") because every finding to date was anchored
to a specific medication row. A START finding has no such row — it flags an absence. Migration 0008
drops the `NOT NULL` constraint rather than inventing a sentinel medication or a parallel table;
`medication_b_id` was already nullable for exactly this asymmetry.

**Discrepancy classification reuses the same finding table and the same normalizer, twice.**
`app/medication/discrepancy.py` takes two already-normalized medication lists (`previous`,
`current`) and produces a deterministic RxCUI-first, name-fallback diff: `added` (in current, no
match in previous), `omitted` (in previous, no match in current), `dose_changed` /
`frequency_changed` (matched pair, differing field). `medication_a_id` is always the current-list
row when one exists (added/dose/frequency), else the previous-list row (omitted); `medication_b_id`
is the matched previous-list row for dose/frequency changes, else null — the same "primary +
optional secondary" shape Phase 1's interaction findings already use.

## Consequences
- No new tables beyond `pip_criteria`; `medication_findings`, `drug_data_snapshots`, and the
  existing repository/service/router streaming shape are reused unchanged in kind (widened, not
  redesigned).
- `condition_keywords` substring matching is intentionally simple (no clinical-terminology
  ontology/ICD-10 mapping in this phase) — a user-supplied condition string like "heart failure"
  must lexically resemble the criterion's own keyword. Documented as a known precision limit, not a
  silent gap: unmatched conditions simply produce no finding, never a wrong one.
- Reusing the free-text-parse-then-normalize pipeline for the "previous" list costs one additional
  LLM call (budgeted, same `LLMCallBudget` already governing the request) rather than requiring a
  second, structured-input-only endpoint.

## Alternatives considered
- **A generic "rule expression" DSL** (e.g., stored boolean expressions over patient attributes):
  more general, but over-engineered for two fixed, well-known criteria sets and harder to keep
  golden-tested against the source citations.
- **A separate `medication_discrepancies` table**: rejected — `medication_findings` already models
  "one deterministic finding, one or two medications, provenance JSONB"; a parallel table would
  duplicate that shape for no isolation or query benefit.
