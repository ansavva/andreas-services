"""
Sweep Lambda entrypoint.

Triggered on a fixed EventBridge cadence. Reconciles runs orphaned by a restart
(in-progress -> error) and refreshes the materialized `past` flag on
events/sub-events, applying the per-event auto-past-when-all-subs-past rule.
"""

import logging

import events
import runs

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    orphaned = runs.reconcile_orphaned_runs()
    past_changed = events.sweep()
    logger.info("Sweep reconciled %d orphaned run(s), updated %d past flag(s)",
                orphaned, past_changed)
    return {"orphaned_runs": orphaned, "past_changed": past_changed}
