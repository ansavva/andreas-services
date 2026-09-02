"""`studio character turnaround` — draft a character's STANDARD reference set.

**This command does three things, and used to do eight.** It resolves WHICH
images carry identity, asks the API for the angles, and prints what came back.

    studio character turnaround <name> --project <p> --dry-run   # assemble, record nothing
    studio character turnaround <name> --project <p> --group face
    studio character turnaround <name> --project <p> --angle body_back --model nano-banana-pro

WHAT MOVED, AND WHY IT HAD TO
-----------------------------
The angle spec was `domain/templates/reference_angles.yaml`, a file in this
package, and this module read it, filled it from the bible, counted `[ImageN]`
slots and built a payload. All of that is now
`POST /api/characters/<id>/turnaround`.

Every word of that prose was behind a `pip install`. Tuning one — which is the
entire nature of it, it is written against what a model actually returned —
meant a code change, a review and a release, and the app could not show a person
a reference prompt, let alone let them fix one or start a render. The spec is
rows the API serves and the app edits; `studio spec` moves it between stacks.

**Assembly moved rather than being copied.** Two implementations would be two
opinions about what a run was told to render, and a run records the outcome
rather than the reasoning — so the disagreement would be undetectable
afterwards. That is the argument `engine/refs.py` records for moving selection
behind `GET /api/characters/<id>/selection`, unchanged.

WHAT DELIBERATELY STAYED
------------------------
**Which images carry identity.** The route refuses to guess it, and this module
is where the guessing would otherwise happen: `--seed-pick`, `--pick`,
`--pick-tag`, the seed-tree walk and the oversized-pool refusal are all here.
Which photographs say who somebody is is the judgement a reference library is
built out of, and `_too_many` exists precisely so sort order never makes it.

NOTHING SUBMITS, AT ALL
-----------------------
Every angle becomes an unapproved `draft`. `--dry-run` stops one step earlier
and records nothing. Approval and submission are `runs approve` and
`runs submit`, which is where they were already.

TWO HUMAN GATES, AND WHY THEY ARE SEPARATE
------------------------------------------
1. **Spending.** Nothing is submitted until a person has seen the full payload
   and said yes. There is no flag that answers this for them — an earlier
   version had `--yes`, which is exactly the door an agent walks through while
   believing it had approval from something else.
2. **Identity.** A generated image does NOT enter `characters/<name>/reference/`
   on its own. The turnaround leaves every result in its run and stops. Promoting one
   into a character's identity is a second, deliberate act:

       studio objects copy <runref> --to <name>/reference/
       studio describe <node> --tag default --tag face

   These are different decisions. "Yes, spend a few dollars seeing what this
   looks like" is not "yes, this image is now part of who this character is",
   and a single confirmation covering both silently turns the first into the
   second. The run keeps its output either way, so nothing is lost by looking
   first.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from types import SimpleNamespace

import click

from studio_pipeline.adapters import api, auth, store
from studio_pipeline.adapters import entities as E
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import paths as P
from studio_pipeline.domain import projects as PROJ
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import refs as REFS

# `errors.die`, not a copy re-exported from the HTTP adapter — see
# `errors.die`'s docstring for the nine that used to exist.
from studio_pipeline.errors import die  # noqa: E402

# `TEMPLATES_DIR`, not `dirname(CHARACTER.__file__)`. That expression resolved
# the spec only while `characters` was a single module one level above
# `templates/`; the moment it became a package (#305) it pointed a segment too
# deep and the turnaround lost its spec. The directory names itself now — the same
# correction `STUDIO_DIR` exists for.

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


def run_turnaround(name: str, opts) -> int:
    """The whole turnaround. Shared with `character create --turnaround`.

    **The assembly is the API's now, and this command does three things.** It
    resolves WHICH images carry identity — the one judgement that has to stay
    with a person, and the one thing the route deliberately refuses to guess —
    then asks for the angles, then prints what came back.

    Everything it used to do between those steps is gone: reading a spec off
    disk, filling it from the bible, counting `[ImageN]` slots and building a
    payload. All of it is `POST /api/characters/<id>/turnaround`, so the CLI and
    the app cannot disagree about what a reference render was told to say.
    """
    CHARACTER.check_name(name)
    record = CHARACTER.resolve(name)
    # `require_project` returns the RECORD, not the slug it was handed. Both are
    # needed and kept apart: the record is what a run is filed against (an id,
    # which survives a rename), the slug is what gets printed back to a person.
    project = PROJ.require_project(opts.project)
    opts.project = project["slug"]

    ident, source = identity_nodes(name, opts.identity, opts.pick, opts.pick_tag,
                                   opts.identity_max, getattr(opts, "seed_pick", None))
    print(f"identity from {source}/ — {len(ident)} image(s):", file=sys.stderr)
    for node in ident:
        # The id AND the name. The id is what the run records and what a reader
        # can look up afterwards; the name is the only half a person recognises.
        print(f"  {node}  {store.node(node).get('name', '')}", file=sys.stderr)

    extra = None
    if opts.extra:
        try:
            extra = json.loads(opts.extra)
        except json.JSONDecodeError as exc:
            raise TurnaroundError(f"--extra is not valid JSON: {exc}")
        if not isinstance(extra, dict):
            raise TurnaroundError("--extra must be a JSON object.")
    if opts.aspect_ratio:
        extra = {**(extra or {}), "aspect_ratio": opts.aspect_ratio}

    try:
        answer = E.draft_turnaround(
            record["id"],
            project=project["id"],
            identity=ident,
            group=None if opts.group == "all" else opts.group,
            angles=list(opts.angle) if opts.angle else None,
            model=opts.model,
            extra=extra,
            preview=bool(opts.dry_run),
        )
    except api.ApiError as exc:
        raise TurnaroundError(str(exc))

    made = answer.get("preview") if opts.dry_run else answer.get("drafted")
    made = made or []
    failed = answer.get("failed") or []

    # GATE 1 — every payload, in full. It is rendered from the plan the API
    # assembled and sent back, rather than from a second assembly here: two
    # assemblies are two chances to differ, and the one that matters is the one
    # the row holds.
    sheet_dest = (store.ensure_child_folder(record["root"], "review")["id"]
                  if opts.review_sheet else None)
    for entry in made:
        label = f"{opts.project}/ref-{entry['angle'].replace('_', '-')}"
        print(f"\n===== angle {entry['angle']}  ->  run output (NOT yet a reference) =====")
        print(_payload_review(label, entry))
        if opts.review_sheet:
            nodes = [send["node"] for send in entry.get("sends") or []]
            print(f"===== IMAGES — what {entry['angle']} actually sends =====\n"
                  f"{review_sheet(entry['angle'], nodes, opts.review_sheet, sheet_dest)}")

    origin = app_origin()
    if opts.dry_run:
        print(f"\n(preview — {len(made)} angle(s) assembled, nothing recorded, "
              f"nothing billed)", file=sys.stderr)
    else:
        print(f"\n{len(made)} draft(s) — nothing approved, nothing submitted, "
              f"nothing billed:", file=sys.stderr)
        for entry in made:
            where = (f"{origin}/p/{project['id']}/r/{entry['id']}" if origin
                     else entry["id"])
            print(f"  {entry['angle']:<32} {where}", file=sys.stderr)

    for entry in failed:
        print(f"  {entry['angle']:<32} NOT DRAFTED — {entry['error']}", file=sys.stderr)

    if made and not opts.dry_run:
        print(f"\nreview and approve each in the app, then send it:\n"
              f"  studio runs submit <run-id>\n"
              f"  studio runs discard <run-id>      # one you do not want\n"
              f"  studio runs list {opts.project} --status draft",
              file=sys.stderr)
    return 1 if failed else 0


def _payload_review(label: str, entry: dict) -> str:
    """The two documents hard rule #2 wants read, from the plan the API assembled.

    The same two the runner prints — PROMPT then INPUT — and deliberately the
    same shape, because a person comparing a turnaround's payload with a
    `studio run`'s should not have to notice which command produced it. Image
    fields are named rather than presigned: a signed URL is 2 KB of noise, and
    the send rows already say which node lands in which slot.
    """
    plan = entry.get("plan") or {}
    sends = entry.get("sends") or []
    params = dict(plan.get("params") or {})
    body = {
        "run": label,
        "model": entry.get("model"),
        "input": {**params, "prompt": "<< see document 1/2 — PROMPT >>",
                  "images": [send["node"] for send in sends]},
    }
    return (f"===== 1/2  PROMPT — serialized into the `prompt` string at submit time =====\n"
            f"{json.dumps(plan.get('prompt') or '', indent=2, ensure_ascii=False)}\n\n"
            f"===== 2/2  INPUT — the parameters this model receives =====\n"
            f"{json.dumps(body, indent=2, ensure_ascii=False)}")


TURNAROUND_OPTIONS = [
    click.option("--aspect-ratio", help="Override the aspect ratio for every angle."),
    click.option("--dry-run", is_flag=True,
                 help="Assemble every payload and record nothing. Without it each "
                      "angle becomes an unapproved draft."),
    click.option("--extra", help="JSON object merged into every angle's model inputs."),
    click.option("--group", type=click.Choice(["all", *P.ANGLE_GROUPS]), default="all",
                 help="Render only this group of angles (default: all)."),
    click.option("--identity", type=click.Choice(["auto", "seed", "refs"]), default="auto",
                 help=("Where identity comes from: seed photos, the reference index, or "
                       "auto (seed when it has any).")),
    click.option("--identity-max", type=int, default=IDENTITY_MAX,
                 help=f"How many identity images to send per angle (default {IDENTITY_MAX})."),
    click.option("--model", help="Override the model for every angle. See `models`."),
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
                 help="Render only this angle id. Repeatable — `studio spec show` lists them."),
]


def with_turnaround_options(fn):
    for option in reversed(TURNAROUND_OPTIONS):
        fn = option(fn)
    return fn


@click.command("turnaround", epilog="\n\nArguments:\n  NAME  The character to render.")
@click.argument("name", required=True)
@with_turnaround_options
def cmd_turnaround(name, **options):
    """Draft the standard face and body reference set for a character.

    One draft per angle in this library's reference spec (`studio spec show`).
    The seed photographs say who it is, the spec says what each angle is, and
    the API assembles the two. Nothing is approved and nothing is submitted.
    """
    opts = SimpleNamespace(**options)
    try:
        code = run_turnaround(name, opts)
    except TurnaroundError as exc:
        die(str(exc))
    # `ctx.exit`, not `return`. **Click ignores a callback's return value**, so a
    # partial turnaround — some angles drafted, some refused — reported success
    # for as long as this said `return`. The same trap took `spec push`'s
    # conflict refusal, which is the worse of the two places to have it.
    if code:
        click.get_current_context().exit(code)
