"""How an id, a media type and a reel entry are DERIVED. One definition each.

**These lived in `catalog_check.py` and that is why nobody knew they were
live.** Three of them are the arithmetic the dev-seed loader runs on every
object it writes, and the loader nearly reimplemented all three before somebody
noticed `CM.entity_id` already existed — because a module named for a migration
reads like a module you are not supposed to call.

The migration itself has been retired; see `maintenance/catalog.py`. What is
here is what outlived it, and what a second implementation of would be a second
answer to "which entity owns this?" — the question the whole key scheme rests on.
"""
from __future__ import annotations

import mimetypes
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

def in_the_reel(row: dict) -> bool:
    """Whether a node row qualifies for the sparse `by-recent` key (D5).

    A file, and an image or a video. **Not a folder** — that is the pollution
    the re-key fixes. **Not a document**: `request.json` is a file node and has
    no business in a reel of media. **Not an entity row**, which is not a node
    at all and never reaches this function.
    """
    return (row.get("kind") == "file"
            and str(row.get("content_type") or "").startswith(("image/", "video/")))
