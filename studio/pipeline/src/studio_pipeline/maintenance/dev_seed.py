"""`studio dev-seed` — promote a fixture out of this machine's dev stack.

The dev fixture is **promoted, not generated**. A human drives the CLI against
their own dev stack as ordinary work; a handful of the nodes that produces
become the fixture every other machine downloads. `publish` reads that stack's
catalog, copies the chosen blobs into the seed bucket, and writes the two
documents `scripts/dev-aws-seed.sh` loads.

    studio dev-seed tree                       what is in this stack, by path
    studio dev-seed publish --path A --path B  a dry run: what would be promoted
    studio dev-seed publish --path A --apply --dev-subjects-only

IT GENERATES NOTHING, SO IT COSTS NOTHING
-----------------------------------------
No model is called, no `REPLICATE_API_TOKEN` is read, and there is no hard-rule-#2
approval gate here — **the approval already happened**, at the moment the human
ran the generations that filled the dev stack. This is a copy. `tests/
test_dev_seed.py` pins that with a test rather than a comment, the way
`test_dev_scripts.py` pins the same property for the loader; read what it does
and does not catch before adding an import here.

THE OTHER HALF OF `dev-aws-seed.sh`
-----------------------------------
That script (#285) shipped first and its header carries "THE CONTRACT WITH
#284", which specifies `catalog.json` and `manifest.json` field by field. Its
author constructed the schema because #284 only sketched it; this module is the
writer that makes the contract two-sided. It is not asserted here in prose — a
test builds a fixture with this module and runs it through the loader's own
`fixture_problems` shell function, so a disagreement is a red test rather than
a bad publish.

    v1/catalog.json    the node tree: path, kind, created_at, source, content_type
    v1/manifest.json   version, object count, total bytes, per-object sha256
    v1/media/<path>    the bytes

Both documents are **authoritative in git** (`studio/fixtures/dev-seed/<v>/`) and
copied into the bucket for the loader. Every name in them is invented, so hard
rule #1 does not force them into S3 — which is also what makes the guard below
load-bearing rather than decorative.

NO IDS ARE PUBLISHED, AND THAT IS THE DESIGN
--------------------------------------------
`catalog_seed.py` derives ids as `uuid5` over `s3://<bucket>/<path>` and
`dev-aws-seed.sh` reimplements that derivation. The bucket name is *in* the
derivation, so two machines derive different ids from the same fixture — which
is correct, they are different libraries. It follows that a fixture must carry
no ids at all: the loader derives them against the machine it is seeding, and an
id written here would be an id from someone else's stack.

So the fixture's only cross-reference is `path`, the slash-joined chain of names
from the library root — the same encoding `catalog_seed.py` uses, and one scheme
rather than two. This module walks `parent_id` to build it, because the API
mints `node-<uuid4>` at random and a dev stack's ids are not derived from
anything.

WHAT IS WORTH PROMOTING
-----------------------
#284 is explicit that a session's output must not be promoted wholesale: a
fixture's job is to exercise the shapes the app cares about, and an exploratory
session will not produce them by accident. Six to eight objects — stills at two
or three aspect ratios, one short video, a run folder with `request.json` and
`result.json`, a folder nested three deep, one deliberately awkward name, and an
empty folder.

(#284 says "a zero-byte folder marker, which is what a folder made in the
console looks like". That predates the catalog. A folder is a row now, not a
marker object, and the loader's contract has no way to express a marker — a
folder node may not carry a `source`. The shape that survives the translation is
a **childless folder node**, which is what the app sees either way, and naming
an empty folder with `--path` promotes exactly that.)

Nothing here picks for you. `--path` is required and repeatable, `--max-objects`
caps what a folder can expand into, and there is no `--all`.

HARD RULE #1 APPLIES TO THE PROMOTION
-------------------------------------
`catalog.json` lands in git, so a name in the dev stack becomes a name in the
repository. That is allowed for a DEV SUBJECT and never for a production
character — the rule is env-scoped (`studio/CLAUDE.md`), and `source()` refuses
a `prod` bucket or table before anything else runs, so a fixture is dev-origin
by construction. What is left for `name_problems` to decide is which dev
subjects this repo publishes, and it reads that off `DEV_SUBJECTS` rather than
off the shape of the name. It is honest about what it still cannot catch.
"""
from __future__ import annotations

import collections
import concurrent.futures
import hashlib
import json
import os
import re
import uuid

import click

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline import profiles
from studio_pipeline.errors import die
from studio_pipeline.domain import paths as P
from studio_pipeline.maintenance import derive as CM

#: The one "tree" `name_positions` reports under. An entity root is a child of
#: the library root now, so there is no `characters/` or `projects/` folder to
#: name the group after — every top-level folder is somebody's slug.
ENTITY_ROOTS = "entity roots"

#: The shared seed bucket. Publisher and loader name it once between them, and
#: `STUDIO_DEV_SEED_BUCKET` overrides it for an ephemeral environment.
SEED_BUCKET = os.environ.get("STUDIO_DEV_SEED_BUCKET") or "studio-dev-seed-us-east-1"

#: Where the authoritative copies live. The bucket gets a copy; git holds the
#: original, because a fixture is reviewed in a diff.
FIXTURE_DIR = STUDIO_DIR / "fixtures" / "dev-seed"

#: The default cap on a promotion. #284 asks for six to eight objects and the
#: reason is arithmetic: every machine downloads this on every fresh stack. The
#: cap exists because `--path` on a folder takes its whole subtree, which is the
#: one way a careful selection turns into a wholesale one by accident.
MAX_OBJECTS = 12

#: Text-ish objects whose bytes are read and reported on. Everything else is
#: promoted unread — see `name_problems`.
TEXT_SUFFIXES = (".json", ".yaml", ".yml", ".txt", ".md")

#: Above this, a "text" file is not something a human is going to review, and
#: reading it into memory to scan it is not obviously the right thing either.
TEXT_MAX_BYTES = 256 * 1024


# ── reading the source stack ────────────────────────────────────────────────


def source() -> tuple[str, str]:
    """The dev stack this machine is pointed at, or a refusal.

    **The `prod` refusal is the first thing that happens, and it is the guard
    the first version of #284 needed.** That version copied production media
    into a shared bucket, which is the mistake the whole issue was rewritten to
    avoid: production material is not purpose-made for dev, and a fixture every
    machine downloads is the last place it belongs. `dev-aws-seed.sh` makes the
    same refusal on the same two names for the mirror-image reason.

    Both values come from the environment (`STUDIO_S3_BUCKET`,
    `STUDIO_CATALOG_TABLE`), pinned by `dev-setup.sh` from the dev stack's
    Terraform outputs.
    """
    bucket, table = s3c.bucket(), ddbc.table()
    for name in (bucket, table):
        if "prod" in name:
            die(f"refusing to read '{name}' — a fixture is promoted from a dev "
                "stack, never from production. Run scripts/dev-setup.sh, or "
                "export STUDIO_S3_BUCKET and STUDIO_CATALOG_TABLE for the dev "
                "stack you mean.")
    return bucket, table


