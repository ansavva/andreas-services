"""`studio add-model` — onboard a Replicate model into the registry.

Reads BOTH the live input schema AND the README, because each catches what the
other misses. Real cases from this repo:

  * `openai/gpt-image-2`'s schema offers `background: "transparent"`; its README
    says transparent backgrounds are unsupported. The schema is too permissive,
    so that value must be recorded under `denied`.
  * The same README lists three aspect ratios where the schema has eighteen.
    There the docs are stale and the schema is right.

The rule that falls out, and that this script encodes: **the schema is
authoritative for what a field accepts, the docs for what the model actually
honours.** A human still has to read the caveats — inference cannot do that
part — so the proposed entry is printed for review and nothing is written
without `--write`.

  studio add-model openai/gpt-image-2              # propose, write nothing
  studio add-model openai/gpt-image-2 --write      # append to the registry

WHAT THIS DOES NOT DO
---------------------
It does not write the model's `SKILL.md`. It used to, from a format string held
here, and that was the wrong shape: the generated page was boilerplate around a
`TODO` comment asking a human for the only part worth reading — what the model
is good at, and which values its schema offers but it ignores. Meanwhile the
boilerplate rotted unread, and by August 2026 it was stamping a path that had
not existed for months into every newly onboarded model's documentation.

The irony was that this command already fetches the README those TODOs asked
someone to go and read. So it now prints what it learned and stops. The
`studio-media-add-model` skill writes the page, from this output and from the
fourteen existing model skills as models. Prose is authored where prose is
authored; no code in this package generates documentation.
"""

import json
import re
import sys

import click

from studio_pipeline.adapters import replicate as RA
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import schema as MS

# `errors.die`, not a copy re-exported from the HTTP adapter — see
# `errors.die`'s docstring for the nine that used to exist.
from studio_pipeline.errors import die  # noqa: E402

# Field names to look for, most specific first. The TYPE decides the role, not
# the name: a reference set is an array, a first/last frame is a single string.
# `image` means "the start frame" on Seedance and "the reference list" nowhere,
# so guessing from the name alone mislabels every video model.
REF_FIELDS = ["input_images", "image_input", "reference_images", "images", "image"]
START_FIELDS = ["image", "start_image", "first_frame_image", "first_frame"]
END_FIELDS = ["last_frame_image", "end_image", "last_frame"]
VIDEO_HINTS = ("duration", "fps", "generate_audio", "mode", "multi_prompt", "video")
EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif|bmp)\b", re.I)


def readme(model: str, token: str) -> str:
    """The model's prose docs. Returns "" when it has none — not fatal."""
    try:
        return RA.api_text(f"{RA.API_ROOT}/models/{model}/readme", token)
    except RA.ReplicateError:
        return ""


NEGATIVE_RE = re.compile(
    r"[^.\n]*\b(?:do(?:es)?n[’']?t support|does not support|not supported|"
    r"no knob|cannot|can[’']?t\b|unsupported|only supports)\b[^.\n]*\.", re.I)


def caveats(text: str, props: dict, schemas: dict) -> list[str]:
    """Surface README sentences that limit the model, for `denied` review.

    This is the half no schema can give you. `openai/gpt-image-2` publishes
    `background: "transparent"` in its schema while its README says transparent
    backgrounds are unsupported — a value that validates and is then ignored.
    Anything flagged here should be read and, where it names a value the schema
    still offers, recorded under `denied`.
    """
    if not text:
        return ["no README found — check the model page by hand for constraints "
                "the schema does not express."]
    out: list[str] = []
    enums = {v for k in props
             for v in (MS.enum_of(props[k], schemas) or []) if isinstance(v, str)}
    for m in NEGATIVE_RE.finditer(text):
        s = " ".join(m.group(0).split())
        if len(s) > 240:
            continue
        named = sorted(e for e in enums if re.search(rf"\b{re.escape(e)}\b", s))
        flag = f"  <-- names schema value(s) {named}; STRONG `denied` candidate" if named else ""
        out.append(f"README CAVEAT: {s}{flag}")
    if not out:
        out.append("README names no obvious limitation — still read it before trusting the entry.")
    return out


