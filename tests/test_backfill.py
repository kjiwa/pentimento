import tempfile
import unittest
from pathlib import Path

from pentimento import backfill, corpus, sessions
from pentimento import plan as plan_module


def _write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.md").write_text(text)


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
            corpus.load_all(self.directory, sessions=session_sessions), "resume-eager-bird-slow-otter"
        )
        self.assertEqual(child.fields["parent"], "eager-bird")

    def test_rederive_overwrites_derived_fields_but_not_intent_or_created(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: active\nparent: stale-plan\n"
            "project: stale-project\ncreated: 2020-01-01\n---\n\n# Root\n\n## Progress\n- [x] done\n",
        )
        session_sessions = {
            "root-plan": sessions.Session(
                slug="root-plan", project="real-project", started="2026-09-01T00:00:00.000Z", prompt=""
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        backfill.run(plans, session_sessions, rederive=True)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions=session_sessions), "root-plan")
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
            "---\npentimento:\n  status: complete\n  intent: unset\n  created: 2026-09-01\n---\n\n# Root\n",
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
                slug="root-plan", project="real-project", started="2026-09-01T00:00:00.000Z", prompt=""
            ),
        }
        plans = corpus.load_all(self.directory, sessions=session_sessions)
        changed = backfill.run(plans, session_sessions)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions=session_sessions), "root-plan")
        self.assertEqual(reloaded.fields["project"], "real-project")

    def test_rederive_does_not_clear_a_project_that_no_longer_derives(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\nproject: kept-project\ncreated: 2026-09-01\n---\n\n# Root\n",
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
            "---\nstatus: partial\nintent: unset\n---\n\n# Root\n\n## Progress\n- [x] one\n- [x] two\n",
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
            "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n\n## Progress\n- [x] one\n- [ ] two\n",
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
            "---\npentimento:\n  status: complete\n  intent: unset\n  created: 2026-09-01\n---\n\n# Root\n\n## Progress\n- [ ] todo\n",
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
            "---\npentimento:\n  status: partial\n  intent: unset\n  created: 2026-09-01\n---\n\n# Root\n\n## Progress\n- [ ] todo\n",
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
            "---\npentimento:\n  status: complete\n  intent: unset\n  created: 2026-09-01\n---\n\n# Root\n\n## Progress\n- [x] one\n- [ ] two\n",
        )
        plans = corpus.load_all(self.directory, sessions={})
        changed = backfill.run(plans)
        self.assertEqual(changed, [])

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_set_survives_a_backfill(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: not-started\n  intent: unset\n  created: 2026-09-01\n---\n\n# Root\n\nNot started.\n",
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


if __name__ == "__main__":
    unittest.main()
