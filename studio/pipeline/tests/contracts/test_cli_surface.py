"""The Click tree must expose exactly what argparse did.

`cli_surface_reference.json` was captured off the real argparse parsers before
the conversion: every command, subcommand, option, flag spelling, arity,
default, choice list, repeatability, value type and help string — 255 params.
Porting that by hand is 255 chances to move a default silently, so the port was
generated from this snapshot and these tests close the loop.

If a test here fails after an intentional CLI change, regenerate the reference
deliberately — do not edit it to match. It is the record of a contract.
"""

import json
import pathlib

import pytest

from studio_pipeline import cli
from tests.contracts import cli_surface

REFERENCE = json.loads(
    (pathlib.Path(__file__).parent / "cli_surface_reference.json").read_text()
)


def _live(name: str) -> dict:
    command = cli.main.get_command(None, name)
    assert command is not None, f"`studio {name}` is missing from the CLI"
    return cli_surface.from_click(command)


def _epilogs(name: str) -> str:
    """Every epilog in a command tree, concatenated.

    `click.argument` takes no `help=` — the one capability argparse has that
    Click does not. Rather than lose the text, the port folds each positional's
    description into its command's epilog, so `--help` still explains it. This
    is where that text is checked for.
    """
    import click

    def walk(cmd):
        yield cmd.epilog or ""
        if isinstance(cmd, click.Group):
            for sub in cmd.commands.values():
                yield from walk(sub)

    return " ".join(" ".join(t.split()) for t in walk(cli.main.get_command(None, name)))


def test_every_referenced_command_still_exists():
    live = set(cli.main.commands)
    assert set(REFERENCE) <= live, f"commands lost in the port: {set(REFERENCE) - live}"


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_command_surface_matches_reference(name):
    expected, actual = REFERENCE[name], _live(name)

    assert set(actual["commands"]) == set(expected["commands"]), (
        f"`studio {name}` subcommands differ: "
        f"missing={set(expected['commands']) - set(actual['commands'])}, "
        f"added={set(actual['commands']) - set(expected['commands'])}"
    )

    for scope, exp_node in [("", expected)] + [
        (sub, expected["commands"][sub]) for sub in expected["commands"]
    ]:
        act_node = actual if scope == "" else actual["commands"][scope]
        where = f"studio {name} {scope}".strip()
        for kind in ("options", "arguments"):
            assert set(act_node[kind]) == set(exp_node[kind]), (
                f"{where}: {kind} differ: "
                f"missing={set(exp_node[kind]) - set(act_node[kind])}, "
                f"added={set(act_node[kind]) - set(exp_node[kind])}"
            )
            for param, exp in exp_node[kind].items():
                act = act_node[kind][param]
                for field in ("flags", "nargs", "default", "required",
                              "choices", "flag", "multiple", "type"):
                    if field not in exp:
                        continue
                    assert act.get(field) == exp.get(field), (
                        f"{where} --{param}: {field} changed "
                        f"{exp.get(field)!r} -> {act.get(field)!r}"
                    )


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_help_text_survived(name):
    """Help strings are the CLI's documentation; a silent port must keep them."""
    expected, actual = REFERENCE[name], _live(name)
    lost = []
    for scope, exp_node in [("", expected)] + [
        (sub, expected["commands"][sub]) for sub in expected["commands"]
    ]:
        act_node = actual if scope == "" else actual["commands"].get(scope, {})
        for kind in ("options", "arguments"):
            for param, exp in exp_node[kind].items():
                if not exp.get("help"):
                    continue
                got = (act_node.get(kind, {}).get(param) or {}).get("help", "")
                want = " ".join(exp["help"].split())
                # Click re-wraps; compare on collapsed whitespace. A positional
                # carries its text in the epilog instead (see _epilogs).
                if " ".join(got.split()) == want:
                    continue
                if kind == "arguments" and want in _epilogs(name):
                    continue
                lost.append(f"studio {name} {scope} --{param}".replace("  ", " "))
    assert not lost, f"help text changed or lost on: {lost}"


def test_the_reference_is_canonically_serialised():
    """**The file must already be exactly what `cli_surface.dumps` would write.**

    This is the enforcement that a docstring was standing in for, and standing in
    badly: how the reference is encoded has been got wrong twice, in opposite
    directions — once by escaping every non-ASCII character while the file held
    literal ones, once by the reverse. Both times, a helper asked to add a single
    command also rewrote ten help strings belonging to commands nobody had
    touched, which buries the reviewable diff that is the only thing making it
    safe to update a contract at all.

    A sentence saying "use these settings" cannot fail. This can, and it fails on
    the commit that introduces the drift rather than on the unrelated PR that
    next runs the helper.

    If this goes red: do not hand-edit the file to match. Run
    `uv run python -m tests.contracts.update_cli_reference <command>` for a
    command you actually changed, and the whole file comes back canonical — then
    read the diff, which is the point.
    """
    on_disk = cli_surface.REFERENCE.read_text()

    assert cli_surface.dumps(json.loads(on_disk)) == on_disk, (
        "cli_surface_reference.json is not in the form `cli_surface.dumps` "
        "writes, so the next update to it will rewrite lines nobody changed"
    )
