"""A Click parameter must not shadow something its own body relies on.

**Five bugs of this shape shipped, and every one of them printed `--help`
happily.** Click passes each option to the function as a parameter named after
its dest, so a command whose module also has a function of that name ends up
with two meanings for one word inside one scope — and the parameter always wins.

    studio runs outputs --presign      `presign(...)` called the bool. TypeError.
    studio projects inputs --presign   latent, same shape
    studio scenes outputs --presign    latent, same shape
    studio movies outputs --presign    latent, same shape
    studio character refs              `keys = resolve_selection(...)` assigned
                                       over the `--keys` flag, so `if keys:`
                                       tested the list. The download branch was
                                       unreachable and had been for its whole life.

Renaming the parameter is not the fix available: `cli_surface_reference.json`
records the dest and is a contract. So the fix is always at the call site, and
this is the check that says which call sites need one.

**Two patterns, because the five bugs came in two shapes:**

* **Shadowed call** — a parameter has the same name as a module-level function,
  and the body calls that name. Whatever the body meant, it gets the parameter.
* **Assigned-over** — the body rebinds a parameter to something of a different
  kind, and a later branch tests the parameter meaning the original. This is the
  `--keys` bug and it is the quieter of the two: no exception, just a branch
  that silently stops being reachable.

An assignment to a parameter is not wrong in itself — `pick`, `tags` and `slots`
are all parsed in place from a comma string, and that is fine because nothing
afterwards wants the raw string. So the assigned-over check fires only when the
parameter is a **flag**, where the boolean is the only thing it could ever have
meant and rebinding it always destroys information.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import click
import pytest

from studio_pipeline import STUDIO_DIR, cli

SOURCE_ROOT = STUDIO_DIR / "pipeline" / "src" / "studio_pipeline"


def _commands():
    """Every leaf command in the tree, as (path, command)."""
    def walk(command, path):
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                yield from walk(sub, [*path, name])
        else:
            yield " ".join(path), command

    return sorted(walk(cli.main, []), key=lambda pair: pair[0])


def _callback(command):
    """The function a command actually runs, past any decorator.

    **`inspect.unwrap`, and it is load-bearing.** `errors.reports` wraps a
    command with `functools.wraps`, which copies `__name__` but leaves
    `__code__` belonging to the wrapper — so the naive version of this resolved
    every `@reports`-decorated command to `errors.py`, found no function of that
    name in it, and dropped the command from the analysis. Silently: 24 of the
    47 commands were skipped, including all six of `runs`, and the negative
    control that reintroduced the `runs outputs` bug passed.
    """
    return inspect.unwrap(getattr(command, "callback", None))


def _module_of(command) -> pathlib.Path | None:
    """The file a command's callback was defined in."""
    filename = getattr(getattr(_callback(command), "__code__", None), "co_filename", None)
    return pathlib.Path(filename) if filename else None


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _module_functions(tree: ast.Module) -> set[str]:
    """Names bound to a function at module level — what a parameter can shadow.

    Only top-level definitions: a name defined inside another function is not in
    scope where a command body runs, so it cannot be what the body meant.
    """
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _called_names(node: ast.AST) -> set[str]:
    return {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }


def _retyped_names(node: ast.AST) -> set[str]:
    """Names assigned something that is not a bool literal.

    `force = True` is excluded deliberately, and the exclusion is the difference
    between a rule people keep and one they turn off. `studio character edit`
    does exactly that — `--discard` implies `--force` — and the flag still means
    the one thing it ever meant, so every later test of it is still right.

    What is caught is a flag rebound to a value of another kind: a list, a
    string, anything with its own truthiness. After that a later `if flag:`
    reads like a question about the option and is a question about the new
    value, which is how `character refs` lost its download branch.
    """
    found = set()
    for child in ast.walk(node):
        targets, value = [], None
        if isinstance(child, ast.Assign):
            targets, value = child.targets, child.value
        elif isinstance(child, (ast.AugAssign, ast.AnnAssign)):
            targets, value = [child.target], child.value
        if isinstance(value, ast.Constant) and isinstance(value.value, bool):
            continue
        found |= {t.id for t in targets if isinstance(t, ast.Name)}
    return found


def _analysed():
    """(label, command, function node, module tree) for every command with source."""
    out = []
    for label, command in _commands():
        path = _module_of(command)
        if path is None or SOURCE_ROOT not in path.parents:
            continue
        tree = _tree(path)
        function = _function(tree, _callback(command).__name__)
        if function is not None:
            out.append((label, command, function, tree))
    return out


ANALYSED = _analysed()


def test_the_whole_command_tree_was_actually_analysed():
    """A guard on the guard.

    Every check below iterates `ANALYSED`, so a resolver that quietly returned
    nothing would make all of them pass while checking no command at all — the
    exact failure this file exists to catch elsewhere.
    """
    resolved = {label for label, *_ in ANALYSED}
    everything = {label for label, _ in _commands()}
    missing = everything - resolved

    assert not missing, (
        f"{len(missing)} command(s) resolved to no source and were analysed by "
        f"nothing: {sorted(missing)}"
    )
    # Named explicitly because these are the five the checks below exist for. A
    # resolver change that drops them would otherwise leave a green file.
    assert {"runs outputs", "projects inputs", "scenes outputs", "movies outputs",
            "character refs"} <= resolved


@pytest.mark.parametrize("label", [entry[0] for entry in ANALYSED])
def test_no_parameter_shadows_a_function_the_body_calls(label):
    """`--presign` on four commands, each calling a `presign` that was a bool."""
    _label, command, function, tree = next(e for e in ANALYSED if e[0] == label)
    parameters = {p.name for p in command.params}
    shadowed = parameters & _module_functions(tree) & _called_names(function)

    assert not shadowed, (
        f"`studio {label}`: parameter(s) {sorted(shadowed)} shadow a function of the "
        f"same name that this body calls. The parameter wins, so the call gets the "
        f"option's value.\n"
        f"Fix at the call site — reach the function through its module, or inline it. "
        f"Renaming the parameter is not available: the dest is recorded in "
        f"cli_surface_reference.json."
    )


@pytest.mark.parametrize("label", [entry[0] for entry in ANALYSED])
def test_no_flag_is_assigned_over(label):
    """The `--keys` bug: rebinding a flag makes a later `if flag:` mean something else.

    A flag reassigned another bool is fine and is not reported — see
    `_retyped_names`.
    """
    _label, command, function, _tree = next(e for e in ANALYSED if e[0] == label)
    flags = {p.name for p in command.params if getattr(p, "is_flag", False)}
    clobbered = flags & _retyped_names(function)

    assert not clobbered, (
        f"`studio {label}`: flag(s) {sorted(clobbered)} are assigned over in the body. "
        f"A flag is a bool, so a later test of it silently means the new value — "
        f"which is how `character refs` lost its download branch.\n"
        f"Give the new value its own name. (Assigning another bool is allowed.)"
    )
