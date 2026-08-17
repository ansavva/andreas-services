"""The tests that would have caught the move.

Not feature tests — these assert the things a restructure breaks and a
`--help` smoke test does not: that every module imports, that the constants
pointing at files still point at files, that the CLI reaches every command, and
that the cross-module calls resolve.

The `import os` that went missing from `engine/refs.py` during the package move
passed every `--help` in the suite, because printing usage does not touch the
function that used it. `test_no_undefined_names_anywhere` here, and
`test_project_input_keys_resolve_in_the_order_asked_for` in the cross-module
suite, are the two that go red on it.
"""

import importlib
import pathlib
import pkgutil

import pytest

import studio_pipeline
from studio_pipeline import cli

_COMMANDS = sorted(cli.main.commands)


def test_studio_dir_points_at_the_service_root():
    """STUDIO_DIR is the constant every module derives its paths from."""
    assert studio_pipeline.STUDIO_DIR.name == "studio"
    assert (studio_pipeline.STUDIO_DIR / "pipeline" / "pyproject.toml").is_file()
    # The two halves of the service, proving this is the shared root and not
    # the package directory.
    assert (studio_pipeline.STUDIO_DIR / "backend").is_dir()
    assert (studio_pipeline.STUDIO_DIR / ".claude" / "skills").is_dir()


def _all_modules():
    for info in pkgutil.walk_packages(studio_pipeline.__path__,
                                      prefix="studio_pipeline."):
        yield info.name


@pytest.mark.parametrize("name", sorted(_all_modules()))
def test_every_module_imports(name):
    """A module that cannot import is a module whose command cannot run."""
    importlib.import_module(name)


def test_no_undefined_names_anywhere():
    """Static analysis over the package for undefined names (pyflakes F821).

    This is the check that the `import os` dropped from `engine/refs.py` during
    the package move needed. Every subcommand's `--help` passed with it broken,
    because printing usage never reaches the function that used it.

    Delegated to ruff rather than hand-rolled: a first attempt walked each
    function's `co_names` and compared against module globals, which flags every
    attribute and method name as undefined and false-positived on 24 of 26
    modules. Undefined-name analysis needs real scope tracking, and ruff has it.
    """
    import shutil
    import subprocess

    ruff = shutil.which("ruff")
    if not ruff:
        pytest.skip("ruff not on PATH (it is in the dev dependency group)")

    root = pathlib.Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [ruff, "check", "--select", "F821,F822,F811", "--output-format", "concise",
         str(root / "studio_pipeline")],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"undefined or redefined names:\n{out.stdout}"


def test_every_command_is_in_a_help_section():
    """The root help is grouped by hand, so a new command can miss a section.

    An ungrouped command still runs but never appears in `studio --help`, which
    is the same as not existing for anyone discovering the tool.
    """
    sectioned = {n for _, names in cli._Grouped.SECTIONS for n in names}
    registered = set(cli.main.commands)
    assert registered == sectioned, (
        f"registered but not in any help section: {registered - sectioned}; "
        f"in a section but not registered: {sectioned - registered}"
    )


@pytest.mark.parametrize("command", sorted(_COMMANDS))
def test_every_command_is_invocable(command):
    """Each attached command is a real Click command with a callback."""
    import click

    cmd = cli.main.get_command(None, command)
    assert isinstance(cmd, click.Command), f"{command} is not a Click command"
    assert cmd.callback is not None or isinstance(cmd, click.Group), (
        f"{command} has no callback and is not a group"
    )


@pytest.mark.parametrize("command", sorted(_COMMANDS))
def test_every_command_help_renders(command):
    """`--help` must not raise — a bad epilog or help string only shows here."""
    from click.testing import CliRunner

    result = CliRunner().invoke(cli.main, [command, "--help"])
    assert result.exit_code == 0, f"studio {command} --help failed:\n{result.output}"


def test_root_help_renders():
    from click.testing import CliRunner

    result = CliRunner().invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    for title, _ in cli._Grouped.SECTIONS:
        assert title in result.output, f"section {title!r} missing from root help"


def test_packaged_data_files_exist():
    """models.json and the profile template ship inside the package.

    Both were reached by relative path before the move, and a wheel that omits
    them fails only at runtime.
    """
    import os

    from studio_pipeline.domain import characters
    from studio_pipeline.engine import registry

    assert os.path.isfile(registry.PATH), f"registry missing at {registry.PATH}"
    assert os.path.isfile(characters.TEMPLATE), f"template missing at {characters.TEMPLATE}"


def test_local_working_dirs_resolve_under_studio():
    """`character edit` and the migrator write here; both are git-ignored."""
    from studio_pipeline.domain import characters
    from studio_pipeline.maintenance import migrate_layout

    root = str(studio_pipeline.STUDIO_DIR)
    assert characters.LOCAL_DIR.startswith(root)
    assert characters.LOCAL_DIR.endswith("local/characters")
    assert migrate_layout.JOURNAL_DIR.startswith(root)
