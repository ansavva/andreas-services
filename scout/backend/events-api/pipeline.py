"""
Run pipeline orchestration.

Ties together fetching (fetcher), artifact storage (artifacts) and the run
lifecycle (runs) for both real runs and preview dry-runs. Our code acquires the
content; an injected extract_fn turns the fetched pages into events. Extraction
is stubbed in this phase — the Claude Agent SDK extractor is wired in Phase 3 —
so extract_fn defaults to "no events".

- preview(): fetch + extract in memory, persisting nothing (no run, no S3).
- execute_run(): create a run record, store all fetched content to S3, record
  per-link outcomes, extract, and finish the run. Scheduled runs advance the
  source's schedule; manual runs never shift it.
"""

import artifacts
import fetcher
import runs
import sources
import store


def _no_events(_pages):
    return []


def _acquire_root(source, fetch_fn, email_body):
    """Return (html, text, base_url, root_domain) for the source's root content."""
    if source["type"] == sources.WEBPAGE:
        url = source["identity"]
        _status, html = fetch_fn(url)
        return html, None, url, fetcher.host_of(url)
    # Email: the body is supplied by the caller (Gmail ingestion lives elsewhere).
    body = email_body or ""
    return body, body, None, source.get("identity", "")


def _gather_pages(source, *, fetch_fn, email_body, on_link_outcome=None,
                  store_linked=None):
    """Acquire the root plus (optionally) one level of same-domain links.
    Returns (pages, root_html, root_text). on_link_outcome / store_linked are
    callbacks used by execute_run to persist outcomes + pages."""
    html, text, base_url, root_domain = _acquire_root(source, fetch_fn, email_body)
    pages = [{"url": base_url, "content": text or html or ""}]

    if source.get("follow_links"):
        cap = int(store.get_settings()["link_follow_cap"])
        outcomes = fetcher.follow_links(
            html or "", base_url=base_url, root_domain=root_domain,
            cap=cap, fetch_fn=fetch_fn,
        )
        for index, outcome in enumerate(outcomes):
            record = {k: v for k, v in outcome.items() if k != "content"}
            if outcome["ok"]:
                if store_linked is not None:
                    record["s3_ref"] = store_linked(index, outcome["content"])
                pages.append({"url": outcome["url"], "content": outcome["content"]})
            if on_link_outcome is not None:
                on_link_outcome(record)
    return pages, html, text


def preview(source, *, fetch_fn=fetcher.fetch_url, extract_fn=_no_events,
            email_body=None):
    """Dry-run: fetch + extract without persisting any run or event records."""
    link_outcomes = []
    pages, _html, _text = _gather_pages(
        source, fetch_fn=fetch_fn, email_body=email_body,
        on_link_outcome=link_outcomes.append,
    )
    return {
        "events": extract_fn(pages),
        "link_outcomes": link_outcomes,
        "pages_fetched": len(pages),
    }


def execute_run(source, trigger, *, fetch_fn=fetcher.fetch_url,
                extract_fn=_no_events, email_body=None):
    """Run a source for real: persist a run record, store fetched content to S3,
    record per-link outcomes, extract, and finish the run."""
    source_id = source["source_id"]
    run = runs.start_run(source_id, trigger)
    run_id = run["run_id"]
    if trigger == runs.TRIGGER_SCHEDULED:
        sources.advance_schedule(source_id)

    try:
        def _store_linked(index, content):
            return artifacts.store_linked_page(source_id, run_id, index, content)

        pages, root_html, root_text = _gather_pages(
            source, fetch_fn=fetch_fn, email_body=email_body,
            on_link_outcome=lambda rec: runs.add_link_outcome(source_id, run_id, rec),
            store_linked=_store_linked,
        )
        if root_html:
            runs.set_artifacts(source_id, run_id,
                               root_html=artifacts.store_root_html(source_id, run_id, root_html))
        if root_text:
            runs.set_artifacts(source_id, run_id,
                               root_body=artifacts.store_root_body(source_id, run_id, root_text))

        events = extract_fn(pages)
        runs.finish_run(source_id, run_id, status=runs.SUCCESS,
                        events_count=len(events),
                        summary={"events": len(events), "pages": len(pages)})
    except Exception as exc:  # pylint: disable=broad-except
        runs.finish_run(source_id, run_id, status=runs.ERROR, error_reason=str(exc))

    return runs.get_run(source_id, run_id)
