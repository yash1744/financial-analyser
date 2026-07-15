import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models.auth_token import AuthToken
from app.models.enums import TokenPurpose
from app.repositories.base import BaseRepository


class AuthTokenRepository(BaseRepository):
    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        purpose: TokenPurpose,
        expires_at: datetime,
    ) -> AuthToken:
        token = AuthToken(
            user_id=user_id,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_valid(self, token_hash: str, purpose: TokenPurpose) -> AuthToken | None:
        """The token matching this hash, if it is unused and unexpired."""
        result = await self.session.execute(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def invalidate_active(self, user_id: uuid.UUID, purpose: TokenPurpose) -> None:
        """Mark every outstanding token of this purpose used, so at most
        one emailed link is ever live per user."""
        await self.session.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )
