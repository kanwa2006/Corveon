# Corveon — Architecture

Authoritative system design. Derived from the Master Implementation Blueprint v1.0 (+§23).
Resolved decisions are recorded as [ADRs](adr/); do not re-open them.

---

## 1. Component map

```
                         ┌─────────────────────────────────────────┐
                         │  FRONTEND (Next.js App Router, React 19)  │
                         │  Chat UI · Dashboards · Upload · Exports  │
                         └───────────────┬───────────────────────────┘
                                         │ HTTPS / SSE (stream + progress)
                         ┌───────────────▼───────────────────────────┐
                         │  API GATEWAY (FastAPI)                      │
                         │  Auth · RBAC · rate limit · request trace  │
                         └───────────────┬───────────────────────────┘
                                         │
             ┌───────────────────────────┼──────────────────────────────┐
   ┌─────────▼─────────┐   ┌─────────────▼────────────┐   ┌────────────▼───────────┐
   │ AI ORCHESTRATOR   │   │  DOMAIN SERVICES         │   │  ASYNC PIPELINE         │
   │ (custom graph)    │   │  Chats · Docs · Users    │   │  (ARQ workers + Redis)  │
   │ routing + policy  │   │  Analytics · Audit       │   │  upload→OCR→chunk→embed │
   └────────┬──────────┘   └──────────────┬───────────┘   └────────────┬───────────┘
   ┌────────▼──────────┐        ┌─────────▼─────────┐        ┌─────────▼──────────┐
   │ AGENT RUNTIME     │        │ DATA LAYER        │        │ EXTERNAL MED APIs  │
   │ specialized agents│        │ Postgres+pgvector │        │ openFDA·DailyMed·  │
   │ (single-resp.)    │        │ Redis · R2        │        │ RxNav·PubMed·CT.gov│
   └────────┬──────────┘        └───────────────────┘        └─────────┬──────────┘
   ┌────────▼───────────────────────────────────────────────────────┐ │
   │ PROVIDER-AGNOSTIC AI LAYER                                       │◄┘
   │ Gemini · Claude · OpenAI · OpenRouter · Ollama (pools/failover)  │
   └──────────────────────────────────────────────────────────────────┘
```

One line per component:
- **Frontend** — chat, dashboards, upload, exports; opens SSE against the backend.
- **API Gateway (FastAPI)** — authenticates, authorizes (RBAC + resource ownership), rate-limits,
  attaches a `trace_id`, and delegates. Thin; no business logic.
- **AI Orchestrator** — custom typed async state graph; the deterministic routing policy that
  decides which agents/retrieval/providers run, and when *not* to (ADR-0003).
- **Domain Services** — chats, documents, users, analytics, audit.
- **Async Pipeline** — ARQ workers on Redis for ingest/OCR/embed/verify/export/delete.
- **Agent Runtime** — single-responsibility agents implementing `run(state) -> state`.
- **Data Layer** — Postgres 16 + pgvector (source of truth & isolation), Redis (cache + queue),
  Cloudflare R2 (objects).
- **External Medical APIs** — openFDA, DailyMed, RxNav, PubMed/PMC, ClinicalTrials.gov, MeSH.
- **Provider-Agnostic AI Layer** — optional provider plugins with pools/failover/health.

## 2. Design principles
1. **Evidence before response.** Important statements carry provenance + confidence (§7 below).
2. **Assume documents are unreliable.** The evidence engine never trusts an upload by default.
3. **Determinism where safety lives.** Medication logic is a rules engine, not a prompt (ADR-0004/0005).
4. **Provider independence.** Business logic never names a provider; absence ≠ failure (ADR-0006).
5. **Absolute per-chat isolation.** No cross-chat/global read path (§5 below).
6. **Retrieve/compute only when it helps.** Anti-"always-on" for both RAG and the agent graph.
7. **Observable by construction.** Span + `trace_id` log on every path.

## 3. Representative request flow — "verify this uploaded treatment PDF"
1. Client uploads PDF → API returns `202 {job_id}`; SSE channel opens (backend, not Vercel).
2. Pipeline emits stage events: Uploading → Validating → Extracting → OCR (if scanned) → Cleaning
   → Chunking → Embedding → Indexing → Complete.
3. User asks a question → API calls the Orchestrator `{chat_id, query, available_artifacts}`.
4. **Query Understanding** agent → detects claim-verification intent + medication mentions.
5. Routing policy decides: RAG over uploaded doc = YES; trusted public evidence = YES;
   medication-safety = YES (drugs present); pure-LLM-only = NO.
6. **Retrieval** agent pulls this chat's vectors + queries openFDA/DailyMed/PubMed (cache-first);
   **Medication-Safety** agent normalizes to RxCUI and runs the rules engine.
7. **Evidence Verification** agent tags each statement by source class and scores confidence.
8. **Citation Verification** agent confirms every citation resolves to a real source.
9. **Response Generation** composes; **Response Review** + **Risk Assessment** gate it.
10. Answer streams back with a transparent `routing_trace` panel.

