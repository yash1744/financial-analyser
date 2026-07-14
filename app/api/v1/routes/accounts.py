import uuid

from fastapi import APIRouter

from app.api.deps import AccountQueryServiceDep, CurrentUserDep
from app.schemas.account import AccountResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    user: CurrentUserDep,
    service: AccountQueryServiceDep,
    item_id: uuid.UUID | None = None,
) -> list[AccountResponse]:
    """All synced accounts of the authenticated user, optionally one item's."""
    return await service.list_accounts(user.id, item_id)
