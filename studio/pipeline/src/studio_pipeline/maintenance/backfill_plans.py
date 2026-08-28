"""`studio catalog backfill-plans` — give every run that predates the plan one.

A run gained an AUTHORED half: `plan` (the prompt and the params a person chose)
and `SEND#` rows (each bound image, its role, and where it came from). Runs made
before that have neither, so the app can show what came out of them and never
what they were for.

**This reconstructs it, and the reconstruction is total rather than partial.**
Measured against production on 2026-08-27: 254 runs, 254 with `request.json`,
254 with `bindings`, three distinct models and every one still in the registry.
Not one run needs a guess.

    request.json  {"model": …, "input": {prompt, aspect_ratio, quality, …}}
                                │                └──────────► plan.params
                                └───────────────────────────► plan.prompt

    bindings      {"input_images": [n1 … n6]}
                   │  field name              ──────────────► send.field
                   │  models.json[…].images   ──────────────► send.role
                   └  position in the list    ──────────────► SEND#0001 … n

`source` — which character group, which run output, which input-pool position —
is NOT computed here. `catalog.source_of` derives it in the API from where each
node sits, so a run submitted today and a run reconstructed from history describe
their images in identical words rather than in two dialects.

WHY IT PARSES `request.json` WHEN THE API MAY NOT
-------------------------------------------------
The rule is that the *service* never decodes that document: the pipeline changes
its shape freely, so route code reading a key inside one becomes wrong without
notice. This is the pipeline. It is where that shape is owned, and it is the same
division the retired `catalog_migrate.py` worked under when it turned run
documents into envelopes.

WHY IT WRITES TO DYNAMODB RATHER THAN THROUGH THE API
------------------------------------------------------
Because the alternative was worse. `PATCH /api/runs/<id>/plan` refuses a run that
has been submitted — a plan edited after the fact would sit beside `request.json`
describing something that was never sent — and that refusal is load-bearing. A
backfill route that could rewrite a submitted run's plan would be a hole in it,
kept forever for a one-shot. So this joins `catalog gc` and `catalog verify` as a
maintenance command holding its own AWS clients, which is what the profile is
for: `studio --profile prod catalog backfill-plans`.

WHY THERE IS NO JOURNAL
-----------------------
`catalog gc` and `catalog reseat` journal because they DELETE, and `reseat`
refuses to run until the journal says a verify passed. This adds attributes and
rows, deletes nothing, touches no object in S3, and skips any run that already
has a plan — so a second run reports zero and changes nothing. `--apply` exists
so a person reads the report first, not because the write needs guarding.

WHAT IT WILL NOT DO
-------------------
Nothing is invented. A run whose `request.json` is missing or unparseable, or
whose model has left the registry, is REPORTED and skipped — and `--apply`
refuses while any remain, which is the discipline the entity-model migration ran
under (`UNPARSEABLE must be 0`). A plausible plan over a run nobody can check is
worse than a run with no plan.

**One gap cannot be closed by anything, and it is stated rather than papered
over.** Before angle images became catalog nodes they travelled through `gather`
marked `shared:<key>` and were stripped before the record was written
(`engine/submit.py`). Runs from that era under-report their images, and no
reconstruction can recover what was never recorded. They are counted in the
report as `plates_unknowable`.
"""
from __future__ import annotations

import collections
import json

import click

from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.engine import registry as REG
from studio_pipeline.errors import reports

#: What a run's plan says about where it came from. `authored` is written by
#: `engine/submit.py` when a person made it; this writes the other one, and the
#: difference is visible on the run page rather than implied.
ORIGIN = "backfilled"

#: Who a backfilled approval names. **Not a person**, deliberately: nobody
#: consented in a browser to a run made in August, and a row claiming they did
#: would be a lie a future reader cannot detect. The mechanism names itself.
APPROVED_BY = "backfill"


class BackfillError(Exception):
    """A run that cannot be reconstructed without guessing."""


# ── reading what is already recorded ────────────────────────────────────────


def runs_in(ddb) -> list[dict]:
    """Every run envelope in the table, oldest first.

    A scan, because this is a one-shot over the whole library and the alternative
    — walking projects and their listing rows — costs more requests to answer the
    same question. Oldest first so a partial `--apply` is resumable in the order
    a person would expect.
    """
    # `ddbc.scan` already unmarshals, so these are plain dicts — the raw
    # `{"S": …}` shape never reaches here.
    found = [item for item in ddbc.scan(ddb)
             if str(item.get("pk", "")).startswith("RUN#")
             and item.get("sk") == "META"]
    return sorted(found, key=lambda run: run.get("created") or "")