def read_library(ddb, library: str | None = None) -> dict:
    """The whole library: its nodes, and the entity rows that own them.

    One scan, for the reason `catalog_seed.already_seeded` scans: a dev stack is
    small, and a GSI query would silently omit any row missing one of the
    index's key attributes — which is a row this command should refuse over, not
    skip. The same scan answers all four shapes, so reading the entities costs
    nothing on top of reading the tree:

        nodes      node_id -> `NODE#<id>` / `META`
        records    `CHAR#<id>` or `PROJ#<id>` -> its `META`, tagged with `kind`
        refs       `CHAR#<id>` -> its `REF#<node>` rows, each carrying `node`
        involves   `PROJ#<id>` -> the `CHAR#<id>` sort keys it is linked to

    **The entity rows used not to be read at all**, and the fixture `build`
    wrote was `{"version": 1, nodes}` with no `entities` key while
    `dev-aws-seed.sh` documented and validated version 2 with one. Nothing
    caught it because `fixture_problems` treats `entities` as optional and never
    checks `version`, so the document validated, loaded, and produced loose
    folders under the library root with no character or project records at all —
    precisely the outcome the loader's own header says the version bump existed
    to prevent.
    """
    libraries, metas = {}, {}
    records, refs, involves = {}, collections.defaultdict(list), collections.defaultdict(list)
    for item in ddbc.scan(ddb):
        pk, sk = item.get("pk", ""), item.get("sk", "")
        if sk == "META" and pk.startswith("LIB#"):
            libraries[pk.removeprefix("LIB#")] = item
        elif sk == "META" and pk.startswith("NODE#") and item.get("node_id"):
            metas[item["node_id"]] = item
        elif sk == "META" and pk.startswith(("CHAR#", "PROJ#")):
            kind = "character" if pk.startswith("CHAR#") else "project"
            records[pk] = dict(item, kind=kind)
        elif pk.startswith("CHAR#") and sk.startswith("REF#"):
            refs[pk].append(dict(item, node=sk.removeprefix("REF#")))
        elif pk.startswith("PROJ#") and sk.startswith("CHAR#"):
            involves[pk].append(sk)

    if not libraries:
        die(f"no library in '{ddbc.table()}'. Sign in to the local app and put "
            "something in it first — a fixture is promoted from work, not built.")
    if library is None and len(libraries) > 1:
        die("this table holds more than one library; name one with --library:\n"
            + "\n".join(f"       {lib}  ({row.get('name')})"
                        for lib, row in sorted(libraries.items())))
    lib = library or next(iter(libraries))
    if lib not in libraries:
        die(f"no library '{lib}' in '{ddbc.table()}'")

    root = libraries[lib].get("root_node")
    nodes = {nid: row for nid, row in metas.items() if row.get("lib") == lib}
    if root not in nodes:
        die(f"library {lib} names root node {root}, which has no row. The "
            "catalog is broken; `studio catalog verify` reports on it.")
    return {"lib": lib, "root": root, "name": libraries[lib].get("name") or "Studio",
            "nodes": nodes,
            "records": {pk: row for pk, row in records.items() if row.get("lib") == lib},
            "refs": dict(refs), "involves": dict(involves)}


def name_paths(library: dict) -> dict[str, str]:
    """`node_id -> "a/b/c"`, the chain of NAMES from the library root.

    The root itself maps to `""`. A node whose parent chain does not reach the
    root is left out and reported by the caller — an orphan is a broken row, and
    inventing a path for it would put a fiction in the fixture.
    """
    nodes, root = library["nodes"], library["root"]
    resolved: dict[str, str] = {root: ""}

    def walk(node_id: str, seen: frozenset[str]) -> str | None:
        if node_id in resolved:
            return resolved[node_id]
        row = nodes.get(node_id)
        if row is None or node_id in seen:
            return None
        parent = walk(row.get("parent_id"), seen | {node_id})
        if parent is None or not row.get("name"):
            return None
        resolved[node_id] = f"{parent}/{row['name']}" if parent else row["name"]
        return resolved[node_id]

    for node_id in nodes:
        walk(node_id, frozenset())
    return resolved


# ── choosing what to promote ────────────────────────────────────────────────


def expand(paths: dict[str, str], wanted: list[str]) -> dict:
    """Turn the `--path` list into the exact node set the fixture will carry.

    Three things happen, and they are reported separately because they are
    different kinds of decision:

    * **chosen** — a path the human named.
    * **descendants** — everything under a chosen folder. This is what makes
      `--path` usable for a run folder, and it is also the one way a careful
      selection becomes a wholesale one, which is what `--max-objects` is for.
    * **ancestors** — the folders above a chosen node. Not a choice at all: the
      loader refuses a fixture whose parent folders are missing and will not
      invent one, because a silently-invented folder is a shape nobody reviewed.
    """
    by_path = {path: node_id for node_id, path in paths.items() if path}
    missing = [p for p in wanted if p not in by_path]

    chosen, descendants = set(), set()
    for path in wanted:
        if path not in by_path:
            continue
        chosen.add(by_path[path])
        prefix = path + "/"
        descendants |= {nid for p, nid in by_path.items() if p.startswith(prefix)}
    descendants -= chosen

    ancestors: set[str] = set()
    for node_id in chosen | descendants:
        parts = paths[node_id].split("/")
        for depth in range(1, len(parts)):
            ancestor = by_path.get("/".join(parts[:depth]))
            if ancestor is not None:
                ancestors.add(ancestor)
    ancestors -= chosen | descendants

    return {"chosen": chosen, "descendants": descendants,
            "ancestors": ancestors, "missing": missing,
            "all": chosen | descendants | ancestors}


# ── hard rule #1 ────────────────────────────────────────────────────────────

#: **The dev subjects that may be named in this repository.**
#:
#: This used to be a REGEX over the *shape* of a name —
#: `^(?:<[a-z]+>|subject-[a-z0-9-]+|demo|sample|fixture|example)$` — with a
#: second one refusing anything Title Cased. Both are gone, because the rule
#: they enforced is gone: hard rule #1 is env-scoped now (see `studio/CLAUDE.md`).
#: A dev subject exists only in a per-machine dev stack and in the shared
#: fixture, and naming one is fine. A PRODUCTION character is still never named.
#:
#: A shape test could not express that distinction — `mira` and `demo` are the
#: same string to a regex, which the old docstring admitted at length — so the
#: gate moved to where the distinction actually lives: a list, edited
#: deliberately. Adding a subject is a reviewed diff on this line, which is a
#: better gate than a pattern that let every lowercase first name through and
#: refused every capitalised one.
#:
#: The mechanical half of "this is dev material" is NOT here. It is `source()`,
#: which refuses to read a bucket or table whose name contains `prod` before
#: anything else happens — so a fixture is dev-origin by construction and this
#: list only decides WHICH dev subjects are publishable.
#: Top-level folders this repo PUTS THERE ITSELF, which are not name positions
#: at all — nobody's slug, no entity's root, and nothing a person chose.
#:
#: **Leaving `config` out of this broke the publisher the moment the loader
#: started working.** The angle images are ordinary nodes under `config/`, pushed
#: by `studio config sync`. `dev-aws-seed.sh` pushed them BEFORE it wrote the
#: library, so the push failed on every fresh stack and `config/` never existed
#: — which is the only reason the name check had never seen it. Fixing that
#: ordering made the angle images land, and the very next `dev-seed publish` refused
#: the stack over a folder the loader had just created.
#:
#: `catalog_gc.SHARED_PREFIXES` is the same idea for the same two names, on the
#: delete side.
SHARED_ROOTS = frozenset({P.CONFIG, "phrasebook"})

