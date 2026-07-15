"""Read-side services: filtered views over synced data as clean DTOs.

Kept separate from the sync services (write side) — these never call
Plaid and never commit.
"""

import math
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.transaction import TransactionRepository
from app.repositories.user import UserRepository
from app.schemas.account import AccountResponse
from app.schemas.category import CategoryResponse
from app.schemas.transaction import (
    PaginatedTransactionsResponse,
    TransactionListQuery,
    TransactionResponse,
)
from app.services.exceptions import NotFoundError


class AccountQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.accounts = AccountRepository(session)

    async def list_accounts(
        self, user_id: uuid.UUID, item_id: uuid.UUID | None = None
    ) -> list[AccountResponse]:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")
        accounts = await self.accounts.list_for_user(user_id, item_id)
        return [AccountResponse.model_validate(account) for account in accounts]


class TransactionQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.transactions = TransactionRepository(session)

    async def get_transaction(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> TransactionResponse:
        transaction = await self.transactions.get_for_user(transaction_id, user_id)
        if transaction is None:
            raise NotFoundError(f"transaction {transaction_id} does not exist")
        return TransactionResponse.model_validate(transaction)

    async def list_transactions(
        self, user_id: uuid.UUID, query: TransactionListQuery
    ) -> PaginatedTransactionsResponse:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")
        rows, total = await self.transactions.search(
            user_id=user_id,
            account_id=query.account_id,
            category_id=query.category_id,
            classification=query.classification,
            merchant=query.merchant,
            start_date=query.start_date,
            end_date=query.end_date,
            min_amount=query.min_amount,
            max_amount=query.max_amount,
            sort_by=query.sort_by,
            sort_dir=query.sort_dir,
            limit=query.page_size,
            offset=(query.page - 1) * query.page_size,
        )
        return PaginatedTransactionsResponse(
            items=[TransactionResponse.model_validate(row) for row in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
            total_pages=math.ceil(total / query.page_size),
        )


class CategoryQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self.categories = CategoryRepository(session)

    async def list_categories(self) -> list[CategoryResponse]:
        categories = await self.categories.list_all()
        return [CategoryResponse.model_validate(category) for category in categories]
