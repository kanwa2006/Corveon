# ADR-0016: Short-lived stream ticket bridges httpOnly-cookie auth to direct-to-backend SSE

- **Status:** Accepted
- **Date:** 2026-07-08

## Context
ADR-0012 adopted httpOnly cookies for the frontend session and explicitly deferred one open
question to this feature: ADR-0007 requires the browser to open SSE connections **directly**
against the FastAPI backend (never proxied through a Vercel Route Handler, which would reintroduce
the serverless-timeout problem ADR-0007 exists to avoid) — but the httpOnly session cookie is
scoped to the Next.js origin and JS cannot read it to attach it to a cross-origin request, and
native `EventSource` cannot attach a custom `Authorization` header even if JS could.

This feature adds two endpoints the browser must reach directly: `POST /chats/{id}/messages`
(chat streaming) and `GET /jobs/{id}/events` (ingestion progress).

## Decision
A Next.js Route Handler (`POST /api/stream-ticket`), authenticated the normal cookie/`backendFetch`
way, calls a new backend endpoint `POST /api/v1/auth/stream-ticket` that mints a **stream ticket**:
a normal-shaped JWT (`TokenType.STREAM`) with a 60-second TTL, tied to the same user. The Route
Handler returns just the ticket value (not a cookie) to the browser, which appends it as a
`?ticket=` query parameter on its direct request to the backend.

A new dependency, `get_streaming_user` (`app/api/deps.py`), is wired into **only** these two
endpoints in place of `get_current_user`: it accepts the normal `Authorization` header (delegating
to `get_current_user` unchanged) **or**, only when no header is present, a `?ticket=` query
parameter decoded strictly as `TokenType.STREAM`. Every other endpoint is untouched — a normal
(15-minute) access token never gains query-string acceptance anywhere.

## Consequences
- Both SSE endpoints are reachable directly by the browser, satisfying ADR-0007, without ever
  exposing the real session-backing access token in a URL, browser history, or server access log —
  only a 60-second, single-purpose ticket is exposed that way.
- No change to the existing cookie/`backendFetch` pattern for any non-streaming endpoint.
- Tradeoff: one extra round trip (mint ticket, then open the stream) before a message send or a
  progress subscription starts — negligible next to an LLM call or a document-parse job.

## Alternatives considered
- **Hold the access token in memory (frontend) and send it directly:** the other candidate ADR-0012
  named. Rejected because it still doesn't solve `EventSource`'s header limitation, and it would
  hand the real, longer-lived access token to client JS at all — a strictly worse blast radius than
  a purpose-built 60-second ticket, for no simplicity gain (the round trip is the same either way).
- **Relay SSE through a Next.js Route Handler:** simplest to wire, but reopens exactly the
  serverless-timeout problem ADR-0007 rejected — not on the table.
