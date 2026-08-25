"""`studio catalog confirm-outputs` — finish the uploads that stopped one call short.

An upload is three calls: create the node, PUT the bytes, confirm. The confirm is
the only one that runs `HeadObject` and writes `size` and `content_type` onto the
row, and until it does the node is a placeholder — a key with an object behind it
that the catalog has no record of.

**The three entity output routes never got their confirm.**
`POST /api/runs/<id>/outputs`, `POST /api/scenes/<id>/output` and
`POST /api/movies/<id>/output` mint the node and sign the PUT together, and
`store.upload_to_url` PUT the bytes and stopped. So every run output studio has
ever produced is a placeholder, and `browse.is_abandoned_upload` keys on `size`
being absent — which kept all of them out of every folder listing and out of the
reel. The bytes were in S3, the run's `outputs` named them, the run page drew
them (it expands by id and presigns off `blob_key`, which no listing does), and
the `output/` folder they lived in rendered empty.

`store.upload_to_url` confirms now. This repairs what it wrote before it did.

WHY THIS WALKS ENTITIES RATHER THAN SCANNING THE TABLE
------------------------------------------------------
The rows it is looking for are the ones a listing hides, so a listing cannot find
them — that is the defect. Two ways out: scan DynamoDB for file rows with a
`blob_key` and no `size`, or ask the entities that name their outputs.

It asks the entities, and that is the narrower question on purpose. A table scan
would also surface **genuinely** abandoned uploads — a browser upload whose PUT
failed — and those are placeholders that SHOULD stay hidden, because there are no
bytes behind them. An entity output is different: something recorded a completed
generation and named the node, so the bytes are expected to exist and their
absence is itself worth reporting. Walking runs, scenes and movies is a question
only the broken case answers.

It also means this needs no AWS credentials, which is the rule the rest of the
pipeline follows (#308) and which the other `catalog` commands are the exception
to rather than the model for.

WHY THERE IS NO JOURNAL
-----------------------
`catalog gc` takes two invocations and writes a journal because it deletes. This
adds two attributes to a row, read from `HeadObject` — the same call the confirm
route was always going to make — and writes nothing to S3. A second run reports
zero and changes nothing. `--apply` is here so a person sees the report first,
not because the write needs guarding.

WHAT IT REFUSES TO DO
---------------------
Nothing is invented. `confirm-upload` writes the length and type S3 reports, so a
node whose object is missing gets a 404 and is reported as such rather than
repaired with a plausible size — a row promising bytes that are not there is the
one state worse than the one being fixed.
"""
from __future__ import annotations

import click

from studio_pipeline.adapters import api, entities, store

# What a repaired, skipped or failed candidate is called in the report. Spelled
# out rather than derived from the entity kind, because "run output" reads as
# English in a line a person is scanning and `run` alone does not.
KINDS = {"run": "run output", "scene": "scene output", "movie": "movie output"}


def _candidates() -> list[dict]:
    """Every node a run, scene or movie names as its output, across every project.

    One record per entity, and the node ids come off the record rather than off a
    folder listing — which is the whole point, since the listing is what hides
    them.

    A run reports its outputs already expanded (`get_run` fills in `size` for
    each), and a scene and a movie report `output: {"node": …}` and nothing else.
    The size is therefore read from the node in `_classify` for all three rather
    than from the run's expansion for one of them: two ways of deciding the same
    thing is how the two come to disagree.
    """
    found: list[dict] = []
    for project in entities.list_projects():
        proj_id = project["id"]

        cursor = None
        while True:
            page = entities.query_runs(project=proj_id, cursor=cursor)
            for row in page.get("runs") or []:
                record = entities.get_run(row["id"])
                for entry in record.get("outputs") or []:
                    node = entry.get("node") or entry.get("id")
                    if node:
                        found.append({"kind": "run", "entity": row["id"],
                                      "node": node, "name": entry.get("name") or ""})
            cursor = page.get("cursor")
            if not cursor:
                break

        for scene in entities.project_scenes(proj_id):
            record = entities.get_scene(scene["id"])
            node = (record.get("output") or {}).get("node")
            if node:
                found.append({"kind": "scene", "entity": scene["id"],
                              "node": node, "name": record.get("slug") or ""})

        for movie in entities.project_movies(proj_id):
            record = entities.get_movie(movie["id"])
            node = (record.get("output") or {}).get("node")
            if node:
                found.append({"kind": "movie", "entity": movie["id"],
                              "node": node, "name": record.get("slug") or ""})

    return found


