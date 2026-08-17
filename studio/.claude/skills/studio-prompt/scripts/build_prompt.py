#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Assemble + validate a structured "JSON prompt" for one of the studio-* video
engines, and split it into the serialized prompt string plus whatever the engine
actually takes alongside it.

Every engine's `prompt` field is a plain TEXT string. "JSON prompting" means
serializing a structured object into that string; models read structured text
consistently. This tool:

  1. takes a structured object (creative blocks + a `technical` block),
  2. validates the shared prompting rules (one camera move, no bare "fast", no
     camera verbs in the action, no vague adjectives, beat budget, …) plus the
     rules specific to the target engine,
  3. ROUTES the technical fields off the prompt text — to Replicate API params
     for Seedance and for Kling, and
  4. emits {prompt, input, warnings, errors, timeline}.

Key ordering follows ByteDance's own guidance — SUBJECT + ACTION lead, because
"the first 20-30 words carry the most weight" — not the camera-first order some
third-party guides push. It holds for Kling too.

ENGINES (--engine, default `seedance`)
  seedance    bytedance/seedance-2.0 via Replicate. NO negative_prompt param, so
              `negative` stays inside the prompt as an "avoid" key. Technical
              fields become the Replicate `input` object. Drafts are checked
              against this model's wording list (data in S3).
  kling-replicate
              kwaivgi/kling-v3-omni-video via Replicate. THE DEFAULT KLING PATH:
              pay-per-second, no resource package, `reference_images` like
              Seedance's. Native multi-shot up to 6 cuts, emitted as the model's
              `multi_prompt` JSON array. No seed, no negative_prompt.

IMAGE-TO-VIDEO
  Set `"start_image": true` when a start frame is supplied. The validator then
  warns about text that re-describes what the frame already shows (scene,
  lighting, wardrobe, a long appearance block) — describing it twice makes the
  model fight the image and drift.

Usage:
  build_prompt.py prompt.json
  build_prompt.py prompt.json --engine kling-replicate
  build_prompt.py - < prompt.json
  build_prompt.py --json '{"subject": "...", "action": "..."}'
  build_prompt.py prompt.json --duration 8 --aspect-ratio 9:16 --emit input

Author the object like:
  {
    "subject": "A young woman in a white linen dress",
    "action": "Slowly turns to face the sea, skirt lifting in the breeze",
    "scene": "Rocky coastline at dusk, warm golden haze",
    "camera": {"shot": "medium", "movement": "slow push-in", "lens_mm": 35, "speed": "slow"},
    "lighting": "Low golden-hour sun, soft rim light",
    "style": "Cinematic film tone, gentle contrast, 35mm grain",
    "audio": "Soft wind, distant gulls",
    "dialogue": ["It's finally quiet out here."],
    "negative": "jitter, bent limbs, temporal flicker, extra fingers",
    "technical": {"aspect_ratio": "16:9", "duration": 6, "resolution": "1080p", "generate_audio": true}
  }

For a multi-shot piece, use timeline mode by supplying `shots`:
  {
    "subject": "A detective in a long coat",
    "style": "Neo-noir, teal/amber grade",
    "shots": [
      {"t": "0s", "shot": "wide",   "camera": "static",          "description": "Stands at the end of a rain-slicked street"},
      {"t": "3s", "shot": "medium", "camera": "slow dolly in",    "description": "Camera closes in from behind"},
      {"t": "6s", "shot": "close",  "camera": "hold",             "description": "Rain beads on his collar; he exhales"}
    ],
    "technical": {"duration": 8, "aspect_ratio": "21:9"}
  }
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# --- engine capabilities ----------------------------------------------------
# `negative`:  "prompt" -> folded into the prompt text as `avoid`
#              "param"  -> emitted separately; MUST stay out of the prompt text
# `technical`: "api"    -> a Replicate `input` object
#              "replicate_kling" -> a Replicate `input` for kwaivgi/kling-v3-omni-video
# `max_cuts`:  hard ceiling on shots (None -> use the 3-beats-per-8s density rule)
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "studio-core", "scripts")))
import registry as REG  # noqa: E402


