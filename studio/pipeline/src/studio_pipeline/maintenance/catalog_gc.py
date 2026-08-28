"""`studio catalog gc` — delete the blobs no node references.

A node and its bytes are written apart. The API signs an upload before the
confirm that records it, and `delete_node` removes rows and hands the caller the
keys to delete afterwards — so an interruption on either side leaves an object in
the bucket nothing can reach. This command finds those and, on `--apply`, removes
them.

**THE ONLY THING THAT MAKES A BLOB GARBAGE IS THAT NO ROW NAMES IT.** Never the
shape of its key. Prod holds `characters/<slug>/…` and `projects/<slug>/…` keys
written years before the table existed alongside the `blobs/<node_id>` keys
written after it, and a row may name either — `services/catalog.py` keeps
`blob_key` opaque for exactly this reason. A test on the prefix would collect
half the library.

WHAT MAY BE COLLECTED IS AN ALLOWLIST
-------------------------------------
`COLLECTABLE_PREFIXES` names the three prefixes a blob has ever been written
under. Everything else is left alone, referenced or not, and the list has to fail
in that direction: `config/` and `phrasebook/` are shared material that sits
outside the catalog deliberately (`catalog_seed.py` records no node for either),
so no row will ever name one and a denylist would hold only until someone adds a
fourth kind of shared material. `config/pose/` holds the framing plates a
turnaround binds — collecting those is the most expensive mistake available
here.

Empty-folder markers are never collected either. They carry no bytes, no row
names one, and deleting one destroys the only evidence that an empty folder
exists.

TWO INVOCATIONS, AND THE FIRST IS NOT ADVISORY
----------------------------------------------
`--apply` deletes only keys a previous dry run wrote into the same journal. The
orphan set is re-derived from a fresh scan and a fresh listing — the bucket moves
under you — and then intersected with what was journalled, so anything orphaned
*after* a person read the report is reported and left alone. That is why the
journal carries the whole list rather than a sample, unlike `catalog_seed.py`'s
plan: there the list is re-derivable, here it is the input.

A delete is a tombstone. The bucket is versioned and nothing here is granted
`s3:DeleteObjectVersion`, so the bytes survive — but a tombstone still hides
media from the app until someone restores it by hand, which is not the same as
undoing a mistake.
"""
from __future__ import annotations

import click

from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die
from studio_pipeline.maintenance.journal import (
    journal_path,
    load_journal,
    save_journal,
)

#: Prefixes that belong to nobody and must never be proposed for deletion.
#:
#: `config/` comes from `paths.py`, which still names it — the pose plates.
#:
#: **`phrasebook/` was here and is gone**, and dropping it changes a LABEL and
#: not a safety property. Collection is the `COLLECTABLE_PREFIXES` allowlist
#: below, so a `phrasebook/` object was never collectable by either list; this
#: one only decides whether an uncollectable key is reported as `shared`
#: (outside the catalog on purpose) or `outside` (unrecognised, look at it).
#:
#: It was carried as a literal after the phrasebook became `TERM#` rows, while
#: buckets written before that change still held `phrasebook/wording.yaml`.
#: Prod was the only one, its 16 entries are rows now, and the object is
#: deleted. Calling a leftover document "outside the catalog by design" is the
#: part that has stopped being true — it is a leftover, and `outside` is the
#: bucket that says so to whoever runs this next.
SHARED_PREFIXES = (P.CONFIG + "/",)

