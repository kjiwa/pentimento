import contextlib
import io
import json
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

    def test_clear_parent_flag_removes_parent(self):
        _write(
            self.directory,
            "child-plan",
            "---\nstatus: not-started\nintent: unset\nparent: root-plan\n---\n\n# Child\n",
        )
        args = cli.build_parser().parse_args(["set", "child-plan", "--clear-parent"])
        result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "child-plan")
        self.assertNotIn("parent", reloaded.fields)

    def test_empty_parent_removes_parent(self):
        _write(
            self.directory,
            "child-plan",
            "---\nstatus: not-started\nintent: unset\nparent: root-plan\n---\n\n# Child\n",
        )
        args = cli.build_parser().parse_args(["set", "child-plan", "--parent", ""])
        result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "child-plan")
        self.assertNotIn("parent", reloaded.fields)

    def test_add_tag_writes(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["set", "root-plan", "--add-tag", "auth"])
        self.assertEqual(cli.cmd_set(args), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.tags, ["auth"])

    def test_existing_mixed_case_tags_are_normalized_on_any_tag_edit(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\ntags: [Auth]\n---\n\n# Root\n",
        )
        args = cli.build_parser().parse_args(["set", "root-plan", "--add-tag", "security"])
        self.assertEqual(cli.cmd_set(args), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.tags, ["auth", "security"])

    def test_remove_tag_removes_a_normalized_match(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\ntags: [auth, security]\n---\n\n# Root\n",
        )
        args = cli.build_parser().parse_args(["set", "root-plan", "--remove-tag", "auth"])
        self.assertEqual(cli.cmd_set(args), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.tags, ["security"])

    def test_clear_tags_pops_the_field(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\ntags: [auth, security]\n---\n\n# Root\n",
        )
        args = cli.build_parser().parse_args(["set", "root-plan", "--clear-tags"])
        self.assertEqual(cli.cmd_set(args), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertNotIn("tags", reloaded.fields)

    def test_invalid_tag_exits_one_and_writes_nothing(self):
        original = "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n"
        _write(self.directory, "root-plan", original)
        args = cli.build_parser().parse_args(["set", "root-plan", "--add-tag", "Nope!"])
        self.assertEqual(cli.cmd_set(args), 1)

        text = (self.directory / "root-plan.md").read_text()
        self.assertEqual(text, original)

    def test_status_change_preserves_mtime(self):
        _write(
            self.directory,
            "root-plan",
            "---\npentimento:\n  status: not-started\n  intent: unset\n---\n\n# Root\n",
        )
        path = self.directory / "root-plan.md"
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime - 86400))
        before = path.stat().st_mtime

        args = cli.build_parser().parse_args(["set", "root-plan", "--status", "complete"])
        self.assertEqual(cli.cmd_set(args), 0)

        self.assertEqual(path.stat().st_mtime, before)
        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_no_op_set_leaves_file_bytes_and_mtime_untouched(self):
        original = "---\npentimento:\n  status: not-started\n  intent: unset\n---\n\n# Root\n"
        _write(self.directory, "root-plan", original)
        path = self.directory / "root-plan.md"
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime - 86400))
        before = path.stat().st_mtime

        args = cli.build_parser().parse_args(["set", "root-plan", "--status", "not-started"])
        self.assertEqual(cli.cmd_set(args), 0)

        self.assertEqual(path.stat().st_mtime, before)
        self.assertEqual(path.read_text(), original)


class CmdListTagFilterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def _run_json(self, argv):
        out = io.StringIO()
        args = cli.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(out):
            cli.COMMANDS[args.command](args)
        return out.getvalue()

    def test_repeated_tag_is_an_and_filter(self):
        _write(
            self.directory,
            "auth-plan",
            "---\nstatus: not-started\nintent: unset\ntags: [auth, security]\n---\n\n# Auth\n",
        )
        _write(
            self.directory,
            "billing-plan",
            "---\nstatus: not-started\nintent: unset\ntags: [billing]\n---\n\n# Billing\n",
        )

        both = json.loads(self._run_json(["list", "--tag", "auth", "--tag", "security", "--format", "json"]))
        self.assertEqual([p["id"] for p in both], ["auth-plan"])

        neither = json.loads(self._run_json(["list", "--tag", "auth", "--tag", "billing", "--format", "json"]))
        self.assertEqual(neither, [])

    def test_tag_filter_is_case_insensitive(self):
        _write(
            self.directory,
            "auth-plan",
            "---\nstatus: not-started\nintent: unset\ntags: [Auth]\n---\n\n# Auth\n",
        )
        matched = json.loads(self._run_json(["list", "--tag", "auth", "--format", "json"]))
        self.assertEqual([p["id"] for p in matched], ["auth-plan"])

    def test_empty_result_emits_empty_json_array(self):
        _write(self.directory, "root-plan", "# Root\n")
        output = self._run_json(["list", "--project", "no-such", "--format", "json"])
        self.assertEqual(json.loads(output), [])


class CmdShowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_field_order_is_canonical_regardless_of_file_order(self):
        _write(
            self.directory,
            "root-plan",
            "---\nproject: example\nstatus: complete\nintent: active\n---\n\n# Root\n",
        )
        out = io.StringIO()
        args = cli.build_parser().parse_args(["show", "root-plan"])
        with contextlib.redirect_stdout(out):
            cli.cmd_show(args)
        lines = out.getvalue().splitlines()
        id_index = next(i for i, line in enumerate(lines) if line.startswith("id:"))
        status_index = next(i for i, line in enumerate(lines) if line.startswith("status:"))
        intent_index = next(i for i, line in enumerate(lines) if line.startswith("intent:"))
        project_index = next(i for i, line in enumerate(lines) if line.startswith("project:"))
        self.assertLess(id_index, status_index)
        self.assertLess(status_index, intent_index)
        self.assertLess(intent_index, project_index)

    def test_id_line_holds_the_plan_id(self):
        _write(self.directory, "root-plan", "# Root\n")
        out = io.StringIO()
        args = cli.build_parser().parse_args(["show", "root-plan"])
        with contextlib.redirect_stdout(out):
            cli.cmd_show(args)
        lines = out.getvalue().splitlines()
        id_line = next(line for line in lines if line.startswith("id:"))
        self.assertIn("root-plan", id_line)


class CmdCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_clean_corpus_exits_zero(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n\n## Progress\n- [ ] todo\n",
        )
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

    def test_table_output_prints_a_code_plan_message_header(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\nparent: no-such-plan\n---\n\n# Root\n",
        )
        out = io.StringIO()
        args = cli.build_parser().parse_args(["check", "--color", "never"])
        with contextlib.redirect_stdout(out):
            cli.cmd_check(args)
        header = out.getvalue().splitlines()[0]
        self.assertEqual(header.split(), ["CODE", "PLAN", "MESSAGE"])


class CmdHistoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_no_such_plan_exits_one(self):
        args = cli.build_parser().parse_args(["history", "no-such-plan"])
        self.assertEqual(cli.cmd_history(args), 1)

    def test_no_history_prints_message_and_exits_zero(self):
        _write(self.directory, "root-plan", "# Root\n")
        out = io.StringIO()
        args = cli.build_parser().parse_args(["history", "root-plan"])
        with contextlib.redirect_stdout(out):
            result = cli.cmd_history(args)
        self.assertEqual(result, 0)
        self.assertIn("no session history for root-plan", out.getvalue())


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
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n\n## Progress\n- [ ] todo\n",
        )
        args = cli.build_parser().parse_args(["check"])
        output = self._run(args)
        self.assertIn("1 plan checked, 0 findings", output)

    def test_index_reports_summary(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["index"])
        output = self._run(args)
        self.assertIn("1 plan indexed", output)
    def test_list_empty_filter_reports_summary(self):
        _write(self.directory, "root-plan", "---\nstatus: complete\n---\n\n# Root\n")
        args = cli.build_parser().parse_args(["list", "--status", "not-started", "--color", "never"])
        output = self._run(args)
        self.assertIn("0 of 1 plan", output)

    def test_tree_empty_filter_reports_summary(self):
        _write(self.directory, "root-plan", "---\nstatus: complete\n---\n\n# Root\n")
        args = cli.build_parser().parse_args(["tree", "--status", "not-started", "--color", "never"])
        output = self._run(args)
        self.assertIn("0 of 1 plan", output)



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


class VersionTests(unittest.TestCase):
    def test_version_flag_exits_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.build_parser().parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)


class EmptyCorpusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name) / "no-such-plans-dir"
        _isolate_env(self, self.directory)

    def test_list_hint_goes_to_stderr_with_exit_zero(self):
        args = cli.build_parser().parse_args(["list"])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = cli.cmd_list(args)
        self.assertEqual(result, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertNotEqual(err.getvalue(), "")

    def test_tree_hint_goes_to_stderr_with_exit_zero(self):
        args = cli.build_parser().parse_args(["tree"])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = cli.cmd_tree(args)
        self.assertEqual(result, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertNotEqual(err.getvalue(), "")


class UnknownIdSuggestionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_show_suggests_a_close_match(self):
        _write(self.directory, "api-auth-rollout", "# Rollout\n")
        args = cli.build_parser().parse_args(["show", "api-auth-rollot"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = cli.cmd_show(args)
        self.assertEqual(result, 1)
        self.assertIn("did you mean", err.getvalue())
        self.assertIn("api-auth-rollout", err.getvalue())


class BackfillFooterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_dry_run_footer_distinguishes_from_a_real_run(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["backfill", "--dry-run"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.cmd_backfill(args)
        self.assertIn("(dry run)", out.getvalue())

    def test_no_changes_footer(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["backfill"])
        cli.cmd_backfill(args)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.cmd_backfill(args)
        self.assertIn("no changes", out.getvalue())

    def test_quiet_suppresses_footer(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["backfill", "--quiet"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.cmd_backfill(args)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
