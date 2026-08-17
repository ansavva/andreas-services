"""The studio generation pipeline.

The local half of studio: everything that produces media, as one installable
package rather than a scatter of standalone scripts. The `SKILL.md` files under
`studio/.claude/skills/` are the agent-facing documentation for it; this is the
code they drive, through the `studio` command in `cli.py`.
"""

import os
import pathlib

# The one place that knows where `studio/` is.
#
# This used to be computed independently in each script that needed it, as a
# count of `".."` segments from its own location — which meant the correct
# number differed by directory depth and was silently wrong the moment a file
# moved. Deriving it once, from the package's own position, is why moving a
# module inside this package is now free.
STUDIO_DIR = pathlib.Path(__file__).resolve().parents[2]

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
