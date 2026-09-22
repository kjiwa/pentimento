from __future__ import annotations

import dataclasses
import unittest

from pentimento import check
from pentimento import touches as touches_module


@dataclasses.dataclass
class FakePlan:
    id: str
    status: str = "not-started"
    pinned: bool = False
    intent: str = "unset"
    tags: list = dataclasses.field(default_factory=list)
    parent: str | None = None
    project: str | None = "example"
    source: str = "claude"
    has_title: bool = True
    body: str = "## Progress\n\n- [ ] todo\n"
    started: str = ""


@dataclasses.dataclass
class FakeSession:
    project: str = ""
    prompt: str = ""


class RunTests(unittest.TestCase):
    def test_clean_corpus_has_no_findings(self):
        root = FakePlan(id="root")
        child = FakePlan(id="child", parent="root")
        self.assertEqual(check.run([root, child]), [])

    def test_dangling_parent_is_reported(self):
        plan = FakePlan(id="orphan", parent="no-such-plan")
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "dangling-parent")
        self.assertEqual(findings[0].plan_id, "orphan")
        self.assertNotIn("orphan", findings[0].message)

    def test_self_parent_is_reported(self):
        plan = FakePlan(id="loopy", parent="loopy")
        findings = check.run([plan])
        self.assertTrue(any(f.code == "self-parent" and f.plan_id == "loopy" for f in findings))

    def test_cross_project_parent_is_reported(self):
        parent = FakePlan(id="parent", project="project-a")
        child = FakePlan(id="child", parent="parent", project="project-b")
        findings = check.run([parent, child])
        self.assertTrue(
            any(f.code == "cross-project-parent" and f.plan_id == "child" for f in findings)
        )

    def test_cycle_is_reported(self):
        a = FakePlan(id="a", parent="b")
        b = FakePlan(id="b", parent="a")
        findings = check.run([a, b])
        self.assertTrue(any(f.code == "cycle" and f.plan_id == "a" for f in findings))
        self.assertTrue(any(f.code == "cycle" and f.plan_id == "b" for f in findings))

    def test_self_parent_is_reported_once_without_cycle_duplicate(self):
        plan = FakePlan(id="loopy", parent="loopy")
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "self-parent")

    def test_node_pointing_to_cycle_is_not_reported_as_cycle(self):
        a = FakePlan(id="a", parent="b")
        b = FakePlan(id="b", parent="a")
        x = FakePlan(id="x", parent="a")
        findings = check.run([a, b, x])
        cycle_ids = [f.plan_id for f in findings if f.code == "cycle"]
        self.assertIn("a", cycle_ids)
        self.assertIn("b", cycle_ids)
        self.assertNotIn("x", cycle_ids)

    def test_off_vocabulary_status_is_reported(self):
        plan = FakePlan(id="weird-status", status="bogus")
        findings = check.run([plan])
        self.assertTrue(
            any(f.code == "off-vocabulary-status" and f.plan_id == "weird-status" for f in findings)
        )

    def test_off_vocabulary_intent_is_reported(self):
        plan = FakePlan(id="weird-intent", intent="bogus")
        findings = check.run([plan])
        self.assertTrue(
            any(f.code == "off-vocabulary-intent" and f.plan_id == "weird-intent" for f in findings)
        )

    def test_duplicate_id_across_sources_is_reported(self):
        claude_plan = FakePlan(id="same-id", source="claude")
        cursor_plan = FakePlan(id="same-id", source="cursor")
        findings = check.run([claude_plan, cursor_plan])
        self.assertTrue(any(f.code == "duplicate-id" and f.plan_id == "same-id" for f in findings))

    def test_missing_title_is_reported(self):
        plan = FakePlan(id="no-title", has_title=False)
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing-title")
        self.assertEqual(findings[0].plan_id, "no-title")
        self.assertNotIn("no-title", findings[0].message)

    def test_malformed_tag_is_reported(self):
        plan = FakePlan(id="bad-tags", tags=["Auth", "security"])
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "malformed-tag")
        self.assertEqual(findings[0].plan_id, "bad-tags")
        self.assertIn("Auth", findings[0].message)

    def test_valid_tags_are_not_reported(self):
        plan = FakePlan(id="good-tags", tags=["auth", "security"])
        self.assertEqual(check.run([plan]), [])

    def test_missing_progress_is_reported(self):
        plan = FakePlan(id="no-progress", body="# Root\n\nJust prose, no heading.\n")
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing-progress")
        self.assertEqual(findings[0].plan_id, "no-progress")
        self.assertNotIn("no-progress", findings[0].message)

    def test_missing_progress_is_silent_when_heading_is_present(self):
        plan = FakePlan(id="has-progress", body="## Progress\n\n- [ ] todo\n")
        self.assertEqual(check.run([plan]), [])

    def test_underived_project_fires_when_session_supplies_a_project(self):
        plan = FakePlan(id="no-project", project=None)
        sessions = {"no-project": FakeSession(project="real-project")}
        findings = check.run([plan], sessions)
        self.assertTrue(
            any(f.code == "underived-project" and f.plan_id == "no-project" for f in findings)
        )

    def test_underived_project_is_silent_without_a_session(self):
        plan = FakePlan(id="no-project", project=None)
        self.assertEqual(check.run([plan]), [])

    def test_underived_project_is_silent_when_project_already_set(self):
        plan = FakePlan(id="has-project", project="example")
        sessions = {"has-project": FakeSession(project="real-project")}
        self.assertEqual(check.run([plan], sessions), [])

    def test_status_behind_history_fires_when_a_later_session_worked_the_plan(self):
        plan = FakePlan(id="not-started-but-done", status="not-started")
        touches = {
            "not-started-but-done": [
                touches_module.Touch(
                    plan_id="not-started-but-done",
                    session="implement-it-later",
                    tool="Read",
                    at="2026-09-05T00:00:00.000Z",
                    cwd="/home/user/example",
                )
            ]
        }
        findings = check.run([plan], touches=touches)
        self.assertTrue(
            any(
                f.code == "status-behind-history" and f.plan_id == "not-started-but-done"
                for f in findings
            )
        )

    def test_status_behind_history_is_silent_without_touches(self):
        plan = FakePlan(id="not-started-but-done", status="not-started")
        self.assertEqual(check.run([plan]), [])

    def test_status_behind_history_is_silent_when_only_the_authoring_session_touched_it(self):
        plan = FakePlan(id="not-started-but-done", status="not-started")
        touches = {
            "not-started-but-done": [
                touches_module.Touch(
                    plan_id="not-started-but-done",
                    session="not-started-but-done",
                    tool="Write",
                    at="2026-09-01T00:00:00.000Z",
                    cwd="/home/user/example",
                )
            ]
        }
        self.assertEqual(check.run([plan], touches=touches), [])

    def test_status_behind_history_is_silent_for_settled_statuses(self):
        plan = FakePlan(id="already-complete", status="complete")
        touches = {
            "already-complete": [
                touches_module.Touch(
                    plan_id="already-complete",
                    session="implement-it-later",
                    tool="Read",
                    at="2026-09-05T00:00:00.000Z",
                    cwd="/home/user/example",
                )
            ]
        }
        self.assertEqual(check.run([plan], touches=touches), [])

    def test_status_behind_progress_fires_when_progress_outranks_recorded_status(self):
        plan = FakePlan(id="stale", status="not-started", body="## Progress\n\n- [x] done\n")
        findings = check.run([plan])
        self.assertTrue(
            any(f.code == "status-behind-progress" and f.plan_id == "stale" for f in findings)
        )

    def test_status_behind_progress_is_silent_for_superseded(self):
        plan = FakePlan(id="stale", status="superseded", body="## Progress\n\n- [x] done\n")
        self.assertEqual(check.run([plan]), [])

    def test_status_behind_progress_is_silent_when_in_sync(self):
        plan = FakePlan(id="synced", status="complete", body="## Progress\n\n- [x] done\n")
        self.assertEqual(check.run([plan]), [])

    def test_status_behind_progress_is_silent_for_pinned(self):
        plan = FakePlan(
            id="stale", status="not-started", pinned=True, body="## Progress\n\n- [x] done\n"
        )
        findings = check.run([plan])
        self.assertFalse(any(f.code == "status-behind-progress" for f in findings))

    def test_pin_diverged_fires_when_pinned_status_disagrees_with_derived(self):
        plan = FakePlan(
            id="stale", status="not-started", pinned=True, body="## Progress\n\n- [x] done\n"
        )
        findings = check.run([plan])
        self.assertTrue(any(f.code == "pin-diverged" and f.plan_id == "stale" for f in findings))

    def test_pin_diverged_is_silent_when_pinned_status_agrees(self):
        plan = FakePlan(
            id="synced", status="complete", pinned=True, body="## Progress\n\n- [x] done\n"
        )
        self.assertEqual(check.run([plan]), [])

    def test_pin_diverged_is_silent_when_unpinned(self):
        plan = FakePlan(id="unpinned", status="not-started", body="## Progress\n\n- [x] done\n")
        findings = check.run([plan])
        self.assertFalse(any(f.code == "pin-diverged" for f in findings))

    def test_unreadable_file_is_reported(self):
        from pathlib import Path

        skips = [("claude", Path("/plans/secret.md"), OSError("Permission denied"))]
        findings = check.run([], skips=skips)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "unreadable-file")
        self.assertEqual(findings[0].plan_id, "secret.md")

    def test_no_skips_means_no_unreadable_file_findings(self):
        self.assertEqual(check.run([FakePlan(id="root")], skips=[]), [])

    def test_unadopted_reference_fires_on_a_parentless_plan_with_an_eligible_reference(self):
        parent = FakePlan(id="eager-bird", started="2026-09-01T00:00:00Z")
        child = FakePlan(
            id="slow-otter",
            body="See eager-bird for background.\n\n## Progress\n\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
        )
        findings = check.run([parent, child])
        self.assertTrue(
            any(f.code == "unadopted-reference" and f.plan_id == "slow-otter" for f in findings)
        )

    def test_unadopted_reference_is_silent_when_parent_is_set(self):
        parent = FakePlan(id="eager-bird", started="2026-09-01T00:00:00Z")
        child = FakePlan(
            id="slow-otter",
            parent="eager-bird",
            body="See eager-bird for background.\n\n## Progress\n\n- [ ] todo\n",
            started="2026-09-02T00:00:00Z",
        )
        findings = check.run([parent, child])
        self.assertFalse(any(f.code == "unadopted-reference" for f in findings))


if __name__ == "__main__":
    unittest.main()