DEV_SUBJECTS = frozenset({
    "jason",                                  # the seed fixture's subject
    "subject-a", "subject-b",                 # what the test fixtures use
    "demo", "sample", "fixture", "example",   # the generic stand-ins
    # Projects, which land in a name position too — an entity root is a
    # top-level folder whether a character or a project owns it, so there is one
    # list rather than two. A project is normally named after the WORK, which is
    # why this one reads nothing like a person.
    "flex-study",
})

#: A slug the API would accept: lowercase, starting alphanumeric. The same rule
#: `domain/paths.check_slug` applies, restated here because the loader validates
#: a document rather than a live record.
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

#: Any capitalised word of three letters or more, for the report. Not a refusal
#: — see `name_problems` on why.
TITLE_TOKEN = re.compile(r"\b[A-Z][a-z]{2,}\b")


def name_positions(paths: dict[str, str]) -> dict[str, list[str]]:
    """Every segment sitting where the layout says a NAME goes.

    **This moved up one level with the entity model, and the guard got
    stronger.** It used to look for the segment under `characters/` and the
    segment under `projects/`, because those two folders were the whole layout
    and `paths.py` built them. There is no `characters/` folder any more: an
    entity's root folder is a child of the LIBRARY root, and its name is its
    slug.

    So the position where a name is provably a name is now the FIRST segment of
    every path, and every one of them is checked. Nothing is skipped for being
    in an unrecognised tree — which is what the old shape did, silently, for any
    folder a person had made by hand at the top level.

    Grouped under one key rather than two, because there is no longer a folder
    name that tells a character apart from a project. That distinction lives in
    the entity rows, and a fixture carries none — see the module docstring on
    why no ids are published.
    """
    found = collections.defaultdict(set)
    for path in paths.values():
        parts = path.split("/") if path else []
        if parts and parts[0] and parts[0] not in SHARED_ROOTS:
            found[ENTITY_ROOTS].add(parts[0])
    return {tree: sorted(names) for tree, names in found.items()}


def name_problems(all_paths: dict[str, str]) -> list[str]:
    """Every reason this promotion may not be published, one per line.

    **WHAT IT CHECKS.** One thing: every segment in a name position anywhere in
    the source library is in `DEV_SUBJECTS`. **The whole stack, not just the
    selection** — #284 is explicit that generating naturally and sanitising
    afterwards is the wrong order, because by then the name is already in the
    bucket, the run JSON and the keys. So the property is "this stack was
    *driven* with subjects that may be published", and a stack with one
    unlisted name in a corner of it fails whether or not that corner is being
    promoted.

    **THIS IS NARROWER THAN IT LOOKS, AND DELIBERATELY SO.** It used to be two
    checks — a shape regex over the name positions and a Title-Case refusal over
    every published segment — and both are deleted rather than adapted. The
    Title-Case check has no meaning under an allowlist: it existed to catch a
    name that the shape test would otherwise wave through, and a list has no
    such gap. Keeping it would only have refused `<Name>`-shaped folders that
    are now perfectly publishable.

    **WHAT IT CANNOT CATCH.** None of these is hypothetical:

    * **A name in a promoted file's BYTES.** A prompt in `request.json`, a
      caption, a bible. Text objects are scanned and their capitalised tokens
      *reported* — but a report is a thing a human reads, and lowercase prose
      naming someone is not reported at all. The reason it is a report rather
      than a refusal is that a refusal on capitalised words in prose would fire
      on every sentence and be turned off within a week.
    * **A face.** The fixture is media, and media of a real person carries an
      identity no text check has any purchase on. Under the old absolute rule
      this was listed as a reason not to publish such a fixture at all. Under
      the env-scoped rule it is a reason to be deliberate about WHO is on the
      list: a dev subject's likeness goes into a private bucket that every
      machine in this account downloads, and adding a name here is the moment
      that decision is made.
    * **The attestation itself.** `--dev-subjects-only` is a flag. Nothing
      verifies it, and nothing can.
    """
    problems = []
    for tree, names in sorted(name_positions(all_paths).items()):
        bad = [n for n in names if n not in DEV_SUBJECTS]
        if bad:
            problems.append(
                f"{tree}/ holds {', '.join(repr(n) for n in bad)} — not a dev "
                "subject this repo publishes. A fixture is promoted from a "
                "stack DRIVEN with listed subjects, not from one sanitised "
                "afterwards; this is the whole stack, not just what you "
                "selected. Add the name to DEV_SUBJECTS in dev_seed.py if it "
                "belongs there, or rename it in the dev stack.")
    return problems


def text_tokens(bodies: dict[str, bytes]) -> dict[str, list[str]]:
    """Capitalised tokens found in each promoted text object, for the report.

    Reported, never refused. The point is that a human sees this list on the dry
    run, before they type `--apply` — which is the only mechanism there is for
    the half of hard rule #1 that no regex decides. See `name_problems`.
    """
    found = {}
    for path, body in sorted(bodies.items()):
        if not path.lower().endswith(TEXT_SUFFIXES) or len(body) > TEXT_MAX_BYTES:
            continue
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            continue
        tokens = sorted(set(TITLE_TOKEN.findall(text)))
        if tokens:
            found[path] = tokens
    return found


# ── the two documents ───────────────────────────────────────────────────────


