"""Turning a domain failure into a clean command-line failure.

The domain raises exceptions; the command line wants a one-line message on
stderr and a non-zero exit. Each module used to do that with a `try/except`
wrapped around its whole `if/elif` dispatch, which is why the dispatch had to
be one function. With one function per command, the handling belongs in a
decorator instead — otherwise it is copied into every command, and the copy
that gets forgotten shows the user a traceback.
"""

from __future__ import annotations

import functools
import sys


def reports(*exception_types: type[BaseException]):
    """Report the named exceptions as `error: <message>` and exit 1.

    Deliberately not `click.ClickException`, which would print `Error:` with a
    capital E. Every one of these tools has printed lowercase `error:` since it
    was a standalone script, and the message shape is something people grep.
    """

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except exception_types as exc:
                print(f"error: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc

        return wrapper

    return decorate
