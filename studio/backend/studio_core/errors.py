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


class AuthError(Exception):
    """The caller did not prove who they are — maps to HTTP 401.

    The one error here not built on a stdlib exception, because none of them
    means "unauthenticated": `PermissionError` is an `OSError` about a file, and
    hanging this off `ValueError` would file a rejected credential alongside a
    malformed folder name. Which status comes back is the whole point — 401
    tells the SPA to sign in again, 400 tells it to fix the request.

    Its message is user-facing and stays coarse. Which of the checks failed is
    of use to an attacker and of none to a caller, whose remedy is the same
    either way, so nothing raised here names the claim — and nothing, ever,
    echoes the token.
    """


class ConfigError(RuntimeError):
    """A required integration is not configured — maps to HTTP 500."""


class UpstreamError(RuntimeError):
    """A call to AWS failed — maps to HTTP 502."""
