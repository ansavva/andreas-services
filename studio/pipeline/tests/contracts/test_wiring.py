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

import ast
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

    root = studio_pipeline.STUDIO_DIR / "pipeline"
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
    """The profile template ships inside the package, and the registry no longer does.

    **`models.json` used to be asserted here and is deliberately not.** It moved
    to `backend/studio_core/`, because the API needed to measure a reference
    selection against the same entries the CLI does and could not read a file
    inside a Python package. What this package ships is the reader; the file is
    the backend's, and `registry_file.PATH` below is the repo path the two
    write commands edit, not a packaged resource.
    """
    import os

    from studio_pipeline.domain import characters
    from studio_pipeline.engine import registry_file

    assert os.path.isfile(characters.TEMPLATE), f"template missing at {characters.TEMPLATE}"
    assert os.path.isfile(registry_file.PATH), (
        f"the committed registry is missing at {registry_file.PATH} — "
        "`add-model` and `models refresh` write it"
    )


def test_local_working_dirs_resolve_under_studio():
    """`character edit` writes here, and it is git-ignored.

    **This used to assert a second directory and no longer does.** The journal
    half moved twice — `migrate_layout.JOURNAL_DIR`, then
    `catalog_seed.JOURNAL_DIR`, then `catalog_check.JOURNAL_DIR` — following
    each rename of the AWS-direct maintenance commands that wrote it. Those
    commands are deleted: `verify` and `gc` are gone with the orphan class they
    swept, which the API now records a sweep row for instead of leaving to be
    found by a bucket scan. Nothing writes a journal, so there is no second
    constant to follow.

    What is left is unchanged in what it protects: `local/` is git-ignored and
    must sit under `studio/`.
    """
    from studio_pipeline.domain import characters

    root = str(studio_pipeline.STUDIO_DIR)
    assert characters.LOCAL_DIR.startswith(root)
    assert characters.LOCAL_DIR.endswith("local/characters")


def test_every_callback_accepts_the_parameters_click_will_pass():
    """A declared option must match its callback's signature, statically.

    `--from` arrives as `from_` unless a name is given, and a callback expecting
    `src_pool` then raises TypeError — but only when the command is invoked WITH
    arguments. `test_every_subcommand_dispatches` invokes each leaf bare, so a
    command with required arguments exits on usage before the callback is ever
    called, and the mismatch survives. `studio curate move` was broken this way
    from the argparse port until someone tried to move an image.
    """
    import inspect

    import click

    from studio_pipeline import cli

    broken = []

    def walk(command, path):
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                walk(sub, path + [name])
            return
        if command.callback is None:
            return
        signature = inspect.signature(command.callback)
        if any(p.kind is p.VAR_KEYWORD for p in signature.parameters.values()):
            return                      # **options — takes whatever it is given
        unaccepted = {p.name for p in command.params} - set(signature.parameters)
        if unaccepted:
            broken.append(f"studio {' '.join(path)}: callback cannot accept {sorted(unaccepted)}")

    walk(cli.main, [])
    assert not broken, "\n".join(broken)


def test_dry_run_actually_renders_a_payload(library, monkeypatch):
    """`--dry-run` is what a person reads before saying to submit. It has to work.

    It read `args.json` while Click had stored the flag as `json_` (`json` is not
    a legal attribute name for it), so every `studio run --dry-run` raised
    AttributeError — the one command the spending rule tells everyone to use
    before billing. The wiring test above cannot see this: the callback takes
    `**options`, so it accepts every parameter; the mismatch is in the body.
    """
    from click.testing import CliRunner

    from studio_pipeline import cli

    # `quality` and `moderation` are here because the REAL model has them and
    # the registry now defaults both. A stub narrower than the model it stands
    # in for turns a correct default into a spurious "does not accept".
    props = {f: {} for f in ("prompt", "aspect_ratio", "output_format",
                             "input_images", "quality", "moderation")}
    monkeypatch.setattr("studio_pipeline.engine.schema.fetch", lambda *a, **k: (props, {}))

    result = CliRunner().invoke(cli.main, [
        "run", "--model", "gpt-image-2", "--project", "porch-teaser", "--dry-run",
        "--prompt", "a test", "--key", library.face_1])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "1/2  PROMPT" in result.output
    assert "2/2  INPUT" in result.output
    assert "a test" in result.output


