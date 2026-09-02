"""Resolve a character's or a project's images to NODE IDS.

Lifted from the two identical copies in the image and video submitters. Three
pools are addressed here, and the distinction between them is the point:

  a character's reference index   generated identity imagery — body positions,
              face angles, wardrobe. Far more than a model accepts at once, so
              a SUBSET is chosen from the described index rather than the folder
              being sent whole. Reference-ness is a `REF#` row now, not a
              location, so this asks the record and not the tree.
  a character's corpus/seed/archive pools   material about the character, not
              identity. Named explicitly, never pulled in automatically.
  a project's input pool          uploads and frames to drive a specific
              generation from. Picked from by POSITION.

Everything returned is a node id — the identity a record keeps forever. Not a
key and not a URL: a signed URL expires, is ~2 KB of noise and carries
time-limited bucket access that must not outlive the request, and a key or a
path is invalidated by the first rename. Presigning happens at submit time and
is never stored.

WHAT THIS MODULE STOPPED DOING, AND WHY THAT IS THE WHOLE POINT
---------------------------------------------------------------
It used to walk `characters/<slug>/reference/` itself, read the bible's index,
resolve `--pick` against basenames, apply `default_set`, and then check the
result against the engine's cap. Every one of those steps also existed in the
SPA, written separately, and the two could disagree about which images a
generation actually saw — a disagreement nobody can audit after the fact,
because the run recorded the outcome and not the reasoning.

Resolution is now `GET /api/characters/<id>/selection` and both halves of studio
call it. What is left here is the translation: the API refuses an over-cap
selection with `api.Conflict`, and a person needs to be told how to narrow it.
That message is this module's remaining job and it is worth keeping — a refusal
that only says "too many" leaves you guessing which four to drop.

WHY THERE IS NO "SEND EVERYTHING" MODE
--------------------------------------
`--character` used to mean "send the whole reference folder", which worked only
while the folder was kept small enough to fit the smallest engine cap. It is not
kept small any more — it is a library. So a selection is either named
(`--pick` / `--pick-tag`) or comes from the character's `default_set`, and if the
result still exceeds the model's cap the caller REFUSES rather than silently
dropping images. Which images a generation saw is not something to leave to
whatever a listing happened to return.

That rule is now enforced in ONE place instead of two. It used to be checked
here *and* implied by whatever `resolve_selection` returned; passing `limit=cap`
to the route makes the API the only thing that decides, so the CLI cannot be
lenient where the SPA is strict.
"""

import contextlib
import io

from studio_pipeline.adapters import api
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import projects as PROJECTS


class RefError(Exception):
    """A character's or project's images could not be resolved."""


@contextlib.contextmanager
def _reason(what: str):
    """Turn a `die()` in the layer below into a RefError that says why.

    The domain layer reports failure by printing to stderr and exiting, so a
    bare `SystemExit` carries only the status code — `str(SystemExit(1))` is
    "1". The message is the entire value, so it is captured and re-raised. The
    old subprocess version got this for free from `capture_output`; doing it by
    hand is the cost of the call being in-process.

    `api.NotFound` joins it because resolution is a route now: a character that
    does not exist arrives as a 404 rather than as a listing that came back
    empty, and a caller catching `RefError` should not have to catch both.
    `api.Conflict` deliberately passes straight through — it is the over-cap
    refusal, and it has a message of its own worth writing.

    **Every other `ApiError` is wrapped too, and that is not tidying.** A filter
    that matches nothing is a 400 now rather than an empty list, and 400 raises
    the base class — which no caller of this module catches. Unwrapped, asking
    for a reference by a name with a typo in it would end a run in a traceback
    instead of one `error:` line naming the typo.
    """
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            yield
    except SystemExit as exc:
        detail = err.getvalue().strip() or f"exited {exc.code}"
        raise RefError(f"could not read {what}:\n{detail}") from exc
    except api.NotFound as exc:
        raise RefError(f"could not read {what}: {exc}") from exc
    except api.Conflict:
        raise
    except api.ApiError as exc:
        raise RefError(str(exc)) from exc
    finally:
        # Anything not part of a failure still belongs on the real stderr.
        rest = err.getvalue()
        if rest and not rest.strip().startswith("error:"):
            import sys
            sys.stderr.write(rest)


def character_record(character: str) -> dict:
    """A character name (or id) -> its record, with `die`/404 turned into RefError."""
    with _reason(f"character {character}"):
        return CHARACTER.resolve(character)


