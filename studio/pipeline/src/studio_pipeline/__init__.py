"""The studio generation pipeline.

The local half of studio: everything that produces media, as one installable
package rather than a scatter of standalone scripts. The `SKILL.md` files under
`studio/.claude/skills/` are the agent-facing documentation for it; this is the
code they drive, through the `studio` command in `cli.py`.
"""

import os
import pathlib


def _studio_dir() -> pathlib.Path:
    """Find `studio/` by looking for it, not by counting `".."` segments.

    Every script used to compute this independently as a fixed number of
    parents, which was correct only for that file's depth and silently wrong
    the moment one moved. A count is still wrong when the PACKAGE moves — it
    just moves the breakage up a level, as adopting a `src/` layout proved.

    So this searches upward for the directory that holds both halves of the
    service, and says so loudly if it cannot find one.
    """
    for candidate in pathlib.Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "pipeline").is_dir():
            return candidate
    raise RuntimeError(
        "cannot locate the studio/ directory above "
        f"{__file__} — expected an ancestor holding both backend/ and pipeline/"
    )


# The one place that knows where `studio/` is. Everything needing `.env` or
# `local/` derives it from here.
STUDIO_DIR = _studio_dir()

# Local secrets (REPLICATE_API_TOKEN). Git-ignored; see .env.example.
ENV_FILE = STUDIO_DIR / ".env"


def env_value(name: str) -> str | None:
    """Read `name` from the environment, falling back to `studio/.env`.

    The environment wins so a caller can override per invocation without
    editing the file.
    """
    value = os.environ.get(name)
    if value:
        return value.strip()
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None
