"""Unit tests for the two-pass Anthropic-API extractor. The API call is stubbed.

The runner is the seam: it accepts the call kwargs (system/prompt/tools/…) and
yields normalized message dicts. Tests script tool_input (the structured-output
path) or text (the JSON fallback path)."""

import json
import unittest

from scout_core.adapters import extractor


def _runner_from(messages):
    """Build a runner that ignores inputs and replays a scripted message list."""
    def _runner(**_kwargs):
        yield from messages
    return _runner


def _capturing_runner(messages, captured):
    """Replay messages while recording the kwargs the runner was called with."""
    def _runner(**kwargs):
        captured.append(kwargs)
        yield from messages
    return _runner


_EVENT_INPUT = {"events": [{
    "title": "Jazz Night",
    "description": "Live jazz",
    "start_date": "2026-06-01",
    "start_time": "20:00",
    "location": {"name": "The Blue Note", "address": "131 W 3rd", "timezone": "America/New_York"},
    "event_labels": ["jazz", "live"],
    "images": ["https://x.com/a.jpg"],
    "sub_events": [{"start_date": "2026-06-02", "start_time": "20:00"}],
}]}

_CANDIDATES_INPUT = {"candidates": [{
    "title": "Jazz Night",
    "hints": "this Saturday, doors 7pm",
    "detail_url": "https://venue.org/jazz",
    "fallback_event": {"title": "Jazz Night", "start_date": "2026-05-30"},
}]}


class TestTriage(unittest.TestCase):
    def test_triage_parses_candidates_from_tool_input(self):
        messages = [{"role": "result", "tool_input": _CANDIDATES_INPUT,
                     "usage": {"input_tokens": 200, "output_tokens": 50}}]
        result = extractor.triage([{"url": "gmail:1", "content": "c", "date": "x"}],
                                  model="haiku", now="2026-05-29", timezone="UTC",
                                  runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(len(result.candidates), 1)
        cand = result.candidates[0]
        self.assertEqual(cand["title"], "Jazz Night")
        self.assertEqual(cand["detail_url"], "https://venue.org/jazz")
        self.assertEqual(cand["fallback_event"]["start_date"], "2026-05-30")
        self.assertEqual(result.usage["input_tokens"], 200)

    def test_triage_system_prompt_carries_today_and_tz(self):
        captured = []
        messages = [{"role": "result", "tool_input": {"candidates": []}}]
        extractor.triage([{"url": "u", "content": "c", "date": "Tue 27 May 2026"}],
                         model="haiku", now="2026-05-29", timezone="Europe/London",
                         runner=_capturing_runner(messages, captured))
        system = captured[0]["system"]
        self.assertIn("2026-05-29", system)
        self.assertIn("Europe/London", system)
        # The page's received date is surfaced in the user content for anchoring.
        self.assertIn("Tue 27 May 2026", captured[0]["prompt"])

    def test_triage_retries_once_on_malformed_then_fails(self):
        calls = {"n": 0}

        def _runner(**_kwargs):
            calls["n"] += 1
            yield {"role": "result", "text": "not json"}

        result = extractor.triage([{"content": "c"}], model="haiku",
                                  now="2026-05-29", timezone="UTC", runner=_runner)
        self.assertEqual(result.status, extractor.STATUS_ERROR)
        self.assertEqual(calls["n"], 2)  # one retry


class TestEnrich(unittest.TestCase):
    def test_enrich_parses_events_and_tracks_usage(self):
        messages = [{"role": "result", "tool_input": _EVENT_INPUT,
                     "usage": {"input_tokens": 300, "output_tokens": 130}}]
        result = extractor.enrich({"title": "Jazz Night"}, "detail page text",
                                  model="sonnet", now="2026-05-29", timezone="UTC",
                                  runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(len(result.events), 1)
        event = result.events[0]
        self.assertEqual(event["title"], "Jazz Night")
        self.assertEqual(len(event["sub_events"]), 1)
        self.assertEqual(event["location"]["name"], "The Blue Note")
        self.assertEqual(result.usage["output_tokens"], 130)

    def test_enrich_system_lists_known_labels(self):
        captured = []
        messages = [{"role": "result", "tool_input": {"events": []}}]
        extractor.enrich({"title": "X", "hints": "Fri"}, "page",
                         model="sonnet", now="2026-05-29", timezone="UTC",
                         known_labels=["music", "theatre"], source="gmail:1",
                         date="27 May", runner=_capturing_runner(messages, captured))
        self.assertIn("music", captured[0]["system"])
        self.assertIn("theatre", captured[0]["system"])
        # The mention + detail page are both in the user content.
        self.assertIn("EVENT MENTION", captured[0]["prompt"])
        self.assertIn("DETAIL PAGE", captured[0]["prompt"])

    def test_enrich_handles_text_json_fallback(self):
        messages = [{"role": "result", "text": json.dumps(_EVENT_INPUT)}]
        result = extractor.enrich({"title": "Jazz Night"}, "",
                                  model="sonnet", now="2026-05-29", timezone="UTC",
                                  runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(result.events[0]["title"], "Jazz Night")

    def test_enrich_zero_events_is_completed(self):
        messages = [{"role": "result", "tool_input": {"events": []}}]
        result = extractor.enrich({"title": "X"}, "p", model="sonnet",
                                  now="2026-05-29", timezone="UTC",
                                  runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(result.events, [])

    def test_enrich_budget_exceeded_from_runner(self):
        def _budget(**_kwargs):
            raise extractor.BudgetExceeded("token budget exceeded")
            yield  # pragma: no cover

        result = extractor.enrich({"title": "X"}, "p", model="sonnet",
                                  now="2026-05-29", timezone="UTC", runner=_budget)
        self.assertEqual(result.status, extractor.STATUS_BUDGET_EXCEEDED)
        self.assertEqual(result.events, [])


class TestLegacyExtract(unittest.TestCase):
    """The single-pass extract() is retained for back-compat."""

    def test_build_prompt_embeds_content(self):
        prompt = extractor.build_prompt(
            [{"url": "https://x.com", "content": "root body"},
             {"url": "https://x.com/1", "content": "linked body"}])
        self.assertIn("root body", prompt)
        self.assertIn("linked body", prompt)

    def test_extract_parses_text_json(self):
        messages = [{"role": "result", "text": json.dumps(_EVENT_INPUT)}]
        result = extractor.extract([{"content": "c"}], model="m",
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(result.events[0]["title"], "Jazz Night")

    def test_extract_malformed_is_error(self):
        messages = [{"role": "result", "text": "not json at all"}]
        result = extractor.extract([{"content": "c"}], model="m",
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_ERROR)


if __name__ == "__main__":
    unittest.main()
