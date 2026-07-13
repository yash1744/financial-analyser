from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.exceptions import ConflictError


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def create_user(self, email: str) -> User:
        normalized = email.strip().lower()
        if await self.users.get_by_email(normalized) is not None:
            raise ConflictError(f"a user with email {normalized!r} already exists")
        user = await self.users.create(normalized)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            # Lost a race with a concurrent insert; same outcome as the pre-check
            await self.session.rollback()
            raise ConflictError(f"a user with email {normalized!r} already exists") from exc
        await self.session.refresh(user)
        return user
