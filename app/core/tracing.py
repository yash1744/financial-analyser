"""OpenTelemetry setup: one TracerProvider for the process, wired to
whatever exporter OTEL_TRACES_EXPORTER selects, plus the tracer every
custom span in the app pulls from.

Default is "none" — the SDK and every automatic instrumentation still
run (so the code paths that create spans are always exercised and any
misuse fails fast), but nothing is exported. That's what makes this safe
to leave on by default in CI and local dev: no backend, no network call,
no setup required. Point OTEL_TRACES_EXPORTER at "console" or "otlp" to
actually see traces.
"""

import logging
from collections.abc import Generator, Mapping
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, Status, StatusCode

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Mirrors pyproject.toml's [project].version — this app has no
# [build-system], so it's never installed as a package and
# importlib.metadata can't discover its version at runtime.
_APP_VERSION = "0.1.0"

# The tracer every custom span in the app pulls from (app/ai/agent.py,
# app/services/*.py, ...). Module-level like `logging.getLogger(__name__)`
# — safe before setup_tracing() runs; spans are just no-ops until then.
tracer = trace.get_tracer("finance-app")


@contextmanager
def traced_span(
    name: str,
    attributes: Mapping[str, str | int | float | bool] | None = None,
    *,
    redact_errors: bool = False,
) -> Generator[Span]:
    """Start a custom span around a business operation and standardize
    error recording: any exception raised inside is attached to the span
    (record_exception + ERROR status) before propagating, so it shows up
    on the span in Grafana/Jaeger without every call site repeating that
    boilerplate. Never swallows — the caller's exception handling is
    unaffected.

    redact_errors=True records only the exception's type, not its message
    or traceback — some domain exceptions (e.g. AuthService's ConflictError
    on a duplicate email) embed user-supplied PII in their message, which
    must not end up in a trace even though it's fine in an HTTP response
    body. Use this for any span wrapping a flow where that can happen.
    """
    # record_exception/set_status_on_exception disabled: those are
    # start_as_current_span's own defaults, and they'd record the RAW
    # exception (no redaction) a second time on top of the handling
    # below — exactly the leak redact_errors exists to prevent. The
    # except clause here is the only place that records anything.
    with tracer.start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) as span:
        if attributes:
            span.set_attributes(attributes)
        try:
            yield span
        except Exception as exc:
            if redact_errors:
                span.record_exception(type(exc)(type(exc).__name__))
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            else:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def _build_exporter(settings: Settings) -> SpanExporter | None:
    if settings.otel_traces_exporter == "otlp":
        headers = dict(
            pair.split("=", 1) for pair in settings.otel_exporter_otlp_headers.split(",") if pair
        )
        return OTLPSpanExporter(
            endpoint=f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces",
            headers=headers or None,
        )
    if settings.otel_traces_exporter == "console":
        return ConsoleSpanExporter()
    return None


def setup_tracing(settings: Settings, app: FastAPI) -> None:
    """Build the TracerProvider, wire the exporter, and instrument
    FastAPI/SQLAlchemy/httpx/urllib3/botocore. Called once from
    create_app(), before the app takes traffic."""
    resource = Resource.create(
        {
            SERVICE_NAME: settings.otel_service_name,
            SERVICE_VERSION: _APP_VERSION,
            "deployment.environment": settings.environment,
        }
    )
    sampler = ParentBased(TraceIdRatioBased(settings.otel_traces_sample_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = _build_exporter(settings)
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    # SQLAlchemy's instrumentor hooks engine events (before_cursor_execute,
    # etc.), which fire the same whether the engine is driven synchronously
    # or through AsyncEngine's greenlet wrapper — instrument the sync
    # engine underneath app.db.session's AsyncEngine.
    from app.db.session import engine as db_engine

    SQLAlchemyInstrumentor().instrument(
        engine=db_engine.sync_engine, tracer_provider=provider
    )
    # Anthropic/OpenAI SDKs run on httpx; plaid-python runs on urllib3;
    # boto3 (R2 storage) runs on botocore. All three call out from
    # asyncio.to_thread workers, which propagate the current span context
    # automatically (asyncio.to_thread copies contextvars into the
    # thread), so these nest correctly under the request span with no
    # extra wiring.
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    URLLib3Instrumentor().instrument(tracer_provider=provider)
    BotocoreInstrumentor().instrument(tracer_provider=provider)

    logger.info(
        "tracing initialized: exporter=%s service=%s",
        settings.otel_traces_exporter,
        settings.otel_service_name,
    )


def shutdown_tracing() -> None:
    """Flush and close the exporter on app shutdown so the last batch of
    spans (e.g. the shutdown request itself) isn't lost."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()