def entities(library: dict, paths: dict[str, str],
             selected: set[str]) -> list[dict]:
    """The `entities` half of `catalog.json`: who owns the promoted folders.

    **Everything is expressed as a PATH**, because a fixture carries no ids —
    see the module docstring. A character's `root`, its `hero`, every entry in
    its `default_set` and every `references[].node` is the slash-joined chain of
    names, and `dev-aws-seed.sh` maps them back to the ids it derived for the
    machine it is seeding.

    **An entity is dropped, not repaired, when its root was not promoted.** The
    loader refuses an entity whose root is not a folder node in the fixture, and
    inventing one here would put a folder in the fixture that nobody selected.
    Reference entries and involvements are filtered the same way and for the
    same reason: a `REF#` row naming an image that was not promoted is a row
    pointing at nothing.

    `schema_version`, `profile` and `counts` are carried through as they stand.
    They are the record's own, and a fixture that normalised them would seed a
    library subtly unlike the one it was promoted from.
    """
    promoted = {paths[n] for n in selected}

    def path_of(node_id):
        path = paths.get(node_id or "")
        return path if path in promoted else None

    out = []
    for pk, row in sorted(library["records"].items(), key=lambda kv: kv[1]["slug"]):
        root = path_of(row.get("root"))
        if root is None:
            continue
        entity = {"kind": row["kind"], "slug": row["slug"], "root": root}

        if row["kind"] == "character":
            kept = [entry for entry in library["refs"].get(pk, [])
                    if path_of(entry["node"])]
            kept.sort(key=lambda e: (e.get("group") or "", e.get("order") or 0))
            references = [{"node": paths[entry["node"]],
                           "group": entry.get("group") or "unsorted",
                           "order": entry.get("order"),
                           "description": entry.get("description") or "",
                           "tags": entry.get("tags") or [],
                           "created": entry.get("created")}
                          for entry in kept]
            # `default_set` must be a SUBSET of `references` or the loader
            # refuses the whole fixture. Filtered here rather than trusted: a
            # node sits in the set with its `REF#` row filtered out above only
            # when the two disagree in the source stack, which is a thing
            # `catalog verify` reports on and not a thing to publish.
            named = {ref["node"] for ref in references}
            entity.update(
                display_name=row.get("display_name") or row["slug"],
                fictional=bool(row.get("fictional", True)),
                schema_version=row.get("schema_version"),
                hero=path_of(row.get("hero")),
                default_set=[p for p in (path_of(n)
                                         for n in row.get("default_set") or [])
                             if p in named],
                profile=row.get("profile") or {},
                references=references,
            )
        else:
            entity.update(
                title=row.get("title") or row["slug"],
                description=row.get("description") or "",
                hero=path_of(row.get("hero")),
                counts=row.get("counts") or {},
                characters=sorted(
                    library["records"][sk]["slug"]
                    for sk in library["involves"].get(pk, [])
                    if sk in library["records"]
                    and path_of(library["records"][sk].get("root"))),
            )
        out.append({k: v for k, v in entity.items() if v is not None})
    return out


def source_key(version: str, path: str) -> str:
    """Where a node's bytes live in the seed bucket.

    Keyed by the fixture's own path rather than by an id, so the bucket is
    legible in a listing and the manifest is legible in a diff. Paths are unique
    within a library, which is what the loader's "claimed by exactly one node"
    cross-check needs.
    """
    return f"{version}/media/{path}"


def build(library: dict, paths: dict[str, str], selected: set[str],
          blobs: dict[str, bytes], version: str) -> tuple[dict, dict]:
    """`catalog.json` and `manifest.json`, exactly as `dev-aws-seed.sh` reads them.

    Sizes and checksums come from the bytes that were actually read, not from
    the `size` attribute on the row: the row is what the API recorded and the
    manifest is what the loader will verify a download against, so the manifest
    has to describe the object rather than the record of it.

    **`version` is 2 and `entities` is always present**, even when it is empty.
    An empty list and a missing key load identically, so writing the key anyway
    is what makes "this fixture describes no entities" a statement rather than
    an omission. This document used to say `1` and carry no entities at all —
    see `read_library`.
    """
    nodes, objects = [], {}
    for node_id in sorted(selected, key=lambda n: paths[n]):
        row, path = library["nodes"][node_id], paths[node_id]
        node = {"path": path, "kind": row["kind"], "created_at": row["created_at"]}
        if row["kind"] == "file":
            key = source_key(version, path)
            body = blobs[node_id]
            node["source"] = key
            node["content_type"] = (row.get("content_type")
                                    or CM.content_type(path))
            objects[key] = {"size": len(body),
                            "sha256": hashlib.sha256(body).hexdigest()}
        nodes.append(node)

    catalog = {"version": 2, "library_name": library["name"],
               "entities": entities(library, paths, selected), "nodes": nodes}
    manifest = {"version": version, "object_count": len(objects),
                "total_bytes": sum(o["size"] for o in objects.values()),
                "objects": objects}
    return catalog, manifest


def document(doc: dict) -> bytes:
    """A fixture document as bytes, in the one formatting both copies use.

    Two spaces and a trailing newline, so the git copy is a readable diff, and
    byte-identical to what goes in the bucket so `catalog.json` in the repo and
    `catalog.json` in S3 can be compared with a checksum rather than a parser.
    """
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# ── loading a fixture into this stack ───────────────────────────────────────
#
# The other half of `publish`, and it used to be 1000 lines of bash
# (`scripts/dev-aws-seed.sh`, #285). It is here now for one measured reason:
# **the shell version moved 12.4 MB out of S3 and back into it, one `aws`
# process per object, and took 71 seconds to do 0.6 seconds of work.**
#
#     download + upload, per-object CLI     71s      what this replaces
#     server-side copy, per-object CLI      23s      the CLI startup, alone
#     server-side copy, one process         0.5s     what this does
#     59 node writes as transactions        2.5s     what this replaces
#     59 node writes via batch_write_item   0.1s     what this does
#
# Nothing about S3 or DynamoDB was slow. The cost was entirely a shell script
# paying ~0.4s of Python interpreter startup per object — the irony being that
# `uuid5_url` was reimplemented in bash specifically so the script would "never
# need Python".
#
# **The bytes never leave S3 now.** `copy_object` is a server-side copy, so the
# fixture is not pulled through this machine at all. The old script checksummed
# every object locally before writing anything, on the reasoning that the
# manifest checksum is the only thing that says the fixture is the fixture. That
# check is gone: it cost the entire round trip, it duplicated a verify pass that
# ran immediately afterwards anyway, and the recovery from a bad load into a DEV
# stack is `dev-aws-reset.sh`. `manifest.json` is still published and still
# describes the bytes; nothing reads it back on the way in.
#
# **A re-seed overwrites rather than skipping.** The shell version put
# `attribute_not_exists(pk)` on every item and read a refusal as "already
# seeded", which is what made a second run a no-op. `batch_write_item` takes no
# conditions, so a second run rewrites the same rows with the same values —
# idempotent by value instead of by condition. The difference shows only if
# somebody edited a seeded row and re-ran the loader, and "refill this stack
# from the fixture" is what the command means.

#: uuid5 over a URL, matching `maintenance/derive` and the shell loader it
#: replaces. `test_dev_seed` pins the three derivations against the values the
#: bash implementation produced, so a stack seeded by either is the same stack.
NAMESPACE = uuid.NAMESPACE_URL

#: How many items `batch_write_item` takes at once. DynamoDB's limit, not ours.
BATCH = 25

#: Concurrent `copy_object` calls. Server-side copies are latency-bound and
#: cost nothing locally, so this is about round trips rather than bandwidth.
COPY_WORKERS = 32


def library_id(bucket: str) -> str:
    """One bucket, one library; the bucket names it."""
    return f"lib-{uuid.uuid5(NAMESPACE, f's3://{bucket}')}"


