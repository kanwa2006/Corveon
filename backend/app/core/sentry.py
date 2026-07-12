"""Optional Sentry error tracking (docs/ARCHITECTURE.md §16). Initialized
by both long-lived processes (API lifespan, ARQ worker startup) when a DSN
is configured — a no-op otherwise: absence of an optional integration is a
normal, valid state, never a warning (§23.1)."""

from __future__ import annotations


def configure_sentry(dsn: str | None, environment: str) -> None:
    if not dsn:
        return
    # Imported lazily so deployments without a DSN never pay the import.
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=environment, send_default_pii=False)
