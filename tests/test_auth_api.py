"""Authentication + authorization tests: register/login flows, token
enforcement on protected endpoints, and cross-user isolation."""

import uuid

from httpx import ASGITransport, AsyncClient

from app.db.session import SessionFactory
from app.main import app
from app.models.user import User
from tests.conftest import TEST_PASSWORD, register_user


async def test_register_login_me():
    transport = ASGITransport(app=app)
    email = f"auth-{uuid.uuid4().hex[:12]}@example.com"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # register issues a working token
        resp = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == email
        assert "password" not in resp.text
        headers = {"Authorization": f"Bearer {body['access_token']}"}

        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == email

        # duplicate email → 409 (case-insensitive)
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email.upper(), "password": TEST_PASSWORD},
        )
        assert resp.status_code == 409

        # password too short → 422
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": f"x-{email}", "password": "short"},
        )
        assert resp.status_code == 422

        # login works; wrong password and unknown email both 401 with the
        # same message (no email-existence oracle)
        resp = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == email

        resp = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert resp.status_code == 401
        wrong_pw_detail = resp.json()["detail"]

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": f"nobody-{email}", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == wrong_pw_detail

        # cleanup
        async with SessionFactory() as session:
            user = await session.get(User, uuid.UUID(body["user"]["id"]))
            await session.delete(user)
            await session.commit()


async def test_protected_endpoints_require_valid_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        protected = [
            ("GET", "/api/v1/accounts"),
            ("GET", "/api/v1/transactions"),
            ("GET", "/api/v1/analytics/monthly-spending"),
            ("GET", "/api/v1/insights/spending-summary"),
            ("GET", "/api/v1/auth/me"),
            ("POST", "/api/v1/plaid/link-token"),
            ("POST", "/api/v1/transactions/sync"),
            ("POST", "/api/v1/ai/chat"),
        ]
        for method, path in protected:
            # no token
            resp = await client.request(method, path, json={"message": "x"})
            assert resp.status_code == 401, f"{method} {path}: {resp.status_code}"
            assert resp.headers.get("www-authenticate") == "Bearer"
            # garbage token
            resp = await client.request(
                method, path, json={"message": "x"},
                headers={"Authorization": "Bearer not-a-jwt"},
            )
            assert resp.status_code == 401, f"{method} {path}: {resp.status_code}"

        # health stays public
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200


async def test_cross_user_isolation():
    """User B must never see user A's data, even with valid auth."""
    transport = ASGITransport(app=app)
    user_a_id = user_b_id = None
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a, user_a_id = await register_user(client)
        headers_b, user_b_id = await register_user(client)

        # reads are scoped by the token, not by anything client-supplied
        resp = await client.get("/api/v1/accounts", headers=headers_b)
        assert resp.status_code == 200 and resp.json() == []
        resp = await client.get("/api/v1/transactions", headers=headers_b)
        assert resp.json()["total"] == 0

        # B cannot act on A's items by guessing ids: unknown-for-this-user
        fake_item = str(uuid.uuid4())
        resp = await client.post(
            "/api/v1/transactions/sync",
            json={"item_id": fake_item},
            headers=headers_b,
        )
        assert resp.status_code == 404

    # cleanup
    async with SessionFactory() as session:
        for uid in (user_a_id, user_b_id):
            user = await session.get(User, uuid.UUID(uid))
            await session.delete(user)
        await session.commit()


async def test_pre_auth_account_can_be_claimed():
    """Rows created before auth existed (password_hash NULL) are claimed
    by registering with the same email; their data is preserved."""
    email = f"legacy-{uuid.uuid4().hex[:12]}@example.com"
    async with SessionFactory() as session:
        legacy = User(email=email)  # no password_hash
        session.add(legacy)
        await session.commit()
        await session.refresh(legacy)
        legacy_id = str(legacy.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 201
        assert resp.json()["user"]["id"] == legacy_id  # same row, not a new one

        # a second registration attempt is now a normal conflict
        resp = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": "other-pass-123"}
        )
        assert resp.status_code == 409

    async with SessionFactory() as session:
        user = await session.get(User, uuid.UUID(legacy_id))
        await session.delete(user)
        await session.commit()
