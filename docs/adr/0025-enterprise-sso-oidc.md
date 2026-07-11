# ADR-0025: Enterprise SSO via OIDC, org-scoped, SAML deferred

- **Status:** Accepted
- **Date:** 2026-07-11

## Context
"Enterprise path" (blueprint, `docs/ROADMAP.md`) lists SSO as its last unimplemented item —
Qdrant (ADR-0022), a read replica (ADR-0023), and Ollama-only deployment mode (ADR-0024) are
already done. An enterprise customer wants their users to authenticate through their own identity
provider (Okta, Azure AD, Google Workspace, etc.) instead of — or in addition to — Corveon's local
email+password auth, scoped to their `organizations` row so one org's SSO configuration never
authenticates a user into a different org.

Two protocol families are commonly meant by "enterprise SSO": OIDC (OAuth2-based, JSON/JWT) and
SAML (XML-based, older, still required by some enterprises). They are architecturally unrelated —
different wire formats, different crypto (JWT signatures vs. XML digital signatures), different
metadata exchange. Building both correctly in one PR is a materially larger and riskier
undertaking than everything else in "Enterprise path" combined.

## Decision
Implement **OIDC only** (Authorization Code flow + PKCE), the more modern and more commonly
supported protocol among the two, and design the seam so SAML can be added later as a second
implementation without touching this one — the same "clean seam, one protocol now" shape as
ADR-0001 (pgvector now, Qdrant later) and ADR-0006 (provider registry).

**Org routing is by email domain, not org ID/slug.** A user enters their email on the login page;
the backend looks up `org_sso_configs.email_domain` (unique) to find which org's IdP to redirect
to. This matches real-world "Continue with SSO" UX (Slack, Notion, etc.) and never requires a user
to know or expose an internal org identifier.

**Flow:**
1. `POST /auth/sso/start {email}` — looks up the org config by email domain; `404` if none
   configured. Generates `state`, PKCE `code_verifier`/`code_challenge` (S256), and a `nonce`;
   stores `{code_verifier, nonce, org_id}` in Redis keyed by `state`, TTL 300s, single-use. Returns
   `{redirect_url}` (the IdP's authorization endpoint, from OIDC discovery) for the frontend to
   navigate to.
2. IdP authenticates the user, redirects the browser to `GET /auth/sso/callback?code=&state=`.
3. Backend validates `state` against Redis (CSRF protection, deletes it — single use), exchanges
   `code` for tokens at the IdP's token endpoint (PKCE `code_verifier`, `client_id`,
   `client_secret`), verifies the returned `id_token`'s signature via the IdP's JWKS (fetched over
   `httpx`, RS256 only, `iss`/`aud`/`exp`/`nonce` all checked) and extracts `email`.
4. JIT-provisions the `User` (creates on first login, scoped to the config's `org_id`,
   `password_hash=NULL`) or finds an existing one by email — **rejects if an existing user's
   `org_id` doesn't match the authenticating org's**, so a misconfigured or malicious IdP can never
   move a user across the isolation boundary.
5. Mints a normal session via the **existing** `create_access_token`/`create_refresh_token`
   (`app/core/security.py`) — identical `TokenResponse` shape as password login, so the frontend
   BFF's existing cookie-setting code (ADR-0012) needs zero changes, and every other part of the
   app is unaware a user authenticated via SSO at all.

**Data model:** new `org_sso_configs` table (`org_id` UNIQUE FK, `provider_type` — always `"oidc"`
today, `issuer`, `client_id`, `client_secret_encrypted`, `email_domain` UNIQUE, `is_active`) —
mirrors the shape already documented (but unbuilt) for `trusted_sources`
(`org_id`/`type`/JSONB-ish config/`is_active`, `docs/ARCHITECTURE.md` §4). `users.password_hash`
becomes nullable — an SSO-only user has none; `login()` rejects with a clear message rather than a
generic auth failure when it's `NULL`.

