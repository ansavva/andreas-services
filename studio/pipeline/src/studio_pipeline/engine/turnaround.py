"""`studio character turnaround` — render a character's STANDARD reference set.

One command over the angle spec (`domain/templates/reference_angles.yaml`). Each
angle in that spec becomes one recorded run: the angle's prompt, filled from the
character's own bible, plus two kinds of image — a generic ANGLE IMAGE from
`config/angle/` saying how to stand, and the character's own SEED photos (or a
named reference selection) saying who it is.

Why it lives in `engine/` and not `domain/`: this is model invocation. It runs
the same nine-step submit lifecycle `runner.py` drives, and reuses it rather than
repeating it — `gather` → `preflight` → `render` → `execute`, once per angle. The
dependency arrow `cli → domain → adapters` stays intact, and importing
`domain.characters` from here is what `refs.py` already does.

    studio character turnaround <name> --project <p> --dry-run   # nine payloads, no spend
    studio character turnaround <name> --project <p> --group face
    studio character turnaround <name> --project <p> --angle body_back --model nano-banana-pro

NOTHING SUBMITS WITHOUT APPROVAL. Every payload is rendered as the two-document
PROMPT / INPUT review first, and the batch then needs one explicit confirmation
from a person. `--dry-run` stops after drafting, so every payload has an
address in the app and none of them is approved.

WHAT THE ANGLE IMAGE IS FOR, AND WHY CITATIONS ARE COMPUTED
-----------------------------------------------------
A prompt says "[ImageN] is a pose guide — take only the stance from it". If N is
not where the angle image actually landed, that instruction is aimed at the character's
own face, and nothing errors: the render is just quietly wrong.

The position is therefore never assumed. `gather()` assembles the list — it
de-dupes, filters by what the model accepts, and orders by category — so the
resolved list is the only authority on where the angle image is. This module reads the
position out of it and fills the spec's `{angle_slot}` / `{identity_slots}` with
real numbers. That the angle image currently comes out first (this module passes it as
the first explicit key) is an outcome, not something a prompt may rely on.

TWO HUMAN GATES, AND WHY THEY ARE SEPARATE
------------------------------------------
1. **Spending.** Nothing is submitted until a person has seen the full payload
   and said yes. There is no flag that answers this for them — an earlier
   version had `--yes`, which is exactly the door an agent walks through while
   believing it had approval from something else.
2. **Identity.** A generated image does NOT enter `characters/<name>/reference/`
   on its own. The turnaround leaves every result in its run and stops. Promoting one
   into a character's identity is a second, deliberate act:

       studio character add-refs <name> --to <group> --from-run <runref>

   These are different decisions. "Yes, spend a few dollars seeing what this
   looks like" is not "yes, this image is now part of who this character is",
   and a single confirmation covering both silently turns the first into the
   second. The run keeps its output either way, so nothing is lost by looking
   first.
"""

from __future__ import annotations

import json
import os
import string
import sys
import urllib.parse
from types import SimpleNamespace

import click
import yaml

from studio_pipeline.adapters import auth, store
from studio_pipeline.domain import TEMPLATES_DIR
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import paths as P
from studio_pipeline.domain import projects as PROJ
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import refs as REFS
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import schema as MS
from studio_pipeline.engine import submit as SUB

# `errors.die`, not a copy re-exported from the HTTP adapter — see
# `errors.die`'s docstring for the nine that used to exist.
from studio_pipeline.errors import die  # noqa: E402

SPEC_FILE = "reference_angles.yaml"
# `TEMPLATES_DIR`, not `dirname(CHARACTER.__file__)`. That expression resolved
# the spec only while `characters` was a single module one level above
# `templates/`; the moment it became a package (#305) it pointed a segment too
# deep and the turnaround lost its spec. The directory names itself now — the same
# correction `STUDIO_DIR` exists for.
SPEC_PATH = str(TEMPLATES_DIR / SPEC_FILE)

# One angle image plus a handful of identity images is what an angle needs. Seed pools
# run to twenty-odd photographs, and sending all of them would breach the
# smaller engine caps and buy nothing — more angles of the same face do not
# sharpen it.
IDENTITY_MAX = 4


class TurnaroundError(Exception):
    """Anything that should stop the turnaround before it bills."""


# --------------------------------------------------------------------------
# the spec
# --------------------------------------------------------------------------

def load_spec(path: str = SPEC_PATH) -> dict:
    """Read the angle spec, or fail saying which file is wrong."""
    try:
        with open(path) as fh:
            spec = yaml.safe_load(fh)
    except FileNotFoundError:
        raise TurnaroundError(f"the angle spec is missing from the package: {path}")
    except yaml.YAMLError as exc:
        raise TurnaroundError(f"{path} is not valid YAML:\n  {exc}")
    if not isinstance(spec, dict) or not spec.get("angles"):
        raise TurnaroundError(f"{path} must be a mapping with a non-empty `angles:` list.")

    ids = [s.get("id") for s in spec["angles"]]
    if len(set(ids)) != len(ids):
        raise TurnaroundError(f"{path} has duplicate angle id(s).")
    for angle in spec["angles"]:
        missing = [k for k in ("id", "group", "angle_image", "prompt", "description", "tags")
                   if not angle.get(k)]
        if missing:
            raise TurnaroundError(f"{path}: angle {angle.get('id')!r} is missing {missing}.")
        if angle["group"] not in P.ANGLE_GROUPS:
            raise TurnaroundError(
                f"{path}: angle {angle['id']!r} has group {angle['group']!r}; "
                f"expected one of {list(P.ANGLE_GROUPS)}."
            )
        # An image nobody cites is an image the model is free to blend, which is
        # the whole reason citations are computed rather than hard-coded.
        if angle.get("torso_image") and "{torso_slot}" not in angle["prompt"]:
            raise TurnaroundError(
                f"{path}: angle {angle['id']!r} binds a torso_image but its prompt "
                f"never cites {{torso_slot}}, so nothing tells the model what "
                f"that image is for."
            )
    unknown = [f for f in spec.get("default_set") or [] if f not in ids]
    if unknown:
        raise TurnaroundError(f"{path}: default_set names angle(s) that do not exist: {unknown}")
    return spec


