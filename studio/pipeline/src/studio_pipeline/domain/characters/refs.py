"""Which of a character's images a model gets shown — and it is TAGS.

There is no reference index and no default set. Both answered one question —
which of this character's many pictures does a generation see — and both
answered it somewhere other than on the picture, and the invariant between
them drifted: one production character carried four ids in `default_set` that
named no row at all, and a default shoot sent three images where seven were
meant.

It is tags on the file now. `default` is the handful; a group tag like `face`
or `body` says what the picture is. Both travel with the image through a
rename, a move and a copy. Two commands remain, and they answer the two
questions worth asking:

    studio character images <name>       what has this character got, and tagged how
    studio character selection <name>    what would a model be shown

Both are `domain/subjects.py`'s, bound to the character subject.

HARD RULE #2b IS UNCHANGED
--------------------------
What a generation is shown is who the character IS, and every later render is
held against it. A generated image still never becomes identity on its own:
promoting one is a separate human act — copy it into the character's tree,
then tag it. **The copy is not optional.** Ownership is the tree: a run's
output tagged `default` is a file in the run's folder with a tag on it, and it
is not this character's identity, because nothing outside the character's
branch is.
"""
from __future__ import annotations

from studio_pipeline.domain import subjects as S
from studio_pipeline.domain.characters.base import COMMANDS, SUBJECT
from studio_pipeline.domain.subjects import DEFAULT_TAG

#: The pool a character's identity images conventionally live in.
REFERENCE_POOL = S.IDENTITY_POOL


def selection_nodes(record, pick: list[str] | None = None, tags: list[str] | None = None,
                    slots: list[int] | None = None, limit: int | None = None) -> list[dict]:
    """The ordered entries a model would actually be shown. **Resolved by the API.**"""
    return S.selection_nodes(SUBJECT, record, pick=pick, tags=tags, slots=slots, limit=limit)


_COMMANDS = COMMANDS
cmd_images = _COMMANDS["images"]
cmd_selection = _COMMANDS["selection"]

__all__ = ["DEFAULT_TAG", "REFERENCE_POOL", "cmd_images", "cmd_selection", "selection_nodes"]
