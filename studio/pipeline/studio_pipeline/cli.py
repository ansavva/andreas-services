"""`studio` — the command over the whole generation pipeline.

This module is only wiring: every command is defined in the module that
implements it, and this attaches them to one root group.

History, because it explains the shape. There used to be nineteen argparse
parsers invoked by file path, and then a dispatcher that swapped `sys.argv` to
forward to them. Both are gone — Click resolves the tree itself, so
`studio runs show --help` is routed rather than rewritten on the way through.

Nothing about the individual command surfaces changed in that move.
`tests/cli_surface_reference.json` is a snapshot of what argparse exposed —
every option, its flags, arity, default, choices, repeatability and help — and
`test_cli_surface.py` asserts the Click tree still matches it.
"""

from __future__ import annotations

import click

from studio_pipeline.characters import character as _character
from studio_pipeline.characters import contact_sheet as _contact_sheet
from studio_pipeline.characters import curate as _curate
from studio_pipeline.engine import add_model as _add_model
from studio_pipeline.engine import runner as _runner
from studio_pipeline.prompt import build as _prompt
from studio_pipeline.store import backfill_replicate as _backfill
from studio_pipeline.store import convert as _convert
from studio_pipeline.store import download as _download
from studio_pipeline.store import frames as _frames
from studio_pipeline.store import migrate_layout as _migrate
from studio_pipeline.store import movies as _movies
from studio_pipeline.store import phrasebook as _phrasebook
from studio_pipeline.store import presign as _presign
from studio_pipeline.store import projects as _projects
from studio_pipeline.store import rewrite as _rewrite
from studio_pipeline.store import runs as _runs
from studio_pipeline.store import scenes as _scenes
from studio_pipeline.store import upload as _upload


class _Grouped(click.Group):
    """A root group whose help is grouped rather than one flat alphabet.

    Twenty commands listed alphabetically tells you nothing about which layer
    each belongs to. Click has no native section support, so the listing is
    formatted here.
    """

    SECTIONS = [
        ("generate",    ["run", "models", "add-model"]),
        ("records",     ["runs", "scenes", "movies", "frames", "projects"]),
        ("characters",  ["character", "curate", "contact-sheet"]),
        ("authoring",   ["prompt", "phrasebook"]),
        ("objects",     ["upload", "download", "presign", "convert"]),
        ("maintenance", ["rewrite", "backfill-replicate", "migrate-layout"]),
    ]

    def format_commands(self, ctx, formatter):
        for title, names in self.SECTIONS:
            rows = []
            for name in names:
                cmd = self.get_command(ctx, name)
                if cmd is None or cmd.hidden:
                    continue
                rows.append((name, (cmd.get_short_help_str(limit=60) or "")))
            if rows:
                with formatter.section(title):
                    formatter.write_dl(rows)

    def list_commands(self, ctx):
        """Section order, not alphabetical — it is roughly the order you meet them."""
        ordered = [n for _, names in self.SECTIONS for n in names]
        return ordered + sorted(set(self.commands) - set(ordered))


SHORT_HELP = {
    # Two commands read alike and are not, so both say which is which.
    "run": "submit a generation to any registered model (creates a run)",
    "models": "the model registry: list, show, refresh",
    "runs": "query the run store: list, find, show, outputs, favorite",
    # Its docstring's first line wraps mid-sentence, which truncates badly.
    "character": "manage on-model characters: profile, references, pools",
}

ROOT_HELP = """The studio generation pipeline.

Runs locally, under your own AWS login, against the media bucket. Nothing here
deploys. `studio <command> --help` for a command's own options.

Note `run` and `runs` are different: `run` submits a generation, `runs` queries
the ones already recorded.
"""


@click.group(cls=_Grouped, help=ROOT_HELP)
@click.version_option(package_name="studio-pipeline", prog_name="studio")
def main() -> None:
    pass


# `run` and `models` are the runner's own two subcommands, lifted to the top
# level because that is where a user meets them. Attaching the existing command
# objects keeps one definition of each.
main.add_command(_runner.main.commands["run"], "run")
main.add_command(_runner.main.commands["models"], "models")


for _name, _cmd in [
    ("add-model", _add_model.main),
    ("runs", _runs.main),
    ("scenes", _scenes.main),
    ("movies", _movies.main),
    ("frames", _frames.main),
    ("projects", _projects.main),
    ("character", _character.main),
    ("curate", _curate.main),
    ("contact-sheet", _contact_sheet.main),
    ("prompt", _prompt.main),
    ("phrasebook", _phrasebook.main),
    ("upload", _upload.main),
    ("download", _download.main),
    ("presign", _presign.main),
    ("convert", _convert.main),
    ("rewrite", _rewrite.main),
    ("backfill-replicate", _backfill.main),
    ("migrate-layout", _migrate.main),
]:
    main.add_command(_cmd, _name)


# Each module's docstring opens with "`studio <cmd>` — …", which is the right
# title inside the module and redundant beside the command name in a listing.
for _n, _cmd in main.commands.items():
    if _n in SHORT_HELP:
        _cmd.short_help = SHORT_HELP[_n]
    elif _cmd.help:
        _first = _cmd.help.strip().split("\n")[0]
        if _first.startswith("`studio ") and " — " in _first:
            _cmd.short_help = _first.split(" — ", 1)[1].rstrip(".")


if __name__ == "__main__":
    main()
