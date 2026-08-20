"""`studio frames` — pull still frames out of a run's video. Two jobs, both load-bearing.

**Chaining.** A video engine can only continue a shot from a start frame, so a
sequence longer than one generation needs the previous clip's LAST FRAME as the
next clip's `start_image`. Several skills describe that workflow; this is what
performs it.

    studio frames last <runref> --add-input   # -> projects/<p>/input/<p>_in_<n>.png

**Verification.** A generated clip has to be looked at before more money is spent
on top of it, and a video cannot be read the way an image can. `grid` samples
frames across the clip and tiles them into one contact sheet, which *can* be
read — including by an agent, which otherwise has no way to check its own output.

    studio frames grid <runref> --count 4 --dest /tmp/check

WHERE FRAMES GO
---------------
`--add-input` writes to the **project's input pool** (`projects/<p>/input/`),
never to a character's `reference/`. An extracted frame is model output;
promoting it into the identity set feeds generated pixels back in as identity
and compounds drift. Chaining from the input pool is correct and expected —
curating into a character's `reference/` is a separate, deliberate decision.

CHAINS — an ordered list of one sequence's own frames
-----------------------------------------------------
When rendering shot N of a sequence, its `reference_images` should be the frames
that sequence has already produced — the image shot 1 started from, plus each
handoff frame since — **not** the character's `reference/` set.

**A planned scene does not need this.** `studio scenes` derives that list from
`scene.json`, where both halves already live. A chain is for a sequence with no
scene behind it, which is the only thing it was ever actually used for: two
records of one sequence, kept in sync by hand, is the shape of every bug this
repo has had to write a migrator for.

Those frames are on-model for *this* scene: same location, wardrobe, lighting and
grade. The curated set is a different context, so feeding it in mid-scene pulls
the render toward that other context and fights the continuity the chain exists
to hold. Reach into `reference/` only when the scene introduces something the
existing frames cannot show, and then send only the images that show it.

`--chain` records each handoff frame as it is produced, so the list is derived
rather than remembered:

    studio frames last <runref> --add-input --chain <slug>
    studio frames chain <project>/<slug> --seed <s3 key of shot 1's start image>
    studio frames chain <project>/<slug> --args --max 7   # -> --key … --key …

`--chain` takes a bare slug or the qualified `<project>/<slug>` — the project
comes from the runref either way. Both spellings work because `chain` requires
the qualified one and these two never did, and a rule that differs between
sibling commands is the rule people get wrong.

`--max` keeps the seed plus the most recent frames, because every engine caps
`reference_images` (Kling 7). The seed is kept because it anchors the look the
whole scene inherits.

For anything planned with `studio scenes`, use `studio scenes handoff` instead:
it records the frame on the shot itself, so there is no second list.

ffmpeg comes from the `imageio-ffmpeg` wheel, so there is no system install.
"""
from __future__ import annotations

import os
import tempfile

import click

from studio_pipeline.adapters.ffmpeg import (  # noqa: E402  — shared ffmpeg layer
    VIDEO_EXT,
    contact_grid,
    grab,
)
from studio_pipeline.adapters.s3 import BUCKET, client, die  # noqa: E402
from studio_pipeline.domain import paths as P  # noqa: E402
from studio_pipeline.domain import projects as PROJECTS
from studio_pipeline.domain import runs as R  # noqa: E402


def fetch_video(s3, ref: str, project: str | None, tmp: str) -> tuple[str, str, str]:
    """Resolve a runref to exactly one video and download it. -> (project, run_id, path)."""
    run_project, run_id = R.resolve_run(ref, default_project=project)
    keys = R.resolve_output_keys(ref, default_project=project)
    vids = [k for k in keys if k.lower().endswith(VIDEO_EXT)]
    if not vids:
        die(f"{ref}: no video output (got {keys or 'nothing'})")
    if len(vids) > 1:
        die(f"{ref}: {len(vids)} videos — append #N to pick one")
    local = os.path.join(tmp, os.path.basename(vids[0]))
    s3.download_file(BUCKET, vids[0], local)
    return run_project, run_id, local


def chain_slug(slug: str) -> str:
    """A chain slug, accepting the `<project>/<slug>` form `chain` takes.

    `slugify` turns `/` into `-`, so `--chain <project>/<slug>` on `last`/`at`
    used to create a chain called `<project>-<slug>` — in the right project, but
    under a name `frames chain <project>/<slug>` could then never find. It went
    unnoticed because a chain that does not exist reads as an empty one, so the
    only symptom was a second chain quietly appearing beside the real one. The
    module docstring taught that exact form, which is how it was reached.

    Both spellings are accepted now rather than one being refused: `chain`
    requires the qualified form and these two never did, and a rule that differs
    between sibling commands is the rule people get wrong.
    """
    return R.slugify(slug.split("/", 1)[1] if "/" in slug else slug)


def chain_key(project: str, slug: str) -> str:
    return P.chain_key(project, chain_slug(slug))


def load_chain(s3, project: str, slug: str) -> dict:
    """An absent chain reads as an empty one — `read_json` returns None for a
    missing key rather than raising, so check the value, not just for an error."""
    doc = None
    try:
        doc = R.read_json(chain_key(project, slug))
    except Exception:
        doc = None
    return doc or {"chain": f"{project}/{chain_slug(slug)}", "project": project,
                   "slug": chain_slug(slug), "seed": None, "frames": []}


