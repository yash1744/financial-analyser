import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)


class HealthService:
    """Reports liveness of the app and its dependencies."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def check(self) -> HealthResponse:
        db_status: str = "up"
        try:
            await self.session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Database health check failed")
            db_status = "down"

        return HealthResponse(
            status="ok" if db_status == "up" else "degraded",
            app=self.settings.app_name,
            environment=self.settings.environment,
            database=db_status,
        )
