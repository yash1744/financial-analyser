import pytest
from sqlalchemy import delete

from app.db.session import SessionFactory, engine
from app.models.plaid_item import PlaidItem


@pytest.fixture(autouse=True)
async def purge_fake_items():
    """Tests seed plaid_items with fixed 'item-*' ids; a failed run leaves
    them attached to that run's user, and the next run's exchange-token
    then 409s ("connected by another user"). Purge them up front — real
    Plaid item ids never use this prefix, so dev data is untouched.
    Cascades clean the dependent accounts/transactions/sync state."""
    async with SessionFactory() as session:
        await session.execute(
            delete(PlaidItem).where(PlaidItem.plaid_item_id.like("item-%"))
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def dispose_engine_pool():
    """Each test runs in its own event loop, but the engine is module-level.

    asyncpg connections are bound to the loop that created them, so the
    pool must be emptied before the loop closes or the next test inherits
    dead connections ("Event loop is closed").
    """
    yield
    await engine.dispose()
