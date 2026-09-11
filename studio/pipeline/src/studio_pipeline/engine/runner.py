"""`studio run` — invoke ANY registered Replicate model, image or video.

One runner over the model registry (`models.json`). `--model` takes any
registry key; the entry decides which image fields exist, what the caps are,
and which values the model will refuse. There is deliberately no default model:
the engines are peers, chosen per shot.

Every submission is recorded as a RUN ROW — its project, model, status,
timings, the characters it used and the node ids it bound — with the provider's
own request and response kept beside it as documents studio stores and never
decodes. The bytes land in the run's own folder. `--project` is REQUIRED and
never inferred: where output lands is the one thing rerunning a command cannot
undo. Nothing is ever uploaded to Replicate: assets reach it only as short-lived
presigned URLs minted at submit time.

  studio models                          # the registry
  studio models show gpt-image-2         # entry + LIVE schema
  studio models refresh                  # re-snapshot enums

  studio run --model gpt-image-2 --project <project> \
      --prompt "..." --character <name> --pick-tag face --name <file> --dry-run

  studio run --model kling --project <project> --input-file input.json \
      --character <name> --start-run <project>/latest#1 --name <file> --poll

`--dry-run` renders the payload for a person to read and submits nothing. Nothing bills
without it having been shown first.
"""

import json
import sys
from types import SimpleNamespace

import click

from studio_pipeline.domain import projects as PROJ
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import add_model as AM
from studio_pipeline.engine import refs as REFS
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import registry_file as RF
from studio_pipeline.engine import schema as MS
from studio_pipeline.engine import submit as SUB

# `errors.die`, not a copy re-exported from the HTTP adapter — see
# `errors.die`'s docstring for the nine that used to exist.
from studio_pipeline.errors import die  # noqa: E402


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------

@click.group(help=__doc__)
def main():
    pass


@main.group("models", invoke_without_command=True)
@click.option("--json", "json_", is_flag=True)
@click.pass_context
def cmd_models(ctx, json_):
    if ctx.invoked_subcommand is not None:
        return None
    entries = REG.all()
    if json_:
        print(json.dumps(entries, indent=2))
        return 0
    for kind in ("image", "video"):
        rows = {k: v for k, v in entries.items() if v.get("kind") == kind}
        if not rows:
            continue
        print(f"\n{kind.upper()}")
        for key, e in rows.items():
            imgs = e.get("images") or {}
            cap = imgs.get("max_refs")
            field = imgs.get("refs")
            print(f"  {key:<16} {e['model']:<32} {field}{f' (≤{cap})' if cap else ''}")
            print(f"  {'':<16} {e.get('note', '')}")
    print()
    return 0


@cmd_models.command("show")
@click.argument("model", required=True)
@click.option("--json", "json_", is_flag=True)
def cmd_models_show(model, json_):
    try:
        entry = REG.get(model)
    except REG.RegistryError as e:
        die(str(e))
    try:
        props, schemas = MS.fetch(entry["model"])
    except MS.SchemaError as e:
        die(str(e))

    if json_:
        print(json.dumps({"entry": entry, "schema": props}, indent=2))
        return 0

    print(f"===== {entry['key']}  —  {entry['model']} =====")
    print(f"kind    {entry['kind']}")
    print(f"skill   {entry['skill']}")
    print(f"note    {entry.get('note', '')}")
    imgs = entry.get("images") or {}
    if imgs.get("refs"):
        cap = imgs.get("max_refs")
        print(f"images  {imgs['refs']}{f' (≤{cap})' if cap else ' (no documented cap)'}"
              f"   accepts {' '.join(sorted(REG.accepts_ext(entry)))}")
    if imgs.get("start"):
        print(f"frames  first={imgs['start']}  last={imgs['end']}"
              + ("   (mutually exclusive with references)" if imgs.get("start_excludes_refs") else ""))
    for field, blocked in (entry.get("denied") or {}).items():
        for value, why in blocked.items():
            print(f"CAVEAT  {field}={value!r} is rejected locally — {why}")

    print("\n----- live input schema -----")
    for k in sorted(props, key=lambda k: props[k].get("x-order", 99)):
        spec = props[k]
        allowed = MS.enum_of(spec, schemas)
        bits = []
        if allowed:
            bits.append(f"enum={allowed}")
        if spec.get("minimum") is not None or spec.get("maximum") is not None:
            bits.append(f"range=[{spec.get('minimum')}, {spec.get('maximum')}]")
        if spec.get("default") is not None:
            bits.append(f"default={spec['default']!r}")
        print(f"  {k:<22} {'  '.join(bits)}")
    return 0


