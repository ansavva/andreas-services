"""lora-lab — the character-LoRA experiment.

Everything in this package is experiment-grade and gitignored. It exists to
answer one question: does a per-character LoRA beat studio's reference-image
approach on identity? The shape deliberately mirrors studio_pipeline
(`cli -> domain -> adapters`, `env_value`, urllib adapters) so whatever
survives the experiment can be lifted into the pipeline rather than rewritten.

Hard rules of studio/CLAUDE.md apply: no character name may be written into
any file that could be committed — this whole tree is gitignored, and every
command takes the slug at runtime anyway.
"""

import os
import pathlib


def _lab_dir() -> pathlib.Path:
    """The directory holding this project's pyproject.toml."""
    for candidate in pathlib.Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError(f"cannot locate the lab root above {__file__}")


def _studio_dir() -> pathlib.Path:
    """Find `studio/` the way studio_pipeline does: by looking for it."""
    for candidate in pathlib.Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "pipeline").is_dir():
            return candidate
    raise RuntimeError(
        f"cannot locate the studio/ directory above {__file__} — expected an "
        "ancestor holding both backend/ and pipeline/"
    )


LAB_DIR = _lab_dir()
STUDIO_DIR = _studio_dir()

# Working state and per-character material. Everything under here stays on
# this machine; datasets and grids are the only record of on-pod work.
LOCAL_DIR = LAB_DIR / "local"
ASSETS_DIR = LAB_DIR / "assets"

# Same credential precedence as studio_pipeline.env_value: the environment,
# then ~/.config/andreas-services/studio/dev.env, then studio/.env. The lab
# adds RUNPOD_API_KEY and HF_TOKEN to the set of names read this way.
CONFIG_DIR = (
    pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config")
    / "andreas-services"
    / "studio"
)
DEV_ENV_FILE = CONFIG_DIR / "dev.env"
ENV_FILE = STUDIO_DIR / ".env"


def _read_env_file(path: pathlib.Path, name: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def env_value(name: str) -> str | None:
    """`name` from the environment, then the config dir, then `studio/.env`."""
    if name in os.environ:
        return os.environ[name]
    return _read_env_file(DEV_ENV_FILE, name) or _read_env_file(ENV_FILE, name)


def studio_bin() -> str:
    """The `studio` console script, PATH or not.

    dev-setup.sh puts the pipeline venv on PATH only inside Claude sessions;
    from a plain terminal the venv's script is the reliable address.
    """
    import shutil

    found = shutil.which("studio")
    if found:
        return found
    candidate = STUDIO_DIR / "pipeline" / ".venv" / "bin" / "studio"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError(
        f"no studio CLI on PATH and none at {candidate} — run studio/scripts/dev-setup.sh once"
    )
