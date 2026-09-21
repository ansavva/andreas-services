"""`studio location` — manage the places a frame is shot in.

A location is a room, a set, a street, a stage: anything a character is
photographed IN that has to look the same from one render to the next. It is
the second subject `domain/subjects.py` builds a command tree for, and it is
the same shape as a character in every way the library cares about:

    the record   id, name, rev, root, hero, profile   — one row, queryable
    the tree     a folder node the record names as `root`, holding the
                 reference images and whatever else is filed under it

What differs is the bible. A location has no face and no wardrobe; what
holds it on-model is its GEOGRAPHY, so `templates/location.yaml` describes
`space` (what is fixed — the plan, the openings, the built-in furniture),
`dressing` (what is in it and could move), `lighting` (where the light comes
from, and its states), `palette`, and named camera `vantages` under
`rendering`, so a shot can be called for by position rather than described
from scratch.

Which images a generation is shown is the `default` tag, as for a character.
The group tags are the vantages: `wide` for an establishing view, `reverse`,
`detail`, `plan` — a convention, not a schema, and `studio describe <node>
--tag default --tag wide` is the whole of filing one.

Hard rule #2b applies unchanged: a rendered view of a room becomes its
identity only by a person copying it into the location's tree and tagging
it, on a yes. A run leaves its results where they are.

Subcommands:
  list                          Every location, with sent and file counts.
  show   <name>                 The record: id, rev, counts, the folders it has.
  create <name> [--from-profile FILE]
                                The record, its index row and its root.
  edit   <name>                 Round-trip the bible through
                                local/locations/<name>.yaml.
  set-profile <name> [FILE]     Replace the bible (FILE omitted: the local copy).
  rename <old> <new>            One PATCH. Nothing moves.
  delete <name>                 Remove the record; keeps the folder by default.
  textblock <name>              A pasteable paragraph of what is fixed.
  images <name> [--tag T]       Every image under it, and how each is tagged.
  selection <name> [--pick|--tag|--limit|--slots|--presign]
                                What a model would actually be shown.
  add-to <name> POOL FILES…     Add to a pool — any folder but reference/.
  pool   <name> POOL            List one the location has.

Examples:
  studio location create <name>
  studio location edit <name>
  studio location images <name>
  studio location selection <name> --tag wide --limit 3 --presign
  studio run --model nano-banana-pro --character <name> --location <place> --prompt "…" --dry-run
"""
from __future__ import annotations

from studio_pipeline import STUDIO_DIR
from studio_pipeline.domain import TEMPLATES_DIR
from studio_pipeline.domain import subjects as S

TEMPLATE = str(TEMPLATES_DIR / "location.yaml")
LOCAL_DIR = str(STUDIO_DIR / "local" / "locations")

# The conventional pools. `reference/` holds the views a generation is shown;
# `corpus/` collected photographs and plans of the place; `archive/` retired
# material. Made on first use, never required.
POOLS = ("reference", "corpus", "archive")

PROFILE_KEYS = (
    "name",
    "identity",
    "space",
    "dressing",
    "lighting",
    "palette",
    "rendering",
    "consistency",
    "text_identity_block",
)

SUBJECT = S.Subject(
    kind="location",
    segment="locations",
    id_prefix="loc-",
    cli="location",
    template=TEMPLATE,
    local_dir=LOCAL_DIR,
    profile_keys=PROFILE_KEYS,
    group_example="wide",
    pools=POOLS,
    next_step="add photographs or plans with `studio location add-to {name} corpus <img>...`",
)


def resolve(location: str) -> dict:
    """An id, or a name matched client-side -> the location record."""
    return S.resolve(SUBJECT, location)


def load_profile(name: str) -> dict:
    """The bible of one location, as one map."""
    return S.load_profile(SUBJECT, name)


def selection_nodes(record, pick=None, tags=None, slots=None, limit=None) -> list[dict]:
    """The ordered entries a model would be shown of this location. **Resolved by the API.**"""
    return S.selection_nodes(SUBJECT, record, pick=pick, tags=tags, slots=slots, limit=limit)


main = S.group(SUBJECT, __doc__)
