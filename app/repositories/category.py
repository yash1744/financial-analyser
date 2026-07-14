import uuid

from sqlalchemy import select

from app.models.category import Category
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository):
    async def list_all(self) -> list[Category]:
        result = await self.session.execute(select(Category).order_by(Category.name))
        return list(result.scalars())

    async def get_or_create(
        self, name: str, parent_id: uuid.UUID | None
    ) -> Category:
        result = await self.session.execute(
            select(Category).where(
                Category.name == name,
                Category.parent_category_id == parent_id
                if parent_id is not None
                else Category.parent_category_id.is_(None),
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            return existing
        category = Category(name=name, parent_category_id=parent_id)
        self.session.add(category)
        await self.session.flush()  # assign the id
        return category
