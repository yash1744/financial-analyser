"""Maps service-layer exceptions to HTTP responses.

Services raise domain exceptions and never import HTTP concepts; this
module is the single place where those become status codes. Starlette
matches handlers by MRO, so subclasses (e.g. PlaidItemLoginRequiredError)
hit the most specific handler registered.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    ConflictError,
    NotFoundError,
    PlaidConfigurationError,
    PlaidItemLoginRequiredError,
    PlaidServiceError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
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