# The allowlist. `blobs/` is what `services/catalog.py::blob_key_for` writes;
# the other two are the trees `paths.py` built before the table existed and that
# rows still name. Spelled out rather than imported from `paths.py` because this
# is a statement about what may be DELETED, and it must not silently widen the
# day a new tree is added there.
#
# This used to add that a non-empty `STUDIO_S3_PREFIX` would put every key
# outside the list, so nothing would be collected. That variable is gone —
# nothing in the package reads a bucket prefix any more — so the caveat is
# dropped rather than kept as a warning about a knob that does not exist. The
# listing below is still of the raw bucket, which is the part that mattered.
#
# `libraries/` joined the list with the entity model, which also changed what
# the other three MEAN. `characters/` and `projects/` used to be name paths —
# `characters/<slug>/reference/face/<file>.png` — and are now id-prefixed blob
# keys: `characters/<char id>/<node id>.png`. Both shapes are live in prod at
# once, which is exactly why this list is about the first segment and nothing
# further: a rule that parsed the second segment would have to know which era a
# key came from, and `services/catalog.py` is the only module allowed to touch a
# `blob_key` at all.
#
# `blobs/` is now legacy — it is what the API wrote before keys carried an
# owner — and it stays, because prod holds thousands and a row still names each
# one.
COLLECTABLE_PREFIXES = ("blobs/", "characters/", "libraries/", "projects/")

# `DeleteObjects` takes a thousand keys and no more.
BATCH = 1000

# Enough of the list to judge it by; the journal holds all of it.
SHOWN = 20


def referenced_keys(ddb) -> set[str]:
    """Every `blob_key` any row names, table-wide.

    Not filtered by library and not filtered by `sk`. A reference from a library
    this command was not thinking about is still a reference, and a `blob_key`
    on an item the schema does not put one on is a reason to keep the object
    rather than a reason to ignore it — every ambiguity here resolves towards
    not deleting.

    A scan rather than an index query, for the reason `catalog_check.verify`
    scans: a GSI drops any row missing one of its key attributes, and a dropped
    row reads here as "nothing references this". That got sharper with the
    sparse `by-recent` key — an index a row is deliberately absent from is now
    an ordinary thing rather than a corruption, so "query the index" would
    quietly skip every folder and every document.
    """
    return {item["blob_key"] for item in ddbc.scan(ddb) if item.get("blob_key")}


def survey(s3, referenced: set[str]) -> dict:
    """Every object in the bucket, sorted into exactly one bucket of reasons."""
    found = {"orphans": [], "referenced": [], "shared": [], "outside": [],
             "markers": [], "sizes": {}}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3c.bucket()):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            found["sizes"][key] = obj.get("Size", 0)
            if key.endswith("/"):
                found["markers"].append(key)
            elif not key.startswith(COLLECTABLE_PREFIXES):
                # The allowlist is tested BEFORE the reference test, on purpose.
                # Whatever else is true of a key, a key outside these prefixes
                # cannot reach the delete list by any path through this function
                # — which is the property worth being able to read off the code.
                # The split below only makes the report say which kind it is.
                (found["shared"] if key.startswith(SHARED_PREFIXES)
                 else found["outside"]).append(key)
            elif key in referenced:
                found["referenced"].append(key)
            else:
                found["orphans"].append(key)
    for reason in ("orphans", "referenced", "shared", "outside", "markers"):
        found[reason].sort()
    return found


def orphan_bytes(found: dict) -> int:
    return sum(found["sizes"][key] for key in found["orphans"])


def report(found: dict) -> None:
    print(f"{'referenced':<12} {len(found['referenced']):>6}  a row names this key")
    print(f"{'shared':<12} {len(found['shared']):>6}  "
          f"{' + '.join(SHARED_PREFIXES)} — outside the catalog by design")
    print(f"{'outside':<12} {len(found['outside']):>6}  under none of "
          f"{', '.join(COLLECTABLE_PREFIXES)} — never collected")
    print(f"{'markers':<12} {len(found['markers']):>6}  empty-folder markers")
    print(f"{'ORPHANS':<12} {len(found['orphans']):>6}  "
          f"{orphan_bytes(found):,} bytes, referenced by nothing")
    for key in found["orphans"][:SHOWN]:
        print(f"             {key}")
    if len(found["orphans"]) > SHOWN:
        print(f"             … and {len(found['orphans']) - SHOWN} more")


