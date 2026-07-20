import uuid

from sqlalchemy import delete, select

from app.models.label import Label, TransactionLabel
from app.repositories.base import BaseRepository


class LabelRepository(BaseRepository):
    async def list_for_user(self, user_id: uuid.UUID) -> list[Label]:
        result = await self.session.execute(
            select(Label).where(Label.user_id == user_id).order_by(Label.name)
        )
        return list(result.scalars())

    async def get_for_user(self, label_id: uuid.UUID, user_id: uuid.UUID) -> Label | None:
        result = await self.session.execute(
            select(Label).where(Label.id == label_id, Label.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, *, user_id: uuid.UUID, name: str) -> Label:
        label = Label(user_id=user_id, name=name)
        self.session.add(label)
        await self.session.flush()  # assign the id; surfaces the unique-name conflict early
        return label

    async def is_assigned(self, transaction_id: uuid.UUID, label_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(TransactionLabel).where(
                TransactionLabel.transaction_id == transaction_id,
                TransactionLabel.label_id == label_id,
            )
        )
        return result.first() is not None

    async def assign(self, transaction_id: uuid.UUID, label_id: uuid.UUID) -> None:
        self.session.add(
            TransactionLabel(transaction_id=transaction_id, label_id=label_id)
        )
        await self.session.flush()

    async def unassign(self, transaction_id: uuid.UUID, label_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(TransactionLabel).where(
                TransactionLabel.transaction_id == transaction_id,
                TransactionLabel.label_id == label_id,
            )
        )
