from __future__ import annotations

import unittest

from pentimento import shortid


class ShortenTests(unittest.TestCase):
    def test_two_segment_suffix_is_chosen_when_unique(self):
        ids = ["is-it-possible-to-abundant-rabbit", "some-other-plan-id"]
        result = shortid.shorten(ids)
        self.assertEqual(result["is-it-possible-to-abundant-rabbit"], "abundant-rabbit")

    def test_colliding_two_segment_suffix_escalates_to_three(self):
        ids = ["foo-abundant-rabbit", "bar-abundant-rabbit"]
        result = shortid.shorten(ids)
        self.assertEqual(result["foo-abundant-rabbit"], "foo-abundant-rabbit")
        self.assertEqual(result["bar-abundant-rabbit"], "bar-abundant-rabbit")

    def test_duplicate_ids_fall_back_to_the_full_id(self):
        ids = ["a-plan-id", "a-plan-id"]
        result = shortid.shorten(ids)
        self.assertEqual(result["a-plan-id"], "a-plan-id")


class MatchesTests(unittest.TestCase):
    def test_matches_is_segment_aligned(self):
        ids = ["some-jackrabbit"]
        self.assertEqual(shortid.matches(ids, "rabbit"), [])

    def test_matches_a_trailing_segment_run(self):
        ids = ["some-jackrabbit", "some-other-rabbit"]
        self.assertEqual(shortid.matches(ids, "rabbit"), ["some-other-rabbit"])

    def test_matches_full_id(self):
        ids = ["some-jackrabbit", "some-other-rabbit"]
        self.assertEqual(shortid.matches(ids, "some-jackrabbit"), ["some-jackrabbit"])


if __name__ == "__main__":
    unittest.main()
