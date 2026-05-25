"""
Source-run processor Lambda entrypoint.

Invoked (async) by the scheduler for due sources and by the admin console for
manual runs and previews. Runs the fetch + Agent SDK extraction pipeline for one
source. Shares the scout-core image with the events API; the Lambda function
overrides the image command to point here.

Event payload: {"source_id": str, "trigger"?: "scheduled"|"manual",
"mode"?: "run"|"preview", "email_body"?: str}.
"""

import logging

import pipeline
import runs
import sources
import store

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    source_id = event.get("source_id")
    if not source_id:
        return {"error": "source_id is required"}
    source = sources.get_source(source_id)
    if source is None:
        return {"error": "source not found"}

    settings = store.get_settings()
    extractor = pipeline.make_extractor(source, settings)
    email_body = event.get("email_body")

    if event.get("mode") == "preview":
        return pipeline.preview(source, extractor=extractor, email_body=email_body)

    trigger = event.get("trigger", runs.TRIGGER_MANUAL)
    run = pipeline.execute_run(source, trigger, extractor=extractor,
                               email_body=email_body)
    logger.info("Run %s for source %s finished: %s", run["run_id"], source_id,
                run["status"])
    return {"run_id": run["run_id"], "status": run["status"],
            "events_count": int(run.get("events_count", 0))}
