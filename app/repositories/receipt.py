import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.receipt import Receipt, ReceiptImage
from app.repositories.base import BaseRepository


class ReceiptRepository(BaseRepository):
    async def get_for_transaction(self, transaction_id: uuid.UUID) -> Receipt | None:
        result = await self.session.execute(
            select(Receipt)
            .where(Receipt.transaction_id == transaction_id)
            .options(selectinload(Receipt.images))
        )
        return result.scalar_one_or_none()

    async def create(self, transaction_id: uuid.UUID) -> Receipt:
        receipt = Receipt(transaction_id=transaction_id)
        self.session.add(receipt)
        await self.session.flush()
        # a fresh receipt has no images; set the collection so response
        # serialization doesn't trigger a lazy load
        await self.session.refresh(receipt, ["images"])
        return receipt

    async def get_image(
        self, receipt_id: uuid.UUID, image_id: uuid.UUID
    ) -> ReceiptImage | None:
        result = await self.session.execute(
            select(ReceiptImage).where(
                ReceiptImage.id == image_id,
                ReceiptImage.receipt_id == receipt_id,
            )
        )
        return result.scalar_one_or_none()

    def add_image(
        self,
        receipt: Receipt,
        *,
        storage_key: str,
        content_type: str,
        file_name: str,
        size_bytes: int,
    ) -> ReceiptImage:
        image = ReceiptImage(
            storage_key=storage_key,
            content_type=content_type,
            file_name=file_name,
            size_bytes=size_bytes,
        )
        # assign via the relationship so receipt.images reflects the new
        # image in memory (the session uses expire_on_commit=False, so a
        # re-query would return the stale cached collection)
        image.receipt = receipt
        self.session.add(image)
        return image