def select_angles(spec: dict, group: str | None, only: tuple[str, ...]) -> list[dict]:
    angles = spec["angles"]
    if only:
        by_id = {s["id"]: s for s in angles}
        unknown = [s for s in only if s not in by_id]
        if unknown:
            raise TurnaroundError(
                f"no such angle(s): {', '.join(unknown)}\n"
                f"       the spec defines: {', '.join(by_id)}"
            )
        return [by_id[s] for s in only]
    if group and group != "all":
        angles = [s for s in angles if s["group"] == group]
        if not angles:
            raise TurnaroundError(f"the spec has no angle in group {group!r}.")
    return angles


# --------------------------------------------------------------------------
# the prompt
# --------------------------------------------------------------------------

def _first_top(profile: dict) -> str:
    """The garment a face angle image should wear: the most frequent top, plainly.

    The bible's first `tops[]` entry is the character's usual one, and its
    `detail` often names embroidery or a graphic — which a model renders
    differently every time and would make the group inconsistent. So the detail
    is not used.

    But the schema puts the COLOUR in that same field ("<colour, cut, any
    embroidery or graphic>"), so dropping it whole threw the colour away too,
    and an angle image came back in a colour nobody chose. `colour:` is the narrow way
    back in: one word the angle image can state, kept apart from the prose it would
    otherwise have to be parsed out of. Optional — a bible that names the colour
    inside `item` ("white ribbed tank") already reads correctly without it.
    """
    tops = ((profile.get("wardrobe") or {}).get("tops")) or []
    top = tops[0] if tops and isinstance(tops[0], dict) else {}
    item = (top.get("item") or "plain T-shirt").strip().rstrip(".").lower()
    colour = str(top.get("colour") or "").strip().rstrip(".").lower()
    return (f"Wearing a plain {colour + ' ' if colour else ''}{item}, unbranded, "
            f"with no logo, text or embroidery")


def _age_text(profile: dict) -> str:
    """The age to render at — stated, because the references will not agree.

    Seed photographs accumulate over years: the same person at 35 and at 55 in
    the same identity set, with the model free to average them. Nothing in the
    prompt named an age, so nothing decided it. The bible has always carried
    `identity.apparent_age`; this reads it out, and the intro beside it says the
    stated age beats what any reference happens to show.
    """
    return " ".join(str((profile.get("identity") or {}).get("apparent_age") or "").split())


def _build_text(profile: dict, group: str = "body") -> str:
    """The person's PROPORTIONS, for a body angle image — from the bible, never here.

    A body angle image exists to record a build, and the first one rendered lost it:
    the figure came back lean and narrow-shouldered, with none of the bible's
    shoulder-to-waist taper or arm mass. The cause is the angle image. It is an
    untextured mannequin with its own proportions, and `{guide}`'s "take nothing
    else from it — not its build, proportions" was the only thing arguing
    otherwise, buried against a whole reference image.

    So the same lesson as the crop and the profile: state it in the foreground,
    with something checkable in it. The bible already carries exactly that under
    `body.silhouette` — a ratio, in head-widths — and `body.arms`. This reads
    them out; the wording stays generic because the specifics belong to the
    character (hard rule 1).

    WHICH FIELDS, AND WHY IT DEPENDS ON THE GROUP
    It began as `silhouette` + `arms`, which left four of the bible's six body
    fields unread — including `body_hair`, written expressly to defeat the
    smooth fitness-model default a model renders when nobody says otherwise.
    Unused, on the one angle image that strips the wardrobe back to shorts.

    A face angle image crops at mid-chest, so legs and body hair are not in frame and
    would be noise; it takes what shows above the crop. A body angle image is the
    whole figure and takes everything. Same split as `must_intro_face` /
    `must_intro_body`, for the same reason.

    THE LISTS ARE NAMED, NOT EXHAUSTIVE, AND THAT USED TO ROT SILENTLY.
    `body:` is a free-form map — the API validates the section names and stores
    what is under them raw — so a bible may carry fields this tuple has never
    heard of. It has: `back`, `hands` and `midsection` were added to one
    character's bible and read by nothing, and in the same edit
    `lower_body_and_hands` was split into `lower_body` + `hands`, which dropped
    the legs clause out of every body angle image without a word. A missing field is
    the one failure mode that leaves no trace in the payload, so:

    - the tuples below name the fields whose ORDER matters, and
    - `_extra_body_fields` sweeps up anything else the bible carries, so a new
      field reaches the prompt the moment it is written rather than the day
      somebody remembers to edit this file.

    Legacy spellings are accepted alongside the current ones, because a bible
    written before a rename is still a valid bible.

    HEIGHT comes first, and from `identity` rather than `body`. It is the one
    proportion the bible states as a NUMBER, and it was the only one never
    sent: the build clause read the `body:` block alone, so a corrected
    height_read sat unused while the prompt argued the point in adjectives.
    A figure has no scale of its own against a plain backdrop, so the number is
    the only thing that can settle it.
    """
    body = profile.get("body") or {}
    height = str((profile.get("identity") or {}).get("height_read") or "").strip()
    fields = ("silhouette", "chest_and_shoulders", "back", "neck", "arms", "hands")
    if group != "face":
        fields += ("midsection", "lower_body", "lower_body_and_hands", "body_hair")
    fields += _extra_body_fields(body, fields)
    parts = [height] + [str(body.get(k) or "").strip() for k in fields]
    return " ".join(" ".join(p.split()) for p in parts if p)


