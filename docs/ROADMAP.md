# Corveon — Phased Build Roadmap

Respects the strict per-feature order (Architecture → Database → API → Backend → Frontend →
Testing → Docs). Each phase ends with all relevant test layers green in CI. Buildable on free infra.

## Phase 0 — Foundation ✅ (this repository)
Repository structure, standards, documentation set, CLAUDE.md, ADR log, CI/CD skeleton, env
contract. No application code. Self-review complete.

## Week 1 — MVP core
- ✅ Auth + users (OAuth2/JWT, Argon2, RBAC) — backend (register/login/refresh/logout/me) +
  frontend (login/register, httpOnly-cookie session via BFF proxy, ADR-0012).
- ✅ Chat CRUD with **per-chat isolation** (app guard + Postgres RLS, verified with a genuine
  cross-user bypass-attempt test + repo invariant, ADR-0013) — backend (create/list/get/rename/
  pin/archive/delete) + frontend (chat list with search/filter, chat detail, dashboard preview).
- ✅ Single-provider chat (Gemini + Ollama, ADR-0006 registry) with **SSE streaming** direct from
  the backend (ADR-0007), bridged from the httpOnly-cookie session via a short-lived stream ticket
  (ADR-0016) — backend (fast-path/RAG-grounded orchestrator slice) + frontend (message thread,
  streaming composer).
- ✅ PDF upload → parse → chunk → embed → **in-chat** semantic search — backend (ARQ ingestion
  pipeline: validate/extract/chunk/embed/index; pgvector HNSW search filtered by `chat_id` +
  `model_id`, ADR-0008/0015) + frontend (upload with live per-stage progress, document list).
- ✅ Minimal dashboard (auth landing page + recent-chats preview; message UI now live on the chat
  detail page).
- ✅ Core tests + CI green — backend (ruff/format/mypy --strict/pytest 155 passed/Alembic sync
  check/bandit/pip-audit), frontend (lint/typecheck/38 unit tests/build), and a full-stack
  Playwright **e2e + a11y** job (14/14) wired into CI against a live Postgres+Redis+backend+worker.

## Month 1 — Provider layer & orchestration
- ✅ Provider-agnostic layer: key pools, failover, **health monitoring + circuit breaker**
  (`app/providers/health.py`), per-provider **token-bucket** rate limiting + per-request **LLM call
  budget** (`app/providers/budget.py`), provider call metrics/structured logging
  (`app/providers/metrics.py`), **degraded/absent-provider handling preserved** (§23.1/§23.2). All
  five catalog providers now adapt: Gemini, Ollama, **Anthropic** (Messages API), and **OpenAI** /
  **OpenRouter** (shared OpenAI-compatible base, `app/providers/openai_compatible.py` —  one adapter
  per wire protocol, not per vendor) — each registered only when its key pool is configured.
- ✅ Orchestrator + deterministic routing policy + `routing_trace`; **fast-path** (§23.5); per-request
  LLM budget enforced. A 4-way routing policy (`fast_path` / `pure_llm` / `rag_grounded` /
  `rag_no_match`) built from a Query Understanding step (`classify_intent`) and a Task Planning step
  (`_plan_task`) — honestly scoped to the two subsystems that exist today (chat + documents); the
  other five blueprint branches (public evidence, org-trusted, multi-agent verification, external
  lookup) land as new steps in the same pipeline once Month 3/6-12 build the subsystems they need,
  not a rewrite.
- ✅ Multi-format ingestion (DOCX/PPT/MD/images + OCR). A MIME-keyed parser registry
  (`app/ingestion/parsing.py::parse_document`) dispatches to `parse_pdf` / `parse_docx` /
  `parse_pptx` / `parse_markdown` / `parse_image`; scanned (image-only) PDF pages fall back to
  Tesseract OCR automatically. The upload endpoint derives the canonical MIME type from the file
  extension (not the client's `Content-Type`, which is inconsistent across browsers for less-common
  types) and validates with per-format magic bytes or UTF-8 decodability.