@cmd_models.command("refresh", epilog="\n\nArguments:\n  MODEL  Default: every model.")
@click.argument("model", required=False)
@click.option("--json", "json_", is_flag=True)
def cmd_models_refresh(model, json_):
    targets = [model] if model else list(REG.all())
    import datetime as dt
    for name in targets:
        entry = REG.get(name)
        try:
            props, schemas = MS.fetch(entry["model"])
        except MS.SchemaError as e:
            print(f"  {name}: SKIPPED — {e}", file=sys.stderr)
            continue
        snap = MS.snapshot(props, schemas)
        snap["refreshed"] = dt.date.today().isoformat()
        RF.save_snapshot(entry["key"], snap)
        print(f"  {entry['key']:<16} {len(snap) - 1} fields snapshotted")
    return 0


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def build_payload(entry: dict, args) -> dict:
    payload: dict = {}
    if getattr(args, "input_file", None):
        payload = json.load(open(args.input_file))
        if not isinstance(payload, dict):
            die("--input-file must contain a JSON object.")

    prompt = None
    if getattr(args, "prompt_file", None):
        prompt = open(args.prompt_file).read().strip()
    elif getattr(args, "prompt", None):
        prompt = args.prompt
    if prompt:
        payload["prompt"] = prompt

    # Not every model has a prompt. An upscaler takes an image and settings and
    # nothing else, and its registry entry records that as `"prompt": null` —
    # so demanding one here made it unrunnable: the only payload the CLI would
    # build was the one the model's own schema rejected.
    if entry.get("prompt") is None:
        if payload.get("prompt"):
            die(f"{entry['key']} takes no prompt — drop --prompt/--prompt-file.")
    elif not payload.get("prompt"):
        die("a prompt is required — pass --prompt, --prompt-file, "
            "or an --input-file containing one.")

    if args.extra:
        try:
            extra = json.loads(args.extra)
        except json.JSONDecodeError as e:
            die(f"--extra is not valid JSON: {e}")
        if not isinstance(extra, dict):
            die("--extra must be a JSON object.")
        payload.update(extra)
    if args.aspect_ratio:
        payload["aspect_ratio"] = args.aspect_ratio

    # ── the registry's defaults, UNDER everything a caller asked for ──────────
    #
    # **Last in the function and first in precedence order**, which is the whole
    # of the rule: a default is what happens when nobody chose. `--extra`, an
    # `--input-file`, `--aspect-ratio` and `character turnaround`'s per-model
    # block have all had their say by now, and each of them keeps it.
    #
    # It is here rather than at the three call sites because there are three:
    # `studio run`, `scenes board` and `scenes render` all build their payload
    # through this function, and a default applied in one of them would be a
    # default the other two silently did not have.
    #
    # **They are visible, not implicit.** Whatever lands here is in the payload
    # `submit.render` prints and a person reads under hard rule #2 — so a
    # wrong default is something you read before you spend, not something you
    # discover on an invoice. That is what makes setting one safe at all.
    for field, value in REG.defaults(entry).items():
        payload.setdefault(field, value)

    # Never trust image fields baked into the payload — they are bound from S3.
    imgs = entry.get("images") or {}
    for f in (imgs.get("refs"), imgs.get("start"), imgs.get("end")):
        if f and f in payload:
            die(f"pass images via --character/--ref-run/--key (and --start-run "
                f"for a first frame), not in the payload as `{f}`.")
    return payload


