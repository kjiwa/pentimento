import dataclasses
import unittest
from pathlib import Path

from pentimento import frontmatter, lineage, times

CURSOR_FIXTURES = Path(__file__).parent / "fixtures" / "cursor"


@dataclasses.dataclass
class FakePlan:
    id: str
    body: str
    started: str
    project: str = "example"
    source: str = "claude"

    @property
    def created_at(self):
        return times.parse_iso(self.started)


@dataclasses.dataclass
class FakeSession:
    prompt: str


class DeriveParentTests(unittest.TestCase):
    def test_cursor_follow_up_fixture_resolves_its_snake_case_parent(self):
        parent_id = "skip_list_range_query_d3d1b015"
        child_id = "range_vs_submap_benchmark_4a0ba26d"
        _, child_body, _ = frontmatter.parse((CURSOR_FIXTURES / f"{child_id}.plan.md").read_text())
        parent = FakePlan(
            id=parent_id, body="# Parent\n", started="2026-09-01T00:00:00Z", source="cursor"
        )
        child = FakePlan(
            id=child_id, body=child_body, started="2026-09-02T00:00:00Z", source="cursor"
        )
        self.assertEqual(lineage.derive_parent(child, [parent, child], {}), parent_id)

    def test_snake_case_identifier_that_is_not_an_id_resolves_to_nothing(self):
        parent = FakePlan(
            id="skip_list_range_query_d3d1b015",
            body="# Parent\n",
            started="2026-09-01T00:00:00Z",
            source="cursor",
        )
        child = FakePlan(
            id="other_plan_00000000",
            body="Uses the skip_list module\n",
            started="2026-09-02T00:00:00Z",
            source="cursor",
        )
        self.assertIsNone(lineage.derive_parent(child, [parent, child], {}))

    def test_started_is_compared_as_an_instant_not_as_text(self):
        parent = FakePlan(id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z")
        child = FakePlan(id="slow-otter", body="# Child\n", started="2026-09-01T00:00:00.500Z")
        sessions = {"slow-otter": FakeSession(prompt="Resume ~/.claude/plans/eager-bird.md")}
        self.assertEqual(lineage.derive_parent(child, [parent, child], sessions), parent.id)

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

    def test_earliest_mentioned_exact_reference_wins(self):
        older = FakePlan(id="older-plan", body="# Older\n", started="2026-09-01T00:00:00Z")
        newer = FakePlan(id="newer-plan", body="# Newer\n", started="2026-09-05T00:00:00Z")
        child = FakePlan(
            id="child-plan",
            body="See ~/.claude/plans/older-plan.md and ~/.claude/plans/newer-plan.md\n",
            started="2026-09-10T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [older, newer, child], {})
        self.assertEqual(parent_id, older.id)

    def test_codename_reference_resolves_to_the_full_id(self):
        parent = FakePlan(
            id="plan-claude-plans-implement-plan-claude-wobbly-willow",
            body="# Parent\n",
            started="2026-09-01T00:00:00Z",
        )
        child = FakePlan(
            id="follow-up-to-plan-wobbly-willow-merry-spindle",
            body="Follow-up to plan wobbly-willow\n\n## Progress\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertEqual(parent_id, parent.id)

    def test_exact_reference_outranks_a_codename_reference_in_the_same_tier(self):
        codename_hit = FakePlan(
            id="wobbly-willow", body="# Codename hit\n", started="2026-09-01T00:00:00Z"
        )
        exact_hit = FakePlan(id="exact-plan", body="# Exact hit\n", started="2026-09-02T00:00:00Z")
        child = FakePlan(
            id="child-plan",
            body="Mentions wobbly-willow first, then ~/.claude/plans/exact-plan.md\n",
            started="2026-09-05T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [codename_hit, exact_hit, child], {})
        self.assertEqual(parent_id, exact_hit.id)

    def test_first_mentioned_codename_wins_over_a_later_one(self):
        agile_micali = FakePlan(id="agile-micali", body="# Older\n", started="2026-09-01T00:00:00Z")
        recursive_kahan = FakePlan(
            id="recursive-kahan", body="# Newer\n", started="2026-09-05T00:00:00Z"
        )
        child = FakePlan(
            id="kahan-twinkly-fiddle",
            body="Plan agile-micali landed and recursive-kahan too\n\n## Progress\n- [ ] todo\n",
            started="2026-09-10T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [agile_micali, recursive_kahan, child], {})
        self.assertEqual(parent_id, agile_micali.id)

    def test_ambiguous_codename_derives_nothing(self):
        first = FakePlan(
            id="something-twinkly-fiddle", body="# First\n", started="2026-09-01T00:00:00Z"
        )
        second = FakePlan(
            id="another-twinkly-fiddle", body="# Second\n", started="2026-09-02T00:00:00Z"
        )
        child = FakePlan(
            id="child-plan",
            body="See twinkly-fiddle for context\n\n## Progress\n- [ ] todo\n",
            started="2026-09-05T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [first, second, child], {})
        self.assertIsNone(parent_id)

    def test_codename_embedded_in_a_longer_id_is_not_a_reference(self):
        wobbly_willow = FakePlan(
            id="wobbly-willow", body="# Parent\n", started="2026-09-01T00:00:00Z"
        )
        child = FakePlan(
            id="child-plan",
            body="Follow-up to plan wobbly-willow-merry-spindle\n\n## Progress\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [wobbly_willow, child], {})
        self.assertIsNone(parent_id)

    def test_codename_reference_in_a_different_project_is_ignored(self):
        parent = FakePlan(
            id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z", project="other"
        )
        child = FakePlan(
            id="slow-otter",
            body="See eager-bird\n\n## Progress\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
            project="example",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertIsNone(parent_id)

    def test_codename_reference_from_a_different_source_is_ignored(self):
        parent = FakePlan(
            id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z", source="cursor"
        )
        child = FakePlan(
            id="slow-otter",
            body="See eager-bird\n\n## Progress\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
            source="claude",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertIsNone(parent_id)

    def test_codename_reference_started_after_plan_is_ignored(self):
        parent = FakePlan(id="eager-bird", body="# Parent\n", started="2026-09-10T00:00:00Z")
        child = FakePlan(
            id="slow-otter",
            body="See eager-bird\n\n## Progress\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertIsNone(parent_id)

    def test_codename_self_reference_is_ignored(self):
        solo = FakePlan(
            id="standalone-plan",
            body="See standalone-plan\n\n## Progress\n- [ ] todo\n",
            started="2026-09-01T00:00:00Z",
        )
        parent_id = lineage.derive_parent(solo, [solo], {})
        self.assertIsNone(parent_id)

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

    def test_candidate_from_a_different_source_is_ignored(self):
        parent = FakePlan(
            id="eager-bird", body="# Parent\n", started="2026-09-01T00:00:00Z", source="cursor"
        )
        child = FakePlan(
            id="slow-otter",
            body="See ~/.claude/plans/eager-bird.md\n",
            started="2026-09-02T00:00:00Z",
            source="claude",
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

    def test_cursor_plan_reference_finds_parent(self):
        parent = FakePlan(
            id="eager-bird",
            body="# Parent\n",
            started="2026-09-01T00:00:00Z",
            source="cursor",
        )
        child = FakePlan(
            id="slow-otter",
            body="See ~/.cursor/plans/eager-bird.plan.md\n",
            started="2026-09-02T00:00:00Z",
            source="cursor",
        )
        parent_id = lineage.derive_parent(child, [parent, child], {})
        self.assertEqual(parent_id, parent.id)


class InCycleTests(unittest.TestCase):
    def test_a_chain_returning_to_the_plan_is_a_cycle(self):
        self.assertTrue(lineage.in_cycle("a", {"a": "b", "b": "c", "c": "a"}))

    def test_a_self_parent_is_a_cycle(self):
        self.assertTrue(lineage.in_cycle("a", {"a": "a"}))

    def test_a_chain_into_another_plans_cycle_is_not_a_cycle(self):
        parent_of = {"x": "a", "a": "b", "b": "a"}
        self.assertFalse(lineage.in_cycle("x", parent_of))
        self.assertTrue(lineage.in_cycle("a", parent_of))

    def test_a_chain_ending_at_a_root_or_a_missing_plan_is_not_a_cycle(self):
        self.assertFalse(lineage.in_cycle("a", {"a": "b", "b": None}))
        self.assertFalse(lineage.in_cycle("a", {"a": "gone"}))
        self.assertFalse(lineage.in_cycle("a", {}))


if __name__ == "__main__":
    unittest.main()
