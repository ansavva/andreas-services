"""`studio frames` — pull still frames out of a run's video. Two jobs, both load-bearing.

**Chaining.** A video engine can only continue a shot from a start frame, so a
sequence longer than one generation needs the previous clip's LAST FRAME as the
next clip's `start_image`. Several skills describe that workflow; this is what
performs it.

    studio frames last <runref> --add-input   # -> the project's input pool

**Verification.** A generated clip has to be looked at before more money is spent
on top of it, and a video cannot be read the way an image can. `grid` samples
frames across the clip and tiles them into one contact sheet, which *can* be
read — including by an agent, which otherwise has no way to check its own output.

    studio frames grid <runref> --count 4 --dest /tmp/check

A FRAME IS A NODE ID, NOT A KEY
-------------------------------
Everything this module hands back — a pooled frame, a chain entry, a seed — is a
**node id**. It was an S3 key until the entity model, and a key is invalidated
by any rename or move of the file it names: a chain built in the morning stopped
naming its own frames the moment somebody tidied the input pool. Nothing here
constructs an address either, because there is nothing left to construct — the
project record names its root and the tree is walked from it.

WHERE FRAMES GO
---------------
`--add-input` writes to the **project's input pool**, never to a character's
`reference/`. An extracted frame is model output; promoting it into the identity
set feeds generated pixels back in as identity and compounds drift. Chaining
from the input pool is correct and expected — curating into a character's
`reference/` is a separate, deliberate decision (hard rule #2b).

The pool no longer numbers what it is given, either. `--input N` is position N
in `GET /api/projects/<id>/inputs`, so a frame keeps whatever basename it
arrived with and `projects.add_inputs` reports the position it landed at.

CHAINS — an ordered list of one sequence's own frames
-----------------------------------------------------
When rendering shot N of a sequence, its `reference_images` should be the frames
that sequence has already produced — the image shot 1 started from, plus each
handoff frame since — **not** the character's `reference/` set.

**A planned scene does not need this.** `studio scenes` derives that list from
the scene's shot rows, where both halves already live. A chain is for a sequence
with no scene behind it, which is the only thing it was ever actually used for:
two records of one sequence, kept in sync by hand, is the shape of every bug
this repo has had to write a migrator for.

Those frames are on-model for *this* scene: same location, wardrobe, lighting and
grade. The curated set is a different context, so feeding it in mid-scene pulls
the render toward that other context and fights the continuity the chain exists
to hold. Reach into `reference/` only when the scene introduces something the
existing frames cannot show, and then send only the images that show it.

**A chain stays an ordinary JSON file** in the project's `chains/` folder, and
deliberately so: it is an ad-hoc sequence with no scene behind it, and the
entity model's open question #4 leaves `chains/` a folder rather than making a
sixth entity out of something that may not survive scenes maturing. What changed
is what is inside it — node ids — and how it is written: `store.write_into` a
folder node the project record leads to, rather than a key built from a slug.

    studio frames last <runref> --add-input --chain <slug>
    studio frames chain <project>/<slug> --seed <node id of shot 1's start image>
    studio frames chain <project>/<slug> --args --max 7   # -> --key … --key …

`--chain` takes a bare slug or the qualified `<project>/<slug>` — the project
comes from the runref either way. Both spellings work because `chain` requires
the qualified one and these two never did, and a rule that differs between
sibling commands is the rule people get wrong.

`--max` keeps the seed plus the most recent frames, because every engine caps
`reference_images` (Kling 7). The seed is kept because it anchors the look the
whole scene inherits.

For anything planned with `studio scenes`, use `studio scenes handoff` instead:
it records the frame on the shot row itself, so there is no second list.

ffmpeg comes from the `imageio-ffmpeg` wheel, so there is no system install.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

import click

from studio_pipeline.adapters.ffmpeg import (  # noqa: E402  — shared ffmpeg layer
    contact_grid,
    grab,
)
from studio_pipeline.adapters import api, store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
from studio_pipeline.domain import projects as PROJECTS  # noqa: E402
from studio_pipeline.domain import runs as R  # noqa: E402

#: The project subfolder a chain lives in. One of `paths.PROJECT_DIRS`, named
#: again here because this is the only module that resolves it — a convention,
#: looked up by name under the project's root and created if someone deleted
#: it, never a path this module builds.
CHAINS_FOLDER = "chains"


def fetch_video(ref: str, project: str | None, tmp: str) -> tuple[dict, str]:
    """Resolve a runref to exactly one video and download it. -> (run record, path).

    Returns the **record**, not a `(project, id)` pair, for the reason
    `runs.resolve_run` gives: every caller went straight on to read the run, and
    a pair meant a second round trip plus two more strings to keep in step.

    `resolve_output_nodes` does the extension filter and raises when a run holds
    no video at all, so the only case left here is the ambiguous one — a run
    with several clips, where picking silently would put the wrong frame at the
    front of the next shot.
    """
    record = R.resolve_run(ref, default_project=project)
    nodes = R.resolve_output_nodes(ref, default_project=project, kinds=R.VID_EXTS)
    if len(nodes) > 1:
        die(f"{ref}: {len(nodes)} videos — append #N to pick one")
    node = store.node(nodes[0])
    local = os.path.join(tmp, node.get("name") or f"{nodes[0]}.mp4")
    store.download_node(nodes[0], pathlib.Path(local))
    return record, local


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


def chain_name(slug: str) -> str:
    """The chain's filename inside `chains/`. A name, not a key."""
    return f"{chain_slug(slug)}.json"


