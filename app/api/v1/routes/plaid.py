from fastapi import APIRouter

from app.api.deps import AccountSyncServiceDep, PlaidLinkServiceDep
from app.schemas.account import AccountsSyncRequest, AccountsSyncResponse
from app.schemas.plaid import (
    ExchangeTokenRequest,
    LinkTokenRequest,
    LinkTokenResponse,
    PlaidItemResponse,
)

router = APIRouter(prefix="/plaid", tags=["plaid"])


@router.post("/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    body: LinkTokenRequest, service: PlaidLinkServiceDep
) -> LinkTokenResponse:
    """Step 1 of the Link flow: token the frontend hands to Plaid Link."""
    result = await service.create_link_token(body.user_id)
    return LinkTokenResponse(link_token=result.link_token, expiration=result.expiration)


@router.post("/exchange-token", response_model=PlaidItemResponse, status_code=201)
async def exchange_public_token(
    body: ExchangeTokenRequest, service: PlaidLinkServiceDep
) -> PlaidItemResponse:
    """Step 2: trade Link's public_token for a stored, encrypted connection."""
    item = await service.exchange_public_token(body.user_id, body.public_token)
    return PlaidItemResponse.model_validate(item)


@router.post("/accounts/sync", response_model=AccountsSyncResponse)
async def sync_accounts(
    body: AccountsSyncRequest, service: AccountSyncServiceDep
) -> AccountsSyncResponse:
    """Fetch accounts for one item (or all the user's items) and upsert them."""
    summaries = await service.sync_accounts(body.user_id, body.item_id)
    return AccountsSyncResponse(items=summaries)
