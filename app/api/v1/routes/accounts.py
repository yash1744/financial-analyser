import uuid

from fastapi import APIRouter

from app.api.deps import AccountQueryServiceDep, CurrentUserDep
from app.schemas.account import AccountNicknameUpdate, AccountResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    user: CurrentUserDep,
    service: AccountQueryServiceDep,
    item_id: uuid.UUID | None = None,
) -> list[AccountResponse]:
    """All synced accounts of the authenticated user, optionally one item's."""
    return await service.list_accounts(user.id, item_id)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account_nickname(
    account_id: uuid.UUID,
    body: AccountNicknameUpdate,
    user: CurrentUserDep,
    service: AccountQueryServiceDep,
) -> AccountResponse:
    """Set or clear an account's nickname (null/blank clears it, reverting
    the display to the original Plaid name). The Plaid name is preserved."""
    return await service.set_nickname(user.id, account_id, body.nickname)
