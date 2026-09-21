"""Locations: where a frame is, and which images say so.

A location is a room, a set, a street, a stage — anything a character is
photographed IN that has to look the same from one render to the next. It is
the second subject kind `routes/subjects.py` builds routes for, with the same
rows, the same `default`-tagged selection and the same bible mechanics as a
character; this module holds the one thing that is a location's own: **the
bible's sections.**

A location has no face and no wardrobe. What holds it on-model is its
geography, so the bible is `identity` (the card), `space` (what is fixed —
the plan, the openings, the built-in furniture), `dressing` (what is in it and
could move), `lighting` (where the light comes from, and its states), `palette`,
`rendering` (medium, lens, and the named camera VANTAGES a shot can be called
for by) and `consistency`. `rendering` is left out of the textblock's raw
material for the reason `voice` is on a character: a text-only engine is
being told what the place looks like, not what to shoot it on.

Group tags are the location's vantages: an image tagged `default` and `wide`
is an establishing view a generation is shown; `detail` and `reverse` narrow
the selection the way `face` and `body` do for a character. The tags are a
convention, not a schema — see `subjects.selection`.
"""

from studio_core.routes import subjects
from studio_core.routes.subjects import DEFAULT_TAG, TEXT_BLOCK
from studio_core.services import catalog

PROFILE_SECTIONS = (
    "identity",
    "space",
    "dressing",
    "lighting",
    "palette",
    "rendering",
    "consistency",
)

IDENTITY_BEARING = ("identity", "space", "dressing", "lighting", "palette", "consistency")

SPEC = subjects.Subject(
    kind=catalog.ENTITY_LOCATION,
    segment="locations",
    sections=PROFILE_SECTIONS,
    identity_bearing=IDENTITY_BEARING,
    cli="location",
)

bp = subjects.blueprint(SPEC)


def clean_profile(raw) -> dict:
    """A location's bible, validated by section — see `subjects.clean_profile`."""
    return subjects.clean_profile(SPEC, raw)


__all__ = ["DEFAULT_TAG", "IDENTITY_BEARING", "PROFILE_SECTIONS", "SPEC", "TEXT_BLOCK",
           "bp", "clean_profile"]
