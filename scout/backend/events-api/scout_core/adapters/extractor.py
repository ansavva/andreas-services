"""
Event extraction via the Anthropic Messages API (two-pass).

Our own code acquires the source content (fetcher / gmail / pipeline); this
module turns that fetched text into structured events with Claude. Extraction
runs in two passes so the model gets focused, high-signal context instead of one
giant blob:

1. triage()  — a cheap/fast model reads each fetched page and reports the
   distinct candidate events it sees, plus, per candidate, the single best
   "detail" URL to open and a best-effort fallback event built from what is
   already visible. (The pipeline then fetches those detail pages.)
2. enrich()  — a stronger model is given one candidate's mention plus the text
   of its fetched detail page and returns the full, accurate event record.

Both passes use Anthropic tool-use with a forced tool so the model returns a
validated JSON object (no fragile free-text parsing), a system prompt that
anchors relative dates to "today", temperature 0, and prompt caching on the
static system + tool blocks. The API call is isolated behind an injectable
`runner` so the pipeline and tests can supply a scripted response. The runner
yields normalized message dicts:

    {"role": "result", "tool_input": dict|None, "text": str,
     "usage": {"input_tokens", "output_tokens"}}

The legacy single-pass extract()/build_prompt()/parse_events() helpers are kept
for back-compat and as a text-parsing fallback.
"""

import json
import time

STATUS_COMPLETED = "completed"
STATUS_BUDGET_EXCEEDED = "budget_exceeded"
STATUS_ERROR = "error"

# Cap the prompt's embedded source content (~30k tokens) and the model's output.
MAX_CONTENT_CHARS = 120000
MAX_OUTPUT_TOKENS = 16000


class BudgetExceeded(Exception):
    """Raised when a token or runtime budget cap is hit."""


class ExtractionResult:
    def __init__(self, status, *, events=None, transcript=None,
                 usage=None, error=None):
        self.status = status
        self.events = events or []
        self.transcript = transcript or []
        self.usage = usage or {"input_tokens": 0, "output_tokens": 0}
        self.error = error


class TriageResult:
    def __init__(self, status, *, candidates=None, listing_urls=None,
                 transcript=None, usage=None, error=None):
        self.status = status
        self.candidates = candidates or []
        self.listing_urls = listing_urls or []
        self.transcript = transcript or []
        self.usage = usage or {"input_tokens": 0, "output_tokens": 0}
        self.error = error


# ---------------------------------------------------------------------------
# Tool schemas (forced tool-use → validated structured output)
# ---------------------------------------------------------------------------

_LOCATION_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "name": {"type": "string"},
        "address": {"type": "string"},
        "timezone": {"type": "string", "description": "IANA tz, e.g. Europe/London"},
    },
}

_EVENT_PROPERTIES = {
    "title": {"type": "string"},
    "description": {"type": "string", "description": "concise markdown"},
    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
    "start_time": {"type": ["string", "null"], "description": "HH:MM 24h or null"},
    "end_time": {"type": ["string", "null"], "description": "HH:MM 24h or null"},
    "location": _LOCATION_SCHEMA,
    "event_labels": {"type": "array", "items": {"type": "string"}},
    "images": {"type": "array", "items": {"type": "string"}},
    "sub_events": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "start_time": {"type": ["string", "null"]},
                "end_time": {"type": ["string", "null"]},
                "location": _LOCATION_SCHEMA,
                "event_labels": {"type": ["array", "null"], "items": {"type": "string"}},
            },
        },
    },
}

RECORD_EVENTS_TOOL = {
    "name": "record_events",
    "description": "Record the structured event listing(s) extracted from the content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": _EVENT_PROPERTIES,
                    "required": ["title"],
                },
            },
        },
        "required": ["events"],
    },
}