#: Read by the turnaround only on a body angle image, never on a face angle image that crops at
#: mid-chest. Anything below the crop belongs here.
_BELOW_THE_CROP = frozenset({"midsection", "lower_body", "lower_body_and_hands",
                             "body_hair", "feet"})

#: Not a description of the character — a rendering direction about him, already
#: carried into the prompt by its own clause. Sweeping it in would say it twice.
_NOT_BUILD = frozenset({"posture"})


def _extra_body_fields(body: dict, already: tuple[str, ...]) -> tuple[str, ...]:
    """Body fields the tuples above do not name, in the bible's own order.

    So that writing a new field into a bible is enough to get it rendered. The
    named tuples still decide ORDER for the fields that have one; this only
    appends what they missed.
    """
    seen = set(already) | _NOT_BUILD
    below = _BELOW_THE_CROP & set(already)
    return tuple(k for k in body
                 if k not in seen
                 and (below or k not in _BELOW_THE_CROP))


def _style_text(profile: dict, defaults: dict) -> str:
    """What MEDIUM to render in — the character's, never this code's.

    The spec used to assert "photographic, no stylisation" for every angle, which
    is right only for a character whose material is photographs. For one who
    exists as pen-and-ink panels it would have converted him into a medium he has
    never appeared in, and the reference images passed alongside would have been
    fighting the prompt. So the images lead and the bible names what they are.
    """
    style = ((profile.get("rendering") or {}).get("default_style") or "").strip()
    intro = (defaults.get("style_intro") or "").strip()
    return f"{intro} {style.rstrip('.') or defaults.get('style_fallback', '')}.".strip()


def _must_text(profile: dict, intro: str) -> str:
    musts = ((profile.get("consistency") or {}).get("must")) or []
    if not musts:
        return ""
    return intro.strip() + " " + "; ".join(m.strip().rstrip(".") for m in musts) + "."


def _slots_phrase(positions: list[int]) -> str:
    """[Image2] / [Image2] and [Image3] / [Image2], [Image3] and [Image4]."""
    names = [f"[Image{n}]" for n in positions]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def build_prompt(angle: dict, spec: dict, profile: dict,
                 angle_position: int, identity_positions: list[int],
                 torso_position: int | None = None) -> str:
    """Fill one angle's prompt template. Raises if the spec names a value we lack."""
    defaults = spec.get("defaults") or {}
    intro = defaults.get(f"must_intro_{angle['group']}") or defaults.get("must_intro_face") or ""
    values = {
        **{k: v for k, v in defaults.items() if isinstance(v, str)},
        "top": _first_top(profile),
        "style": _style_text(profile, defaults),
        "must": _must_text(profile, intro),
        "build": _build_text(profile, angle["group"]),
        "age": _age_text(profile),
        "identity_block": (profile.get("text_identity_block") or "").strip(),
        "angle_slot": f"[Image{angle_position}]",
        "identity_slots": _slots_phrase(identity_positions),
    }
    # Absent rather than empty when the angle binds no torso angle image, so a prompt
    # that cites one it never declared fails loudly instead of rendering "".
    if torso_position is not None:
        values["torso_slot"] = f"[Image{torso_position}]"
    try:
        text = string.Formatter().vformat(angle["prompt"], (), values)
    except KeyError as exc:
        raise TurnaroundError(
            f"angle {angle['id']!r} uses {{{exc.args[0]}}}, which nothing provides.\n"
            f"       available: {', '.join(sorted(values))}"
        )
    return " ".join(text.split())


# --------------------------------------------------------------------------
# the images
# --------------------------------------------------------------------------

def angle_key(angle: dict) -> str:
    """The angle's angle image, as a full key, checked for shape.

    The spec stores a bucket-relative key (`config/angle/body/front.png`) so the
    prose in source control names the object in S3 that `dev-setup.sh` copies out.
    """
    return _angle_key(angle, "angle_image")


def torso_angle_key(angle: dict) -> str | None:
    """The angle's SECOND guide, or None — see `angle_keys` for why it exists."""
    return _angle_key(angle, "torso_image") if angle.get("torso_image") else None


def angle_keys(angle: dict) -> list[str]:
    """Every guide angle image this angle binds, in citation order.

    Most angles bind one. The back three-quarters bind two, because the face
    angle images are cut from a head sheet and END AT A NECK STUMP: they carry no
    shoulder line at all, so `{guide}`'s "match the direction the body and head
    face" has no body in it to match, and a symmetric stump reads as square.
    Rendered that way, both back three-quarters came back with a correctly
    turned head on a torso flat to the camera — the prompt said to angle the
    shoulders and the reference image said not to, and the image won. The body
    angle image for the same orientation is a whole figure at 135 degrees, so binding
    it as a second guide gives the torso a direction to copy.
    """
    return [k for k in (angle_key(angle), torso_angle_key(angle)) if k]


def _angle_key(angle: dict, field: str) -> str:
    rel = angle[field]
    if not rel.startswith(P.config_root()):
        raise TurnaroundError(
            f"angle {angle['id']!r}: {field} {rel!r} must be a key under "
            f"{P.CONFIG}/ — angle images are config, not character material."
        )
    # No prefixing on the way out. `store` addresses by tree-relative path, so
    # the angle's value already IS the key — this went through `s3.key`, which
    # had become the identity function once the global prefix went.
    return rel


