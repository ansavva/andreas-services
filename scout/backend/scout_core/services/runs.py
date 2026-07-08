"""
Source-run lifecycle.

Each scheduled or manual execution of a source produces a run record at
PK=SRC#<source_id>, SK=RUN#<run_id> (run_id is a ULID, so querying the source
partition descending yields newest-first). While a run is in progress it also
carries a GSI1 marker in the RUN#INPROGRESS partition so a boot-time sweep can
reconcile runs orphaned by a restart.

Finishing a run updates the owning source's materialized health fields
(last_run_at, last_run_status, consecutive_zero_event_runs) that back the
source-health view. Preview (dry-run) executions never call this module.
"""

from scout_core.repositories import store

TRIGGER_SCHEDULED = "scheduled"
TRIGGER_MANUAL = "manual"
TRIGGERS = (TRIGGER_SCHEDULED, TRIGGER_MANUAL)

IN_PROGRESS = "in_progress"
SUCCESS = "success"
ERROR = "error"

# Reserved error reasons (distinct so the admin alerting can tell them apart).
REASON_BUDGET_EXCEEDED = "budget_exceeded"
REASON_ORPHANED = "orphaned-by-restart"

_INPROGRESS_PK = "RUN#INPROGRESS"


def start_run(source_id, trigger):
    if trigger not in TRIGGERS:
        raise ValueError(f"invalid trigger: {trigger!r}")
    run_id = store.new_id()
    started_at = store.now_iso()
    item = store.base_item(
        store.source_pk(source_id), store.run_sk(run_id), store.RUN,
        run_id=run_id,
        source_id=source_id,
        trigger=trigger,
        status=IN_PROGRESS,
        started_at=started_at,
        events_count=0,
        link_outcomes=[],
        GSI1PK=_INPROGRESS_PK,
        GSI1SK=started_at,
    )
    return store.put(item)


def get_run(source_id, run_id):
    return store.get(store.source_pk(source_id), store.run_sk(run_id))


def list_runs(source_id, *, include_deleted=False):
    """Runs for a source, newest-first."""
    return store.query_all(
        store.source_pk(source_id), sk_begins_with="RUN#",
        live_only=not include_deleted, ascending=False,
    )


def list_runs_page(source_id, *, include_deleted=False, limit=None, start_key=None):
    """Cursor-paginated runs for a source, newest-first. Returns (items, next_key)."""
    return store.query_page(
        store.source_pk(source_id), sk_begins_with="RUN#",
        live_only=not include_deleted, ascending=False,
        limit=limit, start_key=start_key,
    )


# Stored-artifact label per kind, used to render the run history UI.
_ARTIFACT_LABELS = {
    "transcript": "Transcript",
    "root_body": "Fetched text",
    "root_html": "HTML",
}


def artifact_descriptors(run):
    """List the artifacts a given run actually produced, as {kind, label[, index]}.

    Only descriptors for refs the run carries are returned, so the UI never
    offers buttons that 404. Linked pages are expanded positionally.
    """
    if run is None:
        return []
    out = []
    for kind, label in _ARTIFACT_LABELS.items():
        if run.get(_ARTIFACT_ATTRS[kind]):
            out.append({"kind": kind, "label": label})
    for i, outcome in enumerate(run.get("link_outcomes") or []):
        if outcome.get("s3_ref"):
            out.append({"kind": "linked", "label": f"Link {i + 1}", "index": i})
    return out


def in_progress_source_ids():
    """Source ids that currently have an in-progress run, resolved in a single
    GSI1 query against the RUN#INPROGRESS partition."""
    rows = store.query_index_all("GSI1", _INPROGRESS_PK)
    return {r["source_id"] for r in rows}


# Stored-artifact kinds and the run attribute that holds each S3 ref. Linked
# pages are addressed positionally via the run's link_outcomes.
_ARTIFACT_ATTRS = {
    "root_body": "s3_root_body_ref",
    "root_html": "s3_root_html_ref",
    "transcript": "agent_transcript_ref",
}

ARTIFACT_KINDS = (*_ARTIFACT_ATTRS, "linked")


def artifact_ref(run, kind, index=None):
    """Resolve the S3 ref for one of a run's stored artifacts, or None if the
    run never produced it. ``linked`` selects the index-th followed page."""
    if run is None:
        return None
    if kind == "linked":
        outcomes = run.get("link_outcomes") or []
        if index is None or index < 0 or index >= len(outcomes):
            return None
        return outcomes[index].get("s3_ref")
    attr = _ARTIFACT_ATTRS.get(kind)
    return run.get(attr) if attr else None


def set_artifacts(source_id, run_id, **refs):
    """Attach S3 references (root_body, root_html, transcript) to a run."""
    key_map = {
        "root_body": "s3_root_body_ref",
        "root_html": "s3_root_html_ref",
        "transcript": "agent_transcript_ref",
    }
    attrs = {key_map[k]: v for k, v in refs.items() if k in key_map and v is not None}
    store.set_attrs(store.source_pk(source_id), store.run_sk(run_id), attrs)


def add_link_outcome(source_id, run_id, outcome):
    """Append a per-link fetch outcome (url, ok, status/reason, optional s3_ref).
    Per-link failures are recorded, never raised."""
    store.core().update_item(
        Key={"PK": store.source_pk(source_id), "SK": store.run_sk(run_id)},
        UpdateExpression=(
            "SET link_outcomes = list_append(if_not_exists(link_outcomes, :e), :o)"
        ),
        ExpressionAttributeValues={":e": [], ":o": [outcome]},
    )


def finish_run(source_id, run_id, *, status, events_count=0, error_reason=None,
               summary=None):
    """Complete a run and roll its outcome into the source's health counters."""
    if status not in (SUCCESS, ERROR):
        raise ValueError(f"invalid terminal status: {status!r}")
    finished_at = store.now_iso()

    attrs = {"status": status, "finished_at": finished_at,
             "events_count": events_count}
    if error_reason is not None:
        attrs["error_reason"] = error_reason
    if summary is not None:
        attrs["extracted_summary"] = summary
    pk, sk = store.source_pk(source_id), store.run_sk(run_id)
    store.set_attrs(pk, sk, attrs)
    # Drop the in-progress marker so the orphan sweep no longer sees it.
    store.remove_attrs(pk, sk, ["GSI1PK", "GSI1SK"])

    _roll_up_health(source_id, finished_at, status, events_count)
    return get_run(source_id, run_id)


def _roll_up_health(source_id, finished_at, status, events_count):
    source = store.get(store.source_pk(source_id), "META")
    if source is None:
        return
    prev = int(source.get("consecutive_zero_event_runs", 0) or 0)
    counter = prev + 1 if events_count == 0 else 0
    store.set_attrs(store.source_pk(source_id), "META", {
        "last_run_at": finished_at,
        "last_run_status": status,
        "consecutive_zero_event_runs": counter,
    })


def reconcile_orphaned_runs():
    """Boot-time recovery: any run still flagged in-progress was orphaned by a
    restart — transition it to error. Returns the count reconciled."""
    orphaned = store.query_index_all("GSI1", _INPROGRESS_PK, live_only=False)
    for run in orphaned:
        finish_run(
            run["source_id"], run["run_id"],
            status=ERROR, error_reason=REASON_ORPHANED,
        )
    return len(orphaned)
