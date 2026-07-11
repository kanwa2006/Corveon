"""medication safety engine phase 3 — pip_criteria table, nullable medication_a_id

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_pip_source = postgresql.ENUM(
    "beers_2023",
    "stopp_v3",
    "start_v3",
    name="pip_criterion_source",
    create_type=False,
)
_pip_direction = postgresql.ENUM(
    "avoid",
    "start_consider",
    name="pip_criterion_direction",
    create_type=False,
)
_finding_severity = postgresql.ENUM(
    "major",
    "moderate",
    "minor",
    "unclassified",
    name="medication_finding_severity",
    create_type=False,
)


def upgrade() -> None:
    # A START-criterion finding (ADR-0019) flags a *missing* medication —
    # there is no medication row to anchor medication_a_id to. Phase 1/2
    # findings are unaffected: they always populate this column, this only
    # widens what's allowed.
    op.alter_column("medication_findings", "medication_a_id", nullable=True)

    _pip_source.create(op.get_bind(), checkfirst=True)
    _pip_direction.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "pip_criteria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source", _pip_source, nullable=False),
        sa.Column("criterion_id", sa.String(), nullable=False),
        sa.Column("drug_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("condition_keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("direction", _pip_direction, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("severity", _finding_severity, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["drug_data_snapshots.id"],
            name=op.f("fk_pip_criteria_snapshot_id_drug_data_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pip_criteria")),
    )
    op.create_index(op.f("ix_pip_criteria_snapshot_id"), "pip_criteria", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_pip_criteria_snapshot_id"), table_name="pip_criteria")
    op.drop_table("pip_criteria")

    _pip_direction.drop(op.get_bind(), checkfirst=True)
    _pip_source.drop(op.get_bind(), checkfirst=True)

    # Best-effort: fails if a START-type finding (medication_a_id IS NULL)
    # was persisted after upgrade — same documented limitation as any
    # downgrade of a widening migration; a real rollback would need a data
    # migration to backfill or delete those rows first.
    op.alter_column("medication_findings", "medication_a_id", nullable=False)