def check_angles(angles: list[dict]) -> None:
    """Every angle image must already be there. Fail once, listing all of them.

    An ordinary `exists` on an ordinary name path, because an angle image is an
    ordinary node under the library's `config/` folder. It was shared material
    with no node until the entity model, which is why this used to be the one
    check that could not ask the catalog.
    """
    missing = []
    for angle in angles:
        for key in angle_keys(angle):
            if not store.exists(key):
                missing.append(key)
    if missing:
        raise TurnaroundError(
            "angle image(s) missing from the bucket:\n"
            + "".join(f"       {k}\n" for k in missing)
            + "       These live in the repo under studio/config/ and are copied out by\n"
            "       studio/scripts/dev-setup.sh — run it, then try again."
        )


def app_origin() -> str | None:
    """Where the SPA that shows a run lives, derived from the API's own host.

    The two halves of studio are one label apart — `studio-api.andreas.services`
    serves the API and `studio.andreas.services` serves the app — so the origin
    is the API's with `-api` dropped from its first label. Derived rather than
    configured because a profile carries the five values that select a STACK,
    and adding a sixth for a cosmetic link would make every existing profile
    incomplete.

    `None` when the host is not that shape — a dev API on localhost has no app
    at a guessable port — and the caller prints the ids alone, which are what
    `runs show` and `runs approve` take anyway.
    """
    try:
        parsed = urllib.parse.urlparse(auth.api_url())
    except Exception:                                        # noqa: BLE001
        return None
    host, _, rest = (parsed.hostname or "").partition(".")
    if not host.endswith("-api") or not rest:
        return None
    return f"{parsed.scheme}://{host[:-len('-api')]}.{rest}"


def _draft_only(prepared: list, project: dict, name: str) -> int:
    """Record every angle as a DRAFT and stop. **Nothing is approved, nothing bills.**

    This is what `studio run --dry-run` does, and a turnaround not doing it was
    the difference between a payload you can open and a payload that scrolls
    past. The old branch printed a count and returned, and this module argued
    for that in a comment: a run id "has not happened yet and must not", because
    hard rule #2 says the payload is approved before anything exists.

    **That reasoning predates a run having an authored half.** A draft is not a
    submission and not an approval — it is the payload, given an address, in a
    state `NEVER_BILLED` names explicitly. The approval is a separate row bound
    to a digest of the plan and its `SEND#` rows, and the API refuses to move a
    run out of the unsubmitted states without one that still matches. So drafting
    here makes the gate STRONGER than the text block it replaces: the words and
    images somebody agreed to end up where they can be read back, in the app,
    instead of in a terminal scrollback nobody can link to.

    One bad angle does not cancel the rest, for the reason the submit loop below
    gives: a failure is almost always a property of that angle alone.
    """
    origin = app_origin()
    drafted: list[tuple[str, dict]] = []
    failed: list[tuple[str, str]] = []
    for angle, entry, args, payload, bindings in prepared:
        try:
            drafted.append((angle["id"], SUB.draft(entry, payload, bindings, args)))
        except SUB.SubmitError as exc:
            failed.append((angle["id"], str(exc)))

    print(f"\n{len(drafted)} draft(s) — nothing approved, nothing submitted, "
          f"nothing billed:", file=sys.stderr)
    for angle_id, record in drafted:
        where = (f"{origin}/p/{project['id']}/r/{record['id']}" if origin
                 else record["id"])
        print(f"  {angle_id:<32} {where}", file=sys.stderr)
    for angle_id, why in failed:
        print(f"  {angle_id:<32} NOT DRAFTED — {why}", file=sys.stderr)

    if drafted:
        print(f"\nreview and approve each in the app, then send it:\n"
              f"  studio runs submit <run-id>\n"
              f"  studio runs discard <run-id>      # one you do not want\n"
              f"  studio runs list {project['slug']} --status draft",
              file=sys.stderr)
    return 1 if failed else 0


def _too_many(name: str, pool: str, entries: list[dict], limit: int, how: str) -> TurnaroundError:
    """Refuse an oversized pool rather than taking the first few.

    `reference/` already refuses an over-cap selection rather than truncating,
    "because which images a generation saw should not be decided by whatever the
    folder listing happened to return". A seed pool deserves the same: sorted
    order is not quality order. One character's seed pool opens with a poster, a
    launch graphic, a collage and a wide shot of him across a room — the four
    worst images in it for carrying a face, and exactly the four a silent
    `[:limit]` would have sent.
    """
    listing = "".join(f"       {_label(e)}\n" for e in entries[:20])
    more = f"       … and {len(entries) - 20} more\n" if len(entries) > 20 else ""
    return TurnaroundError(
        f"{name}'s {pool}/ holds {len(entries)} images and an angle sends {limit}.\n"
        f"       Name the ones that carry identity best — a clear, unobstructed "
        f"view of the face and build:\n{listing}{more}"
        f"       {how}"
    )


def _seed_nodes(name: str) -> list[dict]:
    """The image NODES in a character's seed pool.

    Node records rather than ids, because everything this module does with a
    seed image afterwards is either bind it (which wants the id) or name it to a
    person (which wants the filename). A pool listing that returned only ids
    would make every refusal below print uuids at somebody trying to choose
    between four photographs.

    **The WHOLE pool, subfolders included.** This read the root listing alone,
    which is the same thing as asserting that nobody files their seed material —
    and the moment anyone does, the photographs they filed stop existing as far
    as a shoot is concerned. Not refused with a message: absent. One character
    had thirteen restored photographs one folder down and a shoot went on
    resolving identity from the four loose ones in the root, while `--seed-pick`
    answered "not in seed/" to every name in the folder a person was reading off
    `character pool <name> seed --group restored`.

    Each entry carries a `path` relative to the pool, which is what `_label`
    prints and what `--seed-pick` matches, so two folders may hold the same
    basename without either becoming unnameable.
    """
    return [n for n in REFS.character_pool_nodes(name, "seed", tree=True)
            if os.path.splitext(n.get("name") or "")[1].lower() in R.IMG_EXTS]


