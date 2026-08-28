"""`studio catalog backfill-plans` — every run that predates the plan gets one.

A run gained an authored half — `plan`, and one `SEND#` row per bound image —
and every run made before that has neither. The claim these tests hold up is
that the reconstruction is **total rather than partial**: measured against
production, 254 runs, 254 with `request.json`, 254 with `bindings`, three models
and all three still in the registry. Nothing needs a guess.

So what is tested is mostly what it REFUSES to do. A plausible plan over a run
nobody can check is worse than a run that plainly has none, which is why a single
unreconstructable run stops the whole `--apply`.
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.maintenance import backfill_plans as BF


def _run_row(ddb, s3, run_id="run-1", *, model="google/nano-banana-pro",
             status="succeeded", bindings=None, request=True, body=None,
             plan=None):
    """A run exactly as one looks before the backfill: no plan, no send rows."""
    payload = {"request": None, "response": None, "prompt": None}
    if request:
        node_id = f"node-{run_id}-request"
        key = f"projects/proj-1/{node_id}.json"
        document = body if body is not None else {
            "model": model,
            "input": {"prompt": "a porch at dawn", "aspect_ratio": "9:16",
                      "output_format": "png", "quality": "high"},
        }
        s3.put_object(
            Bucket=s3c.bucket(), Key=key,
            Body=json.dumps(document).encode() if isinstance(document, dict)
            else document)
        ddb.put_item(TableName=ddbc.table(), Item={
            "pk": {"S": f"NODE#{node_id}"}, "sk": {"S": "META"},
            **ddbc.to_item({"node_id": node_id, "name": "request.json",
                            "blob_key": key, "kind": "file", "lib": "lib-1"})})
        payload["request"] = node_id

    row = {"id": run_id, "lib": "lib-1", "project": "proj-1", "status": status,
           "kind": "image", "engine": "e", "model": model,
           "created": "2026-08-01T10:00:00.000000+00:00",
           "bindings": bindings if bindings is not None else {
               "image_input": ["node-a", "node-b"]},
           "characters": [], "folder": "node-folder", "outputs": [],
           "payload": payload}
    if plan is not None:
        row["plan"] = plan
    ddb.put_item(TableName=ddbc.table(), Item={
        "pk": {"S": f"RUN#{run_id}"}, "sk": {"S": "META"}, **ddbc.to_item(row)})
    return run_id


def _invoke(*args):
    return CliRunner().invoke(cli.main, ["catalog", "backfill-plans", *args])


def _sends(ddb, run_id):
    items = ddb.query(
        TableName=ddbc.table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :s)",
        ExpressionAttributeValues={":pk": {"S": f"RUN#{run_id}"},
                                   ":s": {"S": "SEND#"}})["Items"]
    return [ddbc.from_item(item) for item in items]


def _record(ddb, run_id):
    return ddbc.from_item(ddb.get_item(
        TableName=ddbc.table(),
        Key={"pk": {"S": f"RUN#{run_id}"}, "sk": {"S": "META"}})["Item"])


# ── the reconstruction ──────────────────────────────────────────────────────


def test_the_prompt_and_the_params_come_straight_out_of_request_json():
    """**Lossless because `input` holds no image fields.**

    They were presigned in after the record was written, so what is stored is the
    prompt and the params and nothing else — verified against a real production
    document before this was relied on.
    """
    plan = BF.plan_from({"model": "m", "input": {
        "prompt": "a porch", "aspect_ratio": "9:16", "quality": "high"}})

    assert plan["prompt"] == "a porch"
    assert plan["params"] == {"aspect_ratio": "9:16", "quality": "high"}
    assert plan["origin"] == "backfilled", "a reconstruction says so on the record"


def test_roles_come_from_the_registry_not_from_the_field_name():
    """Guessing that a field called `image` is a start frame would be inventing
    the one thing a person would rely on."""
    assert BF.roles_for("kwaivgi/kling-v3-omni-video") == {
        "start_image": "start", "end_image": "end",
        "reference_images": "reference"}


def test_a_model_that_has_left_the_registry_is_a_refusal():
    try:
        BF.roles_for("someone/deleted-model")
    except BF.BackfillError as exc:
        assert "not in the registry" in str(exc)
    else:
        raise AssertionError("a model with no registry entry must not be guessed")


def test_the_order_of_the_bindings_becomes_the_order_of_the_sends():
    """Position is the meaning: a prompt citing "the first image" depends on it."""
    sends = BF.sends_from({"image_input": ["node-a", "node-b", "node-c"]},
                          {"image_input": "reference"})

    assert [s["node"] for s in sends] == ["node-a", "node-b", "node-c"]
    assert {s["role"] for s in sends} == {"reference"}


def test_the_approval_names_the_mechanism_and_the_moment_it_really_happened():
    """**Not a person, and not `now`.**

    `record_request` is called immediately after the terminal confirm returns, so
    the row's `created` is within milliseconds of somebody actually saying yes —
    a real timestamp. `by` names the mechanism, because nobody approved these in
    a browser and a row implying they had would be undetectable later.
    """
    approval = BF.approval_for({"created": "2026-08-01T10:00:00+00:00"}, "sha256:x")

    assert approval == {"by": "backfill", "at": "2026-08-01T10:00:00+00:00",
                        "digest": "sha256:x"}


# ── the command ─────────────────────────────────────────────────────────────


def test_a_dry_run_reports_and_writes_nothing(bucket, catalog_table):
    _run_row(catalog_table, bucket)

    result = _invoke()

    assert result.exit_code == 0, result.output
    assert "reconstructable:     1" in result.output
    assert "nothing written" in result.output
    assert _record(catalog_table, "run-1").get("plan") is None


def test_applying_writes_the_plan_the_sends_and_the_approval(bucket, catalog_table):
    _run_row(catalog_table, bucket)

    result = _invoke("--apply")

    assert result.exit_code == 0, result.output
    record = _record(catalog_table, "run-1")
    assert record["plan"]["prompt"] == "a porch at dawn"
    assert record["plan"]["params"]["aspect_ratio"] == "9:16"
    assert record["approval"]["by"] == "backfill"
    assert record["plan_digest"].startswith("sha256:")
    assert [s["node"] for s in _sends(catalog_table, "run-1")] == ["node-a", "node-b"]


def test_the_send_rows_are_zero_padded_so_ten_sorts_after_two(bucket, catalog_table):
    """`SEND#10` sorts before `SEND#2` as a string, which would make plate *n*
    the wrong plate."""
    _run_row(catalog_table, bucket,
             bindings={"image_input": [f"node-{n:02d}" for n in range(1, 13)]})

    _invoke("--apply")

    assert [s["node"] for s in _sends(catalog_table, "run-1")] == [
        f"node-{n:02d}" for n in range(1, 13)]


def test_source_is_left_for_the_api_to_derive(bucket, catalog_table):
    """**One dialect.** `catalog.source_of` computes provenance from where a node
    sits, so a run submitted today and a run reconstructed from history describe
    their images in identical words. A second derivation here would be a second
    answer."""
    _run_row(catalog_table, bucket)

    _invoke("--apply")

    assert all(send.get("source") is None for send in _sends(catalog_table, "run-1"))


def test_it_is_idempotent(bucket, catalog_table):
    """A second run reports zero and changes nothing — which is the property that
    makes a journal unnecessary, unlike `catalog gc`."""
    _run_row(catalog_table, bucket)
    _invoke("--apply")

    again = _invoke()

    assert "reconstructable:     0" in again.output
    assert "skipped (already has a plan): 1" in again.output


def test_a_draft_is_left_alone(bucket, catalog_table):
    """It was never missing a plan — it has one because a person wrote it."""
    _run_row(catalog_table, bucket, run_id="run-draft", status="draft")

    result = _invoke()

    assert "skipped (unsubmitted): 1" in result.output


def test_one_unreconstructable_run_stops_the_whole_apply(bucket, catalog_table):
    """**A library where some runs have a plan and some have a guess is worse
    than one where the old runs plainly have neither.**

    The same discipline the entity-model migration ran under: UNPARSEABLE must be
    0 before anything is written.
    """
    _run_row(catalog_table, bucket, run_id="run-ok")
    _run_row(catalog_table, bucket, run_id="run-bad", request=False)

    result = _invoke("--apply")

    assert result.exit_code != 0
    assert "UNRECONSTRUCTABLE:   1" in result.output
    assert _record(catalog_table, "run-ok").get("plan") is None, (
        "a partial backfill is refused, not attempted and abandoned half way")


def test_unparseable_json_is_reported_rather_than_guessed_at(bucket, catalog_table):
    _run_row(catalog_table, bucket, run_id="run-bad", body=b"{not json")

    result = _invoke()

    assert "UNRECONSTRUCTABLE:   1" in result.output
    assert "not valid JSON" in result.output


def test_a_run_that_bound_nothing_is_counted_rather_than_diagnosed(bucket, catalog_table):
    """The one gap nothing can close.

    Before pose plates had catalog nodes they were stripped before the record was
    written, so those runs under-report their images — and a text-only generation
    looks identical from here. Counted, never invented.
    """
    _run_row(catalog_table, bucket, bindings={})

    result = _invoke()

    assert "bound no images at all" in result.output


def test_a_float_parameter_round_trips_rather_than_raising(bucket, catalog_table):
    """**Caught by trialling the backfill on one production run, not by a test.**

    `TypeSerializer` refuses a float outright, and nothing that had ever gone
    through `to_item` held one — until a plan's params, which are whatever the
    model was given. `topazlabs/image-upscale` takes
    `face_enhancement_strength: 0.8`, and 131 of production's 254 runs are
    upscales, so this would have failed on the second run of a full apply.

    The failure was three frames inside boto3 and named nothing about which
    attribute was at fault, which is the other half of why it is worth a test.
    """
    _run_row(catalog_table, bucket, model="topazlabs/image-upscale",
             bindings={"image": ["node-a"]},
             body={"model": "topazlabs/image-upscale",
                   "input": {"prompt": None, "face_enhancement_strength": 0.8,
                             "upscale_factor": 2}})

    result = _invoke("--apply")

    assert result.exit_code == 0, result.output
    params = _record(catalog_table, "run-1")["plan"]["params"]
    assert params["face_enhancement_strength"] == 0.8, "stored as 0.8, not as 17 digits"
    assert params["upscale_factor"] == 2, "an int stays an int"


def test_a_promptless_run_stores_a_plan_its_own_digest_agrees_with(bucket, catalog_table):
    """**The bug the one-run trial against production caught.**

    `to_item` drops a top-level `None`, so `prompt: None` never landed — while
    the digest had been computed over a dict that still had it. The stored plan
    and the stored digest therefore disagreed, which `get_run` reports as
    `stale: true`: every one of production's 131 upscale runs would have told a
    person on its own page that the payload changed after it was approved, about
    work nobody had touched.
    """
    _run_row(catalog_table, bucket, model="topazlabs/image-upscale",
             bindings={"image": ["node-a"]},
             body={"model": "topazlabs/image-upscale",
                   "input": {"upscale_factor": "2x"}})

    _invoke("--apply")

    record = _record(catalog_table, "run-1")
    assert "prompt" in record["plan"], "a null prompt is a real answer, not an absence"
    assert record["plan"]["prompt"] is None
    assert record["plan_digest"] == BF.plan_digest(
        record["plan"], _sends(catalog_table, "run-1")
    ), "the stored digest must agree with the stored plan, or every read says stale"


def test_the_digest_survives_a_round_trip_through_dynamodb(bucket, catalog_table):
    """**The third time this exact `Decimal` trap has bitten in this change.**

    Every number read out of DynamoDB is a `Decimal`, and `json.dumps` with
    `default=str` renders one as the string `"0.8"` where the float renders as
    the number `0.8`. So the digest written before the row and the digest
    recomputed from the row disagreed — and `catalog verify` uses this function,
    so it would have reported `stale_plan_digest` over 131 perfectly intact runs.

    `services/catalog.py::plan_digest` normalises for exactly this reason; the
    backend has a test named the same thing. This is the pipeline's copy of both.
    """
    _run_row(catalog_table, bucket, model="topazlabs/image-upscale",
             bindings={"image": ["node-a"]},
             body={"model": "topazlabs/image-upscale",
                   "input": {"face_enhancement_strength": 0.8, "steps": 30}})

    _invoke("--apply")

    record = _record(catalog_table, "run-1")
    assert record["plan_digest"] == BF.plan_digest(
        record["plan"], _sends(catalog_table, "run-1")
    )