**Client secret at rest:** encrypted with Fernet (`cryptography`, already a transitive dependency,
now declared explicitly) under a new `SSO_CONFIG_ENCRYPTION_KEY` setting — checked only when an
org actually saves an SSO config (not a blanket `Settings` validator, since SSO itself is optional
per-org, matching every other optional subsystem's posture). This is a deliberate, narrow exception
to "secrets via env only" (CLAUDE.md §8): an OIDC client secret is **tenant-configured integration
data**, not an application secret — it cannot be a single env var in a multi-tenant deployment. It
is never returned by `GET /org/sso-config` (write-only field, same posture as a password hash).

**Config management:** `POST/GET/DELETE /org/sso-config`, `org-admin`/`superadmin` only, always
scoped to the caller's own `org_id` (never accepted from the request body — prevents a compromised
admin token from writing another org's config).

**Frontend scope, this PR:** both the end-user login flow — a "Sign in with SSO" entry point on the
login page (email → redirect) and the callback route that sets cookies exactly like password login
— **and** a production-ready org-admin settings page (`/settings/sso`) for
`POST/GET/DELETE /org/sso-config`, built from the existing design system (`Card`, `Button`, `Input`,
`Label`, `Dialog`, `AlertError`/`AlertSuccess`) rather than the "documented API, UI deferred"
posture `/org/trusted-sources` used. SSO configuration is the one org-admin action this milestone
adds, and a raw-API-only workflow for entering a client secret was judged too rough for a
production-facing feature; unlike `/org/trusted-sources`, this doesn't set a new precedent — no new
admin framework was introduced, only existing settings/form/layout patterns reused.

## Consequences
- Zero behavior change for any org that never configures SSO — password login is completely
  unaffected, `password_hash` stays populated for every existing/normal user.
- JWKS/discovery fetches are async (`httpx`, matching every other external client in this codebase)
  and Redis-cached via a new `app/sso/cache.py` mirroring `app/medication/cache.py`'s
  `get_or_fetch` shape exactly (deliberately not shared — same reasoning as that module's own
  docstring: domains don't couple to one shared cache module's evolution).
- SAML is not implemented. Revisit if an enterprise customer specifically requires it — the
  `provider_type` column and the callback's "verify assertion → JIT-provision → mint session" shape
  already anticipate a second implementation without a redesign.
- No RLS policy is added for `org_sso_configs` — unlike `chats`/`documents` (ADR-0013), this table
  is never read from a per-user request path directly; it's read once by the `/auth/sso/start`
  lookup (unauthenticated, by design — a user isn't logged in yet) and by the admin CRUD endpoints
  (already RBAC + own-org scoped at the application layer). Per-chat-isolation's RLS posture is
  about chat *content*; this is account-provisioning configuration, a different threat model.
- Playwright e2e coverage in this PR is the login-page SSO entry point only (email input, routing
  to a 404/"not configured" state) — a full browser round-trip through a real or mock external IdP
  is out of scope for this PR's e2e infra; the actual callback logic (state/nonce/PKCE/JWKS
  verification/JIT provisioning/cross-org rejection) is thoroughly covered by backend API tests
  against a mocked IdP (`httpx.MockTransport`, the same pattern already used for every other
  external service in this codebase).

## Alternatives considered
- **Both OIDC and SAML in this PR:** rejected — SAML's XML signing/canonicalization/metadata
  surface is a materially different, larger, separately-reviewable body of work; bundling it here
  would violate "one atomic milestone per PR."
- **Org routing by URL slug/ID instead of email domain:** rejected — requires a user to know or be
  told an internal identifier before they can even start logging in; email-domain routing is the
  standard UX and needs no new user-facing concept.
- **A synchronous `PyJWKClient` (pyjwt's built-in JWKS helper) wrapped in `asyncio.to_thread`:**
  rejected — this codebase's external-client convention is a hand-rolled async `httpx` client with
  Redis caching (RxNorm, openFDA, all six evidence connectors); matching that convention was judged
  more valuable than reusing pyjwt's synchronous convenience wrapper.
- **API-only config management, UI deferred (the `/org/trusted-sources` precedent):** reconsidered
  and rejected — SSO configuration is an org-admin-facing production workflow (entering a client
  secret, an issuer URL, an email domain), not an internal/rarely-touched setting; a settings page
  was built in this PR instead, reusing existing form/layout/settings patterns rather than
  introducing a new admin framework.
