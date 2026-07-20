import uuid

from sqlalchemy import select

from app.models.user_category import CategoryMapping, UserCategory
from app.repositories.base import BaseRepository


class UserCategoryRepository(BaseRepository):
    async def list_for_user(self, user_id: uuid.UUID) -> list[UserCategory]:
        result = await self.session.execute(
            select(UserCategory)
            .where(UserCategory.user_id == user_id)
            .order_by(UserCategory.name)
        )
        return list(result.scalars())

    async def get_for_user(
        self, user_category_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserCategory | None:
        result = await self.session.execute(
            select(UserCategory).where(
                UserCategory.id == user_category_id, UserCategory.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create(self, *, user_id: uuid.UUID, name: str) -> UserCategory:
        user_category = UserCategory(user_id=user_id, name=name)
        self.session.add(user_category)
        await self.session.flush()  # assign the id; surfaces the unique-name conflict early
        return user_category

    async def list_mappings_for_user(self, user_id: uuid.UUID) -> list[CategoryMapping]:
        result = await self.session.execute(
            select(CategoryMapping).where(CategoryMapping.user_id == user_id)
        )
        return list(result.scalars())

    async def get_mapping(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> CategoryMapping | None:
        result = await self.session.execute(
            select(CategoryMapping).where(
                CategoryMapping.user_id == user_id,
                CategoryMapping.category_id == category_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_mapping(
        self, user_id: uuid.UUID, category_id: uuid.UUID, user_category_id: uuid.UUID
    ) -> CategoryMapping:
        """Create the mapping, or repoint it if one already exists for this
        (user, Plaid category) — the PK is (user_id, category_id), so a
        category can only ever map to one user category at a time."""
        mapping = await self.get_mapping(user_id, category_id)
        if mapping is None:
            mapping = CategoryMapping(
                user_id=user_id, category_id=category_id, user_category_id=user_category_id
            )
            self.session.add(mapping)
        else:
            mapping.user_category_id = user_category_id
        await self.session.flush()
        return mapping

    async def remove_mapping(self, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
        mapping = await self.get_mapping(user_id, category_id)
        if mapping is not None:
            await self.session.delete(mapping)
