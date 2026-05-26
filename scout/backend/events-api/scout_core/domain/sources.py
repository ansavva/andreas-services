"""
Source service layer.

A source is the origin of events — either an email subscription (identity = the
sender's domain) or a webpage (identity = a root URL). Sources live at
PK=SRC#<id>, SK=META and are listed via GSI1: non-archived sources sit in the
SRC#LISTED partition (the admin's default view), archived ones in SRC#ARCHIVED.
Schedulable sources also carry a GSI4 entry keyed by next_run_at so the
scheduler can range-query "what is due now" and the health view can spot
overdue sources.

Status (active|disabled) and the archived flag are independent: either one
stops scheduled runs. Run execution, S3 artifacts, and extraction live in
runs.py / fetcher.py / artifacts.py.
"""

from datetime import datetime, timedelta, timezone

from scout_core.domain import labels
from scout_core.adapters import store

EMAIL = "email"
WEBPAGE = "webpage"
SOURCE_TYPES = (EMAIL, WEBPAGE)

SCHEDULED = "scheduled"
ONE_OFF = "one-off"
WEBPAGE_MODES = (SCHEDULED, ONE_OFF)

ACTIVE = "active"
DISABLED = "disabled"

PRESETS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}

_LISTED_PK = "SRC#LISTED"
_ARCHIVED_PK = "SRC#ARCHIVED"
_HEALTH_PK = "SRCHEALTH"


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Config validation & scheduling
# ---------------------------------------------------------------------------

def _validate_config(source_type, config):
    config = dict(config or {})
    if source_type == EMAIL:
        freq = config.get("check_frequency", "daily")
        if freq not in PRESETS:
            raise ValueError(f"invalid email check_frequency: {freq!r}")
        config["check_frequency"] = freq
    else:  # WEBPAGE
        mode = config.get("mode", SCHEDULED)
        if mode not in WEBPAGE_MODES:
            raise ValueError(f"invalid webpage mode: {mode!r}")
        config["mode"] = mode
        if mode == SCHEDULED:
            preset = config.get("schedule_preset", "daily")
            if preset not in PRESETS:
                raise ValueError(f"invalid schedule_preset: {preset!r}")
            config["schedule_preset"] = preset
    return config


def _preset(source):
    if source["type"] == EMAIL:
        return source.get("config", {}).get("check_frequency", "daily")
    return source.get("config", {}).get("schedule_preset", "daily")


def is_schedulable(source):
    """A source runs on schedule only when active, not archived, not deleted —
    and, for one-off webpages, only until its first run."""
    if source.get("deleted_at") or source.get("archived"):
        return False
    if source.get("status", ACTIVE) != ACTIVE:
        return False
    if source["type"] == WEBPAGE and source.get("config", {}).get("mode") == ONE_OFF:
        return not source.get("last_run_at")
    return True


