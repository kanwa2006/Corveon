"""ORM models. Import every model module here so Alembic's autogenerate (and
the CI models↔migrations sync check, ADR-0002) sees the full metadata."""

from app.data.models.organization import Organization
from app.data.models.user import User, UserRole

__all__ = ["Organization", "User", "UserRole"]