def node_id(bucket: str, path: str) -> str:
    """`""` is the library root, which is why the trailing slash is not optional."""
    return f"node-{uuid.uuid5(NAMESPACE, f's3://{bucket}/{path}')}"


def materialised(bucket: str, parent: str) -> str:
    """The `path` attribute for a node sitting directly inside `parent`.

    Ancestor ids, root first, slash-delimited — the derived index that makes a
    subtree one `begins_with` query. `parent_id` stays authoritative.
    """
    out = f"/{node_id(bucket, '')}/"
    if parent:
        walked = ""
        for part in parent.split("/"):
            walked = f"{walked}/{part}" if walked else part
            out += f"{node_id(bucket, walked)}/"
    return out


def extension_of(path: str) -> str:
    """`.png`, or `""` when the basename carries none.

    Decoration for a human reading the S3 console — `content_type` on the row is
    authoritative — and on the key only because a bucket of extensionless uuids
    is unreadable.
    """
    base = path.rsplit("/", 1)[-1]
    stem, dot, ext = base.rpartition(".")
    return f".{ext}" if dot and stem and ext else ""


def blob_key(bucket: str, nid: str, path: str,
             owner_kind: str | None, owner_root: str | None) -> str:
    """`<owner_kind>/<owner_id>/<node_id><ext>`, stamped once and never parsed.

    Anything owned by no entity sits under `libraries/<lib id>/`, which is a real
    state rather than a fallback: material at the library root belongs to nobody
    in particular.
    """
    ext = extension_of(path)
    if not owner_kind:
        return f"libraries/{library_id(bucket)}/{nid}{ext}"
    owner = CM.entity_id(owner_kind, node_id(bucket, owner_root))
    return f"{owner_kind}s/{owner}/{nid}{ext}"


def fixture_documents(s3, seed_bucket: str, version: str) -> tuple[dict, dict]:
    """`catalog.json` and `manifest.json`, or a refusal that says whose job it is.

    The failure worth wording carefully is a seed bucket with nothing in it: a
    raw `NoSuchKey` from boto3 reads as a broken dev stack, and it is not one.
    """
    def read(name):
        key = f"{version}/{name}"
        try:
            return json.loads(s3.get_object(Bucket=seed_bucket, Key=key)["Body"].read())
        except s3.exceptions.NoSuchKey:
            return None
        except json.JSONDecodeError as exc:
            die(f"s3://{seed_bucket}/{key} is not valid JSON: {exc}")

    catalog = read("catalog.json")
    if catalog is None:
        die(f"no fixture at s3://{seed_bucket}/{version}/catalog.json.\n"
            "       Nothing is wrong with your stack — there is nothing to load. "
            "Publish one with `studio dev-seed publish`.")
    manifest = read("manifest.json")
    if manifest is None:
        die(f"s3://{seed_bucket}/{version}/catalog.json exists and manifest.json "
            "does not. The fixture is incomplete.")
    return catalog, manifest


def problems(catalog: dict, manifest: dict) -> list[str]:
    """Every reason this fixture cannot be loaded, one per line.

    **The port of `fixture_problems`, and the contract stopped being two-sided
    when it moved.** The shell validator and this module used to be separate
    implementations of one schema, with `test_dev_seed` feeding the publisher's
    output through the loader's own jq to prove they agreed. That test was
    guarding against drift between two things; there is one thing now, so the
    agreement is structural rather than asserted. The failure cases it
    parametrised moved here with it.

    All of them at once rather than the first: a fixture is fixed by editing it
    in git and re-publishing, so a list is one round trip and a first-failure is
    as many round trips as there are mistakes.
    """
    found: list[str] = []
    nodes = catalog.get("nodes")
    objects = manifest.get("objects")
    if nodes is None:
        return ["catalog.json has no `nodes`"]
    if objects is None:
        return ["manifest.json has no `objects`"]
    if not nodes:
        found.append("catalog.json lists no nodes")

    paths = [node.get("path") or "" for node in nodes]
    folders = {node.get("path") for node in nodes if node.get("kind") == "folder"}
    for path, count in collections.Counter(paths).items():
        if count > 1:
            found.append(f"duplicate path: {path}")

    for node in nodes:
        path = node.get("path") or ""
        if not path:
            found.append("a node has no `path`")
            continue
        # The same rejections the API validator makes: an empty segment, `.` or
        # `..`, a control character, or a name over 255 bytes.
        for segment in path.split("/"):
            if (not segment or segment in (".", "..")
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in segment)
                    or len(segment.encode()) > 255):
                found.append(f"unusable name in path {json.dumps(path)}")
        if node.get("kind") not in ("file", "folder"):
            found.append(f"{path}: kind must be `file` or `folder`, "
                         f"not {json.dumps(node.get('kind'))}")
        if not node.get("created_at"):
            found.append(f"{path}: no `created_at` — the fixture carries the ordering")
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent and parent not in folders:
            found.append(f"{path}: its parent folder is not a node in catalog.json")
        if node.get("kind") == "file":
            if not node.get("source"):
                found.append(f"{path}: a file node needs a `source` key in the seed bucket")
            elif node["source"] not in objects:
                found.append(f"{path}: source {node['source']} is not in manifest.json")
            if not node.get("content_type"):
                found.append(f"{path}: a file node needs a `content_type`")
        elif node.get("source") is not None:
            found.append(f"{path}: a folder node may not carry a `source`")

    sources = [node["source"] for node in nodes
               if node.get("kind") == "file" and node.get("source")]
    for source, count in collections.Counter(sources).items():
        if count > 1:
            found.append(f"source claimed by more than one node: {source}")
    for key in objects:
        if key not in set(sources):
            found.append(f"manifest object claimed by no node: {key}")

    # `entities` is OPTIONAL — a fixture of loose material under the library
    # root is a real library — but anything it DOES say has to resolve, or the
    # loader would write a record pointing at a folder that is not there.
    entities = catalog.get("entities") or []
    slugs = [entity.get("slug") for entity in entities]
    for slug, count in collections.Counter(slugs).items():
        if count > 1:
            found.append(f"two entities claim the slug: {slug}")
    characters = {entity.get("slug") for entity in entities
                  if entity.get("kind") == "character"}
    for entity in entities:
        slug, root = entity.get("slug"), entity.get("root")
        if entity.get("kind") not in ("character", "project"):
            found.append(f"entity {json.dumps(slug)}: kind must be `character` or `project`")
        if not slug or not SLUG.match(slug):
            found.append(f"entity root {json.dumps(root)}: slug must be lowercase "
                         "[a-z0-9_-] starting alphanumeric")
        if not root or root not in folders:
            found.append(f"entity {json.dumps(slug)}: its root {json.dumps(root)} "
                         "is not a folder node")
        elif "/" in root:
            # A root has to be a TOP-LEVEL folder, because that is where the
            # owner of a blob key is read from. An entity rooted deeper would
            # own bytes the key scheme cannot express.
            found.append(f"entity {json.dumps(slug)}: its root must be a folder at "
                         f"the library root, not {json.dumps(root)}")
        if entity.get("kind") == "character":
            named = {ref.get("node") for ref in entity.get("references") or []}
            for ref in entity.get("references") or []:
                if ref.get("node") not in paths:
                    found.append(f"{slug}: reference {json.dumps(ref.get('node'))} "
                                 "is not a node in catalog.json")
            for want in entity.get("default_set") or []:
                if want not in named:
                    found.append(f"{slug}: default_set names {json.dumps(want)}, "
                                 "which is not one of its references")
        else:
            for involved in entity.get("characters") or []:
                if involved not in characters:
                    found.append(f"{slug}: involves {json.dumps(involved)}, which is "
                                 "not a character in this fixture")

    declared = manifest.get("object_count", -1)
    if declared != len(objects):
        found.append(f"manifest object_count is {declared} but it lists {len(objects)}")
    total = manifest.get("total_bytes", -1)
    actual = sum(entry.get("size", 0) for entry in objects.values())
    if total != actual:
        found.append(f"manifest total_bytes is {total} but its sizes add to {actual}")
    return found


