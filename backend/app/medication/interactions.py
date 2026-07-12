"""Deterministic drug-drug interaction rules engine (blueprint §9,
ADR-0004) — DDInter 2.0 primary, openFDA label-derived fallback for pairs
the pinned snapshot doesn't cover. Purely deterministic: no LLM
involvement anywhere in this module (CLAUDE.md §6: "the rules engine is
the source of truth")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.medication import DrugInteraction, FindingSeverity, InteractionSource
from app.medication.openfda_ddi_client import OpenFdaDdiMatch


@dataclass(frozen=True, slots=True)
class NormalizedMedication:
    raw_text: str
    name: str
    rxcui: str | None
    dose: str | None
    route: str | None
    frequency: str | None
    # Names the deterministic rules engines match on (RxNorm IN/MIN
    # ingredient names first, then the user's parsed name — lowercased, see
    # normalizer.normalize_entry). ``name`` itself is display-only: RxNav's
    # canonical name is often a verbose branded product string that
    # ingredient-keyed rule tables (renal thresholds, DDInter, Beers/STOPP)
    # can never match.
    match_names: tuple[str, ...] = ()

    @property
    def names_for_matching(self) -> tuple[str, ...]:
        """Falls back to the display name when no match names were supplied
        (direct construction in tests, or callers predating match_names)."""
        if self.match_names:
            return self.match_names
        return (self.name.strip().lower(),)


@dataclass(frozen=True, slots=True)
class InteractionFinding:
    # Indices into the ``medications`` list passed to find_interactions —
    # the caller (medication analysis service) maps these to persisted
    # Medication row ids once medications are saved.
    medication_a_index: int
    medication_b_index: int
    severity: FindingSeverity
    source: InteractionSource
    rule_id: str
    explanation: str
    provenance: dict[str, Any]


class SupportsCheckPair(Protocol):
    async def check_pair(self, label_drug: str, mentioned_drug: str) -> OpenFdaDdiMatch | None: ...


def _normalize_name(name: str) -> str:
    return name.strip().lower()


async def _lookup_ddinter(
    session: AsyncSession, name_a: str, name_b: str
) -> DrugInteraction | None:
    sorted_a, sorted_b = sorted((name_a, name_b))
    result = await session.execute(
        select(DrugInteraction).where(
            DrugInteraction.drug_a_name == sorted_a, DrugInteraction.drug_b_name == sorted_b
        )
    )
    return result.scalars().first()


async def _lookup_openfda_fallback(
    openfda_client: SupportsCheckPair, name_a: str, name_b: str
) -> OpenFdaDdiMatch | None:
    # Label authors don't cross-reference symmetrically — check both
    # directions before concluding openFDA has nothing either.
    match = await openfda_client.check_pair(name_a, name_b)
    if match is not None:
        return match
    return await openfda_client.check_pair(name_b, name_a)


async def find_interactions(
    medications: list[NormalizedMedication],
    *,
    session: AsyncSession,
    openfda_client: SupportsCheckPair,
) -> list[InteractionFinding]:
    """Checks every distinct pair in ``medications`` — DDInter first, then
    the openFDA label fallback for any pair DDInter has no record for.
    O(n²) pairs is the correct, complete behavior for a medication-safety
    check (a missed interaction is a safety gap, not an acceptable
    optimization tradeoff) — medication lists are short (tens of entries,
    not thousands), so this stays fast in practice."""
    findings: list[InteractionFinding] = []
    for i in range(len(medications)):
        for j in range(i + 1, len(medications)):
            medication_a, medication_b = medications[i], medications[j]
            names_a = medication_a.names_for_matching
            names_b = medication_b.names_for_matching

            # DDInter rows are keyed on ingredient names — check every
            # (ingredient/parsed) name combination for the pair; lists are
            # 1-2 names each, so this stays a handful of cheap DB lookups.
            ddinter_row: DrugInteraction | None = None
            for name_a in names_a:
                for name_b in names_b:
                    ddinter_row = await _lookup_ddinter(
                        session, _normalize_name(name_a), _normalize_name(name_b)
                    )
                    if ddinter_row is not None:
                        break
                if ddinter_row is not None:
                    break
            if ddinter_row is not None:
                findings.append(
                    InteractionFinding(
                        medication_a_index=i,
                        medication_b_index=j,
                        severity=ddinter_row.severity,
                        source=InteractionSource.DDINTER,
                        rule_id=str(ddinter_row.id),
                        explanation=ddinter_row.description,
                        provenance={"snapshot_id": str(ddinter_row.snapshot_id)},
                    )
                )
                continue

            # openFDA label search is by generic name — use each side's
            # best match name (first ingredient when resolved, else the
            # parsed name), never the branded display string.
            fallback = await _lookup_openfda_fallback(openfda_client, names_a[0], names_b[0])
            if fallback is not None:
                findings.append(
                    InteractionFinding(
                        medication_a_index=i,
                        medication_b_index=j,
                        severity=FindingSeverity.UNCLASSIFIED,
                        source=InteractionSource.OPENFDA_LABEL,
                        rule_id=fallback.label_id,
                        explanation=fallback.snippet,
                        provenance={"url": fallback.url},
                    )
                )

    return findings
