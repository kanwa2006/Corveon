# ADR-0007: SSE served by the FastAPI backend, never Vercel serverless

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
Corveon streams tokens and long job-progress events over Server-Sent Events. Serverless functions
cap execution time, which conflicts with long-lived streams and long-running jobs (§23.3).

## Decision
All SSE streaming and job-event channels are served by the **FastAPI backend running as a persistent
process** (Fly.io / Render), never from Vercel serverless functions. Vercel hosts only the
static/RSC frontend, which opens SSE connections against the backend
(`NEXT_PUBLIC_SSE_BASE_URL` → backend). Long work runs in ARQ workers; the client subscribes to
`GET /api/v1/jobs/{id}/events`.

## Consequences
- Removes a real production failure mode (streams cut off at the serverless timeout).
- Clear separation: Vercel = frontend delivery; backend host = all persistent connections and compute.
- Tradeoff: the backend host must support long-lived connections (Fly/Render do).

## Alternatives considered
- **SSE from Vercel functions:** even with raised timeouts, wrong tool for indefinite streams.
- **WebSockets everywhere:** heavier than needed; SSE fits one-way token/progress streaming and pairs
  cleanly with FastAPI's native SSE support.
