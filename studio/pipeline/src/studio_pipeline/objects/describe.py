"""`studio describe` — what an image or video SHOWS, written onto the file.

    studio describe <node> --text "Shirtless at the pool, whistle on a cord."
    studio describe <node> --tag poolside --tag shirtless
    studio describe <node> --clear-tags
    studio describe <node>                     # read back what is there

**A caption belongs to the picture, not to a set it happens to be in.** It used
to live on the `REF#` row that made a file one character's reference, so the
same image had words inside a reference grid and none anywhere else — and a file
nobody had made a reference had nowhere at all to put them. This library has
twelve such files sitting in `reference/` folders right now.

`character set-ref-desc` still works and writes to exactly the same place. What
that command adds is the group and the order, which ARE facts about the set.

**Tags are free-form and folded** — trimmed, lower-cased, de-duplicated — because
a tag is a selector. `Poolside` and `poolside ` filtering as two different things
is a bug that renders identically in a chip and shows up as a `--pick-tag` that
quietly returns half the set.

Nothing here writes an object. A description is a column.
"""
import click

from studio_pipeline.adapters import store


@click.command(help=__doc__)
@click.argument("node", required=True)
@click.option("--text", help="The description. Pass an empty string to clear it.")
@click.option("--tag", "tags", multiple=True, help="Repeatable. Replaces the existing tags.")
@click.option("--clear-tags", is_flag=True, help="Remove every tag.")
def describe(node, text, tags, clear_tags):
    if tags and clear_tags:
        raise click.ClickException("pass --tag or --clear-tags, not both.")

    changes: dict = {}
    if text is not None:
        changes["description"] = text
    if clear_tags:
        changes["tags"] = None
    elif tags:
        changes["tags"] = list(tags)

    if not changes:
        # A bare invocation reads rather than failing. Looking one up is the
        # commonest reason to type this, and `--help` is not that answer.
        record = store.node(node)
        click.echo(record.get("name", node))
        click.echo(f"  {record.get('description') or '(no description)'}")
        click.echo(f"  tags: {', '.join(record.get('tags') or []) or '(none)'}")
        return

    updated = store.describe_node(node, **changes)
    click.echo(f"{updated.get('name', node)}: described")
    if updated.get("description"):
        click.echo(f"  {updated['description']}")
    click.echo(f"  tags: {', '.join(updated.get('tags') or []) or '(none)'}")
