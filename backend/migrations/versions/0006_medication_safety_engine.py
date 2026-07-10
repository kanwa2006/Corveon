"""medication safety engine phase 1 — medications/medication_findings/drug_data_snapshots, with RLS

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_finding_type = postgresql.ENUM(
    "interaction",
    "renal",
    "pip",
    "discrepancy",
    name="medication_finding_type",
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
_interaction_source = postgresql.ENUM(
    "ddinter",
    "openfda_label",
    name="medication_interaction_source",
    create_type=False,
)

# RLS (docs/ARCHITECTURE.md §5, same pattern as migrations 0003/0005):
# chat_id is the isolation anchor; every policy checks ownership via a
# correlated EXISTS against chats (ADR-0013). drug_data_snapshots is
# deliberately excluded — it is shared reference data, not chat content.
_TABLES_WITH_CHAT_ID_RLS = ("medications", "medication_findings")


def _rls_policy_sql(table: str) -> str:
    # `table` is always one of the fixed literals in _TABLES_WITH_CHAT_ID_RLS
    # above (never external input), so this is not an injection vector.
    policy_name = f"{table}_chat_isolation"
    return f"""
        CREATE POLICY {policy_name} ON {table}
        USING (
            EXISTS (
                SELECT 1 FROM chats c
                WHERE c.id = {table}.chat_id
                AND c.user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM chats c
                WHERE c.id = {table}.chat_id
                AND c.user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            )
        )
        """


def upgrade() -> None:
    _finding_type.create(op.get_bind(), checkfirst=True)
    _finding_severity.create(op.get_bind(), checkfirst=True)
    _interaction_source.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "medications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("rxcui", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("dose", sa.String(), nullable=True),
        sa.Column("route", sa.String(), nullable=True),
        sa.Column("frequency", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"], ["chats.id"], name=op.f("fk_medications_chat_id_chats"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medications")),
    )
    op.create_index(op.f("ix_medications_chat_id"), "medications", ["chat_id"])

    op.create_table(
        "medication_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("medication_a_id", sa.Uuid(), nullable=False),
        sa.Column("medication_b_id", sa.Uuid(), nullable=True),
        sa.Column("type", _finding_type, nullable=False),
        sa.Column("severity", _finding_severity, nullable=False),
        sa.Column("source", _interaction_source, nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_medication_findings_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["medication_a_id"],
            ["medications.id"],
            name=op.f("fk_medication_findings_medication_a_id_medications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["medication_b_id"],
            ["medications.id"],
            name=op.f("fk_medication_findings_medication_b_id_medications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medication_findings")),
    )
    op.create_index(op.f("ix_medication_findings_chat_id"), "medication_findings", ["chat_id"])

    op.create_table(
        "drug_data_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drug_data_snapshots")),
    )

    op.create_table(
        "drug_interactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("drug_a_name", sa.String(), nullable=False),
        sa.Column("drug_b_name", sa.String(), nullable=False),
        sa.Column("severity", _finding_severity, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["drug_data_snapshots.id"],
            name=op.f("fk_drug_interactions_snapshot_id_drug_data_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drug_interactions")),
    )
    op.create_index(
        op.f("ix_drug_interactions_pair"), "drug_interactions", ["drug_a_name", "drug_b_name"]
    )
    op.create_index(op.f("ix_drug_interactions_snapshot_id"), "drug_interactions", ["snapshot_id"])

    for table in _TABLES_WITH_CHAT_ID_RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(_rls_policy_sql(table))


def downgrade() -> None:
    for table in reversed(_TABLES_WITH_CHAT_ID_RLS):
        op.execute(f"DROP POLICY IF EXISTS {table}_chat_isolation ON {table}")

    op.drop_index(op.f("ix_drug_interactions_snapshot_id"), table_name="drug_interactions")
    op.drop_index(op.f("ix_drug_interactions_pair"), table_name="drug_interactions")
    op.drop_table("drug_interactions")

    op.drop_table("drug_data_snapshots")

    op.drop_index(op.f("ix_medication_findings_chat_id"), table_name="medication_findings")
    op.drop_table("medication_findings")

    op.drop_index(op.f("ix_medications_chat_id"), table_name="medications")
    op.drop_table("medications")

    _interaction_source.drop(op.get_bind(), checkfirst=True)
    _finding_severity.drop(op.get_bind(), checkfirst=True)
    _finding_type.drop(op.get_bind(), checkfirst=True)
