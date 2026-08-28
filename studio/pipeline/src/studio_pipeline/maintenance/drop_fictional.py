"""`studio catalog drop-fictional` — remove the dead `fictional` attribute.

`fictional` recorded whether a character was invented or a real person's
likeness. The field was removed from the service, the pipeline and the app, so
nothing reads it and nothing writes it any more — but rows created before that
still carry the attribute, where it is neither maintained nor true.

**Dead data is worse than no data, because it still reads as an answer.** A
future `catalog verify`, a hand-written scan or somebody browsing the table sees
a `fictional` on a character row and has no way to know it stopped meaning
anything. This drops it.

WHY IT WRITES TO DYNAMODB RATHER THAN THROUGH THE API
------------------------------------------------------
There is no route to write through. `PATCH /api/characters/<id>` no longer
accepts the key and `services/catalog.py` no longer stores it — which is the
point, and adding a route to unset one dead attribute would be a hole kept
forever for a one-shot. So this joins `catalog gc`, `catalog verify` and
`catalog backfill-plans` as a maintenance command holding its own AWS clients:
`studio --profile prod catalog drop-fictional --apply`.

WHY THERE IS NO JOURNAL
-----------------------
`catalog gc` and `catalog reseat` journal because they delete *media* — bytes in
S3 that nothing else holds a copy of. This removes one attribute from one row per
character, touches no object, and creates and deletes nothing else. A second run
reports zero and changes nothing, because a row without the attribute is skipped.

WHAT IT WILL NOT DO
-------------------
It does not read the value, act on it, or preserve it. The attribute is dropped
whatever it says. **Capture it first if you want it** — a `REMOVE` is not
recoverable from the table, and point-in-time recovery is the only other copy.
"""
from __future__ import annotations

import click

from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.errors import reports

#: The attribute this drops. Named once so the scan filter, the report and the
#: update expression cannot drift apart.
ATTRIBUTE = "fictional"


class DropError(Exception):
    """The sweep cannot proceed."""


def carrying(ddb) -> list[dict]:
    """Every character row still holding the attribute, oldest first.

    Filtered server-side: on a table where most rows are nodes, sends and refs,
    shipping every item back to test one key is a cost paid for nothing. Oldest
    first so a partial `--apply` is resumable in the order a person would expect.
    """
    found = [item for item in ddbc.scan(ddb, FilterExpression=f"attribute_exists({ATTRIBUTE})")
             if str(item.get("pk", "")).startswith("CHAR#") and item.get("sk") == "META"]
    return sorted(found, key=lambda char: char.get("created") or "")


def drop(ddb, char: dict) -> None:
    """Remove the attribute from one row. Conditional, so a race is a no-op.

    `attribute_exists` makes the write idempotent against a concurrent sweep
    rather than merely repeatable: two runs cannot both report having dropped the
    same row.
    """
    try:
        ddb.update_item(
            TableName=ddbc.table(),
            Key={"pk": {"S": char["pk"]}, "sk": {"S": char["sk"]}},
            UpdateExpression=f"REMOVE {ATTRIBUTE}",
            ConditionExpression=f"attribute_exists({ATTRIBUTE})",
        )
    except ddb.exceptions.ConditionalCheckFailedException:
        pass


# ── the command ─────────────────────────────────────────────────────────────


@click.command("drop-fictional")
@click.option("--apply", "apply_", is_flag=True,
              help="Write. Without it this reports and changes nothing.")
@click.option("--limit", type=int, help="Stop after this many characters (for a trial).")
@reports(DropError)
def cmd_drop_fictional(apply_, limit):
    """Drop the retired `fictional` attribute from every character row.

    Reports first, always. The value is not shown: it is dead, it is not
    necessarily true, and printing it would invite somebody to act on it.
    """
    ddb = ddbc.client()
    if not ddbc.table_exists(ddb):
        raise DropError(f"no table {ddbc.table()!r} — check the profile.")

    chars = carrying(ddb)
    if limit:
        chars = chars[:limit]

    print(f"table:               {ddbc.table()}")
    print(f"carrying {ATTRIBUTE!r}: {len(chars)}")
    for char in chars:
        print(f"  {char['pk']}")

    if not chars:
        print("\nnothing to do.")
        return

    if not apply_:
        print("\n(dry run — nothing written. Re-run with --apply.)")
        return

    for char in chars:
        drop(ddb, char)
    print(f"\ndropped {ATTRIBUTE!r} from {len(chars)} character row(s).")