def _seed_picked(name: str, seed_pick: str) -> list[dict]:
    """Resolve `--seed-pick` names, in the order given.

    Four spellings of the same image, because the pool is a tree and a person
    types whichever one they are looking at: the pool-relative path
    (`restored/<file>.jpg`), that path without its extension, the bare basename,
    and the bare stem. The paths are matched first — they are the unambiguous
    form, and the only one that can name both of two same-named files.

    **An ambiguous basename is refused, not resolved.** Two subfolders may hold
    a `front.jpg`, and picking whichever the walk reached first would decide
    which photograph carries a person's identity by sort order. That is the same
    mistake `_too_many` exists to prevent one level up, so it fails the same way:
    say which paths matched, and let the person name one.
    """
    seed = _seed_nodes(name)
    want = [x.strip() for x in seed_pick.split(",") if x.strip()]

    def _path(entry: dict) -> str:
        return entry.get("path") or entry.get("name") or ""

    by_path = {_path(n): n for n in seed}
    by_path_stem = {os.path.splitext(p)[0]: n for p, n in by_path.items()}
    by_base: dict[str, list[dict]] = {}
    for entry in seed:
        by_base.setdefault(entry.get("name") or "", []).append(entry)
        stem = os.path.splitext(entry.get("name") or "")[0]
        if stem:
            by_base.setdefault(stem, []).append(entry)

    chosen, missing, ambiguous = [], [], []
    for one in want:
        if one in by_path:
            chosen.append(by_path[one])
        elif one in by_path_stem:
            chosen.append(by_path_stem[one])
        elif len(by_base.get(one, [])) == 1:
            chosen.append(by_base[one][0])
        elif by_base.get(one):
            ambiguous.append(one)
        else:
            missing.append(one)

    if ambiguous:
        lines = "".join(
            f"       {one} -> {', '.join(_path(e) for e in by_base[one])}\n"
            for one in ambiguous)
        raise TurnaroundError(
            f"more than one file in {name}'s seed/ is called this:\n{lines}"
            f"       name the one you mean by its path, e.g. "
            f"{_path(by_base[ambiguous[0]][0])}")
    if missing:
        raise TurnaroundError(
            f"not in {name}'s seed/: {', '.join(missing)}\n"
            f"       see: studio character pool {name} seed\n"
            f"       a pool has subfolders; a file in one is named "
            f"<folder>/<file>")
    return chosen


def _ids(entries: list[dict]) -> list[str]:
    """Node ids out of selection entries or node records, whichever arrived.

    `character_selection` keys the node on `node` and `character_pool_nodes`
    keys it on `id`, because the first is a `REF#` row wearing its file and the
    second is a plain node. One place knows both spellings rather than four.
    """
    return [e.get("node") or e["id"] for e in entries]


def _label(entry: dict) -> str:
    """What to call an image when asking a person to choose between them.

    Its filename, which is the only thing they can recognise. A node id is the
    right thing to BIND and the wrong thing to print in a refusal — the
    distinction the entity model makes everywhere, applied to one message.

    Its pool-relative PATH when it has one, because that is what a person types
    back: a listing of a tree that printed bare basenames would offer names
    `--seed-pick` then had to guess between, and would hide that two of them are
    different photographs in different folders. Reference entries carry no
    `path` and are unaffected.
    """
    return (entry.get("path") or entry.get("name")
            or entry.get("node") or entry.get("id") or "?")


def identity_nodes(name: str, source: str, pick: str | None, tags: str | None,
                   limit: int = IDENTITY_MAX,
                   seed_pick: str | None = None) -> tuple[list[str], str]:
    """The NODE IDS of the images that say WHO this is, and where they came from.

    Node ids, where this returned S3 keys. A binding names a node now, so a
    turnaround that resolved a path would be stranded the first time one of these
    images was renamed — which is the whole of what the entity model fixes and
    is exactly the case that matters here, because a seed photograph is renamed
    by hand more often than anything else in a character.

    Seed material is preferred: it is the founding source, and driving a turnaround
    off already-generated references feeds model output back in as identity,
    which compounds drift with every pass.

    Nothing here silently truncates. If a pool holds more than one angle sends,
    the caller is asked which — see `_too_many`.
    """
    if pick or tags:
        chosen = REFS.character_selection(
            name, None, [x.strip() for x in pick.split(",")] if pick else None,
            [t.strip() for t in tags.split(",")] if tags else None)
        # The two pools MIX. Naming references used to silence --seed-pick
        # entirely, which is backwards for the case that wants both: curated
        # reference frames give clean, consistent angles, and a couple of seed
        # photographs anchor them to the real source so a turnaround is not driven
        # purely by earlier model output. Refusing the combination made the
        # safer choice the one you could not express.
        if seed_pick:
            chosen = chosen + _seed_picked(name, seed_pick)
            source = "reference+seed"
        else:
            source = "reference"
        if len(chosen) > limit:
            raise _too_many(name, source, chosen, limit,
                            "Narrow --pick / --pick-tag / --seed-pick, or raise "
                            "--identity-max.")
        return _ids(chosen), source

    if source in ("auto", "seed"):
        seed = _seed_nodes(name)
        if seed_pick:
            picked = _seed_picked(name, seed_pick)
            if len(picked) > limit:
                raise _too_many(name, "seed", picked, limit,
                                "Pick fewer, or raise --identity-max.")
            return _ids(picked), "seed"
        if seed:
            if len(seed) > limit:
                raise _too_many(
                    name, "seed", seed, limit,
                    f"--seed-pick <file>,<file>       # name them\n"
                    f"       --identity refs --pick …        # use the reference index instead\n"
                    f"       studio contact-sheet --character {name} --folder seed --out "
                    f"/tmp/{name}-seed.png   # look first")
            return _ids(seed), "seed"
        if source == "seed":
            raise TurnaroundError(
                f"{name} has no images in seed/, and --identity seed was asked for.\n"
                f"       Add the founding material: studio character add-to {name} seed <files…>"
            )

    chosen = REFS.character_selection(name, None, None, None)
    if not chosen:
        raise TurnaroundError(
            f"{name} has nothing to carry identity — seed/ is empty and reference/ has "
            f"no selection.\n"
            f"       Add source material first: studio character add-to {name} seed <files…>"
        )
    if len(chosen) > limit:
        raise _too_many(name, "reference", chosen, limit,
                        f"Narrow it with --pick / --pick-tag, or set a default_set:\n"
                        f"       studio character refs {name} --describe")
    return _ids(chosen), "reference"


