"""Extract a machine-readable description of the CLI surface.

Used two ways: to snapshot what argparse exposed before the Click conversion,
and to describe what Click exposes after it. If the two agree, the conversion
did not quietly move a default, drop a flag, or change an arity — which is the
entire risk of porting 239 options by hand.

Deliberately semantic rather than textual. Comparing `--help` output would
drown in formatting differences between the two libraries and prove nothing
about behaviour.
"""

from __future__ import annotations

import argparse


def _norm_default(value):
    """Defaults must compare across libraries, so reduce them to plain data.

    Click represents "no default" with a sentinel object and argparse with
    None; they mean the same thing, so both become None.
    """
    if value is None or repr(value).endswith("UNSET"):
        return None
    if isinstance(value, (str, int, float, bool, list, tuple)):
        return list(value) if isinstance(value, tuple) else value
    return repr(value)


def _norm_type(t) -> str:
    """The value type, as a name both libraries agree on."""
    if t is None:
        return "str"
    name = getattr(t, "name", None) or getattr(t, "__name__", None) or str(t)
    return {"integer": "int", "text": "str", "boolean": "bool",
            "choice": "str", "float": "float"}.get(str(name).lower(), str(name))


def _norm_nargs(nargs):
    """argparse and Click spell arity differently; normalise to a count or a word."""
    if nargs is None:
        return 1
    if nargs in ("*", "+", "?"):
        return nargs
    if nargs == argparse.REMAINDER:
        return "*"
    return nargs


def from_argparse(parser: argparse.ArgumentParser) -> dict:
    """Describe an argparse parser, recursing into its subparsers."""
    out = {"options": {}, "arguments": {}, "commands": {}}

    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                out["commands"][name] = from_argparse(sub)
            continue
        if isinstance(action, argparse._HelpAction):
            continue

        is_flag = isinstance(action, (argparse._StoreTrueAction,
                                      argparse._StoreFalseAction))
        # `action="append"` is repeatability, and it is invisible in `nargs` —
        # flattening it would turn `--key a --key b` into just `b`.
        multiple = isinstance(action, argparse._AppendAction)
        entry = {
            "dest": action.dest,
            "multiple": multiple,
            "hidden": action.help == argparse.SUPPRESS,
            # A flag takes no value in either library; Click still reports
            # nargs=1 for one, so both are pinned to 0 and compared as flags.
            "nargs": 0 if is_flag else _norm_nargs(action.nargs),
            "default": _norm_default(action.default),
            "required": bool(action.required),
            "choices": sorted(map(str, action.choices)) if action.choices else None,
            "flag": is_flag,
            "type": "bool" if is_flag else _norm_type(action.type),
            "help": "" if action.help == argparse.SUPPRESS else (action.help or "").strip(),
        }
        if action.option_strings:
            entry["flags"] = sorted(action.option_strings)
            # Keyed by the flag the USER types, not the destination name. Click
            # has to rename a few dests to avoid shadowing a module (`json` ->
            # `json_`), and that rename is invisible from the command line.
            out["options"][_key(action.option_strings)] = entry
        else:
            out["arguments"][action.dest] = entry
    return _collapse_arity(out)


def from_click(command) -> dict:
    """Describe a Click command/group in the same shape."""
    import click

    out = {"options": {}, "arguments": {}, "commands": {}}

    for param in command.params:
        is_flag = bool(getattr(param, "is_flag", False))
        entry = {
            "dest": param.name,
            "multiple": bool(getattr(param, "multiple", False)),
            "hidden": bool(getattr(param, "hidden", False)),
            "nargs": 0 if is_flag else ("*" if param.nargs == -1 else param.nargs),
            "default": _norm_default(param.default),
            "required": bool(param.required),
            "choices": (sorted(map(str, param.type.choices))
                        if isinstance(param.type, click.Choice) else None),
            "flag": is_flag,
            "type": "bool" if is_flag else _norm_type(param.type),
            "help": (getattr(param, "help", "") or "").strip(),
        }
        if isinstance(param, click.Option):
            if param.name == "help":
                continue
            entry["flags"] = sorted(param.opts + param.secondary_opts)
            out["options"][_key(param.opts + param.secondary_opts)] = entry
        else:
            out["arguments"][param.name] = entry

    if isinstance(command, click.Group):
        for name, sub in command.commands.items():
            out["commands"][name] = from_click(sub)
    return _collapse_arity(out)


def _key(option_strings) -> str:
    """The longest flag, without dashes — what a user actually types."""
    longest = max(option_strings, key=len)
    return longest.lstrip("-").replace("-", "_")


def _collapse_arity(node: dict) -> dict:
    """argparse `+` and Click `nargs=-1, required=True` are the same contract.

    argparse spells "one or more" as `nargs="+"`. Click has no such arity: it
    spells it as unlimited (`nargs=-1`) plus `required=True`, which refuses an
    empty list at parse time exactly as `+` does. Both are recorded as `+` so a
    faithful port compares equal.
    """
    for entry in list(node["arguments"].values()) + list(node["options"].values()):
        if entry["nargs"] == "*" and entry["required"]:
            entry["nargs"] = "+"
        # argparse spells "zero or one" as `?`; Click spells the same thing as
        # a single non-required parameter.
        if entry["nargs"] == "?" and not entry["required"]:
            entry["nargs"] = 1
    return node


class _Captured(Exception):
    """Raised to stop a `main()` the moment its parser is fully built."""


def capture_argparse(main) -> argparse.ArgumentParser:
    """Build a module's parser without running its command.

    Every `main()` here constructs its parser and then calls `parse_args()`, so
    intercepting that call yields the finished parser and stops before any work
    or any AWS call happens. This avoids having to refactor nineteen modules to
    expose a `build_parser()` purely so they can be inspected.
    """
    holder = {}
    original = argparse.ArgumentParser.parse_args

    def spy(self, *args, **kwargs):
        holder["parser"] = self
        raise _Captured

    argparse.ArgumentParser.parse_args = spy
    try:
        main()
    except _Captured:
        pass
    finally:
        argparse.ArgumentParser.parse_args = original

    if "parser" not in holder:
        raise AssertionError(f"{main.__module__} never called parse_args()")
    return holder["parser"]
