"""Call another module's CLI in-process and read its JSON answer.

Three call sites used to shell out with `uv run <script>.py … --json` and parse
stdout. That was not a style choice: every script had its own environment, so a
direct import was impossible and a subprocess was the only way one part of the
pipeline could ask another a question.

One package removes the reason, and this removes the subprocess — but keeps the
JSON-over-stdout contract exactly as it was. The callers were written against
that contract, and changing the transport and the contract in one step would
make any failure ambiguous about which half broke.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys


class InvokeError(Exception):
    """A sub-CLI failed, or did not answer in JSON."""


def call_json(main, args: list[str], *, prog: str = "studio"):
    """Run `main()` with `args`, capturing stdout, and parse it as JSON.

    `main` is any of this package's zero-argument entry points: they all read
    `sys.argv` through argparse, so the argv swap is what passes arguments.
    """
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = [prog, *args]
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main() or 0
    except SystemExit as exc:  # argparse errors, and `die()` helpers
        code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = saved
    if code != 0:
        detail = (err.getvalue() or "").strip()
        raise InvokeError(detail or f"exited {code}")
    body = out.getvalue() or "[]"
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise InvokeError(f"did not answer in JSON:\n{body}")