def request_document(s3, bucket: str, ddb, node_id: str) -> dict:
    """`request.json`, read through its node and parsed. **Pipeline-side only.**"""
    item = ddb.get_item(TableName=ddbc.table(),
                        Key={"pk": {"S": f"NODE#{node_id}"}, "sk": {"S": "META"}})
    node = ddbc.from_item(item.get("Item") or {})
    if not node:
        raise BackfillError(f"payload node {node_id} has no row")
    key = node.get("blob_key")
    if not key:
        raise BackfillError(f"payload node {node_id} has no blob")
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BackfillError(f"{node_id} is not valid JSON: {exc}") from exc


# ── the reconstruction ──────────────────────────────────────────────────────


def plan_from(document: dict) -> dict:
    """`request.json` -> the authored half.

    `input` holds the prompt and the params and **no image fields** — those were
    presigned in after the record was written, which is exactly why this is
    lossless. Verified against a real production document before it was relied
    on: `{aspect_ratio, output_format, prompt, quality}`, and nothing else.
    """
    payload = dict(document.get("input") or {})
    prompt = payload.pop("prompt", None)
    return {"version": 1, "origin": ORIGIN, "prompt": prompt, "params": payload}


def roles_for(model: str) -> dict[str, str]:
    """Which model input means what, read off the registry rather than guessed.

    `images.start`, `.end` and `.refs` are the field names this model binds, so
    the mapping from a stored binding's field to a send's role is exact. A model
    the registry has never heard of gets no mapping and the run is skipped —
    guessing that a field called `image` is a start frame would be inventing the
    one thing a person would rely on.
    """
    for entry in REG.all().values():
        if entry["model"] != model:
            continue
        images = entry.get("images") or {}
        return {images[name]: role
                for name, role in (("start", "start"), ("end", "end"),
                                   ("refs", "reference"))
                if images.get(name)}
    raise BackfillError(f"model {model!r} is not in the registry")


def sends_from(bindings: dict, roles: dict[str, str]) -> list[dict]:
    """The stored map, in order, as send rows. `source` is the API's to derive."""
    return [
        {"field": field, "role": roles.get(field, "input"), "node": node}
        for field, value in (bindings or {}).items()
        for node in (value if isinstance(value, list) else [value])
    ]


def approval_for(run: dict, digest: str) -> dict:
    """A stamp naming when the payload was actually consented to.

    **`at` is the run's `created`, and it is a real timestamp rather than a
    convenient one.** `engine/submit.py` calls `record_request` immediately after
    the terminal confirm returns, so the row's creation is within milliseconds of
    the moment somebody said yes. `by` names the mechanism, not a person, because
    nobody approved these in a browser and a row implying they had would be
    undetectable later.
    """
    return {"by": APPROVED_BY, "at": run.get("created"), "digest": digest}


def plan_digest(plan: dict | None, sends: list[dict]) -> str:
    """The digest, spelled as `services/catalog.plan_digest` spells it.

    A third implementation of one hash, and the reason is the same one that makes
    `derive.extension` a copy of `keys.extension`: the pipeline does not import
    the backend package. What holds them together is that a wrong digest here is
    not silent — `catalog verify` recomputes it server-side, and a backfilled run
    whose stored digest disagrees with its own plan reports as stale on its own
    page.
    """
    import decimal
    import hashlib

    def plain(value):
        """`Decimal` back to the number it was. **Load-bearing, not tidiness.**

        Every number read out of DynamoDB is a `Decimal`, and `json.dumps` with
        `default=str` renders one as the STRING `"0.8"` where the float renders
        as the number `0.8`. So a digest computed before the write and the same
        digest recomputed after reading the row back disagreed — which is how
        `catalog verify` came to report `stale_plan_digest` over a run whose
        plan was perfectly intact, and it would have said so about all 131
        upscales. `services/catalog.py::plan_digest` normalises for exactly this
        reason and this copy did not.
        """
        if isinstance(value, decimal.Decimal):
            return (int(value) if value == value.to_integral_value()
                    else float(value))
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        return value

    payload = plain({
        "plan": plan or {},
        "sends": [{"field": s.get("field"), "role": s.get("role"),
                   "node": s.get("node")} for s in sends or []],
    })
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def reconstruct(run: dict, document: dict) -> dict:
    """One run's plan, sends, digest and approval — or `BackfillError`."""
    plan = plan_from(document)
    sends = sends_from(run.get("bindings") or {}, roles_for(run.get("model")))
    digest = plan_digest(plan, sends)
    return {"plan": plan, "sends": sends, "plan_digest": digest,
            "approval": approval_for(run, digest)}


# ── writing ─────────────────────────────────────────────────────────────────


