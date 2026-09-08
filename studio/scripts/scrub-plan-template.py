#!/usr/bin/env python
"""Drop the retired `plan.template` from every run that still carries one.

**A one-off, kept because the fingerprint makes it more than a field delete.**
`plan_digest` hashes the whole plan, so removing an attribute from a stored plan
without recomputing the fingerprint beside it leaves a row whose projected hash
describes a plan that no longer exists — and `GET /api/runs?fingerprint=` is
answered off that projection. Both move together here, in one transaction per
run, or neither does.

Why the field went at all is in `routes/runs.py::_expanded`: nothing read it
back once the create bar started seeding from `plan.prompt`, and sitting inside
the fingerprint it made two byte-identical submissions hash differently —
a false negative on the one guard against paying for the same generation twice.

## It reuses the API's own code, deliberately

`catalog.submission_fingerprint` computes the hash and
`catalog.update_project_entity` writes the row. A second implementation of
either would be a second opinion about what a run was told to render, and the
disagreement would be invisible afterwards. Notably it does NOT go through
`PATCH /api/runs/<id>/plan`: `_revised` forces `status: "draft"`, which on a run
that was actually submitted would rewrite history rather than tidy it.

## Running it

Dry by default — it prints every run it would touch and writes nothing:

    poetry -C studio/backend run python studio/scripts/scrub-plan-template.py
    poetry -C studio/backend run python studio/scripts/scrub-plan-template.py --apply

The table comes from `STUDIO_CATALOG_TABLE`, which `dev-up.sh` exports for this
machine's dev stack. Production is named explicitly, and only ever explicitly:

    STUDIO_CATALOG_TABLE=studio-prod-catalog poetry -C studio/backend run \\
        python studio/scripts/scrub-plan-template.py --apply

Idempotent: a second pass finds nothing, because the filter is the presence of
the attribute rather than a marker this script writes.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from boto3.dynamodb.types import TypeDeserializer  # noqa: E402

from studio_core import config  # noqa: E402
from studio_core.clients.aws import dynamodb  # noqa: E402
from studio_core.services import catalog  # noqa: E402

_load = TypeDeserializer()


def _runs_with_a_template():
    """Every run record whose stored plan still carries a `template`.

    A Scan rather than a Query, because the question is not asked of one
    partition: runs live under `RUN#<id>` and there is no index on "has a
    template". It reads the whole table once, which for a library of this size
    is a few seconds and a few cents, and it runs twice in the life of this
    script.

    The filter is on the ROW — `sk = META` and a `RUN#` partition — and the
    plan is inspected in Python, because `attribute_exists(plan.template)` on a
    map is expressible but silently matches nothing when `plan` is absent, and
    a filter that quietly matches nothing is the worst possible outcome here.
    """
    paginator = dynamodb.client().get_paginator("scan")
    for page in paginator.paginate(
        TableName=config.catalog_table(),
        FilterExpression="sk = :meta AND begins_with(pk, :run)",
        ExpressionAttributeValues={
            ":meta": {"S": catalog.META},
            ":run": {"S": catalog.ENTITY_KEYS[catalog.ENTITY_RUN][1]},
        },
    ):
        for item in page.get("Items", []):
            record = {key: _load.deserialize(value) for key, value in item.items()}
            if isinstance(record.get("plan"), dict) and "template" in record["plan"]:
                yield record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write. Without it nothing is written.")
    args = parser.parse_args()

    table = config.catalog_table()
    print(f"table: {table}{'' if args.apply else '   (dry run)'}")

    touched = 0
    for record in _runs_with_a_template():
        plan = {k: v for k, v in record["plan"].items() if k != "template"}
        sends = catalog.sends(record["id"])
        fingerprint = catalog.submission_fingerprint(record.get("model"), plan, sends)
        moved = "" if fingerprint == record.get("fingerprint") else " · fingerprint moves"
        print(f"  {record['id']}  {record.get('status', '?'):<10}{moved}")
        touched += 1
        if args.apply:
            # The listing row carries the fingerprint too — the whole reason it
            # is projected — so it is written in the same transaction. `status`
            # is deliberately absent from both: this tidies a field, it does
            # not move a run.
            catalog.update_project_entity(
                catalog.ENTITY_RUN, record,
                {"plan": plan, "fingerprint": fingerprint},
                {"fingerprint": fingerprint},
            )

    if not touched:
        print("nothing to scrub.")
    elif args.apply:
        print(f"scrubbed {touched} run(s).")
    else:
        print(f"{touched} run(s) would be scrubbed. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
