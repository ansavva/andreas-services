"""
Run pipeline orchestration (two-pass extraction).

Ties together fetching (fetcher), artifact storage (artifacts), the run
lifecycle (runs) and extraction (extractor). Our code acquires the root content
(webpage root or email bodies); extraction then runs in two passes:

1. triage  — a cheap model reads each fetched page and reports the distinct
   candidate events plus, per candidate, the best "detail" URL to open.
2. for each candidate with a usable detail URL (cross-domain for email,
   same-domain for webpage; junk-filtered; capped at the link-follow cap) we
   fetch and clean that page, then run an enrich pass — a stronger model turns
   the mention + detail page into the full event record.
3. candidates with no usable/fetchable link fall back to the best-effort event
   the triage pass already produced (no second call), so nothing is lost.

The two passes are injected as callables (triage / enrich) so tests can script
them; make_passes() binds the real extractor with the source's models, budgets,
today's date, timezone, and known labels.

- preview(): fetch + extract in memory, persisting nothing (no run, no S3).
- execute_run(): create a run record, store fetched content + the transcript to
  S3, record per-link outcomes, and finish the run — success on a completed
  extraction, error (with the distinct budget_exceeded reason) otherwise,
  discarding partial output. Scheduled runs advance the source's schedule;
  manual runs never shift it.
"""

import json
import time
from datetime import datetime, timezone

from scout_core.adapters import artifacts
from scout_core.domain import events as events_mod
from scout_core.adapters import extractor as extractor_mod
from scout_core.adapters import fetcher
from scout_core.domain import labels
from scout_core.domain import notifications
from scout_core.domain import runs
from scout_core.domain import sources
from scout_core.adapters import store


def noop_triage(_pages):
    return extractor_mod.TriageResult(extractor_mod.STATUS_COMPLETED, candidates=[])


def noop_enrich(_candidate, _page_text, **_kwargs):
    return extractor_mod.ExtractionResult(extractor_mod.STATUS_COMPLETED, events=[])


def make_passes(source, settings, *, runner=None):
    """Build (triage_fn, enrich_fn) for a source, applying per-source model /
    budget overrides on top of the system defaults and binding today's date,
    timezone and the known event-label vocabulary into the prompts."""
    triage_model = (source.get("triage_model_override")
                    or settings["default_triage_model"])
    enrich_model = source.get("agent_model_override") or settings["default_agent_model"]
    budget_tokens = int(source.get("agent_budget_tokens_override")
                        or settings["default_agent_budget_tokens"])
    budget_seconds = int(source.get("agent_budget_seconds_override")
                         or settings["default_agent_budget_seconds"])
    now = datetime.now(timezone.utc).date().isoformat()
    tz = settings.get("system_timezone", "UTC")
    known_labels = [lbl["name"] for lbl in labels.list_labels(store.EVENT_LABEL)]

    def triage_fn(pages):
        return extractor_mod.triage(
            pages, model=triage_model, now=now, timezone=tz,
            budget_tokens=budget_tokens, budget_seconds=budget_seconds, runner=runner)

    def enrich_fn(candidate, page_text, *, source_ref=None, date=None):
        return extractor_mod.enrich(
            candidate, page_text, model=enrich_model, now=now, timezone=tz,
            known_labels=known_labels, source=source_ref, date=date,
            budget_tokens=budget_tokens, budget_seconds=budget_seconds, runner=runner)

    return triage_fn, enrich_fn


def _gather_webpage_pages(source, *, fetch_fn):
    """Webpage root, cleaned to text. Returns (pages, root_html). Link-following
    is driven by the triage pass downstream, not here."""
    url = source["identity"]
    _status, html = fetch_fn(url)
    pages = [{"url": url, "content": fetcher.clean_html(html or "")}]
    return pages, html