REPORT_CANDIDATES_TOOL = {
    "name": "report_candidates",
    "description": "Report each distinct, attendable event found in the content, "
                   "plus any links to pages listing further events.",
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "hints": {
                            "type": "string",
                            "description": "verbatim date/time/venue text seen here",
                        },
                        "detail_url": {
                            "type": ["string", "null"],
                            "description": "URL of THIS event's own full-details page "
                                           "(organizer / ticketing / event page), or null",
                        },
                        "fallback_event": {
                            "type": "object",
                            "description": "best-effort fields from what's visible now",
                            "properties": _EVENT_PROPERTIES,
                        },
                    },
                    "required": ["title"],
                },
            },
            "listing_urls": {
                "type": "array",
                "description": "URLs of pages that list MORE events (a 'what's on' / "
                               "events index / category page), not a single event. "
                               "Used to discover events not detailed in this content.",
                "items": {"type": "string"},
            },
        },
        "required": ["candidates"],
    },
}


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _date_clause(now, timezone):
    return (f"Today is {now} ({timezone}). Resolve every relative date "
            f'("this Friday", "next weekend", "tonight") against this date. '
            "Never output a date in the past unless the source explicitly "
            "describes an event that already happened.")


def build_triage_system(*, now, timezone):
    """System prompt for pass 1 — find events + their detail links (no full
    extraction yet)."""
    return (
        "You are an event scout. You read raw content from an email newsletter "
        "or a webpage and identify every distinct, real-world event a person "
        "could attend (concerts, shows, markets, talks, classes, screenings, "
        "festivals, etc.).\n\n"
        + _date_clause(now, timezone) + "\n\n"
        "Do not extract full details yet. For each event capture: a short "
        "title; any date/time/venue hints visible here (verbatim is fine); and "
        "detail_url — the link to THIS event's own full-details page (organizer "
        "/ ticketing / event page), or null if none clearly belongs to it. Also "
        "fill fallback_event with whatever fields you can already tell from this "
        "content, in case no detail page is available.\n\n"
        "Separately, put into listing_urls any links that lead to a page listing "
        "MORE events — a 'what's on', events index, calendar, or category page — "
        "rather than one specific event. These are followed to discover events "
        "not described here. A link is a listing only when it plausibly contains "
        "several events; when in doubt, treat a single-event page as detail_url, "
        "not a listing.\n\n"
        "Ignore navigation, ads, unsubscribe/preferences/social links, and "
        "anything that is not an attendable event. If there are no events and no "
        "listing links, report empty lists."
    )


def build_enrich_system(*, now, timezone, known_labels=None):
    """System prompt for pass 2 — produce one clean, complete event listing."""
    labels_line = (
        "event_labels: prefer these existing labels — "
        + ", ".join(known_labels) + ". Only invent a new label when none fit."
    ) if known_labels else (
        "event_labels: short, lowercase topical tags (e.g. music, theatre, family)."
    )
    return (
        "You are an event scout building one clean calendar listing.\n\n"
        + _date_clause(now, timezone) + "\n\n"
        "You are given (1) the original mention of one event and (2) the full "
        "text of its detail page (when available). Produce the most accurate, "
        "complete listing:\n"
        "- Prefer the detail page for dates, times, venue, address and "
        "description; fall back to the mention when the page is missing or "
        "thin.\n"
        "- description: concise, useful markdown (what it is, who it's for, "
        "notable details). No marketing fluff or unsubscribe text.\n"
        "- start_date YYYY-MM-DD; start_time/end_time HH:MM 24h or null.\n"
        "- location.timezone: the IANA timezone of the venue's city.\n"
        "- Use sub_events when this single event recurs on multiple distinct "
        "dates.\n"
        "- " + labels_line + "\n"
        "- images: direct image URLs for the event, if any.\n\n"
        "If this turns out not to be a real attendable event, record an empty "
        "list."
    )


def _page_header(page):
    src = page.get("url") or "root content"
    date = page.get("date")
    return f"----- SOURCE: {src} (received {date}) -----" if date else f"----- SOURCE: {src} -----"


def build_triage_prompt(pages):
    """User content for pass 1: the fetched pages embedded inline."""
    sections = [f"{_page_header(p)}\n{p.get('content') or ''}" for p in pages]
    body = "\n\n".join(sections)
    if len(body) > MAX_CONTENT_CHARS:
        body = body[:MAX_CONTENT_CHARS]
    return "===== SOURCE CONTENT =====\n" + body


