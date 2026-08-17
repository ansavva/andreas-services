"""Load and query the model registry (`models.json`).

The registry is the single source of truth for every studio-* tool: the image
submitter, the video submitter, the prompt builder, the format converter and the
backfill importer all read model facts from here instead of keeping their own
partial copy. Adding a model is a data change, not a code change in five files.

    from studio_pipeline.engine import registry as REG
    entry = REG.get("gpt-image-2")     # by key or alias
    entry = REG.by_model_id("openai/gpt-image-2")
    for key, entry in REG.images():    # or .videos(), or .all()
        ...

Every entry is returned as a plain dict with the shape documented in
`models.json`. `REG.field(entry, "images.refs")` reads a dotted path with a
default, so callers do not litter `.get(...)` chains.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "models.json")


class RegistryError(Exception):
    """The registry is missing, malformed, or was asked for an unknown model."""


def _load() -> dict:
    try:
        with open(PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise RegistryError(f"registry not found at {PATH}")
    except json.JSONDecodeError as e:
        raise RegistryError(f"{PATH} is not valid JSON: {e}")
    models = data.get("models")
    if not isinstance(models, dict) or not models:
        raise RegistryError(f"{PATH} has no `models` object")
    return models


def all() -> dict[str, dict]:
    """Every entry, keyed by registry name, in file order."""
    return _load()


def keys() -> list[str]:
    """Registry names only — what `--model` accepts. Sorted for stable help text."""
    return sorted(_load())


def _alias_map() -> dict[str, str]:
    out = {}
    for key, entry in _load().items():
        out[key] = key
        for alias in entry.get("aliases") or []:
            out[alias] = key
    return out


def resolve(name: str) -> str:
    """Registry key for `name`, following aliases. Raises on an unknown model."""
    aliases = _alias_map()
    if name not in aliases:
        raise RegistryError(
            f"unknown model {name!r}\n"
            f"       registered: {', '.join(sorted(_load()))}\n"
            f"       add one with: studio add_model <owner>/<name>"
        )
    return aliases[name]


def get(name: str) -> dict:
    """One entry by registry key or alias, with its key attached as `key`."""
    key = resolve(name)
    entry = dict(_load()[key])
    entry["key"] = key
    return entry


def by_model_id(model_id: str) -> dict | None:
    """One entry by Replicate id (`owner/name`), or None. Used by the backfill."""
    for key, entry in _load().items():
        if entry.get("model") == model_id:
            out = dict(entry)
            out["key"] = key
            return out
    return None


def of_kind(kind: str) -> dict[str, dict]:
    return {k: v for k, v in _load().items() if v.get("kind") == kind}


def images() -> dict[str, dict]:
    return of_kind("image")


def videos() -> dict[str, dict]:
    return of_kind("video")


def field(entry: dict, path: str, default=None):
    """Read a dotted path out of an entry: field(e, "images.max_refs")."""
    cur = entry
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return default if cur is None else cur


def accepts_ext(entry: dict) -> set[str]:
    """The image extensions this model will take, as a set."""
    return set(field(entry, "images.accepts_ext", []) or [])


def save_snapshot(key: str, snapshot: dict) -> None:
    """Write a refreshed schema snapshot for one model, preserving file order.

    Only `snapshot` is ever rewritten — the structural fields are hand-curated
    and must survive a refresh untouched.
    """
    with open(PATH) as f:
        data = json.load(f)
    if key not in data.get("models", {}):
        raise RegistryError(f"cannot snapshot unknown model {key!r}")
    data["models"][key]["snapshot"] = snapshot
    with open(PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
