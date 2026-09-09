import dataclasses
import unittest

from pentimento import lineage


@dataclasses.dataclass
class FakePlan:
    id: str
    body: str
    started: str
    project: str = "example"


@dataclasses.dataclass
class FakeSession:
    prompt: str


class DeriveParentTests(unittest.TestCase):
    def test_session_prompt_finds_parent(self):
        parent = FakePlan(id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z")
        child = FakePlan(id="slow-otter", body="# Child\n", started="2026-09-02T00:00:00Z")
        sessions = {"slow-otter": FakeSession(prompt="Resume ~/.claude/plans/eager-bird.md")}
        parent_id = lineage.derive_parent(child, [parent, child], sessions)
        self.assertEqual(parent_id, parent.id)

    def test_preamble_reference_finds_parent(self):
        parent = FakePlan(id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z")
        child = FakePlan(
            id="slow-otter",
            body="# Child\n\nSupersedes ~/.claude/plans/eager-bird.md\n\n## Progress\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertEqual(parent_id, parent.id)

    def test_progress_section_reference_is_not_a_parent_signal(self):
        parent = FakePlan(id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z")
        child = FakePlan(
            id="slow-otter",
            body="# Child\n\n## Progress\n\nExecuted ~/.claude/plans/eager-bird.md\n",
            started="2026-09-02T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertIsNone(parent_id)

    def test_newest_surviving_candidate_wins(self):
        older = FakePlan(id="older-plan", body="# Older\n", started="2026-09-01T00:00:00Z")
        newer = FakePlan(id="newer-plan", body="# Newer\n", started="2026-09-05T00:00:00Z")
        child = FakePlan(
            id="child-plan",
            body="See ~/.claude/plans/older-plan.md and ~/.claude/plans/newer-plan.md\n",
            started="2026-09-10T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [older, newer, child], {})
        self.assertEqual(parent_id, newer.id)

    def test_no_signal_leaves_root(self):
        solo = FakePlan(id="standalone-plan", body="# Standalone\n", started="2026-09-01T00:00:00Z")
        parent_id = lineage.derive_parent(solo, [solo], {})
        self.assertIsNone(parent_id)

    def test_candidate_in_a_different_project_is_ignored(self):
        parent = FakePlan(
            id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z", project="other"
        )
        child = FakePlan(
            id="slow-otter",
            body="See ~/.claude/plans/eager-bird.md\n",
            started="2026-09-02T00:00:00Z",
            project="example",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertIsNone(parent_id)

    def test_candidate_started_after_plan_is_ignored(self):
        parent = FakePlan(id="eager-bird", body="# Parent\n", started="2026-09-10T00:00:00Z")
        child = FakePlan(
            id="slow-otter",
            body="See ~/.claude/plans/eager-bird.md\n",
            started="2026-09-02T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertIsNone(parent_id)

    def test_self_reference_is_ignored(self):
        solo = FakePlan(
            id="standalone-plan",
            body="See ~/.claude/plans/standalone-plan.md\n",
            started="2026-09-01T00:00:00Z",
        )
        parent_id = lineage.derive_parent(solo, [solo], {})
        self.assertIsNone(parent_id)


if __name__ == "__main__":
    unittest.main()