def build_enrich_prompt(candidate, page_text, *, source=None, date=None):
    """User content for pass 2: one event's mention + its detail page text."""
    src = source or "source"
    received = f", received {date}" if date else ""
    parts = [
        f"===== EVENT MENTION (from {src}{received}) =====",
        (candidate.get("title") or "").strip(),
    ]
    hints = (candidate.get("hints") or "").strip()
    if hints:
        parts.append(hints)
    detail_url = candidate.get("detail_url")
    if page_text:
        parts.append("")
        header = f"===== DETAIL PAGE: {detail_url} =====" if detail_url else "===== DETAIL PAGE ====="
        parts.append(header)
        body = page_text
        if len(body) > MAX_CONTENT_CHARS:
            body = body[:MAX_CONTENT_CHARS]
        parts.append(body)
    return "\n".join(parts)


# Legacy single-pass prompt (kept for back-compat / text fallback) --------------

_SCHEMA = """Return ONLY a JSON object of the form:
{
  "events": [
    {
      "title": "string",
      "description": "string (markdown)",
      "start_date": "YYYY-MM-DD",
      "start_time": "HH:MM or null",
      "end_time": "HH:MM or null",
      "location": {"name": "string", "address": "string", "timezone": "IANA tz"} or null,
      "event_labels": ["string", ...],
      "images": ["https://...", ...],
      "sub_events": [
        {"start_date": "YYYY-MM-DD", "start_time": "HH:MM or null",
         "end_time": "HH:MM or null", "location": {...} or null,
         "event_labels": ["string", ...] or null}
      ]
    }
  ]
}
Use sub_events when a single event spans multiple distinct dates. If no events
are present, return {"events": []}. Output only the JSON, no prose."""


def build_prompt(pages):
    """Legacy single extraction prompt with page contents embedded inline."""
    sections = []
    for page in pages:
        src = page.get("url") or "root content"
        sections.append(f"----- SOURCE: {src} -----\n{page.get('content') or ''}")
    body = "\n\n".join(sections)
    if len(body) > MAX_CONTENT_CHARS:
        body = body[:MAX_CONTENT_CHARS]
    return (
        "You extract structured event listings from the fetched source content "
        "below. " + _SCHEMA + "\n\n===== SOURCE CONTENT =====\n" + body
    )


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

def _strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _normalize_location(raw):
    return raw if isinstance(raw, dict) else None


def _normalize_event(raw):
    title = (raw.get("title") or "").strip()
    if not title:
        return None
    event = {
        "title": title,
        "description": raw.get("description") or "",
        "start_date": raw.get("start_date") or "",
        "start_time": raw.get("start_time") or None,
        "end_time": raw.get("end_time") or None,
        "location": _normalize_location(raw.get("location")),
        "event_labels": [s for s in (raw.get("event_labels") or []) if s],
        "images": [s for s in (raw.get("images") or []) if s],
        "event_url": raw.get("event_url") or None,
        "sub_events": [],
    }
    for sub in raw.get("sub_events") or []:
        if not isinstance(sub, dict):
            continue
        event["sub_events"].append({
            "start_date": sub.get("start_date") or "",
            "start_time": sub.get("start_time") or None,
            "end_time": sub.get("end_time") or None,
            "location": _normalize_location(sub.get("location")),
            "event_labels": [s for s in (sub.get("event_labels") or []) if s] or None,
        })
    return event


def _normalize_candidate(raw):
    title = (raw.get("title") or "").strip()
    if not title:
        return None
    detail_url = raw.get("detail_url")
    fallback = raw.get("fallback_event")
    fallback = dict(fallback) if isinstance(fallback, dict) else {}
    fallback["title"] = title
    return {
        "title": title,
        "hints": raw.get("hints") or "",
        "detail_url": detail_url if isinstance(detail_url, str) and detail_url else None,
        "fallback_event": _normalize_event(fallback),
    }


def _events_from_payload(payload):
    raw_events = payload.get("events", []) if isinstance(payload, dict) else payload
    normalized = [_normalize_event(e) for e in (raw_events or []) if isinstance(e, dict)]
    return [e for e in normalized if e is not None]


def parse_events(transcript):
    """Find the final tool_input (or textual output) in the transcript and parse
    events from it."""
    for message in reversed(transcript):
        payload = message.get("tool_input")
        if payload is None:
            text = (message.get("text") or "").strip()
            if not text:
                continue
            payload = json.loads(_strip_fences(text))
        return _events_from_payload(payload)
    return []


