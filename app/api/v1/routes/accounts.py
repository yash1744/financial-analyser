import uuid

from fastapi import APIRouter

from app.api.deps import AccountQueryServiceDep
from app.schemas.account import AccountResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    user_id: uuid.UUID,
    service: AccountQueryServiceDep,
    item_id: uuid.UUID | None = None,
) -> list[AccountResponse]:
    """All synced accounts for a user, optionally narrowed to one item."""
    return await service.list_accounts(user_id, item_id)
