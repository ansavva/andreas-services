"""Which of a character's images a model gets shown — and it is TAGS now.

There is no reference index and no default set. Both answered one question —
which of this character's many pictures does a generation see — and both
answered it somewhere other than on the picture:

    a `CHAR#<id>` / `REF#<node>` row     said an image was identity, in a group,
                                         at an order
    `default_set` on the character       said which handful to actually send

So the same fact lived in two places with an invariant between them, and the
invariant drifted. One production character carried four ids in `default_set`
that named no row at all, and a default shoot sent three images where seven were
meant, with nothing anywhere saying so.

It is tags on the file now. `default` is the handful; a group tag like `face` or
`body` says what the picture is. Both travel with the image through a rename, a
move and a copy, because they are attributes of the node rather than a second
record pointing at it — so nothing can drift from anything.

WHAT THAT DELETED HERE
----------------------
`refs`, `add-refs`, `set-ref-desc`, `describe-refs`, `order`, `regroup`,
`detach` and `default-set` — eight commands, all of them writing to an index
that does not exist. Tagging is `studio describe <node> --tag …`, which already
existed for exactly this and is now the only way in. `order` has nothing left to
order; `regroup` is a tag edit; `detach` is removing a tag.

Two commands remain, and they answer the two questions worth asking:

    studio character images <name>       what has this character got, and tagged how
    studio character selection <name>    what would a model be shown

HARD RULE #2b IS UNCHANGED
--------------------------
What a generation is shown is who the character IS, and every later render is
held against it. A generated image still never becomes identity on its own:
`studio character turnaround` leaves its results in their runs, and promoting
one is a separate human act — copy it into the character's tree, then tag it.
**The copy is not optional any more.** Ownership is the tree: a run's output
tagged `default` is a file in the run's folder with a tag on it, and it is not
this character's identity, because nothing outside the character's branch is.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import click

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.domain.characters.base import die, resolve

#: What a selection asks for when nobody names a tag. The API's default too —
#: spelled here so the message a person reads names the tag they would type.
DEFAULT_TAG = "default"

#: The pool a character's identity images conventionally live in. A convention
#: only, and a weaker one than it used to be: the tag is what makes an image
#: identity, so one filed anywhere under the character counts.
REFERENCE_POOL = "reference"


def _record(character) -> dict:
    """A record, an id or a name -> the record. Callers pass whichever they hold."""
    return character if isinstance(character, dict) else resolve(character)


def selection_nodes(record, pick: list[str] | None = None, tags: list[str] | None = None,
                    slots: list[int] | None = None, limit: int | None = None) -> list[dict]:
    """The ordered entries a model would actually be shown.

    **The resolution is the API's.** `?pick=` names images, `?tag=` names tags,
    and neither means `default` — with the cap enforced server-side, so an
    over-cap selection comes back as `api.Conflict` rather than silently
    truncated. Which images a generation saw must not be decided by whatever a
    listing happened to return. The caller catches that; nothing here converts it.

    `slots` is applied HERE and only here: it is 1-based positional picking
    *within* the resolved selection ("send the 1st and 3rd of what you would have
    sent"), which is arithmetic on an answer rather than a question about the
    character. Sending it to the API would make the route's own `slot` numbering
    mean two things.
    """
    found = entities.selection(_record(record)["id"], pick=pick, tag=tags, limit=limit)
    chosen = found.get("selection") or []
    if slots:
        try:
            chosen = [chosen[i - 1] for i in slots]
        except IndexError:
            die(f"--slots out of range: the selection has {len(chosen)} image(s)")
        for position, entry in enumerate(chosen, 1):
            entry["slot"] = position
    return chosen


def _split(value: str | None) -> list[str] | None:
    return [x.strip() for x in value.split(",") if x.strip()] if value else None


@click.command("images")
@click.argument("name", required=True)
@click.option("--json", "json_", is_flag=True)
@click.option("--tag", "tags", help="Comma-separated; an image must carry ALL of them.")
def cmd_images(name, json_, tags):
    """Every image under a character, with the tags that decide what it is for.

    **This replaces `character refs`, and it lists more than that ever did.** The
    old command listed the reference index — the images somebody had filed rows
    for — so a picture sitting in `corpus/` or dropped into the tree by hand was
    invisible to it, which is how twelve files in this library ended up with no
    description anywhere. Every image under the character is here; the tags say
    which are identity.
    """
    record = _record(name)
    found = entities.character_images(record["id"], tags=_split(tags))
    if json_:
        print(json.dumps(found, indent=2))
        return
    if not found:
        print(f"{record['name']} has no images"
              + (f" tagged {tags}" if tags else ""), file=sys.stderr)
        return
    for entry in found:
        marked = "*" if DEFAULT_TAG in (entry.get("tags") or []) else " "
        # The NAME leads, because that is what a person is looking at on a
        # screen full of pictures; the id is what a script passes on.
        print(f"{marked} {entry['name']:<32} {', '.join(entry.get('tags') or []) or '-':<26} "
              f"{entry['id']}  {entry.get('description') or ''}")
    sent = sum(1 for e in found if DEFAULT_TAG in (e.get("tags") or []))
    print(f"\n{len(found)} image(s); {sent} carry `{DEFAULT_TAG}` and are what a "
          f"generation is shown.\nTag one: studio describe <node> --tag {DEFAULT_TAG} --tag face",
          file=sys.stderr)


@click.command("selection")
@click.argument("name", required=True)
@click.option("--dest", help="Download the selection to this dir instead of printing it.")
@click.option("--json", "json_", is_flag=True)
@click.option("--limit", type=int, help="The model's cap. Over it is REFUSED, never truncated.")
@click.option("--pick", help="Comma-separated node ids or filenames.")
@click.option("--presign", is_flag=True, help="Print ordered presigned HTTPS URLs.")
@click.option("--slots", help="Comma-separated 1-based positions WITHIN the resolved selection.")
@click.option("--tag", "tags", help="Comma-separated tags; an image must carry ALL of them.")
def cmd_selection(name, dest, json_, limit, pick, presign, slots, tags):
    """What a model would be shown, in slot order. **Resolved by the API.**

    With no `--tag` and no `--pick` this is the character's `default` images.
    Slot N is position N in THIS list — not a trailing file number and not a
    position in `reference/`. The same route the SPA calls, so the two cannot
    disagree about what a generation saw.
    """
    record = _record(name)
    try:
        chosen = selection_nodes(record, _split(pick), _split(tags),
                                 [int(x) for x in _split(slots) or []] or None, limit)
    except api.Conflict as exc:
        die(f"{exc}\n       a character is a library, not a set to send whole. Narrow it "
            f"with --pick / --tag, or take `{DEFAULT_TAG}` off the ones you do not "
            f"want sent:\n       studio describe <node> --tag face")
    except api.NotFound as exc:
        die(str(exc))
    if not chosen:
        die(f"no images resolved for {record['name']}")

    if dest:
        os.makedirs(dest, exist_ok=True)
        out = {}
        for entry in chosen:
            local = os.path.join(dest, entry.get("name") or f"{entry['node']}.bin")
            store.download_node(entry["node"], pathlib.Path(local))
            out[entry["node"]] = os.path.abspath(local)
        print(json.dumps(out, indent=2))
        print(f"downloaded {len(out)} image(s) to {dest}. For Replicate prefer "
              "--presign (full-res, zero context cost).", file=sys.stderr)
        return
    if presign:
        urls = [store.presign_node(entry["node"]) for entry in chosen]
        print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
        print(f"presigned {len(urls)} image(s) for {record['name']}. "
              "Slot N is position N in THIS list; cite as [Image1]…", file=sys.stderr)
        return
    if json_:
        print(json.dumps(chosen, indent=2))
        return
    for entry in chosen:
        print(f"slot {entry['slot']:<3} {entry['node']:<42} "
              f"{', '.join(entry.get('tags') or []) or '-':<24} "
              f"{entry.get('description') or '(no description)'}")
