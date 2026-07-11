"""Fernet encryption for org_sso_configs.client_secret at rest (ADR-0025) —
a tenant-configured integration credential, not an application secret
(CLAUDE.md §8 is about the latter), so it lives in the database rather than
an env var; this module is what protects it there. Checked only when an org
actually saves an SSO config — never at startup, since SSO is optional per
org (§23.1's "absence is normal" posture)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class SsoEncryptionNotConfiguredError(Exception):
    """SSO_CONFIG_ENCRYPTION_KEY is unset, or a stored secret can no longer
    be decrypted under the currently configured key."""


def _fernet(settings: Settings) -> Fernet:
    if not settings.SSO_CONFIG_ENCRYPTION_KEY:
        raise SsoEncryptionNotConfiguredError(
            "SSO_CONFIG_ENCRYPTION_KEY must be set to configure organization SSO."
        )
    return Fernet(settings.SSO_CONFIG_ENCRYPTION_KEY.encode("utf-8"))


def encrypt_client_secret(client_secret: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(client_secret.encode("utf-8")).decode("ascii")


def decrypt_client_secret(encrypted: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(encrypted.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SsoEncryptionNotConfiguredError(
            "Stored client secret could not be decrypted — SSO_CONFIG_ENCRYPTION_KEY may "
            "have changed since this organization's SSO was configured."
        ) from exc
