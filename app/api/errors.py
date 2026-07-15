"""Maps service-layer exceptions to HTTP responses.

Services raise domain exceptions and never import HTTP concepts; this
module is the single place where those become status codes. Starlette
matches handlers by MRO, so subclasses (e.g. PlaidItemLoginRequiredError)
hit the most specific handler registered.
"""

import logging
import math

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
    NotFoundError,
    PlaidConfigurationError,
    PlaidItemLoginRequiredError,
    PlaidServiceError,
    RateLimitedError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthenticationError)
    async def unauthenticated(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(RateLimitedError)
    async def rate_limited(request: Request, exc: RateLimitedError) -> JSONResponse:
        retry_after = max(1, math.ceil(exc.retry_after_seconds))
        return JSONResponse(
            status_code=429,
            content={"detail": str(exc)},
            headers={"Retry-After": str(retry_after)},
        )

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(PlaidItemLoginRequiredError)
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

    @app.exception_handler(PlaidServiceError)
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

    @app.exception_handler(PlaidConfigurationError)
    async def plaid_misconfigured(
        request: Request, exc: PlaidConfigurationError
    ) -> JSONResponse:
        logger.error("Plaid configuration error: %s", exc)
        return JSONResponse(
            status_code=503, content={"detail": "Plaid integration is not configured"}
        )

    # --- AI layer (Starlette matches by MRO: subclasses first) ---

    @app.exception_handler(LLMRateLimitError)
    async def llm_rate_limited(
        request: Request, exc: LLMRateLimitError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "the assistant is busy; try again shortly"},
        )

    @app.exception_handler(LLMTimeoutError)
    async def llm_timeout(request: Request, exc: LLMTimeoutError) -> JSONResponse:
        return JSONResponse(
            status_code=504, content={"detail": "the assistant timed out"}
        )

    @app.exception_handler(LLMError)
    async def llm_error(request: Request, exc: LLMError) -> JSONResponse:
        # 502: we are the client of an upstream API that failed
        logger.error("LLM upstream failure: %s", exc)
        return JSONResponse(
            status_code=502, content={"detail": "the assistant is unavailable"}
        )

    @app.exception_handler(LLMConfigurationError)
    async def llm_misconfigured(
        request: Request, exc: LLMConfigurationError
    ) -> JSONResponse:
        logger.error("LLM configuration error: %s", exc)
        return JSONResponse(
            status_code=503, content={"detail": "LLM integration is not configured"}
        )

    @app.exception_handler(AgentLoopError)
    async def agent_loop_exceeded(
        request: Request, exc: AgentLoopError
    ) -> JSONResponse:
        logger.error("agent loop exhausted: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "the assistant could not complete the request"},
        )
