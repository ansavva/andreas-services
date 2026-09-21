"""A SUBJECT — a character or a location — and the one command tree both get.

A character is who is in the frame; a location is where the frame is. To the
library they are the same thing: a row with a UUID and a validated `profile`
map (the bible), a root folder whose images carry tags, and one route that
resolves which of those images a model is shown. The pipeline's two command
groups — `studio character` and `studio location` — are therefore ONE set of
commands built twice, and this module is where they are built.

What differs between the two is held in a `Subject` and nothing else: the API
segment, the id prefix, the yaml template the bible is seeded from, the keys
that template has, and the words a message uses. `characters/` and
`locations.py` each declare one `Subject` and bind these functions to it.

THE BIBLE IS A FIELD ON A ROW, NOT A DOCUMENT IN A BUCKET
---------------------------------------------------------
The bible is `profile` on the record — a validated map the API owns — and one
of its keys lives outside it as a real field, because it is not description,
it is identity:

    name          -> the record's `name`, a free-text label

`document` merges the promoted field back in, and that is a compatibility seam
with a reason: `domain/prompt.py` reads a bible as one map and indexes it by
key. Handing it a map with a key silently missing would not fail; it would
render slightly worse prompts, which is the failure that does not get noticed.

Nothing in the bible names a file: which images are identity is a tag on each
image, so a rename cannot strand a description.

`rev` IS THE CONFLICT CHECK, AND IT HAPPENS WHERE THE WRITE HAPPENS
-------------------------------------------------------------------
Comparing a version here and then writing is check-then-write, with a window
in between where somebody else's write lands and is lost. `rev` closes it:
`PATCH /api/<segment>/<id>/profile` takes `{profile, rev}` and the API refuses
a stale one with a `ConditionExpression`, so there is no gap at all. A `409`
arrives as `api.Conflict` and means exactly one thing: somebody wrote since you
read.

The local sidecar holds the `rev` observed at pull time, and `edit --push`
sends *that* rather than whatever the record says today — so a push of a copy
pulled an hour ago is refused by the API rather than quietly reverting every
description written since.

WHICH IMAGES A MODEL IS SHOWN IS TAGS
------------------------------------
`default` is the handful a generation gets; a group tag beside it — `face` or
`body` on a character, `wide`, `reverse` or `detail` on a location — says what
the picture is. Both travel with the image through a rename, a move and a
copy, because they are attributes of the node rather than a second record
pointing at it. `selection_nodes` asks the API, never the tree, so the CLI
and the SPA cannot disagree about what a model saw.

THE POOLS ARE A CONVENTION, NOT A SCHEMA
----------------------------------------
A pool is any folder under the subject's root. `pool_folder` *ensures* rather
than asserts — a subject is created holding nothing, and a folder appears the
first time something is filed into it. `require_pool` is the read-side twin
and refuses rather than creates, because a listing must not leave an empty
folder behind where a typo was.
"""
from __future__ import annotations

import dataclasses
import difflib
import json
import mimetypes
import os
import pathlib
import sys
from pathlib import Path

import click
import yaml

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die

#: What a selection asks for when nobody names a tag. The API's default too —
#: spelled here so the message a person reads names the tag they would type.
DEFAULT_TAG = "default"

#: The pool a subject's identity images conventionally live in. A convention
#: only, and a weak one: the tag is what makes an image identity, so one filed
#: anywhere under the subject counts. `add-to` refuses it on the way IN so
#: that filing a picture there is not mistaken for making it identity.
IDENTITY_POOL = "reference"

#: The one bible key that lives on the record rather than inside `profile`.
PROMOTED = ("name",)

#: Keys an old character document may still carry from the reference-index
#: era. Warned about, not refused, so an old file is still editable into a
#: new one.
STALE_KEYS = ("references", "default_set")

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}


