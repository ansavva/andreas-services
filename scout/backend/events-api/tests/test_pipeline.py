"""Integration tests for the run pipeline (pipeline.py) over moto DynamoDB + S3."""

import os
import unittest

import boto3
from moto import mock_dynamodb, mock_s3

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")
os.environ["SCOUT_ARTIFACTS_BUCKET"] = "scout-artifacts-test"

from scout_core.adapters import artifacts  # noqa: E402
from scout_core.adapters import extractor  # noqa: E402
from scout_core.domain import notifications  # noqa: E402
from scout_core.domain import pipeline  # noqa: E402
from scout_core.domain import runs  # noqa: E402
from scout_core.domain import sources  # noqa: E402
from scout_core.adapters import store  # noqa: E402

_GSI_ATTRS = [
    "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "GSI3PK", "GSI3SK",
    "GSI4PK", "GSI4SK", "GSI5PK", "GSI5SK",
]

ROOT_HTML = """
  <html><body>
    <main>
      <h1>Live Show</h1>
      <a href="https://example.com/show">show details</a>
      <a href="https://offsite.com/x">offsite</a>
    </main>
  </body></html>
"""


def _triage_one(pages):
    """Stub triage: one candidate pointing at the same-domain detail page."""
    return extractor.TriageResult(
        extractor.STATUS_COMPLETED,
        candidates=[{
            "title": "Live Show",
            "hints": "Friday",
            "detail_url": "https://example.com/show",
            "fallback_event": {"title": "Live Show", "start_date": "2099-01-01"},
        }],
        transcript=[{"role": "result", "tool_input": {"candidates": []}}],
    )


def _enrich_one(candidate, page_text, **_kwargs):
    return extractor.ExtractionResult(
        extractor.STATUS_COMPLETED,
        events=[{"title": "Extracted", "saw_detail": bool(page_text)}],
        transcript=[{"role": "result", "tool_input": {"events": []}}],
    )


