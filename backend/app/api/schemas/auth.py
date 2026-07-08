"""Auth request/response schemas (docs/API.md — Auth)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.data.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access: str
    refresh: str


class AccessTokenResponse(BaseModel):
    access: str


class StreamTicketResponse(BaseModel):
    ticket: str


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    org_id: uuid.UUID | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
