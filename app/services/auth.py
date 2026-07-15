"""Authentication: password hashing, JWT issue/verify, register/login,
email verification, and password reset.

Passwords are bcrypt-hashed (never stored or logged in plain text).
Tokens are stateless HS256 JWTs whose subject is the user id; every
protected request decodes the token and loads the user — there is no
server-side session state.

Verification/reset links carry a random single-use token; only its
SHA-256 hash is stored (see AuthToken). Unverified users can still log
in — this app predates verification, so blocking would lock out every
existing account; verification status is surfaced on the user instead.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.enums import TokenPurpose
from app.models.user import User
from app.repositories.auth_token import AuthTokenRepository
from app.repositories.user import UserRepository
from app.services.email import EmailMessage, EmailSender
from app.services.exceptions import AuthenticationError, ConflictError

logger = logging.getLogger(__name__)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # malformed hash
        return False


class AuthService:
    def __init__(
        self, session: AsyncSession, settings: Settings, email_sender: EmailSender
    ) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.tokens = AuthTokenRepository(session)
        self.email = email_sender

    # --- tokens ---

    def create_token(self, user_id: uuid.UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(hours=self.settings.jwt_expiry_hours),
        }
        return jwt.encode(
            payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm
        )

    async def user_from_token(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_algorithm],
            )
            user_id = uuid.UUID(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
            raise AuthenticationError("invalid or expired token") from exc
        user = await self.users.get(user_id)
        if user is None:  # e.g. account deleted after the token was issued
            raise AuthenticationError("invalid or expired token")
        return user

    # --- flows ---

    async def register(self, email: str, password: str) -> tuple[User, str]:
        normalized = email.strip().lower()
        # An existing email always conflicts — including rows created
        # before auth existed (password_hash NULL): emails are unverified,
        # so letting those be "claimed" would be an account takeover.
        if await self.users.get_by_email(normalized) is not None:
            raise ConflictError(f"a user with email {normalized!r} already exists")

        user = await self.users.create(normalized, password_hash=hash_password(password))
        try:
            await self.session.commit()
        except IntegrityError as exc:
            # Lost a race with a concurrent insert; same outcome as the pre-check
            await self.session.rollback()
            raise ConflictError(f"a user with email {normalized!r} already exists") from exc
        await self.session.refresh(user)
        # Best-effort: a broken mail setup must not block registration —
        # the user can always resend from the verify-email page.
        try:
            await self.request_email_verification(user)
        except Exception:
            logger.exception("verification email to %s failed", user.email)
        return user, self.create_token(user.id)

    async def login(self, email: str, password: str) -> tuple[User, str]:
        user = await self.users.get_by_email(email.strip().lower())
        # Same error for unknown email / no password / wrong password —
        # don't leak which emails exist
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise AuthenticationError("incorrect email or password")
        return user, self.create_token(user.id)

    # --- email verification ---

    async def request_email_verification(self, user: User) -> bool:
        """Email a fresh verification link. Returns False (and sends
        nothing) when the address is already verified."""
        if user.email_verified_at is not None:
            return False
        raw = await self._issue_token(
            user.id,
            TokenPurpose.EMAIL_VERIFICATION,
            timedelta(hours=self.settings.email_verification_ttl_hours),
        )
        await self.session.commit()
        link = f"{self.settings.app_base_url}/verify-email?token={raw}"
        await self.email.send(
            EmailMessage(
                to=user.email,
                subject="Verify your email address",
                body=(
                    "Welcome! Confirm this email address by opening the link "
                    f"below (valid for {self.settings.email_verification_ttl_hours} "
                    f"hours):\n\n{link}\n\nIf you didn't create this account, "
                    "you can ignore this message."
                ),
            )
        )
        return True

    async def verify_email(self, raw_token: str) -> User:
        token = await self.tokens.get_valid(
            _hash_token(raw_token), TokenPurpose.EMAIL_VERIFICATION
        )
        if token is None:
            raise AuthenticationError("invalid or expired verification link")
        user = await self.users.get(token.user_id)
        if user is None:  # account deleted after the email went out
            raise AuthenticationError("invalid or expired verification link")
        now = datetime.now(UTC)
        token.used_at = now
        if user.email_verified_at is None:
            user.email_verified_at = now
        await self.session.commit()
        return user

    # --- password reset ---

    async def request_password_reset(self, email: str) -> None:
        """Email a reset link if the address belongs to an account.
        Always returns silently — the caller's response must not reveal
        whether the email exists (no account-enumeration oracle)."""
        user = await self.users.get_by_email(email.strip().lower())
        if user is None or user.password_hash is None:
            return
        raw = await self._issue_token(
            user.id,
            TokenPurpose.PASSWORD_RESET,
            timedelta(minutes=self.settings.password_reset_ttl_minutes),
        )
        await self.session.commit()
        link = f"{self.settings.app_base_url}/reset-password?token={raw}"
        try:
            await self.email.send(
                EmailMessage(
                    to=user.email,
                    subject="Reset your password",
                    body=(
                        "A password reset was requested for this account. Open "
                        "the link below to choose a new password (valid for "
                        f"{self.settings.password_reset_ttl_minutes} minutes):\n\n"
                        f"{link}\n\nIf you didn't request this, you can ignore "
                        "this message — your password is unchanged."
                    ),
                )
            )
        except Exception:
            # swallowing keeps the response uniform; a send failure that
            # only happens for existing accounts would leak existence
            logger.exception("password reset email to %s failed", user.email)

    async def reset_password(self, raw_token: str, new_password: str) -> User:
        token = await self.tokens.get_valid(
            _hash_token(raw_token), TokenPurpose.PASSWORD_RESET
        )
        if token is None:
            raise AuthenticationError("invalid or expired reset link")
        user = await self.users.get(token.user_id)
        if user is None:
            raise AuthenticationError("invalid or expired reset link")
        now = datetime.now(UTC)
        user.password_hash = hash_password(new_password)
        token.used_at = now
        # a successful reset kills every other outstanding reset link
        await self.tokens.invalidate_active(user.id, TokenPurpose.PASSWORD_RESET)
        # completing the emailed flow proves mailbox ownership
        if user.email_verified_at is None:
            user.email_verified_at = now
        await self.session.commit()
        return user

    # --- internals ---

    async def _issue_token(
        self, user_id: uuid.UUID, purpose: TokenPurpose, ttl: timedelta
    ) -> str:
        """Replace any outstanding token of this purpose with a fresh one;
        returns the raw value (stored only as a hash)."""
        await self.tokens.invalidate_active(user_id, purpose)
        raw = secrets.token_urlsafe(32)
        await self.tokens.create(
            user_id=user_id,
            token_hash=_hash_token(raw),
            purpose=purpose,
            expires_at=datetime.now(UTC) + ttl,
        )
        return raw
