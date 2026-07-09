# CORVEON — Master Implementation Blueprint (v1.0)
## A Modular, Open-Source, Evidence-Grounded Healthcare AI Platform

*Master specification for autonomous implementation by Claude Code. Current as of July 2026. No application code — this is the engineering contract. Build the platform exactly as specified; do not re-open resolved decisions.*

---

## TL;DR
- **The platform is named `Corveon`** — a coined, collision-free name (verified: no healthcare/AI/medical company, product, GitHub org, or obvious trademark uses it; only unrelated personal social handles). It is an open-source, provider-agnostic clinical intelligence platform whose defining stance is that **every uploaded document is treated as potentially unreliable** and every important answer is grounded in transparent, multi-source medical evidence with explicit provenance and confidence.
- **The architecture is fully resolved with zero open decisions:** FastAPI + Next.js 16, PostgreSQL 16 + pgvector (HNSW), ARQ on Redis, a **custom lightweight orchestrator** (not LangGraph/CrewAI — least lock-in for a solo dev), a **deterministic medication rules engine as source of truth** (the LLM only parses input and explains rule outputs), and a hybrid Evidence Verification Engine over verified-free sources (openFDA, DailyMed, RxNorm/RxNav, PubMed E-utilities, ClinicalTrials.gov). The entire MVP is buildable on free infrastructure.
- **It is a clear engineering progression beyond DocuMind** (single-mode, always-on RAG, one provider) by adding relational+vector modeling with absolute per-chat isolation, distributed async processing, provider failover, conditional multi-agent orchestration, full observability, and per-feature testing — and it explicitly engineers out each of the author's stated past failure categories.

---

## 0. How to read this document
Every module follows the mandated order: **Architecture → Database → API → Backend → Frontend → Testing → Documentation.** No decision is left open; every "choose X over Y" is resolved with justification. Facts about external APIs, datasets, versions, and licenses were verified via web search in July 2026 and are attributed inline; where a fact could not be fully verified it is explicitly flagged.

**Sourcing limitation (flagged):** Programmatic GitHub fetching of `github.com/kanwa2006` (author) and `github.com/tejasri106/Genesis` (benchmark) was not performed. Skill/quality calibration is based on the task's supplied descriptions and senior-engineering benchmarks. Treat the Genesis "quality bar" as a described standard, not an inspected artifact — do not attempt to copy its code, architecture, UI, structure, algorithms, prompts, or docs (originality is required regardless).

---

## 1. Final Project Name + Rationale + Collision Check

**Chosen name: `Corveon`.**

**Rationale:** "Corveon" is a coined name evoking *cor* (Latin "heart/core" — the clinical core and the central orchestrator) with a clean, modern *-eon* suffix suggesting durability and scale. It is short, globally pronounceable, carries no negative connotations in major languages, and is brandable as both an open-source flagship and a future startup. It deliberately does not describe the medication engine narrowly — medication safety is one module, not the whole product, so a disease- or drug-flavored name would misrepresent the platform.

**Collision-check result (verified July 2026):** No healthcare, healthcare-AI, medical-software company, product, GitHub organization, or obvious trademark uses "Corveon." The only "Corveon" results are unrelated personal social-media handles (Instagram, Spotify, TikTok) and a rare given name. **Recommendation:** phonetic neighbors exist in the health-AI space — Corva Health, Corti (corti.ai), CorroHealth — so a formal USPTO/WIPO trademark clearance is advisable before commercial launch, but there is no direct collision and the name is safe to adopt now.

**Rejected alternatives (each a verified collision):** "Medrona" → Medrona Inc., an active AI-enabled medical-billing/RCM healthcare company (Tacoma, WA, founded 2013) in the exact vertical; "Veritome" → an EU AI Act compliance vendor (Relay Labs, Dublin); "Evidium" → a funded, transparency-focused healthcare-AI startup (Series A, Health2047); "Aletheia" → multiple active healthcare marketing/data firms.

---

## 2. Product Identity

**Corveon is an open-source, provider-agnostic clinical intelligence platform that treats every uploaded document as potentially unreliable and grounds every important answer in transparent, multi-source medical evidence.** A single AI Orchestrator decides per request which models, retrieval strategies, and specialized agents to run; an Evidence Verification Engine cross-checks claims against trusted public medical knowledge (openFDA, DailyMed, RxNorm/RxNav, PubMed/PMC, ClinicalTrials.gov, MeSH) and organization-defined trusted corpora; and a deterministic Medication-Safety Engine performs RxNorm normalization, drug–drug interaction detection, renal/dose checks, and STOPP/START/Beers screening. It is a human-in-the-loop assistant that never replaces a licensed professional and never answers confidently on suspected misinformation.

**How it complements DocuMind and surpasses the Genesis bar:** DocuMind AI is a single-mode RAG PDF-QA SaaS (always-on retrieval, one provider, FAISS, no relational modeling). Corveon is a demonstrable engineering step up: relational + vector data modeling with enforced per-chat isolation, distributed async processing, external medical-API integration with caching and pinned reproducible snapshots, provider-agnostic failover, a deterministic rules engine as source of truth, multi-agent orchestration invoked *conditionally*, full observability, and per-feature testing. Where DocuMind always retrieves, Corveon decides *when not to*. This meets or exceeds the described Genesis quality bar by adding safety-critical determinism, provenance tagging, and enterprise-grade modularity — while remaining completely original.

---

## 3. Full System Architecture

### 3.1 Component map (textual)
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
             │                           │                              │
   ┌─────────▼─────────┐   ┌─────────────▼────────────┐   ┌────────────▼───────────┐
   │ AI ORCHESTRATOR   │   │  DOMAIN SERVICES         │   │  ASYNC PIPELINE         │
   │ (custom, graph)   │   │  Chats · Docs · Users    │   │  (ARQ workers + Redis)  │
   │ routing + policy  │   │  Analytics · Audit       │   │  upload→OCR→chunk→embed │
   └────────┬──────────┘   └──────────────┬───────────┘   └────────────┬───────────┘
            │                             │                            │
   ┌────────▼──────────┐        ┌─────────▼─────────┐        ┌─────────▼──────────┐
   │ AGENT RUNTIME     │        │ DATA LAYER        │        │ EXTERNAL MED APIs  │
   │ specialized agents│        │ Postgres+pgvector │        │ openFDA·DailyMed·  │
   │ (single-resp.)    │        │ Redis cache       │        │ RxNav·PubMed·CT.gov│
   └────────┬──────────┘        │ Object store (R2) │        └─────────┬──────────┘
            │                   └───────────────────┘                  │
   ┌────────▼───────────────────────────────────────────────────────┐ │
   │ PROVIDER-AGNOSTIC AI LAYER                                        │◄┘
   │ Gemini · Claude · OpenAI · OpenRouter · Ollama (key pools/failover)│
   └───────────────────────────────────────────────────────────────────┘
