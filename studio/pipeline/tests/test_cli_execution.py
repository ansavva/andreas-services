"""Commands that actually run, against the moto bucket.

The surface tests inspect the parser and never dispatch, so they passed while
`args.func` — which argparse attached through `set_defaults` and Click has no
equivalent for — was undefined on every subcommand of `character`, `curate` and
`run`. `--help` passed too. Only invoking a command finds that class of bug,
which is what this file is for.

Read-only commands, deliberately: the point is proving the dispatch path
reaches real logic, not re-testing what each command does.
"""

import pytest
from click.testing import CliRunner

from studio_pipeline import cli

# (argv, a fragment that must appear in the output)
READ_ONLY = [
    (["character", "list"], "subject-a"),
    (["character", "show", "subject-a"], "Subject A"),
    (["character", "refs", "subject-a", "--keys"], "reference/face/subject-a_1.webp"),
    (["character", "pool", "subject-a", "seed"], "seed/subject-a_1.webp"),
    (["curate", "groups", "subject-a"], "face"),
    (["projects", "list"], "subject-a"),
    (["projects", "show", "subject-a"], "subject-a"),
    (["runs", "list", "subject-a"], "wave-porch"),
    (["scenes", "list", "subject-a"], "board-test"),
    (["scenes", "plan", "subject-a/board-test"], "shot-01"),
    (["scenes", "show", "subject-a/board-test"], "storyboard"),
    (["phrasebook", "terms", "--model", "kling"], "bare chest"),
    (["phrasebook", "models"], "kling"),
    (["models"], "seedance"),
]


@pytest.mark.parametrize("argv,expected", READ_ONLY, ids=lambda v: " ".join(v) if isinstance(v, list) else "")
def test_command_runs(media_bucket, argv, expected):
    result = CliRunner().invoke(cli.main, argv)
    assert result.exit_code == 0, (
        f"`studio {' '.join(argv)}` exited {result.exit_code}\n"
        f"{result.output}\n{result.exception!r}"
    )
    assert expected in result.output, (
        f"`studio {' '.join(argv)}` did not mention {expected!r}:\n{result.output}"
    )


def test_every_subcommand_dispatches(media_bucket):
    """No subcommand may fail on a missing handler.

    Walks the whole tree and invokes each leaf with no arguments. A command
    that needs arguments exits 2 (usage) — that is fine, it proves Click routed
    to it. What must never happen is an AttributeError or a KeyError, which is
    what a missing dispatch entry raises.
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


def test_repeatable_option_collects_every_value(media_bucket):
    """`--pick` twice must keep both, not the last.

    Ten options used `action="append"`. Click spells that `multiple=True`, and
    getting it wrong silently keeps only the final value — the kind of thing
    that shows up as a generation quietly using one reference image.
    """
    result = CliRunner().invoke(cli.main, [
        "character", "refs", "subject-a", "--keys",
        "--pick", "face/subject-a_1.webp,body/subject-a_1.webp",
    ])
    assert result.exit_code == 0, result.output
    assert "face/subject-a_1.webp" in result.output
    assert "body/subject-a_1.webp" in result.output


def test_usage_error_exits_two(media_bucket):
    """A mutually exclusive pair still refuses, with argparse's exit code."""
    result = CliRunner().invoke(cli.main, ["contact-sheet", "--out", "/tmp/x.png"])
    assert result.exit_code == 2, result.output
    assert "exactly one of --character or --src" in result.output


# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------
# Click's standalone mode DISCARDS a command's return value — it only honours
# it when invoked with standalone_mode=False. The argparse->Click port kept
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
def test_exit_code_is_honoured(media_bucket, argv, expected):
    result = CliRunner().invoke(cli.main, argv)
    assert result.exit_code == expected, (
        f"`studio {' '.join(argv)}` exited {result.exit_code}, expected {expected}\n"
        f"{result.output}"
    )


def test_character_refs_downloads(media_bucket, tmp_path):
    """**The path ruff found and 517 tests did not.**

    Splitting `characters.py` into a package left `tempfile` unimported in the
    module that took `refs`' download branch, so `studio character refs <name>`
    with no `--keys` and no `--presign` raised `NameError`. Nothing caught it:
    `test_every_subcommand_dispatches` invokes each leaf with no arguments and
    stops at the usage error, which never reaches a body.

    That is the same shape as the two failures `--help is not a test` was
    written for. The download branch is the default one — no flag selects it —
    so it is the branch a person gets by typing the obvious thing.
    """
    result = CliRunner().invoke(
        cli.main, ["character", "refs", "subject-a", "--dest", str(tmp_path)]
    )

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert list(tmp_path.iterdir()), "nothing was written to --dest"


def test_character_refs_keys_still_prints_keys(media_bucket):
    """The other half of the same fix: `--keys` must still print them.

    The bug was that BOTH branches printed keys, so a test of `--keys` alone
    would have passed against the broken code.
    """
    result = CliRunner().invoke(cli.main, ["character", "refs", "subject-a", "--keys"])

    assert result.exit_code == 0, result.output
    assert "characters/subject-a/reference/" in result.output