def collect(s3, keys: list[str]) -> dict:
    """Delete the keys in `DeleteObjects` batches. No `VersionId`, ever.

    Naming a version is what turns a recoverable tombstone into a permanent
    removal. The grant is not held, so it would fail rather than destroy
    anything — but the protection is a grant somebody could one day "tidy up",
    and this is the call that would quietly start meaning something else.
    """
    deleted, failed = [], []
    for start in range(0, len(keys), BATCH):
        answer = s3.delete_objects(
            Bucket=s3c.bucket(),
            Delete={"Objects": [{"Key": key} for key in keys[start:start + BATCH]]},
        )
        deleted += [entry["Key"] for entry in answer.get("Deleted", [])]
        failed += [f"{entry['Key']}: {entry.get('Message') or entry.get('Code')}"
                   for entry in answer.get("Errors", [])]
    return {"deleted": sorted(deleted), "failed": failed}


@click.command("gc", help=__doc__,
               short_help="delete blobs no node references (dry run by default)")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def cmd_gc(apply, journal):
    """List the blobs nothing references; remove them with `--apply`."""
    ddb = ddbc.client()
    if not ddbc.table_exists(ddb):
        die(f"no table '{ddbc.table()}' — the references live in it. Apply the "
            "infra first, or set STUDIO_CATALOG_TABLE.")

    referenced = referenced_keys(ddb)
    # The guard that matters most, and the cheapest. An empty or wrong table
    # names no blob, which would make every object in the bucket look like
    # garbage — the one input that turns this command into a bucket wipe.
    if not referenced:
        die(f"no row in '{ddbc.table()}' names a blob. An unseeded or wrong table "
            "makes every object look unreferenced, so this refuses rather than "
            "proposing the whole bucket. Run `studio catalog seed`, or check "
            "STUDIO_CATALOG_TABLE.")

    s3 = s3c.client()
    found = survey(s3, referenced)
    print(f"[{'APPLY' if apply else 'dry run'}] bucket {s3c.bucket()}, "
          f"table {ddbc.table()}, {len(referenced)} referenced key(s)\n")
    report(found)

    jpath = journal_path(journal)
    doc = load_journal(jpath)

    if not apply:
        doc["gc"] = {"bucket": s3c.bucket(), "table": ddbc.table(),
                     "referenced": len(referenced), "bytes": orphan_bytes(found),
                     "orphans": found["orphans"]}
        save_journal(jpath, doc)
        print("\nnothing deleted. `--apply` removes exactly what is listed above.")
        print(f"journal: {jpath}")
        return

    confirmed = set(doc.get("gc", {}).get("orphans") or [])
    if not confirmed:
        die(f"{jpath} records no dry run. `--apply` deletes only what a dry run "
            "listed, so run `studio catalog gc` first and read what it found.")

    current = set(found["orphans"])
    doomed = [key for key in found["orphans"] if key in confirmed]
    unconfirmed = [key for key in found["orphans"] if key not in confirmed]
    # Journalled, and no longer an orphan: already deleted, or something gave it
    # a row since. Either way it is not this run's to remove.
    withdrawn = sorted(key for key in confirmed if key not in current)

    res = collect(s3, doomed)
    print(f"\n{'deleted':<12} {len(res['deleted']):>6}  tombstoned; "
          "the versions remain")
    print(f"{'unconfirmed':<12} {len(unconfirmed):>6}  orphaned since the dry "
          "run — left alone")
    print(f"{'withdrawn':<12} {len(withdrawn):>6}  in the journal, not an orphan now")
    for entry in res["failed"]:
        print(f"FAILED       {entry}")

    doc["gc_applied"] = {"bucket": s3c.bucket(), "table": ddbc.table(),
                         "deleted": res["deleted"], "failed": res["failed"],
                         "unconfirmed": unconfirmed, "withdrawn": withdrawn}
    save_journal(jpath, doc)
    print(f"journal: {jpath}")
    if res["failed"]:
        raise SystemExit(1)
