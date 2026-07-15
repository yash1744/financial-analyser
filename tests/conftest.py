import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.db.session import SessionFactory, engine
from app.models.plaid_item import PlaidItem

TEST_PASSWORD = "test-password-123"  # noqa: S105 — test fixture credential


async def register_user(
    client: AsyncClient, email: str | None = None
) -> tuple[dict[str, str], str]:
    """Register a fresh user; returns (auth headers, user_id)."""
    email = email or f"t-{uuid.uuid4().hex[:12]}@example.com"
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # registration also sets the httpOnly auth cookie; drop it so tests
    # authenticate explicitly via headers (anonymous 401 asserts stay valid)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return headers, body["user"]["id"]


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
