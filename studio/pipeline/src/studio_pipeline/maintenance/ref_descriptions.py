"""`studio catalog descriptions` — move a caption off the row, onto the file.

A description used to live on the `CHAR#<id>` / `REF#<node>` row that makes a
file one character's reference. It lives on the node now, because it is a fact
about the picture rather than about the set: "head and shoulders in full profile"
is true of the file in `corpus/`, in `archive/`, and after somebody moves it.

`group` and `order` stay on the row. Those ARE facts about the set.

WHY THIS EXISTS AT ALL RATHER THAN A FALLBACK READ
--------------------------------------------------
The alternative was for `_reference_view` to read the node and fall back to the
row. That is one line and it never goes away: two homes for one field, with
every future writer having to decide which, and a reader that cannot tell a
migrated library from an unmigrated one. So the read moved in one step and this
moves the data ahead of it.

**Run it BEFORE deploying the read change.** Both stores agree in between — this
only writes, and nothing reads a node description until the deploy lands. Run
after, and every existing reference shows a blank caption until it finishes.

Idempotent. A row whose node already carries the same words is skipped, so a
second run reports zero and changes nothing.
"""
from __future__ import annotations

import click

from studio_pipeline.adapters import ddb


def _folded(tags) -> list[str]:
    """As `catalog.clean_tags` folds them: trimmed, lower-cased, de-duplicated."""
    seen, out = set(), []
    for entry in tags or []:
        tag = " ".join(str(entry).split()).lower()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


# Not `reseat`: that verb already means "re-stamp a blob key" one command over,
# and two commands whose names differ by a suffix is how the wrong one gets run.
@click.command("descriptions", help=__doc__)
@click.option("--apply", "apply_", is_flag=True, help="Write. Without it, report only.")
def cmd_reseat_descriptions(apply_):
    client = ddb.client()
    table = ddb.table()

    moves = []
    # `ddb.scan` supplies the table name itself and yields deserialized rows.
    for row in ddb.scan(client,
                        FilterExpression="begins_with(sk, :ref)",
                        ExpressionAttributeValues={":ref": {"S": "REF#"}}):
        node_id = row["sk"].split("#", 1)[1]
        description = (row.get("description") or "").strip()
        tags = _folded(row.get("tags"))
        if not description and not tags:
            continue

        node = client.get_item(
            TableName=table,
            Key={"pk": {"S": f"NODE#{node_id}"}, "sk": {"S": "META"}},
        ).get("Item")
        if node is None:
            # A row pointing at a node that is gone is a detach that half-landed.
            # Reported, never repaired here: this command moves words, and
            # deciding what to do about a dangling reference is `catalog gc`'s
            # kind of question, not this one's.
            click.echo(f"  ORPHAN  {row['pk']} -> {node_id} (no such node)")
            continue

        current = ddb.from_item(node)
        if current.get("description") == description and _folded(current.get("tags")) == tags:
            continue
        moves.append((node_id, current.get("name", node_id), description, tags))

    for _node_id, name, description, tags in moves:
        click.echo(f"  {name}: {description[:60] or '(no description)'}"
                   f"{' · ' + ', '.join(tags) if tags else ''}")

    if not moves:
        click.echo("nothing to move.")
        return

    if not apply_:
        click.echo(f"\n{len(moves)} description(s) would move onto their files. "
                   "Re-run with --apply.")
        return

    for node_id, name, description, tags in moves:
        assignments = {}
        if description:
            assignments["description"] = {"S": description}
        if tags:
            assignments["tags"] = {"L": [{"S": tag} for tag in tags]}
        client.update_item(
            TableName=table,
            Key={"pk": {"S": f"NODE#{node_id}"}, "sk": {"S": "META"}},
            UpdateExpression="SET " + ", ".join(f"#{i} = :{i}" for i in range(len(assignments))),
            ExpressionAttributeNames={f"#{i}": k for i, k in enumerate(assignments)},
            ExpressionAttributeValues={f":{i}": v for i, v in enumerate(assignments.values())},
            ConditionExpression="attribute_exists(pk)",
        )
        click.echo(f"  moved: {name}")

    click.echo(f"\n{len(moves)} description(s) moved.")
