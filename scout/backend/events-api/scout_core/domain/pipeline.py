"""
Run pipeline orchestration.

Ties together fetching (fetcher), artifact storage (artifacts), the run
lifecycle (runs) and extraction (extractor). Our code acquires the content; an
injected `extractor` callable (pages -> ExtractionResult) turns the fetched
pages into events. The default is a no-op extractor (zero events); the real
Claude Agent SDK extractor is supplied by the caller via make_extractor().

- preview(): fetch + extract in memory, persisting nothing (no run, no S3).
- execute_run(): create a run record, store all fetched content + the agent
  transcript to S3, record per-link outcomes and the tool-use summary, and
  finish the run — success on a completed extraction, error (with the distinct
  budget_exceeded reason) otherwise, discarding partial output.
  Scheduled runs advance the source's schedule; manual runs never shift it.
"""

import json
import time

from scout_core.adapters import artifacts
from scout_core.domain import events as events_mod
from scout_core.adapters import extractor as extractor_mod
from scout_core.adapters import fetcher
from scout_core.domain import notifications
from scout_core.domain import runs
from scout_core.domain import sources
from scout_core.adapters import store


def noop_extractor(_pages):
    return extractor_mod.ExtractionResult(extractor_mod.STATUS_COMPLETED, events=[])


def make_extractor(source, settings, *, runner=None):
    """Build a pages->ExtractionResult callable for a source, applying the
    per-source model/budget overrides on top of the system defaults."""
    model = source.get("agent_model_override") or settings["default_agent_model"]
    budget_tokens = (source.get("agent_budget_tokens_override")
                     or settings["default_agent_budget_tokens"])
    budget_seconds = (source.get("agent_budget_seconds_override")
                      or settings["default_agent_budget_seconds"])

    def _extract(pages):
        return extractor_mod.extract(
            pages, model=model, budget_tokens=int(budget_tokens),
            budget_seconds=int(budget_seconds), runner=runner,
        )

    return _extract


def _gather_webpage_pages(source, *, fetch_fn, on_link_outcome, store_linked):
    """Webpage root plus, when follow_links is on, one level of same-domain links.
    Returns (pages, root_html, root_text)."""
    url = source["identity"]
    _status, html = fetch_fn(url)
    pages = [{"url": url, "content": html or ""}]

    if source.get("follow_links"):
        cap = int(store.get_settings()["link_follow_cap"])
        outcomes = fetcher.follow_links(
            html or "", base_url=url, root_domain=fetcher.host_of(url),
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
    return pages, html, None


def _gather_email_pages(source, *, gmail_fetch, email_body, since_epoch,
                        on_link_outcome, store_linked):
    """Recent Events-labeled messages for the source's sender domain, one page
    per message. gmail_fetch(domain, since_epoch) -> [message dicts]; when it is
    absent an inline email_body stands in for a single message (test/manual seam).
    Returns (pages, None, None) — bodies are stored per-message, not as a root."""
    if gmail_fetch is not None:
        messages = gmail_fetch(source.get("identity", ""), since_epoch)
    elif email_body is not None:
        messages = [{"message_id": "inline", "subject": "", "body_markdown": email_body}]
    else:
        messages = []

    pages = []
    for index, message in enumerate(messages):
        content = message.get("body_markdown") or ""
        ref = f"gmail:{message.get('message_id', '')}"
        pages.append({"url": ref, "content": content})
        outcome = {"url": ref, "ok": True, "subject": message.get("subject", "")}
        if message.get("image_url"):
            outcome["image_url"] = message["image_url"]
        if store_linked is not None and content:
            outcome["s3_ref"] = store_linked(index, content)
        if on_link_outcome is not None:
            on_link_outcome(outcome)
    return pages, None, None


def _gather_pages(source, *, fetch_fn, email_body, gmail_fetch=None,
                  since_epoch=None, on_link_outcome=None, store_linked=None):
    """Acquire the content pages for a source. Returns (pages, root_html,
    root_text); root_* are None for email sources."""
    if source["type"] == sources.EMAIL:
        return _gather_email_pages(
            source, gmail_fetch=gmail_fetch, email_body=email_body,
            since_epoch=since_epoch, on_link_outcome=on_link_outcome,
            store_linked=store_linked)
    return _gather_webpage_pages(
        source, fetch_fn=fetch_fn, on_link_outcome=on_link_outcome,
        store_linked=store_linked)


def preview(source, *, fetch_fn=fetcher.fetch_url, extractor=noop_extractor,
            email_body=None, gmail_fetch=None, since_epoch=None):
    """Dry-run: fetch + extract without persisting any run or event records."""
    link_outcomes = []
    pages, _html, _text = _gather_pages(
        source, fetch_fn=fetch_fn, email_body=email_body,
        gmail_fetch=gmail_fetch, since_epoch=since_epoch,
        on_link_outcome=link_outcomes.append,
    )
    result = extractor(pages)
    return {
        "status": result.status,
        "events": result.events,
        "link_outcomes": link_outcomes,
        "pages_fetched": len(pages),
    }


def execute_run(source, trigger, *, fetch_fn=fetcher.fetch_url,
                extractor=noop_extractor, email_body=None, gmail_fetch=None,
                since_epoch=None):
    """Run a source for real: persist a run, store fetched content + transcript
    to S3, record outcomes + tool-use, and finish the run."""
    source_id = source["source_id"]
    run = runs.start_run(source_id, trigger)
    run_id = run["run_id"]
    fetch_started_epoch = int(time.time())
    # Note: advancing the schedule on scheduled runs is the scheduler's job (it
    # claims the slot at dispatch); manual runs never shift the schedule.

    try:
        def _store_linked(index, content):
            return artifacts.store_linked_page(source_id, run_id, index, content)

        pages, root_html, root_text = _gather_pages(
            source, fetch_fn=fetch_fn, email_body=email_body,
            gmail_fetch=gmail_fetch, since_epoch=since_epoch,
            on_link_outcome=lambda rec: runs.add_link_outcome(source_id, run_id, rec),
            store_linked=_store_linked,
        )
        if root_html:
            runs.set_artifacts(source_id, run_id,
                               root_html=artifacts.store_root_html(source_id, run_id, root_html))
        if root_text:
            runs.set_artifacts(source_id, run_id,
                               root_body=artifacts.store_root_body(source_id, run_id, root_text))

        result = extractor(pages)
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
