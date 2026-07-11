"""Org SSO config repository — the only place that queries
org_sso_configs (ADR-0025)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.sso import OrgSsoConfig


class SsoConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_org_id(self, org_id: uuid.UUID) -> OrgSsoConfig | None:
        result = await self._session.execute(
            select(OrgSsoConfig).where(OrgSsoConfig.org_id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email_domain(self, email_domain: str) -> OrgSsoConfig | None:
        result = await self._session.execute(
            select(OrgSsoConfig).where(OrgSsoConfig.email_domain == email_domain)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        org_id: uuid.UUID,
        issuer: str,
        client_id: str,
        client_secret_encrypted: str,
        email_domain: str,
    ) -> OrgSsoConfig:
        existing = await self.get_by_org_id(org_id)
        if existing is not None:
            existing.issuer = issuer
            existing.client_id = client_id
            existing.client_secret_encrypted = client_secret_encrypted
            existing.email_domain = email_domain
            existing.is_active = True
            await self._session.flush()
            return existing

        config = OrgSsoConfig(
            org_id=org_id,
            issuer=issuer,
            client_id=client_id,
            client_secret_encrypted=client_secret_encrypted,
            email_domain=email_domain,
        )
        self._session.add(config)
        await self._session.flush()
        return config

    async def delete(self, config: OrgSsoConfig) -> None:
        await self._session.delete(config)
        await self._session.flush()