def _gather_email_pages(source, *, gmail_fetch, email_body, since_epoch):
    """Recent Events-labeled messages for the source's sender domain, one page
    per message (body markdown + received date). gmail_fetch(domain, since) ->
    [message dicts]; an inline email_body stands in for a single message
    (test/manual seam). Returns (pages, None)."""
    if gmail_fetch is not None:
        messages = gmail_fetch(source.get("identity", ""), since_epoch)
    elif email_body is not None:
        messages = [{"message_id": "inline", "subject": "",
                     "body_markdown": email_body}]
    else:
        messages = []

    pages = []
    for message in messages:
        pages.append({
            "url": f"gmail:{message.get('message_id', '')}",
            "content": message.get("body_markdown") or "",
            "date": message.get("date") or None,
        })
    return pages, None


def _gather_pages(source, *, fetch_fn, email_body, gmail_fetch=None,
                  since_epoch=None):
    """Acquire the root content pages for a source. Returns (pages, root_html);
    root_html is None for email sources."""
    if source["type"] == sources.EMAIL:
        return _gather_email_pages(
            source, gmail_fetch=gmail_fetch, email_body=email_body,
            since_epoch=since_epoch)
    return _gather_webpage_pages(source, fetch_fn=fetch_fn)


def _followable(url, *, same_domain_only, root_domain):
    """Whether a triage-chosen detail URL is worth fetching."""
    if not url or fetcher.is_junk_link(url):
        return False
    if same_domain_only and not fetcher.same_domain(url, root_domain):
        return False
    return True


def run_extraction(source, pages, *, triage, enrich, fetch_fn,
                   on_link_outcome=None, store_linked=None, settings=None):
    """Two-pass extraction over the gathered pages. Returns an ExtractionResult.

    Triage runs per page (so each candidate inherits that page's date/url for
    relative-date anchoring). Detail pages chosen by triage are fetched (junk-
    filtered; same-domain for webpage, cross-domain for email), recorded as link
    outcomes, and stored; each fetched candidate is enriched. Linkless or beyond
    the fan-out cap → the triage fallback event is used directly."""
    settings = settings or store.get_settings()
    link_cap = int(settings["link_follow_cap"])
    same_domain_only = source["type"] != sources.EMAIL
    root_domain = fetcher.host_of(source.get("identity", "")) if same_domain_only else ""

    transcript = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    def _add(result):
        transcript.extend(result.transcript)
        usage["input_tokens"] += int(result.usage.get("input_tokens", 0) or 0)
        usage["output_tokens"] += int(result.usage.get("output_tokens", 0) or 0)

    # Pass 1: triage each page into candidates (carrying the page's url + date).
    candidates = []  # list of (candidate, page)
    triage_error = None
    for page in pages:
        result = triage([page])
        _add(result)
        if result.status == extractor_mod.STATUS_BUDGET_EXCEEDED:
            return extractor_mod.ExtractionResult(
                extractor_mod.STATUS_BUDGET_EXCEEDED, transcript=transcript,
                usage=usage, error=result.error)
        if result.status != extractor_mod.STATUS_COMPLETED:
            triage_error = result.error or "triage failed"
            continue
        candidates.extend((c, page) for c in result.candidates)

    if not candidates and triage_error:
        return extractor_mod.ExtractionResult(
            extractor_mod.STATUS_ERROR, transcript=transcript, usage=usage,
            error=triage_error)

    # Pass 2: fetch the chosen detail pages + enrich; fall back otherwise.
    events = []
    fetches = 0
    for candidate, page in candidates:
        page_text = ""
        detail_url = candidate.get("detail_url")
        if (fetches < link_cap
                and _followable(detail_url, same_domain_only=same_domain_only,
                                root_domain=root_domain)):
            index = fetches
            fetches += 1
            try:
                status, text = fetcher.fetch_text(detail_url, fetch_fn=fetch_fn)
                ok = 200 <= status < 300
                record = {"url": detail_url, "ok": ok}
                if ok:
                    page_text = text
                    record["http_status"] = status
                    if store_linked is not None:
                        record["s3_ref"] = store_linked(index, text)
                else:
                    record["reason"] = f"http {status}"
            except Exception as exc:  # pylint: disable=broad-except
                record = {"url": detail_url, "ok": False, "reason": str(exc)}
            if on_link_outcome is not None:
                on_link_outcome(record)

        if page_text:
            result = enrich(candidate, page_text, source_ref=page.get("url"),
                            date=page.get("date"))
            _add(result)
            if result.status == extractor_mod.STATUS_COMPLETED and result.events:
                events.extend(result.events)
                continue
            # Enrich failed/empty — fall back to the triage event below.
        fallback = candidate.get("fallback_event")
        if fallback:
            events.append(fallback)

    return extractor_mod.ExtractionResult(
        extractor_mod.STATUS_COMPLETED, events=events, transcript=transcript,
        usage=usage)


