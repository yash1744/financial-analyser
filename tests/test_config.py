"""Boot-time secret enforcement: outside local dev, the app must refuse
to construct settings with missing or default secrets."""

import pytest

from app.core.config import DEV_JWT_SECRET, Settings

REAL_SECRET = "x" * 48
FERNET_KEY = "A" * 42 + "="  # shape only; validity is TokenCipher's concern


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_local_dev_needs_no_secrets():
    settings = make()
    assert settings.jwt_secret_key == DEV_JWT_SECRET


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_non_local_refuses_default_jwt_secret(environment):
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        make(environment=environment, token_encryption_key=FERNET_KEY)


def test_non_local_refuses_short_jwt_secret():
    with pytest.raises(ValueError, match="at least 32"):
        make(
            environment="production",
            jwt_secret_key="short",
            token_encryption_key=FERNET_KEY,
        )


def test_non_local_refuses_missing_encryption_key():
    with pytest.raises(ValueError, match="TOKEN_ENCRYPTION_KEY"):
        make(environment="production", jwt_secret_key=REAL_SECRET)


def test_non_local_with_real_secrets_boots():
    settings = make(
        environment="production",
        jwt_secret_key=REAL_SECRET,
        token_encryption_key=FERNET_KEY,
    )
    assert settings.environment == "production"
