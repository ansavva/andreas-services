"""refs.py — resolve a character's or a project's images to S3 KEYS.

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

import os

from studio_pipeline._invoke import InvokeError, call_json
from studio_pipeline.characters import character as CHARACTER
from studio_pipeline.store import projects as PROJECTS


class RefError(Exception):
    """A character's or project's images could not be resolved."""


def _run(module, args: list[str], what: str, who: str) -> list:
    """Ask another part of the pipeline for a list of keys, as JSON."""
    try:
        return call_json(module.main, args)
    except InvokeError as exc:
        raise RefError(f"could not read {who}'s {what}:\n{exc}")


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
    args = ["refs", character, "--keys", "--json"]
    if pick:
        args += ["--pick", ",".join(pick)]
    if tags:
        args += ["--pick-tag", ",".join(tags)]
    if slots:
        args += ["--slots", ",".join(str(s) for s in slots)]
    keys = _run(CHARACTER, args, "reference set", character)

    if cap is not None and len(keys) > cap:
        raise RefError(
            f"{character}'s selection is {len(keys)} image(s) but {cap_name} takes {cap}.\n"
            f"  reference/ is a library, not a set to send whole. Narrow it:\n"
            f"    character.py refs {character} --describe        # what each image shows\n"
            f"    --pick-tag face            # everything tagged face\n"
            f"    --pick <file>,<file>       # exactly these\n"
            f"    character.py default-set {character} --set …    # make a choice the default"
        )
    return keys


def character_pool_keys(character: str, pool: str) -> list[str]:
    """Keys in a character's corpus/, seed/ or archive/ pool.

    `archive/` is retired material: resolve it only when the user asked for
    those images specifically.
    """
    return _run(CHARACTER, ["pool", character, pool, "--json"], f"{pool} pool", character)


def project_input_keys(project: str, numbers: list[int]) -> list[str]:
    """Resolve input-pool numbers to S3 keys, in the order asked for."""
    keys = _run(PROJECTS, ["inputs", project, "--json"], "input pool", f"project {project}")
    by_n = _numbered(keys)
    missing = [n for n in numbers if n not in by_n]
    if missing:
        raise RefError(f"not in project {project}'s input pool: {missing} "
                       f"(have: {sorted(by_n)})")
    return [by_n[n] for n in numbers]
