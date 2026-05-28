"""
Event extraction via the Anthropic Messages API.

Our own code acquires the source content (fetcher / gmail / pipeline); this
module sends that fetched text to Claude in a single Messages API call and parses
the structured events out of the JSON response. We previously drove this through
the Claude Agent SDK (which spawns the Claude Code CLI), but that subprocess is
unreliable inside Lambda — a direct API call is simpler, faster, and cheaper.

The API call is isolated behind `runner` so the pipeline and tests can inject a
scripted response; the default runner uses the `anthropic` package (imported
lazily so this module loads without it). The runner yields normalized message
dicts:

    {"role": "result", "text": str, "usage": {"input_tokens", "output_tokens"}}
"""

import json
import time

STATUS_COMPLETED = "completed"
STATUS_BUDGET_EXCEEDED = "budget_exceeded"
STATUS_ERROR = "error"

# Cap the prompt's embedded source content (~30k tokens) and the model's output.
MAX_CONTENT_CHARS = 120000
MAX_OUTPUT_TOKENS = 8000


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


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

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
    """A single extraction prompt with the fetched page contents embedded inline
    (the model extracts from this text directly — no tools)."""
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
        "location": raw.get("location") if isinstance(raw.get("location"), dict) else None,
        "event_labels": [s for s in (raw.get("event_labels") or []) if s],
        "images": [s for s in (raw.get("images") or []) if s],
        "sub_events": [],
    }
    for sub in raw.get("sub_events") or []:
        if not isinstance(sub, dict):
            continue
        event["sub_events"].append({
            "start_date": sub.get("start_date") or "",
            "start_time": sub.get("start_time") or None,
            "end_time": sub.get("end_time") or None,
            "location": sub.get("location") if isinstance(sub.get("location"), dict) else None,
            "event_labels": [s for s in (sub.get("event_labels") or []) if s] or None,
        })
    return event


def parse_events(transcript):
    """Find the final textual output in the transcript and parse events from it."""
    for message in reversed(transcript):
        text = (message.get("text") or "").strip()
        if not text:
            continue
        payload = json.loads(_strip_fences(text))
        raw_events = payload.get("events", []) if isinstance(payload, dict) else payload
        normalized = [_normalize_event(e) for e in raw_events if isinstance(e, dict)]
        return [e for e in normalized if e is not None]
    return []


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract(pages, *, model, budget_tokens=None, budget_seconds=None, runner=None):
    """Run the extraction over the fetched pages under a budget cap. Returns an
    ExtractionResult; partial output is discarded on budget/error."""
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


def default_runner(*, prompt, model, budget_seconds):
    """One Anthropic Messages API call. Yields a single normalized result message.
    Imported lazily so this module loads without the SDK installed."""
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=float(budget_seconds) if budget_seconds else 120.0,
        )
    except anthropic.APITimeoutError as exc:
        raise BudgetExceeded("runtime budget exceeded") from exc

    text = "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    )
    usage = getattr(response, "usage", None)
    yield {
        "role": "result",
        "text": text,
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        },
    }