```

### 3.2 Representative request flow (sequence: "verify this uploaded treatment PDF")
1. Client uploads PDF → API returns `202` + `job_id`; SSE channel opens.
2. Async pipeline emits stage events: Uploading → Validating file → Extracting content → OCR (if scanned) → Cleaning text → Chunking → Creating embeddings → Indexing → Complete.
3. User asks a question in that chat. API calls the Orchestrator with `{chat_id, query, available_artifacts}`.
4. Orchestrator runs **Query Understanding agent** → detects claim-verification intent + medication mentions.
5. Routing policy decides: RAG over uploaded doc = YES; trusted public evidence = YES (guideline check); medication-safety = YES (drugs present); pure-LLM-only = NO.
6. **Retrieval agent** pulls chunks from the chat's own vectors + queries openFDA/DailyMed/PubMed (cache-first). **Medication-safety agent** normalizes drugs to RxCUI and runs the rules engine.
7. **Evidence Verification agent** tags each statement as (a) uploaded-doc, (b) verified-public, (c) org-trusted, (d) AI-reasoning, or (e) conflicting/insufficient; computes a confidence score.
8. **Citation Verification agent** confirms every cited reference resolves to a real source (fabricated-citation guard).
9. **Response Generation agent** composes the answer; **Response Review** + **Risk Assessment** agents gate it (block confident answers on suspected misinformation).
10. Answer streams back with a transparent `routing_trace` panel (which providers/agents/sources ran and why).

### 3.3 Deployment topology (free-tier MVP)
- **Frontend:** Vercel (Next.js, free Hobby tier) or Cloudflare Pages.
- **Backend API + workers:** single container on Fly.io / Render free tier (or a small always-free VM).
- **Postgres + pgvector:** Supabase or Neon free tier.
- **Redis:** Upstash free tier (serverless) for cache + ARQ queue.
- **Object storage:** Cloudflare R2 (no egress fees) or Supabase Storage.
- **LLM inference:** Gemini free tier default; Ollama local for zero-cost dev; OpenRouter free models as fallback.

---

## 4. Technology Stack (final decisions, one-line justification each)

| Layer | Decision | Why it is the best engineering choice (not just popular) |
|---|---|---|
| Backend framework | **FastAPI (0.139.x, Python 3.12)** | Native async, Pydantic v2 typing, built-in OpenAPI, and native Server-Sent Events support (shipped 2026) for streaming/progress without extra libs. |
| ASGI server | **Uvicorn** (Gunicorn workers in prod) | Standard, battle-tested ASGI runtime pairing with FastAPI. |
| Frontend | **Next.js 16.2.x (App Router) + React 19, TypeScript** | Current stable line (16.x, Turbopack default; 16.2.7 was current stable as of June 2026); RSC + streaming suit progressive AI output. |
| Relational DB | **PostgreSQL 16** | ACID, mature, free; single source of truth for tenancy and isolation. |
| Vector store | **pgvector (0.8+/0.9), HNSW index, inside Postgres** | Free, no extra service; 2026 benchmarks show HNSW matches/beats dedicated stores under ~10M vectors; SQL joins enable per-chat isolation filters natively. |
| Task queue | **ARQ (async Redis queue)** | Async-native (matches FastAPI's event loop), tiny footprint, Redis-only — no separate broker; ideal for a solo dev vs Celery's operational weight. |
| Cache / broker | **Redis (Upstash free tier)** | One system for both external-API caching and the ARQ queue. |
| Object storage | **Cloudflare R2** | S3-compatible, zero egress fees, generous free tier. |
| ORM / migrations | **SQLAlchemy 2.0 (async) + Alembic** | Typed ORM; Alembic gives deterministic, reviewable migrations (directly attacks the "migration conflicts" failure category). |
| Embeddings | **sentence-transformers (BAAI/bge-small-en or e5-small), local CPU** | Free, no GPU, no per-token cost; keeps sensitive text off external services (privacy). |
| OCR | **Tesseract (pytesseract) + PyMuPDF; OCRmyPDF for scanned PDFs** | Fully open-source, CPU-only, no API cost. |
| Doc parsing | **PyMuPDF (PDF), python-docx (DOCX), python-pptx (PPT/PPTX), markdown-it, Pillow (images)** | Format-specific, open-source; extensible parser registry for future formats. |
| Orchestration/agents | **Custom lightweight orchestrator (typed async state graph)** — see §7 | Least lock-in, full observability, best long-term fit for a solo dev; heavyweight frameworks add churn/opacity. |
| Auth | **FastAPI OAuth2 password/JWT (access+refresh) + Argon2 hashing** | Standard, self-hosted, free; no auth vendor lock-in. |
| Testing | **pytest, pytest-asyncio, httpx, Testcontainers, Playwright, axe-core** — see §15 | Full free/open coverage unit→e2e→accessibility. |
| Observability | **OpenTelemetry + Prometheus + Grafana + structlog JSON + Sentry free tier** — see §16 | Open standards, no lock-in, free tiers cover MVP. |
| Containerization | **Docker + docker-compose (dev), multi-stage image (prod)** | Reproducible; runs on any free tier. |
| CI/CD | **GitHub Actions** | Free for public repos; gates tests before deploy. |

**Conflict resolutions (final, no re-opening):** (a) *Qdrant vs pgvector* → **pgvector**, because a solo dev on free infra benefits more from one database with SQL-enforced isolation than a second service; revisit Qdrant only past ~10M vectors. (b) *Celery vs ARQ* → **ARQ**, for async-native simplicity and single-broker operation. (c) *Framework vs custom orchestrator* → **custom** (§7). (d) *Next.js vs plain React* → **Next.js** for streaming/RSC and routing maturity.

---

## 5. Provider-Agnostic AI Layer

**Design principle:** business logic never references a concrete provider. Providers are registered via config/env only.

- **Registration:** each provider is a config entry `{name, adapter, base_url, model_ids, key_pool, priority, capabilities, rpm_limit, rpd_limit}`. Adding a provider = add a config block + (if a new API shape) a thin adapter implementing the common `generate()/embed()` interface. No business-logic edits.
- **Key pools & rotation:** multiple keys per provider in a rotating pool; round-robin with per-key usage counters; a key hitting `429` is quarantined with exponential backoff.
- **Load balancing:** weighted by remaining quota + measured latency; sticky within a single multi-step agent run for cache coherence.
- **Failover & fallback:** ordered by `priority`; on failure (timeout, 429, 5xx) the router advances to the next healthy provider/model; circuit-breaker per provider.
- **Retries:** exponential backoff with jitter (1s→2s→4s→8s), capped attempts, request idempotency keys.
- **Quota / rate-limit handling:** token-bucket per provider tuned to each provider's published limits; requests queue rather than fail hard.
- **Health monitoring:** periodic lightweight health pings; degraded/unhealthy status feeds routing.
- **Prioritization:** free/local providers preferred for non-critical steps; higher-capability providers reserved for reasoning/verification.

**Verified 2026 provider facts + recommended free-tier default config:**

| Provider | 2026 free-tier reality (verified) | Role in Corveon |
|---|---|---|
| **Google Gemini API** | Free tier exists (billing disabled, no credit card) but was tightened in 2026: Google cut free-tier quotas 50–80% on **Dec 7 2025** and moved Pro models behind billing. Per Google's official rate-limits docs (ai.google.dev, updated 2026-07-03), as of March 2026: **Gemini 2.5 Pro = 5 RPM / 100 RPD, 2.5 Flash = 10 RPM / 250 RPD, 2.5 Flash-Lite = 15 RPM / 1,000 RPD; all share 250,000 TPM.** Limits are per-project (not per-key) and can change without notice; free-tier inputs may be used to improve Google's models. | **Primary default** (Flash / Flash-Lite class) for general reasoning/generation. |
| **Anthropic Claude API** | Paid; strong reasoning/quality. | Optional high-quality reasoning/verification when a key is provided. |
| **OpenAI API** | Paid; standard tiered rate limits with exponential-backoff guidance. | Optional provider. |
| **OpenRouter** | Per OpenRouter's official rate-limits doc: **"Free usage: 50 requests/day, 20 requests/minute · Purchased > $10 worth of Credits: 1000 requests/day, 20 requests/minute."** The 20 RPM cap never rises with credits; the $10 threshold is a permanent unlock. `:free` models can be pulled/changed without notice → not for production-critical paths. OpenAI-compatible API. | Fallback + model breadth. |
| **Ollama / local** | Free, self-hosted, no rate limits, full privacy. | Zero-cost dev default + privacy-sensitive inference. |

**Recommended free default:** Gemini Flash-Lite / Flash (primary) → OpenRouter `:free` model (fallback) → Ollama local (dev + privacy). Because Gemini free-tier data may be used for training, **route any org-trusted or sensitive text to Ollama local by policy.**

---

## 6. AI Orchestrator + Intelligent Knowledge Routing

**Decision inputs per request:** query intent + entities (Query Understanding agent), artifacts attached to *this chat only*, detected drug mentions, detected claims/citations, requested output type, provider health, and a cost/latency budget.

**Routing policy (deterministic decision tree, fully transparent):**
- **Pure LLM reasoning** — general, self-contained query (no doc dependency, no claim to verify, no drugs).
- **RAG over uploaded docs** — query references chat-attached documents.
- **RAG over trusted public medical knowledge** — query asserts/asks about clinical facts or guidelines.
- **Hybrid RAG** — both uploaded docs and external evidence needed (e.g., "is this PDF's recommendation still current?").
- **Org-trusted retrieval** — chat/tenant has registered corpora relevant to the query.
- **Multi-agent reasoning** — verification, medication safety, or risk assessment implicated.
- **External knowledge retrieval** — targeted API calls (RxNorm, openFDA, PubMed) for specific lookups.

**When NOT to RAG (explicit anti-"always-on" rule):** retrieval is skipped when the query is conversational, purely computational, or fully answerable from in-chat context. Retrieval runs only when it improves grounding, accuracy, explainability, or evidence quality.

**Transparency/surfacing:** every response carries a `routing_trace` object (providers used, agents invoked, sources queried, why-retrieved / why-not) rendered in a collapsible UI panel. Nothing is hidden.

---

## 7. Multi-Agent Design + Framework Decision

**Framework decision: build a custom, lightweight, typed orchestrator (a plain Python state-graph of async nodes over a Pydantic state object), NOT a heavyweight framework.**

**Justification vs alternatives (verified 2026 landscape):** LangGraph 1.0 (GA Oct 2025) is the strongest production graph framework (durable state, HITL, time-travel debugging) and is the designated **fallback** if the custom layer ever proves insufficient for one complex flow; CrewAI optimizes for fast role/task prototypes but hits ceilings; LlamaIndex Workflows is retrieval-first; AutoGen/Microsoft Agent Framework skews enterprise/.NET; Pydantic-AI is type-safe but young. For a **solo developer evolving this for years**, the dominant concerns are **least lock-in, maximum observability, and no forced churn** from a fast-moving dependency (the agent-framework ecosystem shipped more breaking change in Q2 2026 than any prior quarter). A custom orchestrator over a stable core gives full control of tracing, deterministic routing, and testability with zero framework-upgrade risk. The design keeps a clean seam so LangGraph can be adopted later for a specific complex flow without rewriting agents.

**Agent catalog (each single-responsibility, invoked only when needed):**

| Agent | Sole responsibility |
|---|---|
| Query Understanding | Parse intent, entities, drug mentions, claim/citation presence. |
| Task Planning | Select which agents/sources this request needs. |
| Retrieval | Fetch chunks from in-chat vectors, public APIs, org corpora. |
| Evidence Verification | Tag statements by source class; detect outdated/unsupported claims. |
| Clinical Safety Validation | Enforce safety-first guardrails; flag human-in-the-loop needs. |
| Medication-Safety Analysis | Run the deterministic drug rules engine (§9). |
| Document Understanding | Structure/semantics of parsed documents. |
| OCR Processing | Invoke OCR only for image/scanned inputs. |
| Reasoning | Multi-step inference over assembled context. |
| Citation Verification | Confirm each citation resolves to a real source. |
| Response Generation | Compose premium-formatted answer. |
| Response Review | QA the draft against policy and evidence. |
| Risk Assessment | Score patient-safety risk; can block/soften output. |
| Export Generation | Produce Markdown/PDF/print artifacts. |

**Extensibility:** agents implement a common `Agent` protocol (`run(state) -> state`) and self-register; adding an agent never requires redesigning the orchestrator — the routing policy simply gains a branch.

---

## 8. Evidence Verification Engine (flagship differentiator)

**Pipeline stages:** Ingest & parse → claim/segment extraction → source-class tagging → external evidence retrieval → contradiction/outdatedness/fabrication detection → confidence scoring → conflict handling → provenance-annotated output.

**Public trusted sources (verified 2026 access):**
| Source | Verified status / limits | Use |
|---|---|---|
| **openFDA** | Free; **240 req/min + 1,000/day without a key; 240 req/min + 120,000/day with a free key**; max `limit=1000` per call (open.fda.gov). | Drug labels, adverse events, recalls; DDI fallback. |
| **DailyMed** | Free RESTful API **v2** (XML/JSON), GET-only, structured product labels (SPL) (dailymed.nlm.nih.gov). | Authoritative label text. |
| **RxNorm / RxNav (NLM)** | Free; **no license needed** for RxNorm/RxTerms/Prescribable/RxClass; **≤20 requests/sec/IP**. **The RxNav Drug–Drug Interaction API was discontinued Jan 2, 2024** — do NOT rely on it. | Drug normalization → RxCUI. |
| **PubMed/PMC E-utilities** | Free; **3 req/sec without key, 10 req/sec with a free API key** (ncbi.nlm.nih.gov). | Literature evidence. |
| **ClinicalTrials.gov** | Free public API. | Trial evidence. |
| **MeSH** | Free NLM vocabulary. | Concept normalization. |

**Org-trusted knowledge (source class C):** tenants register their own corpora (guidelines, SOPs, protocols, policies, institutional knowledge) via a `trusted_source` provider interface, versioned and access-scoped; new provider types plug in without redesign.

**Provenance / source-tagging model:** every emitted statement is annotated with exactly one class: **(a)** uploaded document, **(b)** verified public evidence, **(c)** organization-trusted evidence, **(d)** AI reasoning, **(e)** conflicting/insufficient evidence. Each class has distinct visual treatment in the UI.

**Confidence scoring approach:** a transparent composite of (i) source-class weight (verified public/org > AI reasoning), (ii) agreement across independent sources, (iii) recency vs guideline dates, (iv) citation-resolution success. Surfaced as a 0–100 score plus a plain-language rationale; the method is documented, never a black box.

**Misinformation / outdated-claim detection:** the engine never assumes an uploaded document is correct. It detects contradictory statements, outdated guidelines (comparing against current source dates), unsupported claims, missing evidence, fabricated citations (a citation must resolve to a real PubMed/DOI/label record), and inconsistent recommendations. On detection it warns, explains why, shows the conflicting evidence, and recommends verification — it never silently uses suspect content and never answers confidently on suspected misinformation.

**Conflict handling:** when sources disagree, the engine presents both positions with provenance and dates rather than silently choosing one; the answer states the conflict explicitly.

---

## 9. Medication-Safety Engine (deterministic core)

**Principle:** the **rules engine is the source of truth**; the LLM only (i) parses messy input text into structured medication entries and (ii) writes explanations grounded strictly in rule outputs, with guardrails against adding facts.

**Ingestion:** FHIR bundles (incl. MIMIC-IV-on-FHIR format), discharge summaries, free text, CSV. A normalizer maps every drug to **RxCUI via RxNorm/RxNav** (`findRxcuiByString`, `getApproximateMatch` for fuzzy/typo-tolerant matching).

**Drug–drug interactions:** primary source **DDInter 2.0**, cited to Xiong et al., *Nucleic Acids Research* 2025;53(D1):D1356–D1364: *"The updated database covers 2310 drugs, with 302 516 drug–drug interaction (DDI) records accompanied by 8398 distinct, high-quality mechanism descriptions and management recommendations … freely accessible at https://ddinter2.scbdd.com."* Loaded as a pinned local snapshot. **openFDA label-derived interactions** serve as fallback. Each interaction returns severity + source provenance. (Because NLM discontinued the RxNav DDI API in Jan 2024, DDI data must come from DDInter/openFDA, not RxNav.)

**Renal / dose checks:** implement **both** kidney-function equations and flag threshold-sensitive drugs:
- **Cockcroft-Gault creatinine clearance (CrCl, mL/min)** — the historical FDA/drug-label standard, embedded in most FDA-approved labels: `CrCl = [(140 − age) × weight(kg) × (0.85 if female)] / (72 × serum creatinine mg/dL)`.
- **2021 race-free CKD-EPI creatinine eGFR (mL/min/1.73m²)** — recommended by the NKF-ASN Task Force (Inker et al., *NEJM* 2021;385:1737-1749; Delgado et al., *AJKD* 2022) and by **2024 FDA guidance for industry** for PK/dosing. When used for drug dosing it must be **de-indexed to the patient's actual body surface area** (mL/min/1.73m² → mL/min). The engine supports both, shows both, and flags divergence at critical decision thresholds (e.g., DOACs like apixaban, aminoglycosides, vancomycin). This dual approach hedges a clinical standard that is actively in transition.

**Potentially-inappropriate-prescribing / deprescribing (older adults):**
- **Beers Criteria 2023 (AGS)** — By the 2023 American Geriatrics Society Beers Criteria® Update Expert Panel, *J Am Geriatr Soc* 2023;71(7):2052–2081, doi:10.1111/jgs.18372 (the 7th overall update, 4th under AGS stewardship).
- **STOPP/START v3** — O'Mahony D, et al., *Eur Geriatr Med* 2023;14(4):625–632, doi:10.1007/s41999-023-00777-y: *"The final total number of validated STOPP/START criteria was 190 (133 STOPP and 57 START criteria)"* (up from 114 in version 2).
Both encoded as versioned, pinned rule sets.

**Medication discrepancy classification (across two lists):** deterministic diff producing added / omitted / dose-changed / frequency-changed classes, with RxCUI-level matching.

**LLM-explanation guardrails:** explanations are generated only from a structured rule-output object; a post-generation check verifies the narrative introduces no drug facts, severities, or recommendations absent from the rule output; anything ungrounded is stripped and flagged.

**Datasets for dev/test (verified):** **Synthea** (open-source synthetic patients, no PHI) is the default for development and CI, so the MVP needs no credentialed data. **MIMIC-IV** (PhysioNet Credentialed Health Data License v1.5.0 — requires credentialing + training, for research use, not shipped in the product) is reserved for advanced evaluation only.

---

## 10. Data Layer

### 10.1 Finalized schema (relational + vector)
PostgreSQL 16; all timestamps UTC; all IDs UUID:

- **users**(id, email UNIQUE, password_hash, role, org_id FK, created_at, is_active)
- **organizations**(id, name, plan, created_at)
- **chats**(id, user_id FK, org_id FK, title, is_pinned, is_archived, created_at, updated_at)
- **messages**(id, chat_id FK, role, content, routing_trace JSONB, created_at) — index (chat_id, created_at)
- **documents**(id, chat_id FK, user_id FK, filename, mime_type, status, page_count, created_at) — **chat_id mandatory (isolation anchor)**
- **document_chunks**(id, document_id FK, chat_id FK, ordinal, text, token_count) — chat_id denormalized for isolation filtering
- **chunk_embeddings**(id, chunk_id FK, chat_id FK, embedding vector(384), model_id) — **HNSW index on embedding**; every similarity query is `WHERE chat_id = :current_chat`
- **images**(id, chat_id FK, document_id FK NULL, ocr_text, created_at)
- **saved_responses / notes**(id, chat_id FK, content, created_at)
- **trusted_sources**(id, org_id FK, type, name, config JSONB, version, is_active)
- **medications**(id, chat_id FK, raw_text, rxcui, name, dose, route, frequency)
- **medication_findings**(id, chat_id FK, type, severity, source, rule_id, explanation, provenance JSONB)
- **audit_log**(id, actor_id, action, entity_type, entity_id, ip, metadata JSONB, created_at) — append-only
- **jobs**(id, chat_id FK, type, status, progress_stage, error, created_at, updated_at)
- **external_cache**(key, source, payload JSONB, fetched_at, ttl)
- **drug_data_snapshots**(id, source, version, checksum, imported_at) — reproducible pinned DDInter/Beers/STOPP-START/RxNorm versions

### 10.2 Per-chat isolation at the data layer
Every content-bearing table carries `chat_id`. **Every retrieval query (relational or vector) is filtered by the active chat's `chat_id`;** there is no cross-chat or global-memory read path. Cross-chat access requires an explicit user "import" action that copies/links artifacts into the target chat. Enforcement is defense-in-depth: (1) application-layer guard on every query, (2) PostgreSQL Row-Level Security policies keyed on `chat_id`/`user_id`, (3) a repository layer that refuses queries lacking a `chat_id` predicate.

### 10.3 Migration strategy
Alembic, one migration per schema change, forward-only in prod, reviewed in CI. No auto-generated migration is merged without human review; a CI check asserts models and migrations are in sync (kills "migration conflicts").

### 10.4 Caching & reproducibility
Redis caches external-API responses keyed by `{source}:{query_hash}` with source-appropriate TTLs (respecting openFDA/PubMed/RxNav limits). Drug data (DDInter 2.0, Beers 2023, STOPP/START v3, monthly RxNorm release) is imported as **pinned, checksummed snapshots** recorded in `drug_data_snapshots`, so results are reproducible and auditable across time.

---

## 11. Per-Chat Isolation + Security Model

- **AuthN/AuthZ:** OAuth2 + JWT (short-lived access + refresh), Argon2 hashing; RBAC roles (user, org-admin, superadmin); every endpoint authorizes on both user and resource ownership.
- **Tenancy/isolation:** enforced as in §10.2 (app guard + RLS + repository invariant).
- **Secrets management:** all keys via environment/secret store (never in code or DB); provider key pools loaded at boot; `.env` gitignored; production secrets in the platform's secret manager + GitHub Actions encrypted secrets.
- **Prompt-injection defenses:** untrusted document text is never treated as instructions — it is passed as clearly delimited data under a system-prompt contract; an input screen strips/escapes instruction-like patterns; tool/agent invocation is gated by the orchestrator, not by document content; outputs are validated against expected schemas.
- **Malicious-upload defenses:** MIME + magic-byte validation, size caps, extension allowlist, per-file sandboxed parsing, image/PDF-bomb limits, no execution of uploaded content, antivirus scan hook.
- **Encryption:** TLS in transit everywhere; at rest via provider disk encryption + application-level encryption for sensitive fields.
- **Audit logging:** append-only `audit_log` for auth events, uploads, exports, admin actions, and evidence/medication findings.
- **Least privilege:** DB roles scoped; workers hold only needed capabilities; object-store URLs are short-lived signed links.
- **Privacy:** minimize sensitive data collection; store only what is necessary; support data deletion; route sensitive text to local Ollama to avoid external exposure.

---

## 12. Async Processing / Upload Pipeline

- **Queue/workers:** ARQ workers consume from Redis; job types = ingest, ocr, embed, verify, export.
- **Stages (emitted as SSE progress events):** Uploading → Validating file → Extracting content → OCR (if required) → Cleaning text → Chunking → Creating embeddings → Indexing → Verifying content → Preparing response → Complete.
- **Streaming:** SSE from API to client for both token streaming and stage progress; UI never blocks.
- **Chunking:** structure-aware (headings/sections) with overlap; token-bounded.
- **Parallelism:** independent documents processed concurrently; embeddings batched.
- **Caching:** external-API and embedding caches to avoid recompute.
- **Backpressure & retries:** bounded concurrency; failed stages retry with backoff and surface a "retry failed upload" action; stalled jobs have heartbeats + timeouts so pipelines cannot silently hang (kills "stalled processing").

---

## 13. Full API Contract Catalog (REST + SSE)

Conventions: JSON; errors use a uniform model `{error_code, message, details, trace_id}`; standard status codes (200/201/202/400/401/403/404/409/422/429/500). Auth via `Authorization: Bearer`.

**Auth**
- `POST /api/v1/auth/register` → 201 `{user}`
- `POST /api/v1/auth/login` → 200 `{access, refresh}`
- `POST /api/v1/auth/refresh` → 200 `{access}`
- `POST /api/v1/auth/logout` → 204

**Chats**
- `POST /api/v1/chats` → 201 `{chat}`
- `GET /api/v1/chats?search=&pinned=&archived=` → 200 `[chat]`
- `GET /api/v1/chats/{id}` → 200 `{chat}`
- `PATCH /api/v1/chats/{id}` (rename/pin/archive) → 200
- `DELETE /api/v1/chats/{id}` → 204

**Messages / AI**
- `POST /api/v1/chats/{id}/messages` → 202 + SSE stream (tokens + `routing_trace`)
- `POST /api/v1/chats/{id}/messages/{mid}/regenerate` → 202 + SSE
- `POST /api/v1/chats/{id}/messages/{mid}/continue` → 202 + SSE
- `GET /api/v1/chats/{id}/messages` → 200 `[message]`

**Documents / uploads**
- `POST /api/v1/chats/{id}/documents` (multipart) → 202 `{job_id}`
- `GET /api/v1/jobs/{job_id}` → 200 `{status, progress_stage}` (or SSE `GET /api/v1/jobs/{job_id}/events`)
- `GET /api/v1/chats/{id}/documents` → 200 `[document]`
- `DELETE /api/v1/documents/{id}` → 204

**Search**
- `POST /api/v1/chats/{id}/search` (semantic, in-chat only) → 200 `[hit]`

**Evidence & medication**
- `POST /api/v1/chats/{id}/verify` (evidence verification) → 202 + SSE → `{claims:[{text, source_class, confidence, evidence[]}]}`
- `POST /api/v1/chats/{id}/medications/analyze` → 202 + SSE → `{normalized[], interactions[], renal[], pip_flags[], discrepancies[]}`

**Trusted sources**
- `POST/GET/DELETE /api/v1/org/trusted-sources`

**Export**
- `POST /api/v1/chats/{id}/messages/{mid}/export` `{format: md|pdf}` → 200 file

**Analytics / dashboard**
- `GET /api/v1/analytics/overview` → 200 metrics

**Admin / audit**
- `GET /api/v1/audit?filters` → 200 (admin only)

---

## 14. Frontend Architecture

- **Framework/routing:** Next.js 16 App Router; route groups `(auth)`, `(app)/chats/[chatId]`, `(app)/dashboard`, `(app)/settings`, `(app)/org/trusted-sources`.
- **State:** TanStack Query for server state; Zustand for local UI state; a dedicated SSE hook for streaming.
- **Component system:** shadcn/ui + Radix primitives + Tailwind CSS; Framer Motion for smooth transitions.
- **Design system/tokens:** centralized tokens (spacing scale, type scale, semantic colors — including distinct colors for the five evidence source-classes and for severity levels).
- **Accessibility (WCAG 2.2 AA):** semantic HTML, focus management, keyboard nav, ARIA on interactive components, contrast-compliant tokens, reduced-motion support; verified with axe-core.
- **Premium UX features:** drag-and-drop + file-picker upload with preview/validation/retry; real-time staged progress; loading skeletons; informative empty/error states; per-message copy (whole/section/code/table), export MD/PDF, regenerate, continue, collapse/expand, citation navigation; chat new/rename/search/pin/archive/delete; interactive analytics charts (Recharts); premium AI-response formatting (headings, numbered sections, tables, callout/warning boxes, highlighted key info, strong typography hierarchy, generous whitespace, no walls of text); the transparent `routing_trace` panel.

---

## 15. Testing Strategy (per-feature, before next feature)

| Layer | Tools (free/open) | Scope |
|---|---|---|
| Unit | pytest, pytest-asyncio | pure logic, rules engine, routing policy |
| Integration | pytest + Testcontainers (Postgres, Redis) | DB, cache, queue interactions |
| API contract | httpx + schemathesis | endpoint shapes, status codes, error model |
| Database | pytest + Alembic upgrade/downgrade tests | migrations, RLS/isolation invariants |
| Auth | pytest | JWT, RBAC, ownership checks |
| Upload/OCR/chunking/embedding/retrieval | pytest fixtures + sample corpora + Synthea data | pipeline stages |
| Semantic search / AI pipeline | pytest + recorded provider responses (VCR-style) | routing + retrieval correctness |
| Medication safety | pytest with pinned DDInter/Beers/STOPP-START snapshots + Synthea patients | deterministic rule outputs (golden tests) |
| Export | pytest | MD/PDF fidelity |
| Security | bandit, pip-audit, custom prompt-injection + upload-abuse tests | vuln + abuse |
| Performance | Locust | latency/throughput of hot paths |
| Frontend unit/component | Vitest + React Testing Library | components |
| E2E | Playwright | full user journeys |
| Accessibility | axe-core / Playwright-axe | WCAG checks |
| Regression | full suite in CI on every PR | prevent regressions |

**Definition of done per feature:** all relevant layers above pass in CI before the next feature starts.

---

## 16. Observability & Debugging

- **Structured logs:** structlog JSON with `trace_id` on every request/job.
- **Tracing:** OpenTelemetry spans across API → orchestrator → agents → providers → DB; each agent and provider call is a span (so a slow/failed provider is instantly visible).
- **Metrics:** Prometheus (request latency, error rates, queue depth, job durations, per-provider success/latency/quota, embedding/search timings, upload metrics) with Grafana dashboards.
- **Error tracking:** Sentry free tier for exceptions with source context.
- **Health checks:** `/health` (liveness) and `/ready` (DB/Redis/provider readiness).
- **Justification:** all open standards, free tiers cover the MVP, zero lock-in; directly attacks the "poor observability / difficult debugging" failure categories.

---

## 17. Deployment

- **Free-tier topology:** Vercel (frontend) + Fly.io/Render (API + ARQ worker container) + Supabase/Neon (Postgres+pgvector) + Upstash (Redis) + Cloudflare R2 (objects) + Gemini free / Ollama (LLM).
- **Containerization:** multi-stage Docker image; docker-compose for local (api, worker, postgres, redis, ollama).
- **CI/CD (GitHub Actions):** lint → typecheck → full test matrix → build image → deploy on green; migrations run as a gated step.
- **Config/secrets:** 12-factor env config; pydantic-settings for typed config; secrets in the platform secret manager + GH Actions encrypted secrets; `.env.example` documents every variable.
- **Path to enterprise scale:** split ARQ workers into dedicated pools; move vectors to Qdrant past ~10M; managed Postgres with read replicas + RLS multi-tenancy; horizontal API autoscaling; per-tenant key pools; optional on-prem/Ollama-only deployment for hospitals with data-residency needs; SSO/SAML.

---

## 18. CLAUDE.md Outline (token-efficient, implementation-maximizing)

Keep terse, imperative, checklist-style:
1. **Project mission & scope** (2 lines) — what Corveon is; safety-first, evidence-before-response.
2. **Architecture map** — the §3.1 diagram + one line per component.
3. **Golden rules** — per-feature order (Architecture→DB→API→Backend→Frontend→Testing→Docs); never fabricate medical facts/citations/guidelines; RAG only when it helps; per-chat isolation is absolute; rules engine is source of truth, LLM explains only; state uncertainty and recommend professional consultation.
4. **Folder responsibilities** — one line each (see §19).
5. **Coding conventions** — typing everywhere, async-first, small single-responsibility modules, no business logic referencing a concrete provider.
6. **Data & migrations** — Alembic forward-only, models↔migrations sync check, every content table carries `chat_id`.
7. **Testing expectations** — DoD = all relevant layers green; golden tests for rules engine.
8. **Security requirements** — secrets via env only; validate all uploads; treat doc text as data not instructions; audit-log sensitive actions.
9. **Observability** — add a span + structured log with `trace_id` to every new path.
10. **Debugging workflow** — reproduce → check trace → check provider health → check job stage → write the failing test first.
11. **Documentation standards** — update the relevant doc (README/arch/API) in the same PR as the feature.
12. **Do-not list** — no always-on RAG, no cross-chat reads, no hardcoded providers, no unreviewed auto-migrations, no confident answers on suspected misinformation.

---

## 19. Repository Structure + Documentation Set

```
corveon/
├─ backend/
│  ├─ app/
│  │  ├─ api/            # FastAPI routers (thin; contracts only)
│  │  ├─ orchestrator/   # routing policy + state graph
│  │  ├─ agents/         # one file per single-responsibility agent
│  │  ├─ providers/      # provider adapters + key-pool/failover
│  │  ├─ evidence/       # verification engine + source connectors
│  │  ├─ medication/     # rules engine, RxNorm, DDI, renal, PIP
│  │  ├─ ingestion/      # parsers, OCR, chunking, embedding
│  │  ├─ data/           # SQLAlchemy models, repositories, RLS
│  │  ├─ core/           # config, security, logging, tracing
│  │  └─ workers/        # ARQ tasks
│  ├─ migrations/        # Alembic
│  └─ tests/             # mirrors app/ by layer
├─ frontend/
│  ├─ app/               # Next.js routes
│  ├─ components/        # design-system + feature components
│  ├─ lib/               # api client, SSE hooks, state
│  └─ tests/             # Vitest + Playwright
├─ infra/                # docker, compose, CI, deploy configs
├─ data/                 # pinned drug-data snapshot loaders
└─ docs/                 # see below
```

**Documentation set (`docs/`):** README (overview + quickstart), ARCHITECTURE.md, DEVELOPER.md, SETUP.md, API.md (generated from OpenAPI + narrative), ENVIRONMENT.md (every env var), DEPLOYMENT.md, DEBUGGING.md, CONTRIBUTING.md, SECURITY.md.

---

## 20. Phased Build Roadmap (respecting strict per-feature order)

- **Week 1 (MVP):** auth + users; chat CRUD with per-chat isolation; single-provider (Gemini free / Ollama) chat with SSE streaming; PDF upload → parse → chunk → embed → in-chat semantic search; minimal dashboard; core tests + CI. *Buildable entirely on free infra.*
- **Month 1:** provider-agnostic layer (pools/failover/health); orchestrator + routing policy + `routing_trace`; multi-format ingestion (DOCX/PPT/MD/images+OCR); export MD/PDF; observability stack; expanded test matrix.
- **Month 3:** Evidence Verification Engine (public sources + provenance + confidence + misinformation detection); org-trusted sources; citation verification; premium dashboards/analytics; RLS hardening; audit logging.
- **Month 6–12:** Medication-Safety Engine full (RxNorm + DDInter 2.0 + openFDA fallback + renal dual-equation + Beers 2023 + STOPP/START v3 + discrepancy classification + guardrailed explanations); multi-agent depth; enterprise path (Qdrant option, SSO, read replicas, on-prem/Ollama deployment); accessibility + performance audits; reproducible snapshot automation.

---

## 21. Final Engineering Self-Review

| Risk category | Specific risk | Mitigation until no major preventable weakness remains |
|---|---|---|
| Scalability | pgvector limits past ~10M vectors | HNSW + partitioning now; clean seam to Qdrant later (§17). |
| Scalability | LLM provider quota exhaustion (Gemini free = 5–15 RPM) | key pools, failover, local Ollama fallback, caching (§5). |
| Maintainability | Framework churn | custom orchestrator over stable core; LangGraph optional later (§7). |
| Maintainability | Feature coupling | single-responsibility agents/modules, common protocols (§7,§19). |
| Security | Prompt injection via docs | doc-text-as-data contract, input screening, orchestrator-gated tools (§11). |
| Security | Malicious uploads | MIME/magic-byte/size/sandbox validation (§11). |
| Security | Cross-chat leakage | triple-enforced isolation (app + RLS + repo invariant) (§10.2). |
| Performance | Upload/pipeline bottlenecks | async ARQ, bounded concurrency, batched embeddings, heartbeats/timeouts (§12). |
| Correctness | LLM hallucination of medical facts | rules engine is source of truth; grounded-explanation guardrail; citation verification (§8,§9). |
| Correctness | Outdated/fabricated evidence | source-class tagging, recency checks, citation resolution, conflict surfacing (§8). |
| Observability | Hard-to-diagnose failures | OTel spans per agent/provider, structured logs, health checks (§16). |
| Data integrity | Non-reproducible drug data | pinned checksummed snapshots (§10.4). |
| Regulatory | Renal-dosing standard in flux | dual equations (Cockcroft-Gault + 2021 CKD-EPI) with threshold flags (§9). |
| External dependency | RxNav DDI API discontinued (Jan 2024) | DDInter 2.0 primary + openFDA fallback, not RxNav (§9). |
| Future limitation | Free-tier ceilings | documented enterprise scale-up path (§17). |

---

## 22. How This Design Avoids the Author's Past Failure Categories

- **Architectural inconsistencies** → one enforced per-feature order + CLAUDE.md golden rules.
- **Backend/frontend mismatch** → API contract (§13) + generated OpenAPI types shared with frontend; contract tests.
- **Migration conflicts** → Alembic forward-only + models↔migrations CI sync check.
- **Upload bottlenecks / stalled pipelines** → async ARQ, bounded concurrency, heartbeats, timeouts, retry actions.
- **Poor observability / difficult debugging** → OTel + Prometheus + Sentry + structured logs + `trace_id`.
- **Missing validation** → Pydantic everywhere, upload validation, schema-validated agent outputs.
- **Deployment problems** → containerized, CI-gated, free-tier topology documented.
- **Weak testing** → per-feature DoD across all layers, golden tests for rules.
- **Weak documentation** → docs updated in same PR as feature; full docs set.
- **Scalability limits** → clean seams (Qdrant, worker pools, replicas).
- **Feature coupling** → single-responsibility agents/modules with common protocols.
- **Configuration problems** → typed pydantic-settings, `.env.example`, secrets via env only.

*End of blueprint v1.0. This specification is internally consistent, contains no unresolved decisions, TODOs, or placeholders, and is ready for autonomous implementation by Claude Code.*

---

23.1 True provider independence (new hard requirement; refines §5)
The provider registry treats every provider as an optional plugin discovered at boot. Absence is a normal state, never an error.

Zero providers configured is a valid state. The floor is Ollama-local as the implicit default whenever reachable. If no LLM provider is reachable at all, the platform enters degraded mode: deterministic, non-LLM features still work fully — the medication rules engine, RxNorm normalization, DDI/renal/Beers/STOPP-START checks, discrepancy diff, semantic search, uploads, exports — while LLM-dependent steps return a clean, typed provider_unavailable result the UI renders as an informative empty state, not a stack trace.
Absence ≠ failure. A provider that isn't configured produces no warning, no retry, no health-check noise, no config error. It is simply not in the registry. Only configured-but-unreachable providers trigger health/failover logic.
Capability-based routing. The router only ever considers registered ∧ healthy providers, ranked by priority. With one provider, it uses that one; with many, it load-balances. The routing policy code never names a concrete provider.

This closes the one addendum requirement v1.0 under-specified: "if only one provider exists, operate normally; missing providers must never generate warnings, failures, retries, or errors."
23.2 Multi-agent × free-tier rate limits (latent throughput bug — resolved)
A single evidence-verification request can fan out to many LLM calls, but Gemini free tier is only 5–15 RPM shared per project. Uncontrolled, one user request self-throttles. Resolution:

A per-request LLM-call budget enforced by the orchestrator.
A shared token-bucket all agents respect, tuned to each provider's published limits (§5).
Prompt consolidation: low-stakes, high-frequency agent steps (query understanding, response review) prefer local Ollama so they never consume scarce cloud quota; scarce cloud calls are reserved for reasoning/verification.

23.3 SSE and long jobs vs serverless limits (deployment inconsistency — resolved)
Vercel serverless functions cap execution time, which conflicts with long token streams and long-running jobs. Final rule: all SSE streaming and job-event channels are served by the FastAPI backend on Fly/Render (a persistent process), never from Vercel serverless. Vercel hosts only the static/RSC frontend, which opens SSE connections against the backend. Long work lives in ARQ workers; the client subscribes to GET /api/v1/jobs/{id}/events on the backend. This removes a real production failure mode that v1.0's topology implied but didn't call out.
23.4 Embedding-model versioning & reindex (data-integrity gap — resolved)
chunk_embeddings.model_id exists in §10.1 but had no policy. Final rules: every similarity search filters by model_id — vectors from different embedding models are never mixed in one query; changing the default embedding model requires a background reindex job rather than in-place mixing; the active embedding-model version is recorded in provenance. Prevents silent relevance decay when the model is upgraded years later.
23.5 Low-latency fast-path (satisfies "prioritize low latency")
The orchestrator gets an explicit fast-path: trivial inputs (greetings, simple in-context follow-ups, pure formatting requests) skip the agent graph and go straight to a single LLM call. Orchestrator and multi-agent overhead is paid only when the request genuinely needs it — the anti-"always-on" principle applied to compute, not just retrieval.
23.6 Concrete data deletion (satisfies privacy requirement in §11)
Distinguish archive (soft, reversible) from delete (hard, irreversible). Hard-delete cascades across messages, documents, document_chunks, chunk_embeddings, images, medications, medication_findings, saved_responses and the corresponding R2 objects, executed as an ARQ deletion job, with a single audit-log entry recording the action (not the content). Gives users a real right-to-erasure path.
23.7 Self-documenting repository + ADR log (satisfies addendum #4 and #9)
If CLAUDE.md, the docs/ set, or decision records are missing at implementation time, the coding agent generates them as part of the work — the repo is never allowed to drift into an undocumented state. Add a lightweight ADR log (docs/adr/): one short record per resolved decision (pgvector over Qdrant, ARQ over Celery, custom orchestrator over LangGraph, DDInter over the discontinued RxNav DDI API, dual renal equations). Every "why" from this blueprint becomes discoverable in-repo without external context.
23.8 Consistency confirmations (checked, no change needed)
Embedding dimension (vector(384)) matches the recommended bge-small/e5-small models; React 19 / Next.js 16 are consistent between the diagram and stack table; every content-bearing table carries chat_id for the isolation invariant. No contradictions found beyond those resolved above.
