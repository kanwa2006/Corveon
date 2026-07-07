"""Corveon backend application package.

Top-level FastAPI application. Subpackages have strict, single responsibilities
(see CLAUDE.md §4 and docs/ARCHITECTURE.md). No cross-layer shortcuts: routers
stay thin, business logic never names a concrete AI provider, and every content
query is scoped by ``chat_id``.
"""
