"""model_schema.py — the live Replicate input schema, shared by every studio-* engine.

Every model takes DIFFERENT inputs. Not just different field NAMES (one engine's
`image` is another's `start_image`) but different *value* vocabularies for fields
that look identical: `aspect_ratio` accepts `match_input_image` on one model,
`2048x2048` on a second, and only `1:1 | 3:2 | 2:3` on a third. A payload that is
correct for one model is therefore not merely suboptimal on another — it is
rejected, after the run record has already been written.

So nothing is hardcoded here. The authority is the model's own schema, fetched
live and checked before anything is recorded or billed:

    props, schemas = fetch("openai/gpt-image-2", token)
    check(payload, bindings, "openai/gpt-image-2", props, schemas)

`check` raises SchemaError; callers turn that into their own `die()`. Used by
`submit.py` for every model in the registry, and by `studio.py models show`, so
a payload gets the same scrutiny whichever model it is aimed at.
"""


from studio_pipeline.engine import replicate_api as RA  # noqa: E402


class SchemaError(Exception):
    """A payload the target model will not accept — raised before anything bills."""


def fetch(model: str, token: str) -> tuple[dict, dict]:
    """Return (input properties, all component schemas) for `owner/name`.

    Both halves are needed: enums frequently live behind a `$ref` to a sibling
    component rather than inline on the property itself.
    """
    try:
        body = RA.api("GET", f"{RA.API_ROOT}/models/{model}", token)
    except RA.ReplicateError as e:
        raise SchemaError(str(e))
    schemas = (
        (body.get("latest_version") or {})
        .get("openapi_schema", {}).get("components", {}).get("schemas", {})
    )
    return schemas.get("Input", {}).get("properties", {}), schemas


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
    checked for field NAME only — their values are S3 keys here and become
    presigned URLs later, so there is nothing to range-check.

    `alternatives` maps sibling model name -> its input properties. When a field
    is unknown here but valid there, the error names the model that takes it,
    which is the actual question being asked ("then how do I set this?").
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


def snapshot(props: dict, schemas: dict) -> dict:
    """Distil a schema into the enum/range facts offline tools need.

    Written into the registry by `studio.py models refresh`. Advisory only —
    anything that submits re-validates against the live schema.
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
