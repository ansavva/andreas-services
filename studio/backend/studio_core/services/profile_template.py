"""The blank bible — the shape a subject starts with, and a hint per field.

**`profile_template.json` sits beside `models.json` and is the pipeline's
`templates/profile.yaml` with the placeholders taken out.** The yaml is what
`studio character create` seeds from and what `edit` hands a person to fill
in; its values are `<e.g. late 30s to mid 40s>` — prose about what to write,
which is right in a text editor and wrong in a form field. This is the same
tree with every placeholder emptied and the placeholder's words kept as a
`hints` entry, keyed by dotted path with no list indexes
(`wardrobe.tops.item`, not `wardrobe.tops.0.item`), so the SPA can draw the
words under the field instead of inside it.

**`location_template.json` is the same arrangement for a location**, derived
from `templates/location.yaml`. One file per subject kind, keyed by
`catalog.SUBJECT_KINDS`, and the same contract test holds each pair together.

A list of maps keeps one blank entry rather than none: the entry is the only
record of what a `tops` item or a `drift_modes` row holds, and the form adds
entries by copying the first.

**Two copies of one shape, held together by a test.** The API validates a
bible by section and by nothing below it (`routes/subjects.py`), so the
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

_HERE = pathlib.Path(__file__).resolve().parent.parent

#: One blank bible per subject kind. Spelled by kind name rather than imported
#: from `catalog` so this module stays free of boto3 — it is loaded by the
#: pipeline's fake API too.
PATHS = {
    "character": _HERE / "profile_template.json",
    "location": _HERE / "location_template.json",
}

_DOCS = {kind: json.loads(path.read_text(encoding="utf-8")) for kind, path in PATHS.items()}


def blank_profile(kind: str = "character") -> dict:
    """A fresh copy of the blank bible — every section, every field empty."""
    return copy.deepcopy(_DOCS[kind]["profile"])


def hints(kind: str = "character") -> dict[str, str]:
    """One line per field on what goes in it, keyed by dotted path."""
    return dict(_DOCS[kind]["hints"])


def template(kind: str = "character") -> dict:
    """What `GET /api/<kind>s/profile-template` answers with."""
    return {"profile": blank_profile(kind), "hints": hints(kind)}