def _ephemeral_entry(model: str) -> dict:
    """A registry entry for a model that is not in the registry, held in memory.

    Built by the same inference `studio add-model` proposes, off the same live
    schema, so a trial submission is validated, rendered for reading and
    recorded exactly like a registered one. Nothing is written to `models.json`
    — onboarding is still a deliberate act with a skill page attached, and this
    is the step BEFORE deciding whether that is worth doing.

    The guessed fields are the point of the warning: `accepts_ext` in particular
    is inferred from prose and is the one most likely to be wrong.
    """
    try:
        props, schemas = MS.fetch(model)
    except MS.SchemaError as e:
        die(str(e))
    if not props:
        die(f"{model} has no published input schema — cannot run it.")
    entry, _notes = AM.infer(model, props, schemas, AM.readme(model))
    entry["key"] = model
    print(f"note: {model} is not registered; running it off its live schema. "
          f"Fields are inferred rather than curated — `studio add-model {model}` "
          "proposes an entry to check.", file=sys.stderr)
    return entry


def _refuse_a_duplicate(record: dict, args) -> None:
    """Stop if this exact payload was already sent to this project. `--again` walks past.

    **A batch of 72 upscales was driven twice.** The harness reported the job
    finished when it had not, a second pass ran over the same list, ~46 images
    were generated again for about $2.30 and the results overwrote each other.
    Nothing anywhere noticed, because every send is the first one as far as a
    payload builder is concerned.

    This used to be `engine/ledger.py`, a per-machine file, because answering it
    from the run store meant one `GET /api/runs/<id>` per candidate — around 1800
    requests before the first submit of that batch. The API projects a
    fingerprint onto the listing row now, so it is one query, and it sees the two
    things a local file never could: a second machine, and a colleague.

    Checked after the draft exists rather than before, because the draft is what
    carries the fingerprint — see `submit.already_submitted` for why it is not
    recomputed here. A draft costs a row and no bytes, so the check is still
    free, and `--dry-run` gets the same refusal: that is the command people use
    to look over a batch before starting it.

    `--again` is a decision somebody makes rather than something a script does in
    silence. That was true of the ledger and it is true here.
    """
    if getattr(args, "again", False):
        return
    earlier = SUB.already_submitted(record)
    if not earlier:
        return
    die(f"this exact payload was already submitted to {args.project['name']} as "
        f"{earlier['id']} ({earlier.get('status')}, {earlier.get('created')}).\n"
        f"       Nothing has been sent. This attempt is draft {record['id']}.\n"
        "       To generate it again anyway: --again")


@main.command("run")
@click.option("--aspect-ratio", help="Model-dependent; validated against the live schema.")
@click.option("--character", multiple=True, help=("A character supplying identity. Repeatable — one piece of work "
              "can involve several."))
@click.option("--dest", help="Also keep a local copy in this directory.")
@click.option("--again", is_flag=True, help="Submit even though this exact payload was submitted before.")
@click.option("--dry-run", is_flag=True, help="Show the payload; submit nothing, bill nothing.")
@click.option("--end-key", help="Node id (or name path) of the last frame (video).")
@click.option("--end-run", help="An earlier run's output as the last frame (video).")
@click.option("--extra", help="JSON object of model-specific inputs.")
@click.option("--image-run", help="An earlier run's output as the image being edited.")
@click.option("--input", "input_", type=int, multiple=True, help="Image number from the PROJECT's input pool. Repeatable.")
@click.option("--input-file", help="JSON: the Replicate `input` object WITHOUT image fields.")
@click.option("--interval", type=int, help="Poll interval seconds.")
@click.option("--json", "json_", is_flag=True, help="With --dry-run, emit raw JSON instead of the readable review.")
@click.option("--key", multiple=True, help="Explicit node id (or name path). Repeatable.")
@click.option("--model", required=True, help="REQUIRED registry key. See `models` — the engines are peers.")
@click.option("--no-refs", is_flag=True, help="Deliberately generate with no image inputs.")
@click.option("--pick", help=("Comma-separated reference files (or stems) from the "
              "character's index."))
@click.option("--pick-tag", help="Comma-separated tags; an image must carry ALL of them.")
@click.option("--poll", is_flag=True, help="Video only: wait and archive. Images always wait.")
@click.option("--project", help=("REQUIRED. The project this run belongs to. `studio projects list` "
              "shows what exists."))
@click.option("--prompt", help="The prompt.")
@click.option("--prompt-file", help="Read the prompt from a file instead.")
@click.option("--prompt-json", help="studio-media-prompt source, stored as prompt.json.")
@click.option("--ref-run", multiple=True, help="An earlier run's output as reference material. Repeatable.")
@click.option("--slots", help="Comma-separated positions WITHIN the resolved selection.")
@click.option("--name", help="What the output file is called. Not an identity: "
                                     "a run is addressed by its id or by `latest`.")
