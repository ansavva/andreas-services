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


# The one place that knows where `studio/` is. Everything needing `local/`
# derives it from here.
STUDIO_DIR = _studio_dir()

# **Every local value lives in one file, outside the repository:**
# `~/.config/andreas-services/studio/dev.env` — this machine's dev pool
# password, the frontend's `VITE_*` values, and the provider tokens. A secret
# inside the working tree is one `git add -f`, one wholesale copy of the
# directory, one backup tool away from leaving the machine, and `.gitignore`
# stops none of those; an ignored file also vanishes on `git clean` and never
# exists in a fresh worktree. `studio/.env` used to be read after this file
# and is not read at all now — `dev-setup.sh` imports and deletes one it finds.
#
# Nothing here is environment-scoped despite the file's name: a token is the
# same wherever it is used, and `dev.env` is the right file because the only
# reader is the LOCAL pipeline. The deployed half never sees it — studio's
# Lambda calls no model. `STUDIO_DEV_ENV_FILE` overrides the location, the
# same way it does for the shell scripts.
CONFIG_DIR = (
    pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config")
    / "andreas-services"
    / "studio"
)
DEV_ENV_FILE = pathlib.Path(os.environ.get("STUDIO_DEV_ENV_FILE") or CONFIG_DIR / "dev.env")


def _read_env_file(path: pathlib.Path, name: str) -> str | None:
    """First `name=` assignment in a dotenv-style file, or None."""
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def env_value(name: str) -> str | None:
    """Read `name` from the environment, then `dev.env`.

    The environment wins so a caller can override per invocation without
    editing a file.
    """
    value = os.environ.get(name)
    if value:
        return value.strip()
    return _read_env_file(DEV_ENV_FILE, name)
