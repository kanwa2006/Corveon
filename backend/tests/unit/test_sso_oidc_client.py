"""Unit tests for app/sso/oidc_client.py (ADR-0025): PKCE/state/nonce
generation, authorization-URL construction, discovery/JWKS caching against
httpx.MockTransport, and id_token verification against a real, locally
generated RSA keypair — no live network or real IdP required."""

from __future__ import annotations

import httpx
import jwt
import pytest
from app.sso.oidc_client import (
    IdTokenVerificationError,
    OidcDiscoveryError,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_discovery_document,
    fetch_jwks,
    generate_nonce,
    generate_pkce_pair,
    generate_state,
    verify_id_token,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

pytestmark = pytest.mark.unit

_ISSUER = "https://idp.example.com"
_AUDIENCE = "test-client-id"
_KID = "test-key-1"


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


def _rsa_keypair() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = _KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private_key, jwk


def _sign_id_token(
    private_key: rsa.RSAPrivateKey, *, claims: dict[str, object], kid: str | None = _KID
) -> str:
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(claims, private_key, algorithm="RS256", headers=headers)


def test_generate_pkce_pair_produces_a_derived_challenge() -> None:
    pair = generate_pkce_pair()
    assert pair.verifier
    assert pair.challenge
    assert pair.verifier != pair.challenge
    # S256 challenge is deterministic from the verifier.
    other = generate_pkce_pair()
    assert other.verifier != pair.verifier


def test_generate_state_and_nonce_are_unique_each_call() -> None:
    assert generate_state() != generate_state()
    assert generate_nonce() != generate_nonce()


def test_build_authorization_url_includes_all_required_params() -> None:
    url = build_authorization_url(
        authorization_endpoint="https://idp.example.com/authorize",
        client_id="client-1",
        redirect_uri="https://app.example.com/api/auth/sso/callback",
        state="state-1",
        nonce="nonce-1",
        code_challenge="challenge-1",
    )
    assert url.startswith("https://idp.example.com/authorize?")
    assert "response_type=code" in url
    assert "client_id=client-1" in url
    assert "state=state-1" in url
    assert "nonce=nonce-1" in url
    assert "code_challenge=challenge-1" in url
    assert "code_challenge_method=S256" in url


async def test_fetch_discovery_document_caches_across_calls(app) -> None:  # type: ignore[no-untyped-def]
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        assert request.url.path == "/.well-known/openid-configuration"
        return httpx.Response(200, json={"issuer": _ISSUER, "token_endpoint": "https://x/token"})

    first = await fetch_discovery_document(
        redis=app.state.redis, issuer=_ISSUER, transport=_transport(handler)
    )
    second = await fetch_discovery_document(
        redis=app.state.redis, issuer=_ISSUER, transport=_transport(handler)
    )
    assert first == second
    assert call_count == 1


async def test_fetch_discovery_document_raises_on_http_error(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(OidcDiscoveryError):
        await fetch_discovery_document(
            redis=app.state.redis,
            issuer="https://unreachable-idp.example.com",
            transport=_transport(handler),
        )


async def test_fetch_jwks_returns_the_keys_document(app) -> None:  # type: ignore[no-untyped-def]
    _, jwk = _rsa_keypair()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    result = await fetch_jwks(
        redis=app.state.redis,
        jwks_uri="https://idp.example.com/jwks",
        transport=_transport(handler),
    )
    assert result["keys"] == [jwk]


async def test_exchange_code_for_tokens_posts_the_expected_grant(app) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"id_token": "fake", "access_token": "fake"})

    result = await exchange_code_for_tokens(
        token_endpoint="https://idp.example.com/token",
        client_id="client-1",
        client_secret="secret-1",
        code="auth-code",
        redirect_uri="https://app.example.com/api/auth/sso/callback",
        code_verifier="verifier-1",
        transport=_transport(handler),
    )
    assert result["id_token"] == "fake"
    assert "grant_type=authorization_code" in str(captured["body"])
    assert "code=auth-code" in str(captured["body"])


