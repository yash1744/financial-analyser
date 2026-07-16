"""Maps service-layer exceptions to HTTP responses.

Services raise domain exceptions and never import HTTP concepts; this
module is the single place where those become status codes. Starlette
matches handlers by MRO, so subclasses (e.g. PlaidItemLoginRequiredError)
hit the most specific handler registered.
"""

import functools
import logging
import math
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.ai.exceptions import (
    AgentLoopError,
    LLMConfigurationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.exceptions import (
    AuthenticationError,
    ConflictError,
    InvalidUploadError,
    NotFoundError,
    PlaidConfigurationError,
    PlaidItemLoginRequiredError,
    PlaidServiceError,
    RateLimitedError,
)
from app.services.storage import StorageConfigurationError

logger = logging.getLogger(__name__)

# Exception types whose message can embed user-supplied PII (e.g.
# AuthService.register's ConflictError embeds the raw email). Every
# exception reaching these handlers gets recorded on the current (request)
# span for visibility, per issue #23's "errors should be visible in
# traces" — but for these two types the exception's own message/args
# must never end up in the span, only its type. Fine-grained per-flow
# redaction already happens inside AuthService (see app/core/tracing.py's
# traced_span(redact_errors=True)); this is the backstop for the request
# span every one of these still passes through.
_PII_SENSITIVE_EXCEPTIONS = (AuthenticationError, ConflictError)


def _record_on_current_span(exc: Exception) -> None:
    span = trace.get_current_span()
    if isinstance(exc, _PII_SENSITIVE_EXCEPTIONS):
        span.record_exception(type(exc)(type(exc).__name__))
        span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
    else:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))


def _traced(app: FastAPI, exc_type: type[Exception]):
    """Drop-in replacement for @app.exception_handler(exc_type) that also
    records the exception on the current (request) span before running
    the handler — one place to get every mapped domain exception onto
    its trace, instead of repeating that line in all 13 handler bodies."""

    def decorator(
        func: Callable[[Request, Exception], Awaitable[JSONResponse]],
    ) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
        @functools.wraps(func)
        async def wrapped(request: Request, exc: Exception) -> JSONResponse:
            _record_on_current_span(exc)
            return await func(request, exc)

        app.add_exception_handler(exc_type, wrapped)
        return func

    return decorator


def register_exception_handlers(app: FastAPI) -> None:
    @_traced(app, AuthenticationError)
    async def unauthenticated(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @_traced(app, RateLimitedError)
    async def rate_limited(request: Request, exc: RateLimitedError) -> JSONResponse:
        retry_after = max(1, math.ceil(exc.retry_after_seconds))
        return JSONResponse(
            status_code=429,
            content={"detail": str(exc)},
            headers={"Retry-After": str(retry_after)},
        )

    @_traced(app, NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @_traced(app, ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @_traced(app, InvalidUploadError)
    async def invalid_upload(request: Request, exc: InvalidUploadError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @_traced(app, StorageConfigurationError)
    async def storage_misconfigured(
        request: Request, exc: StorageConfigurationError
    ) -> JSONResponse:
        logger.error("object storage configuration error: %s", exc)
        return JSONResponse(
            status_code=503, content={"detail": "file storage is not configured"}
        )

    @_traced(app, PlaidItemLoginRequiredError)
    async def plaid_login_required(
        request: Request, exc: PlaidItemLoginRequiredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "bank connection requires re-authentication",
                "plaid_error_code": exc.error_code,
            },
        )

    @_traced(app, PlaidServiceError)
    async def plaid_error(request: Request, exc: PlaidServiceError) -> JSONResponse:
        # 502: we are the client of an upstream API that failed
        logger.error(
            "Plaid upstream failure: %s (error_code=%s, request_id=%s)",
            exc,
            exc.error_code,
            exc.request_id,
        )
        return JSONResponse(
            status_code=502,
            content={"detail": str(exc), "plaid_error_code": exc.error_code},
        )

    @_traced(app, PlaidConfigurationError)
    async def plaid_misconfigured(
        request: Request, exc: PlaidConfigurationError
    ) -> JSONResponse:
        logger.error("Plaid configuration error: %s", exc)
        return JSONResponse(
            status_code=503, content={"detail": "Plaid integration is not configured"}
        )

    # --- AI layer (Starlette matches by MRO: subclasses first) ---

    @_traced(app, LLMRateLimitError)
    async def llm_rate_limited(
        request: Request, exc: LLMRateLimitError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "the assistant is busy; try again shortly"},
        )

    @_traced(app, LLMTimeoutError)
    async def llm_timeout(request: Request, exc: LLMTimeoutError) -> JSONResponse:
        return JSONResponse(
            status_code=504, content={"detail": "the assistant timed out"}
        )

    @_traced(app, LLMError)
    async def llm_error(request: Request, exc: LLMError) -> JSONResponse:
        # 502: we are the client of an upstream API that failed
        logger.error("LLM upstream failure: %s", exc)
        return JSONResponse(
            status_code=502, content={"detail": "the assistant is unavailable"}
        )

    @_traced(app, LLMConfigurationError)
    async def llm_misconfigured(
        request: Request, exc: LLMConfigurationError
    ) -> JSONResponse:
        logger.error("LLM configuration error: %s", exc)
        return JSONResponse(
            status_code=503, content={"detail": "LLM integration is not configured"}
        )

    @_traced(app, AgentLoopError)
    async def agent_loop_exceeded(
        request: Request, exc: AgentLoopError
    ) -> JSONResponse:
        logger.error("agent loop exhausted: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "the assistant could not complete the request"},
        )