def _engines_from_registry() -> dict[str, dict]:
    """Build the engine table from the model registry.

    The enums and ranges used to be hardcoded here, a third copy of facts the
    live schema already publishes — and one that could drift silently from what
    the model accepts. They now come from each entry's `snapshot`, refreshed by
    `studio.py models refresh`.

    The snapshot is used rather than a live fetch on purpose: authoring a prompt
    must keep working offline. It is advisory only — whatever finally submits
    re-validates against the live schema, so a stale snapshot can cost a retry
    but can never let a bad payload bill.
    """
    out: dict[str, dict] = {}
    for key, entry in REG.videos().items():
        snap = entry.get("snapshot") or {}
        vid = entry.get("video") or {}
        res_map = vid.get("resolution_map")
        resolutions = (set(res_map) if res_map
                       else set((snap.get(vid.get("resolution_field", "resolution")) or {}).get("enum") or []))
        dur = snap.get("duration") or {}
        lo, hi = dur.get("minimum", 1), dur.get("maximum", 15)
        spec = {
            "key": key,
            "label": f"{entry['model']} (Replicate)",
            "resolutions": resolutions,
            "aspect_ratios": set((snap.get("aspect_ratio") or {}).get("enum") or []),
            # -1 means "intelligent duration" and is handled by its own flag, so
            # the advertised floor is the smallest real length.
            "duration": (max(lo, 1), hi),
            "allow_intelligent_duration": vid.get("allow_intelligent_duration", False),
            "max_cuts": vid.get("max_cuts"),
            "negative": vid.get("negative", "prompt"),
            "technical": vid.get("technical", "api"),
            "image_tokens": vid.get("image_tokens", False),
        }
        cap = REG.field(entry, "prompt.max_chars")
        if cap:
            spec["prompt_max"] = cap
            spec["prompt_recommended"] = cap
        out[key] = spec
        for alias in entry.get("aliases") or []:
            out[alias] = spec
    return out


ENGINES: dict[str, dict] = _engines_from_registry()

# Fields that map to REAL engine settings (not prompt text).
TECHNICAL_KEYS = {"aspect_ratio", "duration", "resolution", "seed", "generate_audio"}
# jsonpromptstudio invents these; no engine here has such a param. Warn + drop.
UNSUPPORTED_TECHNICAL = {"fps", "creativity", "lock_identity", "lock_style", "negative_prompt"}

# Ordered creative keys for the serialized prompt (subject/action FIRST).
PROMPT_KEY_ORDER = ["subject", "action", "scene", "camera", "lighting", "style", "audio", "dialogue", "avoid"]

# Camera-movement vocabulary — used to detect stacking and misplaced verbs.
CAMERA_MOVES = [
    "push-in", "push in", "pull-out", "pull out", "dolly", "pan", "tilt",
    "tracking", "track", "orbit", "aerial", "drone", "crane", "handheld",
    "zoom", "rack focus", "whip",
]
VAGUE_ADJECTIVES = [
    "amazing", "beautiful", "epic", "stunning", "gorgeous", "breathtaking",
    "awesome", "incredible", "majestic", "magical",
]

PHRASEBOOK_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "s3", "scripts", "phrasebook.py",
)