async def test_exchange_code_for_tokens_raises_on_http_error(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(IdTokenVerificationError, match="Token exchange failed"):
        await exchange_code_for_tokens(
            token_endpoint="https://idp.example.com/token",
            client_id="client-1",
            client_secret="secret-1",
            code="bad-code",
            redirect_uri="https://app.example.com/api/auth/sso/callback",
            code_verifier="verifier-1",
            transport=_transport(handler),
        )


def test_verify_id_token_accepts_a_validly_signed_token() -> None:
    private_key, jwk = _rsa_keypair()
    id_token = _sign_id_token(
        private_key,
        claims={
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "email": "user@example.com",
            "nonce": "nonce-1",
        },
    )
    claims = verify_id_token(
        id_token=id_token, jwks={"keys": [jwk]}, issuer=_ISSUER, audience=_AUDIENCE, nonce="nonce-1"
    )
    assert claims["email"] == "user@example.com"


def test_verify_id_token_rejects_a_nonce_mismatch() -> None:
    private_key, jwk = _rsa_keypair()
    id_token = _sign_id_token(
        private_key,
        claims={"iss": _ISSUER, "aud": _AUDIENCE, "email": "user@example.com", "nonce": "nonce-1"},
    )
    with pytest.raises(IdTokenVerificationError, match="nonce"):
        verify_id_token(
            id_token=id_token,
            jwks={"keys": [jwk]},
            issuer=_ISSUER,
            audience=_AUDIENCE,
            nonce="a-different-nonce",
        )


def test_verify_id_token_rejects_wrong_issuer() -> None:
    private_key, jwk = _rsa_keypair()
    id_token = _sign_id_token(
        private_key,
        claims={"iss": "https://not-the-configured-issuer.com", "aud": _AUDIENCE, "nonce": "n"},
    )
    with pytest.raises(IdTokenVerificationError):
        verify_id_token(
            id_token=id_token, jwks={"keys": [jwk]}, issuer=_ISSUER, audience=_AUDIENCE, nonce="n"
        )


def test_verify_id_token_rejects_wrong_audience() -> None:
    private_key, jwk = _rsa_keypair()
    id_token = _sign_id_token(
        private_key, claims={"iss": _ISSUER, "aud": "some-other-client", "nonce": "n"}
    )
    with pytest.raises(IdTokenVerificationError):
        verify_id_token(
            id_token=id_token, jwks={"keys": [jwk]}, issuer=_ISSUER, audience=_AUDIENCE, nonce="n"
        )


def test_verify_id_token_rejects_a_signature_from_an_untrusted_key() -> None:
    private_key, _jwk = _rsa_keypair()
    # A second, unrelated keypair — _rsa_keypair() always assigns the same
    # constant kid, so the JWKS lookup finds this JWK by kid but its public
    # key does not match the signature the token actually carries.
    _other_private_key, other_jwk = _rsa_keypair()
    id_token = _sign_id_token(private_key, claims={"iss": _ISSUER, "aud": _AUDIENCE, "nonce": "n"})
    with pytest.raises(IdTokenVerificationError):
        verify_id_token(
            id_token=id_token,
            jwks={"keys": [other_jwk]},
            issuer=_ISSUER,
            audience=_AUDIENCE,
            nonce="n",
        )


def test_verify_id_token_raises_when_no_jwk_matches_the_kid() -> None:
    private_key, _jwk = _rsa_keypair()
    id_token = _sign_id_token(private_key, claims={"iss": _ISSUER, "aud": _AUDIENCE, "nonce": "n"})
    with pytest.raises(IdTokenVerificationError, match="No matching JWK"):
        verify_id_token(
            id_token=id_token, jwks={"keys": []}, issuer=_ISSUER, audience=_AUDIENCE, nonce="n"
        )
