# Corveon — Observability & Debugging

Directly attacks the "poor observability / difficult debugging" failure category. All tooling is
open-standard with free tiers that cover the MVP (§16).

## The stack
- **Structured logs** — `structlog` JSON; every request/job log carries a `trace_id`.
- **Tracing** — OpenTelemetry spans across API → orchestrator → agents → providers → DB. **Each
  agent call and each provider call is its own span**, so a slow/failed provider is instantly visible.
- **Metrics** — Prometheus: request latency, error rates, queue depth, job durations, per-provider
  success/latency/quota, embedding/search timings, upload metrics. Grafana dashboards in `infra/grafana/`.
- **Error tracking** — Sentry (free tier) with source context; disabled when `SENTRY_DSN` is blank.
- **Health** — `GET /health` (liveness), `GET /ready` (DB / Redis / provider readiness).

## The debugging workflow (from CLAUDE.md §10)
1. **Reproduce** the issue.
2. **Check the trace** — find the `trace_id` in logs; open the span tree; locate the failing/slow span.
3. **Check provider health** — `/ready` and per-provider metrics; is a provider quarantined/circuit-broken?
4. **Check the job stage** — for pipeline issues, read `jobs.progress_stage` and the worker heartbeat.
5. **Write the failing test first**, then fix. Never paper over an error with a bare fallback.

## Common scenarios
| Symptom | First look |
|---|---|
| Slow response | span durations — which agent/provider/DB call dominates? |
| Upload stuck | `jobs.progress_stage` + worker heartbeat; retries/backoff exhausted? |
| Empty/`provider_unavailable` answer | provider health; is this expected degraded mode (§23.1)? |
| Wrong/irrelevant retrieval | confirm `chat_id` AND `model_id` filters; embedding model mismatch (§23.4)? |
| Cross-chat data appears | **stop** — isolation invariant breach; check app guard + RLS + repo predicate |
| Fabricated citation slipped through | citation-verification agent + resolution check; add a regression test |
| Free-tier throttling under load | per-request LLM budget + token-bucket (§23.2); prefer Ollama for low-stakes steps |

## Adding observability to new code
Every new code path must add:
- an OpenTelemetry span (name it for the operation; record key attributes, not secrets), and
- a structured log line carrying the request/job `trace_id`.
Add Prometheus metrics on any new hot path (latency histogram + error counter).

## Local observability
`docker compose -f infra/docker-compose.yml` can be extended with an OTLP collector + Prometheus +
Grafana for local trace/metric inspection; set `OTEL_EXPORTER_OTLP_ENDPOINT` accordingly.
