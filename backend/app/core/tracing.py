"""OpenTelemetry tracing (docs/DEBUGGING.md §16).

Every request gets a span via FastAPI auto-instrumentation. Agent- and
provider-level spans are added as those subsystems land (Month 1 roadmap);
this module wires the process-wide tracer provider and exporter now so later
features only need ``tracer.start_as_current_span(...)``.

When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset, spans are still created (so
in-process code can rely on the API) but are not exported anywhere — a
deliberate no-op, not an error, matching the "absence is normal" policy for
optional infrastructure.
"""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import Settings


def configure_tracing(settings: Settings) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: settings.OTEL_SERVICE_NAME}))
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def instrument_app(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
