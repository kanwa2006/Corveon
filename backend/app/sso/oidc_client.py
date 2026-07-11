"""Async OIDC Relying Party client (ADR-0025): discovery, PKCE, token
exchange, and id_token verification — hand-rolled over ``httpx`` (matching
every other external client in this codebase: RxNorm, openFDA, all six
evidence connectors) rather than pyjwt's synchronous ``PyJWKClient``, which
would block the event loop."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
from dataclasses import dataclass

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from redis.asyncio import Redis

from app.sso.cache import get_or_fetch

_DISCOVERY_CACHE_TTL_SECONDS = 3600
_JWKS_CACHE_TTL_SECONDS = 3600
_HTTP_TIMEOUT_SECONDS = 10.0


class OidcDiscoveryError(Exception):
    """The IdP's discovery document or JWKS could not be fetched."""


class IdTokenVerificationError(Exception):
    """The id_token failed signature or claims verification, or the token
    exchange with the IdP failed."""


@dataclass(frozen=True, slots=True)
class PkcePair:
    verifier: str
    challenge: str


def generate_pkce_pair() -> PkcePair:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PkcePair(verifier=verifier, challenge=challenge)


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)


async def fetch_discovery_document(
    *, redis: Redis, issuer: str, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, object]:
    async def fetch() -> dict[str, object] | None:
        url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            return None
        data: dict[str, object] = response.json()
        return data

    document = await get_or_fetch(
        redis,
        source="discovery",
        query=issuer,
        ttl_seconds=_DISCOVERY_CACHE_TTL_SECONDS,
        fetch=fetch,
    )
    if document is None:
        raise OidcDiscoveryError(f"Could not fetch OIDC discovery document for issuer {issuer!r}.")
    return document


async def fetch_jwks(
    *, redis: Redis, jwks_uri: str, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, object]:
    async def fetch() -> dict[str, object] | None:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.get(jwks_uri)
        if response.status_code >= 400:
            return None
        data: dict[str, object] = response.json()
        return data

    jwks = await get_or_fetch(
        redis, source="jwks", query=jwks_uri, ttl_seconds=_JWKS_CACHE_TTL_SECONDS, fetch=fetch
    )
    if jwks is None:
        raise OidcDiscoveryError(f"Could not fetch JWKS from {jwks_uri!r}.")
    return jwks


def build_authorization_url(
    *,
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_tokens(
    *,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, transport=transport) as client:
        response = await client.post(token_endpoint, data=data)
    if response.status_code >= 400:
        raise IdTokenVerificationError(f"Token exchange failed: HTTP {response.status_code}.")
    result: dict[str, object] = response.json()
    return result


def verify_id_token(
    *, id_token: str, jwks: dict[str, object], issuer: str, audience: str, nonce: str
) -> dict[str, object]:
    """Verifies the id_token's RS256 signature against the IdP's own JWKS
    and its standard claims (iss/aud/exp, all enforced by ``jwt.decode``)
    plus the OIDC nonce (replay protection, checked separately — pyjwt has
    no built-in nonce concept)."""
    try:
        unverified_header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise IdTokenVerificationError(f"Malformed id_token: {exc}") from exc

    kid = unverified_header.get("kid")
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        raise IdTokenVerificationError("JWKS document has no 'keys' array.")
    matching_jwk = next((k for k in keys if isinstance(k, dict) and k.get("kid") == kid), None)
    if matching_jwk is None and len(keys) == 1:
        matching_jwk = keys[0]
    if matching_jwk is None:
        raise IdTokenVerificationError("No matching JWK found for the id_token's key id.")

    public_key = RSAAlgorithm.from_jwk(json.dumps(matching_jwk))
    try:
        claims: dict[str, object] = jwt.decode(
            id_token,
            key=public_key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
        )
    except jwt.PyJWTError as exc:
        raise IdTokenVerificationError(f"id_token verification failed: {exc}") from exc

    if claims.get("nonce") != nonce:
        raise IdTokenVerificationError("id_token nonce does not match the login attempt.")
    return claims
