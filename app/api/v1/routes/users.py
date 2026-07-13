from fastapi import APIRouter

from app.api.deps import UserServiceDep
from app.schemas.user import UserCreateRequest, UserResponse

# Minimal user creation so the Plaid flow has someone to link against.
# Replaced by real signup once authentication lands.
router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreateRequest, service: UserServiceDep) -> UserResponse:
    user = await service.create_user(body.email)
    return UserResponse.model_validate(user)
