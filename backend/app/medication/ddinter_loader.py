"""DDInter 2.0 pinned snapshot loader (blueprint §9/§10.4, ADR-0004,
data/loaders/README.md's already-documented policy: "never commit raw
snapshots — they are fetched, not vendored... each import verifies the
checksum before use; a mismatch fails loudly").

DDInter is loaded as a pinned, checksummed local snapshot — never fetched
at request time (unlike the six live connectors in app/evidence/connectors/).
This module verifies a snapshot file's checksum, records the import in
``drug_data_snapshots``, and populates ``drug_interactions`` with
``(drug_a_name, drug_b_name, severity, description)`` rows — symmetric
pairs stored in sorted-name order so a pairwise lookup only needs to check
one direction (app/medication/interactions.py).

Expected input: a UTF-8 CSV with a header row and columns ``drug_a,
drug_b, severity, description`` — ``severity`` one of DDInter's own
three-tier scale (``major`` / ``moderate`` / ``minor``). The real DDInter
2.0 export (2,310 drugs, 302,516 interaction records, Xiong et al. 2025)
is not bundled with this repository — it is separately licensed and far
too large to vendor; an operator downloads it from
https://ddinter2.scbdd.com, converts it to this column shape, and points
``DDINTER_SNAPSHOT_PATH`` at the resulting file."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.medication import DrugDataSnapshot, DrugInteraction, FindingSeverity

_REQUIRED_COLUMNS = {"drug_a", "drug_b", "severity", "description"}


class DDInterSnapshotError(Exception):
    """Raised when a snapshot file is missing, malformed, or its checksum
    doesn't match an expected value — always fails loudly, never imports
    silently-wrong data (CLAUDE.md: never fabricate/misrepresent medical
    facts)."""


def _normalize_drug_name(name: str) -> str:
    return name.strip().lower()


def compute_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if not _REQUIRED_COLUMNS.issubset(fieldnames):
            raise DDInterSnapshotError(
                f"Snapshot at {path} is missing required columns "
                f"{sorted(_REQUIRED_COLUMNS - fieldnames)}; found {sorted(fieldnames)}."
            )
        return list(reader)


def _read_and_verify(path: Path, expected_checksum: str | None) -> tuple[str, list[dict[str, str]]]:
    # Blocking file I/O, run via asyncio.to_thread from the async caller
    # (matches app/core/storage.py's local-disk fallback convention).
    if not path.exists():
        raise DDInterSnapshotError(f"Snapshot file not found: {path}")

    checksum = compute_checksum(path)
    if expected_checksum is not None and checksum != expected_checksum:
        raise DDInterSnapshotError(
            f"Checksum mismatch for {path}: expected {expected_checksum}, got {checksum}."
        )
    return checksum, _parse_rows(path)


async def load_ddinter_snapshot(
    session: AsyncSession,
    *,
    path: Path,
    version: str,
    expected_checksum: str | None = None,
) -> DrugDataSnapshot:
    """Imports a DDInter 2.0 CSV export as a new pinned snapshot. When
    ``expected_checksum`` is given, a mismatch raises rather than importing
    (guards against silently ingesting a different/corrupted file under an
    already-reviewed version label); the computed checksum is always
    recorded on the resulting row either way, so every import — including
    a first-time one with no prior expected value — is itself reproducible
    and auditable."""
    checksum, rows = await asyncio.to_thread(_read_and_verify, path, expected_checksum)

    snapshot = DrugDataSnapshot(
        source="ddinter", version=version, checksum=checksum, row_count=len(rows)
    )
    session.add(snapshot)
    await session.flush()

    for row in rows:
        raw_severity = row["severity"].strip().lower()
        try:
            severity = FindingSeverity(raw_severity)
        except ValueError as exc:
            raise DDInterSnapshotError(
                f"Unrecognized severity {row['severity']!r} in {path}."
            ) from exc
        drug_a, drug_b = sorted(
            (_normalize_drug_name(row["drug_a"]), _normalize_drug_name(row["drug_b"]))
        )
        session.add(
            DrugInteraction(
                snapshot_id=snapshot.id,
                drug_a_name=drug_a,
                drug_b_name=drug_b,
                severity=severity,
                description=row["description"].strip(),
            )
        )

    await session.flush()
    return snapshot


async def _main() -> None:
    from app.core.config import get_settings
    from app.data.base import Database

    parser = argparse.ArgumentParser(description="Import a DDInter 2.0 snapshot CSV.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--version", required=True, help="Label for this snapshot, e.g. 2025-01.")
    parser.add_argument("--checksum", default=None, help="Expected SHA-256 checksum (optional).")
    args = parser.parse_args()

    db = Database(get_settings())
    try:
        async for session in db.session():
            snapshot = await load_ddinter_snapshot(
                session, path=args.path, version=args.version, expected_checksum=args.checksum
            )
            await session.commit()
            print(
                f"Imported {snapshot.row_count} interactions as snapshot {snapshot.id} "
                f"(version={snapshot.version}, checksum={snapshot.checksum})."
            )
            break
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
