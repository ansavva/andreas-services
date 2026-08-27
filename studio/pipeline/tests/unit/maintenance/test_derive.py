"""`maintenance/derive.py` — the derivations shared by the loader and the checks.

These arrived here in two moves and the second one matters. The module was split
out of `catalog_migrate.py` because being imported from a file named for a
migration is why nobody knew `entity_id`, `content_type` and `in_the_reel` were
live. Then #503 replaced the reel rule wholesale: it decided on `content_type`
and now decides on the file NAME.

`test_the_two_reel_rules_agree` came with it, and is the seam that keeps the
copied extension list honest.
"""
from __future__ import annotations

import re

import pytest

from studio_pipeline import STUDIO_DIR
from studio_pipeline.maintenance import derive


def test_the_two_reel_rules_agree():
    """`REEL_EXTENSIONS` must be exactly what `services/keys.py` calls media.

    The pipeline does not import the backend, so the list is copied and this is
    the seam that keeps the copy honest — the same technique, and the same
    reason, as `test_the_two_key_builders_agree`. An extension added to the API
    and not here is a file the app puts in the reel and `verify` calls pollution.

    **Reached through `STUDIO_DIR` rather than `parents[4]` off a module file.**
    The original counted, and this module has since moved once already; counting
    is what breaks every time a file does.
    """
    keys_py = (STUDIO_DIR / "backend" / "studio_core" / "services" / "keys.py").read_text()
    found: set[str] = set()
    for setname in ("IMAGE_EXTENSIONS", "VIDEO_EXTENSIONS"):
        match = re.search(rf"^{setname} = frozenset\(\{{(.+?)\}}\)", keys_py, re.S | re.M)
        assert match, f"{setname} is gone or no longer a frozenset literal"
        found |= set(re.findall(r'"([^"]+)"', match.group(1)))

    assert found == set(derive.REEL_EXTENSIONS), (
        f"only in keys.py: {sorted(found - set(derive.REEL_EXTENSIONS))}; "
        f"only in derive: {sorted(set(derive.REEL_EXTENSIONS) - found)}")


@pytest.mark.parametrize("row, expected", [
    ({"kind": "file", "name": "a.png"}, True),
    ({"kind": "file", "name": "a.MP4"}, True),
    # A document is a file node and has no business in a reel of media.
    ({"kind": "file", "name": "request.json"}, False),
    # A folder is the pollution the re-key fixes.
    ({"kind": "folder", "name": "a.png"}, False),
    # **The regression #503 fixed, stated as a case.** `content_type` is absent
    # until `confirm-upload` runs `HeadObject` and is then whatever S3 reports;
    # sixteen production rows were called `reel_polluted` over it while the app
    # displayed them perfectly. The NAME is the rule at both ends of the live
    # path, so it is the rule here.
    ({"kind": "file", "name": "a.png", "content_type": None}, True),
    ({"kind": "file", "name": "a.png", "content_type": "binary/octet-stream"}, True),
    ({"kind": "file", "name": "notes.txt", "content_type": "image/png"}, False),
])
def test_reel_membership_is_decided_on_the_name(row, expected):
    assert derive.in_the_reel(row) is expected


@pytest.mark.parametrize("name, expected", [
    ("a.png", ".png"),
    ("A.PNG", ".png"),
    ("no-extension", ""),
    ("two.dots.jpg", ".jpg"),
])
def test_an_extension_is_lowercased_the_way_the_api_spells_it(name, expected):
    """A disagreement about case alone would report every `.PNG` in a library as
    drift, and `reseat` would rewrite the same objects on every run, forever."""
    assert derive.extension(name) == expected


def test_an_entity_id_is_derived_from_its_root_node():
    """Not from the slug: a slug is mutable, and a rename between two runs would
    fork the derivation and write a second entity beside the first."""
    assert derive.entity_id("character", "node-1").startswith("char-")
    assert derive.entity_id("project", "node-1").startswith("proj-")
    assert derive.entity_id("character", "node-1") != derive.entity_id("project", "node-1")
