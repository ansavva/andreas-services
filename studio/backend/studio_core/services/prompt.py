"""Authoring a structured video prompt: assemble it, then say what is wrong with it.

Every engine's `prompt` field is a plain TEXT string. "JSON prompting" means
serializing a structured object into that string, because models read structured
text consistently. This module takes the object, checks it against the shared
prompting rules and the target engine's own, routes the technical fields off the
prompt text into the provider's `input`, and answers with both plus the warnings.

**It lived in the pipeline and nothing server-side knew it existed.** Six hundred
and ninety lines of prompting judgement — one camera move per shot, no bare
"fast", no camera verbs in the action, a beat budget scaled to duration, a
warning when a supplied start frame is described twice — reachable only from a
terminal. The SPA could not offer any of it, and neither could anything else that
might come to author a shot.

Two things it needs were already here, which is what made the move worth doing
now rather than later: the model **registry** (`services/registry.py`) supplies
each engine's resolutions, aspect ratios, duration range, cut ceiling and prompt
cap, and the **phrasebook** (`TERM#` rows) supplies the per-model wording list. In
the pipeline both were fetched over the wire to do a local computation.

## What is checked, and what is only warned about

An **error** means the payload cannot be built — an unknown engine, a duration
outside the model's range, more cuts than it takes. A **warning** means it will
build and probably render worse: a vague adjective, a camera move in the action
line, a scene description fighting the start frame. The caller decides what to do
with warnings; `studio prompt --strict` exits non-zero on any.

## No Flask, no boto3, and that is deliberate

The phrasebook lookup is **injected** rather than imported. This module is loaded
by path from `pipeline/tests/support/fake_api.py`, which mirrors the API without
depending on the backend package — the same arrangement `services/storyboard.py`
has, and for the same reason: the alternative is a second implementation of six
hundred lines of prompting rules, which is precisely what this move exists to
end. Importing `catalog` here would pull in boto3 and break that.

No lookup means no phrasebook, which reads as "no substitutions apply" and is the
honest answer for a caller that has no library in hand.

## The snapshot, not a live fetch

Enums and ranges come from each registry entry's `snapshot`, refreshed by
`studio models refresh`. That is deliberate: authoring must not depend on the
provider being up, and it is advisory anyway — whatever finally submits
re-validates against the live schema, so a stale snapshot costs a retry and can
never let a bad payload bill.
"""

from __future__ import annotations

import functools
import json
import re

from studio_core.services import registry as REG

