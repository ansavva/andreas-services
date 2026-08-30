"""Read the model registry — from the API, not from a file this package ships.

The registry is the single source of truth for every studio-* tool: which image
fields a model has, how many references it takes, what it will accept, what its
prompt ceiling is. Adding a model is a data change rather than a code change in
five files.

    from studio_pipeline.engine import registry as REG
    entry = REG.get("gpt-image-2")     # by key, alias, or Replicate id
    for key, entry in REG.images().items():
        ...

## `models.json` moved to the backend, and why

It lived in this package and the API kept a hand-written partial copy —
`ENGINE_CAPS`, three of nine model families — which `GET /api/characters/<id>/selection`
measured an over-cap reference selection against. So the CLI refused a selection
correctly off the real registry while the API let the same selection through for
`gpt-image-2`, the documented default for character frames. Two answers to what a
model accepts, and only one of them auditable.

One of the two had to go, and it could not be the API's: the SPA also builds
selections, and it has no access to a file inside a Python package. So the
registry is `backend/studio_core/models.json`, served at `GET /api/models`, and
this module reads it from there.

## What that costs, stated rather than discovered

* **A new model needs a deploy before production knows it.** `add-model` writes
  the file in the repo; the API serves what shipped. Against a local dev API the
  change is live immediately, because `dev-up.sh` runs the backend from source.
* **Reading the registry needs a session.** It did not before. Every command
  that reaches a model was already signing in, so the only real casualties would
  have been `--help` and the argument parser — and neither touches this: the
  `--model` option is a free string with its own error message, deliberately not
  a `click.Choice`, so nothing here is evaluated at parse time.

## One fetch per process

`_load` memoises. A single `studio run` asks the registry a dozen times —
`accepts_ext`, three `field` reads, a cap, a kind — and a round trip each would
be absurd for a document that cannot change under a running command. The memo is
per process, so a long-lived shell still sees a new model on the next invocation.
`_load.cache_clear()` exists for the tests.
"""

from __future__ import annotations

import functools

from studio_pipeline.adapters import api, entities


class RegistryError(Exception):
    """The registry is unreachable, malformed, or was asked for an unknown model."""


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    """Every entry, keyed by registry name. One HTTP call per process."""
    try:
        models = entities.models()
    except api.ApiError as exc:
        raise RegistryError(
            f"could not read the model registry from the API: {exc}\n"
            "       `studio whoami` says which environment you are in; "
            "`studio login` if you are not signed in."
        ) from exc

    if not isinstance(models, dict) or not models:
        raise RegistryError("the API returned no models")
    return models


def all() -> dict[str, dict]:
    """Every entry, keyed by registry name, each carrying its own `key`."""
    return dict(_load())


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
            f"       add one with: studio add-model <owner>/<name>"
        )
    return aliases[name]


def get(name: str) -> dict:
    """One entry by registry key or alias, with its key attached as `key`."""
    key = resolve(name)
    return {**_load()[key], "key": key}


def by_model_id(model_id: str) -> dict | None:
    """One entry by Replicate id (`owner/name`), or None."""
    for key, entry in _load().items():
        if entry.get("model") == model_id:
            return {**entry, "key": key}
    return None


def of_kind(kind: str) -> dict[str, dict]:
    return {k: v for k, v in _load().items() if v.get("kind") == kind}


def images() -> dict[str, dict]:
    return of_kind("image")


def videos() -> dict[str, dict]:
    return of_kind("video")


def field(entry: dict, path: str, default=None):
    """Read a dotted path out of an entry: field(e, "images.max_refs").

    A stored `null` reads as the default — `max_refs: null` means "no cap", and
    a caller wants to be told that once rather than distinguish absent from null
    at every site.
    """
    cur = entry
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return default if cur is None else cur


def defaults(entry: dict) -> dict:
    """The inputs studio sets when a caller does not. **Studio's decision, not the
    provider's.**

    Not to be confused with `snapshot.<field>.default`, which sits right beside it
    and is the opposite kind of thing: that records what the PROVIDER does when a
    field is absent, it is rewritten wholesale by `studio models refresh`, and a
    studio decision parked there would be silently reverted by the next refresh.
    This block is authored, reviewed in a diff, and never touched by a refresh.

    **Applied under the caller, never over it** — see `runner.build_payload`. A
    default is what happens when nobody chose; anything explicitly set, by
    `--extra`, by `--input-file`, by a flag, or by `character turnaround`'s
    per-model block, wins.

    It exists because `quality` was costing real money by accident. A `gpt-image-2`
    image at `high` is ~$0.198 and at `medium` about a third of that, the
    difference being output tokens, and an ad-hoc `studio run` that named no
    quality got whatever the caller typed or the provider's `auto`. A tier is a
    decision; it belongs somewhere it is made once and can be read.

    Per-model rather than global, because the fields are not shared: `quality` and
    `moderation` exist on the two OpenAI models and nowhere else, and
    `nano-banana-pro` spells the same idea `safety_filter_level`. A value set on a
    model that has no such field is an unknown input the live schema check refuses
    — correctly, and after a draft has been written.
    """
    return dict(entry.get("defaults") or {})


def accepts_ext(entry: dict) -> set[str]:
    """The image extensions this model will take, as a set."""
    return set(field(entry, "images.accepts_ext", []) or [])
