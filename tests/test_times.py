from __future__ import annotations

import datetime
import unittest
from unittest import mock

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

    def test_naive_timestamp_gets_utc_timezone(self):
        dt = times.parse_iso("2026-09-01T12:00:00")
        self.assertEqual(dt, datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc))

    def test_naive_timestamp_works_with_relative(self):
        dt = times.parse_iso("2026-09-01T12:00:00")
        now = datetime.datetime(2026, 9, 1, 12, 0, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(times.relative(dt, now), "just now")


class ParseDateTests(unittest.TestCase):
    def test_parses_iso_date(self):
        self.assertEqual(times.parse_date("2026-09-01"), datetime.date(2026, 9, 1))

    def test_empty_string_is_none(self):
        self.assertIsNone(times.parse_date(""))

    def test_malformed_text_is_none(self):
        self.assertIsNone(times.parse_date("not a date"))


class LocalDayTests(unittest.TestCase):
    def test_none_input_is_none(self):
        self.assertIsNone(times.local_day(None))

    def test_returns_a_date(self):
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertIsInstance(times.local_day(dt), datetime.date)


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

    def test_pentimento_now_overrides_wall_clock(self):
        dt = datetime.datetime(2026, 9, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with mock.patch.dict("os.environ", {"PENTIMENTO_NOW": "2026-09-01T12:00:30Z"}):
            self.assertEqual(times.relative(dt), "just now")


class ParseWhenTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", {"PENTIMENTO_NOW": "2026-09-23T12:00:00Z"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_iso_date_passes_through(self):
        self.assertEqual(times.parse_when("2026-09-01"), datetime.date(2026, 9, 1))

    def test_each_relative_unit_counts_back_from_now(self):
        for text, expected in (
            ("14m", datetime.date(2026, 9, 23)),
            ("5h", datetime.date(2026, 9, 23)),
            ("3d", datetime.date(2026, 9, 20)),
            ("2w", datetime.date(2026, 9, 9)),
            ("1y", datetime.date(2025, 9, 23)),
        ):
            self.assertEqual(times.parse_when(text), expected, msg=text)

    def test_other_text_is_none(self):
        for text in ("", "yesterday", "3", "d", "3days", "-3d", "3D", "2026-13-01"):
            self.assertIsNone(times.parse_when(text), msg=text)

    def test_absurd_age_is_none_not_a_crash(self):
        self.assertIsNone(times.parse_when("999999999y"))


class UtcStampTests(unittest.TestCase):
    def test_converts_to_utc_z_with_whole_seconds(self):
        offset = datetime.timezone(datetime.timedelta(hours=-7))
        dt = datetime.datetime(2026, 9, 1, 5, 0, 0, 123000, tzinfo=offset)
        self.assertEqual(times.utc_stamp(dt), "2026-09-01T12:00:00Z")

    def test_none_is_none(self):
        self.assertIsNone(times.utc_stamp(None))


if __name__ == "__main__":
    unittest.main()
