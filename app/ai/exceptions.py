"""Typed AI-layer errors. Provider SDK exceptions are translated into
these inside the LLM client; the HTTP mapping lives in api/errors.py —
consistent with how services/exceptions.py handles Plaid."""


class AIError(Exception):
    """Base for everything raised by the AI layer."""


class LLMError(AIError):
    """The LLM provider failed (upstream 5xx, malformed response, …)."""


class LLMConfigurationError(AIError):
    """The LLM integration is not configured (missing API key)."""


class LLMAuthError(LLMError):
    """The provider rejected our credentials."""


class LLMRateLimitError(LLMError):
    """Provider rate limit hit; the client may retry later."""


class LLMTimeoutError(LLMError):
    """The provider did not answer within the configured timeout."""


class AgentLoopError(AIError):
    """The tool loop exceeded its iteration budget without a final answer."""
