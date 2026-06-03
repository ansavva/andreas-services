"""Unit tests for the iCal feed parser (ical.py)."""

import unittest

from scout_core.adapters import ical

_FEED = (
    "BEGIN:VCALENDAR\r\n"
    "X-WR-TIMEZONE:America/New_York\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:Boogie Wonder Band\r\n"
    "DTSTART:20260503T000000Z\r\n"          # 00:00 UTC -> 2026-05-02 20:00 EDT
    "DTEND:20260503T030000Z\r\n"            # 03:00 UTC -> 23:00 EDT
    "DESCRIPTION:Disco night\\, with the\r\n"
    "  band\r\n"                            # folded continuation line
    "LOCATION:Hudson Hall\\, 327 Warren St\r\n"
    "URL:https://example.com/e/1\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:All Day Fair\r\n"
    "DTSTART;VALUE=DATE:20260704\r\n"       # all-day, no time
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"                      # no SUMMARY -> dropped
    "DTSTART:20260801T120000Z\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


class TestIcalParser(unittest.TestCase):
    def setUp(self):
        self.events = ical.parse_events(_FEED)

    def test_drops_titleless_events(self):
        self.assertEqual(len(self.events), 2)

    def test_utc_time_localized_to_feed_timezone(self):
        ev = self.events[0]
        self.assertEqual(ev["title"], "Boogie Wonder Band")
        self.assertEqual(ev["start_date"], "2026-05-02")
        self.assertEqual(ev["start_time"], "20:00")
        self.assertEqual(ev["end_time"], "23:00")

    def test_unfolding_and_escaping(self):
        ev = self.events[0]
        self.assertIn("Disco night, with the band", ev["description"])
        self.assertIn("https://example.com/e/1", ev["description"])
        self.assertEqual(ev["location"], {"name": "Hudson Hall",
                                          "address": "327 Warren St"})

    def test_all_day_event_has_no_time(self):
        ev = self.events[1]
        self.assertEqual(ev["title"], "All Day Fair")
        self.assertEqual(ev["start_date"], "2026-07-04")
        self.assertNotIn("start_time", ev)

    def test_default_tz_used_without_xwr(self):
        feed = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:X\r\n"
                "DTSTART:20260101T120000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        # UTC default: 12:00Z stays 12:00 on the same day.
        ev = ical.parse_events(feed, default_tz="UTC")[0]
        self.assertEqual(ev["start_date"], "2026-01-01")
        self.assertEqual(ev["start_time"], "12:00")

    def test_empty_feed(self):
        self.assertEqual(ical.parse_events(""), [])


if __name__ == "__main__":
    unittest.main()
