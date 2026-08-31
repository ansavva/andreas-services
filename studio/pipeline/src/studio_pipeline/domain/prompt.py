"""`studio prompt` — author a structured video prompt, checked by the API.

**The judgement moved to `backend/studio_core/services/prompt.py`.** Six hundred
and ninety lines of prompting rules lived here — one camera move per shot, no
bare "fast", no camera verbs in the action line, a beat budget scaled to
duration, a warning when a supplied start frame is described twice — and nothing
but this command could reach any of it. The SPA could not offer a single check.

Two things the rules need were already server-side, which is what made the move
worth doing: the model registry supplies each engine's ranges and caps, and the
phrasebook is `TERM#` rows. Both were being fetched over the wire in order to do
a local computation.

What is left here is the half a terminal owns: reading the object from a file,
from stdin or from `--json`, turning flags into overrides, printing the result,
and deciding what `--strict` means. `POST /api/prompt` does the rest, writes
nothing, and bills nothing — it is safe to call on every keystroke, which is the
point of it being reachable at all.

Author the object like:

  {
    "subject": "A young woman in a white linen dress",
    "action": "Slowly turns to face the sea, skirt lifting in the breeze",
    "scene": "Rocky coastline at dusk, warm golden haze",
    "camera": {"shot": "medium", "movement": "slow push-in", "lens_mm": 35},
    "lighting": "Low golden-hour sun, soft rim light",
    "style": "Cinematic film tone, gentle contrast, 35mm grain",
    "audio": "Soft wind, distant gulls",
    "negative": "jitter, bent limbs, temporal flicker, extra fingers",
    "technical": {"aspect_ratio": "16:9", "duration": 6, "resolution": "1080p"}
  }

For a multi-shot piece, supply `shots` instead of one `action`; the API budgets
the beats across the duration and refuses more cuts than the engine takes.

  studio prompt prompt.json
  studio prompt prompt.json --engine kling-replicate --duration 8
  studio prompt - < prompt.json
  studio prompt --json '{"subject": "...", "action": "..."}'
"""
from __future__ import annotations

import json
import sys

import click

from studio_pipeline.adapters import api, entities

#: Which flags become overrides, and under which names the API expects them.
#: Declared once so the command signature and the request body cannot drift.
#:
#: **It said that already and was not doing it.** The command restated all
#: sixteen names in a dict literal and this tuple had no reader at all, so the
#: two could disagree in either direction and nothing would notice — an option
#: added below and forgotten here would simply never reach the API. The body is
#: built from this tuple now, which is what the sentence above always claimed.
OVERRIDE_FLAGS = (
    "subject", "action", "scene", "style", "lighting", "audio", "negative",
    "start_image", "camera_movement", "camera_shot", "lens_mm",
    "aspect_ratio", "duration", "resolution", "seed", "no_audio",
)


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def load_object(source: str | None = None, json_text: str | None = None) -> dict:
    """Load the base structured object from `--json`, stdin, or a file.

    Stays here because it is the one part of this that touches a filesystem, and
    because the failure it reports is about a path a person typed.
    """
    raw = None
    if json_text is not None:
        raw = json_text
    elif source == "-":
        raw = sys.stdin.read()
    elif source:
        with open(source, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        return {}
    raw = raw.strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        _err(f"input is not valid JSON: {exc}")
        sys.exit(2)
    if not isinstance(obj, dict):
        _err("top-level JSON must be an object")
        sys.exit(2)
    return obj


@click.command(help=__doc__, epilog="\n\nArguments:\n  SOURCE  Path to a JSON object file, or '-' for stdin.")
@click.argument("source", required=False)
@click.option("--action")
@click.option("--aspect-ratio")
@click.option("--audio")
@click.option("--camera-movement")
@click.option("--camera-shot")
@click.option("--compact", is_flag=True, help="Single-line prompt JSON (no indent).")
@click.option("--duration", type=int)
@click.option("--emit", type=click.Choice(["both", "input", "prompt"]), default='both')
@click.option("--engine", type=click.Choice(["kling", "kling-replicate", "seedance"]), default='seedance', help=("Target engine (default: seedance). Changes negative-prompt "
              "handling, beat budget, enums, and which content rules apply."))
@click.option("--json", "json_", help="Inline JSON object (overrides source).")
@click.option("--lens-mm", type=int)
@click.option("--lighting")
@click.option("--negative")
@click.option("--no-audio", is_flag=True, help="Set generate_audio=false.")
@click.option("--resolution")
@click.option("--scene")
@click.option("--seed", type=int)
@click.option("--start-image", is_flag=True, help=("Declare that a start frame is supplied; enables the "
              "anti-redundancy checks."))
@click.option("--strict", is_flag=True, help="Exit non-zero if any warnings.")
@click.option("--style")
@click.option("--subject")
def prompt(source, action, aspect_ratio, audio, camera_movement, camera_shot, compact,
           duration, emit, engine, json_, lens_mm, lighting, negative, no_audio,
           resolution, scene, seed, start_image, strict, style, subject):
    obj = load_object(source, json_text=json_)

    # Read off the parameters by the names in `OVERRIDE_FLAGS`, so the tuple is
    # the only place the list exists. Click passes every option as a keyword
    # argument named after its flag, which is what makes `locals()` exactly the
    # signature here and not a grab-bag — `source`, `emit`, `engine`, `json_`,
    # `compact` and `strict` are not overrides and are simply not asked for.
    flags = locals()
    # Only what was actually typed. A `None` here would be indistinguishable
    # from "clear this field" on the far side, and `False` is what an unset
    # `is_flag` looks like.
    overrides = {name: flags[name] for name in OVERRIDE_FLAGS
                 if flags[name] not in (None, False)}

    try:
        answer = entities.build_prompt(obj, engine, emit=emit, compact=compact,
                                       overrides=overrides)
    except api.ApiError as exc:
        _err(str(exc))
        raise SystemExit(2) from None

    # **Errors come back in the body rather than as a refusal**, because a
    # half-written prompt is the ordinary case and an editor wants to draw them.
    # A command line wants to stop, so it does.
    errors = answer.pop("errors", None) or []
    if errors:
        for problem in errors:
            _err(problem)
        raise SystemExit(2)

    warnings = answer.get("warnings") or []
    print(json.dumps(answer, ensure_ascii=False, indent=2))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if strict and warnings:
        raise SystemExit(1)
