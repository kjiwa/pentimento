from __future__ import annotations

import dataclasses
import re
import unittest
from pathlib import Path

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


class HintTests(unittest.TestCase):
    def test_hints_cover_the_codes_documented_in_troubleshooting(self):
        docs = Path(__file__).parent.parent / "docs" / "troubleshooting.md"
        documented = set(re.findall(r"^\| `([a-z-]+)` \|", docs.read_text(), re.MULTILINE))
        self.assertEqual(set(check.HINTS), documented)

    def test_every_finding_carries_its_codes_hint(self):
        plan = FakePlan(id="orphan", parent="no-such-plan")
        finding = check.run([plan])[0]
        self.assertEqual(finding.hint, check.HINTS["dangling-parent"])


class UnadoptedTagTests(unittest.TestCase):
    def _codes(self, plans):
        return [(f.code, f.id) for f in check.run(plans) if f.code == "unadopted-tag"]

    def _thread(self, parent_tags, *sibling_tags, child_tags=()):
        plans = [FakePlan(id="root", tags=list(parent_tags))]
        for i, tags in enumerate(sibling_tags):
            plans.append(FakePlan(id=f"sib{i}", parent="root", tags=list(tags)))
        plans.append(FakePlan(id="child", parent="root", tags=list(child_tags)))
        return plans

    def test_fires_with_the_sibling_consensus(self):
        plans = self._thread(["a", "b"], ["a", "b"], ["b", "a", "c"])
        finding = check.run(plans)[0]
        self.assertEqual((finding.code, finding.id), ("unadopted-tag", "child"))
        self.assertEqual(finding.message, "no tags, but its thread carries [a, b]")

    def test_silent_with_no_tagged_sibling(self):
        self.assertEqual(self._codes(self._thread(["a"])), [])

    def test_excludes_a_tag_some_tagged_sibling_lacks(self):
        finding = check.run(self._thread(["a", "b"], ["a", "b"], ["a"]))[0]
        self.assertEqual(finding.message, "no tags, but its thread carries [a]")

    def test_silent_when_no_tag_is_shared(self):
        self.assertEqual(self._codes(self._thread(["a"], ["b"])), [])

    def test_silent_when_the_plan_has_any_tag(self):
        self.assertEqual(self._codes(self._thread(["a"], ["a"], child_tags=["z"])), [])

    def test_silent_when_the_parent_is_untagged(self):
        self.assertEqual(self._codes(self._thread([], ["a"])), [])

    def test_silent_when_the_parent_is_dangling(self):
        plans = [
            FakePlan(id="sib", parent="gone", tags=["a"]),
            FakePlan(id="child", parent="gone"),
        ]
        self.assertEqual(self._codes(plans), [])

    def test_case_insensitive(self):
        findings = check.run(self._thread(["Loadtest"], ["LOADTEST"]))
        finding = next(f for f in findings if f.code == "unadopted-tag")
        self.assertEqual(finding.message, "no tags, but its thread carries [loadtest]")


