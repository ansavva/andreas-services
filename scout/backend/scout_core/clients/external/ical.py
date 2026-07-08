"""
Minimal iCalendar (RFC 5545) parser for event ingestion.

Some sources publish their events through a hosted calendar widget (e.g.
Tockify) that renders client-side from the provider's servers — the host page
contains no event data, so neither a plain fetch nor a headless render yields
anything. Those providers almost always expose a standard **iCal feed**, which
is the reliable, structured source. This module turns a feed's ``VEVENT``
components into scout's extracted-event dict shape
(``title``/``start_date``/``start_time``/``end_time``/``description``/
``location``), so the iCal run path can hand them straight to
``events.convert_extraction`` — no browser, no LLM.

Times are converted to the feed's timezone (``X-WR-TIMEZONE``, else a supplied
default) so the stored wall-clock date/time match what a calendar viewer shows.

Scope: concrete ``VEVENT`` instances as published. Recurrence rules (``RRULE``)
are not expanded — public feeds (Tockify, most "export" feeds) publish
pre-expanded instances for a window, which is what we ingest.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _unfold(text):
    """RFC 5545 line unfolding: a line beginning with a space or tab is a
    continuation of the previous line."""
    lines = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value):
    """Reverse RFC 5545 TEXT escaping."""
    return (value.replace("\\n", "\n").replace("\\N", "\n")
            .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def _parse_prop(line):
    """Split ``NAME[;param=val...]:value`` -> (NAME, params, value), or None."""
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _zone(name):
    try:
        return ZoneInfo(name) if name else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _parse_dt(value, params, feed_tz):
    """Parse a DTSTART/DTEND value to (date 'YYYY-MM-DD', time 'HH:MM' | None),
    localized to feed_tz. All-day (VALUE=DATE / bare YYYYMMDD) has no time."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d.strftime("%Y-%m-%d"), None
    is_utc = value.endswith("Z")
    core = value[:-1] if is_utc else value
    dt = datetime.strptime(core, "%Y%m%dT%H%M%S")
    if is_utc:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.replace(tzinfo=_zone(params.get("TZID")) or feed_tz or timezone.utc)
    local = dt.astimezone(feed_tz or timezone.utc)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def _build(props, feed_tz):
    summary = props.get("SUMMARY")
    title = _unescape(summary[1]).strip() if summary else ""
    if not title:
        return None
    event = {"title": title}
    if "DTSTART" in props:
        params, value = props["DTSTART"]
        date, start_time = _parse_dt(value, params, feed_tz)
        event["start_date"] = date
        if start_time:
            event["start_time"] = start_time
    if "DTEND" in props:
        params, value = props["DTEND"]
        _date, end_time = _parse_dt(value, params, feed_tz)
        if end_time:
            event["end_time"] = end_time
    desc = []
    if "DESCRIPTION" in props:
        desc.append(_unescape(props["DESCRIPTION"][1]).strip())
    if "URL" in props:
        desc.append(props["URL"][1].strip())
    event["description"] = "\n\n".join(d for d in desc if d)
    location = _unescape(props["LOCATION"][1]).strip() if "LOCATION" in props else ""
    if location:
        # iCal LOCATION is a single string, usually "Venue, street, city…".
        # Split the venue name from the address on the first comma so it matches
        # the {name, address} shape convert_extraction's location resolver wants.
        name, _, address = location.partition(",")
        event["location"] = {"name": name.strip(), "address": address.strip()}
    return event


def parse_events(ics_text, *, default_tz="UTC"):
    """Parse an iCal document into a list of extracted-event dicts (the shape
    ``events.convert_extraction`` consumes)."""
    lines = _unfold(ics_text)

    feed_tz_name = default_tz
    for line in lines:
        prop = _parse_prop(line)
        if prop and prop[0] == "X-WR-TIMEZONE" and prop[2].strip():
            feed_tz_name = prop[2].strip()
            break
    feed_tz = _zone(feed_tz_name) or timezone.utc

    events = []
    current = None
    for line in lines:
        prop = _parse_prop(line)
        if not prop:
            continue
        name, params, value = prop
        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            current = {}
        elif name == "END" and value.strip().upper() == "VEVENT":
            if current is not None:
                event = _build(current, feed_tz)
                if event:
                    events.append(event)
            current = None
        elif current is not None:
            current[name] = (params, value)
    return events
