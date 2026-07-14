"""Authentication endpoints: register, login, current user."""

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUserDep
from app.schemas.auth import AuthUser, LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, auth: AuthServiceDep) -> TokenResponse:
    user, token = await auth.register(body.email, body.password)
    return TokenResponse(access_token=token, user=AuthUser.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, auth: AuthServiceDep) -> TokenResponse:
    user, token = await auth.login(body.email, body.password)
    return TokenResponse(access_token=token, user=AuthUser.model_validate(user))


@router.get("/me", response_model=AuthUser)
async def me(user: CurrentUserDep) -> AuthUser:
    return AuthUser.model_validate(user)
