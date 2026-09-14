#!/usr/bin/env python3
"""One-off: move every scene from `SHOT#` rows to `runs` + `scene`. DELETE AFTER PROD.

A scene used to be a storyboard: one `SHOT#<id>` row per planned shot, each
naming the run that rendered it, the runs that boarded its panels, the run whose
last frame it opened on, and the takes it displaced. A scene is now two facts —
`runs` on the scene (the cut, in order) and `scene` on each run (membership) —
with an edge row beside each. This reads the old rows and writes the new facts:

    cut     = every shot's `run`, in `order`               -> scene.runs + SCENE#/RUN# edges
    members = cut ∪ panel runs ∪ opens_on.from_run ∪ takes -> run.scene + RUN#/SCENE# edge
                                                            + `scene` on the run's listing row
    the SHOT# rows, and the plan fields on the record, are deleted

Runs a shot names that no longer exist are skipped and reported. Dry run by
default; `--apply` writes. Reads the table with the default AWS profile, like
`dev-seed`. Prod held 5 scenes and 37 shot rows when this was written.

    python3 studio/scripts/migrate-scenes-to-runs.py --table studio-prod-catalog
    python3 studio/scripts/migrate-scenes-to-runs.py --table studio-prod-catalog --apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import boto3
from boto3.dynamodb.conditions import Attr, Key

PLAN_FIELDS = ("setting", "defaults", "logline", "version")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def scenes(table):
    kwargs = {"FilterExpression": Attr("pk").begins_with("SCENE#") & Attr("sk").eq("META")}
    while True:
        page = table.scan(**kwargs)
        yield from page["Items"]
        if "LastEvaluatedKey" not in page:
            return
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def partition(table, pk: str) -> list[dict]:
    return table.query(KeyConditionExpression=Key("pk").eq(pk))["Items"]


def run_ids_of(shots: list[dict]) -> tuple[list[str], list[str]]:
    """(the cut, in order), (every run the shots name, in first-seen order)."""
    cut, members = [], []

    def seen(run_id):
        if run_id and run_id not in members:
            members.append(run_id)

    for shot in sorted(shots, key=lambda s: float(s.get("order") or 0)):
        if shot.get("run"):
            cut.append(shot["run"])
            seen(shot["run"])
        for panel in shot.get("panels") or []:
            seen(panel.get("run"))
        seen((shot.get("opens_on") or {}).get("from_run"))
        for take in shot.get("takes") or []:
            seen(take.get("run"))
    return cut, members


def migrate(table, apply: bool) -> int:
    stamp = now()
    problems = 0
    for scene in scenes(table):
        scene_id = scene["pk"][len("SCENE#"):]
        lib = scene["lib"]
        rows = partition(table, scene["pk"])
        shots = [r for r in rows if r["sk"].startswith("SHOT#")]
        old_edges = [r["sk"] for r in rows if r["sk"].startswith("RUN#")]
        cut, members = run_ids_of(shots)

        live = {}
        for run_id in members:
            got = table.get_item(Key={"pk": f"RUN#{run_id}", "sk": "META"}).get("Item")
            if got is None:
                print(f"  ! {scene_id}: run {run_id} no longer exists; skipped", file=sys.stderr)
                problems += 1
                continue
            if got.get("scene") and got["scene"] != scene_id:
                print(f"  ! {scene_id}: run {run_id} already belongs to {got['scene']}; "
                      f"left there", file=sys.stderr)
                problems += 1
                continue
            live[run_id] = got
        cut = [r for r in cut if r in live]

        print(f"{scene_id}  {scene.get('name')!r}  {len(shots)} shot rows -> "
              f"cut {len(cut)}, members {len(live)}, "
              f"edges {len(old_edges)} -> {len(dict.fromkeys(cut))}")
        for run_id in cut:
            print(f"    cut     {run_id}")
        for run_id in live:
            if run_id not in cut:
                print(f"    member  {run_id}")
        if not apply:
            continue

        with table.batch_writer() as batch:
            # The scene: the cut on the record, the plan fields off it, edges
            # exactly the cut, shot rows gone.
            table.update_item(
                Key={"pk": scene["pk"], "sk": "META"},
                UpdateExpression="SET #r = :runs, #u = :now REMOVE " +
                                 ", ".join(f"#p{i}" for i in range(len(PLAN_FIELDS))),
                ExpressionAttributeNames={"#r": "runs", "#u": "updated",
                                          **{f"#p{i}": f for i, f in enumerate(PLAN_FIELDS)}},
                ExpressionAttributeValues={":runs": cut, ":now": stamp},
            )
            wanted = {f"RUN#{r}" for r in cut}
            for sk in old_edges:
                if sk not in wanted:
                    batch.delete_item(Key={"pk": scene["pk"], "sk": sk})
            for sk in wanted:
                if sk not in old_edges:
                    batch.put_item(Item={"pk": scene["pk"], "sk": sk, "lib": lib, "created": stamp})
            for shot in shots:
                batch.delete_item(Key={"pk": scene["pk"], "sk": shot["sk"]})
            # Each member run: the attribute, its listing projection, its edge.
            for run_id, record in live.items():
                table.update_item(
                    Key={"pk": f"RUN#{run_id}", "sk": "META"},
                    UpdateExpression="SET scene = :s, updated = :now",
                    ExpressionAttributeValues={":s": scene_id, ":now": stamp},
                )
                if record.get("project") and record.get("created"):
                    table.update_item(
                        Key={"pk": f"PROJ#{record['project']}",
                             "sk": f"RUN#{record['created']}#{run_id}"},
                        UpdateExpression="SET scene = :s",
                        ExpressionAttributeValues={":s": scene_id},
                        ConditionExpression="attribute_exists(pk)",
                    )
                batch.put_item(Item={"pk": f"RUN#{run_id}", "sk": scene["pk"],
                                     "lib": lib, "created": stamp})
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", required=True)
    parser.add_argument("--apply", action="store_true", help="write; dry run otherwise")
    args = parser.parse_args()
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(args.table)
    problems = migrate(table, args.apply)
    print("applied" if args.apply else "dry run — nothing written")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