- ✅ Export (MD/PDF). `POST /chats/{id}/messages/{mid}/export {format: md|pdf}` — synchronous
  (`app/export/message_export.py`), preserving citations (from `routing_trace.retrieved_chunks`)
  and metadata (role, timestamp, routing path/provider/status). PDF uses fpdf2's core Latin-1 font
  with a documented transliteration fallback for out-of-range characters (no bundled Unicode font).
- ✅ Observability: append-only **audit log** (`app/data/models/audit_log.py`, migration `0004`) —
  actor/action/entity/IP/metadata, wired into every sensitive action named in CLAUDE.md §8
  (register/login/logout, document upload/delete, message export) via `AuditLogRepository`, verified
  by querying the table directly (`tests/database/test_audit_log.py`, no admin-read endpoint yet).
  Per-provider-attempt and per-request OTel spans (`provider.stream_chat`, `orchestrator.plan_task`,
  `orchestrator.generate_response`) added alongside the existing Prometheus counters/histograms and
  structlog `trace_id` propagation from Week 1. Grafana dashboards and Sentry wiring stay out of
  scope until there's a deployed environment to point them at — building unusable config against
  nothing would violate the "no half-finished implementations" rule, not satisfy it.
- ✅ Expanded test matrix: the two test layers `docs/DEVELOPER.md` had declared (dependencies
  installed, never wired) are now real. **API contract** (`schemathesis`, CI job `contract`):
  property-based fuzzing against the live OpenAPI schema, scoped to the `not_a_server_error` check —
  it caught a genuine bug (see CHANGELOG: `validation_error_handler` itself crashing into a 500 on
  certain malformed input). Broader checks (`status_code_conformance` etc.) were evaluated and
  rejected for CI: they flag every route returning a correct-but-undocumented 401/404/422, which is
  an OpenAPI-metadata completeness gap across ~20 endpoints, not a contract violation — fixing that
  honestly is its own bounded follow-up, not something to bundle in here. **Performance** (`locust`,
  same CI job): a concurrency smoke — asserts zero request failures under 5 concurrent simulated
  users, not a latency gate (shared CI runners don't give reproducible latency numbers; run
  `locust -f tests/performance/locustfile.py --host <url>` locally for real numbers). The
  `tests/integration` layer in `docs/DEVELOPER.md`'s table is intentionally not a separate suite —
  `tests/api`, `tests/database`, and `tests/security` already run against real Postgres+Redis
  (GitHub Actions services), which is what that layer is actually for; adding a parallel
  Testcontainers-spun Postgres would duplicate infrastructure, not coverage.

## Month 3 — Evidence Verification Engine
- Public sources (openFDA, DailyMed, RxNav, PubMed/PMC, ClinicalTrials.gov, MeSH), cache-first.
- Source-class provenance tagging, transparent confidence scoring, **misinformation/outdated/
  fabrication detection**, conflict surfacing.
- Org-trusted sources (versioned, access-scoped connectors).
- Citation verification (fabricated-citation guard).
- Premium dashboards/analytics; RLS hardening; audit logging.

## Month 6–12 — Medication-Safety Engine (full) & enterprise
- RxNorm normalization + **DDInter 2.0** (pinned) with **openFDA fallback** (ADR-0004).
- **Dual renal equations** — Cockcroft-Gault + 2021 race-free CKD-EPI, divergence flags (ADR-0005).
- **Beers 2023** + **STOPP/START v3** screens; medication-discrepancy classification.
- Guardrailed LLM explanations (no ungrounded facts).
- Multi-agent depth; enterprise path (Qdrant option, SSO, read replicas, on-prem/Ollama).
- Accessibility + performance audits; reproducible snapshot automation.

## Cross-cutting, always-on
Per-feature Definition of Done · docs updated per PR · ADR per resolved decision · golden tests for
rules · no cross-chat reads · no hardcoded providers · no confident answers on suspected misinformation.
