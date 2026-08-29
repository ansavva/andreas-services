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

`--dry-run` renders the payload for approval and submits nothing. Nothing bills
without it having been shown first.
"""

import json
import sys
from types import SimpleNamespace

import click

from studio_pipeline.adapters import replicate as RA
from studio_pipeline.domain import projects as PROJ
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import add_model as AM
from studio_pipeline.engine import ledger as LEDGER
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
    token = RA.load_token()
    try:
        props, schemas = MS.fetch(entry["model"], token)
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
    token = RA.load_token()
    targets = [model] if model else list(REG.all())
    import datetime as dt
    for name in targets:
        entry = REG.get(name)
        try:
            props, schemas = MS.fetch(entry["model"], token)
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
    schema, so a trial submission is validated, rendered for approval and
    recorded exactly like a registered one. Nothing is written to `models.json`
    — onboarding is still a deliberate act with a skill page attached, and this
    is the step BEFORE deciding whether that is worth doing.

    The guessed fields are the point of the warning: `accepts_ext` in particular
    is inferred from prose and is the one most likely to be wrong.
    """
    token = RA.load_token()
    try:
        props, schemas = MS.fetch(model, token)
    except MS.SchemaError as e:
        die(str(e))
    if not props:
        die(f"{model} has no published input schema — cannot run it.")
    entry, _notes = AM.infer(model, props, schemas, AM.readme(model, token))
    entry["key"] = model
    print(f"note: {model} is not registered; running it off its live schema. "
          f"Fields are inferred rather than curated — `studio add-model {model}` "
          "proposes an entry to check.", file=sys.stderr)
    return entry


@main.command("run")
@click.option("--aspect-ratio", help="Model-dependent; validated against the live schema.")
@click.option("--character", multiple=True, help=("A character supplying identity. Repeatable — one piece of work "
              "can involve several."))
@click.option("--dest", help="Also keep a local copy in this directory.")
@click.option("--again", is_flag=True, help="Submit even though this exact payload was submitted before.")
@click.option("--dry-run", is_flag=True, help="Show the payload for approval; submit nothing, bill nothing.")
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
        # no schema validation and no approval render. A registry key never
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

    token = RA.load_token()

    # Where a run lands is never guessed. It used to fall back to the character
    # name and then to a pseudo-character called `misc`, which is how output
    # ended up in three different places for one piece of work. Ask instead.
    #
    # `args.project` is the project RECORD from here down, not the slug a person
    # typed. Everything below wants the id — a runref defaults against it and the
    # run row stores it — and resolving the slug once here is what stops four
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
        SUB.preflight(entry, payload, bindings, token)
    except MS.SchemaError as e:
        die(str(e))

    # A LABEL for the approval render, not an id. A dry run replaces it with the
    # real one below, once the draft exists; a live submission renders under the
    # label because `execute` mints the record and submits in one act.
    run = f"{args.project['slug']}/{R.slugify(args.name)}"

    # **Has this exact submission already been paid for?** See `engine/ledger`
    # for what happened. Checked after preflight so a payload the model would
    # reject is reported as a schema fault rather than as a duplicate, and
    # before the dry run returns so `--dry-run` says it too — a dry run is the
    # thing people use to check a batch before starting it, and it is the
    # cheapest possible moment to find out.
    digest = LEDGER.fingerprint(entry["model"], payload, bindings)
    earlier = LEDGER.seen(args.project["id"], digest)
    if earlier and not args.again:
        die(f"this exact payload was already submitted to {args.project['slug']} "
            f"as {earlier['name']} ({earlier['run']}).\n"
            "       Nothing has been sent. To generate it again anyway: --again")

    if args.dry_run:
        # **A dry run now leaves a DRAFT, and that is the whole of its upgrade.**
        # It rendered a payload to a terminal and kept nothing, so the thing hard
        # rule #2 asks a person to read had no address: it could not be opened in
        # the app, linked to, or approved later. The draft costs a row and no
        # bytes, bills nothing, is hidden from every listing, and is what
        # `studio runs approve` then acts on.
        #
        # `json_`, not `json` — `--json` cannot be a Python attribute name, so
        # Click was given the safe spelling and this line read the unsafe one.
        # It made `--dry-run` raise AttributeError, which is the command the
        # approval rule tells everyone to use before spending money.
        try:
            record = SUB.draft(entry, payload, bindings, args)
        except SUB.SubmitError as e:
            die(str(e))
        print(SUB.render(entry, record["id"], payload, bindings, args.json_))
        print(f"\ndraft {record['id']} — nothing submitted, nothing billed.\n"
              f"       approve it:  studio runs approve {record['id']}\n"
              f"       discard it:  studio runs discard {record['id']}",
              file=sys.stderr)
        return 0

    try:
        # `execute` returns the run record; a single generation has nothing left
        # to do with it, and the exit code a caller reads is success or `die`.
        SUB.execute(entry, payload, bindings, token, args)
    except (SUB.SubmitError, RA.ReplicateError) as e:
        die(str(e))
    # AFTER the submit, never before: a payload the provider refused was not
    # paid for, and a ledger entry written ahead of the call would make the
    # retry look like the duplicate.
    LEDGER.record(args.project["id"], digest, run=run, name=args.name)
    return 0


# --------------------------------------------------------------------------



