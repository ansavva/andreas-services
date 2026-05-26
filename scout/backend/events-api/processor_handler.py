"""
Source-run processor Lambda entrypoint.

Invoked (async) by the scheduler for due sources and by the admin console for
manual runs and previews. Runs the fetch + Agent SDK extraction pipeline for one
source. Shares the scout-core image with the events API; the Lambda function
overrides the image command to point here.

Event payload:
- {"mode": "discover"} — scan the Gmail "Events" label and ensure one active
  email source per sender domain.
- {"source_id": str, "trigger"?: "scheduled"|"manual", "mode"?: "run"|"preview",
  "email_body"?: str} — run/preview one source.
"""

import logging

import gmail
import pipeline
import runs
import sources
import store

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _discover():
    """Auto-create an active email source for every sender domain currently
    under the Gmail "Events" label."""
    ensured = []
    for domain in gmail.discover_domains():
        source, created = sources.ensure_email_source(domain)
        ensured.append({"domain": domain, "source_id": source["source_id"],
                        "created": created})
    logger.info("Discovery ensured %d email source(s)", len(ensured))
    return {"mode": "discover", "ensured": ensured}


def lambda_handler(event, context):
    if event.get("mode") == "discover":
        return _discover()

    source_id = event.get("source_id")
    if not source_id:
        return {"error": "source_id is required"}
    source = sources.get_source(source_id)
    if source is None:
        return {"error": "source not found"}

    settings = store.get_settings()
    extractor = pipeline.make_extractor(source, settings)
    email_body = event.get("email_body")

    # For email sources we pull the sender's recent Events-labeled mail from
    # Gmail, resuming from the source's stored cursor. An inline email_body
    # (tests / manual replay) bypasses the live fetch.
    gmail_fetch = None
    since_epoch = None
    if source["type"] == sources.EMAIL and email_body is None:
        def gmail_fetch(domain, since):
            return gmail.fetch_for_domain(domain, since_epoch=since)
        since_epoch = source.get("last_email_fetch_epoch")

    if event.get("mode") == "preview":
        return pipeline.preview(source, extractor=extractor, email_body=email_body,
                                gmail_fetch=gmail_fetch, since_epoch=since_epoch)

    trigger = event.get("trigger", runs.TRIGGER_MANUAL)
    run = pipeline.execute_run(source, trigger, extractor=extractor,
                               email_body=email_body, gmail_fetch=gmail_fetch,
                               since_epoch=since_epoch)
    logger.info("Run %s for source %s finished: %s", run["run_id"], source_id,
                run["status"])
    return {"run_id": run["run_id"], "status": run["status"],
            "events_count": int(run.get("events_count", 0))}