def _classify(candidate: dict) -> str:
    """`confirmed`, `placeholder`, or `missing` — what the node's own record says.

    **`"size" in view`, not a truthiness test.** The API drops absent attributes
    rather than sending them as null, so a placeholder has no `size` key at all
    and a confirmed empty file has `size` 0. Truthiness cannot tell those apart,
    and `browse.is_abandoned_upload` makes exactly the same distinction for
    exactly the same reason — the two have to agree or this repairs rows the app
    was already showing.

    `missing` is a node id an entity still names after the node was deleted. It
    is not this command's to fix; it is reported so it is not silently counted as
    healthy.
    """
    try:
        record = store.node(candidate["node"])
    except api.NotFound:
        return "missing"
    return "confirmed" if "size" in record else "placeholder"


def _confirm(candidate: dict) -> tuple[str, str]:
    """Run the confirm the upload skipped. Returns `(outcome, detail)`.

    `HeadObject` happens inside the route, so a 404 here means the object is not
    in the bucket — the upload really did fail, rather than merely failing to be
    recorded. That is the one case worth telling apart from a repair, because it
    is the case where the media is actually gone.
    """
    try:
        record = store.node_confirm(candidate["node"])
    except api.NotFound:
        return "gone", "no object behind the key"
    except api.ApiError as exc:
        return "refused", str(exc)
    return "repaired", f"{record.get('size')} bytes, {record.get('content_type') or '?'}"


def _report(rows: list[tuple[str, dict, str]]) -> None:
    for outcome, candidate, detail in rows:
        print(f"  {outcome:<11} {KINDS[candidate['kind']]:<13} {candidate['node']}  "
              f"{candidate['name']}" + (f"  ({detail})" if detail else ""))


@click.command("confirm-outputs", help=__doc__)
@click.option("--apply", "apply_", is_flag=True,
              help="Confirm them. Without it, report only.")
def cmd_confirm_outputs(apply_):
    """Find entity outputs that were never confirmed; repair them with `--apply`."""
    candidates = _candidates()
    if not candidates:
        print("no run, scene or movie names an output. Nothing to check.")
        return

    graded = [(_classify(c), c) for c in candidates]
    placeholders = [c for state, c in graded if state == "placeholder"]
    confirmed = sum(1 for state, _ in graded if state == "confirmed")
    absent = [c for state, c in graded if state == "missing"]

    print(f"[{'APPLY' if apply_ else 'dry run'}] {len(candidates)} entity output(s): "
          f"{confirmed} already confirmed, {len(placeholders)} unconfirmed, "
          f"{len(absent)} naming a node that is gone\n")

    if absent:
        print("named but deleted — not repairable here:")
        _report([("missing", c, "") for c in absent])
        print()

    if not placeholders:
        print("every output that still exists is confirmed. Nothing to do.")
        return

    if not apply_:
        print("unconfirmed — hidden from every folder listing and from the reel:")
        _report([("placeholder", c, "") for c in placeholders])
        print(f"\nnothing written. `--apply` confirms exactly the {len(placeholders)} "
              "listed above, recording the size and type S3 reports.")
        return

    print("confirming:")
    results = []
    for candidate in placeholders:
        outcome, detail = _confirm(candidate)
        results.append((outcome, candidate, detail))
    _report(results)

    repaired = sum(1 for outcome, _, _ in results if outcome == "repaired")
    gone = sum(1 for outcome, _, _ in results if outcome == "gone")
    refused = sum(1 for outcome, _, _ in results if outcome == "refused")
    print(f"\n{repaired} repaired, {gone} with no bytes behind them, {refused} refused.")
    if gone:
        print("a 'gone' row is an upload that genuinely failed. Its entity still names "
              "the node; re-run the generation, or delete the row.")
