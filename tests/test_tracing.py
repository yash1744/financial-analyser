"""OpenTelemetry wiring tests.

app.main.create_app() calls setup_tracing() exactly once at import time
(TracerProvider.set is a one-shot in the OTel API — a second call is a
silent no-op with a warning). So these tests don't swap the provider;
they attach an extra SimpleSpanProcessor(InMemorySpanExporter()) onto
the provider that already exists, alongside whatever the default ("none")
exporter configured, and read spans back from that.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import app
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def span_exporter():
    """An InMemorySpanExporter attached to the app's real TracerProvider,
    so custom spans created via app.core.tracing.traced_span (and the
    auto-instrumented FastAPI/SQLAlchemy spans) show up here exactly as
    they would for any other configured exporter."""
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider), (
        "app.main.create_app() should have called setup_tracing() at import time"
    )
    exporter = InMemorySpanExporter()
    # Simple, not Batch: exports synchronously so spans are visible the
    # instant the span ends, no flush/timing race in the test.
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter
    exporter.clear()


def _by_name(spans: list[ReadableSpan], name: str) -> ReadableSpan:
    matches = [s for s in spans if s.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r} span, found {len(matches)}"
    return matches[0]


def _all_attribute_values(spans: list[ReadableSpan]) -> list[str]:
    """Every attribute value across every span, plus every recorded
    exception's message/stacktrace — the full surface a PII leak could
    hide in."""
    values: list[str] = []
    for span in spans:
        for value in (span.attributes or {}).values():
            values.append(str(value))
        for event in span.events:
            for value in (event.attributes or {}).values():
                values.append(str(value))
    return values


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_register_produces_a_custom_span_with_user_id_not_email(span_exporter):
    email = f"trace-{uuid.uuid4().hex[:12]}@example.com"
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 201, resp.text
        user_id = resp.json()["user"]["id"]

    spans = span_exporter.get_finished_spans()
    span = _by_name(spans, "auth.register")
    assert span.attributes["user.id"] == user_id
    assert span.status.status_code.name == "UNSET"  # no error recorded

    # the email must not have leaked into any span attribute or event
    haystack = " ".join(_all_attribute_values(spans))
    assert email not in haystack


async def test_duplicate_register_error_is_recorded_without_the_email(span_exporter):
    email = f"trace-dup-{uuid.uuid4().hex[:12]}@example.com"
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 201
        # duplicate: the ConflictError's message embeds the raw email —
        # this must not reach the span, on either the redacted custom
        # span or the central request-level recording in api/errors.py
        resp = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 409
        # the HTTP response body is allowed to carry the email — that's
        # the existing, unrelated API contract, not a tracing concern
        assert email in resp.text

    spans = span_exporter.get_finished_spans()
    register_spans = [s for s in spans if s.name == "auth.register"]
    assert len(register_spans) == 2
    failed = next(s for s in register_spans if s.status.status_code.name == "ERROR")
    assert failed.status.description == "ConflictError"

    haystack = " ".join(_all_attribute_values(spans))
    assert email not in haystack


async def test_traced_span_records_exception_exactly_once(span_exporter):
    """start_as_current_span defaults to record_exception=True /
    set_status_on_exception=True — traced_span must disable both and do
    its own (redaction-aware) recording, or every error gets logged
    twice: once correctly, once as the raw, unredacted exception from
    OTel's own default behavior. That second copy is exactly how the
    email leak in the two tests above would have shipped."""
    from app.core.tracing import traced_span

    with pytest.raises(ValueError):
        with traced_span("test.exactly_once"):
            raise ValueError("non-PII operational detail")

    spans = span_exporter.get_finished_spans()
    span = _by_name(spans, "test.exactly_once")
    assert len(span.events) == 1
    assert span.status.description == "non-PII operational detail"


async def test_login_failure_records_no_email(span_exporter):
    email = f"trace-login-{uuid.uuid4().hex[:12]}@example.com"
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert resp.status_code == 401

    spans = span_exporter.get_finished_spans()
    span = _by_name(spans, "auth.login")
    assert span.status.status_code.name == "ERROR"
    haystack = " ".join(_all_attribute_values(spans))
    assert email not in haystack


async def test_health_request_produces_nested_http_and_db_spans(span_exporter):
    async with await _client() as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200

    spans = span_exporter.get_finished_spans()
    root = _by_name(spans, "GET /api/v1/health")
    assert root.parent is None
    assert root.attributes["http.status_code"] == 200

    span_by_id = {s.context.span_id: s for s in spans}
    # at least one DB span (the health check's connectivity SELECT)
    # nests directly under the request span
    db_children = [
        s
        for s in spans
        if s.parent is not None
        and span_by_id.get(s.parent.span_id) is root
        and s.name in ("connect", "SELECT")
    ]
    assert db_children, "expected a DB span nested under the request span"
