"""The blank bible — the shape a character starts with, and a hint per field.

**`profile_template.json` sits beside `models.json` and is the pipeline's
`templates/profile.yaml` with the placeholders taken out.** The yaml is what
`studio character create` seeds from and what `edit` hands a person to fill
in; its values are `<e.g. late 30s to mid 40s>` — prose about what to write,
which is right in a text editor and wrong in a form field. This is the same
tree with every placeholder emptied and the placeholder's words kept as a
`hints` entry, keyed by dotted path with no list indexes
(`wardrobe.tops.item`, not `wardrobe.tops.0.item`), so the SPA can draw the
words under the field instead of inside it.

A list of maps keeps one blank entry rather than none: the entry is the only
record of what a `tops` item or a `drift_modes` row holds, and the form adds
entries by copying the first.

**Two copies of one shape, held together by a test.** The API validates a
bible by section and by nothing below it (`routes/characters.py`), so the
field names here are a starting point and not a rule — a person may add to or
take from any section, and the form lets them. What must not drift is the
sections and the fields the pipeline's engines actually read
(`rendering.default_style`, `wardrobe.tops[].item`, `consistency.must`), and
`pipeline/tests/contracts/test_profile_template.py` asserts the two trees have
the same keys.

`POST /api/characters` seeds a body that carries no `profile` from this, so a
character made in the app starts with the same form as one made by the CLI.
A body that says `profile: {}` gets `{}`: that is a client asking for empty.
"""

import copy
import json
import pathlib

PATH = pathlib.Path(__file__).resolve().parent.parent / "profile_template.json"

_DOC = json.loads(PATH.read_text(encoding="utf-8"))


def blank_profile() -> dict:
    """A fresh copy of the blank bible — every section, every field empty."""
    return copy.deepcopy(_DOC["profile"])


def hints() -> dict[str, str]:
    """One line per field on what goes in it, keyed by dotted path."""
    return dict(_DOC["hints"])


def template() -> dict:
    """What `GET /api/characters/profile-template` answers with."""
    return {"profile": blank_profile(), "hints": hints()}
