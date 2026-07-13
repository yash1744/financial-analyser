from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db_session
from app.main import app


async def test_health_reports_ok_when_db_is_up():
    session = AsyncMock()
    app.dependency_overrides[get_db_session] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


async def test_health_reports_degraded_when_db_is_down():
    session = AsyncMock()
    session.execute.side_effect = ConnectionError("db unreachable")
    app.dependency_overrides[get_db_session] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "down"
