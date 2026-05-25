"""
In-app admin notifications.

Run failures raise a notification for the admin; budget-exceeded failures raise
a distinct one so the admin knows it was a cost cap rather than a content or
network problem. Notifications are global (no per-admin audit) and live in a
single partition, newest-first. Email/SMS alerting is out of scope.
"""

import store

TYPE_RUN_FAILURE = "run_failure"
TYPE_BUDGET_EXCEEDED = "budget_exceeded"

_PK = "NOTIF"


def create(notification_type, message, *, source_id=None, run_id=None,
           severity="error"):
    notification_id = store.new_id()
    item = store.base_item(
        _PK, f"N#{notification_id}", "notification",
        notification_id=notification_id,
        type=notification_type,
        message=message,
        source_id=source_id,
        run_id=run_id,
        severity=severity,
        read=False,
    )
    return store.put(item)


def list_notifications(*, unread_only=False):
    items = store.query_all(_PK, sk_begins_with="N#", ascending=False)
    if unread_only:
        items = [i for i in items if not i.get("read")]
    return items


def mark_read(notification_id):
    store.set_attrs(_PK, f"N#{notification_id}", {"read": True})
    return store.get(_PK, f"N#{notification_id}")


def notify_run_failure(source_id, run_id, reason):
    return create(TYPE_RUN_FAILURE, f"Run failed: {reason}",
                  source_id=source_id, run_id=run_id, severity="error")


def notify_budget_exceeded(source_id, run_id):
    return create(TYPE_BUDGET_EXCEEDED, "Run stopped: agent budget exceeded",
                  source_id=source_id, run_id=run_id, severity="warning")