def owner_of(catalog: dict) -> dict[str, tuple[str, str]]:
    """`top-level folder name -> (entity kind, that same name)`.

    Which entity owns a node's bytes is read off the FIRST segment of its path,
    which is why an entity root has to be a top-level folder.
    """
    return {entity["root"]: (entity["kind"], entity["root"])
            for entity in catalog.get("entities") or []
            if entity.get("root")}


def rows(catalog: dict, manifest: dict, bucket: str, lib: str,
         owner: str) -> list[dict]:
    """Every DynamoDB item the fixture becomes, in one list.

    Built whole and written in batches rather than a transaction per node. The
    shell loader did one `TransactWriteItems` per node for the atomicity of its
    two items — which is real, but it is atomicity between two rows that this
    function writes from one source in one pass, so nothing can observe the gap
    on a stack being seeded from empty. It cost 2.5 seconds against 0.1.
    """
    born = min(node["created_at"] for node in catalog["nodes"])
    root = node_id(bucket, "")
    owners = owner_of(catalog)
    items = [
        {"pk": f"LIB#{lib}", "sk": "META", "name": catalog.get("library_name") or "Studio",
         "root_node": root, "created_at": born},
        {"pk": f"USER#{owner}", "sk": f"LIB#{lib}", "role": "owner", "created_at": born},
        {"pk": f"NODE#{root}", "sk": "META", "node_id": root, "lib": lib,
         "kind": "folder", "path": "/", "created_at": born, "updated_at": born},
    ]

    # `size` is the manifest's, because the manifest describes the BYTES while
    # the catalog describes the tree. A node row claiming a size the object does
    # not have is the one drift the app would show and nothing would explain.
    sizes = {node["path"]: (manifest.get("objects") or {}).get(node.get("source"), {}).get("size", 0)
             for node in catalog["nodes"] if node["kind"] == "file"}
    for node in catalog["nodes"]:
        path, kind = node["path"], node["kind"]
        parent, _, name = path.rpartition("/")
        nid = node_id(bucket, path)
        pid = node_id(bucket, parent) if parent else root
        where = materialised(bucket, parent)
        owner_kind, owner_root = owners.get(path.split("/")[0], (None, None))

        meta = {"pk": f"NODE#{nid}", "sk": "META", "node_id": nid, "parent_id": pid,
                "lib": lib, "name": name, "kind": kind, "path": where,
                "created_at": node["created_at"], "updated_at": node["created_at"]}
        if kind == "file":
            meta["blob_key"] = blob_key(bucket, nid, path, owner_kind, owner_root)
            meta["content_type"] = node["content_type"]
            meta["size"] = sizes.get(path, 0)
            # `reel` is the SPARSE key on `by-recent` (D5): the index is hashed
            # on it, so a row without the attribute is simply not in it. Images
            # and video only — a folder or a request.json has no business in a
            # reel of media.
            if CM.in_the_reel(meta):
                meta["reel"] = lib
        items.append(meta)
        items.append({"pk": f"NODE#{pid}", "sk": f"NAME#{name}", "node_id": nid,
                      "lib": lib, "kind": kind, "path": where,
                      "created_at": node["created_at"]})

    for entity in catalog.get("entities") or []:
        kind, slug = entity["kind"], entity["slug"]
        root_node = node_id(bucket, entity["root"])
        eid = CM.entity_id(kind, root_node)
        claim = "CHARSLUG" if kind == "character" else "PROJSLUG"
        record = {"pk": f"{'CHAR' if kind == 'character' else 'PROJ'}#{eid}",
                  "sk": "META", "id": eid, "lib": lib, "slug": slug, "rev": 1,
                  "created": entity.get("created") or "", "updated": entity.get("created") or "",
                  "root": root_node}
        stamp = min(node["created_at"] for node in catalog["nodes"])
        record["created"] = record["updated"] = stamp
        if kind == "character":
            record.update(
                display_name=entity.get("display_name") or slug,
                fictional=bool(entity.get("fictional", True)),
                schema_version=entity.get("schema_version") or 2,
                hero=node_id(bucket, entity["hero"]) if entity.get("hero") else None,
                default_set=[node_id(bucket, p) for p in entity.get("default_set") or []],
                profile=entity.get("profile") or {})
            for index, ref in enumerate(entity.get("references") or []):
                items.append({"pk": f"CHAR#{eid}", "sk": f"REF#{node_id(bucket, ref['node'])}",
                              "lib": lib, "group": ref.get("group") or "unsorted",
                              "order": ref.get("order") or (index + 1) * 1000,
                              "description": ref.get("description") or "",
                              "tags": ref.get("tags") or [],
                              "created": ref.get("created") or stamp})
        else:
            record.update(
                title=entity.get("title") or slug,
                description=entity.get("description") or "",
                hero=node_id(bucket, entity["hero"]) if entity.get("hero") else None,
                counts=entity.get("counts") or {})
        items.append({k: v for k, v in record.items() if v is not None})
        items.append({"pk": f"LIB#{lib}", "sk": f"{claim}#{slug}",
                      "entity": eid, "created": stamp})
    return items


def copy_blobs(s3, seed_bucket: str, bucket: str, catalog: dict) -> int:
    """Server-side copies, concurrently. Returns how many objects moved.

    **The bytes never touch this machine.** `copy_object` is an S3-to-S3 copy;
    the old shell loader downloaded each object and uploaded it again, which is
    24.8 MB of transfer to move 12.4 MB of fixture and the single largest reason
    seeding took over a minute.

    `ContentType` is set from the ROW rather than left to S3's guess, which is
    why this is `MetadataDirective=REPLACE` — the catalog is authoritative about
    what a file is, and five of the fixture's objects arrived with a `.jpg`
    extension over PNG bytes before they were normalised.
    """
    owners = owner_of(catalog)
    jobs = []
    for node in catalog["nodes"]:
        if node["kind"] != "file":
            continue
        path = node["path"]
        owner_kind, owner_root = owners.get(path.split("/")[0], (None, None))
        nid = node_id(bucket, path)
        jobs.append((node["source"],
                     blob_key(bucket, nid, path, owner_kind, owner_root),
                     node["content_type"]))

    def copy(job):
        source, key, content_type = job
        s3.copy_object(Bucket=bucket, Key=key,
                       CopySource={"Bucket": seed_bucket, "Key": source},
                       ContentType=content_type, MetadataDirective="REPLACE")

    with concurrent.futures.ThreadPoolExecutor(max_workers=COPY_WORKERS) as pool:
        # `map` is lazy and swallows nothing: consuming it is what re-raises a
        # failed copy on this thread rather than losing it in the pool.
        list(pool.map(copy, jobs))
    return len(jobs)


