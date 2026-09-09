from __future__ import annotations

import datetime
import unittest

from pentimento import times


class ParseIsoTests(unittest.TestCase):
    def test_z_suffix_is_normalized(self):
        dt = times.parse_iso("2026-09-01T12:00:00.000Z")
        self.assertEqual(dt, datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc))

    def test_offset_suffix_parses_directly(self):
        dt = times.parse_iso("2026-09-01T12:00:00+00:00")
        self.assertEqual(dt, datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc))

    def test_empty_string_is_none(self):
        self.assertIsNone(times.parse_iso(""))

    def test_malformed_text_is_none(self):
        self.assertIsNone(times.parse_iso("not a timestamp"))


class LocalDateTests(unittest.TestCase):
    def test_none_input_is_none(self):
        self.assertIsNone(times.local_date(None))

    def test_formats_as_year_month_day(self):
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertRegex(times.local_date(dt), r"^\d{4}-\d{2}-\d{2}$")


class LocalStampTests(unittest.TestCase):
    def test_none_input_is_none(self):
        self.assertIsNone(times.local_stamp(None))

    def test_formats_with_hours_and_minutes(self):
        dt = datetime.datetime(2026, 9, 1, 12, 30, 0, tzinfo=datetime.timezone.utc)
        self.assertRegex(times.local_stamp(dt), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


class RelativeTests(unittest.TestCase):
    def test_under_a_minute_is_just_now(self):
        now = datetime.datetime(2026, 9, 1, 12, 0, 30, tzinfo=datetime.timezone.utc)
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(times.relative(dt, now), "just now")

    def test_minutes(self):
        now = datetime.datetime(2026, 9, 1, 12, 14, 0, tzinfo=datetime.timezone.utc)
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(times.relative(dt, now), "14m")

    def test_hours(self):
        now = datetime.datetime(2026, 9, 1, 14, 0, 0, tzinfo=datetime.timezone.utc)
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(times.relative(dt, now), "2h")

    def test_days(self):
        now = datetime.datetime(2026, 9, 4, 12, 0, 0, tzinfo=datetime.timezone.utc)
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(times.relative(dt, now), "3d")

    def test_weeks(self):
        now = datetime.datetime(2026, 10, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(times.relative(dt, now), "5w")

    def test_years(self):
        now = datetime.datetime(2027, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(times.relative(dt, now), "1y")


if __name__ == "__main__":
    unittest.main()
