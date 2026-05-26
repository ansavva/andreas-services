"""
Timezone-aware date/time helpers for the event lifecycle.

Dates/times are entered in an event's location timezone (or the system fallback
timezone when there's no location). We resolve them once to a stable UTC instant
(effective_end_utc) so "past / in-grace" becomes a plain UTC comparison that can
be indexed and swept without per-read timezone math.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(name, fallback="UTC"):
    try:
        return ZoneInfo(name or fallback)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _parse_hm(value):
    parts = str(value).split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return hour, minute


def effective_end_utc(start_date, start_time=None, end_time=None, *,
                      tz="UTC", fallback_tz="UTC"):
    """The UTC instant an occurrence ends. With an end_time, that time on the
    start date; otherwise the end of the start date (23:59:59). Returns None for
    an undated occurrence."""
    if not start_date:
        return None
    tzinfo = zone(tz or fallback_tz)
    year, month, day = (int(p) for p in start_date.split("-"))
    if end_time:
        hour, minute = _parse_hm(end_time)
        local = datetime(year, month, day, hour, minute, tzinfo=tzinfo)
    else:
        local = datetime(year, month, day, 23, 59, 59, tzinfo=tzinfo)
    return local.astimezone(timezone.utc).isoformat()


def is_past(effective_end, grace_hours=0, now=None):
    """True once the effective end (plus grace) is in the past."""
    if not effective_end:
        return False
    now = now or datetime.now(timezone.utc)
    end = datetime.fromisoformat(effective_end)
    return now > end + timedelta(hours=float(grace_hours or 0))