def write_rows(ddb, table: str, items: list[dict]) -> int:
    """`batch_write_item` in twenty-fives, with the unprocessed ones retried.

    DynamoDB may decline part of a batch under throttling and reports which —
    dropping that answer on the floor is how a seed ends up half-written and
    says it succeeded.
    """
    written = 0
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        request = {table: [{"PutRequest": {"Item": ddbc.to_item(item)}} for item in chunk]}
        for _attempt in range(5):
            answer = ddb.batch_write_item(RequestItems=request)
            unprocessed = answer.get("UnprocessedItems") or {}
            written += len(request[table]) - len(unprocessed.get(table, []))
            if not unprocessed:
                break
            request = unprocessed
        else:
            die(f"DynamoDB kept declining writes to {table}; {len(items) - written} "
                "item(s) were not written. Re-run when the table is not throttled.")
    return written


def adopt_roots(ddb, table: str, catalog: dict, bucket: str) -> None:
    """Point each entity's root folder back at the entity that owns it.

    An `Update` rather than a `Put`, because the folder is a node the pass above
    already wrote in full: replacing it here would be a second definition of the
    same row, and the one thing it needs is one more attribute.
    """
    for entity in catalog.get("entities") or []:
        root = node_id(bucket, entity["root"])
        ddb.update_item(
            TableName=table,
            Key=ddbc.to_item({"pk": f"NODE#{root}", "sk": "META"}),
            UpdateExpression="SET #entity = :entity",
            ExpressionAttributeNames={"#entity": "entity"},
            ExpressionAttributeValues=ddbc.to_item(
                {":entity": CM.entity_id(entity["kind"], root)}),
        )


def owner_sub(pool_id: str, email: str) -> str:
    """The `sub` of the dev account that will own the seeded library.

    From the DEV pool, and the failure is worth naming: a library with no
    membership row is a library nobody can read, and the API answers "you are
    not a member of any library" rather than anything about seeding.
    """
    import boto3

    idp = boto3.client("cognito-idp")
    try:
        user = idp.admin_get_user(UserPoolId=pool_id, Username=email)
    except Exception as exc:  # noqa: BLE001 — any failure here means the same thing
        die(f"no '{email}' in {pool_id}, so the library would have no member "
            f"({exc}). Run ./studio/scripts/dev-user.sh first.")
    for attribute in user.get("UserAttributes", []):
        if attribute["Name"] == "sub":
            return attribute["Value"]
    die(f"'{email}' in {pool_id} has no `sub` attribute.")


# ── CLI ─────────────────────────────────────────────────────────────────────


def _clients():
    """S3 and DynamoDB for the dev stack, after the `prod` refusal."""
    bucket, table = source()
    ddb = ddbc.client()
    if not ddbc.table_exists(ddb):
        die(f"no table '{table}'. Run scripts/dev-aws-setup.sh, or export "
            "STUDIO_CATALOG_TABLE for the dev stack you mean.")
    return s3c.client(), ddb, bucket, table


@click.group(help=__doc__)
def main() -> None:
    pass


@main.command("tree")
@click.option("--library", help="library id, if this stack somehow holds more than one")
def cmd_tree(library):
    """List this dev stack's library by path — the `--path` values `publish` takes."""
    _s3, ddb, bucket, table = _clients()
    lib = read_library(ddb, library)
    paths = name_paths(lib)

    print(f"stack      s3://{bucket}/  +  {table}")
    print(f"library    {lib['lib']}  ({lib['name']})")
    orphans = len(lib["nodes"]) - len(paths)
    if orphans:
        print(f"orphans    {orphans}  (no chain to the root; `studio catalog verify`)")
    print()
    for node_id, path in sorted(paths.items(), key=lambda kv: kv[1]):
        if not path:
            continue
        row = lib["nodes"][node_id]
        size = f"{row.get('size', 0):>10}" if row["kind"] == "file" else " " * 10
        print(f"  {row['kind']:<7}{size}  {path}")


@main.command("publish")
@click.option("--path", "wanted", multiple=True, required=True,
              help="a node to promote, by its path in this stack. Repeatable. "
                   "A folder brings its subtree; ancestors are added for you. "
                   "There is deliberately no --all.")
@click.option("--paths-from", type=click.Path(exists=True, dir_okay=False),
              help="read additional --path values from a file, one per line "
                   "(blank lines and # comments ignored)")
@click.option("--fixture-version", default="v1", show_default=True,
              help="the version prefix in the seed bucket; a fixture change is "
                   "additive, so a new shape is v2 rather than a mutation of v1")
@click.option("--seed-bucket", default=SEED_BUCKET, show_default=True,
              help="the shared seed bucket")
@click.option("--library", help="library id, if this stack somehow holds more than one")
@click.option("--max-objects", default=MAX_OBJECTS, show_default=True,
              help="refuse a selection that expands past this many files. #284 "
                   "asks for six to eight: every machine downloads this.")
@click.option("--dev-subjects-only", is_flag=True,
              help="ATTEST that this dev stack was DRIVEN with listed dev "
                   "subjects (see DEV_SUBJECTS) from the first generation — not "
                   "renamed afterwards — that nothing in it belongs to a "
                   "PRODUCTION character, and that you have read the capitalised "
                   "tokens reported from the promoted text. Required for --apply. "
                   "Nothing verifies this; the check reads names, not people.")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
