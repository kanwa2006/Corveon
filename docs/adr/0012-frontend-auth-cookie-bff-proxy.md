# ADR-0012: httpOnly-cookie session via Next.js Route Handler BFF proxy

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
The backend issues JWT access/refresh tokens (§11, `docs/API.md`). The frontend needs to hold
that session client-side without exposing tokens to JS-accessible storage (XSS risk), and needs
route-level UX guarding (redirect unauthenticated users away from protected pages).

A pure client-side model (tokens in `localStorage`/Zustand) is simple but exposes both tokens to
any injected script. A pure httpOnly-cookie model is more secure but creates a real tension with
**ADR-0007** (SSE streams connect the browser directly to the FastAPI backend, a different origin
in the general deployment case) — `EventSource` cannot attach custom headers or reliably carry a
cross-origin httpOnly cookie, so a cookie scoped to the Next.js origin doesn't by itself authorize
a direct-to-backend SSE connection.

## Decision
For this feature (auth only — no SSE endpoints exist yet), adopt the secure httpOnly-cookie
model in full:
- Next.js **Route Handlers** (`app/api/auth/{register,login,refresh,logout,me}/route.ts`) proxy
  every auth call to the FastAPI backend server-to-server. The browser never receives a raw JWT.
- `POST /api/auth/login` sets two httpOnly, `SameSite=Lax` cookies (`corveon_access`,
  `corveon_refresh`); `POST /api/auth/logout` clears them and best-effort revokes the refresh
  token server-side.
- A shared server-only `backendFetch()` helper attaches the access cookie to backend calls and
  transparently retries once via `/auth/refresh` on a 401.
- `proxy.ts` (Next.js 16's renamed `middleware.ts`) checks cookie **presence only** to redirect
  between `/login` and `/dashboard` — this is a UX nicety, not the authorization boundary. Real
  authorization is always enforced by FastAPI validating the bearer token on every request.
- **The SSE-authorization bridge is explicitly deferred** to the Chat feature, where a concrete
  streaming endpoint will exist to design against. Candidates already scoped for that decision:
  a short-lived signed "stream ticket" minted by a Route Handler and passed as an `EventSource`
  query parameter, or holding the access token in memory (not persisted) so the browser can send
  it directly. Revisit this ADR (or add a superseding one) when that feature starts.

## Consequences
- Tokens never touch `localStorage` or JS-readable storage — meaningfully reduces XSS blast
  radius today.
- Every current REST auth flow (register/login/refresh/logout/me) is fully proxied and cookie-
  protected now; no rework needed for those endpoints when the Chat feature lands.
- The pattern established here (`backendFetch`, shared `lib/session.ts` constants) is the seam
  future proxied endpoints (chats, documents) will extend — same helper, same cookie.
- Tradeoff accepted: the SSE bridge is a known, tracked open question, not a solved one. The Chat
  feature must not start streaming work without resolving it first.

## Alternatives considered
- **Zustand + localStorage tokens:** simplest, fewest moving parts, but leaves both tokens
  exposed to any injected script — rejected once "production-ready" auth was requested.
- **Full ticket-based SSE bridge now:** most complete, but designed a mechanism for an endpoint
  that doesn't exist yet in this codebase — premature; revisit with real SSE code in front of us.