class ShowHintTests(unittest.TestCase):
    def test_no_show_hint_names_the_show_command(self):
        for code in check.HINTS:
            self.assertNotIn("pentimento show", check.show_hint(code), msg=code)

    def test_a_hint_without_a_show_step_is_unchanged(self):
        self.assertEqual(check.show_hint("self-parent"), check.HINTS["self-parent"])

    def test_a_show_step_is_dropped_from_the_status_hint(self):
        self.assertIn("pentimento show <id>", check.HINTS["underivable-status"])
        self.assertEqual(
            check.show_hint("underivable-status"),
            "add a checklist to '## Progress', or pentimento set <id> --status <value>",
        )


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
        self.assertEqual(findings[0].id, "orphan")
        self.assertNotIn("orphan", findings[0].message)

    def test_self_parent_is_reported(self):
        plan = FakePlan(id="loopy", parent="loopy")
        findings = check.run([plan])
        self.assertTrue(any(f.code == "self-parent" and f.id == "loopy" for f in findings))

    def test_cross_project_parent_is_reported(self):
        parent = FakePlan(id="parent", project="project-a")
        child = FakePlan(id="child", parent="parent", project="project-b")
        findings = check.run([parent, child])
        self.assertTrue(any(f.code == "cross-project-parent" and f.id == "child" for f in findings))

    def test_cycle_is_reported(self):
        a = FakePlan(id="a", parent="b")
        b = FakePlan(id="b", parent="a")
        findings = check.run([a, b])
        self.assertTrue(any(f.code == "cycle" and f.id == "a" for f in findings))
        self.assertTrue(any(f.code == "cycle" and f.id == "b" for f in findings))

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
        cycle_ids = [f.id for f in findings if f.code == "cycle"]
        self.assertIn("a", cycle_ids)
        self.assertIn("b", cycle_ids)
        self.assertNotIn("x", cycle_ids)

    def test_off_vocabulary_status_is_reported(self):
        plan = FakePlan(id="weird-status", status="bogus")
        findings = check.run([plan])
        self.assertTrue(
            any(f.code == "off-vocabulary-status" and f.id == "weird-status" for f in findings)
        )

    def test_off_vocabulary_intent_is_reported(self):
        plan = FakePlan(id="weird-intent", intent="bogus")
        findings = check.run([plan])
        self.assertTrue(
            any(f.code == "off-vocabulary-intent" and f.id == "weird-intent" for f in findings)
        )

    def test_duplicate_id_across_sources_is_reported(self):
        claude_plan = FakePlan(id="same-id", source="claude")
        cursor_plan = FakePlan(id="same-id", source="cursor")
        findings = check.run([claude_plan, cursor_plan])
        self.assertTrue(any(f.code == "duplicate-id" and f.id == "same-id" for f in findings))

    def test_missing_title_is_reported(self):
        plan = FakePlan(id="no-title", has_title=False)
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing-title")
        self.assertEqual(findings[0].id, "no-title")
        self.assertNotIn("no-title", findings[0].message)

    def test_malformed_tag_is_reported(self):
        plan = FakePlan(id="bad-tags", tags=["Auth", "security"])
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "malformed-tag")
        self.assertEqual(findings[0].id, "bad-tags")
        self.assertIn("Auth", findings[0].message)

    def test_valid_tags_are_not_reported(self):
        plan = FakePlan(id="good-tags", tags=["auth", "security"])
        self.assertEqual(check.run([plan]), [])

    def test_underivable_status_fires_for_unknown_status_with_prose_only_progress(self):
        plan = FakePlan(id="prose", status="unknown", body="## Progress\n\nWorking on it.\n")
        findings = check.run([plan])
        self.assertEqual([f.code for f in findings], ["underivable-status"])
        self.assertEqual(findings[0].id, "prose")
        self.assertNotIn("prose", findings[0].message)
        self.assertIn("no checkboxes", findings[0].message)

    def test_underivable_status_names_a_missing_heading(self):
        plan = FakePlan(id="bare", status="unknown", body="# Root\n\nJust prose.\n")
        findings = check.run([plan])
        self.assertEqual([f.code for f in findings], ["underivable-status"])
        self.assertIn("no '## Progress' heading", findings[0].message)

    def test_underivable_status_is_silent_when_progress_derives(self):
        plan = FakePlan(id="derivable", status="unknown", body="## Progress\n\n- [ ] todo\n")
        codes = [f.code for f in check.run([plan])]
        self.assertNotIn("underivable-status", codes)

    def test_underivable_status_is_silent_for_a_recorded_status(self):
        plan = FakePlan(id="recorded", status="partial", body="# Root\n\nJust prose.\n")
        self.assertEqual(check.run([plan]), [])

    def test_explicit_status_silences_status_findings(self):
        prose = "## Progress\n\nDone, see the notes.\n"
        unticked = "## Progress\n\n- [ ] Decision: adopt nothing\n"
        for plan in (
            FakePlan(id="pinned-prose", status="complete", pinned=True, body=prose),
            FakePlan(id="pinned-unticked", status="complete", pinned=True, body=unticked),
            FakePlan(id="pinned-unknown", status="unknown", pinned=True, body=prose),
            FakePlan(id="superseded", status="superseded", body="## Progress\n\n- [x] done\n"),
        ):
            with self.subTest(plan.id):
                self.assertEqual(check.run([plan]), [])

    def test_explicit_status_silences_status_behind_history(self):
        plan = FakePlan(id="pinned-history", status="not-started", pinned=True)
        touches = {
            "pinned-history": [
                touches_module.Touch(
                    plan_id="pinned-history",
                    session="later-session",
                    tool="Edit",
                    at="2026-09-05T00:00:00.000Z",
                    cwd="/home/user/example",
                )
            ]
        }
        self.assertEqual(check.run([plan], touches=touches), [])

    def test_underived_project_fires_when_session_supplies_a_project(self):
        plan = FakePlan(id="no-project", project=None)
        sessions = {"no-project": FakeSession(project="real-project")}
        findings = check.run([plan], sessions)
        self.assertTrue(
            any(f.code == "underived-project" and f.id == "no-project" for f in findings)
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
                f.code == "status-behind-history" and f.id == "not-started-but-done"
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
            any(f.code == "status-behind-progress" and f.id == "stale" for f in findings)
        )

    def test_status_behind_progress_fires_for_stored_unknown(self):
        plan = FakePlan(id="stale", status="unknown", body="## Progress\n\n- [x] done\n")
        self.assertEqual([f.code for f in check.run([plan])], ["status-behind-progress"])

    def test_status_behind_progress_is_silent_when_in_sync(self):
        plan = FakePlan(id="synced", status="complete", body="## Progress\n\n- [x] done\n")
        self.assertEqual(check.run([plan]), [])

    def test_pin_behind_progress_fires_when_progress_outranks_pinned_status(self):
        plan = FakePlan(
            id="stale", status="partial", pinned=True, body="## Progress\n\n- [x] done\n"
        )
        findings = check.run([plan])
        self.assertEqual([f.code for f in findings], ["pin-behind-progress"])
        self.assertEqual(findings[0].id, "stale")

    def test_pin_behind_progress_is_silent_when_pin_is_ahead_or_equal(self):
        for body in ("## Progress\n\n- [x] done\n", "## Progress\n\n- [x] a\n- [ ] b\n"):
            with self.subTest(body=body):
                plan = FakePlan(id="pin", status="complete", pinned=True, body=body)
                self.assertEqual(check.run([plan]), [])

    def test_unreadable_file_is_reported(self):
        skips = [("claude", Path("/plans/secret.md"), OSError("Permission denied"))]
        findings = check.run([], skips=skips)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "unreadable-file")
        self.assertEqual(findings[0].id, "secret.md")

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
            any(f.code == "unadopted-reference" and f.id == "slow-otter" for f in findings)
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