@dataclasses.dataclass
class Subject:
    """Everything that differs between `studio character` and `studio location`.

    `segment` is the API's plural (`characters`); `id_prefix` what an id of
    this kind starts with (`char-`), which is how `resolve` tells an id from a
    name without a round trip; `cli` the command group's name, so a message
    can say which command to type next. `template` is the yaml the bible is
    seeded from and `profile_keys` the document keys that yaml has — the
    schema `check_profile` holds a pushed file to. `local_dir` is where `edit`
    keeps its working copies. `group_example` is the group tag a hint names
    (`face`; `wide`), and `pools` the conventional folder names `create`
    prints back as a suggestion.

    Not frozen, deliberately: `local_dir` is the seam a test points at a
    temporary directory.
    """
    kind: str
    segment: str
    id_prefix: str
    cli: str
    template: str
    local_dir: str
    profile_keys: tuple
    group_example: str
    pools: tuple
    next_step: str


# ── the record ────────────────────────────────────────────────────────────


def resolve(subject: Subject, name: str) -> dict:
    """An id, or a name matched client-side -> the record.

    **An id is one call; a name is two.** A name is a free-text label: it
    identifies nothing, two subjects may share one, and the API will not
    resolve it — so this lists and matches, and refuses an ambiguous name with
    the ids rather than picking one.

    Raises `api.NotFound` rather than dying, because every caller has a better
    message than this one does: `list` for a person, `RefError` for the engine.
    """
    if name and name.startswith(subject.id_prefix):
        return entities.get_subject(subject.segment, name)
    try:
        found = P.by_name(entities.list_subjects(subject.segment), name, subject.kind)
    except P.PathError as exc:
        raise api.NotFound(str(exc), 404) from exc
    return entities.get_subject(subject.segment, found["id"])


def require(subject: Subject, name: str) -> dict:
    """The record, or a message naming the command that lists the real options."""
    try:
        return resolve(subject, name)
    except api.NotFound:
        die(f"no {subject.kind} {name!r} (see `studio {subject.cli} list`)")


def images(subject: Subject, record: dict, tags: list[str] | None = None) -> list[dict]:
    """Every image under the subject, with the tags that say what each is for."""
    return entities.subject_images(subject.segment, record["id"], tags=tags)


# ── the pools ─────────────────────────────────────────────────────────────


def pool_folder(record: dict, pool: str) -> dict:
    """The node of one pool folder, created if it is not there.

    **Ensuring, not asserting.** The pools are a starting layout; a route or a
    command that cannot find its conventional folder is entitled to make one
    and never to guess, because nothing structural hangs off the folder.
    Deleting `archive/` and then archiving something is a folder appearing, not
    an error.
    """
    return store.ensure_child_folder(record["root"], pool)


def pool_names(record: dict) -> list[str]:
    """The folder names under the subject's root — the pools it actually has."""
    return sorted(n["name"] for n in store.children_of(record["root"])
                  if n.get("kind") == "folder")


def require_pool(record: dict, pool: str) -> dict:
    """The node of one pool folder, or a refusal naming the pools that exist.

    The read-side twin of `pool_folder`. A command that only LISTS a pool
    must not make one: a pool is any folder name now, so `pool <name> sede`
    would otherwise leave an empty `sede/` behind where the `click.Choice`
    used to catch the typo.
    """
    found = store.child(record["root"], pool)
    if found is None or found.get("kind") != "folder":
        have = pool_names(record)
        die(f"{record['name']} has no pool {pool!r} "
            f"(has: {', '.join(f'{n}/' for n in have) or 'no folders'})")
    return found


def pool_nodes(record: dict, pool: str, group: str | None = None) -> list[dict]:
    """The file nodes in a pool, natural-sorted, optionally one level deeper.

    `group` reaches a subfolder of the pool — `reference/face/` — and exists for
    `curate`, which still works a folder at a time because deduplicating means
    reading bytes and reading a whole subtree's worth is what it is trying to
    avoid.
    """
    folder = pool_folder(record, pool)
    if group:
        folder = store.ensure_child_folder(folder["id"], group)
    return store.files_of(folder["id"])