# --------------------------------------------------------------------------
# seeing what is actually being sent
# --------------------------------------------------------------------------

def review_sheet(angle_id: str, nodes: list[str], out_dir: str, dest: str) -> str:
    """A labelled contact sheet of the images one payload binds, in angle order.

    The payload review names its images (`<presigned: characters/…>`) but a name
    is not a look. Approving a generation you cannot see is approving a
    description of it — and the mistakes that matter here are visual: a pose
    angle image that is the wrong way round, an identity image that is mostly a poster,
    a panel whose speech balloon the model will happily reproduce.

    Tiles are captioned `[ImageN]` in the order the model receives them, so the
    sheet and the prompt's citations read against each other. **Captions are
    given, so the worker leaves the order alone** — natural-sorting them by
    filename would renumber the citations the prompt makes.

    **A render job, because Pillow is not in this wheel any more.** Everything
    bound here is already a node — hard rule #3 means anything sent to a model is
    already in S3 — so nothing is uploaded to build this, and `cache` (which
    memoised a download per node) is gone with the downloads.

    It costs a round trip on the approval path, which is a real cost on the one
    path that must not be tedious. It is bounded: a turnaround binds a handful of
    references, and the job is Pillow over images the worker streams.
    """
    from studio_pipeline.domain import renders as RENDER

    result = RENDER.submit("sheet", {
        "parts": [RENDER.part(node, caption=f"[Image{i}] "
                              f"{store.node(node).get('name') or node}")
                  for i, node in enumerate(nodes, start=1)],
        "cols": min(len(nodes), 5), "cell": 320,
        "dest": dest,
        "name": f"{angle_id}.png",
    }, what="the review sheet")
    return RENDER.fetch(result["sheet"], out_dir, f"{angle_id}.png")


# --------------------------------------------------------------------------
# one angle
# --------------------------------------------------------------------------

def angle_args(angle: dict, spec: dict, entry: dict, name: str, opts) -> SimpleNamespace:
    """The namespace `runner`/`submit` expect, for one angle.

    Every image is passed as an explicit `--key`, in the order the model should
    see them: the angle image first, identity after. `--character` is deliberately NOT
    set — this module has already chosen the keys, and letting `gather()` resolve
    a second set from the bible's `default_set` would silently add images nobody
    picked. `record_characters` keeps the run associated with the character all
    the same.
    """
    defaults = spec.get("defaults") or {}
    model = opts.model or angle.get("model") or defaults.get("model")
    if model != entry["key"]:
        raise TurnaroundError(f"internal: angle resolved model {model!r} but entry is {entry['key']!r}")

    extra: dict = {}
    extra.update(defaults.get("extra") or {})
    extra.update((spec.get("per_model") or {}).get(model) or {})
    extra.update(angle.get("extra") or {})
    if opts.extra:
        try:
            override = json.loads(opts.extra)
        except json.JSONDecodeError as exc:
            raise TurnaroundError(f"--extra is not valid JSON: {exc}")
        if not isinstance(override, dict):
            raise TurnaroundError("--extra must be a JSON object.")
        extra.update(override)

    d = SUB.defaults(entry["kind"])
    return SimpleNamespace(
        model=model,
        project=opts.project,
        slug=f"ref-{angle['id'].replace('_', '-')}",
        prompt=None,                      # filled once the citation angles are known
        prompt_file=None, prompt_json=None, input_file=None,
        extra=json.dumps(extra) if extra else None,
        aspect_ratio=opts.aspect_ratio or angle.get("aspect_ratio") or defaults.get("aspect_ratio"),
        key=[], character=(), record_characters=(name,),
        # The angle this run came from, carried into request.json. `add-refs
        # --from-run` reads it back to write the description and tags the spec
        # already holds for that angle — without it those fields are dead data
        # and every promotion is a hand-retype of prose that is right there.
        record_extra={"reference_angle": angle["id"]},
        pick=None, pick_tag=None, slots=None,
        image_run=None, ref_run=(), input_=(), input=(),
        start_run=None, start_key=None, end_run=None, end_key=None,
        no_refs=False, dry_run=opts.dry_run, json_=False, json=False,
        poll=True, dest=opts.dest,
        interval=d["interval"], timeout=d["timeout"],
    )


