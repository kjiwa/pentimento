import unittest

from pentimento import counts


class PluralTests(unittest.TestCase):
    def test_singular(self):
        self.assertEqual(counts.plural(1, "plan"), "1 plan")

    def test_plural(self):
        self.assertEqual(counts.plural(208, "plan"), "208 plans")

    def test_zero_is_plural(self):
        self.assertEqual(counts.plural(0, "finding"), "0 findings")


class SummaryTests(unittest.TestCase):
    def test_unfiltered_shows_total_only(self):
        self.assertEqual(counts.summary(208, 208), "208 plans")

    def test_filtered_shows_shown_of_total(self):
        self.assertEqual(counts.summary(12, 208), "12 of 208 plans")


if __name__ == "__main__":
    unittest.main()
