"""Re-capture NAMED commands in `cli_surface_reference.json`, and nothing else.

`cli_surface_reference.json` is a contract, not a snapshot to overwrite. Its
provenance is the point: it was captured off the real argparse parsers *before*
the Click conversion, so it is independent evidence that 255 parameters survived
a hand port. A wholesale re-capture from the Click tree throws that away and
leaves a file that can only ever agree with itself.

So this rewrites **one top-level command at a time**, on purpose:

    uv run python -m tests.contracts.update_cli_reference character curate projects
    uv run python -m tests.contracts.update_cli_reference --remove rewrite

Everything not named is left byte-for-byte identical, because the file is
re-serialised with exactly the settings it was written with
(`indent=2, sort_keys=True, ensure_ascii=False`, trailing newline) and the
untouched subtrees round-trip unchanged. The diff is then reviewable, which is
the only property that makes updating a contract safe.

It is a helper, not a test, and it is never run by the suite.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from studio_pipeline import cli
from tests.contracts import cli_surface

REFERENCE = pathlib.Path(__file__).parent / "cli_surface_reference.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commands", nargs="*",
                        help="top-level `studio` commands to re-capture")
    parser.add_argument("--remove", action="append", default=[],
                        help="a top-level command that no longer exists")
    args = parser.parse_args(argv)

    reference = json.loads(REFERENCE.read_text())

    for name in args.remove:
        if reference.pop(name, None) is None:
            print(f"note: {name!r} was not in the reference", file=sys.stderr)
        else:
            print(f"removed  studio {name}")

    for name in args.commands:
        command = cli.main.get_command(None, name)
        if command is None:
            print(f"error: `studio {name}` does not exist", file=sys.stderr)
            return 1
        verb = "updated" if name in reference else "added"
        reference[name] = cli_surface.from_click(command)
        print(f"{verb}  studio {name}")

    REFERENCE.write_text(
        json.dumps(reference, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