def phrasebook_terms(model_key: str) -> tuple[list[dict], str | None]:
    """This model's wording list, fetched once. -> (terms, unavailable_reason).

    A wording list is a set of substitutions — a phrase, and the phrase to use
    instead — kept as DATA in S3 rather than in this repository, the same way
    characters are.

    Authoring must keep working without credentials, so a fetch failure degrades
    to a warning rather than an error: the caller is told the list was not read,
    which is honest, instead of being told the draft was checked, which would not be.
    """
    try:
        out = subprocess.run(["uv", "run", PHRASEBOOK_PY, "terms", "--model", model_key],
                             capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return [], f"could not run the phrasebook ({exc.__class__.__name__})"
    if out.returncode != 0:
        detail = (out.stderr or "").strip().splitlines()
        return [], (detail[-1] if detail else "the phrasebook could not be read")
    try:
        return json.loads(out.stdout or "[]"), None
    except json.JSONDecodeError:
        return [], "the phrasebook returned output that could not be parsed"

# Fields a supplied start frame already fixes — re-describing them fights the image.
START_IMAGE_REDUNDANT = ("scene", "lighting")


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def load_object(args: argparse.Namespace) -> dict:
    """Load the base structured object from a file, stdin, or --json."""
    raw = None
    if args.json is not None:
        raw = args.json
    elif args.source == "-":
        raw = sys.stdin.read()
    elif args.source:
        with open(args.source, encoding="utf-8") as fh:
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


def apply_overrides(obj: dict, args: argparse.Namespace) -> None:
    """CLI flags override values inside the loaded object."""
    for key in ("subject", "action", "scene", "style", "lighting", "audio", "negative"):
        val = getattr(args, key)
        if val is not None:
            obj[key] = val
    if args.start_image:
        obj["start_image"] = True

    cam = obj.get("camera")
    if not isinstance(cam, dict):
        cam = {} if cam is None else {"movement": str(cam)}
    if args.camera_movement is not None:
        cam["movement"] = args.camera_movement
    if args.camera_shot is not None:
        cam["shot"] = args.camera_shot
    if args.lens_mm is not None:
        cam["lens_mm"] = args.lens_mm
    if cam:
        obj["camera"] = cam

    tech = obj.get("technical")
    if not isinstance(tech, dict):
        tech = {}
    if args.aspect_ratio is not None:
        tech["aspect_ratio"] = args.aspect_ratio
    if args.duration is not None:
        tech["duration"] = args.duration
    if args.resolution is not None:
        tech["resolution"] = args.resolution
    if args.seed is not None:
        tech["seed"] = args.seed
    if args.no_audio:
        tech["generate_audio"] = False
    if tech:
        obj["technical"] = tech


def _text_fields(obj: dict) -> dict[str, str]:
    """Flatten the creative text into {field: text} for scanning."""
    out: dict[str, str] = {}
    for k in ("subject", "action", "scene", "style", "lighting", "audio", "negative"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v
    cam = obj.get("camera")
    if isinstance(cam, dict):
        for ck in ("shot", "movement", "speed"):
            v = cam.get(ck)
            if isinstance(v, str) and v.strip():
                out[f"camera.{ck}"] = v
    for i, shot in enumerate(obj.get("shots") or []):
        if isinstance(shot, dict):
            for sk in ("camera", "description"):
                v = shot.get(sk)
                if isinstance(v, str) and v.strip():
                    out[f"shots[{i}].{sk}"] = v
    return out


def _beat_budget(duration: int | None, spec: dict) -> int:
    """How many shots this engine can actually resolve in `duration` seconds."""
    hard = spec["max_cuts"]
    if hard is not None:
        return hard
    # Seedance-class density: ~3 beats per 8 seconds, never fewer than 1.
    if not isinstance(duration, int) or duration <= 0:
        return 3
    return max(1, round(duration * 3 / 8))


def validate(obj: dict, engine: str) -> tuple[list[str], list[str]]:
    spec = ENGINES[engine]
    warnings: list[str] = []
    errors: list[str] = []
    fields = _text_fields(obj)

    # --- one camera movement only -----------------------------------------
    cam = obj.get("camera")
    if isinstance(cam, dict):
        move = str(cam.get("movement", "") or "")
        low = move.lower()
        if move:
            # stacking detected via connectors or 2+ distinct move verbs.
            # Match on word boundaries, then drop hits that are substrings of a
            # longer hit ("track" inside "tracking") so one move isn't counted twice.
            raw = {m for m in CAMERA_MOVES if re.search(rf"(?<!\w){re.escape(m)}(?!\w)", low)}
            hits = {m for m in raw if not any(m != o and m in o for o in raw)}
            connector = bool(re.search(r"\b(and|then|\+|,|while|followed by)\b", low))
            if len(hits) >= 2 or (connector and hits):
                warnings.append(
                    f"camera.movement stacks multiple moves ({move!r}); these models "
                    "degrade on stacked moves — keep one shot type + one movement."
                )

    # --- bare 'fast' -------------------------------------------------------
    for field, text in fields.items():
        if re.search(r"\bfast\b", text.lower()) and field.startswith("camera"):
            warnings.append(
                f"{field} uses bare 'fast' ({text!r}); qualify the speed "
                "(e.g. 'fast whip-pan', 'quick 1s push-in') — bare 'fast' causes chaos."
            )

    # --- camera verbs leaking into subject/action -------------------------
    for field in ("subject", "action"):
        text = fields.get(field, "").lower()
        leaked = sorted({m for m in CAMERA_MOVES if re.search(rf"\b{re.escape(m)}\b", text)})
        if leaked:
            warnings.append(
                f"{field} contains camera-move words {leaked}; move camera "
                "direction into the `camera` block, keep this block to subject motion."
            )

    # --- vague adjectives --------------------------------------------------
    for field, text in fields.items():
        if field in ("audio", "negative"):
            continue
        found = sorted({a for a in VAGUE_ADJECTIVES if re.search(rf"\b{a}\b", text.lower())})
        if found:
            warnings.append(
                f"{field} uses vague adjective(s) {found}; replace with concrete, "
                "observable detail (these models ignore mood words like these)."
            )

    # --- beat budget -------------------------------------------------------
    shots = obj.get("shots") or []
    if shots:
        tech = obj.get("technical") if isinstance(obj.get("technical"), dict) else {}
        budget = _beat_budget(tech.get("duration"), spec)
        if len(shots) > budget:
            if spec["max_cuts"] is not None:
                warnings.append(
                    f"{len(shots)} shots exceeds {engine}'s native multi-shot ceiling of "
                    f"{budget} cuts; split the sequence across generations."
                )
            else:
                warnings.append(
                    f"{len(shots)} shots in {tech.get('duration', '?')}s exceeds the ~3-beats-per-8s "
                    f"budget (~{budget} here); the model will drop or morph beats. Split it, or "
                    "render on an engine with native multi-shot (kling-replicate)."
                )

    # --- wording list, from the phrasebook in S3 ---------------------------
    # Runs for every engine; each has its own list. The lists live in S3.
    terms, unavailable = phrasebook_terms(spec["key"])
    if unavailable:
        warnings.append(
            f"wording list not read — {unavailable}. It lives in S3, so this needs "
            "an aws login; the draft was not checked against it."
        )
    for field, text in fields.items():
        if field == "negative":
            continue
        low = text.lower()
        for t in terms:
            if t["avoid"].lower() in low:
                warnings.append(
                    f"{field}: {spec['label']} prefers {t['use']!r} over "
                    f"{t['avoid']!r}."
                )

    # --- engine-specific: [ImageN] reference tokens ------------------------
    if not spec["image_tokens"]:
        for field, text in fields.items():
            if re.search(r"\[(?:Image|Video|Audio)\d+\]", text):
                warnings.append(
                    f"{field} uses a [ImageN]-style reference token; that is Seedance/Replicate "
                    f"syntax and is literal text to {spec['label']}. Supply the frame through the "
                    "UI instead and drop the token."
                )
                break

    # --- image-to-video: don't re-describe what the frame already shows ----
    if obj.get("start_image"):
        redundant = [f for f in START_IMAGE_REDUNDANT if fields.get(f)]
        if redundant:
            warnings.append(
                f"start_image is set but {redundant} still described in text; a start frame "
                "already fixes these, and describing them twice makes the model fight the "
                "image and drift. Cut them."
            )
        subj = fields.get("subject", "")
        if len(subj.split()) > 40:
            warnings.append(
                f"start_image is set but `subject` is {len(subj.split())} words; the frame carries "
                "appearance better than text can. Trim to a short identity anchor "
                "(e.g. 'the man from the source image, unchanged')."
            )

    # --- technical block routing ------------------------------------------
    tech = obj.get("technical")
    if isinstance(tech, dict):
        for k in tech:
            if k in UNSUPPORTED_TECHNICAL:
                if k == "negative_prompt":
                    dest = (
                        "emitted as a separate `negative_prompt`"
                        if spec["negative"] == "param"
                        else "folded into the prompt as `avoid`"
                    )
                    warnings.append(
                        f"technical.negative_prompt is not a technical setting; it was {dest} "
                        "instead. Use the top-level `negative` key going forward."
                    )
                else:
                    warnings.append(
                        f"technical.{k} is not a real {spec['label']} setting; dropped. "
                        "(Some third-party guides invent it.)"
                    )
        if spec["technical"] == "replicate_kling":
            if tech.get("seed") is not None:
                warnings.append(
                    "technical.seed is set, but Kling exposes no seed parameter — "
                    "runs are not reproducible by seed there. Hold the prompt fixed instead."
                )
            if obj.get("start_image") and tech.get("aspect_ratio"):
                warnings.append(
                    "technical.aspect_ratio is ignored for Kling image-to-video; the first "
                    "frame determines the output frame shape. Crop the frame instead."
                )
        ar = tech.get("aspect_ratio")
        if ar is not None and ar not in spec["aspect_ratios"]:
            errors.append(
                f"aspect_ratio {ar!r} not supported by {spec['label']}; "
                f"choose one of {sorted(spec['aspect_ratios'])}."
            )
        res = tech.get("resolution")
        if res is not None and res not in spec["resolutions"]:
            errors.append(
                f"resolution {res!r} not supported by {spec['label']}; "
                f"choose one of {sorted(spec['resolutions'])}."
            )
        dur = tech.get("duration")
        lo, hi = spec["duration"]
        if dur is not None:
            ok = isinstance(dur, int) and lo <= dur <= hi
            if spec["allow_intelligent_duration"] and dur == -1:
                ok = True
            if not ok:
                extra = ", or -1 for intelligent duration" if spec["allow_intelligent_duration"] else ""
                errors.append(
                    f"duration {dur!r} invalid for {spec['label']}; use an int {lo}-{hi}{extra}."
                )

    # --- must have SOMETHING to render ------------------------------------
    if not obj.get("shots") and not obj.get("subject") and not obj.get("action"):
        errors.append("nothing to render: provide at least `subject`/`action`, or a `shots` timeline.")

    return warnings, errors


def _shot_seconds(shots: list, total: int | None) -> list[int] | None:
    """Per-shot durations, from an explicit `dur` or derived from the `t` marks."""
    if any(isinstance(s, dict) and s.get("dur") is not None for s in shots):
        out = []
        for s in shots:
            d = s.get("dur") if isinstance(s, dict) else None
            if not isinstance(d, int) or d < 1:
                return None
            out.append(d)
        return out
    # derive from consecutive start marks: "0s", "3s", …
    starts: list[int] = []
    for s in shots:
        t = s.get("t") if isinstance(s, dict) else None
        if not isinstance(t, str):
            return None
        m = re.match(r"^\s*(\d+)\s*s?\s*$", t)
        if not m:
            return None
        starts.append(int(m.group(1)))
    if not total:
        return None
    ends = starts[1:] + [total]
    durs = [e - s for s, e in zip(starts, ends)]
    return durs if all(d >= 1 for d in durs) else None


def _shot_text(shot) -> str:
    """One shot's prompt text: its description plus shot type / camera."""
    if not isinstance(shot, dict):
        return str(shot).strip()
    bits = [shot.get("description") or ""]
    for k in ("shot", "camera"):
        v = shot.get(k)
        if isinstance(v, str) and v.strip():
            bits.append(f"{'shot type' if k == 'shot' else 'camera'}: {v.strip()}")
    return ", ".join(b.strip().rstrip(".") for b in bits if b and b.strip())


def resolve_negative(obj: dict) -> str | None:
    """The negative text, wherever the author put it."""
    neg = obj.get("negative")
    if not neg:
        tech = obj.get("technical")
        if isinstance(tech, dict):
            neg = tech.get("negative_prompt")
    return neg or None


def build_prompt_object(obj: dict, engine: str) -> tuple[dict, bool]:
    """Return (ordered creative object for serialization, is_timeline).

    On engines with a real negative-prompt field the negative is deliberately
    NOT serialized into the prompt — it goes out alongside it instead.
    """
    spec = ENGINES[engine]
    timeline = bool(obj.get("shots"))
    neg = resolve_negative(obj) if spec["negative"] == "prompt" else None
    out: dict = {}

    if timeline:
        # globals first, then the ordered shot list.
        for k in ("subject", "style", "audio", "lighting"):
            v = obj.get(k)
            if v:
                out[k] = v
        clean_shots = []
        for shot in obj["shots"]:
            if isinstance(shot, dict):
                clean_shots.append({k: v for k, v in shot.items() if v not in (None, "", [])})
            else:
                clean_shots.append(shot)
        out["shots"] = clean_shots
        if neg:
            out["avoid"] = neg
        return out, timeline

    # single-shot: subject/action FIRST, then the rest in canonical order.
    src = dict(obj)
    if neg:
        src["avoid"] = neg
    for key in PROMPT_KEY_ORDER:
        v = src.get(key)
        if v in (None, "", [], {}):
            continue
        if key == "camera" and isinstance(v, dict):
            v = {ck: cv for ck, cv in v.items() if cv not in (None, "")}
            if not v:
                continue
        out[key] = v
    return out, timeline


def build_settings(obj: dict, prompt_str: str, engine: str) -> tuple[str, dict]:
    """Assemble what goes alongside the prompt.

    Returns (key, payload) — ("input", replicate_input) for API engines, or
    ("settings", ui_checklist) for engines driven by hand through a web UI.
    """
    spec = ENGINES[engine]
    tech = obj.get("technical") if isinstance(obj.get("technical"), dict) else {}
    picked = {k: tech[k] for k in TECHNICAL_KEYS if k in tech and tech[k] is not None}

    if spec["technical"] == "api":
        return "input", {"prompt": prompt_str, **picked}

    if spec["technical"] == "replicate_kling":
        # Replicate exposes resolution as `mode`, and multi-shot as a JSON-encoded
        # string array. No seed and no negative_prompt exist on this model.
        mode = {"720p": "standard", "1080p": "pro", "4k": "4k"}.get(
            picked.get("resolution", "1080p"), "pro"
        )
        inp: dict = {"prompt": prompt_str, "mode": mode}
        if "duration" in picked:
            inp["duration"] = picked["duration"]
        inp["generate_audio"] = bool(picked.get("generate_audio"))
        if not obj.get("start_image") and "aspect_ratio" in picked:
            inp["aspect_ratio"] = picked["aspect_ratio"]
        shots = obj.get("shots") or []
        if shots:
            durs = _shot_seconds(shots, picked.get("duration"))
            if durs:
                inp["multi_prompt"] = json.dumps(
                    [{"prompt": _shot_text(sh), "duration": d} for sh, d in zip(shots, durs)],
                    ensure_ascii=False,
                )
        return "input", inp

    return "input", {"prompt": prompt_str, **picked}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Build + validate a studio-* JSON video prompt and split it into a "
        "serialized prompt string plus the engine's own settings.",
    )
    p.add_argument("source", nargs="?", help="Path to a JSON object file, or '-' for stdin.")
    p.add_argument("--json", help="Inline JSON object (overrides source).")
    p.add_argument(
        "--engine",
        choices=sorted(ENGINES),
        default="seedance",
        help="Target engine (default: seedance). Changes negative-prompt handling, "
        "beat budget, enums, and which content rules apply.",
    )
    # creative overrides
    p.add_argument("--subject")
    p.add_argument("--action")
    p.add_argument("--scene")
    p.add_argument("--style")
    p.add_argument("--lighting")
    p.add_argument("--audio")
    p.add_argument("--negative")
    p.add_argument("--camera-movement")
    p.add_argument("--camera-shot")
    p.add_argument("--lens-mm", type=int)
    p.add_argument(
        "--start-image",
        action="store_true",
        help="Declare that a start frame is supplied; enables the anti-redundancy checks.",
    )
    # technical overrides
    p.add_argument("--aspect-ratio")
    p.add_argument("--duration", type=int)
    p.add_argument("--resolution")
    p.add_argument("--seed", type=int)
    p.add_argument("--no-audio", action="store_true", help="Set generate_audio=false.")
    # output control
    p.add_argument("--emit", choices=["both", "prompt", "input"], default="both")
    p.add_argument("--compact", action="store_true", help="Single-line prompt JSON (no indent).")
    p.add_argument("--strict", action="store_true", help="Exit non-zero if any warnings.")
    args = p.parse_args()

    engine = args.engine
    spec = ENGINES[engine]

    obj = load_object(args)
    apply_overrides(obj, args)

    warnings, errors = validate(obj, engine)
    if errors:
        for e in errors:
            _err(e)
        return 2

    prompt_obj, timeline = build_prompt_object(obj, engine)

    prompt_str = json.dumps(
        prompt_obj,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        separators=(",", ":") if args.compact else None,
    )

    hard = spec.get("prompt_max")
    soft = spec.get("prompt_recommended")
    if hard and len(prompt_str) > hard:
        _err(f"prompt is {len(prompt_str)} chars; {spec['label']} caps it at {hard}.")
        return 2
    if soft and len(prompt_str) > soft:
        warnings.append(
            f"prompt is {len(prompt_str)} chars; {spec['label']} recommends <= {soft}. "
            "Trim before submitting — truncation would drop the tail of the prompt."
        )

    settings_key, settings = build_settings(obj, prompt_str, engine)

    if args.emit == "prompt":
        payload: dict = {"prompt": prompt_str}
    elif args.emit == "input":
        payload = {settings_key: settings}
    else:
        payload = {"prompt": prompt_str, settings_key: settings}

    # On engines with a real negative field, hand it back separately — it must
    # be typed into the UI's own box, NOT pasted with the prompt.
    if spec["negative"] == "param" and args.emit != "prompt":
        neg = resolve_negative(obj)
        if neg:
            payload["negative_prompt"] = neg

    payload["engine"] = engine
    payload["timeline"] = timeline
    payload["warnings"] = warnings

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