def _triage_from_payload(payload):
    """Return (candidates, listing_urls) from a report_candidates payload."""
    if not isinstance(payload, dict):
        raw_candidates, raw_listings = payload, []
    else:
        raw_candidates = payload.get("candidates", [])
        raw_listings = payload.get("listing_urls", [])
    candidates = [_normalize_candidate(c) for c in (raw_candidates or [])
                  if isinstance(c, dict)]
    candidates = [c for c in candidates if c is not None]
    listings = [u for u in (raw_listings or []) if isinstance(u, str) and u]
    return candidates, listings


def parse_candidates(transcript):
    """Find the final tool_input (or text) and parse it into (candidates,
    listing_urls)."""
    for message in reversed(transcript):
        payload = message.get("tool_input")
        if payload is None:
            text = (message.get("text") or "").strip()
            if not text:
                continue
            payload = json.loads(_strip_fences(text))
        return _triage_from_payload(payload)
    return [], []


# ---------------------------------------------------------------------------
# Shared call runner with one retry
# ---------------------------------------------------------------------------

def _run_once(runner, *, system, prompt, model, tools, tool_choice,
              budget_tokens, budget_seconds):
    """Drive the runner for one logical call, accumulating usage and enforcing
    the budget. Returns (transcript, usage). Raises BudgetExceeded."""
    transcript = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    started = time.monotonic()
    for message in runner(system=system, prompt=prompt, model=model, tools=tools,
                          tool_choice=tool_choice, budget_seconds=budget_seconds):
        transcript.append(message)
        msg_usage = message.get("usage") or {}
        usage["input_tokens"] += int(msg_usage.get("input_tokens", 0) or 0)
        usage["output_tokens"] += int(msg_usage.get("output_tokens", 0) or 0)
        if budget_seconds and (time.monotonic() - started) > budget_seconds:
            raise BudgetExceeded("runtime budget exceeded")
        if budget_tokens and (usage["input_tokens"] + usage["output_tokens"]) > budget_tokens:
            raise BudgetExceeded("token budget exceeded")
    return transcript, usage


def _call_with_retry(runner, *, system, prompt, model, tools, tool_choice,
                     parse, budget_tokens, budget_seconds):
    """Run a logical call (with one retry on parse/empty failure) and parse the
    payload. Returns (status, parsed, transcript, usage, error)."""
    runner = runner or default_runner
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    last_transcript = []
    last_error = None
    for attempt in range(2):
        try:
            transcript, usage = _run_once(
                runner, system=system, prompt=prompt, model=model, tools=tools,
                tool_choice=tool_choice, budget_tokens=budget_tokens,
                budget_seconds=budget_seconds)
        except BudgetExceeded as exc:
            return STATUS_BUDGET_EXCEEDED, None, last_transcript, total_usage, str(exc)
        except Exception as exc:  # pylint: disable=broad-except
            last_error = str(exc)
            continue
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        last_transcript = transcript
        try:
            parsed = parse(transcript)
        except (ValueError, TypeError) as exc:
            last_error = f"failed to parse model output: {exc}"
            continue
        return STATUS_COMPLETED, parsed, transcript, total_usage, None
    return STATUS_ERROR, None, last_transcript, total_usage, last_error or "extraction failed"


# ---------------------------------------------------------------------------
# Two-pass extraction
# ---------------------------------------------------------------------------

def triage(pages, *, model, now, timezone, budget_tokens=None,
           budget_seconds=None, runner=None):
    """Pass 1: report candidate events (+ their detail URLs) and any links to
    pages listing further events."""
    system = build_triage_system(now=now, timezone=timezone)
    prompt = build_triage_prompt(pages)
    status, parsed, transcript, usage, error = _call_with_retry(
        runner, system=system, prompt=prompt, model=model,
        tools=[REPORT_CANDIDATES_TOOL],
        tool_choice={"type": "tool", "name": "report_candidates"},
        parse=parse_candidates, budget_tokens=budget_tokens,
        budget_seconds=budget_seconds)
    candidates, listing_urls = parsed if parsed else ([], [])
    return TriageResult(status, candidates=candidates, listing_urls=listing_urls,
                        transcript=transcript, usage=usage, error=error)


