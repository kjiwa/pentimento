import tempfile
import unittest
from pathlib import Path

from pentimento import backfill, corpus


def _write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.md").write_text(text)


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def test_backfill_writes_derived_status(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory)
        changed = backfill.run(plans)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.load_all(self.directory)[0]
        self.assertEqual(reloaded.fields["status"], "complete")
        self.assertEqual(reloaded.fields["intent"], "unset")
        self.assertNotIn("parent", reloaded.fields)

    def test_backfill_is_idempotent(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        first_plans = corpus.load_all(self.directory)
        backfill.run(first_plans)

        second_plans = corpus.load_all(self.directory)
        second_changed = backfill.run(second_plans)
        self.assertEqual(second_changed, [])

        third_plans = corpus.load_all(self.directory)
        third_changed = backfill.run(third_plans)
        self.assertEqual(third_changed, [])

    def test_backfill_preserves_body_bytes_apart_from_frontmatter(self):
        original = "# Root\n\nabove\n\n---\n\nbelow (a horizontal rule, not frontmatter)\n"
        _write(self.directory, "root-plan", original)
        plans = corpus.load_all(self.directory)
        backfill.run(plans)

        text = (self.directory / "root-plan.md").read_text()
        self.assertTrue(text.endswith(original))

    def test_dry_run_writes_nothing(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        plans = corpus.load_all(self.directory)
        changed = backfill.run(plans, dry_run=True)
        self.assertEqual(changed, ["root-plan"])

        reloaded = corpus.load_all(self.directory)[0]
        self.assertEqual(reloaded.fields, {})

    def test_lineage_derived_across_corpus(self):
        _write(self.directory, "eager-bird", "# Root plan\n\n## Progress\nPlanning only.\n")
        _write(
            self.directory,
            "resume-eager-bird-slow-otter",
            "# Resume\n\nSee ~/.claude/plans/eager-bird.md\n\n## Progress\nPlanning only.\n",
        )
        plans = corpus.load_all(self.directory)
        backfill.run(plans)

        child = corpus.by_id(corpus.load_all(self.directory), "resume-eager-bird-slow-otter")
        self.assertEqual(child.fields["parent"], "eager-bird")


if __name__ == "__main__":
    unittest.main()
