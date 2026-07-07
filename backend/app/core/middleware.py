"""Request-scoped trace_id propagation (CLAUDE.md §9)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import bind_trace_id

TRACE_HEADER = "X-Request-ID"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or str(uuid.uuid4())
        bind_trace_id(trace_id)
        response = await call_next(request)
        response.headers[TRACE_HEADER] = trace_id
        return response
