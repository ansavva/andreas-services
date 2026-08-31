"""The two hashes both halves of studio have to agree on, byte for byte.

`plan_digest` is what makes an approval mean something after the fact, and
`submission_fingerprint` is what stops the same payload being bought twice. Both
are pure functions of a plan and its ordered sends, and both are compared across
a wire: the CLI reads a digest off a run row and hands it back on `POST
/api/runs/<id>/approve`, and the API recomputes it and refuses a mismatch. A
disagreement between the two sides is therefore not a wrong answer — it is every
approval failing, or worse, one silently passing.

## Why this is a module of its own

**It lives here rather than in `catalog.py` so that the pipeline's test fake can
load the real thing instead of restating it.** `tests/support/fake_api.py` in the
pipeline already imports `services/storyboard.py` and `services/prompt.py` by
path, for exactly this reason and with the same precondition: a module the CLI's
unit suite loads must import neither Flask nor boto3, or the pipeline grows a
dependency on the backend's runtime. `catalog.py` imports both, so the digest
could not be reached from there and was copied — and `routes/runs.py` records
what that cost: three implementations in this repository, one of which silently
disagreed.

So this module imports `hashlib`, `json` and `decimal` and will not grow a
fourth. If it ever does, the pipeline's fake fails loudly at import, which is the
right way for this arrangement to stop working.

## Why the numbers are flattened first

`plain_numbers` is here rather than in `catalog.py` because agreement is what
needs it. A value that has been round-tripped through DynamoDB comes back as
`Decimal` for every number, and `Decimal("0.5")` and `0.5` do not serialise
alike — so a run hashed on the way in and rehashed on the way out would produce
two digests for one payload. `catalog.py` reads it from here for its own second
reason: `jsonify` refuses a `Decimal` outright.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal


def plain_numbers(value):
    """Turn every `Decimal` a read hands back into an int or a float.

    Integral values come back as `int`, so a `rev` reads as `7` rather than
    `7.0` — a client comparing the two would be right to be confused.

    Walks, rather than converting one field: an entity record has `rev`, three
    `counts`, a reference `order` and a `cost.amount` nested two deep.
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: plain_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain_numbers(item) for item in value]
    return value


def plan_digest(plan: dict | None, send_entries: list[dict]) -> str:
    """A hash over everything a person approves: the plan AND the images.

    **This is what makes an approval mean something after the fact.** Hard rule
    #2 says re-approve after *any* edit, and until it existed nothing checked
    it: the approval was a `y` at a terminal and the payload could be edited
    afterwards with no trace. An approval records the digest it was given, `POST
    /api/runs/<id>/approve` refuses one that no longer matches, and the submit
    transition refuses a run whose recorded digest has gone stale.

    The sends are hashed by `(field, role, node)` and their ORDER — swapping two
    reference images changes what the model is shown, and a prompt citing "the
    first image" makes that change material rather than cosmetic. `source` is
    excluded: it is provenance for a reader, and re-deriving it more accurately
    later must not invalidate an approval nobody's payload changed.
    """
    payload = plain_numbers({
        "plan": plan or {},
        "sends": [
            {"field": entry.get("field"), "role": entry.get("role"),
             "node": entry.get("node")}
            for entry in send_entries or []
        ],
    })
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def submission_fingerprint(model: str | None, plan: dict | None,
                           send_entries: list[dict]) -> str:
    """What makes two submissions the same one, projected so a query can find it.

    **This retires a local file.** `engine/ledger.py` kept a per-machine list of
    recently submitted payload hashes because a batch of 72 upscales was driven
    twice — the harness reported the job finished when it had not, both passes
    ran, ~46 images were generated twice and about $2.30 bought results that
    overwrote each other. Nothing noticed, because `run` builds a payload and
    sends it and every send is the first one as far as the pipeline knows.

    Its own docstring named the right fix and declined to build it: the run store
    could answer this, but the listing rows are a small projection and do not
    carry the payload, so comparing meant one `GET /api/runs/<id>` per candidate
    — on the order of 1800 requests before the first submit of that batch. So it
    projects a fingerprint onto the listing row, and `GET /api/runs?fingerprint=`
    is one query.

    **Derived from `plan_digest` rather than hashed independently.** The plan IS
    the payload and the sends ARE the bindings, so a second hash over the same
    material would be a second answer to "is this the same submission" — and the
    two would drift the first time either changed what it included. Only the
    model is added, because two identical plans on different engines are
    different submissions.

    What this catches that the local file could not: a second machine, and a
    colleague. What it still does not catch is a payload assembled differently
    for the same intent — a fingerprint is a guard rail, not a lock.
    """
    return "sha256:" + hashlib.sha256(
        f"{model or ''}\n{plan_digest(plan, send_entries)}".encode()
    ).hexdigest()[:32]