def test_input_pool_numbers_actually_bind(library, monkeypatch):
    """`--input N` must reach the payload, not vanish.

    Click stores it as `input_` (`input` shadows the builtin), and `gather` read
    `args.input` through a defaulting getattr — so the flag bound nothing and
    raised nothing. A silent drop is worse than the crash its sibling caused:
    the run proceeds without the image the caller named.
    """
    from click.testing import CliRunner

    from studio_pipeline import cli

    props = {f: {} for f in ("prompt", "aspect_ratio", "input_images",
                             "quality", "moderation")}
    monkeypatch.setattr("studio_pipeline.engine.schema.fetch", lambda *a, **k: (props, {}))

    result = CliRunner().invoke(cli.main, [
        "run", "--model", "gpt-image-2", "--project", "porch-teaser", "--dry-run",
        "--prompt", "a test", "--input", "1"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    # Position one in the pool listing, as a NODE ID — `--input N` stopped
    # meaning "the file whose name ends _N" when the pool stopped being numbered.
    assert library.input_3 in result.output


# ── the modules this package borrows from the other half of studio ──────────

#: Backend `services/` modules the CLI's unit suite loads for real rather than
#: approximating: `tests/support/fake_api.py` imports each one so that a test
#: gets the API's own answer to "is this plan coherent", "will this prompt
#: render" and "is this the same payload as that one".
SHARED_SERVICES = ("digest", "prompt", "registry", "storyboard")

_SERVICES = studio_pipeline.STUDIO_DIR / "backend" / "studio_core" / "services"

#: What none of them may reach. Not a taste rule — the pipeline declares neither,
#: so an import of either turns every unit test in this suite into a test that
#: needs the backend's environment installed.
FORBIDDEN_ROOTS = frozenset({"flask", "boto3", "botocore", "werkzeug", "PIL",
                             "mangum", "jwt", "requests"})


def _imported_roots(source: pathlib.Path) -> set[str]:
    """Top-level module names a file imports, read out of the source.

    Static, so the answer does not depend on what happens to be installed in the
    interpreter running the suite — which is the whole question: a machine with
    Flask on it would pass a runtime probe while the wheel it ships still could
    not.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("name", SHARED_SERVICES)
def test_a_shared_backend_service_stays_loadable_from_here(name):
    """**The precondition the fake's `_backend_service` rests on.**

    Each of these is loaded, not copied — which is what stopped the fingerprint
    being a second implementation of the backend's, the copy whose own
    comment admitted nothing held the two together and which `routes/runs.py`
    records as one of three, one of them silently disagreeing.

    The arrangement holds only while the module reaches nothing the pipeline does
    not have. It is asserted here rather than left to fail at import because the
    failure would land in whichever unrelated test happened to touch the fake
    first, and would read as that test's problem.

    `registry` is on the list without being loaded directly: `prompt` imports it,
    so it is just as load-bearing.
    """
    reached = _imported_roots(_SERVICES / f"{name}.py")
    assert not (reached & FORBIDDEN_ROOTS), (
        f"services/{name}.py imports {sorted(reached & FORBIDDEN_ROOTS)}; "
        f"tests/support/fake_api.py loads it and this package declares none of them"
    )


@pytest.mark.parametrize("name", SHARED_SERVICES)
def test_a_shared_backend_service_reaches_only_shared_backend_modules(name):
    """The chain, not just the first link.

    `prompt` imports `registry`, which is why `registry` is on the list at all. A
    fourth module joining that chain without joining the list would be checked by
    nothing — and its own imports are exactly where Flask or boto3 would arrive.
    """
    allowed = {f"studio_core.services.{other}" for other in SHARED_SERVICES}
    allowed.add("studio_core.errors")

    reached = set()
    for node in ast.walk(ast.parse((_SERVICES / f"{name}.py").read_text())):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("studio_core"):
            if node.module == "studio_core.services":
                reached.update(f"studio_core.services.{alias.name}"
                               for alias in node.names)
            else:
                reached.add(node.module)
        elif isinstance(node, ast.Import):
            reached.update(alias.name for alias in node.names
                           if alias.name.startswith("studio_core"))

    assert reached <= allowed, (
        f"services/{name}.py reaches {sorted(reached - allowed)}; add it to "
        f"SHARED_SERVICES so its own imports are checked too, or stop reaching it"
    )
