import uuid

from sqlalchemy import select

from app.models.enums import PlaidItemStatus
from app.models.plaid_item import PlaidItem
from app.repositories.base import BaseRepository


class PlaidItemRepository(BaseRepository):
    async def get(self, item_id: uuid.UUID) -> PlaidItem | None:
        return await self.session.get(PlaidItem, item_id)

    async def get_by_plaid_item_id(self, plaid_item_id: str) -> PlaidItem | None:
        result = await self.session.execute(
            select(PlaidItem).where(PlaidItem.plaid_item_id == plaid_item_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[PlaidItem]:
        result = await self.session.execute(
            select(PlaidItem).where(PlaidItem.user_id == user_id).order_by(PlaidItem.created_at)
        )
        return list(result.scalars())

    async def list_by_user_and_institution(
        self, user_id: uuid.UUID, institution_id: str
    ) -> list[PlaidItem]:
        result = await self.session.execute(
            select(PlaidItem)
            .where(
                PlaidItem.user_id == user_id,
                PlaidItem.institution_id == institution_id,
            )
            .order_by(PlaidItem.created_at)
        )
        return list(result.scalars())

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        plaid_item_id: str,
        access_token_encrypted: str,
        institution_id: str | None,
        institution_name: str | None,
        status: PlaidItemStatus = PlaidItemStatus.ACTIVE,
    ) -> PlaidItem:
        item = PlaidItem(
            user_id=user_id,
            plaid_item_id=plaid_item_id,
            access_token_encrypted=access_token_encrypted,
            institution_id=institution_id,
            institution_name=institution_name,
            status=status,
        )
        self.session.add(item)
        await self.session.flush()
        return item
