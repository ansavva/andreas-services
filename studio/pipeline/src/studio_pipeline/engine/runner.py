"""`studio run` — invoke ANY registered Replicate model, image or video.

One runner over the model registry (`models.json`). `--model` takes any
registry key; the entry decides which image fields exist, what the caps are,
and which values the model will refuse. There is deliberately no default model:
the engines are peers, chosen per shot.

Every submission is recorded as a run under
`projects/<project>/runs/<run_id>/` — the prompt, the inputs as S3 KEYS, the
result, and the artifact. `--project` is REQUIRED and never inferred: where
output lands is the one thing rerunning a command cannot undo. Nothing is ever
uploaded to Replicate: assets reach it only as short-lived presigned URLs minted
at submit time.

  studio models                          # the registry
  studio models show gpt-image-2         # entry + LIVE schema
  studio models refresh                  # re-snapshot enums

  studio run --model gpt-image-2 --project <project> \
      --prompt "..." --character <name> --pick-tag face --slug <slug> --dry-run

  studio run --model kling --project <project> --input-file input.json \
      --character <name> --start-run <project>/latest#1 --slug <slug> --poll

`--dry-run` renders the payload for approval and submits nothing. Nothing bills
without it having been shown first.
"""

import json
import sys
from types import SimpleNamespace

import click

from studio_pipeline.adapters import replicate as RA
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.domain import projects as PROJ
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import refs as REFS
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import schema as MS
from studio_pipeline.engine import submit as SUB

die = RA.die


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
        REG.save_snapshot(entry["key"], snap)
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
    if not payload.get("prompt"):
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


@main.command("run")
@click.option("--aspect-ratio", help="Model-dependent; validated against the live schema.")
@click.option("--character", multiple=True, help=("A character supplying identity. Repeatable — one piece of work "
              "can involve several."))
@click.option("--dest", help="Also keep a local copy in this directory.")
@click.option("--dry-run", is_flag=True, help="Show the payload for approval; submit nothing, bill nothing.")
@click.option("--end-key", help="Explicit S3 key as the last frame (video).")
@click.option("--end-run", help="An earlier run's output as the last frame (video).")
@click.option("--expires", type=int, default=3600, help="Presign expiry (default 3600).")
@click.option("--extra", help="JSON object of model-specific inputs.")
@click.option("--image-run", help="An earlier run's output as the image being edited.")
@click.option("--input", "input_", type=int, multiple=True, help="Image number from the PROJECT's input pool. Repeatable.")
@click.option("--input-file", help="JSON: the Replicate `input` object WITHOUT image fields.")
@click.option("--interval", type=int, help="Poll interval seconds.")
@click.option("--json", "json_", is_flag=True, help="With --dry-run, emit raw JSON instead of the readable review.")
@click.option("--key", multiple=True, help="Explicit S3 key. Repeatable.")
@click.option("--model", required=True, help="REQUIRED registry key. See `models` — the engines are peers.")
@click.option("--no-refs", is_flag=True, help="Deliberately generate with no image inputs.")
@click.option("--pick", help=("Comma-separated reference files (or stems) from the "
              "character's index."))
@click.option("--pick-tag", help="Comma-separated tags; an image must carry ALL of them.")
@click.option("--poll", is_flag=True, help="Video only: wait and archive. Images always wait.")
@click.option("--project", help=("REQUIRED. The project this run belongs to. `projects.py list` "
              "shows what exists."))
@click.option("--prompt", help="The prompt.")
@click.option("--prompt-file", help="Read the prompt from a file instead.")
@click.option("--prompt-json", help="studio-prompt source, stored as prompt.json.")
@click.option("--ref-run", multiple=True, help="An earlier run's output as reference material. Repeatable.")
@click.option("--slots", help="Comma-separated positions WITHIN the resolved selection.")
@click.option("--slug", help="Short slug for the run id and filename.")
@click.option("--start-key", help="Explicit S3 key as the first frame (video).")
@click.option("--start-run", help="An earlier run's output as the first frame (video).")
@click.option("--timeout", type=int, help="Give up after N seconds.")
def cmd_run(**options):
    args = SimpleNamespace(**options)
    try:
        entry = REG.get(args.model)
    except REG.RegistryError as e:
        die(str(e))
    d = SUB.defaults(entry["kind"])
    if args.slug is None:
        args.slug = d["slug"]
    if args.interval is None:
        args.interval = d["interval"]
    if args.timeout is None:
        args.timeout = d["timeout"]

    token = RA.load_token()
    s3 = s3c.client()

    # Where a run lands is never guessed. It used to fall back to the character
    # name and then to a pseudo-character called `misc`, which is how output
    # ended up in three different places for one piece of work. Ask instead.
    args.project = PROJ.require_project(s3, args.project)

    payload = build_payload(entry, args)

    try:
        bindings = SUB.gather(entry, s3, args)
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

    run = f"{args.project}/{R.new_run_id(args.slug)}"
    if args.dry_run:
        print(SUB.render(entry, run, payload, bindings, args.json))
        return 0

    try:
        return SUB.execute(entry, payload, bindings, s3, token, args)
    except (SUB.SubmitError, RA.ReplicateError) as e:
        die(str(e))


# --------------------------------------------------------------------------



