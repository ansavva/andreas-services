"""A character's pools — material, not identity.

A pool is any folder under the character's root. `corpus/`, `seed/` and
`archive/` are the conventional starting names, and nothing here knows them:
a character whose only pool is `original/` is as valid as one with all four.
`reference/` is the one name `add-to` treats specially, and only on the way
IN: what makes an image identity is a tag, and `refs.py` owns that.

Both commands are `domain/subjects.py`'s, bound to the character subject.
"""
from __future__ import annotations

from studio_pipeline.domain.characters.base import COMMANDS
from studio_pipeline.domain.subjects import IDENTITY_POOL

_COMMANDS = COMMANDS
cmd_add_to_pool = _COMMANDS["add-to"]
cmd_pool = _COMMANDS["pool"]

__all__ = ["IDENTITY_POOL", "cmd_add_to_pool", "cmd_pool"]
