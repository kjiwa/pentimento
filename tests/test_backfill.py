import tempfile
import unittest
from pathlib import Path

from pentimento import backfill, corpus, sessions
from pentimento import plan as plan_module


def _write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.md").write_text(text)


CURSOR_FIXTURES = Path(__file__).parent / "fixtures" / "cursor"


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def test_backfill_writes_derived_status(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.load_all(self.directory, sessions={})[0]
        self.assertEqual(reloaded.fields["status"], "complete")
        self.assertEqual(reloaded.fields["intent"], "unset")
        self.assertNotIn("parent", reloaded.fields)

    def test_backfill_derives_a_cursor_plan_from_its_todos(self):
        name = "quiet_flag_83cddd33.plan.md"
        (self.directory / name).write_text((CURSOR_FIXTURES / name).read_text())
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans)
        reloaded = corpus.load_all(self.directory, sessions={})[0]
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_backfill_is_idempotent(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        first_plans = corpus.load_all(self.directory, sessions={})
        backfill.run(first_plans)

        second_plans = corpus.load_all(self.directory, sessions={})
        second_changed = backfill.run(second_plans)
        self.assertEqual(second_changed, [])

        third_plans = corpus.load_all(self.directory, sessions={})
        third_changed = backfill.run(third_plans)
        self.assertEqual(third_changed, [])

    def test_backfill_preserves_body_bytes_apart_from_frontmatter(self):
        original = "# Root\n\nabove\n\n---\n\nbelow (a horizontal rule, not frontmatter)\n"
        _write(self.directory, "root-plan", original)
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans)

        text = (self.directory / "root-plan.md").read_text()
        self.assertTrue(text.endswith(original))

    def test_dry_run_writes_nothing(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans, dry_run=True)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.load_all(self.directory, sessions={})[0]
        self.assertEqual(reloaded.fields, {})

    def test_lineage_derived_across_corpus(self):
        _write(self.directory, "eager-bird", "# Root plan\n\n## Progress\nPlanning only.\n")
        _write(
            self.directory,
            "resume-eager-bird-slow-otter",
            "# Resume\n\nSee ~/.claude/plans/eager-bird.md\n\n## Progress\nPlanning only.\n",
        )
        session_sessions = {
            "eager-bird": sessions.Session(
                slug="eager-bird", project="", started="2026-09-01T00:00:00.000Z", prompt=""
            ),
            "resume-eager-bird-slow-otter": sessions.Session(
                slug="resume-eager-bird-slow-otter",
                project="",
                started="2026-09-02T00:00:00.000Z",
                prompt="",
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        backfill.run(plans, session_sessions)

        child = corpus.by_id(
            corpus.load_all(self.directory, sessions=session_sessions),
            "resume-eager-bird-slow-otter",
        )
        self.assertEqual(child.fields["parent"], "eager-bird")

    def test_parent_derives_against_a_project_derived_in_the_same_pass(self):
        # Regression: a plan with neither `project` nor `parent` in frontmatter must
        # still resolve its parent on the pass that first derives its project --
        # `derive_parent` used to see the plan's stale (absent) project and reject
        # every same-project candidate.
        _write(
            self.directory,
            "earlier-plan",
            "---\nproject: real-project\n---\n\n# Earlier\n\n## Progress\nPlanning only.\n",
        )
        _write(
            self.directory,
            "later-plan",
            "# Later\n\nSee ~/.claude/plans/earlier-plan.md\n\n## Progress\nPlanning only.\n",
        )
        session_sessions = {
            "earlier-plan": sessions.Session(
                slug="earlier-plan",
                project="real-project",
                started="2026-09-01T00:00:00.000Z",
                prompt="",
            ),
            "later-plan": sessions.Session(
                slug="later-plan",
                project="real-project",
                started="2026-09-02T00:00:00.000Z",
                prompt="See ~/.claude/plans/earlier-plan.md",
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        later = corpus.by_id(plans, "later-plan")
        fields = backfill.derive_fields(later, plans, session_sessions)

        self.assertEqual(fields["project"], "real-project")
        self.assertEqual(fields["parent"], "earlier-plan")

    def test_rederive_overwrites_derived_fields_but_not_intent_or_created(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: active\nparent: stale-plan\n"
            "project: stale-project\ncreated: 2020-01-01\n---\n\n# Root\n\n## Progress\n"
            "- [x] done\n",
        )
        session_sessions = {
            "root-plan": sessions.Session(
                slug="root-plan",
                project="real-project",
                started="2026-09-01T00:00:00.000Z",
                prompt="",
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        backfill.run(plans, session_sessions, rederive=True)

        reloaded = corpus.by_id(
            corpus.load_all(self.directory, sessions=session_sessions), "root-plan"
        )
        self.assertEqual(reloaded.fields["status"], "complete")
        self.assertEqual(reloaded.fields["project"], "real-project")
        self.assertEqual(reloaded.fields["intent"], "active")
        self.assertEqual(reloaded.fields["created"], "2020-01-01")
        self.assertNotIn("parent", reloaded.fields)

    def test_flat_file_with_complete_fields_is_migrated_to_nested(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\nintent: unset\ncreated: 2026-09-01\n---\n\n# Root\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, ["root-plan"])

        text = (self.directory / "root-plan.md").read_text()
        self.assertIn("pentimento:\n", text)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")
        self.assertEqual(reloaded.fields["created"], "2026-09-01")

    def test_dry_run_reports_migration_without_writing(self):
        original = "---\nstatus: complete\nintent: unset\ncreated: 2026-09-01\n---\n\n# Root\n"
        _write(self.directory, "root-plan", original)
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans, dry_run=True)
        self.assertEqual(changed, ["root-plan"])

        text = (self.directory / "root-plan.md").read_text()
        self.assertEqual(text, original)

    def test_already_nested_and_correct_file_is_skipped(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: complete\n  intent: unset\n  created: 2026-09-01\n"
            "---\n\n# Root\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, [])

    def test_plain_backfill_gap_fills_project_from_a_session(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\ncreated: 2026-09-01\n---\n\n# Root\n",
        )
        session_sessions = {
            "root-plan": sessions.Session(
                slug="root-plan",
                project="real-project",
                started="2026-09-01T00:00:00.000Z",
                prompt="",
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        changed = backfill.run(plans, session_sessions)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.by_id(
            corpus.load_all(self.directory, sessions=session_sessions), "root-plan"
        )
        self.assertEqual(reloaded.fields["project"], "real-project")

    def test_rederive_does_not_clear_a_project_that_no_longer_derives(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\nproject: kept-project\ncreated: 2026-09-01\n"
            "---\n\n# Root\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, {}, rederive=True)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["project"], "kept-project")

    def test_plan_with_tags_is_not_rewritten_by_backfill(self):
        original = (
            "---\npentimento:\n  status: complete\n  intent: unset\n"
            "  tags: [auth, security]\n  created: 2026-09-01\n---\n\n# Root\n"
        )
        _write(self.directory, "root-plan", original)
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, [])

    def test_plain_backfill_promotes_status_on_checkbox_completion(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: partial\nintent: unset\n---\n\n# Root\n\n## Progress\n"
            "- [x] one\n- [x] two\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_superseded_status_survives_a_plain_backfill(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: superseded\nintent: unset\n---\n\n# Root\n\n## Progress\n- [x] done\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "superseded")

    def test_plain_backfill_promotes_not_started_to_partial(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n\n## Progress\n"
            "- [x] one\n- [ ] two\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "partial")

    def test_backfill_does_not_retract_complete_to_not_started(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: complete\n  intent: unset\n  created: 2026-09-01\n"
            "---\n\n# Root\n\n## Progress\n- [ ] todo\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, [])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_backfill_does_not_retract_partial_to_not_started(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: partial\n  intent: unset\n  created: 2026-09-01\n"
            "---\n\n# Root\n\n## Progress\n- [ ] todo\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, [])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "partial")

    def test_backfill_does_not_retract_complete_to_partial(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: complete\n  intent: unset\n  created: 2026-09-01\n"
            "---\n\n# Root\n\n## Progress\n- [x] one\n- [ ] two\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, [])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_rederive_retracts_complete_when_boxes_are_later_unchecked(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: complete\n  intent: unset\n  created: 2026-09-01\n"
            "---\n\n# Root\n\n## Progress\n- [ ] todo\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans, rederive=True)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "not-started")

    def test_rederive_does_not_overwrite_superseded_status(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: superseded\nintent: unset\n---\n\n# Root\n\n## Progress\n- [x] done\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, rederive=True)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "superseded")

    def test_pinned_status_survives_rederive(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\npinned: true\nintent: unset\n---\n\n"
            "# Root\n\n## Progress\n- [ ] todo\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, rederive=True)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")
        self.assertEqual(reloaded.fields["pinned"], "true")

    def test_unpinned_status_still_rederives(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\nintent: unset\n---\n\n# Root\n\n## Progress\n- [ ] todo\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, rederive=True)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "not-started")

    def test_pinned_plans_parent_and_project_still_rederive(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\npinned: true\nintent: unset\nparent: stale-plan\n"
            "project: stale-project\n---\n\n# Root\n\n## Progress\n- [ ] todo\n",
        )
        session_sessions = {
            "root-plan": sessions.Session(
                slug="root-plan",
                project="real-project",
                started="2026-09-01T00:00:00.000Z",
                prompt="",
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        backfill.run(plans, session_sessions, rederive=True)

        reloaded = corpus.by_id(
            corpus.load_all(self.directory, sessions=session_sessions), "root-plan"
        )
        self.assertEqual(reloaded.fields["status"], "complete")
        self.assertEqual(reloaded.fields["project"], "real-project")
        self.assertNotIn("parent", reloaded.fields)

    def test_set_survives_a_backfill(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: not-started\n  intent: unset\n  created: 2026-09-01\n"
            "---\n\n# Root\n\nNot started.\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        first = corpus.by_id(plans, "root-plan")
        first.fields["status"] = "complete"
        plan_module.save(first, keep_mtime=True)

        reloaded_plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(reloaded_plans)
        self.assertEqual(changed, [])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_existing_status_is_not_downgraded_to_unknown(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\nintent: unset\n---\n\n# Root\n\nNo progress section here.\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_cycle_guard_drops_a_derived_parent_that_would_close_a_loop(self):
        # plan-b's parent was hand-set (e.g. via `set --parent`) against the grain of
        # chronology; plan-a has no parent yet and would naturally derive plan-b as its
        # parent, which would close a two-hop cycle.
        _write(
            self.directory,
            "plan-a",
            "# A\n\nSee ~/.claude/plans/plan-b.md\n\n## Progress\n- [ ] todo\n",
        )
        _write(
            self.directory,
            "plan-b",
            "---\nparent: plan-a\n---\n\n# B\n\n## Progress\n- [ ] todo\n",
        )
        session_sessions = {
            "plan-a": sessions.Session(
                slug="plan-a", project="p", started="2026-09-02T00:00:00.000Z", prompt=""
            ),
            "plan-b": sessions.Session(
                slug="plan-b", project="p", started="2026-09-01T00:00:00.000Z", prompt=""
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        backfill.run(plans, session_sessions)

        reloaded = {p.id: p for p in corpus.load_all(self.directory, sessions=session_sessions)}
        self.assertNotIn("parent", reloaded["plan-a"].fields)
        self.assertEqual(reloaded["plan-b"].fields["parent"], "plan-a")

    def test_a_derived_parent_leading_into_another_plans_cycle_is_kept(self):
        _write(self.directory, "plan-a", "# A\n\nSee ~/.claude/plans/plan-b.md\n")
        _write(self.directory, "plan-b", "---\nproject: p\nparent: plan-c\n---\n\n# B\n")
        _write(self.directory, "plan-c", "---\nproject: p\nparent: plan-b\n---\n\n# C\n")
        session_sessions = {
            name: sessions.Session(slug=name, project="p", started=started, prompt="")
            for name, started in (
                ("plan-a", "2026-09-02T00:00:00.000Z"),
                ("plan-b", "2026-09-01T00:00:00.000Z"),
                ("plan-c", "2026-09-01T00:00:00.000Z"),
            )
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        backfill.run(plans, session_sessions)

        reloaded = {p.id: p for p in corpus.load_all(self.directory, sessions=session_sessions)}
        self.assertEqual(reloaded["plan-a"].fields["parent"], "plan-b")

    def test_a_derived_project_that_cannot_be_written_is_skipped(self):
        _write(self.directory, "plan-a", "# A\n\n## Progress\n- [x] done\n")
        bad = {
            "plan-a": sessions.Session(
                slug="plan-a", project="a #b", started="2026-09-01T00:00:00.000Z", prompt=""
            )
        }
        plans = corpus.load_all(self.directory, sessions=bad)
        backfill.run(plans, bad)

        text = (self.directory / "plan-a.md").read_text()
        self.assertNotIn("project:", text)
        self.assertIn("intent:", text)

    def test_only_restricts_writes_and_returned_changed(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        _write(self.directory, "other-plan", "# Other\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans, only={"root-plan"})
        self.assertEqual(changed, ["root-plan"])

        reloaded = {p.id: p for p in corpus.load_all(self.directory, sessions={})}
        self.assertEqual(reloaded["root-plan"].fields["status"], "complete")
        self.assertEqual(reloaded["other-plan"].fields, {})

    def test_only_is_idempotent(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, only={"root-plan"})

        reloaded_plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(reloaded_plans, only={"root-plan"})
        self.assertEqual(changed, [])

    def test_max_status_caps_absent_status_to_cap(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, max_status="partial")

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "partial")
        self.assertEqual(reloaded.fields["intent"], "unset")

    def test_max_status_leaves_status_at_cap_untouched(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: partial\nintent: unset\n---\n\n# Root\n\n## Progress\n- [x] done\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, max_status="partial")

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "partial")

    def test_max_status_clamps_complete_to_partial(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, max_status="partial")

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "partial")

        # A full backfill without the cap then advances it to complete.
        changed = backfill.run(corpus.load_all(self.directory, sessions={}))
        self.assertEqual(changed, ["root-plan"])
        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_colliding_claude_and_cursor_ids_keep_their_own_derived_status(self):
        # foo.md (Claude) and foo.plan.md (Cursor) collide on id "foo". Before
        # P0-1, derived fields were keyed by id, so the last plan derived in
        # each pass overwrote the field written to every plan sharing that id.
        claude_path = self.directory / "foo.md"
        claude_path.write_text("# Claude\n\n## Progress\n- [ ] todo\n")
        cursor_path = self.directory / "foo.plan.md"
        cursor_path.write_text("# Cursor\n\n## Progress\n- [x] done\n")

        claude_plan = plan_module.load(claude_path, sessions={}, source="claude")
        cursor_plan = plan_module.load(cursor_path, sessions={}, source="cursor")
        self.assertEqual(claude_plan.id, cursor_plan.id)

        plans = [claude_plan, cursor_plan]
        backfill.run(plans)

        reloaded_claude = plan_module.load(claude_path, sessions={}, source="claude")
        reloaded_cursor = plan_module.load(cursor_path, sessions={}, source="cursor")
        self.assertEqual(reloaded_claude.fields["status"], "not-started")
        self.assertEqual(reloaded_cursor.fields["status"], "complete")

    def test_max_status_is_idempotent(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory, sessions={})
        backfill.run(plans, max_status="partial")

        reloaded_plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(reloaded_plans, max_status="partial")
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
