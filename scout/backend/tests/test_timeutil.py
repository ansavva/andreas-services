"""Unit tests for timezone-aware past computation (timeutil.py)."""

import unittest
from datetime import datetime, timezone

from scout_core.utils import timeutil


class TestTimeutil(unittest.TestCase):
    def test_effective_end_uses_end_time_in_location_tz(self):
        # 20:00 in New York on 2026-06-01 is 2026-06-02T00:00 UTC (EDT, -4).
        end = timeutil.effective_end_utc("2026-06-01", "18:00", "20:00",
                                         tz="America/New_York")
        self.assertEqual(end, "2026-06-02T00:00:00+00:00")

    def test_effective_end_defaults_to_end_of_day(self):
        end = timeutil.effective_end_utc("2026-06-01", "18:00", None, tz="UTC")
        self.assertEqual(end, "2026-06-01T23:59:59+00:00")

    def test_effective_end_undated_is_none(self):
        self.assertIsNone(timeutil.effective_end_utc("", None, None))

    def test_invalid_timezone_falls_back_to_utc(self):
        end = timeutil.effective_end_utc("2026-06-01", None, "12:00", tz="Not/AZone")
        self.assertEqual(end, "2026-06-01T12:00:00+00:00")

    def test_is_past_respects_grace(self):
        end = "2026-06-01T00:00:00+00:00"
        just_after = datetime(2026, 6, 1, 1, 0, tzinfo=timezone.utc)
        # Within a 24h grace it is not yet past.
        self.assertFalse(timeutil.is_past(end, grace_hours=24, now=just_after))
        well_after = datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(timeutil.is_past(end, grace_hours=24, now=well_after))

    def test_is_past_none(self):
        self.assertFalse(timeutil.is_past(None, grace_hours=0))


if __name__ == "__main__":
    unittest.main()
