"""Authentication: password hashing, JWT issue/verify, register/login.

Passwords are bcrypt-hashed (never stored or logged in plain text).
Tokens are stateless HS256 JWTs whose subject is the user id; every
protected request decodes the token and loads the user — there is no
server-side session state.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.exceptions import AuthenticationError, ConflictError

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # malformed hash
        return False


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)

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
