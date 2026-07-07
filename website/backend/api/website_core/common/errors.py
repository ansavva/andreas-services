"""Domain error types mapped to HTTP responses by the handler."""


class ValidationError(ValueError):
    """Bad user input — maps to HTTP 400."""


class ConfigError(RuntimeError):
    """A required integration is not configured — maps to HTTP 500."""


class UpstreamError(RuntimeError):
    """A call to an external service failed — maps to HTTP 502."""