def _send_sk(order: int) -> str:
    """`SEND#0007`, zero-padded exactly as the API pads it.

    Four digits because the key IS the order: `SEND#10` sorts before `SEND#2` as
    a string, and a prompt citing "the first image" would then be about a
    different picture.
    """
    return f"SEND#{order:04d}"


def write(ddb, run: dict, built: dict) -> None:
    """The envelope's new attributes, then the send rows.

    Envelope first: a run carrying a plan and no sends reads as a run that bound
    nothing, which is wrong but visible; sends with no plan would be rows nothing
    points at. Neither order is transactional across the 25-item limit, and
    re-running repairs either — which is the property that makes a journal
    unnecessary here.
    """
    ddb.update_item(
        TableName=ddbc.table(),
        Key={"pk": {"S": f"RUN#{run['id']}"}, "sk": {"S": "META"}},
        UpdateExpression="SET #p = :p, #d = :d, #a = :a",
        ExpressionAttributeNames={"#p": "plan", "#d": "plan_digest",
                                  "#a": "approval"},
        ExpressionAttributeValues={
            # `to_map`, not `to_item`: a plan is a VALUE map and its `None`s are
            # real answers. Dropping `prompt: None` for a promptless model made
            # the stored plan a different document from the one that was hashed,
            # so every upscale run reported its own payload as changed.
            ":p": {"M": ddbc.to_map(built["plan"])},
            ":d": {"S": built["plan_digest"]},
            ":a": {"M": ddbc.to_item(built["approval"])},
        },
    )
    for order, send in enumerate(built["sends"], 1):
        ddb.put_item(
            TableName=ddbc.table(),
            Item={"pk": {"S": f"RUN#{run['id']}"},
                  "sk": {"S": _send_sk(order)},
                  **ddbc.to_item({"field": send["field"], "role": send["role"],
                                  "node": send["node"],
                                  # Left for the API to fill: `source_of` derives
                                  # it from where the node sits, and a second
                                  # derivation here would be a second dialect.
                                  "source": None,
                                  "created": run.get("created")}),
                  })


# ── the command ─────────────────────────────────────────────────────────────


@click.command("backfill-plans")
@click.option("--apply", "apply_", is_flag=True,
              help="Write. Without it this reports and changes nothing.")
@click.option("--limit", type=int, help="Stop after this many runs (for a trial).")
@reports(BackfillError)
def cmd_backfill_plans(apply_, limit):
    """Reconstruct the authored half of every run that predates it.

    Reports first, always. `--apply` refuses while any run cannot be
    reconstructed, because a library where some runs have a plan and some have a
    guess is worse than one where the old runs plainly have neither.
    """
    ddb = ddbc.client()
    s3 = s3c.client()
    bucket = s3c.bucket()

    runs = runs_in(ddb)
    if limit:
        runs = runs[:limit]

    ready: list[tuple[dict, dict]] = []
    skipped = collections.Counter()
    problems: list[str] = []
    plates_unknowable = 0

    for run in runs:
        if run.get("plan"):
            skipped["already has a plan"] += 1
            continue
        if run.get("status") in ("draft", "approved", "discarded"):
            skipped["unsubmitted"] += 1
            continue
        request = (run.get("payload") or {}).get("request")
        if not request:
            problems.append(f"{run['id']}: no request.json")
            continue
        try:
            document = request_document(s3, bucket, ddb, request)
            built = reconstruct(run, document)
        except BackfillError as exc:
            problems.append(f"{run['id']}: {exc}")
            continue
        # A run that bound nothing at all predates angle images having nodes, or was a
        # deliberate text-only generation. The two are indistinguishable from
        # here, so it is counted rather than diagnosed.
        if not built["sends"]:
            plates_unknowable += 1
        ready.append((run, built))

    print(f"runs scanned:        {len(runs)}")
    print(f"reconstructable:     {len(ready)}")
    for reason, count in sorted(skipped.items()):
        print(f"skipped ({reason}): {count}")
    print(f"UNRECONSTRUCTABLE:   {len(problems)}")
    for line in problems[:20]:
        print(f"  {line}")
    if len(problems) > 20:
        print(f"  … and {len(problems) - 20} more")
    if plates_unknowable:
        print(f"note: {plates_unknowable} run(s) bound no images at all — either a "
              f"text-only generation, or from before angle images had nodes and "
              f"were stripped before the record was written. Not recoverable.")

    if not apply_:
        print("\n(dry run — nothing written. Re-run with --apply.)")
        return

    if problems:
        raise BackfillError(
            f"{len(problems)} run(s) cannot be reconstructed without guessing; "
            f"refusing to write a partial backfill.")

    for run, built in ready:
        write(ddb, run, built)
    print(f"\nwrote plans and sends for {len(ready)} run(s).")
