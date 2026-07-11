"""SSO request/response schemas (docs/API.md — Auth / Org SSO, ADR-0025)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class SsoStartRequest(BaseModel):
    email: EmailStr


class SsoStartResponse(BaseModel):
    redirect_url: str


class SsoConfigUpsertRequest(BaseModel):
    issuer: HttpUrl
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    email_domain: str = Field(min_length=1, max_length=255)


class SsoConfigPublic(BaseModel):
    """Never includes the client secret — write-only, same posture as a
    password hash."""

    id: uuid.UUID
    org_id: uuid.UUID
    provider_type: str
    issuer: str
    client_id: str
    email_domain: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
