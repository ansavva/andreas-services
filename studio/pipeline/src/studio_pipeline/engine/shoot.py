"""`studio character shoot` — render a character's STANDARD reference set.

One command over the shot spec (`domain/templates/reference_shots.yaml`). Each
slot in that spec becomes one recorded run: the slot's prompt, filled from the
character's own bible, plus two kinds of image — a generic POSE PLATE from
`config/pose/` saying how to stand, and the character's own SEED photos (or a
named reference selection) saying who it is.

Why it lives in `engine/` and not `domain/`: this is model invocation. It runs
the same nine-step submit lifecycle `runner.py` drives, and reuses it rather than
repeating it — `gather` → `preflight` → `render` → `execute`, once per slot. The
dependency arrow `cli → domain → adapters` stays intact, and importing
`domain.characters` from here is what `refs.py` already does.

    studio character shoot <name> --project <p> --dry-run     # nine payloads, no spend
    studio character shoot <name> --project <p> --group face
    studio character shoot <name> --project <p> --slot body_back --model nano-banana-pro

NOTHING SUBMITS WITHOUT APPROVAL. Every payload is rendered as the two-document
PROMPT / INPUT review first, and the batch then needs one explicit confirmation
from a person. `--dry-run` stops after the render.

WHAT THE PLATE IS FOR, AND WHY CITATIONS ARE COMPUTED
-----------------------------------------------------
A prompt says "[ImageN] is a pose guide — take only the stance from it". If N is
not where the plate actually landed, that instruction is aimed at the character's
own face, and nothing errors: the render is just quietly wrong.

The position is therefore never assumed. `gather()` assembles the list — it
de-dupes, filters by what the model accepts, and orders by category — so the
resolved list is the only authority on where the plate is. This module reads the
position out of it and fills the spec's `{pose_slot}` / `{identity_slots}` with
real numbers. That the plate currently comes out first (this module passes it as
the first explicit key) is an outcome, not something a prompt may rely on.

TWO HUMAN GATES, AND WHY THEY ARE SEPARATE
------------------------------------------
1. **Spending.** Nothing is submitted until a person has seen the full payload
   and said yes. There is no flag that answers this for them — an earlier
   version had `--yes`, which is exactly the door an agent walks through while
   believing it had approval from something else.
2. **Identity.** A generated image does NOT enter `characters/<name>/reference/`
   on its own. The shoot leaves every result in its run and stops. Promoting one
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
import pathlib
import string
import sys
from types import SimpleNamespace

import click
import yaml

from studio_pipeline.adapters import replicate as RA
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.adapters import store
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import paths as P
from studio_pipeline.domain import projects as PROJ
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import refs as REFS
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import schema as MS
from studio_pipeline.engine import submit as SUB

die = RA.die

SPEC_FILE = "reference_shots.yaml"
SPEC_PATH = os.path.join(
    os.path.dirname(os.path.abspath(CHARACTER.__file__)), "templates", SPEC_FILE
)

# One plate plus a handful of identity images is what a slot needs. Seed pools
# run to twenty-odd photographs, and sending all of them would breach the
# smaller engine caps and buy nothing — more angles of the same face do not
# sharpen it.
IDENTITY_MAX = 4


class ShootError(Exception):
    """Anything that should stop the shoot before it bills."""


# --------------------------------------------------------------------------
# the spec
# --------------------------------------------------------------------------

def load_spec(path: str = SPEC_PATH) -> dict:
    """Read the shot spec, or fail saying which file is wrong."""
    try:
        with open(path) as fh:
            spec = yaml.safe_load(fh)
    except FileNotFoundError:
        raise ShootError(f"the shot spec is missing from the package: {path}")
    except yaml.YAMLError as exc:
        raise ShootError(f"{path} is not valid YAML:\n  {exc}")
    if not isinstance(spec, dict) or not spec.get("slots"):
        raise ShootError(f"{path} must be a mapping with a non-empty `slots:` list.")

    ids = [s.get("id") for s in spec["slots"]]
    if len(set(ids)) != len(ids):
        raise ShootError(f"{path} has duplicate slot id(s).")
    for slot in spec["slots"]:
        missing = [k for k in ("id", "group", "pose_image", "prompt", "description", "tags")
                   if not slot.get(k)]
        if missing:
            raise ShootError(f"{path}: slot {slot.get('id')!r} is missing {missing}.")
        if slot["group"] not in P.POSE_GROUPS:
            raise ShootError(
                f"{path}: slot {slot['id']!r} has group {slot['group']!r}; "
                f"expected one of {list(P.POSE_GROUPS)}."
            )
        # An image nobody cites is an image the model is free to blend, which is
        # the whole reason citations are computed rather than hard-coded.
        if slot.get("torso_image") and "{torso_slot}" not in slot["prompt"]:
            raise ShootError(
                f"{path}: slot {slot['id']!r} binds a torso_image but its prompt "
                f"never cites {{torso_slot}}, so nothing tells the model what "
                f"that image is for."
            )
    unknown = [f for f in spec.get("default_set") or [] if f not in ids]
    if unknown:
        raise ShootError(f"{path}: default_set names slot(s) that do not exist: {unknown}")
    return spec


def select_slots(spec: dict, group: str | None, only: tuple[str, ...]) -> list[dict]:
    slots = spec["slots"]
    if only:
        by_id = {s["id"]: s for s in slots}
        unknown = [s for s in only if s not in by_id]
        if unknown:
            raise ShootError(
                f"no such slot(s): {', '.join(unknown)}\n"
                f"       the spec defines: {', '.join(by_id)}"
            )
        return [by_id[s] for s in only]
    if group and group != "all":
        slots = [s for s in slots if s["group"] == group]
        if not slots:
            raise ShootError(f"the spec has no slot in group {group!r}.")
    return slots


# --------------------------------------------------------------------------
# the prompt
# --------------------------------------------------------------------------

def _first_top(profile: dict) -> str:
    """The garment a face plate should wear: the most frequent top, plainly.

    The bible's first `tops[]` entry is the character's usual one, and its
    `detail` often names embroidery or a graphic — which a model renders
    differently every time and would make the group inconsistent. So the detail
    is not used.

    But the schema puts the COLOUR in that same field ("<colour, cut, any
    embroidery or graphic>"), so dropping it whole threw the colour away too,
    and a plate came back in a colour nobody chose. `colour:` is the narrow way
    back in: one word the plate can state, kept apart from the prose it would
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
    """The person's PROPORTIONS, for a body plate — from the bible, never here.

    A body plate exists to record a build, and the first one rendered lost it:
    the figure came back lean and narrow-shouldered, with none of the bible's
    shoulder-to-waist taper or arm mass. The cause is the pose plate. It is an
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
    Unused, on the one plate that strips the wardrobe back to shorts.

    A face plate crops at mid-chest, so legs and body hair are not in frame and
    would be noise; it takes what shows above the crop. A body plate is the
    whole figure and takes everything. Same split as `must_intro_face` /
    `must_intro_body`, for the same reason.

    HEIGHT comes first, and from `identity` rather than `body`. It is the one
    proportion the bible states as a NUMBER, and it was the only one never
    sent: the build clause read the `body:` block alone, so a corrected
    height_read sat unused while the prompt argued the point in adjectives.
    A figure has no scale of its own against a plain backdrop, so the number is
    the only thing that can settle it.
    """
    body = profile.get("body") or {}
    height = str((profile.get("identity") or {}).get("height_read") or "").strip()
    fields = ("silhouette", "chest_and_shoulders", "neck", "arms")
    if group != "face":
        fields += ("lower_body_and_hands", "body_hair")
    parts = [height] + [str(body.get(k) or "").strip() for k in fields]
    return " ".join(" ".join(p.split()) for p in parts if p)


def _style_text(profile: dict, defaults: dict) -> str:
    """What MEDIUM to render in — the character's, never this code's.

    The spec used to assert "photographic, no stylisation" for every slot, which
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


def build_prompt(slot: dict, spec: dict, profile: dict,
                 pose_position: int, identity_positions: list[int],
                 torso_position: int | None = None) -> str:
    """Fill one slot's prompt template. Raises if the spec names a value we lack."""
    defaults = spec.get("defaults") or {}
    intro = defaults.get(f"must_intro_{slot['group']}") or defaults.get("must_intro_face") or ""
    values = {
        **{k: v for k, v in defaults.items() if isinstance(v, str)},
        "top": _first_top(profile),
        "style": _style_text(profile, defaults),
        "must": _must_text(profile, intro),
        "build": _build_text(profile, slot["group"]),
        "age": _age_text(profile),
        "identity_block": (profile.get("text_identity_block") or "").strip(),
        "pose_slot": f"[Image{pose_position}]",
        "identity_slots": _slots_phrase(identity_positions),
    }
    # Absent rather than empty when the slot binds no torso plate, so a prompt
    # that cites one it never declared fails loudly instead of rendering "".
    if torso_position is not None:
        values["torso_slot"] = f"[Image{torso_position}]"
    try:
        text = string.Formatter().vformat(slot["prompt"], (), values)
    except KeyError as exc:
        raise ShootError(
            f"slot {slot['id']!r} uses {{{exc.args[0]}}}, which nothing provides.\n"
            f"       available: {', '.join(sorted(values))}"
        )
    return " ".join(text.split())


# --------------------------------------------------------------------------
# the images
# --------------------------------------------------------------------------

def plate_key(slot: dict) -> str:
    """The slot's pose plate, as a full key, checked for shape.

    The spec stores a bucket-relative key (`config/pose/body/front.png`) so the
    prose in source control names the object in S3 that `dev-setup.sh` copies out.
    """
    return _plate_key(slot, "pose_image")


def torso_plate_key(slot: dict) -> str | None:
    """The slot's SECOND guide, or None — see `plate_keys` for why it exists."""
    return _plate_key(slot, "torso_image") if slot.get("torso_image") else None


def plate_keys(slot: dict) -> list[str]:
    """Every guide plate this slot binds, in citation order.

    Most slots bind one. The back three-quarters bind two, because the face
    plates are cut from a head sheet and END AT A NECK STUMP: they carry no
    shoulder line at all, so `{guide}`'s "match the direction the body and head
    face" has no body in it to match, and a symmetric stump reads as square.
    Rendered that way, both back three-quarters came back with a correctly
    turned head on a torso flat to the camera — the prompt said to angle the
    shoulders and the reference image said not to, and the image won. The body
    plate for the same orientation is a whole figure at 135 degrees, so binding
    it as a second guide gives the torso a direction to copy.
    """
    return [k for k in (plate_key(slot), torso_plate_key(slot)) if k]


def _plate_key(slot: dict, field: str) -> str:
    rel = slot[field]
    if not rel.startswith(P.CONFIG + "/"):
        raise ShootError(
            f"slot {slot['id']!r}: {field} {rel!r} must be a key under "
            f"{P.CONFIG}/ — plates are config, not character material."
        )
    return s3c.key(rel)


def check_plates(s3, slots: list[dict]) -> None:
    """Every plate must already be in the bucket. Fail once, listing all of them."""
    missing = []
    for slot in slots:
        for key in plate_keys(slot):
            if not store.exists(key):
                missing.append(key)
    if missing:
        raise ShootError(
            "pose plate(s) missing from the bucket:\n"
            + "".join(f"       {k}\n" for k in missing)
            + "       These live in the repo under studio/config/ and are copied out by\n"
            "       studio/scripts/dev-setup.sh — run it, then try again."
        )


def _too_many(name: str, pool: str, keys: list[str], limit: int, how: str) -> ShootError:
    """Refuse an oversized pool rather than taking the first few.

    `reference/` already refuses an over-cap selection rather than truncating,
    "because which images a generation saw should not be decided by whatever the
    folder listing happened to return". A seed pool deserves the same: sorted
    order is not quality order. One character's seed pool opens with a poster, a
    launch graphic, a collage and a wide shot of him across a room — the four
    worst images in it for carrying a face, and exactly the four a silent
    `[:limit]` would have sent.
    """
    listing = "".join(f"       {os.path.basename(k)}\n" for k in keys[:20])
    more = f"       … and {len(keys) - 20} more\n" if len(keys) > 20 else ""
    return ShootError(
        f"{name}'s {pool}/ holds {len(keys)} images and a slot sends {limit}.\n"
        f"       Name the ones that carry identity best — a clear, unobstructed "
        f"view of the face and build:\n{listing}{more}"
        f"       {how}"
    )


def _seed_picked(name: str, seed_pick: str) -> list[str]:
    """Resolve `--seed-pick` names, by basename or bare stem, in the order given."""
    seed = [k for k in REFS.character_pool_keys(name, "seed")
            if os.path.splitext(k)[1].lower() in R.IMG_EXTS]
    want = [x.strip() for x in seed_pick.split(",") if x.strip()]
    by_base = {os.path.basename(k): k for k in seed}
    by_stem = {os.path.splitext(b)[0]: k for b, k in by_base.items()}
    missing = [w for w in want if w not in by_base and w not in by_stem]
    if missing:
        raise ShootError(
            f"not in {name}'s seed/: {', '.join(missing)}\n"
            f"       see: studio character pool {name} seed")
    return [by_base.get(w) or by_stem[w] for w in want]


def identity_keys(s3, name: str, source: str, pick: str | None, tags: str | None,
                  limit: int = IDENTITY_MAX,
                  seed_pick: str | None = None) -> tuple[list[str], str]:
    """The images that say WHO this is, and where they came from.

    Seed material is preferred: it is the founding source, and driving a shoot
    off already-generated references feeds model output back in as identity,
    which compounds drift with every pass.

    Nothing here silently truncates. If a pool holds more than one slot sends,
    the caller is asked which — see `_too_many`.
    """
    if pick or tags:
        keys = REFS.character_ref_keys(
            name, None, [x.strip() for x in pick.split(",")] if pick else None,
            [t.strip() for t in tags.split(",")] if tags else None)
        # The two pools MIX. Naming references used to silence --seed-pick
        # entirely, which is backwards for the case that wants both: curated
        # reference frames give clean, consistent angles, and a couple of seed
        # photographs anchor them to the real source so a shoot is not driven
        # purely by earlier model output. Refusing the combination made the
        # safer choice the one you could not express.
        if seed_pick:
            keys = keys + _seed_picked(name, seed_pick)
            source = "reference+seed"
        else:
            source = "reference"
        if len(keys) > limit:
            raise _too_many(name, source, keys, limit,
                            "Narrow --pick / --pick-tag / --seed-pick, or raise "
                            "--identity-max.")
        return keys, source

    if source in ("auto", "seed"):
        seed = REFS.character_pool_keys(name, "seed")
        seed = [k for k in seed if os.path.splitext(k)[1].lower() in R.IMG_EXTS]
        if seed_pick:
            chosen = _seed_picked(name, seed_pick)
            if len(chosen) > limit:
                raise _too_many(name, "seed", chosen, limit,
                                "Pick fewer, or raise --identity-max.")
            return chosen, "seed"
        if seed:
            if len(seed) > limit:
                raise _too_many(
                    name, "seed", seed, limit,
                    f"--seed-pick <file>,<file>       # name them\n"
                    f"       --identity refs --pick …        # use the reference index instead\n"
                    f"       studio contact-sheet --character {name} --folder seed --out "
                    f"/tmp/{name}-seed.png   # look first")
            return seed, "seed"
        if source == "seed":
            raise ShootError(
                f"{name} has no images in seed/, and --identity seed was asked for.\n"
                f"       Add the founding material: studio character add-to {name} seed <files…>"
            )

    keys = REFS.character_ref_keys(name, None, None, None)
    if not keys:
        raise ShootError(
            f"{name} has nothing to carry identity — seed/ is empty and reference/ has "
            f"no selection.\n"
            f"       Add source material first: studio character add-to {name} seed <files…>"
        )
    if len(keys) > limit:
        raise _too_many(name, "reference", keys, limit,
                        f"Narrow it with --pick / --pick-tag, or set a default_set:\n"
                        f"       studio character refs {name} --describe")
    return keys, "reference"


# --------------------------------------------------------------------------
# seeing what is actually being sent
# --------------------------------------------------------------------------

def review_sheet(s3, slot_id: str, keys: list[str], out_dir: str, cache: dict) -> str:
    """A labelled contact sheet of the images one payload binds, in slot order.

    The payload review names its images (`<presigned: characters/…>`) but a name
    is not a look. Approving a generation you cannot see is approving a
    description of it — and the mistakes that matter here are visual: a pose
    plate that is the wrong way round, an identity image that is mostly a poster,
    a panel whose speech balloon the model will happily reproduce.

    Tiles are captioned `[ImageN]` in the order the model receives them, so the
    sheet and the prompt's citations read against each other.
    """
    from studio_pipeline.domain import contact_sheet as SHEET

    os.makedirs(out_dir, exist_ok=True)
    paths, captions = [], []
    for i, key in enumerate(keys, start=1):
        local = cache.get(key)
        if local is None:
            local = os.path.join(out_dir, f"src-{len(cache)}-{os.path.basename(key)}")
            store.download(key, pathlib.Path(local))
            cache[key] = local
        paths.append(local)
        captions.append(f"[Image{i}] {os.path.basename(key)}")
    out = os.path.join(out_dir, f"{slot_id}.png")
    return SHEET.build(paths, out, cols=min(len(paths), 5), cell=320,
                       captions=captions, quiet=True)


# --------------------------------------------------------------------------
# one slot
# --------------------------------------------------------------------------

def slot_args(slot: dict, spec: dict, entry: dict, name: str, opts) -> SimpleNamespace:
    """The namespace `runner`/`submit` expect, for one slot.

    Every image is passed as an explicit `--key`, in the order the model should
    see them: the plate first, identity after. `--character` is deliberately NOT
    set — this module has already chosen the keys, and letting `gather()` resolve
    a second set from the bible's `default_set` would silently add images nobody
    picked. `record_characters` keeps the run associated with the character all
    the same.
    """
    defaults = spec.get("defaults") or {}
    model = opts.model or slot.get("model") or defaults.get("model")
    if model != entry["key"]:
        raise ShootError(f"internal: slot resolved model {model!r} but entry is {entry['key']!r}")

    extra: dict = {}
    extra.update(defaults.get("extra") or {})
    extra.update((spec.get("per_model") or {}).get(model) or {})
    extra.update(slot.get("extra") or {})
    if opts.extra:
        try:
            override = json.loads(opts.extra)
        except json.JSONDecodeError as exc:
            raise ShootError(f"--extra is not valid JSON: {exc}")
        if not isinstance(override, dict):
            raise ShootError("--extra must be a JSON object.")
        extra.update(override)

    d = SUB.defaults(entry["kind"])
    return SimpleNamespace(
        model=model,
        project=opts.project,
        slug=f"ref-{slot['id'].replace('_', '-')}",
        prompt=None,                      # filled once the citation slots are known
        prompt_file=None, prompt_json=None, input_file=None,
        extra=json.dumps(extra) if extra else None,
        aspect_ratio=opts.aspect_ratio or slot.get("aspect_ratio") or defaults.get("aspect_ratio"),
        key=[], character=(), record_characters=(name,),
        # The slot this run came from, carried into request.json. `add-refs
        # --from-run` reads it back to write the description and tags the spec
        # already holds for that slot — without it those fields are dead data
        # and every promotion is a hand-retype of prose that is right there.
        record_extra={"reference_slot": slot["id"]},
        pick=None, pick_tag=None, slots=None,
        image_run=None, ref_run=(), input_=(), input=(),
        start_run=None, start_key=None, end_run=None, end_key=None,
        no_refs=False, dry_run=opts.dry_run, json_=False, json=False,
        poll=True, dest=opts.dest, expires=opts.expires,
        interval=d["interval"], timeout=d["timeout"],
    )


def prepare(slot: dict, spec: dict, profile: dict, name: str, s3, opts):
    """Everything up to (not including) the submit: bindings, prompt, payload."""
    from studio_pipeline.engine import runner as RUN  # local: runner imports this module's peers

    model = opts.model or slot.get("model") or (spec.get("defaults") or {}).get("model")
    try:
        entry = REG.get(model)
    except REG.RegistryError as exc:
        raise ShootError(str(exc))
    if entry["kind"] != "image":
        raise ShootError(
            f"a reference plate is a still, but {entry['key']} is a {entry['kind']} model."
        )

    args = slot_args(slot, spec, entry, name, opts)
    args.key = [*plate_keys(slot), *opts.identity]

    # Resolve bindings BEFORE the prompt: the citation numbers are positions in
    # the resolved list, and only `gather` knows what that list is.
    try:
        bindings = SUB.gather(entry, s3, args)
    except (SUB.SubmitError, REFS.RefError, R.RunError) as exc:
        raise ShootError(str(exc))
    field = (entry.get("images") or {}).get("refs")
    ordered = bindings.get(field) or []
    if not ordered:
        raise ShootError(f"slot {slot['id']!r} resolved no image inputs.")
    plates = plate_keys(slot)
    torso = torso_plate_key(slot)
    pose_pos = ordered.index(plate_key(slot)) + 1
    torso_pos = ordered.index(torso) + 1 if torso else None
    identity_pos = [i + 1 for i, k in enumerate(ordered) if k not in plates]

    args.prompt = build_prompt(slot, spec, profile, pose_pos, identity_pos, torso_pos)
    payload = RUN.build_payload(entry, args)
    try:
        SUB.check_payload_rules(entry, payload)
    except SUB.SubmitError as exc:
        raise ShootError(str(exc))
    return entry, args, payload, bindings


# --------------------------------------------------------------------------
# filing the result
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------

def run_shoot(name: str, opts) -> int:
    """The whole shoot. Shared with `character create --shoot`."""
    CHARACTER.check_name(name)
    s3 = s3c.client()
    opts.project = PROJ.require_project(s3, opts.project)

    spec = load_spec()
    slots = select_slots(spec, opts.group, tuple(opts.slot or ()))
    profile = CHARACTER.load_profile(s3, name)
    # Deliberately NOT the full write-time schema check. `create`/`set-profile`
    # enforce that on the way in; refusing to render because `voice:` is absent
    # would be a reading command policing a writing rule. What a shoot actually
    # needs is the two keys its prompts draw on, and a thin bible costs prompt
    # quality rather than correctness — so it warns.
    thin = [k for k in ("wardrobe", "consistency") if not profile.get(k)]
    if thin:
        print(f"warning: {name}'s bible has no {', '.join(thin)} — the prompts will carry "
              f"less to hold the render on-model.", file=sys.stderr)
    check_plates(s3, slots)

    ident, source = identity_keys(s3, name, opts.identity, opts.pick, opts.pick_tag,
                                  opts.identity_max, getattr(opts, "seed_pick", None))
    opts.identity = ident
    print(f"identity from {source}/ — {len(ident)} image(s):", file=sys.stderr)
    for k in ident:
        print(f"  {k}", file=sys.stderr)

    token = RA.load_token()
    prepared = []
    for slot in slots:
        entry, args, payload, bindings = prepare(slot, spec, profile, name, s3, opts)
        try:
            SUB.preflight(entry, payload, bindings, token)
        except MS.SchemaError as exc:
            raise ShootError(f"slot {slot['id']!r} would be refused by {entry['key']}:\n{exc}")
        prepared.append((slot, entry, args, payload, bindings))

    # GATE 1 — every payload, in full, before anything bills.
    sheet_cache: dict[str, str] = {}
    for slot, entry, args, payload, bindings in prepared:
        run = f"{opts.project}/{R.new_run_id(args.slug)}"
        print(f"\n===== slot {slot['id']}  ->  run output (NOT yet a reference) =====")
        print(SUB.render(entry, run, payload, bindings, False))
        if opts.review_sheet:
            field = (entry.get("images") or {}).get("refs")
            sheet = review_sheet(s3, slot["id"], bindings.get(field) or [],
                                 opts.review_sheet, sheet_cache)
            print(f"===== IMAGES — what {slot['id']} actually sends =====\n{sheet}")

    if opts.dry_run:
        print(f"\n(dry run — {len(prepared)} slot(s) rendered, nothing submitted, "
              f"nothing billed)", file=sys.stderr)
        return 0

    # No `--yes`. A person reads the payloads above and answers this, or nothing
    # is submitted: an approval flag is the door an agent walks through while
    # believing some earlier exchange counted as consent.
    if not click.confirm(f"\nsubmit {len(prepared)} generation(s) for {name}?", default=False):
        print("nothing submitted.", file=sys.stderr)
        return 1

    # ONE BAD SLOT DOES NOT CANCEL THE REST. A failure here is almost always a
    # property of that slot alone — a plate the model refuses as sensitive, most
    # often — and says nothing about the others. Aborting on the first one cost a
    # live shoot six healthy slots because the refusing slot happened to sort
    # first: seven asked for, `0 slot(s) completed`. So every slot is attempted
    # and the failures are reported together at the end.
    runrefs: dict[str, str] = {}
    failed: list[tuple[str, str]] = []
    for slot, entry, args, payload, bindings in prepared:
        print(f"\n----- {slot['id']} -----", file=sys.stderr)
        try:
            code = SUB.execute(entry, payload, bindings, s3, token, args)
            if code != 0:
                raise SUB.SubmitError(f"exited {code}")
        except (SUB.SubmitError, RA.ReplicateError) as exc:
            print(f"  FAILED — {exc}", file=sys.stderr)
            failed.append((slot["id"], str(exc)))
            continue
        _project, run_id = R.resolve_run(f"{opts.project}/latest", opts.project)
        runrefs[slot["id"]] = f"{opts.project}/{run_id}#1"

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
        print(f"\n{len(failed)} slot(s) FAILED and were skipped:", file=sys.stderr)
        for slot_id, why in failed:
            print(f"  {slot_id}: {why}", file=sys.stderr)
        print("  a slot the model refuses will refuse again — fix or drop its plate "
              "rather than re-running it.", file=sys.stderr)
    if not runrefs:
        return 1
    print("\nNOT added to the character. Review each one, then promote the keepers:",
          file=sys.stderr)
    for slot_id, ref in runrefs.items():
        group = next(s["group"] for s in slots if s["id"] == slot_id)
        print(f"  studio character add-refs {name} --to {group} --from-run {ref}",
              file=sys.stderr)
    print(f"  studio runs outputs {opts.project}/latest --presign   # to look first",
          file=sys.stderr)
    # Non-zero on a partial run: images exist and are listed above, but the set
    # is incomplete and a caller should not read exit 0 as "the shoot is done".
    return 1 if failed else 0


SHOOT_OPTIONS = [
    click.option("--aspect-ratio", help="Override the spec's aspect ratio for every slot."),
    click.option("--dest", help="Also keep a local copy of each plate in this directory."),
    click.option("--dry-run", is_flag=True,
                 help="Render every payload for approval; submit nothing, bill nothing."),
    click.option("--expires", type=int, default=3600, help="Presign expiry (default 3600)."),
    click.option("--extra", help="JSON object merged into every slot's model inputs."),
    click.option("--group", type=click.Choice(["all", *P.POSE_GROUPS]), default="all",
                 help="Shoot only this group of slots (default: all)."),
    click.option("--identity", type=click.Choice(["auto", "seed", "refs"]), default="auto",
                 help=("Where identity comes from: seed photos, the reference index, or "
                       "auto (seed when it has any).")),
    click.option("--identity-max", type=int, default=IDENTITY_MAX,
                 help=f"How many identity images to send per slot (default {IDENTITY_MAX})."),
    click.option("--model", help="Override the spec's model for every slot. See `models`."),
    # Comma-separated, not repeatable — same shape as `refs --pick`. Saying so
    # matters: repeating the flag is not an error, it just keeps the last one,
    # so four --pick flags quietly send one identity image.
    click.option("--pick", help="Comma-separated reference files to carry identity, "
                                "instead of seed/."),
    click.option("--seed-pick", "seed_pick",
                 help="Comma-separated seed files to carry identity, when seed/ holds more "
                      "than one slot sends."),
    click.option("--pick-tag", help="Identity from references carrying ALL these tags."),
    click.option("--project", help="REQUIRED. The project these runs belong to."),
    click.option("--review-sheet", "review_sheet", metavar="DIR",
                 help="Write a labelled contact sheet per slot showing the images that "
                      "payload sends, captioned [ImageN] in the order the model gets them."),
    click.option("--slot", multiple=True,
                 help="Shoot only this slot id. Repeatable — see the spec for the ids."),
]


def with_shoot_options(fn):
    for option in reversed(SHOOT_OPTIONS):
        fn = option(fn)
    return fn


@click.command("shoot", epilog="\n\nArguments:\n  NAME  The character to shoot.")
@click.argument("name", required=True)
@with_shoot_options
def cmd_shoot(name, **options):
    """Render the standard face and body reference set for a character.

    One run per slot in the shot spec: a generic pose plate from config/ says how
    to stand, the character's seed photos say who it is, and the prompt comes
    from the spec filled with the character's own bible. Every payload is shown
    for approval before anything is submitted.
    """
    opts = SimpleNamespace(**options)
    try:
        return run_shoot(name, opts)
    except ShootError as exc:
        die(str(exc))