def compute_next_run_at(source, from_dt=None):
    """Next due time (ISO) for a schedulable source, else None. One-off webpages
    are due immediately until they have run."""
    if not is_schedulable(source):
        return None
    if source["type"] == WEBPAGE and source.get("config", {}).get("mode") == ONE_OFF:
        return _iso(from_dt or _now())
    base = from_dt or _now()
    return _iso(base + PRESETS[_preset(source)])


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def _reindex(source_id):
    """Recompute GSI1 (listed vs archived) and GSI4 (schedule cursor) for a
    source after a state change. Soft-deleted sources are left out of both."""
    source = store.get(store.source_pk(source_id), "META")
    if source is None or source.get("deleted_at"):
        return source
    pk, sk = store.source_pk(source_id), "META"

    sets = {
        "GSI1PK": _ARCHIVED_PK if source.get("archived") else _LISTED_PK,
        "GSI1SK": source.get("identity_norm", source.get("identity", "").lower()),
    }
    next_run = source.get("next_run_at") if is_schedulable(source) else None
    if next_run:
        sets["GSI4PK"] = _HEALTH_PK
        sets["GSI4SK"] = next_run
        store.set_attrs(pk, sk, sets)
    else:
        store.set_attrs(pk, sk, sets)
        store.remove_attrs(pk, sk, ["GSI4PK", "GSI4SK"])
    return store.get(pk, sk)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_source(source_type, identity, *, name=None, config=None,
                  follow_links=False, status=ACTIVE, agent_model=None,
                  agent_budget_tokens=None, agent_budget_seconds=None):
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"unknown source type: {source_type!r}")
    identity = (identity or "").strip()
    if not identity:
        raise ValueError("source identity is required")
    config = _validate_config(source_type, config)

    source_id = store.new_id()
    pk = store.source_pk(source_id)
    item = store.base_item(
        pk, "META", store.SOURCE,
        source_id=source_id,
        type=source_type,
        identity=identity,
        identity_norm=identity.lower(),
        name=(name or identity).strip(),
        config=config,
        follow_links=bool(follow_links),
        status=status,
        archived=False,
        consecutive_zero_event_runs=0,
        agent_model_override=agent_model,
        agent_budget_tokens_override=agent_budget_tokens,
        agent_budget_seconds_override=agent_budget_seconds,
        GSI1PK=_LISTED_PK,
        GSI1SK=identity.lower(),
    )
    next_run = compute_next_run_at(item)
    if next_run:
        item["next_run_at"] = next_run
        item["GSI4PK"] = _HEALTH_PK
        item["GSI4SK"] = next_run
    return store.put(item)


def get_source(source_id):
    return store.get(store.source_pk(source_id), "META")


def get_by_identity(source_type, identity):
    """The live source matching a type + normalized identity, or None. Backed by
    GSI1 (listed + archived partitions), which excludes soft-deleted sources."""
    identity_norm = (identity or "").strip().lower()
    for pk in (_LISTED_PK, _ARCHIVED_PK):
        for source in store.query_index_all("GSI1", pk, ascending=True):
            if (source.get("type") == source_type
                    and source.get("identity_norm") == identity_norm):
                return source
    return None


def ensure_email_source(domain):
    """Idempotently ensure an active email source exists for a sender domain
    discovered under the Gmail "Events" label. Returns (source, created).

    A brand-new source is made due immediately (next_run_at = now) so the next
    scheduler tick — or a manual run — ingests its backlog rather than waiting a
    full check_frequency interval. An already-known source (even archived or
    disabled by an admin) is returned untouched."""
    domain = (domain or "").strip().lower()
    if not domain:
        raise ValueError("domain is required")
    existing = get_by_identity(EMAIL, domain)
    if existing is not None:
        return existing, False

    source = create_source(EMAIL, domain, status=ACTIVE)
    store.set_attrs(store.source_pk(source["source_id"]), "META",
                    {"next_run_at": _iso(_now())})
    return _reindex(source["source_id"]), True


def list_sources(*, archived=False, status=None):
    """Default view (archived=False) or the archived view, optionally filtered
    to a status."""
    pk = _ARCHIVED_PK if archived else _LISTED_PK
    items = store.query_index_all("GSI1", pk, ascending=True)
    if status:
        items = [s for s in items if s.get("status") == status]
    return items


