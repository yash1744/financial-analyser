"""Rate limiting on credential endpoints: sliding-window unit behavior
and the 429 + Retry-After contract on /auth/login and /auth/register."""

import uuid

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_auth_rate_limiter
from app.core.rate_limit import SlidingWindowLimiter
from app.db.session import SessionFactory
from app.main import app
from app.models.user import User
from tests.conftest import TEST_PASSWORD, register_user


def test_sliding_window_limiter():
    clock = [0.0]
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60, time_func=lambda: clock[0])

    assert limiter.check("k") is None
    assert limiter.check("k") is None
    assert limiter.check("k") is None
    # 4th within the window is refused, with time-to-retry
    wait = limiter.check("k")
    assert wait is not None and 0 < wait <= 60

    # other keys are independent
    assert limiter.check("other") is None

    # once the oldest attempt leaves the window, attempts flow again
    clock[0] = 61.0
    assert limiter.check("k") is None


async def test_login_brute_force_gets_429():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    app.dependency_overrides[get_auth_rate_limiter] = lambda: limiter

    transport = ASGITransport(app=app)
    user_id = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, user_id = await register_user(client)
            email_resp = await client.get("/api/v1/auth/me", headers=headers)
            email = email_resp.json()["email"]

            # register consumed one attempt for this (ip, email) key;
            # two failed logins exhaust the limit of 3
            for _ in range(2):
                resp = await client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": "wrong-password"},
                )
                assert resp.status_code == 401

            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
            )
            assert resp.status_code == 429
            assert int(resp.headers["retry-after"]) >= 1

            # even the CORRECT password is refused while throttled —
            # the limiter counts attempts, not failures
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": TEST_PASSWORD},
            )
            assert resp.status_code == 429

            # a different account from the same client is unaffected
            resp = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": f"other-{uuid.uuid4().hex[:8]}@example.com",
                    "password": "irrelevant-pass",
                },
            )
            assert resp.status_code == 401

            # register is throttled by the same mechanism: one success,
            # two conflicts = 3 attempts on the key; the 4th is refused
            reg_email = f"flood-{uuid.uuid4().hex[:8]}@example.com"
            resp = await client.post(
                "/api/v1/auth/register",
                json={"email": reg_email, "password": TEST_PASSWORD},
            )
            assert resp.status_code == 201
            client.cookies.clear()
            for _ in range(2):
                resp = await client.post(
                    "/api/v1/auth/register",
                    json={"email": reg_email, "password": TEST_PASSWORD},
                )
                assert resp.status_code == 409
            resp = await client.post(
                "/api/v1/auth/register",
                json={"email": reg_email, "password": TEST_PASSWORD},
            )
            assert resp.status_code == 429
    finally:
        app.dependency_overrides.clear()
        async with SessionFactory() as session:
            if user_id is not None:
                user = await session.get(User, uuid.UUID(user_id))
                await session.delete(user)
            from sqlalchemy import delete

            await session.execute(delete(User).where(User.email.like("flood-%")))
            await session.commit()