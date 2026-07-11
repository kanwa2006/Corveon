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
| `medications` | chat_id, raw_text, rxcui?, name, dose?, route?, frequency? |
| `medication_findings` | chat_id, medication_a_id, medication_b_id?, type, severity, source, rule_id, explanation, provenance JSONB |
| `audit_log` | append-only: actor_id, action, entity, ip, metadata JSONB |
| `jobs` | chat_id, type, status, progress_stage, error |
| `evidence_verifications` | chat_id, message_id, status (pending/running/succeeded/failed), error |
| `evidence_claims` | chat_id, verification_id, ordinal, text, source_class, confidence_score, confidence_rationale, flags JSONB |
| `evidence_citations` | chat_id, claim_id, source, title, url, identifier, snippet, published_date, supports_claim, resolved |
| `drug_data_snapshots` | source, version, checksum, row_count (reproducible pins, not chat-scoped) |
| `drug_interactions` | snapshot_id, drug_a_name, drug_b_name (sorted pair), severity, description (not chat-scoped) |

External-connector responses are cached in Redis, not a Postgres table — see
[ADR-0017](adr/0017-evidence-cache-via-redis-not-postgres-table.md).

Embedding dimension `vector(384)` matches bge-small-en / e5-small. Every similarity query filters
by **both** `chat_id` and `model_id` (ADR-0008 / §23.4); model changes require a reindex job.

**Pluggable vector store** (`app/data/vectorstore/`, ADR-0001, ADR-0022): pgvector (above) is the
default; **Qdrant** is a config-selected (`VECTOR_STORE=qdrant`) alternative for enterprise
deployments past pgvector's ~10M-vector comfort zone, or already running a Qdrant cluster.
`ChunkRepository` depends only on a `VectorStore` interface (`upsert`/`search`/`has_vectors`/
`embedded_chunk_ids`, keyed by `chat_id`+`model_id` exactly like the SQL predicate above) — business
logic (search endpoint, RAG retrieval, evidence retrieval, ingestion, reindex) never names a
concrete vector-store backend, mirroring the "business logic never names a provider" AI-provider
pattern (ADR-0006). Chunk
*text* always lives in Postgres regardless of which backend stores the embeddings.

**Optional read replica** (`app/data/base.py`, ADR-0023): `DATABASE_READ_REPLICA_URL` is unset by
default (every read stays on the primary); when set, `Database` builds a second engine/session
factory and pure-read endpoints (currently `POST /chats/{id}/search`, via `ReadOnlyRlsDbDep`) use it
instead. The RLS GUC (below) is per-connection session state, never replicated — a replica session
gets its own `set_rls_user` call each request, identical to the primary.

## 5. Per-chat isolation (defense in depth — §10.2)
1. **Application guard** — every query passes the active `chat_id`.
2. **Postgres Row-Level Security** — policies keyed on `chat_id`/`user_id`.
3. **Repository invariant** — the repository layer refuses any content query lacking a `chat_id`
   predicate. Cross-chat access requires an explicit user "import" that copies/links artifacts.

## 6. Orchestration & agents
- **Custom typed state graph** over a plain dataclass state object (`app/agents/state.py`,
  ADR-0003). Clean seam to adopt LangGraph later for a single complex flow without rewriting agents.
- Routing policy is a deterministic decision tree, five of the blueprint's seven named branches
  implemented today: fast-path (trivial input) · pure-LLM (no chat documents, no public evidence
  found either) · RAG-uploaded/grounded · RAG-uploaded/no-match · **RAG-public-evidence** (no chat
  documents, but a public-evidence search found something — `PublicEvidenceAgent`,
  `app/agents/public_evidence.py`, ADR-0021). Org-trusted sources and full multi-agent verification
  remain future work. Every outcome is surfaced as `routing_trace` on the persisted message.
- Agents (`app/agents/`, `Agent` protocol in `base.py`) are single-responsibility, schema-validated
  steps over the shared state: Query Understanding → Task Planning → Retrieval **or** Public
  Evidence Retrieval → Response Generation (`app/orchestrator/chat_orchestrator.py` wires them).
  `PublicEvidenceAgent` reuses the Evidence Verification Engine's own connector registry and
  retrieval function verbatim (`app/evidence/retrieval.py::retrieve_evidence_for_claim`) — no
  parallel retrieval logic, no new connector code (ADR-0021).
