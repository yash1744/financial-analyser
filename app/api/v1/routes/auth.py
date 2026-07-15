"""Authentication endpoints: register, login, logout, current user.

The JWT is delivered two ways at once:
- an httpOnly SameSite=Lax cookie — what the browser app uses; JS can't
  read it, so an XSS can't exfiltrate the credential, and Lax blocks
  cross-site POSTs (CSRF)
- the response body — for API clients (curl, tests) that send it back as
  an Authorization: Bearer header
"""

from fastapi import APIRouter, Response, status

from app.api.deps import AuthServiceDep, CurrentUserDep, SettingsDep
from app.core.config import Settings
from app.schemas.auth import AuthUser, LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_COOKIE = "access_token"


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
    auth: AuthServiceDep,
    settings: SettingsDep,
    response: Response,
) -> TokenResponse:
    user, token = await auth.register(body.email, body.password)
    _set_auth_cookie(response, token, settings)
    return TokenResponse(access_token=token, user=AuthUser.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    auth: AuthServiceDep,
    settings: SettingsDep,
    response: Response,
) -> TokenResponse:
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