def _create_core(dynamodb):
    attribute_definitions = [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
    ] + [{"AttributeName": n, "AttributeType": "S"} for n in _GSI_ATTRS]
    gsis = [{
        "IndexName": f"GSI{i}",
        "KeySchema": [
            {"AttributeName": f"GSI{i}PK", "KeyType": "HASH"},
            {"AttributeName": f"GSI{i}SK", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    } for i in range(1, 6)]
    dynamodb.create_table(
        TableName="scout-core",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=attribute_definitions,
        GlobalSecondaryIndexes=gsis,
        BillingMode="PAY_PER_REQUEST",
    )


def _create_settings(dynamodb):
    dynamodb.create_table(
        TableName="scout-settings",
        KeySchema=[{"AttributeName": "setting_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "setting_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _fetch_fn(url):
    if url == "https://example.com":
        return 200, ROOT_HTML
    if url == "https://example.com/show":
        return 200, "<main><p>Show details</p></main>"
    raise AssertionError(f"unexpected fetch: {url}")


@mock_dynamodb
@mock_s3
class TestPipeline(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        store.reset_settings_cache()
        artifacts._s3 = None
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket="scout-artifacts-test")
        self.src = sources.create_source(
            sources.WEBPAGE, "https://example.com",
            config={"mode": "scheduled"}, follow_links=True,
        )

    def test_preview_persists_nothing(self):
        result = pipeline.preview(self.src, fetch_fn=_fetch_fn,
                                  triage=_triage_one, enrich=_enrich_one)
        self.assertEqual(len(result["events"]), 1)
        # Root page + 1 fetched detail page.
        self.assertEqual(result["pages_fetched"], 2)
        self.assertEqual(len(result["link_outcomes"]), 1)
        self.assertTrue(result["events"][0]["saw_detail"])
        # No run record created.
        self.assertEqual(runs.list_runs(self.src["source_id"]), [])

    def test_execute_run_stores_artifacts_transcript_and_finishes(self):
        run = pipeline.execute_run(self.src, runs.TRIGGER_SCHEDULED,
                                   fetch_fn=_fetch_fn, triage=_triage_one,
                                   enrich=_enrich_one)
        self.assertEqual(run["status"], "success")
        self.assertEqual(int(run["events_count"]), 1)
        self.assertIn("s3_root_html_ref", run)
        self.assertIn("agent_transcript_ref", run)
        self.assertEqual(len(run["link_outcomes"]), 1)
        self.assertTrue(run["link_outcomes"][0]["ok"])
        self.assertIn("s3_ref", run["link_outcomes"][0])

        # Root, fetched detail page and transcript are in S3 and readable.
        sid, rid = self.src["source_id"], run["run_id"]
        self.assertIn("Show details", artifacts.get_text(run["link_outcomes"][0]["s3_ref"]))
        self.assertIn("Live Show", artifacts.get_text(artifacts.root_html_key(sid, rid)))
        self.assertIn("events", artifacts.get_text(run["agent_transcript_ref"]))

    def test_email_listing_page_is_followed_and_re_triaged(self):
        # Email body has no events itself, only a link to a "what's on" page;
        # that page (re-triaged) yields the actual event + its detail link.
        email_src = sources.create_source(sources.EMAIL, "venue.org",
                                          follow_links=True)

        def gmail_fetch(domain, since):
            return [{"message_id": "m1", "subject": "This week", "image_url": "",
                     "date": "Tue, 27 May 2026 09:00:00 +0100",
                     "body_markdown": "See everything on at our venue!",
                     "links": ["https://venue.org/whats-on"]}]

        def fetch_fn(url):
            if url == "https://venue.org/whats-on":
                return 200, "<main>Jazz Night — details</main>"
            if url == "https://venue.org/jazz":
                return 200, "<main><p>Jazz Night full detail</p></main>"
            raise AssertionError(f"unexpected fetch: {url}")

        def triage(pages):
            if "whats-on" in (pages[0].get("url") or ""):
                # The listing page surfaces the real event + its detail link.
                return extractor.TriageResult(
                    extractor.STATUS_COMPLETED,
                    candidates=[{"title": "Jazz Night",
                                 "detail_url": "https://venue.org/jazz",
                                 "fallback_event": {"title": "Jazz Night",
                                                    "start_date": "2099-05-30"}}])
            # The email body itself only points at the listing page.
            return extractor.TriageResult(
                extractor.STATUS_COMPLETED, candidates=[],
                listing_urls=["https://venue.org/whats-on"])

        run = pipeline.execute_run(email_src, runs.TRIGGER_SCHEDULED,
                                   fetch_fn=fetch_fn, triage=triage,
                                   enrich=_enrich_one, gmail_fetch=gmail_fetch)
        self.assertEqual(run["status"], "success")
        self.assertEqual(int(run["events_count"]), 1)
        # Both the listing page and the per-event detail page were fetched.
        urls = {o["url"] for o in run["link_outcomes"]}
        self.assertEqual(urls, {"https://venue.org/whats-on", "https://venue.org/jazz"})

    def test_listing_recursion_respects_global_fetch_cap(self):
        store.put_settings({"link_follow_cap": 1})
        email_src = sources.create_source(sources.EMAIL, "venue.org",
                                          follow_links=True)

        def gmail_fetch(domain, since):
            return [{"message_id": "m1", "subject": "x", "image_url": "", "date": "",
                     "body_markdown": "see listing",
                     "links": ["https://venue.org/whats-on"]}]

        def fetch_fn(url):
            return 200, "<main>stuff</main>"

        def triage(pages):
            # Always surfaces a candidate-with-link and another listing link;
            # the global cap of 1 must stop the fan-out after a single fetch.
            return extractor.TriageResult(
                extractor.STATUS_COMPLETED,
                candidates=[{"title": "E", "detail_url": "https://venue.org/e",
                             "fallback_event": {"title": "E", "start_date": "2099-01-01"}}],
                listing_urls=["https://venue.org/whats-on"])

        run = pipeline.execute_run(email_src, runs.TRIGGER_SCHEDULED,
                                   fetch_fn=fetch_fn, triage=triage,
                                   enrich=_enrich_one, gmail_fetch=gmail_fetch)
        self.assertEqual(run["status"], "success")
        self.assertEqual(len(run["link_outcomes"]), 1)  # capped

    def test_budget_exceeded_marks_error_and_discards_output(self):
        def over_budget(_pages):
            return extractor.TriageResult(
                extractor.STATUS_BUDGET_EXCEEDED,
                transcript=[{"role": "assistant", "text": "..."}],
            )

        run = pipeline.execute_run(self.src, runs.TRIGGER_MANUAL,
                                   fetch_fn=_fetch_fn, triage=over_budget,
                                   enrich=_enrich_one)
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error_reason"], runs.REASON_BUDGET_EXCEEDED)
        self.assertEqual(int(run["events_count"]), 0)  # partial output discarded
        # A distinct budget-exceeded notification is raised.
        notes = notifications.list_notifications()
        self.assertEqual([n["type"] for n in notes], ["budget_exceeded"])

    def test_linkless_candidate_uses_fallback_without_enrich(self):
        def triage_no_link(pages):
            return extractor.TriageResult(
                extractor.STATUS_COMPLETED,
                candidates=[{
                    "title": "Body Only Event",
                    "detail_url": None,
                    "fallback_event": {"title": "Body Only Event",
                                       "start_date": "2099-03-03"},
                }])

        def enrich_should_not_run(candidate, page_text, **_kwargs):
            raise AssertionError("enrich must not run for a linkless candidate")

        result = pipeline.preview(self.src, fetch_fn=_fetch_fn,
                                  triage=triage_no_link, enrich=enrich_should_not_run)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["title"], "Body Only Event")
        self.assertEqual(result["link_outcomes"], [])

    def test_execute_run_records_error_on_root_failure(self):
        def boom(_url):
            raise ConnectionError("dns fail")

        run = pipeline.execute_run(self.src, runs.TRIGGER_MANUAL,
                                   fetch_fn=boom, triage=_triage_one,
                                   enrich=_enrich_one)
        self.assertEqual(run["status"], "error")
        self.assertIn("dns fail", run["error_reason"])

    def test_manual_run_does_not_shift_schedule(self):
        pk = store.source_pk(self.src["source_id"])
        before = store.get(pk, "META")["next_run_at"]
        pipeline.execute_run(self.src, runs.TRIGGER_MANUAL,
                             fetch_fn=_fetch_fn, triage=_triage_one,
                             enrich=_enrich_one)
        self.assertEqual(store.get(pk, "META")["next_run_at"], before)

    def test_email_run_follows_cross_domain_links_and_advances_cursor(self):
        email_src = sources.create_source(sources.EMAIL, "venue.org",
                                          follow_links=True)
        captured = {}

        def gmail_fetch(domain, since):
            captured["domain"] = domain
            captured["since"] = since
            return [
                {"message_id": "m1", "subject": "Show", "image_url": "",
                 "date": "Tue, 27 May 2026 09:00:00 +0100",
                 "body_markdown": "Jazz Night, Friday — tickets at offsite",
                 "links": ["https://offsite.com/jazz"]},
            ]

        def triage_email(pages):
            return extractor.TriageResult(
                extractor.STATUS_COMPLETED,
                candidates=[{
                    "title": "Jazz Night",
                    "detail_url": "https://offsite.com/jazz",
                    "fallback_event": {"title": "Jazz Night", "start_date": "2099-05-30"},
                }])

        def fetch_offsite(url):
            assert url == "https://offsite.com/jazz", url
            return 200, "<main><p>Jazz Night detail</p></main>"

        run = pipeline.execute_run(email_src, runs.TRIGGER_SCHEDULED,
                                   fetch_fn=fetch_offsite, triage=triage_email,
                                   enrich=_enrich_one, gmail_fetch=gmail_fetch)
        self.assertEqual(run["status"], "success")
        self.assertEqual(captured["domain"], "venue.org")
        # The cross-domain detail link was followed + stored.
        self.assertEqual(len(run["link_outcomes"]), 1)
        self.assertEqual(run["link_outcomes"][0]["url"], "https://offsite.com/jazz")
        self.assertIn("Jazz Night detail",
                      artifacts.get_text(run["link_outcomes"][0]["s3_ref"]))
        self.assertTrue(run["events_count"])
        # Cursor advanced for the next run.
        updated = store.get(store.source_pk(email_src["source_id"]), "META")
        self.assertIn("last_email_fetch_epoch", updated)

    def test_email_run_resumes_from_stored_cursor(self):
        email_src = sources.create_source(sources.EMAIL, "venue.org")
        store.set_attrs(store.source_pk(email_src["source_id"]), "META",
                        {"last_email_fetch_epoch": 1700000000})
        email_src = store.get(store.source_pk(email_src["source_id"]), "META")
        seen = {}

        def gmail_fetch(domain, since):
            seen["since"] = since
            return []

        # since_epoch is supplied by the caller (processor); here we pass it
        # through explicitly to assert the pipeline forwards it.
        pipeline.execute_run(email_src, runs.TRIGGER_SCHEDULED,
                             triage=_triage_one, enrich=_enrich_one,
                             gmail_fetch=gmail_fetch,
                             since_epoch=email_src["last_email_fetch_epoch"])
        self.assertEqual(int(seen["since"]), 1700000000)


if __name__ == "__main__":
    unittest.main()
