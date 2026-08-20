"""`studio scenes board` / `render` / `check` — a storyboard, then the shots.

The two commands in a scene's life that spend money, plus the one that tells you
whether they would work before they do.

They live in `engine/` and not beside the rest of `scenes` for the reason
`shoot.py` does: this is model invocation. It drives the same submit lifecycle
`runner.py` drives and reuses it rather than repeating it — `gather` →
`preflight` → `render` → `execute`, once per panel or per shot. The dependency
arrow `cli → domain → adapters` stays intact, and the commands are attached onto
the `scenes` group from `cli.py`, so `domain/scenes.py` never imports `engine`.

    studio scenes check <p>/<slug>              # would this plan fly? free
    studio scenes board <p>/<slug> --dry-run    # every panel payload, no spend
    studio scenes board <p>/<slug>              # the panels
    studio scenes render <p>/<slug> --shot 2    # one shot's video

WHY PANELS ARE CHAINED TO EACH OTHER
------------------------------------
Panel 1 renders from the character's references alone. Every later panel renders
from those *plus the panels already on the board*, so the board converges on one
location, wardrobe and grade instead of drifting a shot at a time. That makes the
batch sequential — a panel cannot reference one that does not exist yet — and it
makes re-rendering panel *k* invalidate everything after it, which is reported
rather than silently tolerated.

WHY A SHOT'S START FRAME IS USUALLY NOT ITS PANEL
-------------------------------------------------
A cut is seamless only from the literal last frame of the shot before it. A panel
composed for the same moment differs from that frame in a hundred small ways, all
of which read as a jump. So when a shot has a handoff frame, the handoff is the
start frame and the panel it displaces becomes a reference — still steering where
the shot goes, no longer breaking the join. The rule lives in
`domain/storyboard.resolve_roles`; this module only turns its answer into
bindings.

EVERY MODEL RULE STAYS IN `submit.py`
-------------------------------------
How many images a model takes, whether a start frame excludes references, which
extensions are rejected, whether the start frame counts against the cap — all of
that is already enforced in `gather` and `preflight`, with error messages that
name the fix. This module decides ROLE and ORDER and hands the result over.
Re-implementing a cap here is how two versions of it drift apart, and the one
that drifts is always the copy.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from types import SimpleNamespace

import click

from studio_pipeline.adapters import replicate as RA
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.adapters import store
from studio_pipeline.domain import contact_sheet as SHEET
from studio_pipeline.domain import paths as P
from studio_pipeline.domain import runs as R
from studio_pipeline.domain import scenes as SC
from studio_pipeline.domain import storyboard as SB
from studio_pipeline.engine import refs as REFS
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import schema as MS
from studio_pipeline.engine import submit as SUB
from studio_pipeline.errors import reports

#: When a model documents no reference cap, a board still should not send the
#: whole history — every extra image dilutes the ones that matter, and the
#: aggregate payload is itself a limit (see `submit.preflight`).
BOARD_REFS_DEFAULT = 8


class BoardError(Exception):
    """Anything that should stop a board or a shot before it bills."""


# --------------------------------------------------------------------------
# selecting
# --------------------------------------------------------------------------

def select_shots(manifest: dict, only: tuple[str, ...]) -> list[dict]:
    """Shots named by number or by id, or all of them."""
    shots = SC.scene_shots(manifest)
    if not only:
        return shots
    by_key = {}
    for shot in shots:
        by_key[str(shot.get("n"))] = shot
        by_key[shot.get("id")] = shot
    picked, unknown = [], []
    for name in only:
        shot = by_key.get(str(name))
        (picked.append(shot) if shot is not None else unknown.append(name))
    if unknown:
        have = ", ".join("{} ({})".format(s.get("n"), s.get("id")) for s in shots)
        raise BoardError(f"no such shot(s): {', '.join(unknown)}\n"
                         f"       this scene has: {have}")
    # De-dupe while keeping the order asked for; `--shot 2 --shot shot-02` is
    # one shot named twice, not two renders.
    seen, out = set(), []
    for shot in picked:
        if id(shot) not in seen:
            seen.add(id(shot))
            out.append(shot)
    return out


def _trim(keys: list[str], budget: int | None) -> list[str]:
    """Keep the NEWEST when there are more images than a model will take.

    The newest panels carry the current state of the scene; the oldest are the
    look everything already inherited. `frames.chain_keys` trims the same way and
    for the same reason.
    """
    if budget is None or budget <= 0 or len(keys) <= budget:
        return keys
    return keys[-budget:]


# --------------------------------------------------------------------------
# a panel
# --------------------------------------------------------------------------

def panel_slug(manifest: dict, shot: dict, panel: dict) -> str:
    return f"{manifest['slug']}-{shot['id']}-p{panel['n']}"


def panel_storyboard_key(manifest: dict, shot: dict, panel: dict, ext: str) -> str:
    project, _, scene_id = manifest["scene"].partition("/")
    return SC.scene_key(project, scene_id, "storyboard",
                        f"{shot['id']}-p{panel['n']}{ext}")


def earlier_panel_keys(manifest: dict, shot: dict, panel: dict) -> list[str]:
    """Every panel already on the board, up to this one, in board order."""
    out = []
    for a_shot, a_panel in SB.board_order(manifest):
        if a_shot is shot and a_panel is panel:
            break
        if a_panel.get("key"):
            out.append(a_panel["key"])
    return out


#: Format name -> the extension a video model will be asked to accept.
_FORMAT_EXT = {"jpg": ".jpg", "jpeg": ".jpeg", "png": ".png", "webp": ".webp"}

#: Smallest first. A panel is looked at once and then sent to a video model
#: several times, so its size is paid for repeatedly.
_FORMAT_PREFERENCE = ("jpg", "jpeg", "png", "webp")


def panel_format(panel_entry: dict, video_model: str) -> str | None:
    """The format to render a panel in, given the model that will consume it.

    Two rules, and the second is the one that costs money.

    A panel the video model cannot read is wasted outright — Kling rejects
    `.webp` and GPT Image writes `.webp` by default, so a whole board can be
    rendered in a format the shots it exists for cannot open.

    And among the formats that *are* accepted, the smallest wins. A PNG plate off
    these models runs ~2 MiB against ~0.3 MiB for the same picture as JPEG, and a
    panel is sent to a video model many times over its life. Kling's failure at
    around 14 MiB of images was a two-minute silence and a retryable-looking
    error, not a validation message, so the way to not meet it is to never get
    near it. Both halves are read from the registry — a model with different
    formats needs no edit here.
    """
    try:
        video_entry = REG.get(video_model)
    except REG.RegistryError:
        return None
    accepted = REG.accepts_ext(video_entry)
    if not accepted:
        return None
    allowed = ((panel_entry.get("snapshot") or {}).get("output_format") or {}).get("enum")
    allowed = allowed or list(_FORMAT_PREFERENCE)
    for fmt in _FORMAT_PREFERENCE:
        if fmt in allowed and _FORMAT_EXT[fmt] in accepted:
            return fmt
    return None


def panel_args(manifest: dict, shot: dict, panel: dict, entry: dict, opts) -> SimpleNamespace:
    """The namespace `runner`/`submit` expect, for one panel."""
    refs = panel.get("references") or {}
    d = SUB.defaults(entry["kind"])
    extra = dict(panel.get("extra") or {})
    project, _, _ = manifest["scene"].partition("/")

    video = (shot.get("motion") or {}).get("model")
    if "output_format" not in extra and video:
        fmt = panel_format(entry, video)
        if fmt:
            extra["output_format"] = fmt

    return SimpleNamespace(
        model=entry["key"],
        project=project,
        slug=panel_slug(manifest, shot, panel),
        prompt=SB.panel_prompt(manifest, panel),
        prompt_file=None, prompt_json=None, input_file=None,
        extra=json.dumps(extra) if extra else None,
        aspect_ratio=panel.get("aspect_ratio"),
        # Identity comes through `--character`, as it does everywhere else, so
        # the bible's described index chooses the subset. The earlier panels are
        # appended as explicit keys after it.
        key=[], character=tuple(refs.get("characters") or ()),
        record_characters=tuple(manifest.get("characters") or ()),
        record_extra={"scene": manifest["scene"], "scene_shot": shot["id"],
                      "scene_panel": panel["n"]},
        pick=refs.get("pick"), pick_tag=refs.get("pick_tag"), slots=None,
        image_run=None, ref_run=(), input_=(), input=(),
        start_run=None, start_key=None, end_run=None, end_key=None,
        no_refs=False, dry_run=opts.dry_run, json_=False, json=False,
        poll=True, dest=opts.dest, expires=opts.expires,
        interval=d["interval"], timeout=d["timeout"],
    )


def prepare_panel(s3, manifest: dict, shot: dict, panel: dict, opts):
    """Everything up to (not including) the submit, for one panel."""
    from studio_pipeline.engine import runner as RUN  # local: runner imports this module's peers

    model = panel.get("model")
    if not model:
        raise BoardError(f"{shot['id']} panel {panel['n']} names no model, and the "
                         f"scene sets no `panel_model` default.")
    try:
        entry = REG.get(model)
    except REG.RegistryError as exc:
        raise BoardError(str(exc))
    if entry["kind"] != "image":
        raise BoardError(f"a storyboard panel is a still, but {entry['key']} is a "
                         f"{entry['kind']} model.")
    if not (panel.get("prompt") or "").strip():
        raise BoardError(f"{shot['id']} panel {panel['n']} has no prompt.")

    args = panel_args(manifest, shot, panel, entry, opts)
    cap = REG.field(entry, "images.max_refs") or BOARD_REFS_DEFAULT
    # The board converges because each panel sees the ones before it. Trimmed to
    # the newest so a long board does not eventually exceed the model's cap —
    # `gather` would refuse rather than truncate, which is right, but a board
    # should not need hand-pruning to keep rendering.
    args.key = list(_trim(earlier_panel_keys(manifest, shot, panel), cap - 1))
    args.key += list((panel.get("references") or {}).get("keys") or [])

    try:
        bindings = SUB.gather(entry, s3, args)
    except (SUB.SubmitError, REFS.RefError, R.RunError) as exc:
        raise BoardError(f"{shot['id']} panel {panel['n']}: {exc}")
    payload = RUN.build_payload(entry, args)
    try:
        SUB.check_payload_rules(entry, payload)
    except SUB.SubmitError as exc:
        raise BoardError(f"{shot['id']} panel {panel['n']}: {exc}")
    return entry, args, payload, bindings


# --------------------------------------------------------------------------
# a shot
# --------------------------------------------------------------------------

def shot_bindings(s3, manifest: dict, shot: dict, entry: dict) -> tuple[str | None, str | None,
                                                                       list[str], list[str]]:
    """(start, end, reference keys, notes) — the whole role resolution, applied.

    Order is load-bearing: the demoted start panel first, then the remaining
    panels, then the scene's own frames. The panels are the instruction for THIS
    shot; the chain is context, and context goes last.
    """
    roles = SB.resolve_roles(shot)
    panels = roles["panels"]
    notes: list[str] = []

    def key_of(i: int) -> str:
        panel = panels[i]
        if not panel.get("key"):
            raise BoardError(
                f"{shot['id']} panel {panel['n']} has not been rendered yet — "
                f"studio scenes board {manifest['scene']} --shot {shot['id']}")
        return panel["key"]

    start = roles["handoff"]
    if start is None:
        # Falling back to the panel is right — a shot with a composed opening
        # frame can render without its predecessor. But a shot that SAID it
        # continues a movement and then quietly opened on a panel instead is
        # exactly the cut that turns out to jump, so it is said out loud even
        # though the render proceeds.
        if shot.get("continues"):
            fix = f"studio scenes handoff {manifest['scene']} --shot {shot['n']}"
            if roles["start_panel"] is None:
                # No handoff and no opening panel: the shot has nothing to start
                # from at all and would compose itself from references. That is
                # not a rough cut, it is a different shot.
                notes.append(
                    f"{shot['id']} continues the shot before it, has no handoff frame "
                    f"recorded and no opening panel — it would start from nothing and "
                    f"compose itself. Render the shot before it first, then: {fix}")
            else:
                notes.append(
                    f"{shot['id']} continues the shot before it but has no handoff frame "
                    f"recorded, so it will open on its own panel and the cut may jump — "
                    f"{fix}")
        if roles["start_panel"] is not None:
            start = key_of(roles["start_panel"])

    end = key_of(roles["end_panel"]) if roles["end_panel"] is not None else None
    refs = [key_of(i) for i in roles["reference_panels"]]
    if roles["demoted"]:
        notes.append(f"{shot['id']} panel 1 is a reference, not the start frame — "
                     f"the previous shot's last frame opens this one, so the cut "
                     f"is seamless")

    motion_refs = (shot.get("motion") or {}).get("references") or {}
    # The scene's own frames, read off the plan rather than out of a second
    # document kept in sync beside it. The start frame is already bound, so it
    # is not sent twice.
    refs += [k for k in SB.scene_frames(manifest, motion_refs.get("max_scene_frames"))
             if k != start and k not in refs]
    refs += list(motion_refs.get("keys") or [])

    # Some models take a start frame and references together, but refuse both
    # once an END frame joins them. A shot that brackets itself with two
    # approved compositions has already said everything the references would
    # have said, so the references are what give way — silently would be wrong,
    # hence the note, and the payload shown for approval is the trimmed one.
    if end and REG.field(entry, "images.end_excludes_refs") and refs:
        notes.append(f"{shot['id']}: {len(refs)} reference(s) dropped — {entry['key']} "
                     f"takes a start and an end frame together and nothing else. The two "
                     f"frames already fix the look at both ends of the shot.")
        refs = []

    cap = REG.field(entry, "images.max_refs")
    if cap:
        # The start and end frames may or may not count toward the cap; the
        # registry says which, and `submit` enforces it. Leaving room here is
        # what turns a refusal into a render.
        if REG.field(entry, "images.start_counts_toward_max_refs"):
            cap -= sum(1 for f in (start, end) if f)
        trimmed = _trim(refs, cap)
        if len(trimmed) != len(refs):
            notes.append(f"{shot['id']}: {len(refs) - len(trimmed)} older reference(s) "
                         f"dropped to fit {entry['key']}'s {REG.field(entry, 'images.max_refs')}")
        refs = trimmed
    return start, end, refs, notes


def shot_args(manifest: dict, shot: dict, entry: dict, opts) -> SimpleNamespace:
    motion = shot.get("motion") or {}
    refs = motion.get("references") or {}
    d = SUB.defaults(entry["kind"])
    extra = dict(motion.get("extra") or {})
    if motion.get("duration") is not None:
        extra.setdefault("duration", motion["duration"])
    project, _, _ = manifest["scene"].partition("/")
    return SimpleNamespace(
        model=entry["key"],
        project=project,
        slug=f"{manifest['slug']}-{shot['id']}",
        prompt=motion.get("prompt"),
        prompt_file=None, prompt_json=None, input_file=None,
        extra=json.dumps(extra) if extra else None,
        aspect_ratio=motion.get("aspect_ratio"),
        key=[],
        # Empty UNLESS the plan asks for it. The default is to send the scene's
        # own frames and nothing else, because a curated set was shot in another
        # context and pulls the render toward it. But that cuts both ways: a
        # scene built only from its own frames inherits whatever it has drifted
        # into, shot after shot, and nothing pulls it back. A plan that names
        # characters in `motion.references` is choosing identity stability over
        # scene-specific framing, and it is a real choice with a real cost —
        # measured: references hold the build and the body hair steady, and lose
        # you the wardrobe and set particulars of the start frame.
        character=tuple(refs.get("characters") or ()),
        record_characters=tuple(manifest.get("characters") or ()),
        record_extra={"scene": manifest["scene"], "scene_shot": shot["id"]},
        pick=refs.get("pick"), pick_tag=refs.get("pick_tag"), slots=None,
        image_run=None, ref_run=(), input_=(), input=(),
        start_run=None, start_key=None, end_run=None, end_key=None,
        no_refs=False, dry_run=opts.dry_run, json_=False, json=False,
        poll=True, dest=opts.dest, expires=opts.expires,
        interval=d["interval"], timeout=d["timeout"],
    )


def prepare_shot(s3, manifest: dict, shot: dict, opts):
    """Everything up to (not including) the submit, for one shot's video."""
    from studio_pipeline.engine import runner as RUN

    model = (shot.get("motion") or {}).get("model")
    if not model:
        raise BoardError(f"{shot['id']} names no model, and the scene sets no default.")
    try:
        entry = REG.get(model)
    except REG.RegistryError as exc:
        raise BoardError(str(exc))
    if entry["kind"] != "video":
        raise BoardError(f"a shot is a clip, but {entry['key']} is a {entry['kind']} model.")
    if not ((shot.get("motion") or {}).get("prompt") or "").strip():
        raise BoardError(f"{shot['id']} has no motion prompt.")

    args = shot_args(manifest, shot, entry, opts)
    start, end, refs, notes = shot_bindings(s3, manifest, shot, entry)
    args.start_key, args.end_key, args.key = start, end, refs

    try:
        bindings = SUB.gather(entry, s3, args)
    except (SUB.SubmitError, REFS.RefError, R.RunError) as exc:
        raise BoardError(f"{shot['id']}: {exc}")
    payload = RUN.build_payload(entry, args)
    try:
        SUB.check_payload_rules(entry, payload)
    except SUB.SubmitError as exc:
        raise BoardError(f"{shot['id']}: {exc}")
    return entry, args, payload, bindings, notes


