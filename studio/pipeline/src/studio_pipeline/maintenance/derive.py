"""How an id, a media type and a reel entry are DERIVED. One definition each.

**These lived in `catalog_check.py` and that is why nobody knew they were
live.** Three of them are the arithmetic the dev-seed loader runs on every
object it writes, and the loader nearly reimplemented all three before somebody
noticed `CM.entity_id` already existed — because a module named for a migration
reads like a module you are not supposed to call.

The migration itself has been retired; see `maintenance/catalog_check.py`. What is
here is what outlived it, and what a second implementation of would be a second
answer to "which entity owns this?" — the question the whole key scheme rests on.
"""
from __future__ import annotations

import mimetypes
import posixpath
import uuid

#: uuid5 over a URL is what NAMESPACE_URL is for. A node id is already globally
#: unique — the seed derived it from `s3://<bucket>/<key>` — so an entity derived
#: from one is unique across buckets without naming a bucket here.
NAMESPACE = uuid.NAMESPACE_URL

KIND_PREFIX = {"character": "char", "project": "proj", "run": "run",
               "scene": "scene", "movie": "movie"}

# The `pk` partition each entity kind gets.

def entity_id(kind: str, root_node: str) -> str:
    """The id of the entity that adopts `root_node`.

    Derived from the node id and from nothing else — not the slug, not the key.
    See the module docstring: a slug is mutable by design, and a rename between
    `plan` and `apply` must not fork the migration.
    """
    return f"{KIND_PREFIX[kind]}-{uuid.uuid5(NAMESPACE, f'studio://{kind}/{root_node}')}"

def content_type(name: str) -> str:
    """Guessed from the extension, not read back with a HEAD.

    Kept from the catalog seed, which measured the trade: every writer in this
    package sets `ContentType` from exactly this call, so guessing reproduces
    what is stored, at zero requests against a bucket with thousands of objects.
    `maintenance/dev_seed.py` is the other caller.
    """
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def extension(name: str) -> str:
    """The suffix the API puts on a key, spelled the way the API spells it.

    `posixpath.splitext(...)[1].lower()` — a copy of `services/keys.py::extension`
    rather than an import, because the pipeline does not depend on the backend
    package and never has.

    **The copy has to agree exactly, and `test_the_two_key_builders_agree` is
    what holds it to that.** `desired_key` decides whether a key has drifted by
    comparing it against what `blob_key_for` stamped at creation; a
    disagreement about case alone would report every `.PNG` in a library as
    drift, and `reseat` would rewrite the same objects on every run, forever.
    """
    return posixpath.splitext(name)[1].lower()


# The extensions `services/keys.py` classifies as image or video, which is what
# decides reel membership. Copied rather than imported — the pipeline does not
# depend on the backend package — and held to the original by
# `test_the_two_reel_rules_agree`.
REEL_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif",
                             ".bmp", ".mp4", ".webm", ".mov", ".m4v"})


def in_the_reel(row: dict) -> bool:
    """Whether a node row qualifies for the sparse `by-recent` key (D5).

    A file, and an image or a video **by its NAME**. Not a folder — that is the
    pollution the re-key fixes. Not a document: `request.json` is a file node
    and has no business in a reel of media. Not an entity row, which is not a
    node at all and never reaches this function.

    **This read `content_type` and now reads the extension, because the API
    decides it on the extension and the API is what writes production rows.**
    `catalog._reel_value` stamps from `keys.kind(name)`, and `browse.reel`
    re-filters the query's results by `keys.kind(record["name"])` — so the name
    is the rule at BOTH ends of the live path, and a second rule here could only
    ever disagree with the thing it is checking.

    It did. `content_type` is absent until `confirm-upload` runs `HeadObject`,
    and it is whatever S3 reports rather than what the file is: sixteen rows in
    production were flagged `reel_polluted` by this function while being
    perfectly ordinary images the app was showing correctly. Fifteen were
    placeholders awaiting a confirm; one was a real JPEG stored as
    `binary/octet-stream`. Every one of them was a false positive, and together
    they blocked `reseat` behind a `verify` that could not pass.

    The name is also the only signal available at every point that has to make
    this call — create, confirm, seed and migrate. `content_type` is available
    at two of them.
    """
    return (row.get("kind") == "file"
            and extension(row.get("name") or "") in REEL_EXTENSIONS)