- **Throughput control (§23.2):** a per-request LLM-call budget + a shared token-bucket per
  provider; low-stakes agent steps prefer local Ollama to conserve scarce cloud quota. Public
  evidence retrieval costs zero additional LLM calls (it's a deterministic connector fan-out, not a
  model call) but does add up to six concurrent HTTP round-trips before generation — mitigated by
  the same Redis cache already in front of every connector (`EVIDENCE_CACHE_TTL_SECONDS`).

## 7. Evidence & provenance
Implemented Month 3 (`app/evidence/`, `POST /chats/{id}/verify` — see [API.md](API.md)). Each
extracted claim gets exactly one source class: **(a)** uploaded document · **(b)** verified public
evidence · **(c)** org-trusted evidence · **(d)** AI reasoning · **(e)** conflicting/insufficient.
`org_trusted` is a real, reserved classification — no claim is tagged with it until the
org-trusted-sources subsystem (still planned) exists to produce it. Confidence (0–100) is a
transparent, deterministic (no LLM) composite of source-class weight, cross-source agreement,
recency vs guideline dates, and citation-resolution success — always reconstructable from its own
rationale string, never a black box. Conflicts are surfaced with both positions, never silently
resolved toward one side. Six public connectors (PubMed, DailyMed, openFDA, ClinicalTrials.gov,
MeSH, RxNorm) plus this chat's own uploaded-document chunks feed retrieval; a citation is only ever
shown once it resolves to a real record at its source (fabricated-citation guard,
`app/evidence/citation_verification.py`) — never LLM-generated.

## 8. Medication-Safety Engine
Phase 1 + Phase 2 + Phase 3 implemented Month 6-12 (`app/medication/`,
`POST /chats/{id}/medications/analyze` — see [API.md](API.md)): free-text medication parsing (LLM,
guardrailed to extract only name/dose/route/frequency already present in the text — never infers or
adds a fact), RxNorm/RxCUI normalization, deterministic drug-drug interaction detection (Phase 1),
deterministic renal-dosing threshold checks (Phase 2), deterministic potentially-inappropriate-
prescribing screening and medication-discrepancy classification (Phase 3), plus an optional,
guardrail-checked LLM narrative on top of the two Phase 3 finding types. **The rules engine is the
source of truth** (CLAUDE.md §6) — DDI detection, renal checks, PIP screening, and discrepancy
classification never make an LLM call; only free-text parsing (mandatory) and narrative generation
(optional, degrades silently) do.

DDInter 2.0 (ADR-0004) is the primary DDI source, loaded as a pinned, checksummed snapshot
(`app/medication/ddinter_loader.py`, never fetched at request time,
[ADR-0018](adr/0018-ddinter-loader-location-and-no-bundled-dataset.md)); openFDA label-derived text
is the fallback for pairs the snapshot doesn't cover, surfaced as the FDA's own label language
(`FindingSeverity.UNCLASSIFIED`) rather than a synthesized severity the source didn't provide.

