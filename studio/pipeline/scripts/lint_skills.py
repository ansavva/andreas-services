#!/usr/bin/env python3
"""Check the skills against the CLI they describe.

`tests/test_cli_surface.py` guards the CLI's shape against a recorded contract.
This guards the other side: the skills under `studio/.claude/skills/` are what an
agent actually reads, and they could describe a CLI that was renamed out from
under them with nothing going red.

Not hypothetical. The pipeline arrived from a repo where each module was a
directly-invoked script, so the docs said `character.py refs <name> --describe`.
Packaging it behind one Click command made every such line unrunnable, and they
survived the move — in the prose, in the tables, and in `die()` strings the CLI
printed at the moment someone was already stuck. An agent that followed them fell
back to raw `aws s3` and rebuilt by hand what `studio character refs --describe`
returns directly.

This is a LINTER, not a test, and lives here rather than in `tests/` on purpose:
checking markdown is not what that suite is for, and 60-odd parametrised cases
for it drowned the wiring tests that are. Run from pre-commit for fast local
feedback and from `studio-pr.yml` for enforcement.

    python pipeline/scripts/lint_skills.py [--verbose]

FOUR CHECKS, and the two skill families are not held to the same one:

  1. every `studio …` line names a real command and subcommand
  2. no `<module>.py <subcommand>` survives in command position
  3. a `studio-media-*` skill names no module; a `studio-code-*` skill may, and
     the modules it names must exist
  4. every relative link resolves

Check 3 is why the families exist. Two media skills used to carry tables of every
module in the package and five of those names had rotted into files that no
longer existed — prose about code only stays true beside the code, so it lives in
`docs/PIPELINE.md`. A code skill is *about* the code, so naming it is the point.

A NOTE ON THE PATTERNS, because the first version of this got it wrong:
`[a-z_]+\\.py` does not match `s3_upload.py`. Four dead `s3_*.py` names sat in a
skill table passing a check written to catch exactly them. The classes below
include digits, and `RETIRED_BARE` covers names that never carried a `.py` at
all — `s3_convert --for` outlived its module by months for that reason.
"""

from __future__ import annotations

import pathlib
import re
import sys

import click

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import studio_pipeline  # noqa: E402
from studio_pipeline import cli  # noqa: E402

SKILLS_DIR = studio_pipeline.STUDIO_DIR / ".claude" / "skills"
# A code skill may name anything real in the pipeline — modules under `src/`,
# but also `conftest.py` or a script. Searching only `src/` called those dead.
PIPELINE = studio_pipeline.STUDIO_DIR / "pipeline"

MEDIA_PREFIX = "studio-media-"
CODE_PREFIX = "studio-code-"

SUBCOMMANDS = {
    name: (set(command.commands) if isinstance(command, click.Group) else set())
    for name, command in cli.main.commands.items()
}

# Module basename -> the `studio` command it became.
FORMER_SCRIPTS = {
    "character": "character", "curate": "curate", "runs": "runs",
    "scenes": "scenes", "movies": "movies", "frames": "frames",
    "projects": "projects", "rewrite": "rewrite", "phrasebook": "phrasebook",
    "models": "models", "build_prompt": "prompt", "s3_convert": "convert",
}

# Retired names that never appeared with a `.py`, so the pattern cannot see them.
RETIRED_BARE = {"s3_convert": "convert", "build_prompt": "prompt",
                "upload_to_replicate": None, "img2datauri": None}

# `studio` counts as an invocation inside a backtick, or at a line start INSIDE A
# CODE FENCE. Both narrowings are paid for: "grey studio backdrop" in a reference
# description read as a call to `backdrop`, and a prose sentence that happened to
# wrap after "both halves of" put `studio read the same tree` at a line start.
_STUDIO_CALL = re.compile(r"(?:^|`|\$ )studio ([a-z][\w-]*)(?:[ \t]+([^\s`'\"\\]+))?", re.M)
_INLINE_CALL = re.compile(r"(?:`|\$ )studio ([a-z][\w-]*)(?:[ \t]+([^\s`'\"\\]+))?")
_SCRIPT_CALL = re.compile(r"\b([a-z0-9_]+)\.py[ \t]+(\S+)")
_MODULE_NAME = re.compile(r"\b[a-z0-9_]+\.py\b")
_LINK = re.compile(r"\]\((\.\.?/[^)#]*)\)")


