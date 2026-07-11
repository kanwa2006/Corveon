"""Liveness/readiness (docs/API.md — Health; docs/DEBUGGING.md §16)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, Any]:
    checks: dict[str, str] = {}
    healthy = True

    try:
        await request.app.state.db.ping()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        healthy = False

    if request.app.state.db.has_read_replica:
        try:
            await request.app.state.db.ping_replica()
            checks["database_replica"] = "ok"
        except Exception as exc:
            checks["database_replica"] = f"error: {exc}"
            healthy = False

    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        healthy = False

    response.status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
