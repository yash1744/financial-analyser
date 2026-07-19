"""LabelService: user-scoped tags, and their assignment to transactions.

Every operation resolves ownership directly — labels via user_id, and
transactions via the existing account→item→user chain — so a foreign
label or transaction id behaves exactly like a missing one (404), the
same convention ReceiptService uses.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.label import Label
from app.models.transaction import Transaction
from app.repositories.label import LabelRepository
from app.repositories.transaction import TransactionRepository
from app.repositories.user import UserRepository
from app.schemas.label import LabelCreate, LabelResponse, LabelUpdate
from app.schemas.transaction import TransactionResponse
from app.services.exceptions import ConflictError, NotFoundError


class LabelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.transactions = TransactionRepository(session)
        self.labels = LabelRepository(session)

    # --- label management ---

    async def list_labels(self, user_id: uuid.UUID) -> list[LabelResponse]:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")
        labels = await self.labels.list_for_user(user_id)
        return [LabelResponse.model_validate(label) for label in labels]

    async def create_label(self, user_id: uuid.UUID, body: LabelCreate) -> LabelResponse:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")
        name = body.name.strip()
        existing = await self.labels.list_for_user(user_id)
        if any(label.name == name for label in existing):
            raise ConflictError(f"a label named {name!r} already exists")

        label = await self.labels.create(user_id=user_id, name=name)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            # Lost a race with a concurrent create of the same name
            await self.session.rollback()
            raise ConflictError(f"a label named {name!r} already exists") from exc
        return LabelResponse.model_validate(label)

    async def rename_label(
        self, user_id: uuid.UUID, label_id: uuid.UUID, body: LabelUpdate
    ) -> LabelResponse:
        label = await self._owned_label(user_id, label_id)
        name = body.name.strip()
        others = await self.labels.list_for_user(user_id)
        if any(other.name == name and other.id != label.id for other in others):
            raise ConflictError(f"a label named {name!r} already exists")

        label.name = name
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"a label named {name!r} already exists") from exc
        return LabelResponse.model_validate(label)

    async def delete_label(self, user_id: uuid.UUID, label_id: uuid.UUID) -> None:
        label = await self._owned_label(user_id, label_id)
        await self.session.delete(label)
        await self.session.commit()

    # --- transaction assignment ---

    async def assign_label(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, label_id: uuid.UUID
    ) -> TransactionResponse:
        transaction = await self._owned_transaction(user_id, transaction_id)
        label = await self._owned_label(user_id, label_id)
        if not await self.labels.is_assigned(transaction.id, label.id):
            await self.labels.assign(transaction.id, label.id)
            await self.session.commit()
            # expire_on_commit=False means the `labels` collection loaded
            # inside _owned_transaction() above is left stale after commit
            # (the identity map keeps this same instance) — refresh it
            # explicitly rather than relying on the commit to invalidate it.
            await self.session.refresh(transaction, attribute_names=["labels"])
        return TransactionResponse.model_validate(transaction)

    async def unassign_label(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, label_id: uuid.UUID
    ) -> TransactionResponse:
        transaction = await self._owned_transaction(user_id, transaction_id)
        label = await self._owned_label(user_id, label_id)
        await self.labels.unassign(transaction.id, label.id)
        await self.session.commit()
        await self.session.refresh(transaction, attribute_names=["labels"])
        return TransactionResponse.model_validate(transaction)

    # --- internals ---

    async def _owned_label(self, user_id: uuid.UUID, label_id: uuid.UUID) -> Label:
        label = await self.labels.get_for_user(label_id, user_id)
        if label is None:
            raise NotFoundError(f"label {label_id} does not exist")
        return label

    async def _owned_transaction(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> Transaction:
        transaction = await self.transactions.get_for_user(transaction_id, user_id)
        if transaction is None:
            raise NotFoundError(f"transaction {transaction_id} does not exist")
        return transaction
