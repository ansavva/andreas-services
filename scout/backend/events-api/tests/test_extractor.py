"""Unit tests for the Anthropic-API extractor (extractor.py). The API call is stubbed."""

import json
import unittest

from scout_core.adapters import extractor


def _runner_from(messages):
    """Build a runner that ignores inputs and replays a scripted message list."""
    def _runner(**_kwargs):
        yield from messages
    return _runner


_EVENTS_JSON = json.dumps({"events": [{
    "title": "Jazz Night",
    "description": "Live jazz",
    "start_date": "2026-06-01",
    "start_time": "20:00",
    "location": {"name": "The Blue Note", "address": "131 W 3rd", "timezone": "America/New_York"},
    "event_labels": ["jazz", "live"],
    "images": ["https://x.com/a.jpg"],
    "sub_events": [{"start_date": "2026-06-02", "start_time": "20:00"}],
}]})


class TestExtractor(unittest.TestCase):
    def test_build_prompt_embeds_content(self):
        prompt = extractor.build_prompt(
            [{"url": "https://x.com", "content": "root body"},
             {"url": "https://x.com/1", "content": "linked body"}])
        self.assertIn("root body", prompt)
        self.assertIn("linked body", prompt)
        self.assertIn("https://x.com/1", prompt)

    def test_completed_parses_events_and_tracks_usage(self):
        messages = [
            {"role": "result", "text": _EVENTS_JSON,
             "usage": {"input_tokens": 300, "output_tokens": 130}},
        ]
        result = extractor.extract([{"content": "c"}], model="m",
                                   budget_tokens=100000, budget_seconds=60,
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(len(result.events), 1)
        event = result.events[0]
        self.assertEqual(event["title"], "Jazz Night")
        self.assertEqual(len(event["sub_events"]), 1)
        self.assertEqual(event["location"]["name"], "The Blue Note")

        self.assertEqual(result.usage["input_tokens"], 300)
        self.assertEqual(result.usage["output_tokens"], 130)

    def test_zero_events_is_completed(self):
        messages = [{"role": "result", "text": '{"events": []}'}]
        result = extractor.extract([{"content": "c"}], model="m",
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(result.events, [])

    def test_parse_handles_code_fences(self):
        messages = [{"role": "result",
                     "text": "```json\n{\"events\": [{\"title\": \"X\", \"start_date\": \"2026-01-01\"}]}\n```"}]
        result = extractor.extract([{"content": "c"}], model="m",
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(result.events[0]["title"], "X")

    def test_malformed_output_is_error(self):
        messages = [{"role": "result", "text": "not json at all"}]
        result = extractor.extract([{"content": "c"}], model="m",
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_ERROR)
        self.assertIn("parse", result.error)

    def test_runner_exception_is_error(self):
        def _boom(**_kwargs):
            raise RuntimeError("sdk crashed")
            yield  # pragma: no cover

        result = extractor.extract([{"content": "c"}], model="m", runner=_boom)
        self.assertEqual(result.status, extractor.STATUS_ERROR)
        self.assertIn("sdk crashed", result.error)

    def test_explicit_budget_exceeded_from_runner(self):
        def _budget(**_kwargs):
            raise extractor.BudgetExceeded("runtime budget exceeded")
            yield  # pragma: no cover

        result = extractor.extract([{"content": "c"}], model="m", runner=_budget)
        self.assertEqual(result.status, extractor.STATUS_BUDGET_EXCEEDED)
        self.assertEqual(result.events, [])

    def test_token_budget_aborts_mid_stream(self):
        messages = [
            {"role": "assistant", "text": "a",
             "usage": {"input_tokens": 600, "output_tokens": 600}},
            {"role": "result", "text": _EVENTS_JSON},
        ]
        result = extractor.extract([{"content": "c"}], model="m",
                                   budget_tokens=1000,
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_BUDGET_EXCEEDED)
        self.assertEqual(result.events, [])  # partial output discarded


if __name__ == "__main__":
    unittest.main()
