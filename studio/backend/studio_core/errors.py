"""Domain error types mapped to HTTP responses by the app factory."""


class ValidationError(ValueError):
    """Bad user input — maps to HTTP 400."""


class NotFoundError(LookupError):
    """The requested key does not exist — maps to HTTP 404."""


class ConfigError(RuntimeError):
    """A required integration is not configured — maps to HTTP 500."""


class UpstreamError(RuntimeError):
    """A call to AWS failed — maps to HTTP 502."""
