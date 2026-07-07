# Corveon — Phased Build Roadmap

Respects the strict per-feature order (Architecture → Database → API → Backend → Frontend →
Testing → Docs). Each phase ends with all relevant test layers green in CI. Buildable on free infra.

## Phase 0 — Foundation ✅ (this repository)
Repository structure, standards, documentation set, CLAUDE.md, ADR log, CI/CD skeleton, env
contract. No application code. Self-review complete.

## Week 1 — MVP core
- Auth + users (OAuth2/JWT, Argon2, RBAC).
- Chat CRUD with **per-chat isolation** (app guard + RLS + repo invariant).
- Single-provider chat (Gemini free / Ollama) with **SSE streaming** from the backend.
- PDF upload → parse → chunk → embed → **in-chat** semantic search.
- Minimal dashboard.
- Core tests + CI green; Alembic baseline + models↔migrations sync check.

## Month 1 — Provider layer & orchestration
- Provider-agnostic layer: key pools, failover, health, token-bucket, **degraded/absent-provider
  handling** (§23.1).
- Orchestrator + deterministic routing policy + `routing_trace`; **fast-path** (§23.5);
  per-request LLM budget (§23.2).
- Multi-format ingestion (DOCX/PPT/MD/images + OCR).
- Export (MD/PDF).
- Observability stack (OTel + Prometheus + Grafana + Sentry + structured logs).
- Expanded test matrix.

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
