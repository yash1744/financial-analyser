from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Common ground for repositories: holds the session, nothing more.

    Concrete repositories (e.g. TransactionRepository) will add typed
    query methods when models exist. Keep SQL/ORM access in this layer
    only — services should never touch the session directly.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
