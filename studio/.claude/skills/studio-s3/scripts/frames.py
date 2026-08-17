# /// script
# requires-python = ">=3.13"
# dependencies = ["boto3", "imageio-ffmpeg"]
# ///
"""frames.py — pull still frames out of a run's video. Two jobs, both load-bearing.

**Chaining.** A video engine can only continue a shot from a start frame, so a
sequence longer than one generation needs the previous clip's LAST FRAME as the
next clip's `start_image`. Several skills describe that workflow; this is what
performs it.

    uv run frames.py last <runref> --add-input   # -> projects/<p>/input/<p>_in_<n>.png

**Verification.** A generated clip has to be looked at before more money is spent
on top of it, and a video cannot be read the way an image can. `grid` samples
frames across the clip and tiles them into one contact sheet, which *can* be
read — including by an agent, which otherwise has no way to check its own output.

    uv run frames.py grid <runref> --count 4 --dest /tmp/check

WHERE FRAMES GO
---------------
`--add-input` writes to the **project's input pool** (`projects/<p>/input/`),
never to a character's `reference/`. An extracted frame is model output;
promoting it into the identity set feeds generated pixels back in as identity
and compounds drift. Chaining from the input pool is correct and expected —
curating into a character's `reference/` is a separate, deliberate decision.

CHAINS — the reference set for a scene is the SCENE'S OWN FRAMES
---------------------------------------------------------------
When rendering shot N of a chained scene, its `reference_images` should be the
frames that scene has already produced — the image shot 1 started from, plus each
handoff frame since — **not** the character's `reference/` set.

Those frames are on-model for *this* scene: same location, wardrobe, lighting and
grade. The curated set is a different context, so feeding it in mid-scene pulls
the render toward that other context and fights the continuity the chain exists
to hold. Reach into `reference/` only when the scene introduces something the
existing frames cannot show, and then send only the images that show it.

`--chain` records each handoff frame as it is produced, so the list is derived
rather than remembered:

    uv run frames.py last <runref> --add-input --chain <project>/<slug>
    uv run frames.py chain <project>/<slug> --seed <s3 key of shot 1's start image>
    uv run frames.py chain <project>/<slug> --args --max 7   # -> --key … --key …

`--max` keeps the seed plus the most recent frames, because every engine caps
`reference_images` (Kling 7). The seed is kept because it anchors the look the
whole scene inherits.

ffmpeg comes from the `imageio-ffmpeg` wheel, so there is no system install.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths as P  # noqa: E402
import runs as R  # noqa: E402
from s3_common import BUCKET, client, die  # noqa: E402
from video import VIDEO_EXT, contact_grid, grab  # noqa: E402  — shared ffmpeg layer

PROJECTS_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.py")


def fetch_video(s3, ref: str, project: str | None, tmp: str) -> tuple[str, str, str]:
    """Resolve a runref to exactly one video and download it. -> (project, run_id, path)."""
    run_project, run_id = R.resolve_run(s3, ref, default_project=project)
    keys = R.resolve_output_keys(s3, ref, default_project=project)
    vids = [k for k in keys if k.lower().endswith(VIDEO_EXT)]
    if not vids:
        die(f"{ref}: no video output (got {keys or 'nothing'})")
    if len(vids) > 1:
        die(f"{ref}: {len(vids)} videos — append #N to pick one")
    local = os.path.join(tmp, os.path.basename(vids[0]))
    s3.download_file(BUCKET, vids[0], local)
    return run_project, run_id, local


def chain_key(project: str, slug: str) -> str:
    return P.chain_key(project, R.slugify(slug))


def load_chain(s3, project: str, slug: str) -> dict:
    """An absent chain reads as an empty one — `read_json` returns None for a
    missing key rather than raising, so check the value, not just for an error."""
    doc = None
    try:
        doc = R.read_json(s3, chain_key(project, slug))
    except Exception:
        doc = None
    return doc or {"chain": f"{project}/{R.slugify(slug)}", "project": project,
                   "slug": R.slugify(slug), "seed": None, "frames": []}


def chain_add(s3, project: str, slug: str, key: str, from_run: str | None) -> dict:
    doc = load_chain(s3, project, slug)
    if any(f["key"] == key for f in doc["frames"]):
        return doc
    doc["frames"].append({"n": len(doc["frames"]) + 1, "key": key,
                          "from_run": from_run, "added": R._now()})
    R.write_json(s3, chain_key(project, slug), doc)
    return doc


def chain_keys(doc: dict, max_n: int | None) -> list[str]:
    """Seed first, then handoff frames. Trimming drops the OLDEST middle frames.

    The seed anchors the look the whole scene inherits, and the most recent
    frames carry the current state, so when an engine's cap forces a choice both
    ends are kept and the middle gives way.
    """
    keys = ([doc["seed"]] if doc.get("seed") else []) + [f["key"] for f in doc["frames"]]
    if max_n is None or len(keys) <= max_n:
        return keys
    if doc.get("seed"):
        return [keys[0]] + keys[-(max_n - 1):]
    return keys[-max_n:]


def add_to_input_pool(project: str, path: str) -> str:
    """Hand off to projects.py so pool numbering stays in one place.

    It answers in JSON, so the assigned key is read rather than reconstructed.
    This used to scrape a log line with a regex and rebuild the key by
    re-appending the extension — which yielded None whenever the message shape
    changed, and only failed AFTER the upload had already happened.
    """
    out = subprocess.run(["uv", "run", PROJECTS_PY, "add-inputs", project, path, "--json"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        die(f"could not add to project {project}'s input pool:\n{out.stderr.strip()}")
    try:
        added = json.loads(out.stdout)
    except json.JSONDecodeError:
        die(f"projects.py did not answer in JSON:\n{out.stdout}\n{out.stderr}")
    if not added:
        die(f"projects.py added nothing for {path}")
    return added[0]["key"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Still frames out of a run's video.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name, help_ in (("last", "the final frame — the chaining handoff"),
                        ("at", "one frame at a given time"),
                        ("grid", "a contact sheet, for looking at the clip")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("ref", help="runref: <project>/<run_id>, <project>/latest, "
                                   "a slug fragment, #N")
        p.add_argument("--project", help="project, when the runref does not carry one")
        p.add_argument("--dest", help="directory to write the image into")
        if name == "at":
            p.add_argument("--time", type=float, required=True, help="seconds")
        if name == "grid":
            p.add_argument("--count", type=int, default=4, help="frames to sample (default 4)")
        else:
            p.add_argument("--add-input", action="store_true",
                           help="upload into the PROJECT's input pool "
                                "(never a character's reference/)")
            p.add_argument("--chain", metavar="SLUG",
                           help="also record this frame in a scene chain, so the next "
                                "shot's reference_images can be derived rather than recalled")

    p = sub.add_parser("chain", help="the frames a scene has produced so far")
    p.add_argument("ref", help="<project>/<slug>")
    p.add_argument("--seed", help="S3 key of the image shot 1 started from")
    p.add_argument("--add-key", action="append", metavar="KEY", dest="add_keys",
                   help="record an existing S3 key as the next frame in the chain. "
                        "Repeatable, order preserved. For frames produced outside "
                        "`last --add-input`, or to reconstruct a chain after the fact.")
    p.add_argument("--args", action="store_true",
                   help="print as `--key K --key K …`, ready to paste into a run")
    p.add_argument("--max", type=int, dest="max_n",
                   help="cap the list (Kling takes 7); keeps the seed and the newest")

    args = ap.parse_args()
    s3 = client()

    if args.cmd == "chain":
        if "/" not in args.ref:
            die("chain ref must be <project>/<slug>")
        project, slug = args.ref.split("/", 1)
        doc = load_chain(s3, project, slug)
        if args.seed:
            doc["seed"] = args.seed
            R.write_json(s3, chain_key(project, slug), doc)
        for k in (args.add_keys or []):
            doc = chain_add(s3, project, slug, k, None)
        keys = chain_keys(doc, args.max_n)
        if not keys:
            die(f"chain {project}/{slug} is empty — record frames with "
                f"`last <runref> --add-input --chain {slug}`, and set the first "
                f"shot's source with --seed")
        if args.args:
            print(" ".join(f"--key {k}" for k in keys))
        else:
            for k in keys:
                print(k)
        return 0

    tmp = tempfile.mkdtemp(prefix="frames-")
    project, run_id, src = fetch_video(s3, args.ref, args.project, tmp)
    dest_dir = args.dest or tmp
    os.makedirs(dest_dir, exist_ok=True)

    if args.cmd == "grid":
        out = os.path.join(dest_dir, f"{run_id}_grid.jpg")
        times = contact_grid(src, args.count, out)
        print(out)
        print("sampled at: " + ", ".join(f"{t:.1f}s" for t in times))
        return 0

    if args.cmd == "last":
        out = grab(src, None, os.path.join(dest_dir, f"{run_id}_last.png"), from_end=0.2)
    else:
        out = grab(src, args.time, os.path.join(dest_dir, f"{run_id}_t{args.time:g}.png"))
    print(out)

    if args.add_input:
        key = add_to_input_pool(project, out)
        print(key)
        if args.chain:
            doc = chain_add(s3, project, args.chain, key, f"{project}/{run_id}")
            print(f"chain {doc['chain']}: {len(doc['frames'])} frame(s)")
    elif getattr(args, "chain", None):
        die("--chain needs --add-input: a chain records S3 keys, and the frame "
            "has to be in the bucket before it has one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
