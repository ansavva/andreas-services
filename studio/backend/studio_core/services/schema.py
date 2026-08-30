"""The live Replicate input schema, and the payload check that runs off it.

Moved from the pipeline's `engine/schema.py`, unchanged in what it decides. It
came here with the submission because it is the check that has to run on the
**submitting** side: a payload validated in the CLI and then sent by the API
would be two opinions about one request, and the SPA — which never had a copy —
would have had none at all.

Every model takes DIFFERENT inputs. Not just different field NAMES (one engine's
`image` is another's `start_image`) but different *value* vocabularies for fields
that look identical: `aspect_ratio` accepts `match_input_image` on one model,
`2048x2048` on a second, and only `1:1 | 3:2 | 2:3` on a third. A payload that is
correct for one model is therefore not merely suboptimal on another — it is
rejected, after the run record has already been written and, worse, after the
transition to `pending` has already been made.

So nothing is hardcoded here. The authority is the model's own schema, fetched
live and checked before the prediction is created.

**Nothing here distils a schema into the registry's `snapshot` form, and the
asymmetry is deliberate.** `models.json` is the pipeline's file — `studio models
refresh` and `studio add-model` are what write it — so the distillation lives
there, beside the file, and this service returns the raw schema and has no
opinion about it. A copy here would be a second distillation of one document.

**`services/registry.py` and this module are not the same answer twice.** The
registry is what studio has *decided* about a model — which fields carry images,
what the reference cap is, what the docs forbid that the schema permits. This is
what the provider will *accept* today. The registry ships in the image and can be
months old; the schema is fetched per submission, which is what catches a model
whose enum changed under a committed snapshot.
"""

import logging

from studio_core.clients import replicate
from studio_core.errors import ValidationError

logger = logging.getLogger(__name__)


class SchemaError(ValidationError):
    """A payload the target model will not accept — raised before anything bills.

    **A `ValidationError`, not merely something like one.** It is the caller's
    request that is wrong, and `app_factory` maps that type to 400 — so
    subclassing is what stops a refused payload reaching the generic handler and
    coming back as `Internal error`, which would report a fixable mistake as an
    outage. It is its own type only so a caller can catch it specifically.
    """


def fetch(model: str) -> tuple[dict, dict]:
    """`(input properties, all component schemas)` for `owner/name`.

    A provider failure comes back as empty maps rather than as an exception, and
    `check` reports a skipped validation. That is deliberate and it is a
    trade-off worth naming: a schema fetch that 500s must not be the thing that
    stops a payload a person has already approved, because the authoritative
    refusal is Replicate's own and this check only exists to make it cheaper and
    earlier.
    """
    try:
        return replicate.model_schema(model)
    except replicate.ReplicateError as exc:
        logger.warning("Could not fetch the input schema for %s: %s", model, exc)
        return {}, {}


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


def check(payload: dict, bindings: dict, model: str, props: dict,
          schemas: dict) -> list[str]:
    """Reject anything `model` will not accept. Raises on the first fault.

    Checks unknown fields, enum membership, and numeric range. `bindings` are
    checked for field NAME only — their values are node ids here and become
    presigned URLs later, so there is nothing to range-check.

    **The `alternatives` argument the pipeline's version took is gone.** It
    fetched every sibling model's schema on the error path so the message could
    say which model *does* take an unknown field, which was worth a handful of
    extra HTTP calls in a terminal a person is watching. Inside a request that a
    person is waiting on it is up to eight serial round trips to a third party
    before a 400, so the message names the model's own valid inputs and stops.
    """
    if not props:
        return ["could not fetch the model's input schema; skipping validation"]

    unknown = [k for k in list(payload) + list(bindings) if k not in props]
    if unknown:
        raise SchemaError(
            f"{model} does not accept: {sorted(unknown)}. "
            f"Valid inputs: {sorted(props)}"
        )

    for key, value in payload.items():
        spec = props.get(key, {})
        allowed = enum_of(spec, schemas)
        if allowed and value not in allowed:
            raise SchemaError(f"{model}: {key}={value!r} is not one of {allowed}")
        if spec.get("type") in ("integer", "number") and isinstance(value, (int, float)):
            low, high = spec.get("minimum"), spec.get("maximum")
            if low is not None and value < low or high is not None and value > high:
                raise SchemaError(
                    f"{model}: {key}={value} is outside the allowed range [{low}, {high}]"
                )
    return []


def check_denied(payload: dict, entry: dict, model: str) -> None:
    """Enforce documented constraints the SCHEMA does not.

    The generated schema is occasionally more permissive than the model — it
    offers `background: transparent` on gpt-image-2, which the docs say is
    unsupported. Such a value validates and is then not honoured, so the registry
    records it under `denied` and it is rejected here, first.
    """
    for field, blocked in (entry.get("denied") or {}).items():
        if field in payload and payload[field] in blocked:
            raise SchemaError(
                f"{model}: {field}={payload[field]!r} — {blocked[payload[field]]}"
            )