def prepare(angle: dict, spec: dict, profile: dict, name: str, opts):
    """Everything up to (not including) the submit: bindings, prompt, payload."""
    from studio_pipeline.engine import runner as RUN  # local: runner imports this module's peers

    model = opts.model or angle.get("model") or (spec.get("defaults") or {}).get("model")
    try:
        entry = REG.get(model)
    except REG.RegistryError as exc:
        raise TurnaroundError(str(exc))
    if entry["kind"] != "image":
        raise TurnaroundError(
            f"a reference angle image is a still, but {entry['key']} is a {entry['kind']} model."
        )

    args = angle_args(angle, spec, entry, name, opts)
    args.key = [*angle_keys(angle), *opts.identity]

    # Resolve bindings BEFORE the prompt: the citation numbers are positions in
    # the resolved list, and only `gather` knows what that list is.
    try:
        bindings = SUB.gather(entry, args)
    except (SUB.SubmitError, REFS.RefError, R.RunError) as exc:
        raise TurnaroundError(str(exc))
    field = (entry.get("images") or {}).get("refs")
    ordered = bindings.get(field) or []
    if not ordered:
        raise TurnaroundError(f"angle {angle['id']!r} resolved no image inputs.")
    # `ordered` holds NODE IDS — `gather` resolved every one of them — so the
    # angle images have to be resolved to ids before their positions can be found in
    # it. Looking up the name path returned a `ValueError` from `list.index`
    # for every angle with an angle image, which is all of them.
    angle_images = [SUB.as_node(key) for key in angle_keys(angle)]
    torso = SUB.as_node(torso_angle_key(angle)) if torso_angle_key(angle) else None
    angle_pos = ordered.index(angle_images[0]) + 1
    torso_pos = ordered.index(torso) + 1 if torso else None
    identity_pos = [i + 1 for i, k in enumerate(ordered) if k not in angle_images]

    args.prompt = build_prompt(angle, spec, profile, angle_pos, identity_pos, torso_pos)
    payload = RUN.build_payload(entry, args)
    try:
        SUB.check_payload_rules(entry, payload)
    except SUB.SubmitError as exc:
        raise TurnaroundError(str(exc))
    return entry, args, payload, bindings


# --------------------------------------------------------------------------
# filing the result
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------

def run_turnaround(name: str, opts) -> int:
    """The whole turnaround. Shared with `character create --turnaround`."""
    CHARACTER.check_name(name)
    # `require_project` returns the RECORD now, not the slug it was handed. Both
    # are needed and they are kept apart deliberately: the record is what a run
    # is filed against (an id, which survives a rename), the slug is what gets
    # printed back to a person and pasted into the follow-up commands below.
    project = PROJ.require_project(opts.project)
    opts.project = project["slug"]

    spec = load_spec()
    angles = select_angles(spec, opts.group, tuple(opts.angle or ()))
    profile = CHARACTER.load_profile(name)
    # Deliberately NOT the full write-time schema check. `create`/`set-profile`
    # enforce that on the way in; refusing to render because `voice:` is absent
    # would be a reading command policing a writing rule. What a turnaround actually
    # needs is the two keys its prompts draw on, and a thin bible costs prompt
    # quality rather than correctness — so it warns.
    thin = [k for k in ("wardrobe", "consistency") if not profile.get(k)]
    if thin:
        print(f"warning: {name}'s bible has no {', '.join(thin)} — the prompts will carry "
              f"less to hold the render on-model.", file=sys.stderr)
    check_angles(angles)

    ident, source = identity_nodes(name, opts.identity, opts.pick, opts.pick_tag,
                                   opts.identity_max, getattr(opts, "seed_pick", None))
    opts.identity = ident
    print(f"identity from {source}/ — {len(ident)} image(s):", file=sys.stderr)
    for node in ident:
        # The id AND the name. The id is what the run records and what a reader
        # can look up afterwards; the name is the only half a person recognises.
        print(f"  {node}  {store.node(node).get('name', '')}", file=sys.stderr)

    prepared = []
    for angle in angles:
        entry, args, payload, bindings = prepare(angle, spec, profile, name, opts)
        # **The RECORD, not the slug.** `draft` reads `args.project["id"]`, and
        # `angle_args` carries whatever `--project` was typed as. `gather` never
        # dereferenced it — a turnaround passes no `--input`, which is the only
        # thing that reads the project pool — so a slug travelled this far
        # unnoticed until a run had to be recorded from it.
        args.project = project
        try:
            SUB.preflight(entry, payload, bindings)
        except MS.SchemaError as exc:
            raise TurnaroundError(f"angle {angle['id']!r} would be refused by {entry['key']}:\n{exc}")
        prepared.append((angle, entry, args, payload, bindings))

    # GATE 1 — every payload, in full, before anything bills.
    # Where a review sheet is written in the library. Resolved once: the worker
    # produces a node and S3 is the only way its bytes reach this machine, so a
    # sheet exists in `review/` whether or not `--review-sheet DIR` was given.
    sheet_dest = (store.ensure_child_folder(
        CHARACTER.resolve(name)["root"], "review")["id"]
        if opts.review_sheet else None)
    for angle, entry, args, payload, bindings in prepared:
        # A LABEL for the approval block, not an id. A run id is minted by the
        # API when the run is recorded, which has not happened yet and must not:
        # hard rule #2 says the payload is approved before anything exists.
        run = f"{opts.project}/{R.slugify(args.slug)}"
        print(f"\n===== angle {angle['id']}  ->  run output (NOT yet a reference) =====")
        print(SUB.render(entry, run, payload, bindings, False))
        if opts.review_sheet:
            field = (entry.get("images") or {}).get("refs")
            sheet = review_sheet(angle["id"], bindings.get(field) or [],
                                 opts.review_sheet, sheet_dest)
            print(f"===== IMAGES — what {angle['id']} actually sends =====\n{sheet}")

    if opts.dry_run:
        return _draft_only(prepared, project, name)

    # No `--yes`. A person reads the payloads above and answers this, or nothing
    # is submitted: an approval flag is the door an agent walks through while
    # believing some earlier exchange counted as approval.
    if not click.confirm(f"\nsubmit {len(prepared)} generation(s) for {name}?", default=False):
        print("nothing submitted.", file=sys.stderr)
        return 1

    # ONE BAD SLOT DOES NOT CANCEL THE REST. A failure here is almost always a
    # property of that angle alone — an angle image the model refuses as sensitive, most
    # often — and says nothing about the others. Aborting on the first one cost a
    # live turnaround six healthy angles because the refusing angle happened to sort
    # first: seven asked for, `0 angle(s) completed`. So every angle is attempted
    # and the failures are reported together at the end.
    runrefs: dict[str, str] = {}
    failed: list[tuple[str, str]] = []
    for angle, entry, args, payload, bindings in prepared:
        print(f"\n----- {angle['id']} -----", file=sys.stderr)
        try:
            code = SUB.execute(entry, payload, bindings, args)
            if code != 0:
                raise SUB.SubmitError(f"exited {code}")
        except SUB.SubmitError as exc:
            print(f"  FAILED — {exc}", file=sys.stderr)
            failed.append((angle["id"], str(exc)))
            continue
        # The run the submit just recorded, by id. `latest` is resolved once and
        # immediately reduced to an id, because the follow-up `add-refs` line
        # printed below may be pasted an hour later — by which time `latest`
        # means a different run.
        record = R.resolve_run(f"{opts.project}/latest", opts.project)
        runrefs[angle["id"]] = f"{record['id']}#1"

    # GATE 2 — the results stay in their runs. Putting a generated image into
    # `characters/<name>/reference/` changes who that character IS, and that is a
    # separate decision from having agreed to spend a few dollars looking. Nothing
    # is lost by stopping here: the run owns its output permanently.
    print(json.dumps({
        "character": name, "project": opts.project,
        "rendered": runrefs,
        "failed": dict(failed),
        "filed_into_reference": None,
    }, indent=2))
    if failed:
        print(f"\n{len(failed)} angle(s) FAILED and were skipped:", file=sys.stderr)
        for angle_id, why in failed:
            print(f"  {angle_id}: {why}", file=sys.stderr)
        print("  an angle the model refuses will refuse again — fix or drop its angle image "
              "rather than re-running it.", file=sys.stderr)
    if not runrefs:
        return 1
    print("\nNOT added to the character. Review each one, then promote the keepers:",
          file=sys.stderr)
    for angle_id, ref in runrefs.items():
        group = next(s["group"] for s in angles if s["id"] == angle_id)
        print(f"  studio character add-refs {name} --to {group} --from-run {ref}",
              file=sys.stderr)
    print(f"  studio runs outputs {opts.project}/latest --presign   # to look first",
          file=sys.stderr)
    # Non-zero on a partial run: images exist and are listed above, but the set
    # is incomplete and a caller should not read exit 0 as "the turnaround is done".
    return 1 if failed else 0


