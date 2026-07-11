"""Org SSO configuration endpoints (docs/API.md — Org SSO, ADR-0025).
Always scoped to the caller's own org_id — never accepted from the request
body, so a compromised admin token can never write another org's config.
Backed by the /settings/sso admin page (frontend/app/(app)/settings/sso)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.api.schemas.sso import SsoConfigPublic, SsoConfigUpsertRequest
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.data.models.user import User, UserRole
from app.data.repositories.audit_log_repository import AuditLogRepository
from app.data.repositories.sso_config_repository import SsoConfigRepository
from app.sso.crypto import encrypt_client_secret

router = APIRouter(prefix="/org", tags=["org-sso"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _require_org(user: User) -> uuid.UUID:
    if user.role not in (UserRole.ORG_ADMIN, UserRole.SUPERADMIN):
        raise ForbiddenError("Only an organization admin can manage SSO configuration.")
    if user.org_id is None:
        raise ValidationAppError("Your account is not associated with an organization.")
    return user.org_id


@router.post("/sso-config", response_model=SsoConfigPublic, status_code=status.HTTP_201_CREATED)
async def upsert_sso_config(
    payload: SsoConfigUpsertRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    current_user: CurrentUserDep,
) -> SsoConfigPublic:
    org_id = _require_org(current_user)

    repo = SsoConfigRepository(db)
    config = await repo.upsert(
        org_id=org_id,
        issuer=str(payload.issuer),
        client_id=payload.client_id,
        client_secret_encrypted=encrypt_client_secret(payload.client_secret, settings),
        email_domain=payload.email_domain.lower(),
    )
    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="org.sso_config.upsert",
        entity_type="org_sso_config",
        entity_id=config.id,
        ip=_client_ip(request),
        metadata={"org_id": str(org_id), "email_domain": config.email_domain},
    )
    await db.commit()
    return SsoConfigPublic.model_validate(config)


@router.get("/sso-config", response_model=SsoConfigPublic)
async def get_sso_config(db: DbDep, current_user: CurrentUserDep) -> SsoConfigPublic:
    org_id = _require_org(current_user)

    config = await SsoConfigRepository(db).get_by_org_id(org_id)
    if config is None:
        raise NotFoundError("No SSO configuration exists for your organization.")
    return SsoConfigPublic.model_validate(config)


@router.delete("/sso-config", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sso_config(request: Request, db: DbDep, current_user: CurrentUserDep) -> None:
    org_id = _require_org(current_user)

    repo = SsoConfigRepository(db)
    config = await repo.get_by_org_id(org_id)
    if config is None:
        raise NotFoundError("No SSO configuration exists for your organization.")

    await repo.delete(config)
    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="org.sso_config.delete",
        entity_type="org_sso_config",
        entity_id=config.id,
        ip=_client_ip(request),
        metadata={"org_id": str(org_id)},
    )
    await db.commit()