@click.option("--start-key", help="Node id (or name path) of the first frame (video).")
@click.option("--start-run", help="An earlier run's output as the first frame (video).")
@click.option("--timeout", type=int, help="Give up after N seconds.")
def cmd_run(**options):
    args = SimpleNamespace(**options)
    try:
        entry = REG.get(args.model)
    except REG.RegistryError as e:
        # **An `owner/name` that is not a registry key is read as a live model.**
        # Evaluating one before onboarding it had no supported path: the
        # alternative was calling Replicate outside the harness entirely, which
        # is how a four-way upscaler comparison ended up with no run records,
        # no schema validation and no payload render. A registry key never
        # contains a slash, so the two cannot be confused — and a typo like
        # `nano-bannana-pro` still fails here rather than reaching a provider.
        if "/" not in args.model:
            die(str(e))
        entry = _ephemeral_entry(args.model)
    d = SUB.defaults(entry["kind"])
    if getattr(args, "name", None) is None:
        args.name = d["slug"]
    if args.interval is None:
        args.interval = d["interval"]
    if args.timeout is None:
        args.timeout = d["timeout"]


    # Where a run lands is never guessed. It used to fall back to the character
    # name and then to a pseudo-character called `misc`, which is how output
    # ended up in three different places for one piece of work. Ask instead.
    #
    # `args.project` is the project RECORD from here down, not the name a person
    # typed. Everything below wants the id — a runref defaults against it and the
    # run row stores it — and resolving the name once here is what stops four
    # call sites doing it four times and disagreeing about which of two projects
    # sharing a name they meant.
    args.project = PROJ.require_project(args.project)

    payload = build_payload(entry, args)

    try:
        bindings = SUB.gather(entry, args)
        SUB.check_payload_rules(entry, payload)
    except (SUB.SubmitError, REFS.RefError, R.RunError) as e:
        die(str(e))

    if not bindings:
        if d["require_images"] and not args.no_refs:
            die("no image inputs. Pass --character / --ref-run / --image-run / --key, "
                "or --no-refs for a deliberate text-only generation.")
        if not d["require_images"]:
            print("warning: no images bound — a character video from a bare text "
                  "prompt will not stay on-model.", file=sys.stderr)

    try:
        SUB.preflight(entry, payload, bindings)
    except MS.SchemaError as e:
        die(str(e))

    if args.dry_run:
        # **A dry run now leaves a DRAFT, and that is the whole of its upgrade.**
        # It rendered a payload to a terminal and kept nothing, so the thing hard
        # rule #2 asks a person to read had no address: it could not be opened in
        # the app, linked to, or submitted later. The draft costs a row and no
        # bytes, bills nothing, is hidden from every listing, and is what
        # `studio runs submit` then acts on.
        #
        # `json_`, not `json` — `--json` cannot be a Python attribute name, so
        # Click was given the safe spelling and this line read the unsafe one.
        # It made `--dry-run` raise AttributeError, which is the command the
        # rule tells everyone to use before spending money.
        try:
            record = SUB.draft(entry, payload, bindings, args)
        except SUB.SubmitError as e:
            die(str(e))
        _refuse_a_duplicate(record, args)
        print(SUB.render(entry, record["id"], payload, bindings, args.json_))
        print(f"\ndraft {record['id']} — nothing submitted, nothing billed.\n"
              f"       submit it:   studio runs submit {record['id']}\n"
              f"       discard it:  studio runs discard {record['id']}",
              file=sys.stderr)
        return 0

    try:
        # `execute` returns the run record; a single generation has nothing left
        # to do with it, and the exit code a caller reads is success or `die`.
        SUB.execute(entry, payload, bindings, args,
                    on_drafted=lambda record: _refuse_a_duplicate(record, args))
    except SUB.SubmitError as e:
        die(str(e))
    # **Nothing to record afterwards any more.** The ledger had to be written
    # after the submit — a payload the provider refused was not paid for, and an
    # entry written ahead of the call would make the retry look like the
    # duplicate. The row IS the record now, and `already_submitted` ignores the
    # states that never billed, so the ordering problem does not exist.
    return 0


# --------------------------------------------------------------------------



