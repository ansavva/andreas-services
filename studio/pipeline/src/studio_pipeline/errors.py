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


def die(msg: str) -> None:
    """Report and exit 1 — the imperative twin of `reports`.

    `reports` is for a module that raises; this is for one that discovers the
    problem mid-function and has nothing useful to raise. Both print the same
    `error: <message>` line, which is what a caller greps for.

    It lives here rather than in `adapters/s3.py`, where the copy the pipeline
    grew up on sat. That put a printing helper behind an AWS import, so
    `adapters/ffmpeg.py` imported an S3 module for it — and retiring that module
    would have taken the whole CLI's error path with it.

    **There were nine copies of this function.** They are gone; this is the only
    one. Two of the nine were in adapters, which is what made the count wrong
    when it was first written down as seven — `adapters/replicate.py` had one
    that `engine/` reached through `die = RA.die`, so three engine modules were
    getting their error path out of an HTTP client. All nine bodies were
    identical apart from `sys.exit(1)` versus `raise SystemExit(1)`, which are
    the same thing.
    """
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


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
