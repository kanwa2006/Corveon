"""Deterministic medication-discrepancy classification across two lists
(blueprint §9, ADR-0019) — added / omitted / dose-changed / frequency-
changed, with RxCUI-level matching. Purely deterministic: no LLM
involvement anywhere in this module (CLAUDE.md §6: "the rules engine is
the source of truth")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.medication.interactions import NormalizedMedication

DiscrepancyKind = Literal["added", "omitted", "dose_changed", "frequency_changed"]


@dataclass(frozen=True, slots=True)
class DiscrepancyFinding:
    kind: DiscrepancyKind
    # Indices into the `current`/`previous` lists passed to
    # classify_discrepancies — the caller maps these to persisted
    # Medication row ids once both lists are saved (same convention as
    # InteractionFinding's medication_a_index/medication_b_index).
    current_index: int | None
    previous_index: int | None
    rule_id: str
    explanation: str
    provenance: dict[str, Any]


def _match_key(medication: NormalizedMedication) -> str:
    """RxCUI-first matching (blueprint §9: "RxCUI-level matching"), falling
    back to normalized name when a medication has no RxCUI match — an
    unmatched drug is still comparable across lists, not silently dropped
    from the diff."""
    if medication.rxcui:
        return f"rxcui:{medication.rxcui}"
    return f"name:{medication.name.strip().lower()}"


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip().lower()
    return stripped or None


def classify_discrepancies(
    previous: list[NormalizedMedication], current: list[NormalizedMedication]
) -> list[DiscrepancyFinding]:
    """Diffs two already-normalized medication lists. Each current-list
    entry is matched to at most one previous-list entry (and vice versa) by
    RxCUI, falling back to normalized name. Medication lists are short
    (tens of entries), so a straightforward first-available-match by list
    order is fast and has well-defined behavior even with duplicate drug
    entries: earliest unmatched occurrence pairs first."""
    findings: list[DiscrepancyFinding] = []

    previous_by_key: dict[str, list[int]] = {}
    for index, medication in enumerate(previous):
        previous_by_key.setdefault(_match_key(medication), []).append(index)

    matched_previous_indices: set[int] = set()

    for current_index, current_medication in enumerate(current):
        candidates = previous_by_key.get(_match_key(current_medication), [])
        previous_index = next(
            (index for index in candidates if index not in matched_previous_indices), None
        )

        if previous_index is None:
            findings.append(
                DiscrepancyFinding(
                    kind="added",
                    current_index=current_index,
                    previous_index=None,
                    rule_id="discrepancy:added",
                    explanation=(
                        f"{current_medication.name} appears in the current list but not "
                        "the previous one."
                    ),
                    provenance={
                        "name": current_medication.name,
                        "rxcui": current_medication.rxcui,
                    },
                )
            )
            continue

        matched_previous_indices.add(previous_index)
        previous_medication = previous[previous_index]

        if _normalize_optional(current_medication.dose) != _normalize_optional(
            previous_medication.dose
        ):
            findings.append(
                DiscrepancyFinding(
                    kind="dose_changed",
                    current_index=current_index,
                    previous_index=previous_index,
                    rule_id="discrepancy:dose_changed",
                    explanation=(
                        f"{current_medication.name}'s dose changed from "
                        f"{previous_medication.dose or 'unspecified'} to "
                        f"{current_medication.dose or 'unspecified'}."
                    ),
                    provenance={
                        "name": current_medication.name,
                        "previous_dose": previous_medication.dose,
                        "current_dose": current_medication.dose,
                    },
                )
            )

        if _normalize_optional(current_medication.frequency) != _normalize_optional(
            previous_medication.frequency
        ):
            findings.append(
                DiscrepancyFinding(
                    kind="frequency_changed",
                    current_index=current_index,
                    previous_index=previous_index,
                    rule_id="discrepancy:frequency_changed",
                    explanation=(
                        f"{current_medication.name}'s frequency changed from "
                        f"{previous_medication.frequency or 'unspecified'} to "
                        f"{current_medication.frequency or 'unspecified'}."
                    ),
                    provenance={
                        "name": current_medication.name,
                        "previous_frequency": previous_medication.frequency,
                        "current_frequency": current_medication.frequency,
                    },
                )
            )

    for previous_index, previous_medication in enumerate(previous):
        if previous_index in matched_previous_indices:
            continue
        findings.append(
            DiscrepancyFinding(
                kind="omitted",
                current_index=None,
                previous_index=previous_index,
                rule_id="discrepancy:omitted",
                explanation=(
                    f"{previous_medication.name} appears in the previous list but not "
                    "the current one."
                ),
                provenance={
                    "name": previous_medication.name,
                    "rxcui": previous_medication.rxcui,
                },
            )
        )

    return findings
