"""Unit tests for the Agent SDK extractor (extractor.py). The SDK call is stubbed."""

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
    def test_build_prompt_lists_files(self):
        prompt, files = extractor.build_prompt(
            [{"url": "https://x.com", "content": "root"},
             {"url": "https://x.com/1", "content": "linked"}])
        self.assertEqual(set(files), {"page_0.txt", "page_1.txt"})
        self.assertEqual(files["page_0.txt"], "root")
        self.assertIn("page_1.txt", prompt)

    def test_completed_parses_events_and_summarizes_tools(self):
        messages = [
            {"role": "assistant", "text": "let me look",
             "tools": [{"name": "WebFetch", "input": {"url": "https://x.com"}}],
             "usage": {"input_tokens": 100, "output_tokens": 50}},
            {"role": "assistant", "text": "searching",
             "tools": [{"name": "WebSearch", "input": {"q": "blue note"}},
                       {"name": "WebFetch", "input": {"url": "https://x.com/2"}}]},
            {"role": "result", "text": _EVENTS_JSON,
             "usage": {"input_tokens": 200, "output_tokens": 80}},
        ]
        result = extractor.extract(messages and [{"content": "c"}], model="m",
                                   budget_tokens=100000, budget_seconds=60,
                                   runner=_runner_from(messages))
        self.assertEqual(result.status, extractor.STATUS_COMPLETED)
        self.assertEqual(len(result.events), 1)
        event = result.events[0]
        self.assertEqual(event["title"], "Jazz Night")
        self.assertEqual(len(event["sub_events"]), 1)
        self.assertEqual(event["location"]["name"], "The Blue Note")

        tools = {t["tool"]: t["count"] for t in result.tool_use_summary}
        self.assertEqual(tools, {"WebFetch": 2, "WebSearch": 1})
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
