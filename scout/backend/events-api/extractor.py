"""
Event extraction via the Claude Agent SDK.

Our own code acquires the source content (fetcher/pipeline); this module hands
the pre-fetched pages to a Claude Agent SDK agent whose only job is extraction.
The agent is granted Read (to read the fetched content written to its working
directory) plus unconstrained WebFetch and WebSearch. We record the full
transcript and a per-tool usage summary, and enforce a token + runtime budget,
aborting cleanly if either is exceeded.

The SDK call is isolated behind `runner` so the pipeline and tests can inject a
scripted message stream; the default runner uses the real `claude_agent_sdk`
package (imported lazily so this module loads without it). The runner yields
normalized message dicts:

    {"role": "assistant"|"result", "text": str,
     "tools": [{"name": str, "input": dict}], "usage": {"input_tokens", "output_tokens"}}
"""

import json
import time

ALLOWED_TOOLS = ["Read", "WebFetch", "WebSearch"]

STATUS_COMPLETED = "completed"
STATUS_BUDGET_EXCEEDED = "budget_exceeded"
STATUS_ERROR = "error"


class BudgetExceeded(Exception):
    """Raised when a token or runtime budget cap is hit mid-run."""


class ExtractionResult:
    def __init__(self, status, *, events=None, transcript=None,
                 tool_use_summary=None, usage=None, error=None):
        self.status = status
        self.events = events or []
        self.transcript = transcript or []
        self.tool_use_summary = tool_use_summary or []
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
    """Return (prompt, files) where files maps a filename to its content; the
    agent reads those files from its working directory via the Read tool."""
    files = {}
    listing = []
    for index, page in enumerate(pages):
        name = f"page_{index}.txt"
        files[name] = page.get("content") or ""
        listing.append(f"- {name} (from: {page.get('url') or 'root content'})")
    prompt = (
        "You extract structured event listings from fetched source content.\n"
        "Read each of these files in your working directory:\n"
        + "\n".join(listing)
        + "\n\nYou may use WebFetch and WebSearch to resolve missing details "
        "(dates, venue, address). " + _SCHEMA
    )
    return prompt, files


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
    """Run the extraction agent over the fetched pages under a budget cap.
    Returns an ExtractionResult; partial output is discarded on budget/error."""
    runner = runner or default_runner
    prompt, files = build_prompt(pages)

    transcript = []
    tool_counts = {}
    usage = {"input_tokens": 0, "output_tokens": 0}
    started = time.monotonic()

    try:
        for message in runner(prompt=prompt, files=files, model=model,
                              allowed_tools=ALLOWED_TOOLS,
                              budget_seconds=budget_seconds):
            transcript.append(message)
            for tool in message.get("tools", []):
                rec = tool_counts.setdefault(
                    tool["name"], {"tool": tool["name"], "count": 0, "args": []})
                rec["count"] += 1
                rec["args"].append(tool.get("input", {}))
            msg_usage = message.get("usage") or {}
            usage["input_tokens"] += int(msg_usage.get("input_tokens", 0) or 0)
            usage["output_tokens"] += int(msg_usage.get("output_tokens", 0) or 0)

            if budget_seconds and (time.monotonic() - started) > budget_seconds:
                raise BudgetExceeded("runtime budget exceeded")
            if budget_tokens and (usage["input_tokens"] + usage["output_tokens"]) > budget_tokens:
                raise BudgetExceeded("token budget exceeded")
    except BudgetExceeded as exc:
        return ExtractionResult(STATUS_BUDGET_EXCEEDED, transcript=transcript,
                                tool_use_summary=list(tool_counts.values()),
                                usage=usage, error=str(exc))
    except Exception as exc:  # pylint: disable=broad-except
        return ExtractionResult(STATUS_ERROR, transcript=transcript,
                                tool_use_summary=list(tool_counts.values()),
                                usage=usage, error=str(exc))

    try:
        events = parse_events(transcript)
    except (ValueError, TypeError) as exc:
        return ExtractionResult(STATUS_ERROR, transcript=transcript,
                                tool_use_summary=list(tool_counts.values()),
                                usage=usage, error=f"failed to parse agent output: {exc}")

    return ExtractionResult(STATUS_COMPLETED, events=events, transcript=transcript,
                            tool_use_summary=list(tool_counts.values()), usage=usage)


def default_runner(*, prompt, files, model, allowed_tools, budget_seconds):
    """Run the real Claude Agent SDK, enforcing the runtime budget, and yield
    normalized message dicts. Imported lazily so this module loads without the
    SDK installed (the source-run-processor image declares the dependency)."""
    import asyncio
    import tempfile

    from claude_agent_sdk import (  # noqa: PLC0415
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        query,
    )

    with tempfile.TemporaryDirectory() as workdir:
        for name, content in files.items():
            with open(f"{workdir}/{name}", "w", encoding="utf-8") as handle:
                handle.write(content)

        options = ClaudeAgentOptions(
            model=model,
            allowed_tools=allowed_tools,
            permission_mode="acceptEdits",
            cwd=workdir,
        )

        async def _collect():
            collected = []
            async for message in query(prompt=prompt, options=options):
                collected.append(_normalize_sdk_message(
                    message, AssistantMessage, ResultMessage, TextBlock, ToolUseBlock))
            return collected

        try:
            messages = asyncio.run(asyncio.wait_for(_collect(), timeout=budget_seconds))
        except asyncio.TimeoutError as exc:
            raise BudgetExceeded("runtime budget exceeded") from exc

    yield from messages


def _normalize_sdk_message(message, AssistantMessage, ResultMessage, TextBlock,
                           ToolUseBlock):
    if isinstance(message, AssistantMessage):
        text_parts, tools = [], []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tools.append({"name": block.name, "input": block.input})
        return {"role": "assistant", "text": "".join(text_parts), "tools": tools}
    if isinstance(message, ResultMessage):
        usage = getattr(message, "usage", None) or {}
        return {
            "role": "result",
            "text": getattr(message, "result", "") or "",
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        }
    return {"role": "other", "text": ""}
