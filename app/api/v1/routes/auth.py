"""Authentication endpoints: register, login, logout, current user.

The JWT is delivered two ways at once:
- an httpOnly SameSite=Lax cookie — what the browser app uses; JS can't
  read it, so an XSS can't exfiltrate the credential, and Lax blocks
  cross-site POSTs (CSRF)
- the response body — for API clients (curl, tests) that send it back as
  an Authorization: Bearer header
"""

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    AuthRateLimiterDep,
    AuthServiceDep,
    CurrentUserDep,
    SettingsDep,
)
from app.core.config import Settings
from app.core.rate_limit import SlidingWindowLimiter
from app.schemas.auth import AuthUser, LoginRequest, RegisterRequest, TokenResponse
from app.services.exceptions import RateLimitedError

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_COOKIE = "access_token"


def _throttle(request: Request, email: str, limiter: SlidingWindowLimiter) -> None:
    """Rate-limit credential attempts per (client ip, email) so a single
    account can't be brute-forced online. X-Forwarded-For is only
    meaningful behind the reverse proxy that sets it; per-IP flood
    control across endpoints stays the proxy's job."""
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )
    retry_after = limiter.check(f"{client_ip}:{email.strip().lower()}")
    if retry_after is not None:
        raise RateLimitedError(
            "too many attempts; try again shortly", retry_after_seconds=retry_after
        )


def _set_auth_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        max_age=settings.jwt_expiry_hours * 3600,
        httponly=True,  # invisible to JavaScript
        samesite="lax",  # not sent on cross-site POSTs
        secure=settings.environment != "local",  # https-only outside dev
        path="/",
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    auth: AuthServiceDep,
    settings: SettingsDep,
    limiter: AuthRateLimiterDep,
    response: Response,
) -> TokenResponse:
    _throttle(request, body.email, limiter)
    user, token = await auth.register(body.email, body.password)
    _set_auth_cookie(response, token, settings)
    return TokenResponse(access_token=token, user=AuthUser.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    auth: AuthServiceDep,
    settings: SettingsDep,
    limiter: AuthRateLimiterDep,
    response: Response,
) -> TokenResponse:
    _throttle(request, body.email, limiter)
    user, token = await auth.login(body.email, body.password)
    _set_auth_cookie(response, token, settings)
    return TokenResponse(access_token=token, user=AuthUser.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clear the auth cookie (an httpOnly cookie can't be cleared by JS).
    Deliberately unauthenticated: signing out with an expired token must
    still work."""
    response.delete_cookie(key=AUTH_COOKIE, path="/")


@router.get("/me", response_model=AuthUser)
async def me(user: CurrentUserDep) -> AuthUser:
    return AuthUser.model_validate(user)
