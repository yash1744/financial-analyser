import pytest

from app.db.session import engine


@pytest.fixture(autouse=True)
async def dispose_engine_pool():
    """Each test runs in its own event loop, but the engine is module-level.

    asyncpg connections are bound to the loop that created them, so the
    pool must be emptied before the loop closes or the next test inherits
    dead connections ("Event loop is closed").
    """
    yield
    await engine.dispose()
