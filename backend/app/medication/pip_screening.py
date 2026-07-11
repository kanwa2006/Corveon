"""Deterministic potentially-inappropriate-prescribing (PIP) screening —
AGS Beers Criteria 2023 + STOPP/START v3 (blueprint §9, ADR-0019). Purely
deterministic: no LLM involvement anywhere in this module (CLAUDE.md §6:
"the rules engine is the source of truth")."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.medication import FindingSeverity, PipCriterion, PipDirection, PipSource
from app.medication.interactions import NormalizedMedication

_MIN_AGE_YEARS = 65

_SOURCE_LABELS = {
    PipSource.BEERS_2023: "AGS Beers Criteria 2023",
    PipSource.STOPP_V3: "STOPP v3",
    PipSource.START_V3: "START v3",
}


@dataclass(frozen=True, slots=True)
class PipFinding:
    # None for a START (omission) finding — it flags a missing medication,
    # not one the patient takes (ADR-0019).
    medication_index: int | None
    criterion_id: str
    source: PipSource
    direction: PipDirection
    severity: FindingSeverity
    drug_names: list[str]
    matched_condition: str | None
    rule_id: str
    explanation: str


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _condition_matches(
    criterion_keywords: list[str], conditions: list[str]
) -> tuple[bool, str | None]:
    """Returns ``(matched, matched_condition)``. An empty
    ``criterion_keywords`` means the criterion is unconditional — matches
    trivially with no specific condition to report. Otherwise, matches the
    first supplied condition string that case-insensitively contains, or is
    contained by, one of the criterion's keywords."""
    if not criterion_keywords:
        return True, None
    for condition in conditions:
        normalized_condition = condition.strip().lower()
        if not normalized_condition:
            continue
        for keyword in criterion_keywords:
            if keyword in normalized_condition or normalized_condition in keyword:
                return True, condition
    return False, None


async def _load_criteria(session: AsyncSession) -> list[PipCriterion]:
    result = await session.execute(select(PipCriterion))
    return list(result.scalars().all())


def _explanation(
    criterion: PipCriterion, *, medication_name: str | None, matched_condition: str | None
) -> str:
    source_label = _SOURCE_LABELS[criterion.source]
    condition_clause = f" given {matched_condition}" if matched_condition else ""
    if criterion.direction == PipDirection.AVOID:
        subject = medication_name or "/".join(criterion.drug_names)
        return (
            f"{source_label} ({criterion.criterion_id}): avoid {subject}{condition_clause} — "
            f"{criterion.rationale} {criterion.recommendation}".strip()
        )
    drugs = "/".join(criterion.drug_names)
    return (
        f"{source_label} ({criterion.criterion_id}): consider starting {drugs}{condition_clause} — "
        f"{criterion.rationale} {criterion.recommendation}".strip()
    )


async def check_pip_criteria(
    medications: list[NormalizedMedication],
    *,
    age_years: int,
    conditions: list[str],
    session: AsyncSession,
) -> list[PipFinding]:
    """Screens ``medications`` against every pinned Beers 2023 / STOPP/START
    v3 criterion. AVOID criteria (every Beers row, and STOPP's
    condition-gated rows) fire when the patient takes a listed drug and —
    for condition-gated criteria — a supplied condition matches.
    START_CONSIDER criteria fire when a condition matches and *none* of the
    criterion's drugs appear anywhere in the current list (an omission, not
    a drug-linked finding). Below age 65, screening is skipped entirely
    (both criteria sets target older adults) — an honest "not applicable",
    not a silently-empty scan."""
    if age_years < _MIN_AGE_YEARS:
        return []

    criteria = await _load_criteria(session)
    normalized_meds = [_normalize_name(m.name) for m in medications]
    findings: list[PipFinding] = []

    for criterion in criteria:
        condition_ok, matched_condition = _condition_matches(
            criterion.condition_keywords, conditions
        )
        if not condition_ok:
            continue

        rule_id = f"{criterion.source.value}:{criterion.criterion_id}"

        if criterion.direction == PipDirection.AVOID:
            for index, normalized_name in enumerate(normalized_meds):
                if normalized_name in criterion.drug_names:
                    findings.append(
                        PipFinding(
                            medication_index=index,
                            criterion_id=criterion.criterion_id,
                            source=criterion.source,
                            direction=criterion.direction,
                            severity=criterion.severity,
                            drug_names=criterion.drug_names,
                            matched_condition=matched_condition,
                            rule_id=rule_id,
                            explanation=_explanation(
                                criterion,
                                medication_name=medications[index].name,
                                matched_condition=matched_condition,
                            ),
                        )
                    )
        else:  # PipDirection.START_CONSIDER
            if any(name in criterion.drug_names for name in normalized_meds):
                continue
            findings.append(
                PipFinding(
                    medication_index=None,
                    criterion_id=criterion.criterion_id,
                    source=criterion.source,
                    direction=criterion.direction,
                    severity=criterion.severity,
                    drug_names=criterion.drug_names,
                    matched_condition=matched_condition,
                    rule_id=rule_id,
                    explanation=_explanation(
                        criterion, medication_name=None, matched_condition=matched_condition
                    ),
                )
            )

    return findings
