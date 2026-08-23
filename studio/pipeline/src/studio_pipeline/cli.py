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

from studio_pipeline.domain import characters as _character
from studio_pipeline.domain import contact_sheet as _contact_sheet
from studio_pipeline.domain import curate as _curate
from studio_pipeline.domain import frames as _frames
from studio_pipeline.domain import movies as _movies
from studio_pipeline.domain import phrasebook as _phrasebook
from studio_pipeline.domain import projects as _projects
from studio_pipeline.domain import prompt as _prompt
from studio_pipeline.domain import runs as _runs
from studio_pipeline.domain import scenes as _scenes
from studio_pipeline.engine import add_model as _add_model
from studio_pipeline.engine import board as _board
from studio_pipeline.engine import runner as _runner
from studio_pipeline.engine import shoot as _shoot
from studio_pipeline.maintenance import catalog_gc as _catalog_gc
from studio_pipeline.maintenance import catalog_migrate as _catalog
from studio_pipeline.maintenance import dev_seed as _dev_seed
from studio_pipeline.objects import config_sync as _config_sync
from studio_pipeline.objects import convert as _convert
from studio_pipeline.session import commands as _session
from studio_pipeline.objects import download as _download
from studio_pipeline.objects import presign as _presign
from studio_pipeline.objects import upload as _upload


class _Grouped(click.Group):
    """A root group whose help is grouped rather than one flat alphabet.

    Twenty commands listed alphabetically tells you nothing about which layer
    each belongs to. Click has no native section support, so the listing is
    formatted here.
    """

    SECTIONS = [
        # First, because nothing below it works until you have signed in.
        ("session",     ["login", "logout", "whoami"]),
        ("generate",    ["run", "models", "add-model"]),
        ("records",     ["runs", "scenes", "movies", "frames", "projects"]),
        ("characters",  ["character", "curate", "contact-sheet"]),
        ("authoring",   ["prompt", "phrasebook"]),
        ("objects",     ["upload", "download", "presign", "convert", "config"]),
        ("maintenance", ["catalog", "dev-seed"]),
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
    "runs": "query the run store: list, find, show, outputs, adopt",
    # Its docstring's first line wraps mid-sentence, which truncates badly.
    "character": "manage on-model characters: profile, references, pools",
    # Its first line reads as prose about the fixture, not as what it does.
    "dev-seed": "promote a dev fixture into the shared seed bucket",
}

ROOT_HELP = """The studio generation pipeline.

Runs locally and talks to the studio API. Start with `studio login`. Nothing
here deploys, and nothing here needs an AWS account — that is the point of
#308. `studio <command> --help` for a command's own options.

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
# The session commands, registered first because nothing else works without
# them: after #308 the CLI holds no AWS credentials and every store call is an
# authenticated HTTP request.
main.add_command(_session.cmd_login, "login")
main.add_command(_session.cmd_logout, "logout")
main.add_command(_session.cmd_whoami, "whoami")

main.add_command(_runner.main.commands["run"], "run")
main.add_command(_runner.main.commands["models"], "models")

# `shoot` reads as a character command and is defined in `engine/` because it
# invokes models. Attaching it here rather than in `characters.py` keeps the
# dependency arrow pointing one way: the character store knows nothing about the
# engine, and only this wiring module knows about both.
_character.main.add_command(_shoot.cmd_shoot, "shoot")

# Same arrangement for the three scene commands that invoke models: the scene
# store stays a store, and `board`/`render`/`check` read as scene commands
# because that is what they are to a user.
_scenes.main.add_command(_board.cmd_board, "board")
_scenes.main.add_command(_board.cmd_render, "render")
_scenes.main.add_command(_board.cmd_check, "check")

# `gc` reads as a fifth catalog phase and is its own module because it is the
# only one that deletes. Attaching it here rather than defining it inside
# `catalog_migrate.py` keeps that separation visible: the migrator copies no
# bytes, moves no objects and deletes nothing, and nothing in it should have to
# say so twice.
_catalog.main.add_command(_catalog_gc.cmd_gc, "gc")


for _name, _cmd in [
    ("add-model", _add_model.add_model),
    ("runs", _runs.main),
    ("scenes", _scenes.main),
    ("movies", _movies.main),
    ("frames", _frames.main),
    ("projects", _projects.main),
    ("character", _character.main),
    ("curate", _curate.main),
    ("contact-sheet", _contact_sheet.contact_sheet),
    ("prompt", _prompt.prompt),
    ("phrasebook", _phrasebook.main),
    ("upload", _upload.upload),
    ("download", _download.download),
    ("presign", _presign.presign),
    ("convert", _convert.convert),
    ("config", _config_sync.main),
    ("catalog", _catalog.main),
    ("dev-seed", _dev_seed.main),
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
