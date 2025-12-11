class HumbuggException(Exception):
  """Domain-specific exception used across services."""


class UnauthorizedException(HumbuggException):
  """Raised when a user attempts an action they cannot perform."""