TURNAROUND_OPTIONS = [
    click.option("--aspect-ratio", help="Override the spec's aspect ratio for every angle."),
    click.option("--dest", help="Also keep a local copy of each rendered image in this directory."),
    click.option("--dry-run", is_flag=True,
                 help="Render every payload for approval; submit nothing, bill nothing."),
    click.option("--extra", help="JSON object merged into every angle's model inputs."),
    click.option("--group", type=click.Choice(["all", *P.ANGLE_GROUPS]), default="all",
                 help="Render only this group of angles (default: all)."),
    click.option("--identity", type=click.Choice(["auto", "seed", "refs"]), default="auto",
                 help=("Where identity comes from: seed photos, the reference index, or "
                       "auto (seed when it has any).")),
    click.option("--identity-max", type=int, default=IDENTITY_MAX,
                 help=f"How many identity images to send per angle (default {IDENTITY_MAX})."),
    click.option("--model", help="Override the spec's model for every angle. See `models`."),
    # Comma-separated, not repeatable — same shape as `refs --pick`. Saying so
    # matters: repeating the flag is not an error, it just keeps the last one,
    # so four --pick flags quietly send one identity image.
    click.option("--pick", help="Comma-separated reference files to carry identity, "
                                "instead of seed/."),
    click.option("--seed-pick", "seed_pick",
                 help="Comma-separated seed files to carry identity, when seed/ holds more "
                      "than one angle sends. A file in a subfolder is named "
                      "<folder>/<file>."),
    click.option("--pick-tag", help="Identity from references carrying ALL these tags."),
    click.option("--project", help="REQUIRED. The project these runs belong to."),
    click.option("--review-sheet", "review_sheet", metavar="DIR",
                 help="Write a labelled contact sheet per angle showing the images that "
                      "payload sends, captioned [ImageN] in the order the model gets them."),
    click.option("--angle", multiple=True,
                 help="Render only this angle id. Repeatable — see the spec for the ids."),
]


def with_turnaround_options(fn):
    for option in reversed(TURNAROUND_OPTIONS):
        fn = option(fn)
    return fn


@click.command("turnaround", epilog="\n\nArguments:\n  NAME  The character to render.")
@click.argument("name", required=True)
@with_turnaround_options
def cmd_turnaround(name, **options):
    """Render the standard face and body reference set for a character.

    One run per angle in the angle spec: a generic angle image from config/ says how
    to stand, the character's seed photos say who it is, and the prompt comes
    from the spec filled with the character's own bible. Every payload is shown
    for approval before anything is submitted.
    """
    opts = SimpleNamespace(**options)
    try:
        return run_turnaround(name, opts)
    except TurnaroundError as exc:
        die(str(exc))