def enrich(candidate, page_text, *, model, now, timezone, known_labels=None,
           source=None, date=None, budget_tokens=None, budget_seconds=None,
           runner=None):
    """Pass 2: produce the full event record for one candidate."""
    system = build_enrich_system(now=now, timezone=timezone, known_labels=known_labels)
    prompt = build_enrich_prompt(candidate, page_text, source=source, date=date)
    status, events, transcript, usage, error = _call_with_retry(
        runner, system=system, prompt=prompt, model=model,
        tools=[RECORD_EVENTS_TOOL],
        tool_choice={"type": "tool", "name": "record_events"},
        parse=parse_events, budget_tokens=budget_tokens,
        budget_seconds=budget_seconds)
    return ExtractionResult(status, events=events, transcript=transcript,
                            usage=usage, error=error)


# ---------------------------------------------------------------------------
# Legacy single-pass extraction (back-compat)
# ---------------------------------------------------------------------------

def extract(pages, *, model, budget_tokens=None, budget_seconds=None, runner=None):
    """Run a single-call extraction over the fetched pages under a budget cap.
    Kept for back-compat; the pipeline now uses triage()/enrich()."""
    runner = runner or default_runner
    prompt = build_prompt(pages)

    transcript = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    started = time.monotonic()

    try:
        for message in runner(prompt=prompt, model=model, budget_seconds=budget_seconds):
            transcript.append(message)
            msg_usage = message.get("usage") or {}
            usage["input_tokens"] += int(msg_usage.get("input_tokens", 0) or 0)
            usage["output_tokens"] += int(msg_usage.get("output_tokens", 0) or 0)

            if budget_seconds and (time.monotonic() - started) > budget_seconds:
                raise BudgetExceeded("runtime budget exceeded")
            if budget_tokens and (usage["input_tokens"] + usage["output_tokens"]) > budget_tokens:
                raise BudgetExceeded("token budget exceeded")
    except BudgetExceeded as exc:
        return ExtractionResult(STATUS_BUDGET_EXCEEDED, transcript=transcript,
                                usage=usage, error=str(exc))
    except Exception as exc:  # pylint: disable=broad-except
        return ExtractionResult(STATUS_ERROR, transcript=transcript,
                                usage=usage, error=str(exc))

    try:
        events = parse_events(transcript)
    except (ValueError, TypeError) as exc:
        return ExtractionResult(STATUS_ERROR, transcript=transcript,
                                usage=usage, error=f"failed to parse model output: {exc}")

    return ExtractionResult(STATUS_COMPLETED, events=events, transcript=transcript,
                            usage=usage)


# ---------------------------------------------------------------------------
# Default runner (Anthropic Messages API, tool-use)
# ---------------------------------------------------------------------------

def default_runner(*, prompt, model, system=None, tools=None, tool_choice=None,
                   budget_seconds=None):
    """One Anthropic Messages API call. Yields a single normalized result
    message. Imported lazily so this module loads without the SDK installed.

    When `tools`/`tool_choice` are given the forced tool's input is yielded as
    `tool_input` (validated structured output); otherwise the text is yielded
    for the legacy JSON-parsing path. The static system prompt + tool schema are
    marked for prompt caching."""
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic()
    kwargs = {
        "model": model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "timeout": float(budget_seconds) if budget_seconds else 120.0,
    }
    if system:
        kwargs["system"] = [{
            "type": "text", "text": system,
            "cache_control": {"type": "ephemeral"},
        }]
    if tools:
        cached_tools = [dict(t) for t in tools]
        cached_tools[-1]["cache_control"] = {"type": "ephemeral"}
        kwargs["tools"] = cached_tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice

    try:
        response = client.messages.create(**kwargs)
    except anthropic.APITimeoutError as exc:
        raise BudgetExceeded("runtime budget exceeded") from exc

    text = "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    )
    tool_input = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_input = block.input
            break

    usage = getattr(response, "usage", None)
    yield {
        "role": "result",
        "tool_input": tool_input,
        "text": text,
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        },
    }
