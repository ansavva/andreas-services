"""Characters: who a subject is, and which images say so.

A character is one of the two subject kinds `routes/subjects.py` builds
routes for — the other is a location — and everything about how the rows,
the selection and the bible work is documented there once. This module holds
the one thing that is a character's own: **the bible's sections.**

The bible is seven maps and one paragraph. `identity`, `face`, `body` and
`wardrobe` say what the character looks like; `voice` how they sound;
`rendering` what medium they exist in; `consistency` what a render is checked
against. `rendering` and `voice` are left out of what `GET .../textblock`
hands back as raw material, deliberately: a text-only engine is being told
what the character LOOKS like, and a medium or an accent spends words on
something the paragraph is not for.
"""

from studio_core.routes import subjects
from studio_core.routes.subjects import DEFAULT_TAG, TEXT_BLOCK
from studio_core.services import catalog

PROFILE_SECTIONS = (
    "identity",
    "face",
    "body",
    "wardrobe",
    "voice",
    "rendering",
    "consistency",
)

IDENTITY_BEARING = ("identity", "face", "body", "wardrobe", "consistency")

SPEC = subjects.Subject(
    kind=catalog.ENTITY_CHARACTER,
    segment="characters",
    sections=PROFILE_SECTIONS,
    identity_bearing=IDENTITY_BEARING,
    cli="character",
)

bp = subjects.blueprint(SPEC)


def clean_profile(raw) -> dict:
    """A character's bible, validated by section — see `subjects.clean_profile`."""
    return subjects.clean_profile(SPEC, raw)


__all__ = ["DEFAULT_TAG", "IDENTITY_BEARING", "PROFILE_SECTIONS", "SPEC", "TEXT_BLOCK",
           "bp", "clean_profile"]
