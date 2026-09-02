"""`studio templates` — read and move the template library, the prose a run fills.

    studio templates show                            # what this stack says
    studio templates pull --path templates.yaml           # stack  -> file
    studio templates push --path templates.yaml           # file   -> stack   (refuses a conflict)
    studio templates push --path templates.yaml --force   # …and overwrite anyway

**A FILE IN THE MIDDLE, RATHER THAN STACK TO STACK IN ONE PROCESS.** A profile
selects an API url and a Cognito pool for the whole process, so a single command
holding two of them would need a second session, a second token cache and a
second `auth` — the sort of thing that works until the day the wrong one is in
force. Two invocations with a `--profile` each cannot make that mistake, and
they leave a reviewable artifact between them: the thing about to be written to
production is a file somebody can read first.

It is also the idiom this package already has. `character edit` round-trips a
bible through `local/`, for the same reason and with the same shape.

## Why a push refuses rather than merges

A row the destination already holds, whose text differs, is the one case where
both sides might be right: prod may carry a fix nobody put back into dev. A
push that overwrote it would revert that fix silently, and a push that skipped
it would report success while leaving the two stacks disagreeing. So it refuses,
prints the difference, and writes nothing at all — not even the rows that were
fine, because a half-applied library is the state that is hardest to reason about.

`--force` overwrites. It is not a convenience: it is the claim that the file is
right and the destination is stale, which is a thing only a person reading the
diff can know.

## What it never does

**No delete.** A row the file does not mention is left alone, exactly as
`config sync` leaves a template image the repo no longer has. A file is a
statement about the rows it contains, not an assertion that nothing else exists
— and the destination is a live library somebody may have added a template to.
"""

from __future__ import annotations

import difflib
import sys

import click
import yaml

from studio_pipeline.adapters import entities as E
from studio_pipeline.errors import die

#: The fields a pushed template carries. Anything else in the file is dropped
#: rather than sent — a pulled file round-trips whatever the API added, and
#: refusing those would make edit-then-push fail on fields it produced itself.
TEMPLATE_FIELDS = ("name", "prompt", "description", "tags", "illustration")


class LibraryError(RuntimeError):
    """The template library could not be read, written or compared."""


def fetch() -> dict:
    """The template library this profile's stack holds."""
    got = E.templates()
    return {"blocks": got.get("blocks") or {}, "templates": got.get("templates") or []}


def read_file(path: str) -> dict:
    """A library document from disk, checked for shape before anything is sent."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except FileNotFoundError:
        raise LibraryError(f"no such file: {path}")
    except yaml.YAMLError as exc:
        raise LibraryError(f"{path} is not valid YAML:\n  {exc}")
    if not isinstance(doc, dict):
        raise LibraryError(f"{path} must be a mapping with `blocks:` and `templates:`.")

    blocks = doc.get("blocks") or {}
    templates = doc.get("templates") or []
    if not isinstance(blocks, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in blocks.items()):
        raise LibraryError(f"{path}: `blocks` must map a name to its text.")
    if not isinstance(templates, list):
        raise LibraryError(f"{path}: `templates` must be a list.")
    for template in templates:
        if not isinstance(template, dict) or not template.get("id"):
            raise LibraryError(f"{path}: every template needs an `id`.")
    if not blocks and not templates:
        raise LibraryError(f"{path} holds no blocks and no templates — nothing to push.")
    return {"blocks": blocks, "templates": templates}


def document(library: dict) -> str:
    """The library as YAML a person can edit.

    Block strings are dumped with `default_style='|'` so a paragraph stays a
    paragraph. A block is prose that a person is going to read and rewrite, and
    YAML's folded scalars turn it into one long line the moment it contains a
    colon.
    """
    blocks = {name: _Literal(text) for name, text in sorted(library["blocks"].items())}
    templates = [{"id": template["id"],
               **{k: template[k] for k in TEMPLATE_FIELDS if template.get(k) is not None}}
              for template in library["templates"]]
    for template in templates:
        if isinstance(template.get("prompt"), str):
            template["prompt"] = _Literal(template["prompt"])
    return yaml.dump({"blocks": blocks, "templates": templates},
                     sort_keys=False, allow_unicode=True, width=88)


class _Literal(str):
    """A string dumped as a `|` block, so prose survives a round trip readable."""


yaml.add_representer(
    _Literal,
    lambda dumper, data: dumper.represent_scalar(
        "tag:yaml.org,2002:str", str(data), style="|"),
)


def _angle_payload(template: dict) -> dict:
    return {k: template[k] for k in TEMPLATE_FIELDS if template.get(k) is not None}


def compare(wanted: dict, held: dict) -> tuple[list, list, list]:
    """(new, same, differing) across blocks and templates, as (kind, name, …) tuples.

    One pass over both kinds rather than two, because every caller below wants
    them interleaved: a push reports "3 new, 1 differs" about the library, not
    about blocks and then about templates.
    """
    held_blocks = held["blocks"]
    held_angles = {a["id"]: a for a in held["templates"]}
    new, same, differing = [], [], []

    for name, text in sorted(wanted["blocks"].items()):
        if name not in held_blocks:
            new.append(("block", name, text, None))
        elif held_blocks[name] == text:
            same.append(("block", name, text, held_blocks[name]))
        else:
            differing.append(("block", name, text, held_blocks[name]))

    for template in wanted["templates"]:
        payload = _angle_payload(template)
        there = held_angles.get(template["id"])
        if there is None:
            new.append(("template", template["id"], payload, None))
        elif _angle_payload(there) == payload:
            same.append(("template", template["id"], payload, _angle_payload(there)))
        else:
            differing.append(("template", template["id"], payload, _angle_payload(there)))
    return new, same, differing


def _lines(value) -> list[str]:
    if isinstance(value, str):
        return value.splitlines()
    return yaml.dump(value, sort_keys=True, allow_unicode=True).splitlines()


def render_conflicts(differing: list) -> str:
    """A unified diff per differing row, destination first.

    Destination as the "before" and the file as the "after", because that is the
    direction the push would move things — a reader is deciding whether to let
    the right-hand side win.
    """
    out = []
    for kind, name, wanted, held in differing:
        out.append(f"----- {kind} {name} -----")
        out += list(difflib.unified_diff(
            _lines(held), _lines(wanted),
            fromfile="destination", tofile="file", lineterm=""))
    return "\n".join(out)


def apply(library: dict, rows: list) -> int:
    """Write the named rows. Returns how many were written."""
    written = 0
    for kind, name, payload, _held in rows:
        if kind == "block":
            E.put_block(name, payload)
        else:
            E.put_template(name, payload)
        written += 1
    return written


# ── CLI ─────────────────────────────────────────────────────────────────────


@click.group("templates")
def main():
    """The template library: the prose a run's prompt is built from."""


