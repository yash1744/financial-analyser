"""Email verification and password reset flows: token issue/redeem,
single-use + expiry enforcement, and the no-account-enumeration contract."""

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.api.deps import get_email_sender
from app.db.session import SessionFactory
from app.main import app
from app.models.auth_token import AuthToken
from app.services.email import EmailMessage
from tests.conftest import TEST_PASSWORD


class CaptureEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)


def _token_from(message: EmailMessage, path: str) -> str:
    match = re.search(rf"{path}\?token=([A-Za-z0-9_-]+)", message.body)
    assert match, f"no {path} link in email body:\n{message.body}"
    return match.group(1)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient) -> tuple[dict[str, str], str]:
    email = f"verify-{uuid.uuid4().hex[:12]}@example.com"
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}, email


async def test_register_sends_verification_and_confirm_verifies():
    sender = CaptureEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        async with _client() as client:
            headers, email = await _register(client)

            # registration produced exactly one verification email
            assert [m.to for m in sender.messages] == [email]
            token = _token_from(sender.messages[0], "/verify-email")

            resp = await client.get("/api/v1/auth/me", headers=headers)
            assert resp.json()["email_verified"] is False

            resp = await client.post(
                "/api/v1/auth/verify-email/confirm", json={"token": token}
            )
            assert resp.status_code == 200, resp.text

            resp = await client.get("/api/v1/auth/me", headers=headers)
            assert resp.json()["email_verified"] is True

            # single-use: redeeming again fails
            resp = await client.post(
                "/api/v1/auth/verify-email/confirm", json={"token": token}
            )
            assert resp.status_code == 401

            # garbage token fails the same way
            resp = await client.post(
                "/api/v1/auth/verify-email/confirm", json={"token": "not-a-token"}
            )
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


async def test_resend_invalidates_previous_link():
    sender = CaptureEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        async with _client() as client:
            headers, _ = await _register(client)
            first = _token_from(sender.messages[0], "/verify-email")

            resp = await client.post(
                "/api/v1/auth/verify-email/request", headers=headers
            )
            assert resp.status_code == 202
            assert len(sender.messages) == 2
            second = _token_from(sender.messages[1], "/verify-email")

            # the older link died when the new one was issued
            resp = await client.post(
                "/api/v1/auth/verify-email/confirm", json={"token": first}
            )
            assert resp.status_code == 401
            resp = await client.post(
                "/api/v1/auth/verify-email/confirm", json={"token": second}
            )
            assert resp.status_code == 200

            # already verified: no further email goes out
            resp = await client.post(
                "/api/v1/auth/verify-email/request", headers=headers
            )
            assert resp.status_code == 202
            assert len(sender.messages) == 2
            assert "already verified" in resp.json()["detail"]

            # resending requires authentication
            resp = await client.post("/api/v1/auth/verify-email/request")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


async def test_forgot_password_resets_and_tokens_are_single_use():
    sender = CaptureEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        async with _client() as client:
            _, email = await _register(client)
            sender.messages.clear()

            resp = await client.post(
                "/api/v1/auth/forgot-password", json={"email": email}
            )
            assert resp.status_code == 202
            token = _token_from(sender.messages[0], "/reset-password")

            new_password = "brand-new-password-1"
            resp = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "password": new_password},
            )
            assert resp.status_code == 200, resp.text

            # old password is dead, new one works
            resp = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
            )
            assert resp.status_code == 401
            resp = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": new_password}
            )
            assert resp.status_code == 200
            # completing the emailed flow also proved mailbox ownership
            assert resp.json()["user"]["email_verified"] is True

            # the reset token can't be replayed
            resp = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "password": "yet-another-pass-2"},
            )
            assert resp.status_code == 401

            # weak replacement passwords are rejected up front
            resp = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "password": "short"},
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_forgot_password_does_not_reveal_account_existence():
    sender = CaptureEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        async with _client() as client:
            _, email = await _register(client)
            sender.messages.clear()

            unknown = f"nobody-{uuid.uuid4().hex[:12]}@example.com"
            known_resp = await client.post(
                "/api/v1/auth/forgot-password", json={"email": email}
            )
            unknown_resp = await client.post(
                "/api/v1/auth/forgot-password", json={"email": unknown}
            )
            # identical status and body either way; email only for the account
            assert known_resp.status_code == unknown_resp.status_code == 202
            assert known_resp.json() == unknown_resp.json()
            assert [m.to for m in sender.messages] == [email]
    finally:
        app.dependency_overrides.clear()


async def test_expired_reset_token_is_rejected():
    sender = CaptureEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        async with _client() as client:
            _, email = await _register(client)
            sender.messages.clear()

            resp = await client.post(
                "/api/v1/auth/forgot-password", json={"email": email}
            )
            assert resp.status_code == 202
            token = _token_from(sender.messages[0], "/reset-password")

            token_hash = hashlib.sha256(token.encode()).hexdigest()
            async with SessionFactory() as session:
                await session.execute(
                    update(AuthToken)
                    .where(AuthToken.token_hash == token_hash)
                    .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
                )
                await session.commit()

            resp = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "password": "whatever-new-pass"},
            )
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