def pool_tree_nodes(record: dict, pool: str) -> list[dict]:
    """Every file node in a pool INCLUDING its subfolders, each carrying a `path`.

    A pool is a tree the moment anyone files it — `seed/original/`,
    `seed/restored/` — and a listing of the root then answers with only what
    was never filed. A caller CHOOSING identity out of a pool wants the tree;
    `curate`, which reads bytes a folder at a time, wants `pool_nodes`.
    """
    return store.walk_files_of(pool_folder(record, pool)["id"])


def upload_file(parent_id: str, local: str, name: str | None = None,
                content_type: str | None = None) -> dict:
    """Upload one local file INTO a folder node, and return the node it made.

    Takes an id, not a name path, and keeps the basename: renaming an arriving
    file would throw away the only thing its name records, and ordering is a
    row attribute.
    """
    source = Path(local)
    filename = name or source.name
    ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return store.upload_into(parent_id, filename, source, content_type=ct)


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ── the bible ─────────────────────────────────────────────────────────────


def parse_profile(text: str, where: str) -> dict:
    """Parse a bible, or die with the YAML error and where it came from."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        die(f"{where} is not valid YAML:\n  {exc}")
    if not isinstance(data, dict):
        die(f"{where} must be a YAML mapping (got {type(data).__name__}).")
    return data


def check_profile(subject: Subject, data: dict, where: str, name: str | None = None) -> None:
    """Refuse a bible that has drifted off the shared schema.

    `references:` and `default_set:` are rows now, so a bible carrying them is
    warned about rather than refused: an old document should still be editable
    into a new one, and the warning is what says the keys will be ignored.
    """
    missing = [k for k in subject.profile_keys if k not in data]
    if missing:
        die(
            f"{where} is missing required key(s): {', '.join(missing)}\n"
            f"  every {subject.kind} carries the same schema — see "
            f"templates/{os.path.basename(subject.template)}."
        )
    stale = [k for k in STALE_KEYS if k in data]
    if stale:
        print(
            f"warning: {where} still carries {', '.join(stale)}; both are rows now and "
            f"this copy is ignored. Tag the images instead: studio describe <node> --tag "
            f"{DEFAULT_TAG}.",
            file=sys.stderr,
        )
    extra = [k for k in data if k not in subject.profile_keys and k not in STALE_KEYS]
    if extra:
        print(
            f"warning: {where} has key(s) outside the schema: {', '.join(extra)}",
            file=sys.stderr,
        )
    if name and data.get("name") != name:
        die(f"{where} declares name: {data.get('name')!r}, but this is {subject.kind} {name!r}.")


def document(record: dict) -> dict:
    """The record as the one map every reader of a bible expects.

    `name` is the record's `name`, the only label it has; every downstream
    reader spells it `name`. See the module docstring.
    """
    profile = dict(record.get("profile") or {})
    merged = {"name": record["name"]}
    merged.update(profile)
    return merged


def load_profile(subject: Subject, name: str) -> dict:
    """The bible of one subject, as one map. **The reader every engine uses.**

    Returns the record's `profile` with `name` merged back in — see the module
    docstring for why it is a field and why it is put back here. One API call;
    there is no document to fetch and no YAML to parse.
    """
    try:
        return document(resolve(subject, name))
    except api.NotFound:
        die(f"no {subject.kind} {name!r} (see `studio {subject.cli} list`).")


def split_document(data: dict) -> dict:
    """A document -> the `profile` map.

    The inverse of `document`. `name` is dropped rather than written: a rename
    is `PATCH /api/<segment>/<id>`, so a bible that disagrees with the record
    cannot rename anything and must not look as though it could.
    """
    return {k: v for k, v in data.items()
            if k not in PROMOTED and k not in STALE_KEYS}


def save_profile(subject: Subject, record: dict, data: dict, rev: int | None = None) -> dict:
    """Write a document back. **One compare-and-swap, not a check then a write.**

    `rev` is the revision the caller last saw — the sidecar's for `edit --push`,
    the record's own for an explicit file. The API refuses a stale one, which is
    the whole of the conflict story; nothing here re-reads and compares.
    """
    try:
        return entities.put_subject_profile(subject.segment, record["id"], split_document(data),
                                            record["rev"] if rev is None else rev)
    except api.Conflict as exc:
        die(f"{exc}\n       {record['name']}'s bible was written by someone else since "
            "you read it — re-run `edit` to pick it up rather than overwriting.")


def remote_rev(subject: Subject, name: str) -> int | None:
    """The record's current `rev`, or None if there is no such subject.

    **Only a 404 is None.** Its ancestor caught every exception, which made a
    refusal indistinguishable from a missing bible — and a missing version
    disabled the conflict check, so a 403 turned the guard off rather than
    reporting it.
    """
    try:
        return int(resolve(subject, name)["rev"])
    except api.NotFound:
        return None


# ── the local round trip (`edit`) ─────────────────────────────────────────
#
# Three files per subject under `local_dir` (all git-ignored):
#   <name>.yaml         the working copy you edit
#   .<name>.base.yaml   pristine copy as pulled — used to detect your edits + diff
#   .<name>.rev         the record's `rev` at pull time — sent back as the CAS
#                       value, so a push of a stale copy is refused by the API
#                       rather than compared here.


def local_paths(subject: Subject, name: str,
                override: str | None = None) -> tuple[str, str, str]:
    """(working copy, base copy, rev file) for a subject."""
    path = (os.path.abspath(override) if override
            else os.path.join(subject.local_dir, f"{name}.yaml"))
    d, stem = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
    return path, os.path.join(d, f".{stem}.base.yaml"), os.path.join(d, f".{stem}.rev")


def fetch_profile(subject: Subject, name: str) -> tuple[str, str]:
    """(the bible as YAML text, the `rev` it was read at).

    **One call, and the two cannot disagree.** The record carries both, so the
    ordering problem two reads would have does not exist.
    """
    record = require(subject, name)
    text = yaml.safe_dump(document(record), sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=100)
    return text, str(record["rev"])


def unified(before: str, after: str, name: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{name} (stored bible)",
            tofile=f"local/{name}.yaml",
        )
    )


def do_pull(subject: Subject, name: str, force: bool, local: str, base: str, revf: str) -> None:
    text, rev = fetch_profile(subject, name)
    if os.path.exists(local) and not force:
        current = read_text(local)
        prior = read_text(base) if os.path.exists(base) else None
        if current != (prior if prior is not None else text):
            die(
                f"local copy has unsaved edits: {local}\n"
                "  push them first (re-run without --pull), or discard them with --discard."
            )
    write_text(local, text)
    write_text(base, text)
    write_text(revf, rev)
    print(local)  # stdout: pipeable, e.g. `code "$(... edit <name>)"`
    print(
        f"wrote {local} (rev {rev})\n"
        f"  edit the file above, then: studio {subject.cli} set-profile {name}",
        file=sys.stderr,
    )


def do_push(subject: Subject, name: str, force: bool, local: str, base: str, revf: str) -> None:
    if not os.path.isfile(local):
        die(f"no local copy at {local} — run `edit {name}` first to pull it.")
    text = read_text(local)
    prior = read_text(base) if os.path.exists(base) else None

    if prior is None and not force:
        die(
            f"no pull record for {local} (missing {os.path.basename(base)}), so the revision\n"
            "  it was taken at is unknown. Re-run with --force to write at the current one."
        )
    if prior is not None and text == prior:
        print(f"no local changes in {local} — nothing to upload.", file=sys.stderr)
        return

    # A bible that no longer parses, or has lost a schema key, is worse than no
    # write at all — every downstream reader breaks on it. Check before the write.
    data = parse_profile(text, local)
    check_profile(subject, data, local, name)

    record = require(subject, name)
    recorded = read_text(revf).strip() if os.path.exists(revf) else ""
    # The recorded rev is the point of the sidecar: sending it makes the API
    # refuse a push built on a copy someone else has since written over. `--force`
    # sends the record's own rev instead, which always succeeds.
    rev = record["rev"] if (force or not recorded) else int(recorded)

    if prior is not None:
        sys.stderr.write(unified(prior, text, name))
    after = save_profile(subject, record, data, rev)
    write_text(base, text)
    write_text(revf, str(after["rev"]))
    print(f"profile updated (rev {rev} → {after['rev']})", file=sys.stderr)


# ── the selection ─────────────────────────────────────────────────────────


def selection_nodes(subject: Subject, record, pick: list[str] | None = None,
                    tags: list[str] | None = None, slots: list[int] | None = None,
                    limit: int | None = None) -> list[dict]:
    """The ordered entries a model would actually be shown.

    **The resolution is the API's.** `?pick=` names images, `?tag=` names tags,
    and neither means `default` — with the cap enforced server-side, so an
    over-cap selection comes back as `api.Conflict` rather than silently
    truncated. The caller catches that; nothing here converts it.

    `slots` is applied HERE and only here: it is 1-based positional picking
    *within* the resolved selection ("send the 1st and 3rd of what you would
    have sent"), which is arithmetic on an answer rather than a question about
    the subject. Sending it to the API would make the route's own `slot`
    numbering mean two things.
    """
    if not isinstance(record, dict):
        record = resolve(subject, record)
    found = entities.subject_selection(subject.segment, record["id"], pick=pick,
                                       tag=tags, limit=limit)
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


# ── the commands ──────────────────────────────────────────────────────────


def commands(subject: Subject) -> dict[str, click.Command]:
    """The twelve commands of `studio <cli>`, bound to one subject.

    Built per subject rather than declared with a decorator each, because the
    two groups are the same commands: a `list` that queries one index, a
    `create` that seeds from one template, an `edit` that round-trips one
    bible. What the two groups say differs by the noun and nothing else.
    """
    kind, cli = subject.kind, subject.cli

    @click.command("list")
    @click.option("--json", "json_", is_flag=True)
    def cmd_list(json_):
        """Every one in the library. **One query.**"""
        found = entities.list_subjects(subject.segment)
        if json_:
            print(json.dumps(found, indent=2))
        elif found:
            for record in found:
                counts = record.get("counts") or {}
                print(f"{record['name']:<20} "
                      f"sent {counts.get('default', 0):<5} files {counts.get('files', 0):<5} "
                      f"updated {str(record.get('updated', ''))[:10]}")
        else:
            print(f"(no {subject.segment} yet — create one with "
                  f"`studio {cli} create <name>`)", file=sys.stderr)

    @click.command("show")
    @click.argument("name", required=True)
    @click.option("--json", "json_", is_flag=True)
    @click.option("--profile", "profile_", is_flag=True, help="Print the bible as YAML.")
    def cmd_show(name, json_, profile_):
        """The record: its id, its counts and the folders it actually has.

        The folder list is read off the root's children rather than printed
        from the conventional pool names, because those are a starting layout
        and a person may have renamed, deleted or added to them.
        """
        record = require(subject, name)
        if profile_:
            sys.stdout.write(yaml.safe_dump(document(record), sort_keys=False,
                                            allow_unicode=True, width=100))
            return
        if json_:
            print(json.dumps(record, indent=2))
            return
        found = images(subject, record)
        counts: dict[str, int] = {}
        for entry in found:
            for tag in entry.get("tags") or []:
                counts[tag] = counts.get(tag, 0) + 1
        folders = [f"{n['name']}/" for n in store.children_of(record["root"])
                   if n.get("kind") == "folder"]
        print(f"{record['name']}  ({record['id']})  rev {record.get('rev')}")
        print(f"  images    {len(found)}"
              f"      sent by default: {counts.get(DEFAULT_TAG, 0)}")
        print(f"  tags      {' · '.join(f'{t} {n}' for t, n in sorted(counts.items())) or '—'}")
        print(f"  root      {record['root']}   {' '.join(folders) or '(no folders)'}")

    @click.command("create")
    @click.argument("name", required=True)
    @click.option("--from-profile", help="Local profile.yaml to seed with (default: blank template).")
    def cmd_create(name, from_profile):
        """Create one: the record, its library index row and its root.

        **One transaction, and no starting pools.** Either the whole record
        exists or none of it does; the first write that needs a pool makes it,
        and the printed names are a suggestion, not a promise that they exist.
        """
        src = from_profile or subject.template
        if not os.path.isfile(src):
            die(f"profile source not found: {src}")
        data = parse_profile(read_text(src), src)
        if src != subject.template:  # the template is deliberately unfilled
            check_profile(subject, data, src, name)

        # **No conflict to catch.** A name is a label and two may share one.
        record = entities.create_subject(subject.segment, name, profile=split_document(data))
        made = [f"{n['name']}/" for n in store.children_of(record["root"])
                if n.get("kind") == "folder"]
        print(f"created {kind} {record['name']}  ({record['id']})")
        print("  " + "  ".join(made or [f"{p}/" for p in subject.pools]))
        if src == subject.template:
            print("  (blank template — fill it in with `edit`, then `set-profile`.)",
                  file=sys.stderr)
        print(f"  next: {subject.next_step.format(name=name)}", file=sys.stderr)
        return 0

    @click.command("delete")
    @click.argument("name", required=True)
    @click.option("--files", type=click.Choice(["keep", "delete"]), default="keep",
                  help=f"What to do with the {kind}'s folder (default: keep it).")
    @click.option("--force", is_flag=True,
                  help="Delete even while projects or runs still name it.")
    def cmd_delete(name, files, force):
        """Delete one.

        **`--files keep` is the default deliberately.** The reverse default
        loses a library to a typo, and an orphaned folder in the library root
        is visible and recoverable; nothing this service does to S3 is undoable.

        **The refusal is the interesting half.** A project or a run that names
        this subject holds a link row, and those rows are what make "every run
        of this subject" answerable. But a run is HISTORY: it really did use
        this subject, and deleting the subject is not a reason to delete the
        work. So `--force` drops the links and leaves the runs.
        """
        record = require(subject, name)
        try:
            entities.delete_subject(subject.segment, record["id"], files=files, force=force)
        except api.Conflict as exc:
            die(f"{exc}\n       pass --force to drop those links and delete it anyway")
        print(f"deleted {kind} {record['name']} (files: {files})")

    @click.command("rename")
    @click.argument("name", required=True)
    @click.argument("new", required=True)
    def cmd_rename(name, new):
        """Give it a new name. **ONE conditional write.**

        A record names a **node id**, and a node id survives a rename by
        construction — so no object is copied and no record is rewritten.
        """
        record = require(subject, name)
        try:
            after = entities.patch_subject(subject.segment, record["id"], record["rev"], name=new)
        except api.Conflict as exc:
            die(str(exc))
        count = len(images(subject, record))
        print(f"renamed {record['name']} → {after['name']}")
        print(f"  0 objects copied · 0 records rewritten · {count} image(s) untouched")

    @click.command("textblock")
    @click.argument("name", required=True)
    def cmd_textblock(name):
        """A pasteable identity paragraph, for engines driven from a start frame.

        `GET /api/<segment>/<id>/textblock` answers with the authored block
        when the bible has one, and with the identity-bearing sections as raw
        material when it does not — the API decides which, so the CLI and the
        SPA cannot paste different paragraphs into the same model.
        """
        record = require(subject, name)
        found = entities.subject_textblock(subject.segment, record["id"])
        authored = (found.get("text") or "").strip()
        # No `<`-check here: the route empties an unfilled `<>` before it
        # answers, so the branch is `text` or nothing.
        if authored:
            print(authored)
            print(f"\n(authored block from {record['name']}'s bible)", file=sys.stderr)
            return

        sys.stdout.write(yaml.safe_dump(found.get("raw") or {}, sort_keys=False,
                                        allow_unicode=True, width=88))
        print(
            f"\nNo authored `text_identity_block` in {record['name']}'s bible — the above "
            "is raw material.\nCompress it into ONE paragraph of ~50-70 words covering only "
            "what a text-only engine\ncannot infer. Then save it back into the bible under "
            f"`text_identity_block:`\n(`studio {cli} edit {record['name']}`) so it is "
            "written once and reused.\n"
            "\nNOTE: with a start frame supplied, keep the pasted block SHORT — the frame "
            "carries\nappearance better than prose, and a long block fights it.",
            file=sys.stderr,
        )

    @click.command("set-profile")
    @click.argument("name", required=True)
    @click.argument("file", required=False)
    def cmd_set_profile(name, file):
        """Replace the bible. With no FILE, pushes the local working copy.

        FILE omitted is the `edit` round trip's second half and uses the `rev`
        recorded at pull time, so a stale copy is refused; FILE given is an
        assertion and uses the record's current `rev`, which the API still
        compare-and-swaps against.
        """
        record = require(subject, name)
        if file is None:
            local, base, revf = local_paths(subject, record["name"])
            do_push(subject, record["name"], False, local, base, revf)
            return
        if not os.path.isfile(file):
            die(f"profile file not found: {file}")
        data = parse_profile(read_text(file), file)
        check_profile(subject, data, file, record["name"])
        after = save_profile(subject, record, data)
        print(f"profile updated (rev {record['rev']} → {after['rev']})", file=sys.stderr)

    @click.command("edit")
    @click.argument("name", required=True)
    @click.option("--diff", is_flag=True, help="Show local-vs-stored differences and exit.")
    @click.option("--discard", is_flag=True, help="Throw away local edits and re-pull.")
    @click.option("--force", is_flag=True,
                  help="Proceed despite unsaved edits or a changed record.")
    # **Relative, not the absolute dir.** Interpolating the absolute path put
    # the author's home directory into the help string, and from there into
    # `cli_surface_reference.json` — a contract that then only matched on the
    # machine it was captured on.
    @click.option("--path",
                  help=f"Working-copy path (default: studio/local/{subject.segment}/<name>.yaml).")
    @click.option("--pull", is_flag=True, help="Force the download direction.")
    @click.option("--push", is_flag=True, help="Force the upload direction.")
    def cmd_edit(name, diff, discard, force, path, pull, push):
        """Round-trip the bible through a local YAML working copy.

        The document is assembled from the record, not downloaded, and pushed
        back as `PATCH …/profile {profile, rev}`.
        """
        local, base, revf = local_paths(subject, name, path)

        if discard:
            do_pull(subject, name, True, local, base, revf)
            return

        if diff:
            if not os.path.isfile(local):
                die(f"no local copy at {local} — run `edit {name}` first to pull it.")
            remote, _rev = fetch_profile(subject, name)
            text = unified(remote, read_text(local), name)
            sys.stdout.write(text)
            if not text:
                print(f"{local} matches the stored bible.", file=sys.stderr)
            return

        # Direction: explicit flags win; otherwise pull when there is no working
        # copy yet, push once there is one. That makes the flow "run, edit, run
        # again".
        if pull:
            do_pull(subject, name, force, local, base, revf)
        elif push or os.path.isfile(local):
            do_push(subject, name, force, local, base, revf)
        else:
            do_pull(subject, name, force, local, base, revf)

    @click.command("images")
    @click.argument("name", required=True)
    @click.option("--json", "json_", is_flag=True)
    @click.option("--tag", "tags", help="Comma-separated; an image must carry ALL of them.")
    def cmd_images(name, json_, tags):
        """Every image under it, with the tags that decide what each is for.

        Every image under the subject is here, wherever it sits; the tags say
        which are identity. A picture dropped into the tree by hand is listed
        the same as one filed by a command.
        """
        record = require(subject, name)
        found = images(subject, record, tags=_split(tags))
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
              f"generation is shown.\nTag one: studio describe <node> --tag {DEFAULT_TAG} "
              f"--tag {subject.group_example}",
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

        With no `--tag` and no `--pick` this is the `default` images. Slot N
        is position N in THIS list. The same route the SPA calls, so the two
        cannot disagree about what a generation saw.
        """
        record = require(subject, name)
        try:
            chosen = selection_nodes(subject, record, _split(pick), _split(tags),
                                     [int(x) for x in _split(slots) or []] or None, limit)
        except api.Conflict as exc:
            die(f"{exc}\n       a {kind} is a library, not a set to send whole. Narrow it "
                f"with --pick / --tag, or take `{DEFAULT_TAG}` off the ones you do not "
                f"want sent:\n       studio describe <node> --tag {subject.group_example}")
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

    @click.command("add-to")
    @click.argument("name", required=True)
    @click.argument("pool", required=True)
    @click.argument("files", nargs=-1, required=True)
    def cmd_add_to_pool(name, pool, files):
        """Add file(s) to a pool — any folder name; basenames kept as they are.

        The pool is created under the root if it is not there. Nothing here
        tags an image, which is the point of the pools being separate:
        material about a subject is not a statement about what it is.
        Promoting one of these into identity is a tag (hard rule #2b), and
        `reference/` is refused here for exactly that reason.
        """
        if pool.strip("/") == IDENTITY_POOL:
            die(f"refusing to add to {IDENTITY_POOL}/: a file there is not identity, a tag "
                f"is. Upload it anywhere, then: studio describe <node> --tag {DEFAULT_TAG} "
                "(hard rule #2b).")
        record = require(subject, name)
        missing = [f for f in files if not os.path.isfile(f)]
        if missing:
            die(f"file(s) not found: {', '.join(missing)}")
        folder = pool_folder(record, pool)
        for local in files:
            node = upload_file(folder["id"], local)
            print(f"  {node['id']}  {node['name']}", file=sys.stderr)
        print(f"added {len(files)} file(s) to {record['name']}/{pool}/", file=sys.stderr)

    @click.command("pool")
    @click.argument("name", required=True)
    @click.argument("pool", required=True)
    @click.option("--group", default=None,
                  help="A subfolder of the pool (e.g. seed/current, reference/face).")
    @click.option("--json", "json_", is_flag=True)
    @click.option("--presign", is_flag=True)
    @click.option("--unreferenced", is_flag=True,
                  help="Only files not tagged `default` — what is sitting in a folder without being identity.")
    def cmd_pool(name, pool, group, json_, presign, unreferenced):
        """List what is actually IN a pool folder.

        POOL is any folder name under the root — `show <name>` prints the ones
        it has. `--group` reaches one level down, because a pool is a tree.
        `--unreferenced` is the question that finds files nothing sends.
        """
        record = require(subject, name)
        require_pool(record, pool)  # a listing makes nothing; a typo is a refusal
        entries = pool_nodes(record, pool, group)
        if unreferenced:
            named = {entry["id"] for entry in images(subject, record, tags=[DEFAULT_TAG])}
            entries = [e for e in entries if e["id"] not in named]
        where = f"{pool}/{group}" if group else f"{pool}/"
        if not entries:
            which = "unreferenced files" if unreferenced else "nothing"
            print(f"({record['name']} has {which} in {where})", file=sys.stderr)
            return
        if presign:
            urls = [store.presign_node(entry["id"]) for entry in entries]
            print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
        elif json_:
            print(json.dumps(entries, indent=2))
        else:
            for entry in entries:
                print(f"{entry['id']}  {entry['name']}")
        if pool == "archive":
            print("note: archive/ is retired material — do not feed it to a model unless "
                  "the user asked for these specifically.", file=sys.stderr)

    return {
        "list": cmd_list, "show": cmd_show, "create": cmd_create, "edit": cmd_edit,
        "set-profile": cmd_set_profile, "delete": cmd_delete, "rename": cmd_rename,
        "textblock": cmd_textblock, "images": cmd_images, "selection": cmd_selection,
        "add-to": cmd_add_to_pool, "pool": cmd_pool,
    }


def group(subject: Subject, help_text: str) -> click.Group:
    """`studio <cli>` — the command group, every command attached in one order."""
    main = click.group(help=help_text)(lambda: None)
    for name, command in commands(subject).items():
        main.add_command(command, name)
    return main