def _invocations(text: str) -> list[tuple[str, str]]:
    """Every `studio …` call: anything backticked, plus fenced-block lines."""
    found = list(_INLINE_CALL.findall(text))
    inside = False
    for line in text.split("\n"):
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            found += _STUDIO_CALL.findall(line)
    return found


def check_commands_exist(text: str) -> list[str]:
    out = []
    for command, second in _invocations(text):
        if command.startswith("-"):
            continue
        if command not in SUBCOMMANDS:
            out.append(f"`studio {command}` is not a command")
        elif SUBCOMMANDS[command] and second and not second.startswith(("-", "#")):
            if second not in SUBCOMMANDS[command]:
                out.append(
                    f"`studio {command} {second}` — {command} has no {second!r} "
                    f"(has: {', '.join(sorted(SUBCOMMANDS[command]))})"
                )
    return out


def check_no_script_era(text: str) -> list[str]:
    out = []
    for module, second in _SCRIPT_CALL.findall(text):
        command = FORMER_SCRIPTS.get(module)
        if command and (not SUBCOMMANDS[command] or second in SUBCOMMANDS[command]):
            out.append(f"`{module}.py {second}` -> `studio {command} {second}`")
    return out


def check_module_names(text: str, family: str) -> list[str]:
    named = sorted(set(_MODULE_NAME.findall(text)))
    bare = sorted(b for b in RETIRED_BARE if re.search(rf"`{re.escape(b)}[ `]", text))
    if family == "code":
        # A code skill may name modules — they just have to be real.
        return [f"{m} does not exist under pipeline/"
                for m in named if not any(PIPELINE.rglob(m))] + [
               f"`{b}` is retired" + (f"; use `studio {RETIRED_BARE[b]}`" if RETIRED_BARE[b] else "")
               for b in bare]
    return [f"names implementation: {m}" for m in named + bare]


def check_links(skill: pathlib.Path, text: str) -> list[str]:
    return [f"link goes nowhere: {t}" for t in _LINK.findall(text)
            if not (skill.parent / t).resolve().exists()]


def main(verbose: bool = False) -> int:
    skills = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if not skills:
        print(f"error: no skills found under {SKILLS_DIR}", file=sys.stderr)
        return 1

    failures, checked = {}, 0
    for skill in skills:
        name = skill.parent.name
        if name.startswith(MEDIA_PREFIX):
            family = "media"
        elif name.startswith(CODE_PREFIX):
            family = "code"
        else:
            failures[name] = [
                f"unknown family — a skill must be `{MEDIA_PREFIX}*` (using the "
                f"pipeline) or `{CODE_PREFIX}*` (changing it)"
            ]
            continue

        text = skill.read_text()
        problems = (check_commands_exist(text)
                    + check_no_script_era(text)
                    + check_module_names(text, family)
                    + check_links(skill, text))
        checked += 1
        if problems:
            failures[name] = problems
        elif verbose:
            print(f"  ok  {name} ({family})")

    if failures:
        print(f"\n{len(failures)} skill(s) out of step with the CLI:\n", file=sys.stderr)
        for name, problems in sorted(failures.items()):
            print(f"  {name}", file=sys.stderr)
            for p in problems:
                print(f"      {p}", file=sys.stderr)
        print("\n  Skills describe `studio <command>`. Document the code once, in"
              "\n  docs/PIPELINE.md#the-modules, and link to it.\n", file=sys.stderr)
        return 1

    print(f"lint_skills: {checked} skills ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--verbose" in sys.argv or "-v" in sys.argv))
