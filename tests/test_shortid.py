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

    def test_uuid_suffix_shortens_to_pre_uuid_codename(self):
        plan_id = "some-prompt-logical-island-of-11111111-1111-4111-8111-111111111111"
        result = shortid.shorten([plan_id, "some-other-plan-id"])
        self.assertEqual(result[plan_id], "logical-island")

    def test_uuid_suffix_colliding_with_non_uuid_escalates_leftward(self):
        uuid_id = "foo-bar-ancient-knuth-of-11111111-1111-4111-8111-111111111111"
        old_id = "baz-qux-ancient-knuth"
        result = shortid.shorten([uuid_id, old_id])
        self.assertEqual(result[uuid_id], "bar-ancient-knuth")
        self.assertEqual(result[old_id], "qux-ancient-knuth")

    def test_identical_pre_uuid_stems_fall_through_to_uuid_tails(self):
        first = "same-stem-eager-fox-of-11111111-1111-4111-8111-111111111111"
        second = "same-stem-eager-fox-of-22222222-2222-4222-8222-222222222222"
        result = shortid.shorten([first, second])
        self.assertEqual(result[first], "8111-111111111111")
        self.assertEqual(result[second], "8222-222222222222")

    def test_non_uuid_id_matching_entire_pre_uuid_stem_keeps_short_id(self):
        short = "foo-bar"
        uuid_id = "foo-bar-of-11111111-1111-4111-8111-111111111111"
        result = shortid.shorten([short, uuid_id])
        self.assertEqual(result[short], "foo-bar")
        self.assertEqual(result[uuid_id], "8111-111111111111")

    def test_single_segment_pre_uuid_stem_falls_through_to_uuid_tail(self):
        uuid_id = "alpha-of-11111111-1111-4111-8111-111111111111"
        result = shortid.shorten([uuid_id, "other-plan"])
        self.assertEqual(result[uuid_id], "8111-111111111111")

    def test_non_uuid_of_suffix_is_not_stripped(self):
        result = shortid.shorten(["project-plan-of-work", "other-plan"])
        self.assertEqual(result["project-plan-of-work"], "of-work")

    def test_every_shortened_id_resolves_uniquely_via_matches(self):
        ids = [
            "is-it-possible-to-abundant-rabbit",
            "some-prompt-logical-island-of-11111111-1111-4111-8111-111111111111",
            "foo-bar-ancient-knuth-of-11111111-1111-4111-8111-111111111111",
            "baz-qux-ancient-knuth",
            "same-stem-eager-fox-of-11111111-1111-4111-8111-111111111111",
            "same-stem-eager-fox-of-22222222-2222-4222-8222-222222222222",
            "foo-bar",
            "foo-bar-of-11111111-1111-4111-8111-111111111111",
            "alpha-of-11111111-1111-4111-8111-111111111111",
            "project-plan-of-work",
        ]
        shortened = shortid.shorten(ids)
        for plan_id, short in shortened.items():
            if short == plan_id:
                continue
            with self.subTest(plan_id=plan_id, short=short):
                self.assertEqual(shortid.matches(ids, short), [plan_id])


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

    def test_matches_uuid_suffixed_plan_by_codename_stem_and_uuid(self):
        plan_id = "some-prompt-logical-island-of-11111111-1111-4111-8111-111111111111"
        ids = [plan_id, "other-plan"]
        for wanted in (
            "logical-island",
            "prompt-logical-island",
            "some-prompt-logical-island",
            "8111-111111111111",
            "11111111-1111-4111-8111-111111111111",
            plan_id,
        ):
            with self.subTest(wanted=wanted):
                self.assertEqual(shortid.matches(ids, wanted), [plan_id])

    def test_uuid_matching_stays_segment_aligned_and_anchored(self):
        plan_id = "some-prompt-jackisland-of-11111111-1111-4111-8111-111111111111"
        ids = [plan_id]
        self.assertEqual(shortid.matches(ids, "island"), [])
        self.assertEqual(shortid.matches(ids, "some-prompt"), [])


if __name__ == "__main__":
    unittest.main()
