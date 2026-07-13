import json
import uuid
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet
from plaid.exceptions import ApiException

from app.core.config import Settings
from app.services.exceptions import (
    PlaidConfigurationError,
    PlaidItemLoginRequiredError,
    PlaidServiceError,
)
from app.services.plaid import PlaidService, build_plaid_client
from app.utils.crypto import TokenCipher


def make_settings(**overrides) -> Settings:
    values = {
        "plaid_client_id": "client-id",
        "plaid_secret": "secret",
        "plaid_env": "sandbox",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def response_with(payload: dict) -> MagicMock:
    response = MagicMock()
    response.to_dict.return_value = payload
    return response


def api_exception(status: int, body: dict) -> ApiException:
    exc = ApiException(status=status, reason="Bad Request")
    exc.body = json.dumps(body)
    return exc


def make_service(client: MagicMock | None = None, **settings_overrides) -> PlaidService:
    return PlaidService(client=client or MagicMock(), settings=make_settings(**settings_overrides))


async def test_create_link_token():
    client = MagicMock()
    client.link_token_create.return_value = response_with(
        {"link_token": "link-sandbox-abc", "expiration": "2026-07-13T12:00:00Z"}
    )
    result = await make_service(client).create_link_token(uuid.uuid4())
    assert result.link_token == "link-sandbox-abc"


async def test_exchange_public_token():
    client = MagicMock()
    client.item_public_token_exchange.return_value = response_with(
        {"access_token": "access-sandbox-xyz", "item_id": "item-1"}
    )
    result = await make_service(client).exchange_public_token("public-sandbox-123")
    assert result.access_token == "access-sandbox-xyz"
    assert result.item_id == "item-1"


async def test_get_accounts():
    client = MagicMock()
    client.accounts_get.return_value = response_with(
        {
            "accounts": [{"account_id": "a1", "name": "Checking"}],
            "item": {"item_id": "item-1", "institution_id": "ins_1"},
        }
    )
    snapshot = await make_service(client).get_accounts("access-token")
    assert snapshot.accounts[0]["account_id"] == "a1"
    assert snapshot.item["institution_id"] == "ins_1"


async def test_sync_transactions_pages_until_has_more_is_false():
    client = MagicMock()
    client.transactions_sync.side_effect = [
        response_with(
            {
                "added": [{"transaction_id": "t1"}],
                "modified": [],
                "removed": [],
                "next_cursor": "cursor-1",
                "has_more": True,
            }
        ),
        response_with(
            {
                "added": [{"transaction_id": "t2"}],
                "modified": [{"transaction_id": "t0"}],
                "removed": [{"transaction_id": "t-gone"}],
                "next_cursor": "cursor-2",
                "has_more": False,
            }
        ),
    ]
    result = await make_service(client).sync_transactions("access-token")
    assert [t["transaction_id"] for t in result.added] == ["t1", "t2"]
    assert result.modified == [{"transaction_id": "t0"}]
    assert result.removed == [{"transaction_id": "t-gone"}]
    assert result.next_cursor == "cursor-2"
    assert client.transactions_sync.call_count == 2


async def test_sync_transactions_restarts_once_on_mutation_during_pagination():
    client = MagicMock()
    client.transactions_sync.side_effect = [
        api_exception(
            400,
            {
                "error_type": "TRANSACTIONS_ERROR",
                "error_code": "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION",
                "error_message": "mutated",
            },
        ),
        response_with(
            {
                "added": [{"transaction_id": "t1"}],
                "modified": [],
                "removed": [],
                "next_cursor": "cursor-1",
                "has_more": False,
            }
        ),
    ]
    result = await make_service(client).sync_transactions("access-token", cursor="orig")
    assert result.next_cursor == "cursor-1"
    assert client.transactions_sync.call_count == 2


async def test_item_login_required_is_raised_as_typed_error():
    client = MagicMock()
    client.accounts_get.side_effect = api_exception(
        400,
        {
            "error_type": "ITEM_ERROR",
            "error_code": "ITEM_LOGIN_REQUIRED",
            "display_message": "Please reconnect your bank",
            "request_id": "req-1",
        },
    )
    with pytest.raises(PlaidItemLoginRequiredError) as excinfo:
        await make_service(client).get_accounts("access-token")
    assert excinfo.value.error_code == "ITEM_LOGIN_REQUIRED"
    assert excinfo.value.request_id == "req-1"
    assert "reconnect" in str(excinfo.value)


async def test_unparseable_error_body_still_raises_service_error():
    client = MagicMock()
    exc = ApiException(status=500, reason="Internal Server Error")
    exc.body = "not-json"
    client.accounts_get.side_effect = exc
    with pytest.raises(PlaidServiceError) as excinfo:
        await make_service(client).get_accounts("access-token")
    assert excinfo.value.status == 500


async def test_sandbox_helper_refuses_outside_sandbox():
    with pytest.raises(PlaidConfigurationError):
        await make_service(plaid_env="production").create_sandbox_public_token()


def test_build_plaid_client_requires_credentials():
    with pytest.raises(PlaidConfigurationError):
        build_plaid_client(make_settings(plaid_client_id="", plaid_secret=""))


def test_token_cipher_round_trip():
    cipher = TokenCipher(Fernet.generate_key().decode())
    token = "access-sandbox-super-secret"
    encrypted = cipher.encrypt(token)
    assert encrypted != token
    assert cipher.decrypt(encrypted) == token


def test_token_cipher_rejects_missing_key():
    with pytest.raises(ValueError):
        TokenCipher("")
