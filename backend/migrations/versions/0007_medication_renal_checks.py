"""medication safety engine phase 2 — add 'calculated' to medication_interaction_source

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Renal findings (Phase 2, ADR-0005) are formula-derived, not looked up
    # from DDInter/openFDA — a new source value distinguishes them.
    # ALTER TYPE ... ADD VALUE is transaction-safe in Postgres 12+ as long
    # as the new value isn't used in the same transaction (it isn't here).
    # IF NOT EXISTS makes this idempotent — downgrade() is a documented
    # no-op (Postgres has no DROP VALUE), so re-running upgrade after a
    # downgrade must not fail on a value that was never actually removed.
    op.execute("ALTER TYPE medication_interaction_source ADD VALUE IF NOT EXISTS 'calculated'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — removing an enum value
    # requires rebuilding the type (and any dependent columns), which would
    # destroy data for rows already using it. Left as a no-op, matching the
    # standard, documented limitation for additive enum migrations; a real
    # rollback of this feature would need a dedicated data migration.
    pass
