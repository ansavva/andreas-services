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
import hashlib
import json
import os
import re

import click

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.errors import die
from studio_pipeline.maintenance import catalog_migrate as CM

#: The one "tree" `name_positions` reports under. An entity root is a child of
#: the library root now, so there is no `characters/` or `projects/` folder to
#: name the group after — every top-level folder is somebody's slug.
ENTITY_ROOTS = "entity roots"

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
DEV_SUBJECTS = frozenset({
    "jason",                                  # the seed fixture's subject
    "subject-a", "subject-b",                 # what the test fixtures use
    "demo", "sample", "fixture", "example",   # the generic stand-ins
})

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
        if parts and parts[0]:
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
@click.option("--seed-bucket", default="studio-dev-seed-us-east-1", show_default=True,
              help="the shared seed bucket (STUDIO_DEV_SEED_BUCKET on the loader)")
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