def chain_add(s3, project: str, slug: str, key: str, from_run: str | None) -> dict:
    doc = load_chain(s3, project, slug)
    if any(f["key"] == key for f in doc["frames"]):
        return doc
    doc["frames"].append({"n": len(doc["frames"]) + 1, "key": key,
                          "from_run": from_run, "added": R._now()})
    R.write_json(chain_key(project, slug), doc)
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
    try:
        added = PROJECTS.add_inputs(client(), project, [path])
    except SystemExit as exc:
        die(f"could not add to project {project}'s input pool: {exc}")
    if not added:
        die(f"the project store added nothing for {path}")
    return added[0]["key"]


def _fetch(ref, project, dest):
    """Pull the run's video down and decide where frames will be written."""
    tmp = tempfile.mkdtemp(prefix="frames-")
    owner, run_id, src = fetch_video(client(), ref, project, tmp)
    dest_dir = dest or tmp
    os.makedirs(dest_dir, exist_ok=True)
    return owner, run_id, src, dest_dir


def _emit(project, run_id, out, add_input, chain):
    """Print the frame, and optionally put it in the pool and the chain."""
    print(out)
    if not add_input:
        if chain:
            die("--chain needs --add-input: a chain records S3 keys, and the frame "
                "has to be in the bucket before it has one")
        return
    key = add_to_input_pool(project, out)
    print(key)
    if chain:
        doc = chain_add(client(), project, chain, key, f"{project}/{run_id}")
        print(f"chain {doc['chain']}: {len(doc['frames'])} frame(s)")


@click.group(help=__doc__)
def main():
    pass


@main.command("last", epilog="\n\nArguments:\n  REF  runref: <project>/<run_id>, <project>/latest, a slug fragment, #N")
@click.argument("ref", required=True)
@click.option("--add-input", is_flag=True, help=("upload into the PROJECT's input pool (never a character's "
              "reference/)"))
@click.option("--chain", help=("also record this frame in a scene chain, so the next shot's "
              "reference_images can be derived rather than recalled"))
@click.option("--dest", help="directory to write the image into")
@click.option("--project", help="project, when the runref does not carry one")
def do_last(ref, add_input, chain, dest, project):
    """The final frame — the chaining handoff."""
    project, run_id, src, dest_dir = _fetch(ref, project, dest)
    out = grab(src, None, os.path.join(dest_dir, f"{run_id}_last.png"), from_end=0.2)
    _emit(project, run_id, out, add_input, chain)


@main.command("at", epilog="\n\nArguments:\n  REF  runref: <project>/<run_id>, <project>/latest, a slug fragment, #N")
@click.argument("ref", required=True)
@click.option("--add-input", is_flag=True, help=("upload into the PROJECT's input pool (never a character's "
              "reference/)"))
@click.option("--chain", help=("also record this frame in a scene chain, so the next shot's "
              "reference_images can be derived rather than recalled"))
@click.option("--dest", help="directory to write the image into")
@click.option("--project", help="project, when the runref does not carry one")
@click.option("--time", type=float, required=True, help="seconds")
def do_at(ref, add_input, chain, dest, project, time):
    """One frame at a given time."""
    project, run_id, src, dest_dir = _fetch(ref, project, dest)
    out = grab(src, time, os.path.join(dest_dir, f"{run_id}_t{time:g}.png"))
    _emit(project, run_id, out, add_input, chain)


@main.command("grid", epilog="\n\nArguments:\n  REF  runref: <project>/<run_id>, <project>/latest, a slug fragment, #N")
@click.argument("ref", required=True)
@click.option("--count", type=int, default=4, help="frames to sample (default 4)")
@click.option("--dest", help="directory to write the image into")
@click.option("--project", help="project, when the runref does not carry one")
def do_grid(ref, count, dest, project):
    """A contact sheet, for looking at the clip."""
    project, run_id, src, dest_dir = _fetch(ref, project, dest)
    out = os.path.join(dest_dir, f"{run_id}_grid.jpg")
    times = contact_grid(src, count, out)
    print(out)
    print("sampled at: " + ", ".join(f"{t:.1f}s" for t in times))


@main.command("chain", epilog="\n\nArguments:\n  REF  <project>/<slug>")
@click.argument("ref", required=True)
@click.option("--add-key", multiple=True, help=("record an existing S3 key as the next frame in the chain. "
              "Repeatable, order preserved. For frames produced outside `last "
              "--add-input`, or to reconstruct a chain after the fact."))
@click.option("--args", is_flag=True, help="print as `--key K --key K …`, ready to paste into a run")
@click.option("--max", "max_", type=int, help="cap the list (Kling takes 7); keeps the seed and the newest")
@click.option("--seed", help="S3 key of the image shot 1 started from")
def do_chain(ref, add_key, args, max_, seed):
    """The frames recorded for a scene chain, in order."""
    s3 = client()
    if "/" not in ref:
        die("chain ref must be <project>/<slug>")
    project, slug = ref.split("/", 1)
    doc = load_chain(s3, project, slug)
    if seed:
        doc["seed"] = seed
        R.write_json(chain_key(project, slug), doc)
    for k in add_key:
        doc = chain_add(s3, project, slug, k, None)
    keys = chain_keys(doc, max_)
    if not keys:
        die(f"chain {project}/{slug} is empty — record frames with "
            f"`last <runref> --add-input --chain {slug}`, and set the first "
            f"shot's source with --seed")
    if args:
        print(" ".join(f"--key {k}" for k in keys))
    else:
        for k in keys:
            print(k)
