import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from pentimento import cli, corpus


def _write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.md").write_text(text)


def _restore_env(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


def _isolate_env(test, directory):
    for key, value in (
        ("AGENT_PLANS_DIR", str(directory)),
        ("AGENT_SESSIONS_DIR", str(directory / "no-such-sessions-dir")),
        ("CURSOR_PLANS_DIR", str(directory / "no-such-cursor-plans-dir")),
    ):
        previous = os.environ.get(key)
        os.environ[key] = value
        test.addCleanup(_restore_env, key, previous)


class CmdSetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_rejects_parent_with_no_such_plan(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        args = cli.build_parser().parse_args(["set", "root-plan", "--parent", "no-such-plan"])
        result = cli.cmd_set(args)
        self.assertEqual(result, 1)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertNotIn("parent", reloaded.fields)

    def test_accepts_parent_that_resolves_to_a_plan(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        _write(self.directory, "child-plan", "# Child\n\n## Progress\n- [ ] todo\n")
        args = cli.build_parser().parse_args(["set", "child-plan", "--parent", "root-plan"])
        result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "child-plan")
        self.assertEqual(reloaded.fields["parent"], "root-plan")


class CmdCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_clean_corpus_exits_zero(self):
        _write(self.directory, "root-plan", "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n")
        args = cli.build_parser().parse_args(["check"])
        self.assertEqual(cli.cmd_check(args), 0)

    def test_dangling_parent_exits_one(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\nparent: no-such-plan\n---\n\n# Root\n",
        )
        args = cli.build_parser().parse_args(["check"])
        self.assertEqual(cli.cmd_check(args), 1)


class CmdBackfillRederiveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_rederive_flag_recomputes_status(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n\n## Progress\n- [x] done\n",
        )
        args = cli.build_parser().parse_args(["backfill", "--rederive", "--quiet"])
        self.assertEqual(cli.cmd_backfill(args), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")


class CmdBackfillRecreateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_recreate_flag_overwrites_created_but_plain_backfill_does_not(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\ncreated: 2020-01-01\n---\n\n# Root\n",
        )
        plain_args = cli.build_parser().parse_args(["backfill", "--quiet"])
        cli.cmd_backfill(plain_args)
        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.fields["created"], "2020-01-01")

        recreate_args = cli.build_parser().parse_args(["backfill", "--recreate", "--quiet"])
        cli.cmd_backfill(recreate_args)
        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertNotEqual(reloaded.fields["created"], "2020-01-01")


class CmdFooterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def _run(self, args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.COMMANDS[args.command](args)
        return out.getvalue()

    def test_list_table_footer_reports_unfiltered_count(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["list", "--color", "never"])
        output = self._run(args)
        self.assertIn("1 plan", output.splitlines()[-1])

    def test_list_table_footer_reports_filtered_of_total(self):
        _write(self.directory, "root-plan", "---\nstatus: complete\n---\n\n# Root\n")
        _write(self.directory, "other-plan", "---\nstatus: not-started\n---\n\n# Other\n")
        args = cli.build_parser().parse_args(["list", "--status", "complete", "--color", "never"])
        output = self._run(args)
        self.assertIn("1 of 2 plans", output.splitlines()[-1])

    def test_list_json_has_no_footer(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["list", "--format", "json"])
        output = self._run(args)
        self.assertNotIn("plan", output.splitlines()[-1].lower())

    def test_tree_table_footer_reports_unfiltered_count(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["tree", "--color", "never"])
        output = self._run(args)
        self.assertIn("1 plan", output.splitlines()[-1])

    def test_tree_tsv_has_no_footer(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["tree", "--format", "tsv"])
        output = self._run(args)
        self.assertNotIn("1 plan", output)

    def test_check_reports_summary(self):
        _write(self.directory, "root-plan", "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n")
        args = cli.build_parser().parse_args(["check"])
        output = self._run(args)
        self.assertIn("1 plan checked, 0 findings", output)

    def test_index_reports_summary(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["index"])
        output = self._run(args)
        self.assertIn("1 plan indexed", output)


class CmdListSortTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_default_sort_is_oldest_modified_first(self):
        _write(self.directory, "older-plan", "# Older\n")
        os.utime(self.directory / "older-plan.md", (1000, 1000))
        _write(self.directory, "newer-plan", "# Newer\n")
        os.utime(self.directory / "newer-plan.md", (2000, 2000))

        args = cli.build_parser().parse_args(["list", "--format", "json"])
        plans = corpus.load_all(self.directory)
        ordered = sorted(plans, key=cli._sort_key(args), reverse=cli._sort_descending(args))
        self.assertEqual([p.id for p in ordered], ["older-plan", "newer-plan"])

    def test_order_desc_puts_newest_modified_first(self):
        _write(self.directory, "older-plan", "# Older\n")
        os.utime(self.directory / "older-plan.md", (1000, 1000))
        _write(self.directory, "newer-plan", "# Newer\n")
        os.utime(self.directory / "newer-plan.md", (2000, 2000))

        args = cli.build_parser().parse_args(["list", "--order", "desc"])
        plans = corpus.load_all(self.directory)
        ordered = sorted(plans, key=cli._sort_key(args), reverse=cli._sort_descending(args))
        self.assertEqual([p.id for p in ordered], ["newer-plan", "older-plan"])

    def test_id_sort_is_ascending_by_default(self):
        _write(self.directory, "b-plan", "# B\n")
        _write(self.directory, "a-plan", "# A\n")
        args = cli.build_parser().parse_args(["list", "--sort", "id"])
        plans = corpus.load_all(self.directory)
        ordered = sorted(plans, key=cli._sort_key(args), reverse=cli._sort_descending(args))
        self.assertEqual([p.id for p in ordered], ["a-plan", "b-plan"])

    def test_status_sort_ranks_lifecycle_order(self):
        _write(self.directory, "done-plan", "---\nstatus: complete\n---\n\n# Done\n")
        _write(self.directory, "new-plan", "---\nstatus: not-started\n---\n\n# New\n")
        args = cli.build_parser().parse_args(["list", "--sort", "status"])
        plans = corpus.load_all(self.directory)
        ordered = sorted(plans, key=cli._sort_key(args), reverse=cli._sort_descending(args))
        self.assertEqual([p.id for p in ordered], ["new-plan", "done-plan"])


if __name__ == "__main__":
    unittest.main()