**Fast-path (§23.5):** trivial inputs (greetings, simple in-context follow-ups, pure formatting)
skip the agent graph and go straight to a single LLM call.

**Degraded mode (§23.1):** if no LLM provider is reachable, deterministic features still work
fully (rules engine, RxNorm, DDI/renal/Beers/STOPP-START, semantic search, upload, export);
LLM-dependent steps return a typed `provider_unavailable` result rendered as an empty state.

## 4. Data model (PostgreSQL 16 + pgvector)
All IDs UUID; all timestamps UTC. Every content-bearing table carries `chat_id`.

| Table | Purpose / notes |
|---|---|
| `organizations` | tenant root (name, plan) |
| `users` | email UNIQUE, password_hash (Argon2), role, org_id, is_active |
| `chats` | user_id, org_id, title, is_pinned, is_archived |
| `messages` | chat_id, role, content, `routing_trace` JSONB · index (chat_id, created_at) |
| `documents` | **chat_id mandatory (isolation anchor)**, filename, mime_type, status, page_count |
| `document_chunks` | document_id, **chat_id (denormalized)**, ordinal, text, token_count |
| `chunk_embeddings` | chunk_id, chat_id, `embedding vector(384)`, model_id · **HNSW index** |
| `images` | chat_id, document_id?, ocr_text |
| `saved_responses` / `notes` | chat_id, content |
| `trusted_sources` | org_id, type, name, config JSONB, version, is_active |
| `medications` | chat_id, raw_text, rxcui, name, dose, route, frequency |
| `medication_findings` | chat_id, type, severity, source, rule_id, explanation, provenance JSONB |
| `audit_log` | append-only: actor_id, action, entity, ip, metadata JSONB |
| `jobs` | chat_id, type, status, progress_stage, error |
| `external_cache` | key, source, payload JSONB, fetched_at, ttl |
| `drug_data_snapshots` | source, version, checksum, imported_at (reproducible pins) |

Embedding dimension `vector(384)` matches bge-small-en / e5-small. Every similarity query filters
by **both** `chat_id` and `model_id` (ADR-0008 / §23.4); model changes require a reindex job.

## 5. Per-chat isolation (defense in depth — §10.2)
1. **Application guard** — every query passes the active `chat_id`.
2. **Postgres Row-Level Security** — policies keyed on `chat_id`/`user_id`.
3. **Repository invariant** — the repository layer refuses any content query lacking a `chat_id`
   predicate. Cross-chat access requires an explicit user "import" that copies/links artifacts.

## 6. Orchestration & agents
- **Custom typed state graph** over a Pydantic state object (ADR-0003). Clean seam to adopt
  LangGraph later for a single complex flow without rewriting agents.
- Routing policy is a deterministic decision tree (pure LLM · RAG-uploaded · RAG-public ·
  hybrid · org-trusted · multi-agent · external-lookup) surfaced as `routing_trace`.
- Agents are single-responsibility, self-registering, schema-validated (catalog in §7 of the blueprint).
- **Throughput control (§23.2):** a per-request LLM-call budget + a shared token-bucket per
  provider; low-stakes agent steps prefer local Ollama to conserve scarce cloud quota.

## 7. Evidence & provenance
Each emitted statement gets exactly one source class:
**(a)** uploaded document · **(b)** verified public evidence · **(c)** org-trusted evidence ·
**(d)** AI reasoning · **(e)** conflicting/insufficient. Confidence (0–100) is a transparent
composite of source-class weight, cross-source agreement, recency vs guideline dates, and
citation-resolution success — documented, never a black box. Conflicts are surfaced with both
positions and dates, never silently resolved.

## 8. Deployment topology (free-tier MVP)
Vercel (frontend static/RSC) · Fly.io/Render (FastAPI API **and** ARQ worker — the persistent
process that serves all SSE, ADR-0007) · Supabase/Neon (Postgres+pgvector) · Upstash (Redis) ·
Cloudflare R2 (objects) · Gemini free / Ollama local (LLM). Details in [DEPLOYMENT.md](DEPLOYMENT.md).

## 9. Repository structure
```
backend/app/{api,orchestrator,agents,providers,evidence,medication,ingestion,data,core,workers}
backend/{migrations,tests}
frontend/{app,components,lib,tests}
infra/            docker, compose, CI, deploy, Grafana
data/loaders/     pinned drug-data snapshot loaders
docs/{,adr/}      this documentation set + decision records
.github/workflows CI/CD
```
Folder responsibilities are also enumerated in [`../CLAUDE.md`](../CLAUDE.md) §4.

## 10. Cross-cutting concerns
- **Security** → [SECURITY.md](SECURITY.md) (auth, isolation, prompt-injection, uploads, encryption, audit).
- **Observability** → [DEBUGGING.md](DEBUGGING.md) (OTel, Prometheus/Grafana, structlog, Sentry, health).
- **Config** → [ENVIRONMENT.md](ENVIRONMENT.md) (typed pydantic-settings, every env var).
- **Scale path** → [DEPLOYMENT.md](DEPLOYMENT.md) (worker pools, Qdrant past ~10M vectors, replicas, SSO).
