import dataclasses
import unittest

from pentimento import lineage


@dataclasses.dataclass
class FakePlan:
    id: str
    body: str
    mtime: float


class SlugBodyTests(unittest.TestCase):
    def test_strips_trailing_adjective_noun(self):
        self.assertEqual(
            lineage.slug_body("resume-planning-session-users-kjiwa-clau-eager-bird"),
            "resume-planning-session-users-kjiwa-clau",
        )

    def test_short_id_returned_unchanged(self):
        self.assertEqual(lineage.slug_body("a-b"), "a-b")


class DeriveParentTests(unittest.TestCase):
    def test_slug_containment_finds_parent(self):
        parent = FakePlan(
            id="resume-planning-session-users-kjiwa-clau-eager-bird",
            body="# Parent\n",
            mtime=1,
        )
        child = FakePlan(
            id="re-plan-claude-plans-resume-planning-ses-sparkling-lecun",
            body="# Child\n",
            mtime=2,
        )
        parent_id, conflict = lineage.derive_parent(child, [parent, child])
        self.assertEqual(parent_id, parent.id)
        self.assertFalse(conflict)

    def test_body_reference_finds_parent(self):
        parent = FakePlan(id="eager-bird", body="# Parent\n", mtime=1)
        child = FakePlan(
            id="sparkling-lecun",
            body="# Child\n\nSupersedes ~/.claude/plans/eager-bird.md\n",
            mtime=2,
        )
        parent_id, conflict = lineage.derive_parent(child, [parent, child])
        self.assertEqual(parent_id, parent.id)
        self.assertFalse(conflict)

    def test_body_reference_nearest_preceding_wins(self):
        older = FakePlan(id="older-plan-aaaaaaaaaaaa", body="# Older\n", mtime=1)
        newer = FakePlan(id="newer-plan-bbbbbbbbbbbb", body="# Newer\n", mtime=5)
        child = FakePlan(
            id="child-plan",
            body="See ~/.claude/plans/older-plan-aaaaaaaaaaaa.md "
            "and ~/.claude/plans/newer-plan-bbbbbbbbbbbb.md\n",
            mtime=10,
        )
        parent_id, conflict = lineage.derive_parent(child, [older, newer, child])
        self.assertEqual(parent_id, newer.id)
        self.assertFalse(conflict)

    def test_no_signal_leaves_root(self):
        solo = FakePlan(id="standalone-plan", body="# Standalone\n", mtime=1)
        parent_id, conflict = lineage.derive_parent(solo, [solo])
        self.assertIsNone(parent_id)
        self.assertFalse(conflict)

    def test_conflicting_signals_left_unset(self):
        a = FakePlan(id="resume-planning-session-alpha-eager-bird", body="# A\n", mtime=1)
        b = FakePlan(id="resume-planning-session-beta-slow-otter", body="# B\n", mtime=2)
        child = FakePlan(
            id="resume-planning-session-alp-continued-loon",
            body="Supersedes ~/.claude/plans/resume-planning-session-beta-slow-otter.md\n",
            mtime=3,
        )
        parent_id, conflict = lineage.derive_parent(child, [a, b, child])
        self.assertIsNone(parent_id)
        self.assertTrue(conflict)


if __name__ == "__main__":
    unittest.main()
