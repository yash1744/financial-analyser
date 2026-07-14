"""Maps Plaid's personal_finance_category taxonomy onto Category rows.

Plaid attaches `{"primary": "FOOD_AND_DRINK", "detailed":
"FOOD_AND_DRINK_COFFEE", ...}` to every transaction. The resolver turns
that into a two-level category tree — primary → parent row ("Food and
Drink"), detailed suffix → child row ("Coffee") — creating rows on first
sight and caching them so a sync run hits the database once per distinct
category. (Plaid's legacy `category` string list is deprecated and not
consulted.)
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.category import CategoryRepository

_MINOR_WORDS = {"and", "or", "of", "the", "a", "an", "in", "to"}


def humanize_code(code: str) -> str:
    """FOOD_AND_DRINK → "Food and Drink"."""
    words = code.lower().split("_")
    return " ".join(
        word if i > 0 and word in _MINOR_WORDS else word.capitalize()
        for i, word in enumerate(words)
    )


def _detailed_suffix(primary: str, detailed: str) -> str:
    """FOOD_AND_DRINK_COFFEE (under FOOD_AND_DRINK) → COFFEE."""
    return detailed.removeprefix(primary).strip("_")


class CategoryResolver:
    def __init__(self, session: AsyncSession) -> None:
        self.categories = CategoryRepository(session)
        # (name, parent_id) → category id
        self._cache: dict[tuple[str, uuid.UUID | None], uuid.UUID] = {}

    async def resolve(self, entry: dict[str, Any]) -> uuid.UUID | None:
        """Category id for one Plaid transaction payload; None when Plaid
        sent no personal_finance_category."""
        pfc = entry.get("personal_finance_category") or {}
        primary = pfc.get("primary")
        if not primary:
            return None
        parent_id = await self._get_or_create(humanize_code(primary), None)
        suffix = _detailed_suffix(primary, pfc.get("detailed") or "")
        if not suffix:
            return parent_id
        return await self._get_or_create(humanize_code(suffix), parent_id)

    async def _get_or_create(
        self, name: str, parent_id: uuid.UUID | None
    ) -> uuid.UUID:
        key = (name, parent_id)
        cached = self._cache.get(key)
        if cached is None:
            category = await self.categories.get_or_create(name, parent_id)
            cached = self._cache[key] = category.id
        return cached