# --------------------------------------------------------------------------
# seeing what is actually being sent
# --------------------------------------------------------------------------

def review_sheet(s3, manifest: dict, label: str, items: list[tuple[str, str]],
                 out_dir: str | None, cache: dict) -> str:
    """A labelled contact sheet of the images one payload binds.

    Separate from the shoot's version because the caption carries the image's
    ROLE, not just its position: for a shot, whether a picture is the start
    frame, the end frame or a reference is the thing most worth checking before
    paying, and `[Image3]` does not say.

    **It is uploaded into the scene, not merely written to disk.** A review sheet
    is the thing someone looks at to decide whether to spend money, and a local
    path is no use to anyone who is not sitting at the machine that made it —
    which, when the pipeline is driven remotely, is nobody. In the scene's own
    `review/` folder it is browsable in the app, it outlives the working
    directory, and it sits beside the panels it was built from. `--review-sheet
    DIR` still keeps a local copy for whoever IS at that machine.
    """
    tmp = out_dir or tempfile.mkdtemp(prefix="review-")
    os.makedirs(tmp, exist_ok=True)
    paths, captions = [], []
    for key, caption in items:
        local = cache.get(key)
        if local is None:
            local = os.path.join(tmp, f"src-{len(cache)}-{os.path.basename(key)}")
            store.download(key, pathlib.Path(local))
            cache[key] = local
        paths.append(local)
        captions.append(caption)
    out = SHEET.build(paths, os.path.join(tmp, f"{label}.png"),
                      cols=min(len(paths), 5), cell=320, captions=captions, quiet=True)

    project, _, scene_id = manifest["scene"].partition("/")
    key = SC.scene_key(project, scene_id, "review", f"{label}.png")
    store.upload(key, pathlib.Path(out), content_type="image/png")
    return key if out_dir is None else f"{key}\n       (local copy: {out})"


