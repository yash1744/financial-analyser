from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "finance-app"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False
    log_level: str = "INFO"

    # API
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://finance:finance@localhost:5432/finance"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Plaid
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: Literal["sandbox", "production"] = "sandbox"
    plaid_products: str = "transactions"  # comma-separated
    plaid_country_codes: str = "US"  # comma-separated
    plaid_webhook_url: str | None = None

    # Fernet key for encrypting Plaid access tokens at rest
    token_encryption_key: str = ""

    # LLM chat (app boots fine without a key; /ai endpoints then return 503)
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"  # used when llm_provider=anthropic
    openai_api_key: str = ""
    openai_model: str = "gpt-5.1"  # used when llm_provider=openai
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 60.0
    llm_max_tool_iterations: int = 8

    @property
    def plaid_products_list(self) -> list[str]:
        return [p.strip() for p in self.plaid_products.split(",") if p.strip()]

    @property
    def plaid_country_codes_list(self) -> list[str]:
        return [c.strip() for c in self.plaid_country_codes.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance so the .env file is read once per process."""
    return Settings()
