from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import (
    CurrentUserDep,
    TransactionQueryServiceDep,
    TransactionSyncServiceDep,
)
from app.schemas.transaction import (
    PaginatedTransactionsResponse,
    TransactionListQuery,
    TransactionsSyncApiRequest,
    TransactionsSyncApiResponse,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=PaginatedTransactionsResponse)
async def list_transactions(
    query: Annotated[TransactionListQuery, Query()],
    user: CurrentUserDep,
    service: TransactionQueryServiceDep,
) -> PaginatedTransactionsResponse:
    """Filterable, sortable, paginated view of the user's transactions."""
    return await service.list_transactions(user.id, query)


@router.post("/sync", response_model=TransactionsSyncApiResponse)
async def sync_transactions(
    body: TransactionsSyncApiRequest,
    user: CurrentUserDep,
    service: TransactionSyncServiceDep,
) -> TransactionsSyncApiResponse:
    """Pull transaction changes from Plaid via cursor-based /transactions/sync."""
    summaries = await service.sync_transactions(user.id, body.item_id)
    return TransactionsSyncApiResponse(items=summaries)