def update_source(source_id, fields):
    """Apply allowed field changes and recompute scheduling/listing indexes."""
    pk = store.source_pk(source_id)
    source = store.get(pk, "META")
    if source is None:
        return None

    updates = {"updated_at": store.now_iso()}
    if "name" in fields and (fields["name"] or "").strip():
        updates["name"] = fields["name"].strip()
    if "follow_links" in fields:
        updates["follow_links"] = bool(fields["follow_links"])
    if "status" in fields:
        if fields["status"] not in (ACTIVE, DISABLED):
            raise ValueError(f"invalid status: {fields['status']!r}")
        updates["status"] = fields["status"]
    if "archived" in fields:
        updates["archived"] = bool(fields["archived"])
    if "config" in fields:
        updates["config"] = _validate_config(source["type"], fields["config"])
    for key in ("agent_model_override", "agent_budget_tokens_override",
                "agent_budget_seconds_override"):
        if key in fields:
            updates[key] = fields[key]

    store.set_attrs(pk, "META", updates)

    # Recompute the schedule cursor against the merged state, then reindex.
    merged = store.get(pk, "META")
    next_run = compute_next_run_at(merged)
    if next_run:
        store.set_attrs(pk, "META", {"next_run_at": next_run})
    else:
        store.remove_attrs(pk, "META", ["next_run_at"])
    return _reindex(source_id)


def set_archived(source_id, archived):
    return update_source(source_id, {"archived": bool(archived)})


def delete_source(source_id):
    """Soft-delete a source (which also stops scheduled runs). Cascade to events
    and runs (with opt-out) is handled by the deletion layer in a later phase."""
    store.soft_delete(store.source_pk(source_id), "META", store.SOURCE)
    # soft_delete strips GSI1/GSI3; also drop the schedule cursor.
    store.remove_attrs(store.source_pk(source_id), "META", ["GSI4PK", "GSI4SK"])


def restore_source(source_id):
    pk = store.source_pk(source_id)
    if store.get(pk, "META") is None:
        return None
    store.restore(pk, "META")
    return _reindex(source_id)


# ---------------------------------------------------------------------------
# Source labels
# ---------------------------------------------------------------------------

def add_label(source_id, label_id):
    return labels.attach_label(store.SOURCE_LABEL, label_id, store.SOURCE, source_id)


def remove_label(source_id, label_id):
    labels.detach_label(store.SOURCE_LABEL, label_id, store.SOURCE, source_id)


def label_ids(source_id):
    return labels.label_ids_of(store.SOURCE, source_id, taxonomy=store.SOURCE_LABEL)


# ---------------------------------------------------------------------------
# Scheduling cursor maintenance (called by the scheduler / run lifecycle)
# ---------------------------------------------------------------------------

def due_sources(now_iso=None):
    """Schedulable sources whose next_run_at is at or before now."""
    now_iso = now_iso or _iso(_now())
    candidates = store.query_index_all(
        "GSI4", _HEALTH_PK, ascending=True, live_only=True
    )
    return [s for s in candidates if s.get("next_run_at", "") <= now_iso]


def health_report(now=None):
    """Surface unhealthy sources for the admin health view: most recent run
    errored, N consecutive zero-event runs, or overdue past the threshold."""
    settings = store.get_settings()
    now = now or _now()
    overdue_cutoff = _iso(now - timedelta(hours=float(settings["health_overdue_hours"])))
    zero_threshold = int(settings["health_zero_event_runs"])

    errored, stale, overdue = [], [], []
    for source in list_sources():
        if source.get("last_run_status") == "error":
            errored.append(source)
        if int(source.get("consecutive_zero_event_runs", 0) or 0) >= zero_threshold:
            stale.append(source)
        next_run = source.get("next_run_at")
        if next_run and next_run < overdue_cutoff:
            overdue.append(source)
    return {"errored": errored, "stale": stale, "overdue": overdue}


def advance_schedule(source_id):
    """Move a scheduled source's next_run_at forward by one interval (used after
    a scheduled run is dispatched). One-off sources fall off the schedule."""
    source = store.get(store.source_pk(source_id), "META")
    if source is None:
        return None
    next_run = compute_next_run_at(source, from_dt=_now())
    if next_run and not (source["type"] == WEBPAGE
                         and source.get("config", {}).get("mode") == ONE_OFF):
        store.set_attrs(store.source_pk(source_id), "META", {"next_run_at": next_run})
    else:
        store.remove_attrs(store.source_pk(source_id), "META", ["next_run_at"])
    return _reindex(source_id)
