"""Dependency-injection wiring for API routes.

Routes declare what they need via Annotated types; construction details
(sessions, settings, service composition) live here in one place.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from plaid.api import plaid_api
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.services.account_sync import AccountSyncService
from app.services.analytics import AnalyticsService
from app.services.health import HealthService
from app.services.insights import InsightsService
from app.services.plaid import PlaidService, build_plaid_client
from app.services.plaid_link import PlaidLinkService
from app.services.queries import (
    AccountQueryService,
    CategoryQueryService,
    TransactionQueryService,
)
from app.services.transaction_sync import TransactionSyncService
from app.services.user import UserService
from app.utils.crypto import TokenCipher

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_health_service(session: DbSessionDep, settings: SettingsDep) -> HealthService:
    return HealthService(session=session, settings=settings)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


@lru_cache
def _plaid_client() -> plaid_api.PlaidApi:
    """One client (with its urllib3 pool) per process."""
    return build_plaid_client(get_settings())


def get_plaid_service(settings: SettingsDep) -> PlaidService:
    return PlaidService(client=_plaid_client(), settings=settings)


PlaidServiceDep = Annotated[PlaidService, Depends(get_plaid_service)]


@lru_cache
def get_token_cipher() -> TokenCipher:
    return TokenCipher(get_settings().token_encryption_key)


TokenCipherDep = Annotated[TokenCipher, Depends(get_token_cipher)]


def get_user_service(session: DbSessionDep) -> UserService:
    return UserService(session=session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_plaid_link_service(
    session: DbSessionDep,
    plaid: PlaidServiceDep,
    cipher: TokenCipherDep,
) -> PlaidLinkService:
    return PlaidLinkService(session=session, plaid=plaid, cipher=cipher)


PlaidLinkServiceDep = Annotated[PlaidLinkService, Depends(get_plaid_link_service)]


def get_account_sync_service(
    session: DbSessionDep,
    plaid: PlaidServiceDep,
    cipher: TokenCipherDep,
) -> AccountSyncService:
    return AccountSyncService(session=session, plaid=plaid, cipher=cipher)


AccountSyncServiceDep = Annotated[AccountSyncService, Depends(get_account_sync_service)]


def get_transaction_sync_service(
    session: DbSessionDep,
    plaid: PlaidServiceDep,
    cipher: TokenCipherDep,
) -> TransactionSyncService:
    return TransactionSyncService(session=session, plaid=plaid, cipher=cipher)


TransactionSyncServiceDep = Annotated[
    TransactionSyncService, Depends(get_transaction_sync_service)
]


def get_account_query_service(session: DbSessionDep) -> AccountQueryService:
    return AccountQueryService(session=session)


def get_transaction_query_service(session: DbSessionDep) -> TransactionQueryService:
    return TransactionQueryService(session=session)


def get_category_query_service(session: DbSessionDep) -> CategoryQueryService:
    return CategoryQueryService(session=session)


AccountQueryServiceDep = Annotated[AccountQueryService, Depends(get_account_query_service)]
TransactionQueryServiceDep = Annotated[
    TransactionQueryService, Depends(get_transaction_query_service)
]
CategoryQueryServiceDep = Annotated[CategoryQueryService, Depends(get_category_query_service)]


def get_analytics_service(session: DbSessionDep) -> AnalyticsService:
    return AnalyticsService(session=session)


AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]


def get_insights_service(session: DbSessionDep) -> InsightsService:
    return InsightsService(session=session)


InsightsServiceDep = Annotated[InsightsService, Depends(get_insights_service)]
