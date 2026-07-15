"""Service-layer exceptions.

Callers (routes, sync jobs) catch these instead of SDK exceptions, so
swapping or upgrading the Plaid SDK never ripples past the service layer.
"""


class NotFoundError(Exception):
    """A referenced entity does not exist. Maps to HTTP 404."""


class ConflictError(Exception):
    """The request contradicts existing state. Maps to HTTP 409."""


class AuthenticationError(Exception):
    """Missing/invalid credentials or token. Maps to HTTP 401."""


class RateLimitedError(Exception):
    """Too many attempts. Maps to HTTP 429 with Retry-After."""

    def __init__(self, message: str, retry_after_seconds: float) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class PlaidConfigurationError(Exception):
    """Plaid credentials are missing or invalid at client-build time."""


class PlaidServiceError(Exception):
    """A Plaid API call failed. Carries Plaid's error taxonomy."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str | None = None,
        error_code: str | None = None,
        request_id: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.error_code = error_code
        self.request_id = request_id
        self.status = status


class PlaidItemLoginRequiredError(PlaidServiceError):
    """The user must re-authenticate via Link update mode.

    Callers should set the PlaidItem's status to LOGIN_REQUIRED.
    """


class PlaidRateLimitError(PlaidServiceError):
    """Plaid rate limit hit; retry with backoff."""