def _sheet_items(entry: dict, bindings: dict) -> list[tuple[str, str]]:
    images = entry.get("images") or {}
    items = []
    for field, role in ((images.get("start"), "start frame"), (images.get("end"), "end frame")):
        if field and bindings.get(field):
            items.append((bindings[field], f"[{role}] {os.path.basename(bindings[field])}"))
    for i, key in enumerate(bindings.get(images.get("refs")) or [], 1):
        items.append((key, f"[Image{i}] {os.path.basename(key)}"))
    return items


def _resolve(ref: str, project: str | None):
    s3 = s3c.client()
    owner, sid = SC.resolve_scene(s3, ref, project)
    manifest = SC.read_manifest(s3, owner, sid)
    if not manifest:
        raise BoardError(f"no scene.json for {owner}/{sid}")
    return s3, owner, sid, manifest


# --------------------------------------------------------------------------
# check — would this plan fly? nothing bills
# --------------------------------------------------------------------------

def run_check(ref: str, opts) -> int:
    """Build every payload and report every refusal, together.

    The cheap pass. A plan that a model will reject is better found here than
    between two paid renders, and a whole board can be planned wrong in one way —
    so the refusals are collected rather than raised one at a time.
    """
    s3, _owner, _sid, manifest = _resolve(ref, opts.project)
    shots = select_shots(manifest, tuple(opts.shot or ()))
    token = RA.load_token()
    problems: list[str] = []
    notes: list[str] = []
    ok = 0

    for shot in shots:
        for panel in shot.get("panels") or []:
            if SB.is_supplied(panel) or (panel.get("key") and not panel.get("stale")):
                continue
            try:
                entry, _args, payload, bindings = prepare_panel(s3, manifest, shot, panel, opts)
                SUB.preflight(entry, payload, bindings, token)
                ok += 1
            except (BoardError, MS.SchemaError) as exc:
                problems.append(str(exc))
        try:
            entry, _args, payload, bindings, shot_notes = prepare_shot(s3, manifest, shot, opts)
            SUB.preflight(entry, payload, bindings, token)
            notes += shot_notes
            ok += 1
        except (BoardError, MS.SchemaError) as exc:
            problems.append(str(exc))

    for note in notes:
        print(f"note: {note}", file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(f"{ok} payload(s) would be accepted as planned.")
    return 0


# --------------------------------------------------------------------------
# board — the panels
# --------------------------------------------------------------------------

def run_board(ref: str, opts) -> int:
    s3, owner, sid, manifest = _resolve(ref, opts.project)
    shots = select_shots(manifest, tuple(opts.shot or ()))

    wanted = []
    for shot in shots:
        for panel in shot.get("panels") or []:
            if opts.panel and panel["n"] not in opts.panel:
                continue
            # A supplied panel is an image the plan pinned, not something to
            # render — there is nothing to make, and --redo cannot make it.
            if SB.is_supplied(panel):
                continue
            if panel.get("key") and not (opts.redo or panel.get("stale")):
                continue
            wanted.append((shot, panel))
    if not wanted:
        print(f"{manifest['scene']} is already boarded — pass --redo to render a "
              f"panel again.", file=sys.stderr)
        return 0

    token = RA.load_token()

    # Prepared one at a time rather than all up front, because a panel's inputs
    # include the panels before it — which for a fresh board do not exist yet.
    # The whole-batch preflight `shoot` can do is not available here; each panel
    # is checked immediately before its own submit instead.
    print(f"{manifest['scene']}: {len(wanted)} panel(s) to render", file=sys.stderr)
    sheet_cache: dict[str, str] = {}
    prepared = []
    for shot, panel in wanted:
        entry, args, payload, bindings = prepare_panel(s3, manifest, shot, panel, opts)
        try:
            SUB.preflight(entry, payload, bindings, token)
        except MS.SchemaError as exc:
            raise BoardError(f"{shot['id']} panel {panel['n']} would be refused by "
                             f"{entry['key']}:\n{exc}")
        prepared.append((shot, panel, entry, args, payload, bindings))

        # GATE 1 — the payload, in full, before anything bills.
        run = f"{owner}/{R.new_run_id(args.slug)}"
        print(f"\n===== {shot['id']} panel {panel['n']}  ->  a storyboard panel =====")
        print(SUB.render(entry, run, payload, bindings, False))
        sheet = review_sheet(s3, manifest, f"{shot['id']}-p{panel['n']}",
                             _sheet_items(entry, bindings), opts.review_sheet, sheet_cache)
        print(f"===== IMAGES — what this panel sends =====\n{sheet}")

    if opts.dry_run:
        print(f"\n(dry run — {len(prepared)} panel(s) rendered, nothing submitted, "
              f"nothing billed)", file=sys.stderr)
        return 0

    # No `--yes`. A person reads the payloads above and answers this, or nothing
    # is submitted: an approval flag is the door an agent walks through while
    # believing some earlier exchange counted as consent.
    if not click.confirm(f"\nsubmit {len(prepared)} panel generation(s) for "
                         f"{manifest['scene']}?", default=False):
        print("nothing submitted.", file=sys.stderr)
        return 1

    boarded: dict[str, str] = {}
    failed: list[tuple[str, str]] = []
    for shot, panel, entry, args, payload, bindings in prepared:
        label = f"{shot['id']} p{panel['n']}"
        print(f"\n----- {label} -----", file=sys.stderr)
        try:
            code = SUB.execute(entry, payload, bindings, s3, token, args)
            if code != 0:
                raise SUB.SubmitError(f"exited {code}")
        except (SUB.SubmitError, RA.ReplicateError) as exc:
            print(f"  FAILED — {exc}", file=sys.stderr)
            failed.append((label, str(exc)))
            continue
        _p, run_id = R.resolve_run(f"{owner}/latest", owner)
        outs = R.run_outputs(owner, run_id)
        if not outs:
            failed.append((label, "the run recorded no output"))
            continue
        src = outs[0]
        dest = panel_storyboard_key(manifest, shot, panel, os.path.splitext(src)[1])
        # The run keeps its own output; the board holds a copy of the panel as it
        # was when approved. This was a server-side CopyObject and is now a read
        # and a write through the API, so the bytes travel through this process —
        # see `store.copy`. A shared blob would have been cheaper and is #334's
        # hazard, not this one's.
        store.copy(src, dest, content_type="image/png")
        panel.update(run=f"{owner}/{run_id}", source_key=src, key=dest,
                     boarded=R._now(), stale=False)
        SC.write_manifest(s3, manifest)
        boarded[label] = dest

    # GATE 2 — the board exists; nothing is animated yet.
    print(json.dumps({"scene": manifest["scene"], "boarded": boarded,
                      "failed": dict(failed), "rendered": None}, indent=2))
    if failed:
        print(f"\n{len(failed)} panel(s) FAILED:", file=sys.stderr)
        for label, why in failed:
            print(f"  {label}: {why}", file=sys.stderr)
    if boarded:
        print(f"\nlook at the board, then render a shot:\n"
              f"  studio scenes sheet {manifest['scene']}\n"
              f"  studio scenes render {manifest['scene']} --shot 1", file=sys.stderr)
    return 1 if failed else 0


# --------------------------------------------------------------------------
# render — one shot's video
# --------------------------------------------------------------------------

def run_render(ref: str, opts) -> int:
    s3, owner, sid, manifest = _resolve(ref, opts.project)
    shots = select_shots(manifest, tuple(opts.shot))
    token = RA.load_token()

    prepared, notes = [], []
    for shot in shots:
        entry, args, payload, bindings, shot_notes = prepare_shot(s3, manifest, shot, opts)
        try:
            SUB.preflight(entry, payload, bindings, token)
        except MS.SchemaError as exc:
            raise BoardError(f"{shot['id']} would be refused by {entry['key']}:\n{exc}")
        prepared.append((shot, entry, args, payload, bindings))
        notes += shot_notes

    for note in notes:
        print(f"note: {note}", file=sys.stderr)

    # GATE 1
    sheet_cache: dict[str, str] = {}
    for shot, entry, args, payload, bindings in prepared:
        run = f"{owner}/{R.new_run_id(args.slug)}"
        print(f"\n===== {shot['id']}  ->  a shot of {manifest['scene']} =====")
        print(SUB.render(entry, run, payload, bindings, False))
        sheet = review_sheet(s3, manifest, shot["id"], _sheet_items(entry, bindings),
                             opts.review_sheet, sheet_cache)
        print(f"===== IMAGES — what {shot['id']} actually sends =====\n{sheet}")

    if opts.dry_run:
        print(f"\n(dry run — {len(prepared)} shot(s) rendered, nothing submitted, "
              f"nothing billed)", file=sys.stderr)
        return 0

    if not click.confirm(f"\nsubmit {len(prepared)} shot generation(s) for "
                         f"{manifest['scene']}?", default=False):
        print("nothing submitted.", file=sys.stderr)
        return 1

    rendered: dict[str, str] = {}
    failed: list[tuple[str, str]] = []
    for shot, entry, args, payload, bindings in prepared:
        print(f"\n----- {shot['id']} -----", file=sys.stderr)
        try:
            code = SUB.execute(entry, payload, bindings, s3, token, args)
            if code != 0:
                raise SUB.SubmitError(f"exited {code}")
        except (SUB.SubmitError, RA.ReplicateError) as exc:
            print(f"  FAILED — {exc}", file=sys.stderr)
            failed.append((shot["id"], str(exc)))
            continue
        _p, run_id = R.resolve_run(f"{owner}/latest", owner)
        shot.update(run=f"{owner}/{run_id}", runref=f"{owner}/{run_id}#1",
                    rendered=R._now())
        SC.write_manifest(s3, manifest)
        rendered[shot["id"]] = f"{owner}/{run_id}#1"

    # GATE 2 — never assemble on its own. Cutting is a decision about the whole
    # scene, and it is made after looking at the shot, not as a side effect of
    # having rendered one.
    print(json.dumps({"scene": manifest["scene"], "rendered": rendered,
                      "failed": dict(failed), "assembled": None}, indent=2))
    if failed:
        print(f"\n{len(failed)} shot(s) FAILED:", file=sys.stderr)
        for shot_id, why in failed:
            print(f"  {shot_id}: {why}", file=sys.stderr)
    for shot_id, runref in rendered.items():
        n = next(s["n"] for s in shots if s["id"] == shot_id)
        print(f"\n{shot_id}: look at it, then carry it forward:\n"
              f"  studio frames grid {runref.split('#')[0]}\n"
              f"  studio scenes handoff {manifest['scene']} --shot {n + 1}",
              file=sys.stderr)
    return 1 if failed else 0


# --------------------------------------------------------------------------
# CLI — attached onto the `scenes` group from cli.py
# --------------------------------------------------------------------------

SHARED = [
    click.option("--dest", help="also keep a local copy of each result"),
    click.option("--dry-run", is_flag=True,
                 help="show every payload for approval; submit nothing, bill nothing"),
    click.option("--expires", type=int, default=3600, help="Presign expiry (default 3600)."),
    click.option("--project", help="project, when the sceneref does not carry one"),
    click.option("--review-sheet",
                 help=("also keep a local copy of each payload's contact sheet here. "
                       "The sheet is uploaded into the scene either way.")),
]


def with_shared(fn):
    for option in reversed(SHARED):
        fn = option(fn)
    return fn


@click.command("board", epilog="\n\nArguments:\n  REF  <project>/<slug>")
@click.argument("ref", required=True)
@with_shared
@click.option("--panel", multiple=True, type=int, help="only this panel number, within each shot")
@click.option("--redo", is_flag=True, help="render a panel again even though it exists")
@click.option("--shot", multiple=True, help="only this shot, by number or id. Repeatable.")
@reports(BoardError, SB.PlanError, P.PathError, MS.SchemaError)
def cmd_board(ref, **kw):
    """`studio scenes board` — render the storyboard panels."""
    raise SystemExit(run_board(ref, SimpleNamespace(**kw)))


@click.command("render", epilog="\n\nArguments:\n  REF  <project>/<slug>")
@click.argument("ref", required=True)
@with_shared
@click.option("--shot", multiple=True, required=True,
              help="the shot to render, by number or id. Repeatable, and required.")
@reports(BoardError, SB.PlanError, P.PathError, MS.SchemaError)
def cmd_render(ref, **kw):
    """`studio scenes render` — render a shot's video from the plan."""
    raise SystemExit(run_render(ref, SimpleNamespace(**kw)))


@click.command("check", epilog="\n\nArguments:\n  REF  <project>/<slug>")
@click.argument("ref", required=True)
@with_shared
@click.option("--shot", multiple=True, help="only this shot, by number or id. Repeatable.")
@reports(BoardError, SB.PlanError, P.PathError, MS.SchemaError)
def cmd_check(ref, **kw):
    """`studio scenes check` — would this plan be accepted? Nothing bills."""
    kw["dry_run"] = True
    raise SystemExit(run_check(ref, SimpleNamespace(**kw)))
