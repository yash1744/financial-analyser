"""UserCategoryService: a user's own rollup buckets, and their mapping
onto Plaid's global category taxonomy.

Ownership: UserCategory carries user_id directly (same shape as Label).
CategoryMapping's Plaid-side (category_id) needs only existence checked —
Category is a shared, unowned taxonomy — while its user_category_id side
is ownership-checked the same way a label assignment is.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_category import UserCategory
from app.repositories.category import CategoryRepository
from app.repositories.user import UserRepository
from app.repositories.user_category import UserCategoryRepository
from app.schemas.user_category import (
    CategoryMappingResponse,
    UserCategoryCreate,
    UserCategoryResponse,
    UserCategoryUpdate,
)
from app.services.exceptions import ConflictError, NotFoundError


class UserCategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.categories = CategoryRepository(session)
        self.user_categories = UserCategoryRepository(session)

    # --- user category management ---

    async def list_categories(self, user_id: uuid.UUID) -> list[UserCategoryResponse]:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")
        categories = await self.user_categories.list_for_user(user_id)
        return [UserCategoryResponse.model_validate(c) for c in categories]

    async def create_category(
        self, user_id: uuid.UUID, body: UserCategoryCreate
    ) -> UserCategoryResponse:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")
        name = body.name.strip()
        existing = await self.user_categories.list_for_user(user_id)
        if any(c.name == name for c in existing):
            raise ConflictError(f"a category named {name!r} already exists")

        category = await self.user_categories.create(user_id=user_id, name=name)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"a category named {name!r} already exists") from exc
        return UserCategoryResponse.model_validate(category)

    async def rename_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID, body: UserCategoryUpdate
    ) -> UserCategoryResponse:
        category = await self._owned_category(user_id, category_id)
        name = body.name.strip()
        others = await self.user_categories.list_for_user(user_id)
        if any(other.name == name and other.id != category.id for other in others):
            raise ConflictError(f"a category named {name!r} already exists")

        category.name = name
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"a category named {name!r} already exists") from exc
        return UserCategoryResponse.model_validate(category)

    async def delete_category(self, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
        category = await self._owned_category(user_id, category_id)
        await self.session.delete(category)
        await self.session.commit()

    # --- mapping Plaid categories onto a user category ---

    async def list_mappings(self, user_id: uuid.UUID) -> list[CategoryMappingResponse]:
        mappings = await self.user_categories.list_mappings_for_user(user_id)
        return [CategoryMappingResponse.model_validate(m) for m in mappings]

    async def set_mapping(
        self, user_id: uuid.UUID, category_id: uuid.UUID, user_category_id: uuid.UUID
    ) -> CategoryMappingResponse:
        if await self.categories.get(category_id) is None:
            raise NotFoundError(f"category {category_id} does not exist")
        await self._owned_category(user_id, user_category_id)  # 404s if not the caller's

        mapping = await self.user_categories.set_mapping(user_id, category_id, user_category_id)
        await self.session.commit()
        return CategoryMappingResponse.model_validate(mapping)

    async def remove_mapping(self, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
        await self.user_categories.remove_mapping(user_id, category_id)
        await self.session.commit()

    # --- internals ---

    async def _owned_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> UserCategory:
        category = await self.user_categories.get_for_user(category_id, user_id)
        if category is None:
            raise NotFoundError(f"category {category_id} does not exist")
        return category
