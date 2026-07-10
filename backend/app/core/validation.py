"""Shared input-validation helpers (CLAUDE.md §5: validate all external
input with Pydantic) — reusable across both Pydantic model fields and
FastAPI ``Query``/``Annotated`` parameters, which don't share a validation
mechanism otherwise."""

from __future__ import annotations


def reject_nul_bytes(value: str | None) -> str | None:
    """Postgres text columns reject an embedded NUL byte at the wire level
    (asyncpg raises ``CharacterNotInRepertoireError``), whether the value
    is stored directly or used in an ``ILIKE`` filter — a Python ``str``
    allows one freely, so any free-text value that reaches the database
    must be rejected here first, surfacing a 422 instead of an uncaught
    500 from the DB driver."""
    if value is not None and "\x00" in value:
        raise ValueError("must not contain NUL bytes.")
    return value