def character_ids(names) -> list[str]:
    """Slugs a person typed -> the ids a run record stores.

    A run's `characters` are ids, so the association survives a rename — which
    is exactly what `runs find --character` used to lose. Resolved here rather
    than in `submit.py` because "what does this name refer to" is this module's
    subject and nothing else's.
    """
    return [character_record(name)["id"] for name in names]


def character_selection(character: str, slots: list[int] | None = None,
                        pick: list[str] | None = None,
                        tags: list[str] | None = None,
                        cap: int | None = None,
                        cap_name: str = "this model") -> list[dict]:
    """The resolved selection as entries — `{slot, node, group, description, …}`.

    Slot N is position N in THIS list. It is not a trailing file number and has
    not been one since references became rows: an image may be called anything,
    and `order` on the row is what decides where it lands.

    The entries carry `name` because a person reviewing a payload needs to know
    which picture is `[Image3]`, and a node id does not say. Callers that only
    bind images want `character_ref_nodes`.

    **`pick` names files; `tags` names tags.** The route matched `pick` against
    a reference's *group* until now, so naming files selected nothing at all and
    reported it nowhere — `--pick` bound zero images and the generation went out
    without them. A filter that matches nothing is refused now, so an empty
    selection cannot reach a model.
    """
    record = character_record(character)
    try:
        with _reason(f"{character}'s reference set"):
            return CHARACTER.selection_nodes(record, pick=pick, tags=tags,
                                             slots=slots, limit=cap)
    except api.Conflict as exc:
        # The API refuses rather than truncating and says how many matched
        # against how many the model takes; what it cannot know is which
        # commands narrow the set, so that half is added here.
        raise RefError(
            f"{exc}\n"
            f"  a character's references are a library, not a set to send whole. "
            f"Narrow it:\n"
            f"    studio character refs {character} --describe        # what each image shows\n"
            f"    --pick-tag face            # everything tagged face\n"
            f"    --pick <file>,<file>       # exactly these\n"
            f"    studio character default-set {character} --set …    # make a choice the default"
        ) from exc


def character_ref_nodes(character: str, slots: list[int] | None = None,
                        pick: list[str] | None = None,
                        tags: list[str] | None = None,
                        cap: int | None = None,
                        cap_name: str = "this model") -> list[str]:
    """The reference images this generation should send, as node ids, in slot order."""
    return [entry["node"] for entry in
            character_selection(character, slots, pick, tags, cap, cap_name)]


def character_pool_nodes(character: str, pool: str, *,
                         tree: bool = False) -> list[dict]:
    """The file nodes in a character's corpus/, seed/ or archive/ pool.

    Node **records**, not bare ids, because every caller picks out of this pool
    by name: `--seed-pick` names a file, and the refusal that lists an oversized
    pool has to print something a person recognises. A uuid is neither.

    `tree=True` descends into the pool's subfolders and labels each entry with a
    `path` relative to the pool. A pool is a tree the moment anyone files it —
    `seed/original/`, `seed/restored/` — and the root listing then answers with
    only what was never filed, which is a wrong answer that looks like a small
    pool rather than like an error. Callers CHOOSING identity out of a pool want
    the tree; `curate`, which works a folder at a time so it does not read a
    subtree's worth of bytes, wants the default.

    `archive/` is retired material: resolve it only when the user asked for
    those images specifically.
    """
    record = character_record(character)
    with _reason(f"{character}'s {pool} pool"):
        if tree:
            return CHARACTER.pool_tree_nodes(record, pool)
        return CHARACTER.pool_nodes(record, pool)


def project_input_nodes(project: dict, numbers: list[int]) -> list[str]:
    """Resolve input-pool POSITIONS to node ids, in the order asked for.

    `project` is the project record, not a name: every caller has already
    resolved one (`--project` is required and never inferred), and re-resolving
    it here would be a second round trip to learn something the caller holds.

    Position, not a filename number. The pool was numbered into basenames
    (`<project>_in_<n>.png`) and a deletion either renumbered every file or left
    a hole that silently changed what `--input 3` meant. The API orders the
    pool; nothing here re-sorts it.
    """
    try:
        return PROJECTS.input_nodes(project, numbers)
    except KeyError as exc:
        # `KeyError`'s str() is the repr of its argument, quotes included.
        raise RefError(str(exc.args[0]) if exc.args else str(exc)) from exc
