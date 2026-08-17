"""The skills must describe the CLI that exists.

`test_cli_surface.py` guards the CLI's shape against a recorded contract. Nothing
guarded the other side: the fifteen `SKILL.md` files under `studio/.claude/skills/`
are what an agent actually reads, and they could describe a CLI that was renamed
out from under them without a single test going red.

That is not hypothetical. The pipeline arrived from a separate repo where each
module was a directly-invoked script, so the docs told you to run
`character.py refs <name> --describe`. Packaging it behind one Click command
made every one of those lines unrunnable, and they survived the move — in the
prose, in the tables, and in `die()` strings the CLI printed at the exact moment
someone was stuck. An agent that followed them fell back to raw `aws s3` calls
and rebuilt by hand what `studio character refs --describe` returns directly.

Three properties, checked against the live Click tree rather than a snapshot,
so they cannot drift apart:

1. every `studio …` line in the skills names a real command and subcommand
2. no `<module>.py <subcommand>` survives in command position — a bare
   `` `runs.py` `` naming a source file is fine and stays fine
3. every relative link in a skill resolves, and every `.py` it names is a
   module that exists
"""

from __future__ import annotations

import pathlib
import re

import click
import pytest

import studio_pipeline
from studio_pipeline import cli

SKILLS = sorted((studio_pipeline.STUDIO_DIR / ".claude" / "skills").glob("*/SKILL.md"))
SRC = studio_pipeline.STUDIO_DIR / "pipeline" / "src" / "studio_pipeline"

# Every command, and the subcommands it accepts (empty set = takes none).
SUBCOMMANDS = {
    name: (set(command.commands) if isinstance(command, click.Group) else set())
    for name, command in cli.main.commands.items()
}

# Module basename -> the `studio` command it became. A `<module>.py <sub>` pair
# where `<sub>` is genuinely one of that command's subcommands is a leftover
# from the script era, not prose.
FORMER_SCRIPTS = {
    "character": "character", "curate": "curate", "runs": "runs",
    "scenes": "scenes", "movies": "movies", "frames": "frames",
    "projects": "projects", "rewrite": "rewrite", "phrasebook": "phrasebook",
    "models": "models", "build_prompt": "prompt", "s3_convert": "convert",
}

# Named in the docs as history, deliberately: the escape hatches that were
# removed when S3 became the only origin. They must not come back as modules.
REMOVED_ON_PURPOSE = {"upload_to_replicate.py"}

# `studio` only counts as an invocation at the start of a line or just inside a
# backtick. Otherwise "grey studio backdrop" in a reference description reads as
# a call to a `backdrop` command.
_STUDIO_CALL = re.compile(r"(?:^|`|\$ )studio ([a-z][\w-]*)(?:[ \t]+([^\s`'\"\\]+))?", re.M)
_SCRIPT_CALL = re.compile(r"\b([a-z_]+)\.py ([a-z][\w-]*)")
_MODULE_NAME = re.compile(r"`(?:[\w/]*/)?([a-z_]+\.py)")
_LINK = re.compile(r"\]\((\.\.?/[^)#]*)\)")


def _skill_id(path: pathlib.Path) -> str:
    return path.parent.name


@pytest.mark.parametrize("skill", SKILLS, ids=_skill_id)
def test_every_documented_command_exists(skill):
    """`studio foo bar` in a skill must be a command you can actually run."""
    bad = []
    for command, second in _STUDIO_CALL.findall(skill.read_text()):
        if command.startswith("-"):
            continue
        if command not in SUBCOMMANDS:
            bad.append(f"`studio {command}` is not a command")
            continue
        # A group needs a subcommand; a flag, a trailing `# comment` or a shell
        # continuation is fine.
        if SUBCOMMANDS[command] and second and not second.startswith(("-", "#")):
            if second not in SUBCOMMANDS[command]:
                bad.append(
                    f"`studio {command} {second}` — {command} has no {second!r} "
                    f"(has: {', '.join(sorted(SUBCOMMANDS[command]))})"
                )
    assert not bad, f"{_skill_id(skill)} documents commands that do not exist:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("skill", SKILLS, ids=_skill_id)
def test_no_script_era_invocations(skill):
    """`character.py refs <name>` is not runnable. `` `runs.py` `` alone is fine."""
    bad = []
    for module, second in _SCRIPT_CALL.findall(skill.read_text()):
        command = FORMER_SCRIPTS.get(module)
        if command and (not SUBCOMMANDS[command] or second in SUBCOMMANDS[command]):
            bad.append(f"`{module}.py {second}` -> `studio {command} {second}`")
    assert not bad, (
        f"{_skill_id(skill)} still tells the reader to run a module directly:\n  "
        + "\n  ".join(bad)
    )


@pytest.mark.parametrize("skill", SKILLS, ids=_skill_id)
def test_named_modules_and_links_resolve(skill):
    """A doc may name a source file, but only one that is really there."""
    modules = {
        name for name in _MODULE_NAME.findall(skill.read_text())
        if name not in REMOVED_ON_PURPOSE
    }
    missing = sorted(m for m in modules if not any(SRC.rglob(m)))
    assert not missing, f"{_skill_id(skill)} names modules that do not exist: {missing}"

    broken = sorted(
        target for target in _LINK.findall(skill.read_text())
        if not (skill.parent / target).resolve().exists()
    )
    assert not broken, f"{_skill_id(skill)} has links that go nowhere: {broken}"


def test_runtime_strings_do_not_teach_the_old_invocation():
    """The CLI's own `die()` and help text must not print an unrunnable command.

    `studio curate groups <name>` printed `character.py refs <name> --describe`
    as the suggested next step — the worst possible moment to hand someone a
    command that does not run.
    """
    bad = []
    for module_file in sorted(SRC.rglob("*.py")):
        for number, line in enumerate(module_file.read_text().splitlines(), 1):
            for module, second in _SCRIPT_CALL.findall(line):
                command = FORMER_SCRIPTS.get(module)
                if command and (not SUBCOMMANDS[command] or second in SUBCOMMANDS[command]):
                    bad.append(
                        f"{module_file.relative_to(SRC)}:{number}: "
                        f"`{module}.py {second}` -> `studio {command} {second}`"
                    )
    assert not bad, "the pipeline prints script-era invocations:\n  " + "\n  ".join(bad)
