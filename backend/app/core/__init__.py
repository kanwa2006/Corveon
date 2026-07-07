"""Core cross-cutting concerns.

Typed configuration (pydantic-settings, 12-factor; secrets from env only),
security (OAuth2 + JWT access/refresh, Argon2 hashing, RBAC), structured logging
(structlog JSON with ``trace_id``), and tracing (OpenTelemetry). Every new code
path adds a span and a ``trace_id``-carrying log (§16).
"""
