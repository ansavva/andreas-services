"""Commands that actually run, against the in-memory library.

The surface tests inspect the parser and never dispatch, so they passed while
`args.func` — which argparse attached through `set_defaults` and Click has no
equivalent for — was undefined on every subcommand of `character`, `curate` and
`run`. `--help` passed too. Only invoking a command finds that class of bug,
which is what this file is for, and a restructure is exactly the change that
produces it.

**These now go through the real adapter stack.** Under the old fixture `store`
was monkeypatched onto a moto bucket in which a node's id was its key, so a
command could send a route or a body the API would refuse and still pass here.
`tests/support/fake_api.py` answers `api.request` instead, so what is exercised is what
the CLI actually puts on the wire.

Read-only commands where possible, deliberately: the point is proving the
dispatch path reaches real logic, not re-testing what each command does.
"""

import pytest
from click.testing import CliRunner

from studio_pipeline import cli

# (argv, a fragment that must appear in the output)
READ_ONLY = [
    (["character", "list"], "subject-a"),
    (["character", "show", "subject-a"], "subject-a"),
    (["character", "refs", "subject-a"], "front-neutral.webp"),
    (["character", "textblock", "subject-a"], "placeholder identity"),
    (["curate", "groups", "subject-a"], "face"),
    (["projects", "list"], "porch-teaser"),
    (["projects", "show", "porch-teaser"], "porch-teaser"),
    (["projects", "inputs", "porch-teaser"], "street-plate.webp"),
    # A run has no label — a listing row carries id, created, model, kind,
    # status and nothing else. Asserting on the model is asserting on a field
    # the projection really holds, which is the whole lesson of `_row`.
    (["runs", "list", "porch-teaser"], "google/nano-banana-pro"),
    (["runs", "find", "--character", "subject-a"], "google/nano-banana-pro"),
    (["models"], "seedance"),
]


@pytest.mark.parametrize("argv,expected", READ_ONLY,
                         ids=lambda v: " ".join(v) if isinstance(v, list) else "")
def test_command_runs(library, argv, expected):
    result = CliRunner().invoke(cli.main, argv)
    assert result.exit_code == 0, (
        f"`studio {' '.join(argv)}` exited {result.exit_code}\n"
        f"{result.output}\n{result.exception!r}"
    )
    assert expected in result.output, (
        f"`studio {' '.join(argv)}` did not mention {expected!r}:\n{result.output}"
    )


def test_every_subcommand_dispatches(library):
    """No subcommand may fail on a missing handler.

    Walks the whole tree and invokes each leaf with no arguments. A command that
    needs arguments exits 2 (usage) — that is fine, it proves Click routed to
    it. What must never happen is an AttributeError or a KeyError, which is what
    a missing dispatch entry raises.
    """
    import click

    def leaves(cmd, path):
        if isinstance(cmd, click.Group):
            for name, sub in cmd.commands.items():
                yield from leaves(sub, path + [name])
        else:
            yield path

    runner, broken = CliRunner(), []
    for path in leaves(cli.main, []):
        result = runner.invoke(cli.main, path)
        exc = result.exception
        if isinstance(exc, (AttributeError, KeyError, NameError, TypeError)):
            broken.append(f"studio {' '.join(path)} -> {type(exc).__name__}: {exc}")
    assert not broken, "commands that cannot dispatch:\n" + "\n".join(broken)


def test_a_comma_list_collects_every_value(library):
    """`--pick a,b` must keep both, not the last.

    Ten options used argparse's `action="append"`; Click spells repeatability
    `multiple=True`, and getting it wrong silently keeps only the final value —
    the kind of thing that shows up as a generation quietly using one reference
    image. `--pick` is the comma-separated half of the same hazard, and the
    consequence is identical.
    """
    result = CliRunner().invoke(cli.main, [
        "character", "selection", "subject-a",
        "--pick", "front-neutral.webp,full-length.webp",
    ])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert library.face_1 in result.output
    assert library.body_1 in result.output


def test_usage_error_exits_two(library):
    """A mutually exclusive pair still refuses, with argparse's exit code."""
    result = CliRunner().invoke(cli.main, ["contact-sheet", "--out", "/tmp/x.png"])
    assert result.exit_code == 2, result.output
    assert "exactly one of --character or --src" in result.output


# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------
# Click's standalone mode DISCARDS a command's return value — it only honours it
# when invoked with standalone_mode=False. The argparse->Click port kept
# `return 1` from the old dispatch functions, so every non-zero exit silently
# became 0. `--strict` that never fails is worse than no `--strict` at all.
EXIT_CODES = [
    # (argv, expected exit)
    (["prompt", "--engine", "kling", "--subject", "a runner",
      "--action", "moves fast down the track", "--strict"], 1),
    (["prompt", "--engine", "kling", "--subject", "a runner",
      "--action", "moves fast down the track"], 0),
    (["phrasebook", "check", "--model", "kling", "--text", "bare chest"], 1),
    (["phrasebook", "check", "--model", "kling", "--text", "nothing matches"], 0),
]


@pytest.mark.parametrize("argv,expected", EXIT_CODES,
                         ids=lambda v: " ".join(v) if isinstance(v, list) else str(v))
def test_exit_code_is_honoured(library, argv, expected):
    if argv[0] == "phrasebook":
        # A term has to exist for `check` to hit. It is one row now, and adding
        # it needs no document to be there first — which is the failure that
        # disappeared with the YAML file.
        from studio_pipeline.adapters import entities

        entities.add_phrasebook_term("kling", "bare chest", "chest")
    result = CliRunner().invoke(cli.main, argv)
    assert result.exit_code == expected, (
        f"`studio {' '.join(argv)}` exited {result.exit_code}, expected {expected}\n"
        f"{result.output}"
    )


def test_character_selection_downloads(library, tmp_path):
    """**The path ruff found and 517 tests did not.**

    Splitting `characters.py` into a package left `tempfile` unimported in the
    module that took the download branch, so `studio character refs <name>` with
    no selector raised `NameError`. Nothing caught it:
    `test_every_subcommand_dispatches` invokes each leaf with no arguments and
    stops at the usage error, which never reaches a body.

    That branch lives on `selection` now — `refs` prints the index and
    `selection` resolves it, which is the split the entity model made real by
    moving resolution into the API. The hazard did not move: a branch nothing
    invokes is a branch nothing checks.
    """
    result = CliRunner().invoke(
        cli.main, ["character", "selection", "subject-a", "--dest", str(tmp_path)]
    )

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert list(tmp_path.iterdir()), "nothing was written to --dest"


def test_character_selection_prints_node_ids_by_default(library):
    """The other half of the same fix: the printing branch must still print.

    The original bug was that BOTH branches printed keys, so a test of the flag
    alone would have passed against the broken code. What is printed is a NODE
    ID now — what a record holds and what a binding names — beside its slot, so
    `[Image1]` in a prompt and slot 1 here are the same image.
    """
    result = CliRunner().invoke(cli.main, ["character", "selection", "subject-a"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "slot 1" in result.output
    assert library.face_1 in result.output
