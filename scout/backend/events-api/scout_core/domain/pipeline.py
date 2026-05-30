"""
Run pipeline orchestration (two-pass extraction).

Ties together fetching (fetcher), artifact storage (artifacts), the run
lifecycle (runs) and extraction (extractor). Our code acquires the root content
(webpage root or email bodies); extraction then runs in two passes:

1. triage  — a cheap model reads each fetched page and reports (a) the distinct
   candidate events, each with its own "detail" URL, and (b) "listing" URLs:
   links to pages that list *more* events (a "what's on" / index page). Listing
   pages are fetched and re-triaged up to MAX_LISTING_DEPTH hops, so an email
   that merely links to a calendar still yields its events.
2. for each candidate with a usable detail URL (cross-domain for email,
   same-domain for webpage; junk-filtered) we fetch and clean that page, then
   run an enrich pass — a stronger model turns the mention + detail page into
   the full event record.
3. candidates with no usable/fetchable link fall back to the best-effort event
   the triage pass already produced (no second call), so nothing is lost.

All listing + detail fetches share one global budget (link_follow_cap) and a
URL de-dup set, so cost stays bounded on large digests.

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


# How many hops of "listing → more events" links to follow. The root pages are
# depth 0; an email body or webpage that links to a "what's on" page is followed
# to depth 1, and that page's own listing links to depth 2. Per-event detail
# pages are reached via enrich, not this recursion.
MAX_LISTING_DEPTH = 2


def run_extraction(source, pages, *, triage, enrich, fetch_fn,
                   on_link_outcome=None, store_linked=None, settings=None):
    """Two-pass extraction with bounded link recursion. Returns ExtractionResult.

    Pass 1 triages each page into (a) candidate events, each with its own detail
    URL, and (b) listing URLs — links to pages that list *more* events (a
    "what's on" / index page). Listing pages are fetched and re-triaged up to
    MAX_LISTING_DEPTH hops, so an email that just links to a calendar still
    yields its events. Pass 2 fetches each candidate's detail page and enriches
    it into a full record; candidates with no usable/fetchable link fall back to
    the best-effort event triage already produced.

    Detail and listing fetches share one global budget (link_follow_cap) and a
    URL de-dup set, so cost stays predictable on large digests. Webpage sources
    stay same-domain; email follows cross-domain (organizer/ticketing) links."""
    settings = settings or store.get_settings()
    link_cap = int(settings["link_follow_cap"])
    same_domain_only = source["type"] != sources.EMAIL
    root_domain = fetcher.host_of(source.get("identity", "")) if same_domain_only else ""

    transcript = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    fetched_urls = set()
    fetch_count = [0]

    def _add(result):
        transcript.extend(result.transcript)
        usage["input_tokens"] += int(result.usage.get("input_tokens", 0) or 0)
        usage["output_tokens"] += int(result.usage.get("output_tokens", 0) or 0)

    def _fetch(url):
        """Fetch + clean one URL under the shared cap, record the outcome, and
        return its text ("" on cap/dup/failure)."""
        if url in fetched_urls or not _followable(
                url, same_domain_only=same_domain_only, root_domain=root_domain):
            return ""
        if fetch_count[0] >= link_cap:
            return ""
        index = fetch_count[0]
        fetch_count[0] += 1
        fetched_urls.add(url)
        try:
            status, text = fetcher.fetch_text(url, fetch_fn=fetch_fn)
            ok = 200 <= status < 300
            record = {"url": url, "ok": ok}
            if ok:
                record["http_status"] = status
                if store_linked is not None:
                    record["s3_ref"] = store_linked(index, text)
            else:
                record["reason"] = f"http {status}"
                text = ""
        except Exception as exc:  # pylint: disable=broad-except
            record = {"url": url, "ok": False, "reason": str(exc)}
            text = ""
        if on_link_outcome is not None:
            on_link_outcome(record)
        return text

    # Pass 1: triage the root pages, following listing links breadth-first up to
    # MAX_LISTING_DEPTH. Each candidate carries the page it was found on (for
    # relative-date anchoring and source attribution).
    candidates = []  # list of (candidate, page)
    triage_error = None
    queue = [(page, 0) for page in pages]
    while queue:
        page, depth = queue.pop(0)
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
        if depth < MAX_LISTING_DEPTH:
            for listing_url in result.listing_urls:
                if fetch_count[0] >= link_cap:
                    break
                text = _fetch(listing_url)
                if text:
                    queue.append(({"url": listing_url, "content": text,
                                   "date": page.get("date")}, depth + 1))

    if not candidates and triage_error:
        return extractor_mod.ExtractionResult(
            extractor_mod.STATUS_ERROR, transcript=transcript, usage=usage,
            error=triage_error)

    # Pass 2: fetch each candidate's detail page + enrich; fall back otherwise.
    events = []
    for candidate, page in candidates:
        page_text = _fetch(candidate.get("detail_url"))
        if page_text:
            result = enrich(candidate, page_text, source_ref=page.get("url"),
                            date=page.get("date"))
            _add(result)
            if result.status == extractor_mod.STATUS_BUDGET_EXCEEDED:
                return extractor_mod.ExtractionResult(
                    extractor_mod.STATUS_BUDGET_EXCEEDED, transcript=transcript,
                    usage=usage, error=result.error)
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
