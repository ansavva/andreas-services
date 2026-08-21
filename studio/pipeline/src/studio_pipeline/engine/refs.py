"""Resolve a character's or a project's images to S3 KEYS.

Lifted from the two identical copies in the image and video submitters. Three
pools are addressed here, and the distinction between them is the point:

  characters/<name>/reference/  generated character imagery — body positions,
              face angles, wardrobe. Far more than a model accepts at once, so
              a SUBSET is chosen from the bible's described index rather than
              the folder being sent whole.
  characters/<name>/corpus/…    material about the character, not identity.
              Addressed by explicit key, never pulled in automatically.
  projects/<p>/input/           the project's working pool — uploads and frames
              to drive a specific generation from. Picked from by number.

Everything returned is an S3 key. Keys, never URLs: a signed URL expires, is
~2 KB of noise, and carries time-limited bucket access that must not outlive
the request. Presigning happens at submit time and is never stored.

WHY THERE IS NO "SEND EVERYTHING" MODE
--------------------------------------
`--character` used to mean "send the whole reference folder", which worked only
while the folder was kept small enough to fit the smallest engine cap. It is not
kept small any more — it is a library. So a selection is either named
(`--pick` / `--pick-tag`) or comes from the bible's `default_set`, and if the
result still exceeds the model's cap the caller REFUSES rather than silently
dropping images. Which images a generation saw is not something to leave to
whatever the folder listing happened to return.
"""

import contextlib
import io
import os

from studio_pipeline.adapters import store
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import projects as PROJECTS


class RefError(Exception):
    """A character's or project's images could not be resolved."""


@contextlib.contextmanager
def _reason(what: str):
    """Turn a `die()` in the layer below into a RefError that says why.

    The store reports failure by printing to stderr and exiting, so a bare
    `SystemExit` carries only the status code — `str(SystemExit(1))` is "1".
    The message is the entire value, so it is captured and re-raised. The old
    subprocess version got this for free from `capture_output`; doing it by
    hand is the cost of the call being in-process.
    """
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            yield
    except SystemExit as exc:
        detail = err.getvalue().strip() or f"exited {exc.code}"
        raise RefError(f"could not read {what}:\n{detail}") from exc
    finally:
        # Anything not part of a failure still belongs on the real stderr.
        rest = err.getvalue()
        if rest and not rest.strip().startswith("error:"):
            import sys
            sys.stderr.write(rest)


def _numbered(keys: list[str]) -> dict[int, str]:
    """Map the trailing _<n> of each filename to its key."""
    by_n: dict[int, str] = {}
    for key in keys:
        stem = os.path.splitext(os.path.basename(key))[0]
        try:
            by_n[int(stem.rsplit("_", 1)[-1])] = key
        except ValueError:
            continue
    return by_n


def character_ref_keys(character: str, slots: list[int] | None = None,
                       pick: list[str] | None = None, tags: list[str] | None = None,
                       cap: int | None = None, cap_name: str = "this model") -> list[str]:
    """The reference images this generation should send, as S3 keys, in slot order.

    Slot N is position N in THIS list — not a trailing file number. With
    subfolders inside `reference/`, filename numbers are only unique within a
    group, so the resolved selection is what defines the order a model sees.
    """
    with _reason(f"{character}'s reference set"):
        keys = CHARACTER.resolve_selection(character, pick, tags, slots)

    if cap is not None and len(keys) > cap:
        raise RefError(
            f"{character}'s selection is {len(keys)} image(s) but {cap_name} takes {cap}.\n"
            f"  reference/ is a library, not a set to send whole. Narrow it:\n"
            f"    studio character refs {character} --describe        # what each image shows\n"
            f"    --pick-tag face            # everything tagged face\n"
            f"    --pick <file>,<file>       # exactly these\n"
            f"    studio character default-set {character} --set …    # make a choice the default"
        )
    return keys


def character_pool_keys(character: str, pool: str) -> list[str]:
    """Keys in a character's corpus/, seed/ or archive/ pool.

    `archive/` is retired material: resolve it only when the user asked for
    those images specifically.
    """
    with _reason(f"{character}'s {pool} pool"):
        folder = CHARACTER.pool_folder(character, pool)
        return [f"{folder}/{e['name']}" for e in store.files(folder)]


def project_input_keys(project: str, numbers: list[int]) -> list[str]:
    """Resolve input-pool numbers to S3 keys, in the order asked for."""
    with _reason(f"project {project}'s input pool"):
        keys = PROJECTS.input_keys(project)
    by_n = _numbered(keys)
    missing = [n for n in numbers if n not in by_n]
    if missing:
        raise RefError(f"not in project {project}'s input pool: {missing} "
                       f"(have: {sorted(by_n)})")
    return [by_n[n] for n in numbers]