@functools.lru_cache(maxsize=1)
def engines() -> dict[str, dict]:
    """Build the engine table from the model registry.

    **A function, memoised, where this was a module constant.** The registry is
    `GET /api/models` now, and a constant is evaluated at import — which is
    before Click has parsed an argument, before a profile is selected, and before
    anyone has signed in. Importing `cli.py` would have opened an HTTP
    connection, so `studio --help` would have needed a session and an unreachable
    API would have been an ImportError rather than a message.

    The enums and ranges used to be hardcoded here, a third copy of facts the
    live schema already publishes — and one that could drift silently from what
    the model accepts. They now come from each entry's `snapshot`, refreshed by
    `studio models refresh`.

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


def phrasebook_terms(model_key: str, lookup=None) -> tuple[list[dict], str | None]:
    """This model's wording list, fetched once. -> (terms, unavailable_reason).

    A wording list is a set of substitutions — a phrase, and the phrase to use
    instead — kept as DATA in S3 rather than in this repository, the same way
    characters are.

    Authoring must keep working when the phrasebook cannot be reached — no
    session, no network, a library that has never held one — so a fetch failure
    degrades to a warning rather than an error: the caller is told the list was
    not read, which is honest, instead of being told the draft was checked,
    which would not be.

    That covers a refusal too, and deliberately. A 403 still leaves the draft
    unchecked, and the warning says so. What must never happen is a refusal
    reported as "no substitutions apply", and `phrasebook.load` raises rather
    than let one become that.
    """
    if lookup is None:
        return [], None
    try:
        rows = lookup(model_key)
        return ([{"avoid": row["avoid"], "use": row["use"]}
                 for row in rows if row.get("avoid")], None)
    except Exception as exc:  # a bug here must not block authoring
        return [], f"could not read the phrasebook ({exc.__class__.__name__})"

# Fields a supplied start frame already fixes — re-describing them fights the image.
START_IMAGE_REDUNDANT = ("scene", "lighting")


TOP_LEVEL = ("subject", "action", "scene", "style", "lighting", "audio", "negative")
CAMERA = {"camera_movement": "movement", "camera_shot": "shot", "lens_mm": "lens_mm"}
TECHNICAL = {"aspect_ratio": "aspect_ratio", "duration": "duration",
             "resolution": "resolution", "seed": "seed"}


def apply_overrides(obj: dict, **overrides) -> None:
    """CLI flags override values inside the loaded object.

    Takes plain keyword values rather than a parsed-arguments object, so the
    rules here can be exercised without going through a command line.
    """
    for key in TOP_LEVEL:
        if overrides.get(key) is not None:
            obj[key] = overrides[key]
    if overrides.get("start_image"):
        obj["start_image"] = True

    cam = obj.get("camera")
    if not isinstance(cam, dict):
        cam = {} if cam is None else {"movement": str(cam)}
    for flag, field in CAMERA.items():
        if overrides.get(flag) is not None:
            cam[field] = overrides[flag]
    if cam:
        obj["camera"] = cam

    tech = obj.get("technical")
    if not isinstance(tech, dict):
        tech = {}
    for flag, field in TECHNICAL.items():
        if overrides.get(flag) is not None:
            tech[field] = overrides[flag]
    if overrides.get("no_audio"):
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


def validate(obj: dict, engine: str, terms_lookup=None) -> tuple[list[str], list[str]]:
    spec = engines()[engine]
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
    terms, unavailable = phrasebook_terms(spec["key"], terms_lookup)
    if unavailable:
        warnings.append(
            f"wording list not read — {unavailable}. It lives in S3, so this needs "
            "working AWS credentials; the draft was not checked against it."
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
    spec = engines()[engine]
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
    spec = engines()[engine]
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



# ── the one entry point ─────────────────────────────────────────────────────


def assemble(obj: dict, engine: str, *, emit: str = "both", compact: bool = False,
             overrides: dict | None = None, terms_lookup=None) -> dict:
    """Object in; prompt, provider input, timeline and warnings out.

    **This was the body of the `studio prompt` command.** Twenty lines of Click
    glue with the whole decision sequence inlined — apply overrides, validate,
    build, check the length cap, split the negative prompt off — so nothing but
    that command could ever run it. It is a function now and the command calls it
    through one HTTP request.

    Errors are RETURNED rather than raised. The caller decides: the CLI prints
    them and exits 2, an editor draws them beside the field they came from, and
    both want the partial result in the same answer.

    The length cap is checked here rather than in `validate`, and that ordering
    is load-bearing: a prompt's length is a property of the serialized string,
    which does not exist until the object has been built. A hard cap is an error
    because the provider would truncate — silently dropping the tail, which on a
    multi-shot prompt is the last cut.
    """
    spec = engines()[engine]
    obj = dict(obj)
    if overrides:
        apply_overrides(obj, **overrides)

    warnings, errors = validate(obj, engine, terms_lookup)
    if errors:
        return {"engine": engine, "errors": errors, "warnings": warnings,
                "prompt": None, "timeline": False}

    prompt_obj, timeline = build_prompt_object(obj, engine)
    prompt_str = json.dumps(
        prompt_obj, ensure_ascii=False,
        indent=None if compact else 2,
        separators=(",", ":") if compact else None,
    )

    hard = spec.get("prompt_max")
    soft = spec.get("prompt_recommended")
    if hard and len(prompt_str) > hard:
        return {"engine": engine, "warnings": warnings, "timeline": timeline,
                "prompt": None,
                "errors": [f"prompt is {len(prompt_str)} chars; "
                           f"{spec['label']} caps it at {hard}."]}
    if soft and len(prompt_str) > soft:
        warnings.append(
            f"prompt is {len(prompt_str)} chars; {spec['label']} recommends "
            f"<= {soft}. Trim before submitting — truncation would drop the "
            "tail of the prompt."
        )

    settings_key, settings = build_settings(obj, prompt_str, engine)

    if emit == "prompt":
        payload: dict = {"prompt": prompt_str}
    elif emit == "input":
        payload = {settings_key: settings}
    else:
        payload = {"prompt": prompt_str, settings_key: settings}

    # On engines with a real negative field, hand it back separately — it must be
    # typed into the provider's own box, NOT pasted with the prompt.
    if spec["negative"] == "param" and emit != "prompt":
        negative = resolve_negative(obj)
        if negative:
            payload["negative_prompt"] = negative

    return {**payload, "engine": engine, "timeline": timeline,
            "warnings": warnings, "errors": []}
