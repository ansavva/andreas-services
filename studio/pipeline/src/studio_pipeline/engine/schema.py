"""The live Replicate input schema, read through the API.

Every model takes DIFFERENT inputs. Not just different field NAMES (one engine's
`image` is another's `start_image`) but different *value* vocabularies for fields
that look identical: `aspect_ratio` accepts `match_input_image` on one model,
`2048x2048` on a second, and only `1:1 | 3:2 | 2:3` on a third. A payload that is
correct for one model is therefore not merely suboptimal on another — it is
rejected, after the run record has already been written.

So nothing is hardcoded here. The authority is the model's own schema, fetched
live and checked before a draft is written.

## This module used to hold a Replicate client, and now holds none

`fetch` was `GET https://api.replicate.com/v1/models/<owner>/<name>` with a
bearer token, through `adapters/replicate.py`. It is
`GET /api/models/<name>/schema` now, and the token is the API's.

**That is the whole reason the CLI no longer has a provider credential.** When
generation moved into the API, three commands were left reaching Replicate for
things that never spend anything — `studio models show`, `studio models refresh`
and `studio add-model` — and each of them was a reason to keep
`REPLICATE_API_TOKEN` on every developer's machine. Routing the read through the
API costs one hop and removes the credential.

## The check still happens twice, on purpose

This runs client-side, before the draft is written, so a payload the model will
refuse never becomes a row and the error names `studio convert` or the sibling
model that does take the field. The API runs its own copy — `services/schema.py`
— at submit time, because the SPA also submits and never passes through here.

That is two implementations of one rule, which is normally the thing to avoid.
It is deliberate here because they are not the same rule: this one is a courtesy
that produces a better message, and that one is the gate. If they ever disagree
the API wins, and the worst outcome is a draft that is refused a moment later
than it could have been.
"""


from studio_pipeline.adapters import api
from studio_pipeline.adapters import entities


class SchemaError(Exception):
    """A payload the target model will not accept — raised before anything bills."""


def fetch(model: str) -> tuple[dict, dict]:
    """Return (input properties, all component schemas) for `owner/name`.

    Both halves are needed: enums frequently live behind a `$ref` to a sibling
    component rather than inline on the property itself.

    **No token argument, and every caller lost one.** The API holds the
    credential; this asks the API. A failure is a `SchemaError` exactly as it was
    when the failure was Replicate's own, because every caller already handles
    that and the distinction between "the provider refused" and "our API could
    not reach the provider" is not one a person at a terminal can act on
    differently.
    """
    try:
        found = entities.model_schema(model)
    except api.ApiError as exc:
        raise SchemaError(f"could not read the input schema for {model}: {exc}") from exc
    return (found or {}).get("props") or {}, (found or {}).get("schemas") or {}


def snapshot(props: dict, schemas: dict) -> dict:
    """Distil a schema into the enum/range facts offline tools need.

    Written into the registry by `studio models refresh` and by `studio
    add-model`. Advisory only — anything that submits re-validates against the
    live schema, which is why a stale snapshot is survivable.

    **Pure, and it stayed here when the fetch left.** The API could have returned
    a distilled form off the same read, and briefly did; that made this a second
    distillation of one document. It is the other way round: `models.json` is the
    pipeline's file, so the only thing that distils a schema into it is the
    pipeline, and the API returns the raw schema and has no opinion about it.
    Keeping it pure also keeps `add_model.infer` a function of its arguments,
    which is what lets it be tested without a wire at all.
    """
    out: dict = {}
    for key, spec in props.items():
        entry: dict = {}
        allowed = enum_of(spec, schemas)
        if allowed:
            entry["enum"] = allowed
        if spec.get("default") is not None:
            entry["default"] = spec["default"]
        for bound in ("minimum", "maximum"):
            if spec.get(bound) is not None:
                entry[bound] = spec[bound]
        if entry:
            out[key] = entry
    return out


def enum_of(spec: dict, schemas: dict) -> list | None:
    """An input's allowed values, following a `$ref` when the enum is indirect."""
    if spec.get("enum"):
        return spec["enum"]
    for sub in spec.get("allOf") or []:
        if sub.get("enum"):
            return sub["enum"]
        ref = sub.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            target = schemas.get(ref.rsplit("/", 1)[-1], {})
            if target.get("enum"):
                return target["enum"]
    return None


def check(
    payload: dict,
    bindings: dict,
    model: str,
    props: dict,
    schemas: dict,
    alternatives: dict[str, dict] | None = None,
) -> list[str]:
    """Reject anything `model` will not accept. Raises SchemaError on the first fault.

    Checks unknown fields, enum membership, and numeric range. `bindings` are
    checked for field NAME only — their values are node ids here and become
    presigned URLs later, so there is nothing to range-check.

    `alternatives` maps sibling model name -> its input properties. When a field
    is unknown here but valid there, the error names the model that takes it,
    which is the actual question being asked ("then how do I set this?"). The
    API's copy of this check drops that argument deliberately: it is worth a
    handful of extra round trips in a terminal a person is watching, and is not
    worth them inside a request a person is waiting on.
    """
    if not props:
        return ["could not fetch the model's input schema; skipping validation"]

    unknown = [k for k in list(payload) + list(bindings) if k not in props]
    if unknown:
        lines = [f"{model} does not accept: {sorted(unknown)}"]
        for field in sorted(unknown):
            takers = sorted(m for m, p in (alternatives or {}).items() if field in p)
            if takers:
                lines.append(f"  `{field}` is accepted by: {', '.join(takers)}")
        lines.append(f"  valid inputs: {sorted(props)}")
        raise SchemaError("\n".join(lines))

    for key, value in payload.items():
        spec = props.get(key, {})
        allowed = enum_of(spec, schemas)
        if allowed and value not in allowed:
            raise SchemaError(f"{model}: {key}={value!r} is not one of {allowed}")
        if spec.get("type") in ("integer", "number") and isinstance(value, (int, float)):
            lo, hi = spec.get("minimum"), spec.get("maximum")
            if lo is not None and value < lo or hi is not None and value > hi:
                raise SchemaError(
                    f"{model}: {key}={value} is outside the allowed range [{lo}, {hi}]"
                )
    return []


def check_denied(payload: dict, entry: dict, model: str) -> None:
    """Enforce documented constraints the SCHEMA does not.

    The generated schema is occasionally more permissive than the model — it
    offers `background: transparent` on gpt-image-2, which the docs say is
    unsupported. Such a value validates and is then not honoured, so the
    registry records it under `denied` and it is rejected here, first.
    """
    for field, blocked in (entry.get("denied") or {}).items():
        if field in payload and payload[field] in blocked:
            raise SchemaError(f"{model}: {field}={payload[field]!r} — {blocked[payload[field]]}")
