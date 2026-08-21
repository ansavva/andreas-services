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

SIX CHECKS, and the two skill families are not held to the same one:

  1. every `studio …` line names a real command and subcommand
  2. every fenced `studio …` line passes its positionals in the CLI's ORDER
     and count
  3. no `aws …` or `boto3` anywhere — a skill cannot reach AWS
  4. no `<module>.py <subcommand>` survives in command position
  5. a `studio-media-*` skill names no module; a `studio-code-*` skill may, and
     the modules it names must exist
  6. every relative link resolves

Check 5 is why the families exist. Two media skills used to carry tables of every
module in the package and five of those names had rotted into files that no
longer existed — prose about code only stays true beside the code, so it lives in
`docs/PIPELINE.md`. A code skill is *about* the code, so naming it is the point.

Check 3 is check 1's other half. A line naming no `studio` command was caught;
a line naming `aws s3 cp` was not, and after #302 the CLI holds no AWS
credentials — so such a line instructs something that cannot work, from a page
read by an agent that will try it anyway.

Check 2 is check 1 taken one token further. `studio curate move` takes
`FILE NAME`; the docstring and `studio-media-character` both wrote `<name>`
first for the file's whole life, and it exits with `invalid character name`.
Check 1 passed it because the command existed. WHAT IT CATCHES AND WHAT IT DOES
NOT is spelled out on `check_invocation_shape`; read that before trusting it.