Renal checks (`app/medication/renal.py`, ADR-0005) implement **both** kidney-function equations
rather than picking one, since the clinical standard is actively in transition: Cockcroft-Gault CrCl
(the historical FDA/label standard) and the 2021 race-free CKD-EPI eGFR (de-indexed to the patient's
own body surface area for dosing use). The four renal-only parameters (weight/sex/serum creatinine/
height) are optional and all-or-nothing together, and require `age_years`; omitting all of them
skips renal checks entirely (an honest "insufficient data" state); supplying a partial set is a
`422`, not a silent skip. Only a small, documented set of threshold-sensitive drug classes (DOACs,
aminoglycosides, vancomycin — the blueprint's own named examples) are checked; a finding's severity
distinguishes clear impairment (both equations agree) from the genuine "standard in flux" case
ADR-0005 exists for (the two equations land on opposite sides of the decision threshold).

**PIP screening** (`app/medication/pip_screening.py`, ADR-0019) checks the current medication list
against every pinned AGS Beers Criteria 2023 / STOPP/START v3 row (`pip_criteria`, loaded the same
pinned-snapshot way as DDInter — `app/medication/pip_loader.py`) whenever the request supplies
`age_years` (independent of whether renal checks are also requested) and the patient is ≥65. AVOID
criteria (every Beers row, and STOPP's condition-gated rows) fire when the patient takes a listed
drug and — if condition-gated — a supplied free-text `conditions` string matches (case-insensitive
substring) one of the criterion's keywords. START_CONSIDER criteria fire on the opposite condition:
a matching condition **and no listed drug present anywhere in the current list** — an omission
finding with no medication to anchor to, which is why `medication_findings.medication_a_id` is
nullable as of this phase.

**Discrepancy classification** (`app/medication/discrepancy.py`, ADR-0019) diffs two independently
parsed-and-normalized medication lists — the request's `raw_text` (current) and, when supplied,
`previous_raw_text` — by RxCUI first, normalized name as fallback, producing `added`/`omitted`/
`dose_changed`/`frequency_changed` findings. This costs one additional, independent LLM parse call
(same budget as the primary parse).

**Guardrailed narrative** (`app/medication/explanation_guardrail.py`, ADR-0020) is an optional,
additive plain-language rendering layered only on top of PIP and discrepancy findings — Phase 1/2's
`explanation` fields are already deterministic strings with no LLM involvement and thus nothing for
a guardrail to check. One batched LLM call (not one per finding) proposes a narrative per finding;
a deterministic post-generation check (`check_narrative_grounded`) discards any narrative that
introduces a medication name outside the finding's own set, a number absent from the finding's own
data, an escalation/severity word, or an unlicensed clinical-directive phrase. A finding's
`explanation` is always shown regardless of whether its `narrative` passed.

**Reproducible snapshot automation** (`app/medication/snapshot_sync.py`, ADR-0019) wires a
`*_SNAPSHOT_PATH`/`*_SNAPSHOT_VERSION` environment-variable pair per pinned source (DDInter 2.0,
Beers 2023, STOPP/START v3) to the existing per-source loaders, replacing "an operator manually
invokes 2-3 different CLI scripts with a hand-typed version each time" with one idempotent sync
step: a source already imported at its pinned version + checksum is left untouched, so running it
repeatedly (on every deploy, or via the `sync_pinned_snapshots` ARQ worker task) never re-imports or
duplicates a snapshot. A configured path with no paired version raises loudly rather than importing
under an inferred label — reproducibility requires an explicit, reviewed version, never one derived
from file content or mtime.

## 9. Deployment topology (free-tier MVP)
Vercel (frontend static/RSC) · Fly.io/Render (FastAPI API **and** ARQ worker — the persistent
process that serves all SSE, ADR-0007) · Supabase/Neon (Postgres+pgvector) · Upstash (Redis) ·
Cloudflare R2 (objects) · Gemini free / Ollama local (LLM). Details in [DEPLOYMENT.md](DEPLOYMENT.md).

**Ollama-only deployment mode** (`DEPLOYMENT_MODE=ollama_only`, ADR-0024) — a code-enforced
guarantee for regulated/data-residency-sensitive deployments (e.g. a hospital) that AI chat and
evidence retrieval never call a cloud provider or a public medical-evidence API: only Ollama is
registered (even if cloud provider keys are set), the evidence-connector registry is built empty
(disabling both Evidence Verification and the chat orchestrator's public-evidence branch at that
one choke point, ADR-0021), and the Medication-Safety Engine's RxNorm/openFDA live-lookup clients
are constructed disabled. Zero behavior change when left at the default (`standard`). Pinned
drug-data snapshot sync (ADR-0019) and local-disk storage (ADR-0014) already made no network calls
and needed no change.

## 10. Repository structure
```
backend/app/{api,orchestrator,agents,providers,evidence,medication,ingestion,data,core,workers}
backend/{migrations,tests}
frontend/{app,components,lib,tests}
infra/            docker, compose, CI, deploy, Grafana
data/loaders/     operator-provisioned raw snapshot files (never committed); loader code lives in
                  backend/app/medication/ (ADR-0018)
docs/{,adr/}      this documentation set + decision records
.github/workflows CI/CD
```
Folder responsibilities are also enumerated in [`../CLAUDE.md`](../CLAUDE.md) §4.

## 11. Cross-cutting concerns
- **Security** → [SECURITY.md](SECURITY.md) (auth, isolation, prompt-injection, uploads, encryption, audit).
- **Observability** → [DEBUGGING.md](DEBUGGING.md) (OTel, Prometheus/Grafana, structlog, Sentry, health).
- **Config** → [ENVIRONMENT.md](ENVIRONMENT.md) (typed pydantic-settings, every env var).
- **Scale path** → [DEPLOYMENT.md](DEPLOYMENT.md) (worker pools, Qdrant past ~10M vectors, replicas, SSO).
