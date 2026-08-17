"""Domain error types mapped to HTTP responses by the app factory."""


class ValidationError(ValueError):
    """Bad user input — maps to HTTP 400."""


class NotFoundError(LookupError):
    """The requested key does not exist — maps to HTTP 404."""


class ConflictError(ValueError):
    """The write would overwrite something that already exists — maps to 409.

    Every write in this service is a rename, a create or a delete, and none of
    them may clobber an object silently: S3 has no "don't overwrite" flag, so
    the check is ours to make and the refusal is ours to report.
    """


class ConfigError(RuntimeError):
    """A required integration is not configured — maps to HTTP 500."""


class UpstreamError(RuntimeError):
    """A call to AWS failed — maps to HTTP 502."""