A NOTE ON THE PATTERNS, because the first version of this got it wrong:
`[a-z_]+\\.py` does not match `s3_upload.py`. Four dead `s3_*.py` names sat in a
skill table passing a check written to catch exactly them. The classes below
include digits, and `RETIRED_BARE` covers names that never carried a `.py` at
all — `s3_convert --for` outlived its module by months for that reason.
"""

from __future__ import annotations

import pathlib
import re
import shlex
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


# Anything that reaches AWS. `aws ` catches the CLI in any casing ("AWS CLI",
# "run `aws login`"); `boto3` catches the SDK. Both are impossible from a skill
# after #302 — the pipeline holds no AWS credentials — so a page that mentions
# either is telling a reader to do something that cannot work.
_AWS_DIRECT = re.compile(r"\baws\s|\bboto3\b", re.I)


def check_no_aws(text: str) -> list[str]:
    return [f"line {n}: reaches AWS directly — the CLI has no AWS credentials; "
            f"say which `studio` command does it: {line.strip()}"
            for n, line in enumerate(text.split("\n"), 1) if _AWS_DIRECT.search(line)]


# --------------------------------------------------------------------------
# positional order and arity
# --------------------------------------------------------------------------

# A placeholder standing for a local file or an object path, and one standing for
# a bare identifier. The check below is exactly the distance between these two
# sets: it is confident about a `<name>` sitting where a FILE belongs, and silent
# about everything it cannot classify.
_FILE_WORDS = {"file", "files", "path", "paths", "image", "images", "img",
               "still", "stills", "photo", "photos", "clip", "clips", "frame",
               "frames", "bible", "source", "sources"}
_NAME_WORDS = {"name", "project", "old", "new", "group", "pool", "slug",
               "character", "scene", "movie", "run"}
# Which arguments this can judge at all, by the name the CLI gives them.
_PATH_ARGS = {"file", "files"}
_JUDGED_NAME_ARGS = {"name", "project", "old", "new", "group", "pool"}

_PLACEHOLDER = re.compile(r"^<([a-z_]+)[^>]*>$")
_EXTENSION = re.compile(r"\.[a-z0-9]{2,4}$", re.I)


def _fenced_invocations(text: str) -> list[str]:
    """Every whole `studio …` command line inside a fenced block.

    Fenced only, and deliberately: prose backticks abbreviate (`studio curate`,
    `studio character refs --describe`) and an abbreviation is not a wrong
    argument order. A fenced line is offered as runnable, so it is held to that.
    """
    lines, inside, pending = [], False, ""
    for raw in text.split("\n"):
        if raw.startswith("```"):
            inside, pending = not inside, ""
            continue
        if not inside:
            continue
        line = raw.strip()
        if pending:
            line, pending = f"{pending} {line}", ""
        if line.endswith("\\"):
            pending = line[:-1].strip()
            continue
        # A trailing comment, a redirect or a pipe ends the command. `#1` is a
        # runref suffix, not a comment, so a comment needs the space before it.
        line = re.split(r"\s#|\s>|\s\|\||\s&&|\s\|", line)[0].strip()
        if line.startswith("$ "):
            line = line[2:].strip()
        if line.startswith("studio ") or line == "studio":
            lines.append(line)
    return lines


# A placeholder may contain a space (`<model key>`), which the shell would not
# accept and `shlex` therefore splits in two. Join it back before tokenising, or
# the tail reads as a stray positional.
_SPACED_PLACEHOLDER = re.compile(r"<[^<>]*>")
# Prose standing in for "and the rest", in either spelling. It is not an
# argument. Dropped only where a positional would go — as an option's VALUE
# (`--prompt "..."`) it is a real token, and removing it there hands the option
# the next flag to eat.
_ELLIPSIS = {"...", "…", "[...]", "[…]"}


def _tokens(line: str) -> list[str] | None:
    joined = _SPACED_PLACEHOLDER.sub(lambda m: m.group(0).replace(" ", "_"), line)
    try:
        return shlex.split(joined)[1:]
    except ValueError:
        return None


def _resolve(tokens: list[str]):
    """Walk the Click tree to the leaf command, returning it and what is left."""
    command, rest = cli.main, list(tokens)
    while isinstance(command, click.Group):
        if not rest or rest[0].startswith("-"):
            return None, []          # a group named without a subcommand
        found = command.commands.get(rest[0])
        if found is None:
            return None, []          # check 1 owns this failure
        command, rest = found, rest[1:]
    return command, rest


def _positionals(command, rest: list[str]) -> list[str] | None:
    """The tokens Click would treat as positional, or None if unparseable.

    An option this command does not declare makes the split unknowable — it may
    or may not swallow the next token — so the line is skipped rather than
    guessed at.
    """
    takes = {}
    for param in command.params:
        if isinstance(param, click.Option):
            for opt in param.opts + param.secondary_opts:
                takes[opt] = 0 if param.is_flag else max(param.nargs, 1)

    out, index = [], 0
    while index < len(rest):
        token = rest[index]
        if token.startswith("-") and len(token) > 1 and not token.startswith("-<"):
            flag, equals, _ = token.partition("=")
            if flag not in takes:
                return None
            index += 1 + (0 if equals else takes[flag])
            continue
        if token not in _ELLIPSIS:
            out.append(token)
        index += 1
    return out


def _usage(command) -> str:
    pieces = []
    for arg in [p for p in command.params if isinstance(p, click.Argument)]:
        if isinstance(arg.type, click.Choice):
            piece = "{" + "|".join(arg.type.choices) + "}"
        else:
            piece = arg.name.upper() + ("..." if arg.nargs == -1 else "")
        pieces.append(piece if arg.required else f"[{piece}]")
    return " ".join(pieces)


def _pair(args, tokens):
    """Match tokens to arguments the way Click does: the variadic takes the middle."""
    variadic = [i for i, a in enumerate(args) if a.nargs == -1]
    if not variadic:
        return list(zip(args, tokens))
    at = variadic[0]
    before, after = args[:at], args[at + 1:]
    if len(tokens) < len(before) + len(after):
        return None
    head = tokens[:len(before)]
    tail = tokens[len(tokens) - len(after):] if after else []
    middle = tokens[len(before):len(tokens) - len(after)] if after else tokens[len(before):]
    return (list(zip(before, head)) + [(args[at], t) for t in middle]
            + list(zip(after, tail)))


def _misplaced(arg, token: str) -> bool:
    """Whether this token is certainly in the wrong argument's position."""
    placeholder = _PLACEHOLDER.match(token)
    word = placeholder.group(1) if placeholder else None

    if isinstance(arg.type, click.Choice):
        return word is None and token not in arg.type.choices
    if arg.name in _PATH_ARGS:
        # A file position wants a path, a glob, or a placeholder naming a file.
        if word is not None:
            return word in _NAME_WORDS
        return not ("/" in token or "*" in token or _EXTENSION.search(token))
    if arg.name in _JUDGED_NAME_ARGS:
        if word is not None:
            return word in _FILE_WORDS
        return "/" in token or bool(_EXTENSION.search(token))
    return False


