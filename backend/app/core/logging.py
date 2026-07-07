"""Structured logging (structlog, wired through the stdlib ``logging`` module).

CLAUDE.md §9: every new code path adds a structured log carrying the request/job
``trace_id``. ``trace_id_var`` is a contextvar bound once per request/job by
middleware or worker wrapper; ``get_logger`` returns a structlog logger that
picks it up automatically via a bound processor.

Routed through stdlib ``logging`` (structlog's recommended dual pipeline) so
third-party libraries that log via the stdlib (uvicorn, sqlalchemy, ...) render
with the same JSON/console formatter as our own structlog calls.
"""

from __future__ import annotations

import contextvars
import logging
import sys

import structlog
from structlog.types import EventDict

from app.core.config import Settings

trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def _inject_trace_id(logger: object, method_name: str, event_dict: EventDict) -> EventDict:
    trace_id = trace_id_var.get()
    if trace_id is not None:
        event_dict["trace_id"] = trace_id
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure structlog + stdlib logging once at process startup."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_trace_id,
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.LOG_FORMAT == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def bind_trace_id(trace_id: str) -> None:
    trace_id_var.set(trace_id)
