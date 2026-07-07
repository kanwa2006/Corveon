"""Prometheus metrics (docs/DEBUGGING.md §16) — request count + latency,
exposed at /metrics. Per-agent/per-provider metrics land with those subsystems."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import Counter, Histogram, make_asgi_app
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "corveon_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "corveon_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        route = request.scope.get("route")
        path = route.path if route is not None else request.url.path

        REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(duration)
        return response


def mount_metrics(app: Starlette) -> None:
    app.mount("/metrics", make_asgi_app())
