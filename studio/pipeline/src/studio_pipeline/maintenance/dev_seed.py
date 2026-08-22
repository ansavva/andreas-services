"""`studio dev-seed` — promote a fixture out of this machine's dev stack.

The dev fixture is **promoted, not generated**. A human drives the CLI against
their own dev stack as ordinary work; a handful of the nodes that produces
become the fixture every other machine downloads. `publish` reads that stack's
catalog, copies the chosen blobs into the seed bucket, and writes the two
documents `scripts/dev-aws-seed.sh` loads.

    studio dev-seed tree                       what is in this stack, by path
    studio dev-seed publish --path A --path B  a dry run: what would be promoted
    studio dev-seed publish --path A --apply --placeholders-only

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
repository. The guard below refuses rather than trusting the human to have used
placeholders — see `name_problems`, which is also honest about the several
things it cannot catch.
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
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die
from studio_pipeline.maintenance import catalog_seed as cs

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
    bucket, table = s3c.bucket(), ddbc.TABLE
    for name in (bucket, table):
        if "prod" in name:
            die(f"refusing to read '{name}' — a fixture is promoted from a dev "
                "stack, never from production. Run scripts/dev-setup.sh, or "
                "export STUDIO_S3_BUCKET and STUDIO_CATALOG_TABLE for the dev "
                "stack you mean.")
    return bucket, table


def read_library(ddb, library: str | None = None) -> dict:
    """The whole library as `{lib, root, nodes: {id: row}}`.

    One scan, for the reason `catalog_seed.already_seeded` scans: a dev stack is
    small, and a GSI query would silently omit any row missing one of the
    index's key attributes — which is a row this command should refuse over, not
    skip.
    """
    libraries, metas = {}, {}
    for item in ddbc.scan(ddb):
        pk, sk = item.get("pk", ""), item.get("sk", "")
        if sk == "META" and pk.startswith("LIB#"):
            libraries[pk.removeprefix("LIB#")] = item
        elif sk == "META" and pk.startswith("NODE#") and item.get("node_id"):
            metas[item["node_id"]] = item

    if not libraries:
        die(f"no library in '{ddbc.TABLE}'. Sign in to the local app and put "
            "something in it first — a fixture is promoted from work, not built.")
    if library is None and len(libraries) > 1:
        die("this table holds more than one library; name one with --library:\n"
            + "\n".join(f"       {lib}  ({row.get('name')})"
                        for lib, row in sorted(libraries.items())))
    lib = library or next(iter(libraries))
    if lib not in libraries:
        die(f"no library '{lib}' in '{ddbc.TABLE}'")

    root = libraries[lib].get("root_node")
    nodes = {nid: row for nid, row in metas.items() if row.get("lib") == lib}
    if root not in nodes:
        die(f"library {lib} names root node {root}, which has no row. The "
            "catalog is broken; `studio catalog verify` reports on it.")
    return {"lib": lib, "root": root, "name": libraries[lib].get("name") or "Studio",
            "nodes": nodes}


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

#: The placeholders the repo uses in place of a character or project name.
#: `<…>` covers the literal placeholders that appear in prose; `subject-a` and
#: its siblings are what the two test fixtures already use, which is why they
#: are the shape a human is most likely to reach for.
PLACEHOLDER = re.compile(r"^(?:<[a-z]+>|subject-[a-z0-9-]+|demo|sample|fixture|example)$")

#: A personal name's shape: `Ada`, `Ada Lovelace`, `Ada-Lovelace`. Deliberately
#: narrow. It fires on a capitalised alphabetic word and nothing else, so
#: `IMG_1966_Original.JPG` and an uppercase extension pass — #284 asks for an
#: awkward name, and refusing every capital would refuse the shape it wants.
TITLE_CASE = re.compile(r"^[^\W\d_][a-zß-ɏ]+(?:[ _-][^\W\d_][a-zß-ɏ]+)*$")

#: Any capitalised word of three letters or more, for the report. Not a refusal
#: — see `name_problems` on why.
TITLE_TOKEN = re.compile(r"\b[A-Z][a-z]{2,}\b")


def _title_case(text: str) -> bool:
    return bool(TITLE_CASE.match(text)) and text[:1].isupper()


def stem(name: str) -> str:
    """A file's name without its extension; a folder's name unchanged."""
    base, dot, ext = name.rpartition(".")
    return base if dot and base and ext.isalnum() and len(ext) <= 5 else name


def name_positions(paths: dict[str, str]) -> dict[str, list[str]]:
    """Every segment sitting where the layout says a NAME goes, by tree.

    `paths.py` is the one module that knows the bucket's shape and it says a
    character's name is the segment under `characters/` and a project's slug is
    the segment under `projects/`. Those are the two positions where a name is
    provably a name rather than a guess, which is what makes the check on them
    a refusal and everything else a report.
    """
    found = collections.defaultdict(set)
    for path in paths.values():
        parts = path.split("/") if path else []
        if len(parts) >= 2 and parts[0] in (P.CHARACTERS, P.PROJECTS):
            found[parts[0]].add(parts[1])
    return {tree: sorted(names) for tree, names in found.items()}


def name_problems(all_paths: dict[str, str], published: dict[str, str]) -> list[str]:
    """Every reason this promotion may not be published, one per line.

    **WHAT IT CHECKS**

    1. **The whole stack, not just the selection.** Every segment in a name
       position anywhere in the source library must be placeholder-shaped. #284
       is explicit that generating naturally and sanitising afterwards is the
       wrong order — by then the name is already in the bucket, the run JSON and
       the keys — so the property being tested is "this stack was *driven* with
       placeholders", and a stack with one real character name in a corner of it
       fails it whether or not that corner is being promoted.
    2. **Every published segment**, for the personal-name shape: a capitalised
       alphabetic word, alone or hyphen/space/underscore-joined to more of them.

    **WHAT IT CANNOT CATCH.** None of these is hypothetical:

    * **A real name that is slug-shaped.** `projects/mira/` and `projects/demo/`
      are the same string to a regex. Every lowercase first name in the world
      passes this, which is exactly why `--placeholders-only` exists: the
      machine checks the shape and the human attests to the provenance.
    * **A name in a promoted file's BYTES.** A prompt in `request.json`, a
      caption, a bible. Text objects are scanned and their capitalised tokens
      *reported* — but a report is a thing a human reads, and lowercase prose
      naming someone is not reported at all. The reason it is a report rather
      than a refusal is that a refusal on capitalised words in prose would fire
      on every sentence and be turned off within a week.
    * **A face.** The fixture is media. A still or a clip of a real person
      carries an identity no text check has any purchase on, and it goes into
      the bucket rather than into git — outside hard rule #1's letter, and
      squarely inside what a fixture on every machine should not contain.
    * **Anything but a first name.** A surname, a nickname, an alias, an
      initial, a name in another script, a name that happens to also be an
      ordinary word.
    * **The attestation itself.** `--placeholders-only` is a flag. Nothing
      verifies it, and nothing can.
    """
    problems = []

    for tree, names in sorted(name_positions(all_paths).items()):
        bad = [n for n in names if not PLACEHOLDER.match(n)]
        if bad:
            problems.append(
                f"{tree}/ holds {', '.join(repr(n) for n in bad)} — a fixture is "
                "promoted from a stack DRIVEN with placeholders "
                "(subject-a, <project>), not from one sanitised afterwards. "
                "This is the whole stack, not just what you selected.")

    for path in sorted(published.values()):
        for segment in path.split("/"):
            if _title_case(stem(segment)):
                problems.append(
                    f"{path}: segment {segment!r} has the shape of a personal "
                    "name. Rename it in the dev stack and re-publish — "
                    "catalog.json lands in git.")
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
                                    or cs.content_type(path))
            objects[key] = {"size": len(body),
                            "sha256": hashlib.sha256(body).hexdigest()}
        nodes.append(node)

    catalog = {"version": 1, "library_name": library["name"], "nodes": nodes}
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
@click.option("--placeholders-only", is_flag=True,
              help="ATTEST that this dev stack was DRIVEN with placeholder names "
                   "(subject-a, <project>) from the first generation — not "
                   "renamed afterwards — and that you have read the capitalised "
                   "tokens reported from the promoted text. Required for --apply. "
                   "Nothing verifies this; the checks catch shapes, not people.")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
def cmd_publish(wanted, paths_from, fixture_version, seed_bucket, library,
                max_objects, placeholders_only, apply):
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

    published = {nid: paths[nid] for nid in picked["all"]}
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

    problems = name_problems(paths, published)
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
        print("\nDry run. Re-run with --apply --placeholders-only to publish.")
        return
    if not placeholders_only:
        die("--apply needs --placeholders-only. catalog.json lands in git, so "
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
