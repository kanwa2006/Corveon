"""Beers 2023 + STOPP/START v3 pinned snapshot loader (blueprint §9/§10.4,
ADR-0019, data/loaders/README.md's already-documented policy: "never commit
raw snapshots... each import verifies the checksum before use; a mismatch
fails loudly").

Both criteria sets are loaded the same way DDInter is (ADR-0018): as a
pinned, checksummed local snapshot, never fetched at request time. This
module verifies a snapshot file's checksum, records the import in
``drug_data_snapshots``, and populates ``pip_criteria`` with one row per
criterion.

Expected input: a UTF-8 CSV with a header row and columns ``source,
criterion_id, drug_names, condition_keywords, direction, rationale,
recommendation, severity`` — ``source`` one of ``beers_2023`` / ``stopp_v3``
/ ``start_v3``; ``drug_names`` and ``condition_keywords`` are ``|``-pipe-
separated lists within their cell (an empty ``condition_keywords`` cell
means the criterion is unconditional); ``direction`` one of ``avoid`` /
``start_consider``; ``severity`` one of ``major``/``moderate``/``minor``/
``unclassified``. The real AGS Beers Criteria 2023 and STOPP/START v3
tables are not bundled with this repository — they are copyrighted works of
the AGS Beers Criteria Update Expert Panel and the STOPP/START v3 authors
respectively; an operator transcribes the published criteria into this
column shape and points the loader at the resulting file."""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.medication import (
    DrugDataSnapshot,
    FindingSeverity,
    PipCriterion,
    PipDirection,
    PipSource,
)
from app.medication.ddinter_loader import compute_checksum

_REQUIRED_COLUMNS = {
    "source",
    "criterion_id",
    "drug_names",
    "condition_keywords",
    "direction",
    "rationale",
    "recommendation",
    "severity",
}


class PipCriteriaSnapshotError(Exception):
    """Raised when a snapshot file is missing, malformed, or its checksum
    doesn't match an expected value — always fails loudly, never imports
    silently-wrong data (CLAUDE.md: never fabricate/misrepresent medical
    facts)."""


def _split_list(cell: str) -> list[str]:
    return [item.strip().lower() for item in cell.split("|") if item.strip()]


def _parse_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if not _REQUIRED_COLUMNS.issubset(fieldnames):
            raise PipCriteriaSnapshotError(
                f"Snapshot at {path} is missing required columns "
                f"{sorted(_REQUIRED_COLUMNS - fieldnames)}; found {sorted(fieldnames)}."
            )
        return list(reader)


def _read_and_verify(path: Path, expected_checksum: str | None) -> tuple[str, list[dict[str, str]]]:
    # Blocking file I/O, run via asyncio.to_thread from the async caller
    # (matches app/medication/ddinter_loader.py's identical convention).
    if not path.exists():
        raise PipCriteriaSnapshotError(f"Snapshot file not found: {path}")

    checksum = compute_checksum(path)
    if expected_checksum is not None and checksum != expected_checksum:
        raise PipCriteriaSnapshotError(
            f"Checksum mismatch for {path}: expected {expected_checksum}, got {checksum}."
        )
    return checksum, _parse_rows(path)


async def load_pip_criteria_snapshot(
    session: AsyncSession,
    *,
    path: Path,
    source_label: str,
    version: str,
    expected_checksum: str | None = None,
) -> DrugDataSnapshot:
    """Imports a Beers 2023 or STOPP/START v3 CSV export as a new pinned
    snapshot. ``source_label`` (e.g. ``"beers2023"`` or ``"stopp_start_v3"``)
    is the top-level ``drug_data_snapshots.source`` value; each row's own
    ``source`` column independently records which of the three criteria
    sets (``beers_2023``/``stopp_v3``/``start_v3``) that specific row
    belongs to, since a single STOPP/START file mixes STOPP and START rows.
    A mismatched ``expected_checksum`` raises rather than importing (guards
    against silently ingesting a different/corrupted file under an
    already-reviewed version label)."""
    checksum, rows = await asyncio.to_thread(_read_and_verify, path, expected_checksum)

    snapshot = DrugDataSnapshot(
        source=source_label, version=version, checksum=checksum, row_count=len(rows)
    )
    session.add(snapshot)
    await session.flush()

    for row in rows:
        try:
            source = PipSource(row["source"].strip().lower())
        except ValueError as exc:
            raise PipCriteriaSnapshotError(
                f"Unrecognized source {row['source']!r} in {path}."
            ) from exc
        try:
            direction = PipDirection(row["direction"].strip().lower())
        except ValueError as exc:
            raise PipCriteriaSnapshotError(
                f"Unrecognized direction {row['direction']!r} in {path}."
            ) from exc
        try:
            severity = FindingSeverity(row["severity"].strip().lower())
        except ValueError as exc:
            raise PipCriteriaSnapshotError(
                f"Unrecognized severity {row['severity']!r} in {path}."
            ) from exc

        drug_names = _split_list(row["drug_names"])
        if not drug_names:
            raise PipCriteriaSnapshotError(
                f"Criterion {row['criterion_id']!r} in {path} has no drug_names."
            )

        session.add(
            PipCriterion(
                snapshot_id=snapshot.id,
                source=source,
                criterion_id=row["criterion_id"].strip(),
                drug_names=drug_names,
                condition_keywords=_split_list(row["condition_keywords"]),
                direction=direction,
                rationale=row["rationale"].strip(),
                recommendation=row["recommendation"].strip(),
                severity=severity,
            )
        )

    await session.flush()
    return snapshot


async def _main() -> None:
    from app.core.config import get_settings
    from app.data.base import Database

    parser = argparse.ArgumentParser(
        description="Import a Beers 2023 or STOPP/START v3 criteria CSV."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--source-label", required=True, help='e.g. "beers2023" or "stopp_start_v3".'
    )
    parser.add_argument("--version", required=True, help="Label for this snapshot, e.g. 2023.")
    parser.add_argument("--checksum", default=None, help="Expected SHA-256 checksum (optional).")
    args = parser.parse_args()

    db = Database(get_settings())
    try:
        async for session in db.session():
            snapshot = await load_pip_criteria_snapshot(
                session,
                path=args.path,
                source_label=args.source_label,
                version=args.version,
                expected_checksum=args.checksum,
            )
            await session.commit()
            print(
                f"Imported {snapshot.row_count} PIP criteria as snapshot {snapshot.id} "
                f"(source={snapshot.source}, version={snapshot.version}, "
                f"checksum={snapshot.checksum})."
            )
            break
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