def infer(model: str, props: dict, schemas: dict, text: str) -> tuple[dict, list[str]]:
    """Propose a registry entry. Returns (entry, notes about what was guessed)."""
    notes: list[str] = []
    owner, name = model.split("/", 1)
    key = name

    kind = "video" if any(h in props for h in VIDEO_HINTS) else "image"
    notes.append(f"kind={kind} — inferred from the presence of {sorted(set(props) & set(VIDEO_HINTS)) or 'no video-ish fields'}")

    def is_array(f: str) -> bool:
        return props.get(f, {}).get("type") == "array"

    def is_scalar(f: str) -> bool:
        return f in props and props[f].get("type") == "string"

    refs = next((f for f in REF_FIELDS if is_array(f)), None)
    if not refs:
        notes.append("NO reference-image ARRAY found — this model takes at most a "
                     "single image, or is text-only; check by hand.")
    start = next((f for f in START_FIELDS if is_scalar(f) and f != refs), None)
    end = next((f for f in END_FIELDS if is_scalar(f)), None)
    if start:
        notes.append(f"start={start} — a single-image field, so read as a first frame, "
                     f"not a reference set.")

    # Caps and accepted formats are stated in prose, inside the REFERENCE
    # field's own description — not anywhere in the schema. Both regexes below
    # read `props[refs]` only. (A joined string of every field's description
    # used to be built here and never used; a cap named in some other field's
    # prose is not this field's cap, so the narrow read is the right one.)
    cap = None
    if refs:
        m = re.search(r"(?:up to|max(?:imum)?)\s+(\d+)", str(props[refs].get("description") or ""), re.I)
        if m:
            cap = int(m.group(1))
            notes.append(f"max_refs={cap} — parsed from the `{refs}` description")
        else:
            notes.append(f"max_refs=null — no documented cap found for `{refs}`; VERIFY")
    exts = sorted({("." + e.group(1).lower().replace("jpeg", "jpeg"))
                   for e in EXT_RE.finditer(str(props.get(refs, {}).get("description") or ""))}) if refs else []
    if not exts:
        exts = [".jpg", ".jpeg", ".png", ".webp"]
        notes.append(f"accepts_ext={exts} — GUESSED (no formats named in the description); VERIFY against the README")

    prompt_cap = None
    m = re.search(r"[Mm]ax(?:imum)?\s+(\d[\d,]{2,})\s+characters", str(props.get("prompt", {}).get("description") or ""))
    if m:
        prompt_cap = int(m.group(1).replace(",", ""))
        notes.append(f"prompt.max_chars={prompt_cap} — parsed from the `prompt` description")

    for sentence in caveats(text, props, schemas):
        notes.append(sentence)

    entry = {
        "model": model,
        "kind": kind,
        # `studio-media-*` is the family for using the pipeline; `studio-code-*`
        # is for changing it. A model's page is always a media skill.
        "skill": f"studio-media-{key.replace('.', '-')}",
        # `backfill_slug` was minted here and is gone from every entry: it named
        # the output file a `backfill-replicate` import wrote, and that command
        # is deleted. Nothing else ever read it.
        "images": {
            "refs": refs, "max_refs": cap,
            "start": start, "end": end,
            "start_excludes_refs": False,
            "accepts_ext": exts,
        },
        "prompt": {"max_chars": prompt_cap},
        "note": "TODO — one line on what this model is for and how it differs from its siblings.",
        "snapshot": {},
    }
    if kind == "video":
        entry["video"] = {
            "negative": "prompt", "technical": "api", "max_cuts": None,
            "image_tokens": False,
            "resolution_field": "resolution" if "resolution" in props else "mode",
            "resolution_map": None,
            "allow_intelligent_duration": False,
        }
        notes.append("video.* block is a TEMPLATE — set max_cuts / technical / "
                     "resolution_map by hand from the docs.")
    if start:
        notes.append(f"frames first={start} last={end} — CHECK whether a start frame "
                     f"excludes references (`start_excludes_refs`); Seedance's does.")
    entry["snapshot"] = MS.snapshot(props, schemas)
    return entry, notes


@click.command(help=__doc__, epilog="\n\nArguments:\n  MODEL  Replicate model id, e.g. openai/gpt-image-2")
@click.argument("model", required=True)
@click.option("--json", "json_", is_flag=True)
@click.option("--key", help="Registry key (default: the model name).")
@click.option("--write", is_flag=True, help=("Append the entry to models.json. Without this, nothing is "
              "written. The skill page is written by `studio-media-add-model`, not here."))
def add_model(model, json_, key, write):
    if "/" not in model:
        die("model must be `owner/name`, e.g. openai/gpt-image-2")
    if REG.by_model_id(model):
        existing = REG.by_model_id(model)
        die(f"{model} is already registered as {existing['key']!r}.\n"
            f"       edit models.json directly, then: studio models refresh {existing['key']}")

    token = RA.load_token()
    try:
        props, schemas = MS.fetch(model, token)
    except MS.SchemaError as e:
        die(str(e))
    if not props:
        die(f"{model} has no published input schema — cannot onboard it.")

    entry, notes = infer(model, props, schemas, readme(model, token))
    key = key or model.split("/", 1)[1]

    if json_:
        print(json.dumps({"key": key, "entry": entry, "notes": notes}, indent=2))
        return 0

    print("===== 1/2  PROPOSED REGISTRY ENTRY — review before writing =====")
    print(json.dumps({key: entry}, indent=2))
    print("\n===== 2/2  WHAT WAS INFERRED vs GUESSED =====")
    for n in notes:
        print(f"  - {n}")
    print("\n  Read the model's README for constraints the schema cannot express")
    print("  (values it lists but does not honour) and add them under `denied`.")

    if not write:
        print("\nnothing written. Re-run with --write to add it.", file=sys.stderr)
        return 0

    data = json.load(open(REG.PATH))
    if key in data["models"]:
        die(f"registry key {key!r} is taken; pass --key to choose another.")
    data["models"][key] = entry
    with open(REG.PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nwrote {key} to {REG.PATH}", file=sys.stderr)
    print(f"\nnext: studio models show {key}", file=sys.stderr)
    print(f"      then write {entry['skill']}'s SKILL.md — the `studio-media-add-model` "
          "skill covers what belongs on the page.", file=sys.stderr)
    return 0
