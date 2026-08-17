"""projects.py — a PROJECT is the unit of production, and this manages them.

    projects/<project>/
        project.json    name, description, the characters involved
        runs/           append-only history (runs.py)
        chains/         a scene's own frames, in order (frames.py)
        scenes/         runs cut into one continuous take (scenes.py)
        movies/         scenes cut into one piece (movies.py)
        favorites/      keepers, copied out of runs (runs.py favorite)
        input/          the working pool — uploads and frames to drive from

PROJECT vs CHARACTER
--------------------
A character is an identity record; a project is a piece of work. They used to be
the same folder, which meant work involving two characters had nowhere to live
and work involving none had to borrow a fake character called `misc`. Now a
project names the characters it involves, and any run inside it records which
ones it actually used.

Nothing is inferred: every generating command takes an explicit `--project`.
Guessing where output lands is the one thing that cannot be undone by rerunning
a command, so the answer is always asked for rather than assumed.

THE INPUT POOL
--------------
`input/` is the project's working material — an upload to edit, a frame pulled
off a clip to drive the next one. It is uncapped and never sent "in full"; it is
picked from. That is the opposite of a character's `reference/`, which is
identity and is chosen from a described index (see studio-character).

Pool basenames are `<project>_in_<n>.<ext>`, numbered from the PROJECT — not
from a character. The first projects happen to be named after characters, so
those agreed by coincidence; deriving from the project is what keeps the next
project's pool correctly named.

CLI
---
    uv run projects.py list
    uv run projects.py new <project> --character <name> --description "…"
    uv run projects.py show <project>
    uv run projects.py add-inputs <project> file.png [file2.png …] [--json]
    uv run projects.py inputs <project> [--json|--presign]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import re
import sys


from studio_pipeline.store import paths as P  # noqa: E402
from studio_pipeline.store import s3 as s3c  # noqa: E402

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
PROJECT_FILE = "project.json"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ── the record ──────────────────────────────────────────────────────────────

def read_project(s3, project: str) -> dict | None:
    try:
        body = s3.get_object(Bucket=s3c.BUCKET, Key=P.project_json_key(project))["Body"].read()
    except Exception:  # noqa: BLE001 — a missing project.json is not an error
        return None
    return json.loads(body)


def write_project(s3, doc: dict) -> str:
    key = P.project_json_key(doc["name"])
    s3.put_object(Bucket=s3c.BUCKET, Key=key,
                  Body=(json.dumps(doc, indent=2) + "\n").encode(),
                  ContentType="application/json")
    return key


def require_project(s3, project: str | None) -> str:
    """The one place a missing --project is turned into a usable error.

    It lists what exists, because the useful answer to "which project?" is the
    set of real options, not the name of the flag that was left out.
    """
    if not project:
        have = P.list_projects(s3)
        die("no project given. Every generating command needs --project.\n"
            f"       existing projects: {', '.join(have) or '(none yet)'}\n"
            "       create one with: projects.py new <project>")
    P.check_slug(project, "project name")
    return project


# ── the input pool ──────────────────────────────────────────────────────────

def pool_max_index(s3, project: str) -> int:
    """Highest N among `<project>_in_<n>.<ext>` already in the pool."""
    pat = re.compile(rf"^{re.escape(project)}_in_(\d+)\.")
    hi = 0
    for key in s3c.list_keys(s3, P.input_prefix(project)):
        if (m := pat.match(os.path.basename(key))):
            hi = max(hi, int(m.group(1)))
    return hi


def add_inputs(s3, project: str, paths: list[str]) -> list[dict]:
    """Upload local files into the pool, numbered on from what is there."""
    n = pool_max_index(s3, project)
    added = []
    for local in paths:
        if not os.path.isfile(local):
            die(f"not a file: {local}")
        ext = os.path.splitext(local)[1].lower()
        if ext not in IMG_EXTS:
            die(f"{local}: the input pool holds images ({', '.join(sorted(IMG_EXTS))})")
        n += 1
        key = P.input_key(project, n, ext)
        ct = mimetypes.guess_type(local)[0] or "application/octet-stream"
        s3.upload_file(local, s3c.BUCKET, key, ExtraArgs={"ContentType": ct})
        added.append({"key": key, "n": n, "from": local})
    return added


def input_keys(s3, project: str) -> list[str]:
    return [k for k in s3c.list_keys(s3, P.input_prefix(project))
            if os.path.splitext(k)[1].lower() in IMG_EXTS]


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="Every project, with the characters it names.")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("new", help="Create a project.")
    p.add_argument("project")
    p.add_argument("--character", action="append", dest="characters",
                   help="A character this project involves. Repeatable.")
    p.add_argument("--description", default="")

    p = sub.add_parser("init", help="Write project.json for a project that has "
                                    "content but no record (e.g. one that predates it).")
    p.add_argument("project")
    p.add_argument("--description", default="")

    p = sub.add_parser("show", help="A project's record and what it holds.")
    p.add_argument("project")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("add-inputs", help="Upload file(s) into the project's input pool.")
    p.add_argument("project")
    p.add_argument("files", nargs="+")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("inputs", help="The project's input pool.")
    p.add_argument("project")
    p.add_argument("--json", action="store_true")
    p.add_argument("--presign", action="store_true")
    p.add_argument("--expires", type=int, default=3600)

    args = ap.parse_args()
    s3 = s3c.client()

    if args.cmd == "list":
        names = P.list_projects(s3)
        if args.json:
            print(json.dumps([read_project(s3, n) or {"name": n} for n in names], indent=2))
        elif names:
            for n in names:
                doc = read_project(s3, n) or {}
                chars = ", ".join(doc.get("characters") or []) or "—"
                print(f"{n:<20} characters: {chars}")
        else:
            print("(no projects yet — create one with `projects.py new <project>`)",
                  file=sys.stderr)
        return 0

    project = P.check_slug(args.project, "project name")

    if args.cmd == "new":
        if read_project(s3, project):
            die(f"project {project!r} already exists")
        for c in (args.characters or []):
            if c not in P.list_characters(s3):
                die(f"no character {c!r} (see `character.py list`)")
        doc = {"name": project, "created": _now(),
               "description": args.description,
               "characters": sorted(args.characters or [])}
        print(write_project(s3, doc))
        return 0

    if args.cmd == "init":
        if read_project(s3, project):
            die(f"project {project!r} already has a project.json")
        if project not in P.list_projects(s3):
            die(f"nothing under {P.project_prefix(project)}/ — use `new` to create a project")
        # The characters are read back out of the runs rather than asked for:
        # the history already knows, and asking invites a wrong answer.
        from studio_pipeline.store import runs as R
        chars: set[str] = set()
        for run_id in R.list_runs(s3, project):
            chars.update(R.run_characters(s3, project, run_id))
        doc = {"name": project, "created": _now(),
               "description": args.description, "characters": sorted(chars)}
        print(write_project(s3, doc))
        return 0

    if args.cmd == "show":
        doc = read_project(s3, project) or {"name": project,
                                            "note": "no project.json — created before the record existed"}
        counts = {kind: len(P.list_ids(s3, P.project_dir_prefix(project, kind)))
                  for kind in ("runs", "scenes", "movies")}
        counts["favorites"] = len(s3c.list_keys(s3, P.favorites_prefix(project)))
        counts["input"] = len(input_keys(s3, project))
        counts["chains"] = len(s3c.list_keys(s3, P.chains_prefix(project)))
        doc = {**doc, "holds": counts}
        if args.json:
            print(json.dumps(doc, indent=2))
        else:
            print(json.dumps(doc, indent=2))
        return 0

    if args.cmd == "add-inputs":
        added = add_inputs(s3, project, args.files)
        if args.json:
            print(json.dumps(added, indent=2))
        else:
            for a in added:
                print(a["key"])
        return 0

    if args.cmd == "inputs":
        keys = input_keys(s3, project)
        if not keys:
            print(f"(project {project} has no input pool yet)", file=sys.stderr)
            return 0
        if args.presign:
            urls = [s3.generate_presigned_url("get_object",
                                              Params={"Bucket": s3c.BUCKET, "Key": k},
                                              ExpiresIn=args.expires) for k in keys]
            print(json.dumps(urls, indent=2) if args.json else "\n".join(urls))
        elif args.json:
            print(json.dumps(keys, indent=2))
        else:
            print("\n".join(keys))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
