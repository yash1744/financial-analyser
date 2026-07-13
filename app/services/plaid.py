"""Plaid gateway service.

This service is the only place that talks to the Plaid API. It does NOT
touch the database — persisting items/accounts/transactions is the job
of the (future) sync service, which composes this with repositories.

The Plaid SDK is synchronous (urllib3), so every call is pushed onto a
worker thread with asyncio.to_thread to keep the event loop unblocked.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

import plaid
from plaid.api import plaid_api
from plaid.exceptions import ApiException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from app.core.config import Settings
from app.schemas.plaid import (
    AccountsSnapshot,
    ExchangedPublicToken,
    LinkTokenResult,
    TransactionsSyncResult,
)
from app.services.exceptions import (
    PlaidConfigurationError,
    PlaidItemLoginRequiredError,
    PlaidRateLimitError,
    PlaidServiceError,
)

logger = logging.getLogger(__name__)

_PLAID_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}

_SYNC_PAGE_SIZE = 500
_MUTATION_ERROR = "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"


def build_plaid_client(settings: Settings) -> plaid_api.PlaidApi:
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise PlaidConfigurationError(
            "PLAID_CLIENT_ID and PLAID_SECRET must be set (see .env.example)"
        )
    configuration = plaid.Configuration(
        host=_PLAID_HOSTS[settings.plaid_env],
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def _translate(exc: ApiException) -> PlaidServiceError:
    """Map an SDK exception onto our service exception hierarchy."""
    error_type = error_code = request_id = None
    message = str(exc.reason or "Plaid API error")
    try:
        body = json.loads(exc.body) if exc.body else {}
    except (TypeError, ValueError):
        body = {}
    if body:
        error_type = body.get("error_type")
        error_code = body.get("error_code")
        request_id = body.get("request_id")
        message = body.get("display_message") or body.get("error_message") or message

    kwargs: dict[str, Any] = {
        "error_type": error_type,
        "error_code": error_code,
        "request_id": request_id,
        "status": exc.status,
    }
    if error_code == "ITEM_LOGIN_REQUIRED":
        return PlaidItemLoginRequiredError(message, **kwargs)
    if error_type == "RATE_LIMIT_EXCEEDED":
        return PlaidRateLimitError(message, **kwargs)
    return PlaidServiceError(message, **kwargs)


class PlaidService:
    def __init__(self, client: plaid_api.PlaidApi, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def _call(self, fn: Callable[[Any], Any], request: Any) -> dict[str, Any]:
        """Run one SDK call off-loop and translate its failures."""
        try:
            response = await asyncio.to_thread(fn, request)
        except ApiException as exc:
            error = _translate(exc)
            logger.warning(
                "Plaid call %s failed: %s (error_code=%s, request_id=%s)",
                getattr(fn, "__name__", fn),
                error,
                error.error_code,
                error.request_id,
            )
            raise error from exc
        return response.to_dict()

    async def create_link_token(self, user_id: uuid.UUID) -> LinkTokenResult:
        """Start the Link flow: a short-lived token the frontend hands to Plaid Link."""
        request_kwargs: dict[str, Any] = {}
        if self._settings.plaid_webhook_url:
            request_kwargs["webhook"] = self._settings.plaid_webhook_url
        request = LinkTokenCreateRequest(
            client_name=self._settings.app_name,
            language="en",
            country_codes=[CountryCode(c) for c in self._settings.plaid_country_codes_list],
            products=[Products(p) for p in self._settings.plaid_products_list],
            user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
            **request_kwargs,
        )
        data = await self._call(self._client.link_token_create, request)
        return LinkTokenResult(link_token=data["link_token"], expiration=data["expiration"])

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        """Trade Link's one-time public_token for the permanent access_token.

        The access_token must be encrypted (TokenCipher) before it is
        persisted to plaid_items.access_token_encrypted.
        """
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        data = await self._call(self._client.item_public_token_exchange, request)
        return ExchangedPublicToken(access_token=data["access_token"], item_id=data["item_id"])

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        """Fetch all accounts under an item, with current balances."""
        request = AccountsGetRequest(access_token=access_token)
        data = await self._call(self._client.accounts_get, request)
        return AccountsSnapshot(accounts=data["accounts"], item=data["item"])

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        """Pull all transaction changes since `cursor` (None = full history).

        Pages through /transactions/sync until has_more is false. If Plaid
        reports a mutation mid-pagination, restarts once from the original
        cursor as its docs require (partial pages must be discarded).
        """
        for attempt in (1, 2):
            try:
                return await self._sync_from(access_token, cursor)
            except PlaidServiceError as error:
                if error.error_code == _MUTATION_ERROR and attempt == 1:
                    logger.info("Sync mutated during pagination; restarting from cursor")
                    continue
                raise
        raise AssertionError("unreachable")

    async def _sync_from(
        self, access_token: str, cursor: str | None
    ) -> TransactionsSyncResult:
        added: list[dict[str, Any]] = []
        modified: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        next_cursor = cursor or ""
        while True:
            kwargs: dict[str, Any] = {"count": _SYNC_PAGE_SIZE}
            if next_cursor:
                kwargs["cursor"] = next_cursor
            request = TransactionsSyncRequest(access_token=access_token, **kwargs)
            data = await self._call(self._client.transactions_sync, request)
            added.extend(data["added"])
            modified.extend(data["modified"])
            removed.extend(data["removed"])
            next_cursor = data["next_cursor"]
            if not data["has_more"]:
                return TransactionsSyncResult(
                    added=added, modified=modified, removed=removed, next_cursor=next_cursor
                )

    async def create_sandbox_public_token(
        self, institution_id: str = "ins_109508"  # "First Platypus Bank" test institution
    ) -> str:
        """Sandbox-only shortcut past the Link UI, for testing the full flow."""
        if self._settings.plaid_env != "sandbox":
            raise PlaidConfigurationError("sandbox_public_token is only available in sandbox")
        request = SandboxPublicTokenCreateRequest(
            institution_id=institution_id,
            initial_products=[Products(p) for p in self._settings.plaid_products_list],
        )
        data = await self._call(self._client.sandbox_public_token_create, request)
        return data["public_token"]
