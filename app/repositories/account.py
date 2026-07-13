import uuid

from sqlalchemy import select

from app.models.account import Account
from app.models.plaid_item import PlaidItem
from app.repositories.base import BaseRepository


class AccountRepository(BaseRepository):
    async def list_for_user(
        self, user_id: uuid.UUID, plaid_item_id: uuid.UUID | None = None
    ) -> list[Account]:
        query = (
            select(Account)
            .join(PlaidItem, Account.plaid_item_id == PlaidItem.id)
            .where(PlaidItem.user_id == user_id)
            .order_by(Account.created_at)
        )
        if plaid_item_id is not None:
            query = query.where(Account.plaid_item_id == plaid_item_id)
        result = await self.session.execute(query)
        return list(result.scalars())

    async def list_for_item(self, plaid_item_id: uuid.UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account)
            .where(Account.plaid_item_id == plaid_item_id)
            .order_by(Account.created_at)
        )
        return list(result.scalars())

    async def create(
        self,
        *,
        plaid_item_id: uuid.UUID,
        plaid_account_id: str,
        name: str,
        account_type: str,
        account_subtype: str | None,
        current_balance,
        available_balance,
        currency: str,
    ) -> Account:
        account = Account(
            plaid_item_id=plaid_item_id,
            plaid_account_id=plaid_account_id,
            name=name,
            account_type=account_type,
            account_subtype=account_subtype,
            current_balance=current_balance,
            available_balance=available_balance,
            currency=currency,
        )
        self.session.add(account)
        await self.session.flush()
        return account