def preview(source, *, fetch_fn=fetcher.fetch_url, triage=noop_triage,
            enrich=noop_enrich, email_body=None, gmail_fetch=None,
            since_epoch=None):
    """Dry-run: fetch + extract without persisting any run or event records."""
    link_outcomes = []
    pages, _root_html = _gather_pages(
        source, fetch_fn=fetch_fn, email_body=email_body,
        gmail_fetch=gmail_fetch, since_epoch=since_epoch,
    )
    result = run_extraction(
        source, pages, triage=triage, enrich=enrich, fetch_fn=fetch_fn,
        on_link_outcome=link_outcomes.append,
    )
    return {
        "status": result.status,
        "events": result.events,
        "link_outcomes": link_outcomes,
        "pages_fetched": len(pages) + len(link_outcomes),
    }


def execute_run(source, trigger, *, fetch_fn=fetcher.fetch_url,
                triage=noop_triage, enrich=noop_enrich, email_body=None,
                gmail_fetch=None, since_epoch=None):
    """Run a source for real: persist a run, store fetched content + transcript
    to S3, record outcomes, and finish the run."""
    source_id = source["source_id"]
    run = runs.start_run(source_id, trigger)
    run_id = run["run_id"]
    fetch_started_epoch = int(time.time())
    # Note: advancing the schedule on scheduled runs is the scheduler's job (it
    # claims the slot at dispatch); manual runs never shift the schedule.

    try:
        def _store_linked(index, content):
            return artifacts.store_linked_page(source_id, run_id, index, content)

        pages, root_html = _gather_pages(
            source, fetch_fn=fetch_fn, email_body=email_body,
            gmail_fetch=gmail_fetch, since_epoch=since_epoch,
        )
        if root_html:
            runs.set_artifacts(source_id, run_id,
                               root_html=artifacts.store_root_html(source_id, run_id, root_html))

        result = run_extraction(
            source, pages, triage=triage, enrich=enrich, fetch_fn=fetch_fn,
            on_link_outcome=lambda rec: runs.add_link_outcome(source_id, run_id, rec),
            store_linked=_store_linked,
        )
    except Exception as exc:  # pylint: disable=broad-except
        runs.finish_run(source_id, run_id, status=runs.ERROR, error_reason=str(exc))
        notifications.notify_run_failure(source_id, run_id, str(exc))
        return runs.get_run(source_id, run_id)

    if result.transcript:
        runs.set_artifacts(source_id, run_id, transcript=artifacts.store_transcript(
            source_id, run_id, json.dumps(result.transcript)))

    if result.status == extractor_mod.STATUS_COMPLETED:
        # Persist the extracted events as pending records (dedup + fuzzy location
        # match applied), then finish the run with the created count.
        conversion = events_mod.convert_extraction(source_id, result.events)
        # Advance the email cursor so the next run only fetches newer messages.
        if source["type"] == sources.EMAIL:
            store.set_attrs(store.source_pk(source_id), "META",
                            {"last_email_fetch_epoch": fetch_started_epoch})
        runs.finish_run(source_id, run_id, status=runs.SUCCESS,
                        events_count=conversion["created"],
                        summary={**conversion, "pages": len(pages)})
    elif result.status == extractor_mod.STATUS_BUDGET_EXCEEDED:
        runs.finish_run(source_id, run_id, status=runs.ERROR,
                        error_reason=runs.REASON_BUDGET_EXCEEDED)
        notifications.notify_budget_exceeded(source_id, run_id)
    else:
        runs.finish_run(source_id, run_id, status=runs.ERROR,
                        error_reason=result.error or "extraction failed")
        notifications.notify_run_failure(source_id, run_id,
                                         result.error or "extraction failed")

    return runs.get_run(source_id, run_id)