def chains_folder(record: dict) -> str:
    """The project's `chains/` folder node, made if someone removed it.

    Self-healing by construction — the layout is convention and nothing depends
    on it existing, so a route that cannot find its folder makes one rather than
    failing. See `projects.py`.
    """
    return store.ensure_child_folder(record["root"], CHAINS_FOLDER)["id"]


def load_chain(record: dict, slug: str) -> dict:
    """An absent chain reads as an empty one.

    Absent means the file is not in `chains/`, which is what `store.child`
    answering None says. It does **not** mean a read that failed: the bare
    `except` this used to carry made a refusal look like an empty chain, and an
    empty chain is the state `chain_add` appends to — so a 403 would have
    started a second chain beside the real one rather than saying no.
    """
    folder = chains_folder(record)
    node = store.child(folder, chain_name(slug))
    if node is not None:
        try:
            return json.loads(store.read_node(node["id"]))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            die(f"chain {record['slug']}/{chain_slug(slug)} is not readable JSON: {exc}")
    return {"chain": f"{record['slug']}/{chain_slug(slug)}",
            "project": record["id"], "slug": chain_slug(slug),
            "seed": None, "frames": []}


def save_chain(record: dict, doc: dict) -> dict:
    """Write a chain back into the project's `chains/` folder.

    `write_into` rather than a keyed write: the folder node is resolved from the
    project record and the file keeps its identity across a replace, so anything
    already naming this chain still names it.
    """
    store.write_into(chains_folder(record), chain_name(doc["slug"]),
                     R.dumps(doc).encode(), content_type="application/json")
    return doc


def chain_add(record: dict, slug: str, node: str, from_run: str | None) -> dict:
    """Append one frame — a NODE ID — to a chain."""
    doc = load_chain(record, slug)
    if any(f.get("node") == node for f in doc["frames"]):
        return doc
    doc["frames"].append({"n": len(doc["frames"]) + 1, "node": node,
                          "from_run": from_run, "added": R._now()})
    return save_chain(record, doc)


def chain_nodes(doc: dict, max_n: int | None) -> list[str]:
    """Seed first, then handoff frames. Trimming drops the OLDEST middle frames.

    The seed anchors the look the whole scene inherits, and the most recent
    frames carry the current state, so when an engine's cap forces a choice both
    ends are kept and the middle gives way.
    """
    nodes = ([doc["seed"]] if doc.get("seed") else []) + [
        f["node"] for f in doc.get("frames") or [] if f.get("node")]
    if max_n is None or len(nodes) <= max_n:
        return nodes
    if doc.get("seed"):
        # `nodes[-0:]` is the WHOLE list, not the empty one, so `--max 1` on a
        # seeded chain would silently return every frame and the cap would do
        # nothing. `storyboard.scene_frames` guards the same edge.
        return [nodes[0]] + (nodes[-(max_n - 1):] if max_n > 1 else [])
    return nodes[-max_n:]


def add_to_input_pool(record: dict, path: str) -> str:
    """Hand off to `projects.py` so the pool has one writer. -> the NODE ID.

    It answers with the node it created, so the caller reads the id rather than
    reconstructing it. This used to scrape a log line with a regex and rebuild a
    key by re-appending the extension — which yielded None whenever the message
    shape changed, and only failed AFTER the upload had already happened.
    """
    try:
        added = PROJECTS.add_inputs(record, [path])
    except SystemExit as exc:
        die(f"could not add to project {record['slug']}'s input pool: {exc}")
    if not added:
        die(f"the project store added nothing for {path}")
    return added[0]["node"]


def _fetch(ref, project, dest):
    """Pull the run's video down and decide where frames will be written."""
    tmp = tempfile.mkdtemp(prefix="frames-")
    record, src = fetch_video(ref, project, tmp)
    dest_dir = dest or tmp
    os.makedirs(dest_dir, exist_ok=True)
    return record, src, dest_dir


