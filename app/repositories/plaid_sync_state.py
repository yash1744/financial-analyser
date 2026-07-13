import uuid

from sqlalchemy import select

from app.models.plaid_sync_state import PlaidSyncState
from app.repositories.base import BaseRepository


class PlaidSyncStateRepository(BaseRepository):
    async def get_for_item(self, plaid_item_id: uuid.UUID) -> PlaidSyncState | None:
        result = await self.session.execute(
            select(PlaidSyncState).where(PlaidSyncState.plaid_item_id == plaid_item_id)
        )
        return result.scalar_one_or_none()

    async def create_for_item(self, plaid_item_id: uuid.UUID) -> PlaidSyncState:
        state = PlaidSyncState(plaid_item_id=plaid_item_id)
        self.session.add(state)
        await self.session.flush()
        return state
