import tempfile
import unittest
from pathlib import Path

from pentimento import backfill, corpus, sessions


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
