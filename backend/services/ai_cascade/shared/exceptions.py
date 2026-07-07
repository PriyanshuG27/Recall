class CascadeError(Exception):
    """Base exception for all AI Cascade errors."""
    pass


class CascadeTimeoutError(CascadeError):
    """Raised when a provider request times out."""
    pass


class SecurityViolationError(CascadeError):
    """Raised when a prompt violates safety or prompt injection filters."""
    pass


class OutputValidationError(CascadeError):
    """Raised when the AI output fails validation heuristics or schemas."""
    pass


class ProviderError(CascadeError):
    """Raised when an AI provider returns an error (e.g. 500)."""
    pass


class RateLimitExceededError(ProviderError):
    """Raised when an AI provider returns a 429 Rate Limit error."""
    pass


class CircuitBreakerOpenError(CascadeError):
    """Raised when a request is blocked because the provider's circuit is open."""
    pass


class ModelDeprecationError(CascadeError):
    """Raised when attempting to execute a deprecated/removed model."""
    pass