def check_invocation_shape(text: str) -> list[str]:
    """Fenced `studio …` lines pass their positionals in the CLI's order.

    WHAT IT CATCHES. Arity — too few or too many positionals for the command.
    Order, for the three argument kinds it can classify from a placeholder:
    a `--pool`-style CHOICE given a value outside its list, a FILE/FILES
    position holding a bare identifier, and a NAME/PROJECT/GROUP/POOL position
    holding something path-shaped. That is the `curate move <name> face/…`
    family, which is the whole class of bug this was added for.

    WHAT IT DOES NOT CATCH. Pages write placeholders, so this checks SHAPE, not
    values — `<project>` in a `<name>` position is indistinguishable from the
    real thing and passes. Two adjacent arguments of the same kind can be
    swapped freely: `character rename OLD NEW` reversed is invisible, and so is
    any pair of plain identifiers. Lines carrying an option the command does not
    declare are skipped whole, because the positional split cannot be known
    without knowing whether that option takes a value. Inline backticked
    commands are not checked at all — see `_fenced_invocations`.
    """
    out = []
    for line in _fenced_invocations(text):
        # `[--flag …]` is usage notation, not a command someone would paste.
        if "[-" in line:
            continue
        tokens = _tokens(line)
        if tokens is None:
            continue
        command, rest = _resolve(tokens)
        if command is None:
            continue
        given = _positionals(command, rest)
        if given is None:
            continue

        args = [p for p in command.params if isinstance(p, click.Argument)]
        least = sum(1 for a in args if a.required)
        most = None if any(a.nargs == -1 for a in args) else len(args)
        usage = _usage(command) or "no positional arguments"
        if len(given) < least or (most is not None and len(given) > most):
            out.append(f"`{line}` — takes {usage}, {len(given)} given")
            continue

        pairs = _pair(args, given)
        if pairs and any(_misplaced(arg, token) for arg, token in pairs):
            out.append(f"`{line}` — argument order is {usage}")
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


# Anything that looks like a skill name, anywhere. `<` is excluded so the
# placeholder form `studio-media-<key>` is not read as a skill called `<key>`.
_SKILL_REF = re.compile(r"\bstudio-(?:media|code)-[a-z0-9][a-z0-9-]*(?<!-)")
_SKIP_DIRS = {".venv", "node_modules", "dist", ".git", "__pycache__", ".pytest_cache"}
_SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".ico", ".lock", ".pyc"}


def check_references(skills: set[str]) -> dict[str, list[str]]:
    """Every `studio-media-*` / `studio-code-*` mentioned anywhere must exist.

    The other checks only read the skills themselves, which is how renaming the
    families left stale names in `.env.example` and `infra/README.md` — files
    nothing thought to look at. A skill name is a cross-repo reference, so it
    gets checked across the repo.
    """
    root = studio_pipeline.STUDIO_DIR
    # The root `studio` router skill names both families to route into them, so
    # it rots the same way if a family is ever renamed. Scan it too.
    roots = [root, root.parent / "CLAUDE.md", root.parent / ".github" / "workflows",
             root.parent / ".claude" / "skills" / "studio"]
    stale: dict[str, list[str]] = {}
    for base in roots:
        files = [base] if base.is_file() else [
            f for f in base.rglob("*")
            if f.is_file() and f.suffix not in _SKIP_SUFFIX
            and not _SKIP_DIRS & set(f.parts)
        ]
        for f in files:
            try:
                text = f.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for ref in sorted(set(_SKILL_REF.findall(text))):
                if ref not in skills:
                    stale.setdefault(str(f.relative_to(root.parent)), []).append(ref)
    return stale


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
                    + check_invocation_shape(text)
                    + check_no_aws(text)
                    + check_no_script_era(text)
                    + check_module_names(text, family)
                    + check_links(skill, text))
        checked += 1
        if problems:
            failures[name] = problems
        elif verbose:
            print(f"  ok  {name} ({family})")

    for where, refs in check_references({s.parent.name for s in skills}).items():
        failures[where] = [f"names a skill that does not exist: {r}" for r in refs]

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
