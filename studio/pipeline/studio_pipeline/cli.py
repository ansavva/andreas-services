"""`studio` — one entry point over the whole pipeline.

There used to be nineteen of these. Every script carried its own argparse
parser and was invoked by its path, so using the pipeline meant knowing which
file implemented what, and the `SKILL.md` files were full of shell fragments
like `S3=.claude/skills/studio-s3/scripts` to make that bearable.

This dispatches to exactly those parsers, unchanged. Each subcommand below is a
module whose `main()` reads `sys.argv`, so `studio runs list --json` runs the
same code `runs.py list --json` did, including its `--help`. Nothing about the
individual command surfaces was redesigned here — that would have made a large
move impossible to review.

Note `run` and `runs`, which are close together on purpose:

    studio run …     submit a generation      (creates a run)
    studio runs …    query the run store      (reads the runs)
"""

from __future__ import annotations

import importlib
import sys

# subcommand -> (module path, the argv it forwards, one-line help)
#
# Most forward nothing and simply pass the user's arguments through. `models`
# and `run` both live in the runner, which has its own two-way subparser, so
# they prepend the word that parser expects.
COMMANDS: dict[str, tuple[str, list[str], str]] = {
    # the model layer
    "run":           ("studio_pipeline.engine.runner", ["run"],    "submit a generation to any registered model"),
    "models":        ("studio_pipeline.engine.runner", ["models"], "the model registry: list, show, refresh"),
    "add-model":     ("studio_pipeline.engine.add_model", [], "register a new Replicate model"),
    # the record stores
    "runs":          ("studio_pipeline.store.runs", [],     "the run store: list, find, show, outputs, favorite"),
    "scenes":        ("studio_pipeline.store.scenes", [],   "the scene store: chain runs into one cut"),
    "movies":        ("studio_pipeline.store.movies", [],   "the movie store: cut scenes into a piece"),
    "frames":        ("studio_pipeline.store.frames", [],   "pull a handoff frame or a verification grid"),
    "projects":      ("studio_pipeline.store.projects", [], "the project registry and its input pool"),
    # characters
    "character":     ("studio_pipeline.characters.character", [], "character records: create, update, list, load"),
    "curate":        ("studio_pipeline.characters.curate", [],    "curate a character's reference library"),
    "contact-sheet": ("studio_pipeline.characters.contact_sheet", [], "render a contact sheet of references"),
    # authoring
    "prompt":        ("studio_pipeline.prompt.build", [],      "author and validate a structured video prompt"),
    "phrasebook":    ("studio_pipeline.store.phrasebook", [],  "the shared wording list"),
    # raw object access
    "upload":        ("studio_pipeline.store.upload", [],   "upload a local file into the tree"),
    "download":      ("studio_pipeline.store.download", [], "download an object to disk"),
    "presign":       ("studio_pipeline.store.presign", [],  "mint a short-lived HTTPS URL"),
    "convert":       ("studio_pipeline.store.convert", [],  "convert an object to a format a model accepts"),
    # maintenance — one-shots, kept because they document what was done
    "rewrite":       ("studio_pipeline.store.rewrite", [],  "rewrite records that name a moved object"),
    "backfill-replicate": ("studio_pipeline.store.backfill_replicate", [], "import past Replicate predictions"),
    "migrate-layout":     ("studio_pipeline.store.migrate_layout", [],     "one-shot: migrate a pre-2026 bucket layout"),
}

# Printed in this order rather than alphabetically — it is roughly the order you
# meet them, and the grouping is the pipeline's actual shape.
GROUPS = [
    ("generate",   ["run", "models", "add-model"]),
    ("records",    ["runs", "scenes", "movies", "frames", "projects"]),
    ("characters", ["character", "curate", "contact-sheet"]),
    ("authoring",  ["prompt", "phrasebook"]),
    ("objects",    ["upload", "download", "presign", "convert"]),
    ("maintenance", ["rewrite", "backfill-replicate", "migrate-layout"]),
]


def usage() -> str:
    lines = ["usage: studio <command> [args]", "", "  studio <command> --help   for a command's own options", ""]
    for title, names in GROUPS:
        lines.append(f"{title}:")
        for name in names:
            lines.append(f"  {name:<21} {COMMANDS[name][2]}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"studio: unknown command {name!r}\n", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 2
    module_path, prefix, _ = COMMANDS[name]
    module = importlib.import_module(module_path)
    # The sub-parsers read sys.argv, so this is how the arguments reach them.
    # argv[0] carries the full command so their `--help` says `studio runs`
    # rather than the module's filename.
    sys.argv = [f"studio {name}", *prefix, *rest]
    return module.main() or 0


if __name__ == "__main__":
    raise SystemExit(main())
