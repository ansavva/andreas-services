"""The tag vocabularies — one for files, one for templates, and never one list.

A tag is reusable: the same word on forty files is one tag, and picking it from a
list is how a person avoids inventing `three-quarter` and `three quarter` on
consecutive days. That is the whole reason this module exists — a free-text box
produces a vocabulary nobody can see, and a vocabulary nobody can see is one
everybody spells differently.

## Two vocabularies, and they do not mix

`face` on a picture and `face` on a template are the same word about different
things: one says what a photograph shows, the other says what a prompt is for.
Offering a file's tags while somebody edits a template would suggest words that
mean nothing there, so the scopes are separate lists with separate CRUD, and
nothing here ever merges them.

## DERIVED, which is what makes deletion honest

There is no `TAG#` row. A tag exists exactly while something carries it, so
"delete a tag when nothing references it" is not a sweep that can fall behind —
it is the definition. Deleting a tag IS removing it from everything that has it,
and the last removal is the deletion.

**What that costs is a colour.** A colour has to be stored somewhere, and a row
holding one would outlive its last reference and need collecting, which is the
drift this arrangement exists to avoid. Colours are worth having and are worth
paying a row for; that is a decision to make deliberately rather than a
side effect of adding one.

**What it buys is that a rename cannot half-happen.** The name is the identity —
`?tag=default,face` filters on it, the CLI passes it, a prod row stores it — so
renaming is rewriting every carrier, in batches, and there is no second record
left saying the old thing.
"""

from studio_core import config
from studio_core.errors import ValidationError
from studio_core.services import catalog

#: The two vocabularies. `file` is what a picture shows and what it is for;
#: `template` is what a prompt makes.
SCOPES = ("file", "template")


def clean_scope(raw: str | None) -> str:
    if raw not in SCOPES:
        raise ValidationError(f"scope must be one of {', '.join(SCOPES)}")
    return raw


def _files(lib: str) -> list[dict]:
    """Every node in the library, as records.

    One `by-path` query on the root's own child path — the same read a recursive
    listing makes, bounded the same way. There is no index on tags and there
    should not be: a tag is a small set on a row, and an index on one would be a
    second copy of the vocabulary to keep in step.
    """
    root = catalog.node(catalog.library(lib)["root_node"])
    found, _truncated = catalog.branch(lib, catalog.child_path(root),
                                       config.max_folder_objects())
    return found


def _carriers(lib: str, scope: str) -> list[tuple[dict, list[str]]]:
    """Everything in one scope that can carry tags, with the tags it carries."""
    if scope == "file":
        return [(record, list(record.get("tags") or [])) for record in _files(lib)]
    return [(record, list(record.get("tags") or []))
            for record in catalog.templates(lib)["templates"]]


def used(lib: str, scope: str) -> list[dict]:
    """Every tag in one vocabulary, with how many things carry it.

    Sorted by name rather than by count: this is a list somebody reads to find a
    word they half-remember, and a list that reorders itself as things are
    tagged is one you cannot learn the shape of.
    """
    counts: dict[str, int] = {}
    for _record, tags in _carriers(lib, scope):
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
    return [{"name": name, "count": counts[name]} for name in sorted(counts)]


def _rewrite(lib: str, scope: str, name: str, replacement: str | None) -> int:
    """Put `replacement` in place of `name` everywhere in one scope, or drop it.

    Returns how many things changed. A no-op is 0 rather than an error: asking
    to delete a tag that is already gone is a request that has been satisfied.
    """
    changed = 0
    for record, tags in _carriers(lib, scope):
        if name not in tags:
            continue
        # Order is preserved and duplicates are not created: renaming `face` to
        # `body` on something already carrying `body` leaves one `body` where
        # the two would otherwise sit next to each other.
        kept: list[str] = []
        for tag in tags:
            tag = replacement if tag == name else tag
            if tag is not None and tag not in kept:
                kept.append(tag)
        if scope == "file":
            catalog.describe_node(record["node_id"], tags=kept)
        else:
            catalog.put_template(lib, record["name"], {**record, "tags": kept})
        changed += 1
    return changed


def rename(lib: str, scope: str, name: str, replacement: str) -> int:
    """Rename one tag across its vocabulary. **Every carrier, or the name lies.**

    The name IS the identity — a filter passes it, a CLI passes it, a stored row
    holds it — so a rename that left one carrier behind would leave two tags
    where a person believes there is one, and the filter would find half of what
    they meant.
    """
    replacement = " ".join((replacement or "").split()).lower()
    if not replacement:
        raise ValidationError("a tag needs a name")
    if len(replacement) > catalog.MAX_TAG:
        raise ValidationError(f"tag longer than {catalog.MAX_TAG} characters")
    if replacement == name:
        return 0
    return _rewrite(lib, scope, name, replacement)


def remove(lib: str, scope: str, name: str) -> int:
    """Delete one tag: take it off everything that carries it.

    **That is the whole of the delete**, because the vocabulary is what is in
    use. There is no row left over to collect and no state where a tag exists
    but nothing has it.
    """
    return _rewrite(lib, scope, name, None)
