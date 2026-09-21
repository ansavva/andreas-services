"""The character bible — `domain/subjects.py`'s round trip, bound to `SUBJECT`.

Everything about how a bible is stored, checked, pulled, pushed and written
back under a `rev` is in `subjects.py`, once, for a character and a location
alike. This module keeps the names the rest of the pipeline and its tests
were written against, each one the generic function with the character
subject already supplied.
"""
from __future__ import annotations

from studio_pipeline.domain import subjects as S
from studio_pipeline.domain.characters.base import COMMANDS, PROFILE_KEYS, SUBJECT

PROMOTED = S.PROMOTED

parse_profile = S.parse_profile
document = S.document
split_document = S.split_document
unified = S.unified


def check_profile(data: dict, where: str, name: str | None = None) -> None:
    """Refuse a bible that has drifted off the character schema."""
    S.check_profile(SUBJECT, data, where, name)


def load_profile(name: str) -> dict:
    """The bible of one character, as one map. **The reader every engine uses.**"""
    return S.load_profile(SUBJECT, name)


def save_profile(record: dict, data: dict, rev: int | None = None) -> dict:
    """Write a document back. One compare-and-swap on `rev`."""
    return S.save_profile(SUBJECT, record, data, rev)


def remote_rev(name: str) -> int | None:
    """The record's current `rev`, or None if there is no such character."""
    return S.remote_rev(SUBJECT, name)


def fetch_profile(name: str) -> tuple[str, str]:
    """(the bible as YAML text, the `rev` it was read at)."""
    return S.fetch_profile(SUBJECT, name)


def local_paths(name: str, override: str | None = None) -> tuple[str, str, str]:
    """(working copy, base copy, rev file) for a character."""
    return S.local_paths(SUBJECT, name, override)


def do_pull(name: str, force: bool, local: str, base: str, revf: str) -> None:
    S.do_pull(SUBJECT, name, force, local, base, revf)


def do_push(name: str, force: bool, local: str, base: str, revf: str) -> None:
    S.do_push(SUBJECT, name, force, local, base, revf)


_COMMANDS = COMMANDS
cmd_list = _COMMANDS["list"]
cmd_show = _COMMANDS["show"]
cmd_create = _COMMANDS["create"]
cmd_edit = _COMMANDS["edit"]
cmd_set_profile = _COMMANDS["set-profile"]
cmd_delete = _COMMANDS["delete"]
cmd_rename = _COMMANDS["rename"]
cmd_textblock = _COMMANDS["textblock"]

__all__ = [
    "PROFILE_KEYS", "PROMOTED", "check_profile", "cmd_create", "cmd_delete", "cmd_edit",
    "cmd_list", "cmd_rename", "cmd_set_profile", "cmd_show", "cmd_textblock",
    "do_pull", "do_push", "document", "fetch_profile", "load_profile", "local_paths",
    "parse_profile", "remote_rev", "save_profile", "split_document", "unified",
]
