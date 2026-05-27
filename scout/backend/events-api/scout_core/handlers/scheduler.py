"""
Scheduler Lambda entrypoint.

Triggered on a fixed EventBridge cadence. Finds sources whose next_run_at is due
(in the system timezone) and dispatches a scheduled run for each by invoking the
processor Lambda asynchronously, then advances each source's schedule so it is
not re-dispatched before the run completes. Manual runs go straight to the
processor and never pass through here.
"""

import json
import logging
import os

import boto3

from scout_core.domain import runs
from scout_core.domain import sources

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_SUFFIX = os.environ.get("SCOUT_TABLE_SUFFIX", "")
_PROCESSOR_FN = os.environ.get("SCOUT_PROCESSOR_FN", f"scout-source-run-processor{_SUFFIX}")

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


def lambda_handler(event, context):
    # Scan the Gmail "Events" label first so newly-seen sender domains become
    # active email sources (picked up on a subsequent tick once due). Gmail
    # access lives in the processor, so this is a fire-and-forget invoke.
    _lambda().invoke(
        FunctionName=_PROCESSOR_FN,
        InvocationType="Event",
        Payload=json.dumps({"mode": "discover"}).encode(),
    )

    dispatched = []
    for source in sources.due_sources():
        source_id = source["source_id"]
        _lambda().invoke(
            FunctionName=_PROCESSOR_FN,
            InvocationType="Event",
            Payload=json.dumps({"source_id": source_id,
                                "trigger": runs.TRIGGER_SCHEDULED}).encode(),
        )
        sources.advance_schedule(source_id)
        dispatched.append(source_id)
    logger.info("Dispatched %d scheduled run(s)", len(dispatched))
    return {"dispatched": dispatched}
