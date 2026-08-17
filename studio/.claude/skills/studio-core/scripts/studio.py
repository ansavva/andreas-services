# /// script
# requires-python = ">=3.13"
# dependencies = ["boto3"]
# ///
"""studio.py — invoke ANY registered Replicate model, image or video.

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

  uv run studio.py models                          # the registry
  uv run studio.py models show gpt-image-2         # entry + LIVE schema
  uv run studio.py models refresh                  # re-snapshot enums

  uv run studio.py run --model gpt-image-2 --project <project> \
      --prompt "..." --character <name> --pick-tag face --slug <slug> --dry-run

  uv run studio.py run --model kling --project <project> --input-file input.json \
      --character <name> --start-run <project>/latest#1 --slug <slug> --poll

`--dry-run` renders the payload for approval and submits nothing. Nothing bills
without it having been shown first.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "s3", "scripts")))

import model_schema as MS  # noqa: E402
import projects as PROJ  # noqa: E402
import refs as REFS  # noqa: E402
import registry as REG  # noqa: E402
import replicate_api as RA  # noqa: E402
import runs as R  # noqa: E402
import s3_common as s3c  # noqa: E402
import submit as SUB  # noqa: E402

die = RA.die


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------

def cmd_models(args) -> int:
    entries = REG.all()
    if args.json:
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


def cmd_models_show(args) -> int:
    try:
        entry = REG.get(args.model)
    except REG.RegistryError as e:
        die(str(e))
    token = RA.load_token()
    try:
        props, schemas = MS.fetch(entry["model"], token)
    except MS.SchemaError as e:
        die(str(e))

    if args.json:
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


def cmd_models_refresh(args) -> int:
    token = RA.load_token()
    targets = [args.model] if args.model else list(REG.all())
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


def cmd_run(args) -> int:
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

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("models", help="List every registered model.")
    msub = p.add_subparsers(dest="sub")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_models)

    q = msub.add_parser("show", help="One model: registry entry + LIVE input schema.")
    q.add_argument("model")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_models_show)

    q = msub.add_parser("refresh", help="Re-snapshot schema enums into models.json.")
    q.add_argument("model", nargs="?", help="Default: every model.")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_models_refresh)

    p = sub.add_parser("run", help="Submit a prediction as a recorded run.")
    p.add_argument("--model", required=True,
                   help="REQUIRED registry key. See `models` — the engines are peers.")
    p.add_argument("--prompt", help="The prompt.")
    p.add_argument("--prompt-file", help="Read the prompt from a file instead.")
    p.add_argument("--input-file",
                   help="JSON: the Replicate `input` object WITHOUT image fields.")
    p.add_argument("--prompt-json", help="studio-prompt source, stored as prompt.json.")
    p.add_argument("--project", help="REQUIRED. The project this run belongs to. "
                                     "`projects.py list` shows what exists.")
    p.add_argument("--character", action="append",
                   help="A character supplying identity. Repeatable — one piece of "
                        "work can involve several.")
    p.add_argument("--pick", help="Comma-separated reference files (or stems) from the "
                                  "character's index.")
    p.add_argument("--pick-tag", help="Comma-separated tags; an image must carry ALL of them.")
    p.add_argument("--slots", help="Comma-separated positions WITHIN the resolved selection.")
    p.add_argument("--ref-run", action="append",
                   help="An earlier run's output as reference material. Repeatable.")
    p.add_argument("--image-run", help="An earlier run's output as the image being edited.")
    p.add_argument("--input", type=int, action="append", metavar="N",
                   help="Image number from the PROJECT's input pool. Repeatable.")
    p.add_argument("--key", action="append", help="Explicit S3 key. Repeatable.")
    p.add_argument("--start-run", help="An earlier run's output as the first frame (video).")
    p.add_argument("--start-key", help="Explicit S3 key as the first frame (video).")
    p.add_argument("--end-run", help="An earlier run's output as the last frame (video).")
    p.add_argument("--end-key", help="Explicit S3 key as the last frame (video).")
    p.add_argument("--no-refs", action="store_true",
                   help="Deliberately generate with no image inputs.")
    p.add_argument("--aspect-ratio", help="Model-dependent; validated against the live schema.")
    p.add_argument("--extra", help="JSON object of model-specific inputs.")
    p.add_argument("--slug", default=None, help="Short slug for the run id and filename.")
    p.add_argument("--dest", help="Also keep a local copy in this directory.")
    p.add_argument("--expires", type=int, default=3600, help="Presign expiry (default 3600).")
    p.add_argument("--poll", action="store_true",
                   help="Video only: wait and archive. Images always wait.")
    p.add_argument("--interval", type=int, default=None, help="Poll interval seconds.")
    p.add_argument("--timeout", type=int, default=None, help="Give up after N seconds.")
    p.add_argument("--dry-run", action="store_true",
                   help="Show the payload for approval; submit nothing, bill nothing.")
    p.add_argument("--json", action="store_true",
                   help="With --dry-run, emit raw JSON instead of the readable review.")
    p.set_defaults(func=cmd_run)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
