"""Submitting a draft that already exists — the second half of a split submission.

`studio run` drafts, approves and submits in one act, because invoking it
without `--dry-run` is the request to submit. This is the other shape: a draft
was left by `--dry-run` or by the app, somebody read it and approved it, and now
it has to go out.

**Nothing here decides anything.** The payload is read back off the record rather
than rebuilt from arguments — a payload assembled a second time would be a second
opinion about what was approved, and approving one thing while submitting another
is the exact gap the digest exists to close. So this module reconstructs the
provider input from `plan`, the bindings from the run's own sends, and hands both
to the one submit lifecycle every other caller uses.

It is a module of its own rather than a function in `submit.py` because
`domain/runs.py` calls it and `domain` does not import `engine` at module level.
"""
from __future__ import annotations

import types

from studio_pipeline.adapters import entities
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import submit as SUB


def payload_of(record: dict) -> dict:
    """The provider input, rebuilt from the plan and from nothing else.

    `plan.params` plus `plan.prompt`, which is exactly what `plan_of` took apart
    when the draft was written. Image fields are absent on purpose: they are
    sends, and they are presigned in at the last moment by `submit`.
    """
    plan = record.get("plan") or {}
    payload = dict(plan.get("params") or {})
    if plan.get("prompt") is not None:
        payload["prompt"] = plan["prompt"]
    return payload


def bindings_of(record: dict, entry: dict | None = None) -> dict:
    """The run's sends, back in the shape `gather` produces and `submit` binds.

    Order within a field is the order of the send rows, which is the order the
    model is handed — and which a prompt citing "the first image" depends on.

    **A start or end frame is a SCALAR, not a one-item list**, and that asymmetry
    is the provider's rather than ours: `reference_images` is an array while
    `start_image` is a string, so `submit` presigns a list into a list and a
    scalar into a scalar. Rebuilding every field as a list sent
    `{"start_image": ["https://…"]}` and Replicate answered
    `422 Invalid type. Expected: string, given: array` — after the run had been
    patched to `pending`, so a draft that `studio run` would have submitted
    happily wedged instead. Which fields are scalar is registry data
    (`images.start` / `images.end`), the same source `sends_for` reads to give
    each send its role, so this asks the entry rather than guessing from a name.
    """
    bindings: dict[str, list[str] | str] = {}
    for send in record.get("sends") or []:
        bindings.setdefault(send["field"], []).append(send["node"])
    images = (entry or {}).get("images") or {}
    for name in ("start", "end"):
        field = images.get(name)
        if field and field in bindings:
            bindings[field] = bindings[field][0]
    return bindings


def entry_for(record: dict):
    """The registry entry this run was drafted against, found by model id.

    By `model` rather than by `engine`: `engine` records the skill name, which is
    prose that has been renamed before, while the model id is what the provider
    is actually called and what the registry is keyed on in practice.
    """
    for entry in REG.all().values():
        if entry["model"] == record.get("model"):
            return entry
    raise SUB.SubmitError(
        f"run {record['id']} names model {record.get('model')!r}, which is not in "
        f"the registry — see `studio models`.")


def submit_draft(record: dict, token: str | None = None) -> dict:
    """Send an approved draft. Returns the closed run record.

    The token is fetched the same way `studio run` fetches it, so a draft
    submitted here bills identically to one submitted in one command.
    """
    entry = entry_for(record)
    payload = payload_of(record)
    bindings = bindings_of(record, entry)
    project = entities.get_project(record["project"])

    # `submit` reads a handful of attributes off `args`, and a draft has already
    # settled every one of them. A namespace carrying just those is honest about
    # that: there is nothing left to decide here, and a full argument parser
    # would invite something to be decided differently the second time.
    args = types.SimpleNamespace(
        project=project,
        name=_output_name(record),
        poll=True,
        interval=SUB.defaults(record["kind"])["interval"],
        timeout=SUB.defaults(record["kind"])["timeout"],
        dest=None,
    )
    return SUB.submit(entry, record, payload, bindings,
                      token or _token(), args)


def _output_name(record: dict) -> str:
    """What the downloaded file is called. A filename, never an identity."""
    return (record.get("plan") or {}).get("name") or record["kind"]


def _token() -> str:
    """The provider token, loaded exactly as `studio run` loads it."""
    from studio_pipeline.adapters import replicate as RA

    return RA.load_token()
