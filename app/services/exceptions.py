"""Service-layer exceptions.

Callers (routes, sync jobs) catch these instead of SDK exceptions, so
swapping or upgrading the Plaid SDK never ripples past the service layer.
"""


class NotFoundError(Exception):
    """A referenced entity does not exist. Maps to HTTP 404."""


class ConflictError(Exception):
    """The request contradicts existing state. Maps to HTTP 409."""


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