def cmd_publish(wanted, paths_from, fixture_version, seed_bucket, library,
                max_objects, dev_subjects_only, apply):
    """Copy chosen nodes into the seed bucket and write the fixture documents."""
    wanted = [p.strip("/") for p in wanted]
    if paths_from:
        with open(paths_from) as fh:
            wanted += [line.strip().strip("/") for line in fh
                       if line.strip() and not line.lstrip().startswith("#")]
    if any(not p for p in wanted):
        die("an empty --path is the library root, which is the whole stack. "
            "Name the nodes you mean; #284 lists the shapes a fixture needs.")

    s3, ddb, bucket, _table = _clients()
    lib = read_library(ddb, library)
    paths = name_paths(lib)
    picked = expand(paths, wanted)
    if picked["missing"]:
        die("no such path in this stack: "
            + ", ".join(repr(p) for p in picked["missing"])
            + "\n       `studio dev-seed tree` lists them.")

    files = sorted((nid for nid in picked["all"]
                    if lib["nodes"][nid]["kind"] == "file"),
                   key=lambda n: paths[n])
    if len(files) > max_objects:
        die(f"{len(files)} objects, over the --max-objects cap of {max_objects}. "
            "A folder brings its subtree, which is how a chosen fixture becomes "
            "a whole session. #284 asks for six to eight; raise the cap only if "
            "you mean it.")

    # Read the bytes before checking anything else about them. The dry run does
    # this too, so `--apply` is a repeat of a run whose report has been read
    # rather than the first time anything is looked at.
    blobs = {}
    for node_id in files:
        key = lib["nodes"][node_id].get("blob_key")
        if not key:
            die(f"{paths[node_id]}: a file node with no blob_key. "
                "`studio catalog verify` reports on it.")
        blobs[node_id] = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

    problems = name_problems(paths)
    tokens = text_tokens({paths[nid]: body for nid, body in blobs.items()})

    catalog, manifest = build(lib, paths, picked["all"], blobs, fixture_version)

    print(f"library     {lib['lib']}  ({lib['name']})")
    print(f"from        s3://{bucket}/")
    print(f"to          s3://{seed_bucket}/{fixture_version}/")
    print(f"            {FIXTURE_DIR / fixture_version}/  (authoritative)")
    print(f"\n  {'chosen':<12}{len(picked['chosen']):>4}")
    print(f"  {'subtree':<12}{len(picked['descendants']):>4}  (under a chosen folder)")
    print(f"  {'ancestors':<12}{len(picked['ancestors']):>4}  "
          "(structural — the loader will not invent one)")
    print(f"  {'objects':<12}{manifest['object_count']:>4}  "
          f"({manifest['total_bytes']} bytes, cap {max_objects})")
    print()
    why = {**{paths[n]: "chosen" for n in picked["chosen"]},
           **{paths[n]: "subtree" for n in picked["descendants"]},
           **{paths[n]: "ancestor" for n in picked["ancestors"]}}
    for node in catalog["nodes"]:
        print(f"  {why[node['path']]:<9}{node['kind']:<7}{node['path']}")

    if tokens:
        print("\ncapitalised tokens in the promoted text — READ THESE. Hard rule "
              "#1 covers what is written, not just what it is called:")
        for path, found in tokens.items():
            print(f"  {path}: {', '.join(found)}")

    if problems:
        print()
        for problem in problems:
            print(f"  REFUSED  {problem}")
        die(f"{len(problems)} name problem(s). Nothing was written.")

    if not apply:
        print("\nDry run. Re-run with --apply --dev-subjects-only to publish.")
        return
    if not dev_subjects_only:
        die("--apply needs --dev-subjects-only. catalog.json lands in git, so "
            "publishing is the moment hard rule #1 applies to this dev stack's "
            "names. `--help` says exactly what you are attesting to.")

    # Bytes first, then `catalog.json`, then `manifest.json`. The order is the
    # loader's diagnostics read backwards: it reads catalog.json first and says
    # "#284 has not landed" when it is absent, which is the right message for a
    # bucket that has never been published to and the wrong one for a publish
    # that was interrupted. Writing catalog.json before manifest.json means an
    # interrupted publish leaves the state whose message is accurate — "catalog
    # exists but manifest does not; the fixture is incomplete".
    for node_id in files:
        node = next(n for n in catalog["nodes"] if n["path"] == paths[node_id])
        s3.put_object(Bucket=seed_bucket, Key=node["source"],
                      Body=blobs[node_id], ContentType=node["content_type"])
    print(f"\n{len(files)} object(s) -> s3://{seed_bucket}/{fixture_version}/media/")

    for name, doc in (("catalog.json", catalog), ("manifest.json", manifest)):
        body = document(doc)
        s3.put_object(Bucket=seed_bucket, Key=f"{fixture_version}/{name}",
                      Body=body, ContentType="application/json")
        target = FIXTURE_DIR / fixture_version / name
        os.makedirs(target.parent, exist_ok=True)
        target.write_bytes(body)
        print(f"{name} -> s3://{seed_bucket}/{fixture_version}/{name}  and  {target}")

    print("\nCommit the two documents — they are the fixture; the bucket holds a "
          "copy.\nA machine picks it up with ./studio/scripts/dev-aws-seed.sh.")


@main.command("load")
@click.option("--fixture-version", default="v1", show_default=True,
              help="Which published fixture to load.")
@click.option("--seed-bucket", default=SEED_BUCKET, show_default=True,
              help="Where the fixture lives.")
@click.option("--email", help="The dev account that will own the library. "
                              "Defaults to $STUDIO_DEV_USER_EMAIL.")
def cmd_load(fixture_version, seed_bucket, email):
    """Load the published fixture into this machine's dev stack.

    The other half of `publish`, and it replaces `scripts/dev-aws-seed.sh` —
    which still works, because it now calls this. See the section comment above
    on why 71 seconds of shell became about one second of Python: the bytes were
    being pulled through the machine and every object cost an `aws` process.

    **Not a merge.** A row the fixture describes is written as the fixture
    describes it, over whatever was there. Refilling a stack is what this is for.
    """
    bucket, table = source()
    ddb = ddbc.client()
    if not ddbc.table_exists(ddb):
        die(f"no table '{table}'. Run scripts/dev-aws-setup.sh first.")
    s3 = s3c.client()

    address = email or os.environ.get("STUDIO_DEV_USER_EMAIL", "").strip()
    if not address:
        die("no --email and no STUDIO_DEV_USER_EMAIL, so the library would have "
            "no member. Run ./studio/scripts/dev-user.sh first.")
    pool = profiles.value("cognito_user_pool_id")

    catalog, manifest = fixture_documents(s3, seed_bucket, fixture_version)
    broken = problems(catalog, manifest)
    if broken:
        for problem in broken:
            print(f"  REFUSED  {problem}")
        die(f"{len(broken)} problem(s) in the fixture. Nothing was written.")

    lib = library_id(bucket)
    owner = owner_sub(pool, address)
    items = rows(catalog, manifest, bucket, lib, owner)

    print(f"fixture     s3://{seed_bucket}/{fixture_version}/")
    print(f"into        s3://{bucket}/  +  {table}")
    print(f"library     {lib}  ({catalog.get('library_name') or 'Studio'})")
    print(f"owner       {address}")

    objects = copy_blobs(s3, seed_bucket, bucket, catalog)
    print(f"\n  objects   {objects:>4}  copied server-side "
          f"({manifest.get('total_bytes', 0)} bytes, never through this machine)")
    written = write_rows(ddb, table, items)
    print(f"  rows      {written:>4}  written")
    adopt_roots(ddb, table, catalog, bucket)
    entities = len(catalog.get("entities") or [])
    print(f"  entities  {entities:>4}  adopted their root folder")
    print("\nSeeded. Start the app with ./studio/scripts/dev-up.sh")
