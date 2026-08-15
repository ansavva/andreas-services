"""Admin source endpoints: CRUD, runs + artifacts, run/preview triggers, labels."""

import json
import os

import boto3
from flask import Blueprint, request

from scout_core import config
from scout_core.repositories import artifacts
from scout_core.repositories import store
from scout_core.routes._shared import body, created, not_found, ok
from scout_core.services import deletion
from scout_core.services import runs
from scout_core.services import sources

bp = Blueprint("sources", __name__, url_prefix="/api/admin/sources")

# Server-controlled artifact chunk size. Stays well under the ~6 MB Lambda
# response cap even after JSON-string escaping.
_ARTIFACT_CHUNK = 512 * 1024

_PROCESSOR_FN = os.environ.get("SCOUT_PROCESSOR_FN")
if not _PROCESSOR_FN:
    raise RuntimeError(
        "SCOUT_PROCESSOR_FN is not set. Terraform sets it on the Lambda; "
        "local runs and tests must set it explicitly."
    )

_lambda_client = None


def _lambda():
    global _lambda_client
    if _lambda_client is None:
        region = (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        _lambda_client = boto3.client("lambda", region_name=region)
    return _lambda_client


def _artifact_url(base, source_id, run_id, descriptor):
    """Build an absolute our-domain URL the client can fetch chunks from."""
    path = (f"{base}/admin/sources/{source_id}/runs/{run_id}/artifact"
            f"?kind={descriptor['kind']}")
    if "index" in descriptor:
        path += f"&index={descriptor['index']}"
    return path


def _trigger(source_id, mode):
    _lambda().invoke(
        FunctionName=_PROCESSOR_FN, InvocationType="Event",
        Payload=json.dumps({"source_id": source_id, "mode": mode}).encode(),
    )
    return {"status": "started", "source_id": source_id, "mode": mode}


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

@bp.get("")
def list_sources():
    archived = request.args.get("archived") == "true"
    limit = int(request.args.get("page_size", "50"))
    start_key = store.decode_cursor(request.args.get("cursor"))
    items, next_key = sources.list_sources_page(
        archived=archived, status=request.args.get("status"),
        limit=limit, start_key=start_key,
    )
    running = runs.in_progress_source_ids()
    for item in items:
        item["running"] = item["source_id"] in running
    return ok({"sources": items, "next_cursor": store.encode_cursor(next_key)})


@bp.post("")
def create_source():
    b = body()
    src = sources.create_source(
        b.get("type"), b.get("identity"), name=b.get("name"),
        config=b.get("config"), follow_links=b.get("follow_links", False),
        agent_model=b.get("agent_model"),
        triage_model=b.get("triage_model"),
        agent_budget_tokens=b.get("agent_budget_tokens"),
        agent_budget_seconds=b.get("agent_budget_seconds"))
    return created(src)


@bp.get("/running")
def running():
    return ok({"running": sorted(runs.in_progress_source_ids())})


@bp.get("/health")
def health():
    return ok(sources.health_report())


@bp.post("/scan-inbox")
def scan_inbox():
    _lambda().invoke(
        FunctionName=_PROCESSOR_FN, InvocationType="Event",
        Payload=json.dumps({"mode": "discover"}).encode(),
    )
    return ok({"status": "started", "mode": "discover"})


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

@bp.get("/<source_id>")
def get_source(source_id):
    src = sources.get_source(source_id)
    return ok(src) if src else not_found("Source not found")


@bp.put("/<source_id>")
def update_source(source_id):
    src = sources.update_source(source_id, body())
    return ok(src) if src else not_found("Source not found")


@bp.delete("/<source_id>")
def delete_source(source_id):
    result = deletion.delete_source(
        source_id, cascade_events=request.args.get("cascade", "true") != "false")
    return ok(result) if result else not_found("Source not found")


@bp.get("/<source_id>/delete-preview")
def delete_preview(source_id):
    return ok(deletion.preview_delete_source(source_id))


@bp.post("/<source_id>/archive")
def archive(source_id):
    return ok(sources.set_archived(source_id, body().get("archived", True)))


@bp.get("/<source_id>/runs")
def list_runs(source_id):
    limit = int(request.args.get("page_size", "20"))
    start_key = store.decode_cursor(request.args.get("cursor"))
    items, next_key = runs.list_runs_page(source_id, limit=limit, start_key=start_key)
    base = config.public_api_base()
    for run in items:
        run["artifacts"] = [
            {**d, "url": _artifact_url(base, source_id, run["run_id"], d)}
            for d in runs.artifact_descriptors(run)
        ]
    return ok({"runs": items, "next_cursor": store.encode_cursor(next_key)})


@bp.get("/<source_id>/runs/<run_id>/artifact")
def run_artifact(source_id, run_id):
    run = runs.get_run(source_id, run_id)
    if run is None:
        return not_found("Run not found")
    kind = request.args.get("kind", "transcript")
    index = request.args.get("index")
    ref = runs.artifact_ref(run, kind, int(index) if index is not None else None)
    if not ref:
        return not_found("Artifact not found")
    offset = int(request.args.get("offset", "0"))
    chunk = int(request.args.get("chunk_size", str(_ARTIFACT_CHUNK)))
    text, next_offset, total = artifacts.get_range(ref, offset, chunk)
    return ok({
        "kind": kind, "content": text,
        "offset": offset, "next_offset": next_offset, "total": total,
    })


@bp.post("/<source_id>/run")
def trigger_run(source_id):
    return ok(_trigger(source_id, "run"))


@bp.post("/<source_id>/preview")
def trigger_preview(source_id):
    return ok(_trigger(source_id, "preview"))


@bp.post("/<source_id>/labels")
def add_label(source_id):
    return ok(sources.add_label(source_id, body()["label_id"]))


@bp.delete("/<source_id>/labels/<label_id>")
def remove_label(source_id, label_id):
    sources.remove_label(source_id, label_id)
    return ok({"removed": label_id})