@main.command("show")
def show():
    """What this stack holds, block by block and template by template."""
    try:
        library = fetch()
    except LibraryError as exc:
        die(str(exc))
    if not library["blocks"] and not library["templates"]:
        # Not an error. An empty library is a real state — a fresh stack has one
        # — and the useful answer is what to do about it, not a non-zero exit
        # that a script would treat as a failure to read.
        print("this library holds no templates — nothing to build a prompt from.\n"
              "       push some:  studio templates push --path <file>", file=sys.stderr)
        return 0
    print(f"blocks ({len(library['blocks'])})")
    for name, text in sorted(library["blocks"].items()):
        first = " ".join(text.split())
        print(f"  {name:<20} {first[:70]}{'…' if len(first) > 70 else ''}")
    print(f"\ntemplates ({len(library['templates'])})")
    for template in library["templates"]:
        print(f"  {template['id']:<32} {template.get('name') or ''}")
    return 0


@main.command("pull")
@click.option("--path", required=True, help="Where to write the document.")
def pull(path: str):
    """Write this stack's templates to a file you can read and edit."""
    try:
        library = fetch()
    except LibraryError as exc:
        die(str(exc))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(document(library))
    print(f"wrote {path} — {len(library['blocks'])} block(s), "
          f"{len(library['templates'])} template(s)", file=sys.stderr)
    return 0


@main.command("push")
@click.option("--path", required=True, help="The document to send.")
@click.option("--force", is_flag=True,
              help="Overwrite rows that differ, instead of refusing.")
@click.option("--dry-run", is_flag=True,
              help="Say what would be written; write nothing.")
def push(path: str, force: bool, dry_run: bool):
    """Send a template document to this profile's stack.

    Refuses outright if any row already there differs, printing the difference
    and writing NOTHING — not even the rows that were fine. A half-applied library
    is the hardest state to reason about, and the rows that differ are exactly
    the ones somebody has to decide about.
    """
    try:
        wanted = read_file(path)
        held = fetch()
    except LibraryError as exc:
        die(str(exc))

    new, same, differing = compare(wanted, held)

    if differing and not force:
        # The diff goes out FIRST and on stdout, because it is the thing being
        # read; `die` writes the one-line refusal and sets the exit code. A
        # `return 1` from a click callback sets neither — click ignores the
        # return value, so the refusal reported success for as long as this said
        # so, which is the failure mode a refusal can least afford.
        print(render_conflicts(differing))
        die(f"{len(differing)} row(s) already there and different. Nothing was "
            f"written.\n"
            f"       Read the diff above, then either fix {path} or — if the file "
            f"is right and\n"
            f"       the destination is stale — push again with --force.")

    writing = new + (differing if force else [])
    plan = (f"{len(new)} new, {len(differing)} overwritten, {len(same)} unchanged"
            if force else f"{len(new)} new, {len(same)} unchanged")
    if dry_run:
        for kind, name, _payload, _held in writing:
            print(f"  would write {kind} {name}", file=sys.stderr)
        print(f"(dry run — {plan}; nothing written)", file=sys.stderr)
        return 0
    if not writing:
        print(f"nothing to do — {plan}.", file=sys.stderr)
        return 0

    written = apply(wanted, writing)
    print(f"wrote {written} row(s) — {plan}.", file=sys.stderr)
    return 0