def _project_of(run: dict) -> dict:
    """The project record a run belongs to. Its `root` is what the pool hangs off."""
    try:
        return PROJECTS.resolve(run["project"])
    except api.NotFound:
        die(f"run {run['id']} names project {run['project']}, which no longer exists")


def _emit(run: dict, out: str, add_input: bool, chain: str | None) -> None:
    """Print the frame, and optionally put it in the pool and the chain."""
    print(out)
    if not add_input:
        if chain:
            die("--chain needs --add-input: a chain records node ids, and the frame "
                "has to be in the library before it has one")
        return
    project = _project_of(run)
    node = add_to_input_pool(project, out)
    print(node)
    if chain:
        doc = chain_add(project, chain, node, run["id"])
        print(f"chain {doc['chain']}: {len(doc['frames'])} frame(s)")


@click.group(help=__doc__)
def main():
    pass


@main.command("last", epilog="\n\nArguments:\n  REF  runref: <project>/<slug>, <project>/latest, a run id, #N")
@click.argument("ref", required=True)
@click.option("--add-input", is_flag=True, help=("upload into the PROJECT's input pool (never a character's "
              "reference/)"))
@click.option("--chain", help=("also record this frame in a scene chain, so the next shot's "
              "reference_images can be derived rather than recalled"))
@click.option("--dest", help="directory to write the image into")
@click.option("--project", help="project, when the runref does not carry one")
def do_last(ref, add_input, chain, dest, project):
    """The final frame — the chaining handoff."""
    run, src, dest_dir = _fetch(ref, project, dest)
    out = grab(src, None, os.path.join(dest_dir, f"{run['id']}_last.png"), from_end=0.2)
    _emit(run, out, add_input, chain)


@main.command("at", epilog="\n\nArguments:\n  REF  runref: <project>/<slug>, <project>/latest, a run id, #N")
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
    run, src, dest_dir = _fetch(ref, project, dest)
    out = grab(src, time, os.path.join(dest_dir, f"{run['id']}_t{time:g}.png"))
    _emit(run, out, add_input, chain)


@main.command("grid", epilog="\n\nArguments:\n  REF  runref: <project>/<slug>, <project>/latest, a run id, #N")
@click.argument("ref", required=True)
@click.option("--count", type=int, default=4, help="frames to sample (default 4)")
@click.option("--dest", help="directory to write the image into")
@click.option("--project", help="project, when the runref does not carry one")
def do_grid(ref, count, dest, project):
    """A contact sheet, for looking at the clip."""
    run, src, dest_dir = _fetch(ref, project, dest)
    out = os.path.join(dest_dir, f"{run['id']}_grid.jpg")
    times = contact_grid(src, count, out)
    print(out)
    print("sampled at: " + ", ".join(f"{t:.1f}s" for t in times))


@main.command("chain", epilog="\n\nArguments:\n  REF  <project>/<slug>")
@click.argument("ref", required=True)
@click.option("--add-key", multiple=True, help=("record an existing NODE ID as the next frame in the chain. "
              "Repeatable, order preserved. For frames produced outside `last "
              "--add-input`, or to reconstruct a chain after the fact."))
@click.option("--args", is_flag=True, help="print as `--key N --key N …`, ready to paste into a run")
@click.option("--max", "max_", type=int, help="cap the list (Kling takes 7); keeps the seed and the newest")
@click.option("--seed", help="node id of the image shot 1 started from")
def do_chain(ref, add_key, args, max_, seed):
    """The frames recorded for a scene chain, in order.

    `--add-key` and `--seed` keep their names — both are in
    `cli_surface_reference.json`, which is a contract — but they take node ids.
    A raw S3 key is refused rather than resolved: hard rule #3 says a binding
    names a node, and quietly accepting the old spelling is how a stale
    addressing scheme survives the change meant to end it.
    """
    if "/" not in ref:
        die("chain ref must be <project>/<slug>")
    project_slug, slug = ref.split("/", 1)
    record = PROJECTS.require_project(project_slug)
    doc = load_chain(record, slug)
    for given in (*add_key, *([seed] if seed else [])):
        if not given.startswith("node-"):
            die(f"{given!r} is not a node id. A chain names nodes, not keys — "
                "a key stops naming a file the moment it is renamed.\n"
                "       studio frames last <runref> --add-input --chain <slug>")
    if seed:
        doc["seed"] = seed
        save_chain(record, doc)
    for node in add_key:
        doc = chain_add(record, slug, node, None)
    nodes = chain_nodes(doc, max_)
    if not nodes:
        die(f"chain {record['slug']}/{chain_slug(slug)} is empty — record frames "
            f"with `last <runref> --add-input --chain {chain_slug(slug)}`, and "
            f"set the first shot's source with --seed")
    if args:
        print(" ".join(f"--key {n}" for n in nodes))
    else:
        for node in nodes:
            print(node)
