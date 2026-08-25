"""The reference index — one `REF#` row per image — and the commands on it.

`reference/` holds far more images than any engine accepts (Kling 7, Seedance 9,
Nano Banana 14), so something has to say WHICH ones to send. That something used
to be a `references:` map inside the bible, keyed on the image's basename. It is
now one row per image, keyed on its **node id**:

    pk = CHAR#<char_id>   sk = REF#<node_id>
    group, order, description, tags, created

Four things follow, and each of them deletes something:

1. **A reference image can be called anything.** `<slug>_face_3.png` carried the
   character, the group and the ordinal in its name; the row carries all three.
   `group_prefix`, `pool_max_index` and `curate renumber` are gone with it.
2. **A regroup is one `PATCH`.** It was a reparent, a records sweep and an index
   rewrite. No object is written at all.
3. **Order is an attribute**, gapped by 1000, and `after` takes the midpoint —
   so a reorder is one write that never touches a neighbour. `character order`
   is the command that replaces filename numbering.
4. **`sync-refs` is deleted, and nothing replaces it.** It reconciled the bible's
   index against what was actually in `reference/`, because the two were
   independent: a file moved by `curate` was a description lost, and an image
   dropped in by hand was invisible until somebody remembered to sync. The index
   cannot drift from the folder any more, because it does not describe the
   folder — it names nodes, and a node survives every rename and every move
   (spec §3.5). There is nothing to reconcile and no `--apply` dry run to get
   wrong.

**Slot N is position N in the RESOLVED SELECTION**, unchanged in meaning and
moved in location: `GET /api/characters/<id>/selection` resolves it, so the CLI
and the SPA cannot disagree about which images a generation was shown. Over-cap
is refused there with the index in the body rather than truncated. `resolve_selection`
used to do this locally against the bible; `selection_nodes` below is the thin
thing left, and all it adds is `slots` — positional picking *within* an already
resolved selection, which is a caller's arithmetic and not a fact about the
character.

HARD RULE #2b IS UNCHANGED AND IS WHY `add-refs` EXISTS
-------------------------------------------------------
What is a reference is who the character IS, and every later render is held
against it. So a generated image never arrives here on its own: `studio character
shoot` leaves its results in their runs and files nothing, and promoting one is a
separate human act. `--from-run` copies the node and then attaches the copy, so
the run keeps its own output and nothing that cited it is disturbed.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import click
import yaml

from studio_pipeline.adapters import api, entities, store
# For `add-refs --from-run`: resolving a runref to its output node ids. One-way —
# the run store knows nothing about characters.
from studio_pipeline.domain import TEMPLATES_DIR
from studio_pipeline.domain import runs as R
from studio_pipeline.domain.characters.base import (
    IMG_EXTS,
    die,
    pool_folder,
    resolve,
    upload_file,
)

#: Where a promoted or uploaded reference file is put when no group is named. A
#: `REF#` row requires a group — reference-ness is now a stated purpose rather
#: than a folder — and inventing one for the caller would be a guess. This is
#: the honest placeholder: it appears in `counts`, it is visible in `refs`, and
#: it is one `regroup` away from wherever it belongs.
UNSORTED = "unsorted"
#: The pool a reference file conventionally lives in. A convention only: the row
#: is what makes an image a reference, so one filed anywhere else still counts.
REFERENCE_POOL = "reference"


def _record(character) -> dict:
    """A record, an id or a slug -> the record. Callers pass whichever they hold."""
    if isinstance(character, dict):
        return character
    try:
        return resolve(character)
    except api.NotFound:
        die(f"no character {character!r} (see `studio character list`)")


def reference_entries(character, group: str | None = None) -> list[dict]:
    """The described index as ONE ordered list, each entry carrying its group.

    `GET /api/characters/<id>/references` returns entries grouped, because the
    SPA draws sections; almost every caller here wants one list in
    `(group, order)` order. `adapters/entities` does the flattening so the group
    key's spelling stays in one file.

    Each entry has `node`, `group`, `order`, `description`, `tags`, `default`,
    and `file` — the node's name, size, content type and a presigned URL — so a
    caller never listens to the folder and never presigns a second time.
    """
    return entities.reference_entries(_record(character)["id"], group)


def selection_nodes(record, pick: list[str] | None = None, tags: list[str] | None = None,
                    slots: list[int] | None = None, limit: int | None = None) -> list[dict]:
    """The ordered entries a model would actually be shown.

    **The resolution is the API's.** `?pick=` / `?tag=` / `default_set` /
    everything, in that order, with the cap enforced server-side — an over-cap
    selection comes back as `api.Conflict` with the index in the message rather
    than silently truncated, because which images a generation saw must not be
    decided by whatever a listing returned. The caller catches that; nothing
    here converts it.

    `slots` is applied HERE and only here: it is 1-based positional picking
    *within* the resolved selection ("send me the 1st and 3rd of what you would
    have sent"), which is arithmetic on an answer rather than a question about
    the character. Sending it to the API would make the route's own `slot`
    numbering — position in the selection it just built — mean two things.
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


def entry_node(record: dict, token: str, entries: list[dict] | None = None) -> str:
    """A node id from what a person actually typed.

    An id is the real address and is what a script should pass. A filename or
    its stem is accepted because a person reading `character refs` sees names,
    and refusing them would make the ids the only usable handle on a screen full
    of pictures. Ambiguity is reported rather than resolved — two files called
    the same thing in two groups is a real state and picking one silently is how
    a description lands on the wrong image.
    """
    if token.startswith("node-"):
        return token
    entries = reference_entries(record) if entries is None else entries
    stem = os.path.splitext(token)[0]
    hits = [e for e in entries
            if (e.get("file") or {}).get("name") == token
            or os.path.splitext((e.get("file") or {}).get("name") or "")[0] == stem]
    if not hits:
        die(f"{record['slug']} has no reference {token!r}. "
            f"See `studio character refs {record['slug']}`.")
    if len(hits) > 1:
        die(f"{token!r} matches {len(hits)} references of {record['slug']} — name the node:\n"
            + "\n".join(f"       {h['node']}  {h['group']}/{(h.get('file') or {}).get('name')}"
                        for h in hits[:6]))
    return hits[0]["node"]


def _split(value: str | None) -> list[str] | None:
    return [x.strip() for x in value.split(",") if x.strip()] if value else None


# --- reading the index -----------------------------------------------------

@click.command("refs")
@click.argument("name", required=True)
@click.option("--group", help="Only this group (face, body, wardrobe, frame, …).")
@click.option("--json", "json_", is_flag=True)
def cmd_refs(name, group, json_):
    """The described reference index: what each image shows, in order.

    This used to be `refs --describe`, with the bare command resolving a
    selection and downloading it. The two are now separate commands, because
    they answer different questions and shared every flag: `refs` reads the
    index, `selection` resolves what a model would be sent.
    """
    record = _record(name)
    entries = reference_entries(record, group)
    if json_:
        print(json.dumps(entries, indent=2))
        return
    if not entries:
        die(f"{record['slug']} has no references yet. Promote one with "
            f"`studio character add-refs {record['slug']} --to <group> --from-run <runref>`.")
    print(f"{'group':<10} {'order':>6}  {'node':<42} {'name':<30} description")
    for entry in entries:
        file = entry.get("file") or {}
        mark = "*" if entry.get("default") else " "
        print(f"{entry['group']:<10} {entry['order']:>6}{mark} {entry['node']:<42} "
              f"{(file.get('name') or '—'):<30} "
              f"{entry.get('description') or '(no description)'}")
    print(f"\n* = in the default set ({len(reference_entries(record))} reference(s) total)",
          file=sys.stderr)


@click.command("selection")
@click.argument("name", required=True)
@click.option("--dest", help="Download the selection to this dir instead of printing it.")
@click.option("--json", "json_", is_flag=True)
@click.option("--limit", type=int, help="The model's cap. Over it is REFUSED, never truncated.")
@click.option("--pick", help="Comma-separated node ids or filenames from the index.")
@click.option("--presign", is_flag=True, help="Print ordered presigned HTTPS URLs.")
@click.option("--slots", help="Comma-separated 1-based positions WITHIN the resolved selection.")
@click.option("--tag", "tags", help="Comma-separated tags; an image must carry ALL of them.")
def cmd_selection(name, dest, json_, limit, pick, presign, slots, tags):
    """What a model would be shown, in slot order. **Resolved by the API.**

    Slot N is position N in THIS list — not a trailing file number and not a
    position in `reference/`. The same route the SPA calls, so the two cannot
    disagree about what a generation saw.
    """
    record = _record(name)
    try:
        chosen = selection_nodes(record, _split(pick), _split(tags),
                                 [int(x) for x in _split(slots) or []] or None, limit)
    except api.Conflict as exc:
        die(f"{exc}\n       reference/ is a library, not a set to send whole. Narrow it "
            f"with --pick / --tag, or make a choice the default:\n"
            f"       studio character default-set {record['slug']} <node> <node> …")
    except api.NotFound as exc:
        die(str(exc))
    if not chosen:
        die(f"no reference images resolved for {record['slug']}")

    if dest:
        os.makedirs(dest, exist_ok=True)
        out = {}
        for entry in chosen:
            local = os.path.join(dest, entry.get("name") or f"{entry['node']}.bin")
            store.download_node(entry["node"], pathlib.Path(local))
            out[entry["node"]] = os.path.abspath(local)
        print(json.dumps(out, indent=2))
        print(f"downloaded {len(out)} reference image(s) to {dest}. For Replicate prefer "
              "--presign (full-res, zero context cost).", file=sys.stderr)
        return
    if presign:
        urls = [store.presign_node(entry["node"]) for entry in chosen]
        print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
        print(f"presigned {len(urls)} reference image(s) for {record['slug']}. "
              "Slot N is position N in THIS list; cite as [Image1]…", file=sys.stderr)
        return
    if json_:
        print(json.dumps(chosen, indent=2))
        return
    for entry in chosen:
        print(f"slot {entry['slot']:<3} {entry['node']:<42} {entry['group']:<10} "
              f"{entry.get('description') or '(no description)'}")


# --- writing into the index ------------------------------------------------

#: The shot spec, read for one reason: a run made by `shoot` records the slot it
#: rendered, and the slot already carries the description and tags that image
#: should be filed under. Read as DATA from `domain/templates/`, not through
#: `engine.shoot`, because `domain` must not import `engine` — the arrow points
#: `cli -> domain -> adapters` and a cycle here is what split the character
#: modules apart in the first place.
_SPEC_PATH = TEMPLATES_DIR / "reference_shots.yaml"


def _slot_description(run_record: dict) -> tuple[str | None, list[str] | None]:
    """The description and tags a promoted run inherits from the slot it shot.

    **Provenance is a bonus, never a requirement.** A run with no
    `reference_slot` — anything not made by `shoot` — promotes undescribed
    rather than borrowing some other slot's words, and a slot id the spec no
    longer holds is treated the same way.

    This existed before the entity model, was lost in the move, and is restored
    because losing it is expensive in a quiet way: the fields sat in the repo
    unread and every promotion retyped them by hand. Fourteen descriptions were
    copied out of the spec twice before anyone noticed.
    """
    slot_id = (run_record.get("extra") or {}).get("reference_slot")
    if not slot_id:
        return None, None
    try:
        spec = yaml.safe_load(_SPEC_PATH.read_text()) or {}
    except OSError:
        return None, None
    for slot in spec.get("slots") or []:
        if slot.get("id") == slot_id:
            described = " ".join((slot.get("description") or "").split())
            return (described or None), (list(slot.get("tags") or []) or None)
    return None, None


@click.command("add-refs", epilog=(
    "\n\nArguments:\n  FILES  Local image files. Omit when using --from-run."))
@click.argument("name", required=True)
@click.argument("files", nargs=-1)
@click.option("--after", help="Place the new entry after this node, rather than last.")
@click.option("--description", help="What the image shows. An undescribed image cannot be "
              "picked by tag.")
@click.option("--from-run", "from_run", multiple=True,
              help=("Promote a RUN's output instead of a local file. Repeatable; takes a "
                    "runref like <project>/latest#1."))
@click.option("--project", help="Default project for a bare runref given to --from-run.")
@click.option("--tags", help="Comma-separated tags for the new entry(ies).")
@click.option("--to", "group", default=UNSORTED,
              help=f"The reference group: face, body, wardrobe, frame, … (default: {UNSORTED}).")
def cmd_add_refs(name, files, after, description, from_run, project, tags, group):
    """Attach image(s) to a character as references.

    THIS IS THE GATE ON A CHARACTER'S IDENTITY (hard rule #2b). Everything else
    about a generation is reversible bookkeeping; what is a reference is who the
    character IS. So a generated image never arrives here on its own — `shoot`
    leaves its results in their runs and prints the `--from-run` line to promote
    the ones a person chose to keep.

    Two steps, always: the bytes arrive (an upload, or a copy of a run's
    output), then a `REF#` row says the image is identity. `--replace` and
    `--start` are gone with the numbering they controlled — order is an
    attribute now, so `character order` moves an entry and nothing is renamed.
    """
    record = _record(name)
    if not files and not from_run:
        die("nothing to add — pass local file(s), or --from-run <runref> to promote "
            "a run's output.")
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")

    folder = store.ensure_child_folder(pool_folder(record, REFERENCE_POOL)["id"], group)
    attached: list[dict] = []

    for local in files:
        node = upload_file(folder["id"], local)
        attached.append(node)
        print(f"  {local} -> {group}/{node['name']}", file=sys.stderr)

    # What a promoted run's images inherit, when the person did not say. Keyed
    # by node id because one `add-refs` may promote several runs at once and
    # they need not have shot the same slot.
    inherited: dict[str, tuple[str | None, list[str] | None]] = {}

    for ref in from_run:
        try:
            nodes = R.resolve_output_nodes(ref, project, kinds=IMG_EXTS)
            described = _slot_description(R.resolve_run(ref, project))
        except R.RunError as exc:
            die(str(exc))
        # A real copy — two blobs, two independent lifetimes. The run keeps its
        # own output, which is the point of promoting rather than moving: every
        # record that cited the run's output still cites the run's output.
        made = store.copy_nodes(nodes, folder["id"]).get("nodes") or []
        attached += made
        for node in made:
            inherited[node["id"]] = described
            print(f"  {ref} -> {group}/{node['name']}", file=sys.stderr)

    cursor = after
    for node in attached:
        # An explicit --description/--tags always wins; the slot only fills a
        # silence.
        slot_description, slot_tags = inherited.get(node["id"], (None, None))
        try:
            entry = entities.add_reference(record["id"], node["id"], group,
                                           description=description or slot_description,
                                           tags=_split(tags) or slot_tags,
                                           after=cursor)
        except api.Conflict:
            print(f"  {node['id']} is already a reference of {record['slug']} — left alone",
                  file=sys.stderr)
            continue
        cursor = node["id"]
        print(f"attached {node['id']} (group {entry['group']}, order {entry['order']})")

    if group == UNSORTED:
        print(f"note: no --to given, so these are in group {UNSORTED!r}. Move them with\n"
              f"      studio character regroup {record['slug']} <node> --to <group>",
              file=sys.stderr)
    if not description:
        print("note: undescribed. An image with no description cannot be picked by tag and "
              f"is invisible to whoever chooses the set:\n"
              f"      studio character set-ref-desc {record['slug']} <node> '…' --tags face,neutral",
              file=sys.stderr)


@click.command("set-ref-desc")
@click.argument("name", required=True)
@click.argument("node", required=True)
@click.argument("description", required=False)
@click.option("--tags", help="Comma-separated, replacing the existing tags.")
def cmd_set_ref_desc(name, node, description, tags):
    """Describe one reference. **One row's write.**

    It was a read of the whole bible, an edit of one entry in a map keyed on the
    basename, and a write of the whole document back — so two descriptions
    written at once fought over one document and the loser was silently
    discarded. NODE is a node id, a filename or its stem.
    """
    record = _record(name)
    entry = entities.patch_reference(record["id"], entry_node(record, node),
                                     description=description, tags=_split(tags))
    print(json.dumps(entry, indent=2))


@click.command("describe-refs")
@click.argument("name", required=True)
@click.option("--from", "from_json", required=True,
              help="JSON object: {node: {group?, description, tags}}.")
def cmd_describe_refs(name, from_json):
    """Describe many references in ONE transaction.

    `PUT /api/characters/<id>/references`. Describing a forty-image library one
    call at a time is forty round trips and forty chances to stop halfway with
    the index half-written; the whole pass lands or none of it does.

    **The document is keyed on node ids now, not basenames.** A basename was
    only ever unique within a group and changed whenever anything was
    renumbered, which is precisely how a description came to sit on the wrong
    image. Filenames and stems are still accepted and resolved here, so a batch
    written by hand off `character refs` keeps working.
    """
    record = _record(name)
    with open(from_json) as fh:
        batch = json.load(fh)
    if not isinstance(batch, dict):
        die("--from must contain an object of {node: {group?, description, tags}}")

    known = reference_entries(record)
    entries = []
    for token, spec in batch.items():
        entry = {"node": entry_node(record, token, known)}
        for field in ("group", "description", "tags"):
            if field in spec:
                entry[field] = spec[field]
        entries.append(entry)
    entities.put_references(record["id"], entries)

    left = [e for e in reference_entries(record) if not (e.get("description") or "").strip()]
    print(f"described {len(entries)} reference(s) in one write; {len(left)} still undescribed",
          file=sys.stderr)
    for entry in left:
        print(f"{entry['node']}  {entry['group']}/{(entry.get('file') or {}).get('name')}")


@click.command("order")
@click.argument("name", required=True)
@click.argument("nodes", nargs=-1, required=True)
@click.option("--after", help="Place the first node after this one. Omit to keep it where it is.")
@click.option("--group", required=True, help="The group being ordered.")
def cmd_order(name, nodes, after, group):
    """Order references explicitly. **NEW — this replaces filename numbering.**

    Order was the trailing number in a filename, so changing it meant renaming
    files, and `curate renumber` existed to close the holes that left. `order`
    is an attribute of the `REF#` row, gapped by 1000, and `after` takes the
    midpoint of two neighbours — so each move here is ONE `PATCH` that touches
    no neighbour and writes no object.

    Each node is placed after the one before it. With `--after`, the first goes
    after that node; without, the first stays where it is and the rest follow
    it.
    """
    record = _record(name)
    known = reference_entries(record, group)
    in_group = {e["node"] for e in known}
    ids = [entry_node(record, token, reference_entries(record)) for token in nodes]
    stray = [i for i in ids if i not in in_group]
    if stray:
        die(f"not in group {group!r}: {', '.join(stray)}\n"
            f"       regroup first: studio character regroup {record['slug']} <node> --to {group}")

    cursor = after and entry_node(record, after, reference_entries(record))
    moved = 0
    for node in ids:
        if cursor is None:
            cursor = node  # the first named node keeps its place; the rest follow it
            continue
        entities.patch_reference(record["id"], node, after=cursor)
        cursor = node
        moved += 1
    print(f"reordered {moved} reference(s) in {group}/ — no object was written")


@click.command("regroup")
@click.argument("name", required=True)
@click.argument("nodes", nargs=-1, required=True)
@click.option("--to", "group", required=True, help="The group to move them into.")
def cmd_regroup(name, nodes, group):
    """Move references into another group. **ONE `PATCH` each, no object written.**

    This was `studio curate regroup`, and it was a file operation: it reparented
    every named object into `reference/<group>/` and then swept every run, scene
    and chain document rewriting the paths that cited them — because a record
    named a path. Skipping that sweep is what once left 69 records pointing at
    images that no longer existed.

    A group is an attribute of a row that names a **node id**. Nothing moves,
    nothing is rewritten, and the file stays exactly where it is — which is also
    why this is a `character` command and no longer a `curate` one: it curates
    nothing on disk.
    """
    record = _record(name)
    known = reference_entries(record)
    for token in nodes:
        node = entry_node(record, token, known)
        entry = entities.patch_reference(record["id"], node, group=group)
        print(f"{node} → group {entry['group']} (order {entry['order']})")
    print(f"moved {len(nodes)} reference(s) to group {group} — no object was written",
          file=sys.stderr)


@click.command("detach")
@click.argument("name", required=True)
@click.argument("nodes", nargs=-1, required=True)
def cmd_detach(name, nodes):
    """Stop treating image(s) as identity. **The files stay exactly where they are.**

    The counterpart to `add-refs`, and the honest way to demote something:
    `curate move … --to archive` moves a file and leaves its row alone, because
    reference-ness is a row and not a location. This removes the row.
    """
    record = _record(name)
    known = reference_entries(record)
    for token in nodes:
        node = entry_node(record, token, known)
        entities.delete_reference(record["id"], node)
        print(f"detached {node} — the file is untouched")


@click.command("default-set")
@click.argument("name", required=True)
@click.argument("nodes", nargs=-1)
def cmd_default_set(name, nodes):
    """Name the references sent when --character is given with no selector.

    An ordered list of node ids on the record — small, ordered, and read on
    every generation, which is why it stayed a field where `references:` became
    rows. With no NODES, prints the current set.
    """
    record = _record(name)
    if not nodes:
        print(json.dumps(record.get("default_set") or [], indent=2))
        return
    known = reference_entries(record)
    ids = [entry_node(record, token, known) for token in nodes]
    try:
        found = entities.put_default_set(record["id"], ids, record["rev"])
    except api.NotFound as exc:
        die(str(exc))
    print(json.dumps(found.get("default_set") or ids, indent=2))
    print(f"default set: {len(ids)} reference(s)", file=sys.stderr)
