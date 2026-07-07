"""API layer — FastAPI routers.

Thin, contract-only endpoints (auth, chats, messages/SSE, documents, jobs,
search, evidence, medication, trusted-sources, export, analytics, audit). No
business logic lives here; routers validate input, authorize, and delegate to
domain services / the orchestrator. Contract is documented in docs/API.md.
"""
