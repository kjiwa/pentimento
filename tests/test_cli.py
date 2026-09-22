import contextlib
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pentimento import cli, corpus
from tests import _header_block, _silenced, _subparsers_action


class _TtyStream(io.StringIO):
    def __init__(self, is_tty: bool):
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


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

    def test_resolves_a_short_id(self):
        _write(self.directory, "is-it-possible-to-abundant-rabbit", "# Root\n")
        args = cli.build_parser().parse_args(["set", "abundant-rabbit", "--status", "complete"])
        with _silenced():
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(
            corpus.load_all(self.directory), "is-it-possible-to-abundant-rabbit"
        )
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_status_pins_the_plan(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        args = cli.build_parser().parse_args(["set", "root-plan", "--status", "complete"])
        with _silenced():
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.fields["pinned"], "true")

    def test_unpin_clears_a_pinned_status(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\npinned: true\nintent: unset\n---\n\n# Root\n",
        )
        args = cli.build_parser().parse_args(["set", "root-plan", "--unpin"])
        with _silenced():
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertNotIn("pinned", reloaded.fields)

    def test_accepts_parent_that_resolves_to_a_plan(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        _write(self.directory, "child-plan", "# Child\n\n## Progress\n- [ ] todo\n")
        args = cli.build_parser().parse_args(["set", "child-plan", "--parent", "root-plan"])
        with _silenced():
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
        with _silenced():
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "child-plan")
        self.assertNotIn("parent", reloaded.fields)

    def test_empty_string_parent_is_looked_up_literally_not_treated_as_clear(self):
        _write(
            self.directory,
            "child-plan",
            "---\nstatus: not-started\nintent: unset\nparent: root-plan\n---\n\n# Child\n",
        )
        args = cli.build_parser().parse_args(["set", "child-plan", "--parent", ""])
        result = cli.cmd_set(args)
        self.assertEqual(result, 1)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "child-plan")
        self.assertEqual(reloaded.fields["parent"], "root-plan")

    def test_parent_named_none_is_a_real_lookup(self):
        _write(self.directory, "none", "# None\n")
        _write(self.directory, "child-plan", "# Child\n")
        args = cli.build_parser().parse_args(["set", "child-plan", "--parent", "none"])
        with _silenced():
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "child-plan")
        self.assertEqual(reloaded.fields["parent"], "none")

    def test_parent_creating_a_cycle_is_rejected(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\nparent: child-plan\n---\n\n# Root\n",
        )
        _write(
            self.directory,
            "child-plan",
            "---\nstatus: not-started\nintent: unset\nparent: root-plan\n---\n\n# Child\n",
        )
        args = cli.build_parser().parse_args(["set", "root-plan", "--parent", "child-plan"])
        result = cli.cmd_set(args)
        self.assertEqual(result, 1)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.fields["parent"], "child-plan")

    def test_dry_run_reports_without_writing(self):
        original = "---\nstatus: not-started\nintent: unset\n---\n\n# Root\n"
        _write(self.directory, "root-plan", original)
        args = cli.build_parser().parse_args(
            ["set", "root-plan", "--status", "complete", "--dry-run"]
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)
        self.assertIn("status", out.getvalue())
        self.assertIn("dry run", out.getvalue())

        text = (self.directory / "root-plan.md").read_text()
        self.assertEqual(text, original)

    def test_clear_project_flag_removes_project(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\nproject: pentimento\n---\n\n# Root\n",
        )
        args = cli.build_parser().parse_args(["set", "root-plan", "--clear-project"])
        with _silenced():
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertNotIn("project", reloaded.fields)

    def test_no_changes_reports_no_changes(self):
        original = "---\nstatus: not-started\npinned: true\nintent: unset\n---\n\n# Root\n"
        _write(self.directory, "root-plan", original)
        args = cli.build_parser().parse_args(["set", "root-plan", "--status", "not-started"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cli.cmd_set(args)
        self.assertEqual(result, 0)
        self.assertIn("no changes", out.getvalue())

    def test_add_tag_writes(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["set", "root-plan", "--add-tag", "auth"])
        with _silenced():
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
        with _silenced():
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
        with _silenced():
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
        with _silenced():
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
        with _silenced():
            self.assertEqual(cli.cmd_set(args), 0)

        self.assertEqual(path.stat().st_mtime, before)
        reloaded = corpus.by_id(corpus.load_all(self.directory), "root-plan")
        self.assertEqual(reloaded.fields["status"], "complete")

    def test_no_op_set_leaves_file_bytes_and_mtime_untouched(self):
        original = (
            "---\npentimento:\n  status: not-started\n  pinned: true\n  intent: unset\n"
            "---\n\n# Root\n"
        )
        _write(self.directory, "root-plan", original)
        path = self.directory / "root-plan.md"
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime - 86400))
        before = path.stat().st_mtime

        args = cli.build_parser().parse_args(["set", "root-plan", "--status", "not-started"])
        with _silenced():
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

        both = json.loads(
            self._run_json(["list", "--tag", "auth", "--tag", "security", "--format", "json"])
        )
        self.assertEqual([p["id"] for p in both], ["auth-plan"])

        neither = json.loads(
            self._run_json(["list", "--tag", "auth", "--tag", "billing", "--format", "json"])
        )
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


class CmdGrepProjectLimitTests(unittest.TestCase):
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

    def test_grep_matches_title_case_insensitively(self):
        _write(self.directory, "auth-plan", "# Auth Redesign\n")
        _write(self.directory, "billing-plan", "# Billing\n")
        matched = json.loads(self._run_json(["list", "--grep", "AUTH", "--format", "json"]))
        self.assertEqual([p["id"] for p in matched], ["auth-plan"])

    def test_grep_matches_body(self):
        _write(self.directory, "root-plan", "# Root\n\nMentions authentication deep in the body.\n")
        matched = json.loads(
            self._run_json(["list", "--grep", "authentication", "--format", "json"])
        )
        self.assertEqual([p["id"] for p in matched], ["root-plan"])

    def test_grep_is_a_regex(self):
        _write(self.directory, "root-plan", "# Root\n\nauth-123\n")
        matched = json.loads(self._run_json(["list", "--grep", r"auth-\d+", "--format", "json"]))
        self.assertEqual([p["id"] for p in matched], ["root-plan"])

    def test_invalid_grep_pattern_exits_one_with_re_error_on_stderr(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["list", "--grep", "(unclosed"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = cli.cmd_list(args)
        self.assertEqual(result, 1)
        self.assertTrue(err.getvalue())

    def test_project_dot_resolves_to_the_current_directory_name(self):
        _write(self.directory, "root-plan", "---\nproject: example\n---\n\n# Root\n")
        with mock.patch("pentimento.cli.Path.cwd", return_value=Path("/home/user/src/example")):
            matched = json.loads(self._run_json(["list", "--project", ".", "--format", "json"]))
        self.assertEqual([p["id"] for p in matched], ["root-plan"])

    def test_set_project_dot_writes_the_current_directory_name(self):
        _write(self.directory, "root-plan", "# Root\n")
        with mock.patch("pentimento.cli.Path.cwd", return_value=Path("/home/user/src/example")):
            args = cli.build_parser().parse_args(["set", "root-plan", "--project", "."])
            with _silenced():
                self.assertEqual(cli.cmd_set(args), 0)
        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["project"], "example")

    def test_limit_keeps_the_tail_under_ascending_order(self):
        for name in ("a-plan", "b-plan", "c-plan"):
            _write(self.directory, name, "# Plan\n")
        matched = json.loads(
            self._run_json(
                ["list", "--sort", "id", "--order", "asc", "-n", "2", "--format", "json"]
            )
        )
        self.assertEqual([p["id"] for p in matched], ["b-plan", "c-plan"])

    def test_limit_keeps_the_head_under_descending_order(self):
        for name in ("a-plan", "b-plan", "c-plan"):
            _write(self.directory, name, "# Plan\n")
        matched = json.loads(
            self._run_json(
                ["list", "--sort", "id", "--order", "desc", "-n", "2", "--format", "json"]
            )
        )
        self.assertEqual([p["id"] for p in matched], ["c-plan", "b-plan"])

    def test_limit_applies_before_the_table_footer_count(self):
        for name in ("a-plan", "b-plan", "c-plan"):
            _write(self.directory, name, "# Plan\n")
        out = self._run_json(["list", "--sort", "id", "-n", "2"])
        self.assertIn("2 of 3 plans", out)

    def test_negative_limit_is_rejected_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.build_parser().parse_args(["list", "-n", "-2"])
        self.assertEqual(ctx.exception.code, 2)

    def test_zero_limit_returns_no_rows_under_ascending_order(self):
        for name in ("a-plan", "b-plan", "c-plan"):
            _write(self.directory, name, "# Plan\n")
        matched = json.loads(
            self._run_json(
                ["list", "--sort", "id", "--order", "asc", "-n", "0", "--format", "json"]
            )
        )
        self.assertEqual(matched, [])

    def test_zero_limit_returns_no_rows_under_descending_order(self):
        for name in ("a-plan", "b-plan", "c-plan"):
            _write(self.directory, name, "# Plan\n")
        matched = json.loads(
            self._run_json(
                ["list", "--sort", "id", "--order", "desc", "-n", "0", "--format", "json"]
            )
        )
        self.assertEqual(matched, [])


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
        header = " ".join(_header_block(lines))
        id_index = header.index("id:")
        status_index = header.index("status:")
        intent_index = header.index("intent:")
        project_index = header.index("project:")
        self.assertLess(id_index, status_index)
        self.assertLess(status_index, intent_index)
        self.assertLess(intent_index, project_index)

    def test_id_line_holds_the_plan_id(self):
        _write(self.directory, "root-plan", "# Root\n")
        out = io.StringIO()
        args = cli.build_parser().parse_args(["show", "root-plan"])
        with contextlib.redirect_stdout(out):
            cli.cmd_show(args)
        header = " ".join(_header_block(out.getvalue().splitlines()))
        self.assertIn("id: root-plan", header)

    def test_resolves_a_short_id(self):
        _write(self.directory, "is-it-possible-to-abundant-rabbit", "# Root\n")
        out = io.StringIO()
        args = cli.build_parser().parse_args(["show", "abundant-rabbit"])
        with contextlib.redirect_stdout(out):
            result = cli.cmd_show(args)
        self.assertEqual(result, 0)
        header = " ".join(_header_block(out.getvalue().splitlines()))
        self.assertIn("id: is-it-possible-to-abundant-rabbit", header)

    def test_header_flows_onto_few_lines_at_a_wide_width(self):
        _write(
            self.directory,
            "root-plan",
            "---\nproject: example\nstatus: complete\nintent: active\n---\n\n# Root\n",
        )
        with mock.patch.dict(os.environ, {"COLUMNS": "100"}):
            out = io.StringIO()
            args = cli.build_parser().parse_args(["show", "root-plan"])
            with contextlib.redirect_stdout(out):
                cli.cmd_show(args)
        header = _header_block(out.getvalue().splitlines())
        self.assertLessEqual(len(header), 5)

    def test_header_flows_onto_more_lines_at_a_narrow_width(self):
        _write(
            self.directory,
            "root-plan",
            "---\nproject: example\nstatus: complete\nintent: active\n---\n\n# Root\n",
        )
        with mock.patch.dict(os.environ, {"COLUMNS": "100"}):
            out = io.StringIO()
            args = cli.build_parser().parse_args(["show", "root-plan"])
            with contextlib.redirect_stdout(out):
                cli.cmd_show(args)
        wide_header = _header_block(out.getvalue().splitlines())

        with mock.patch.dict(os.environ, {"COLUMNS": "20"}):
            narrow_out = io.StringIO()
            args = cli.build_parser().parse_args(["show", "root-plan"])
            with contextlib.redirect_stdout(narrow_out):
                cli.cmd_show(args)
        narrow_header = _header_block(narrow_out.getvalue().splitlines())
        self.assertGreater(len(narrow_header), len(wide_header))

    def test_an_over_long_id_gets_its_own_line_intact(self):
        long_id = "a-very-long-plan-id-that-should-never-be-truncated-no-matter-what"
        _write(self.directory, long_id, "# Root\n")
        with mock.patch.dict(os.environ, {"COLUMNS": "20"}):
            out = io.StringIO()
            args = cli.build_parser().parse_args(["show", long_id])
            with contextlib.redirect_stdout(out):
                cli.cmd_show(args)
        header = _header_block(out.getvalue().splitlines())
        id_line = next(line for line in header if line.startswith("id:"))
        self.assertIn(long_id, id_line)
        self.assertNotIn("…", id_line)

    def test_body_sections_beyond_progress_appear(self):
        _write(
            self.directory,
            "root-plan",
            "# Root\n\n## Progress\n\nNot started.\n\n## Context\n\nBackground details go here.\n",
        )
        out = io.StringIO()
        args = cli.build_parser().parse_args(["show", "root-plan"])
        with contextlib.redirect_stdout(out):
            cli.cmd_show(args)
        rendered = out.getvalue()
        self.assertIn("Progress", rendered)
        self.assertIn("Context", rendered)
        self.assertIn("Background details go here.", rendered)

    def test_full_on_a_non_tty_is_a_no_op(self):
        _write(
            self.directory,
            "root-plan",
            "# Root\n\n## Progress\n\nNot started.\n\n## Context\n\nBackground details go here.\n",
        )
        plain = io.StringIO()
        args = cli.build_parser().parse_args(["show", "root-plan"])
        with contextlib.redirect_stdout(plain):
            cli.cmd_show(args)

        full = io.StringIO()
        args = cli.build_parser().parse_args(["show", "root-plan", "--full"])
        with contextlib.redirect_stdout(full):
            cli.cmd_show(args)

        self.assertEqual(plain.getvalue(), full.getvalue())

    def _show_on_a_tty(self, argv, *, height=3, is_tty=True):
        """Run `show` against a fake tty, returning (stdout text, lines handed to the pager)."""
        _write(
            self.directory,
            "root-plan",
            "# Root\n\n## Progress\n\nNot started.\n\n## Context\n\nBackground details go here.\n",
        )
        out = _TtyStream(is_tty)
        args = cli.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(out):
            with mock.patch.object(cli.style, "terminal_height", return_value=height):
                with mock.patch.object(cli.pager, "page") as page:
                    cli.cmd_show(args)
        paged = page.call_args.args[0] if page.called else None
        return out.getvalue(), paged

    def test_full_on_a_tty_pages_a_plan_taller_than_the_terminal(self):
        printed, paged = self._show_on_a_tty(["show", "root-plan", "--full"])
        self.assertEqual(printed, "")
        self.assertIn("Background details go here.", "\n".join(paged))

    def test_full_does_not_page_a_plan_that_fits(self):
        printed, paged = self._show_on_a_tty(["show", "root-plan", "--full"], height=1000)
        self.assertIsNone(paged)
        self.assertIn("Background details go here.", printed)

    def test_no_pager_prints_the_whole_body(self):
        printed, paged = self._show_on_a_tty(["show", "root-plan", "--full", "--no-pager"])
        self.assertIsNone(paged)
        self.assertIn("Background details go here.", printed)

    def test_plain_show_never_pages(self):
        _, paged = self._show_on_a_tty(["show", "root-plan"])
        self.assertIsNone(paged)

    def test_redirected_output_never_pages(self):
        printed, paged = self._show_on_a_tty(["show", "root-plan", "--full"], is_tty=False)
        self.assertIsNone(paged)
        self.assertIn("Background details go here.", printed)

    def test_json_never_pages(self):
        printed, paged = self._show_on_a_tty(["show", "root-plan", "--full", "--format", "json"])
        self.assertIsNone(paged)
        self.assertEqual(json.loads(printed)[0]["id"], "root-plan")

    def test_format_json_output_is_unchanged_by_full(self):
        _write(
            self.directory,
            "root-plan",
            "# Root\n\n## Progress\n\nNot started.\n\n## Context\n\nBackground details go here.\n",
        )
        plain = self._run_json(["show", "root-plan", "--format", "json"])
        full = self._run_json(["show", "root-plan", "--full", "--format", "json"])
        self.assertEqual(plain, full)

    def test_header_groups_share_lines_by_semantic_field(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\nintent: unset\nparent: none\nproject: example\n"
            "created: 2026-09-14\n---\n\n# Root\n",
        )
        with mock.patch.dict(os.environ, {"COLUMNS": "100"}):
            out = io.StringIO()
            args = cli.build_parser().parse_args(["show", "root-plan"])
            with contextlib.redirect_stdout(out):
                cli.cmd_show(args)
        header = _header_block(out.getvalue().splitlines())
        id_line = next(line for line in header if "id:" in line)
        state_line = next(line for line in header if "status:" in line)
        lineage_line = next(line for line in header if "project:" in line)
        provenance_line = next(line for line in header if "created:" in line)
        self.assertNotIn("status:", id_line)
        self.assertIn("intent:", state_line)
        self.assertIn("parent:", lineage_line)
        self.assertIn("source:", provenance_line)
        self.assertIn("modified:", provenance_line)

    def _show_header_lines(self, plan_id, columns):
        with mock.patch.dict(os.environ, {"COLUMNS": columns}):
            out = io.StringIO()
            args = cli.build_parser().parse_args(["show", plan_id])
            with contextlib.redirect_stdout(out):
                cli.cmd_show(args)
        return _header_block(out.getvalue().splitlines())

    def test_path_is_absolute_and_on_its_own_line_after_id(self):
        _write(self.directory, "root-plan", "---\nstatus: complete\n---\n\n# Root\n")
        header = self._show_header_lines("root-plan", "200")
        self.assertEqual(header[0], "id: root-plan")
        self.assertEqual(header[1], f"path: {self.directory / 'root-plan.md'}")

    def test_path_wider_than_the_terminal_is_never_truncated(self):
        _write(self.directory, "root-plan", "---\nstatus: complete\n---\n\n# Root\n")
        expected = f"path: {self.directory / 'root-plan.md'}"
        header = self._show_header_lines("root-plan", "20")
        self.assertIn(expected, header)

    def test_json_path_matches_the_rendered_path(self):
        _write(self.directory, "root-plan", "# Root\n")
        record = json.loads(self._run_json(["show", "root-plan", "--format", "json"]))[0]
        self.assertEqual(record["path"], str(self.directory / "root-plan.md"))

    def test_status_column_is_stable_regardless_of_id_length(self):
        short_id = "short-plan"
        long_id = short_id + "x" * 40
        for plan_id in (short_id, long_id):
            _write(self.directory, plan_id, "---\nstatus: complete\nintent: unset\n---\n\n# Root\n")
        columns = {}
        for plan_id in (short_id, long_id):
            with mock.patch.dict(os.environ, {"COLUMNS": "100"}):
                out = io.StringIO()
                args = cli.build_parser().parse_args(["show", plan_id])
                with contextlib.redirect_stdout(out):
                    cli.cmd_show(args)
            header = _header_block(out.getvalue().splitlines())
            state_line = next(line for line in header if "status:" in line)
            columns[plan_id] = state_line.index("status:")
        self.assertEqual(columns[short_id], columns[long_id])

    def test_unknown_frontmatter_key_lands_on_its_own_trailing_line(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: complete\nintent: unset\nmystery: field\n---\n\n# Root\n",
        )
        with mock.patch.dict(os.environ, {"COLUMNS": "100"}):
            out = io.StringIO()
            args = cli.build_parser().parse_args(["show", "root-plan"])
            with contextlib.redirect_stdout(out):
                cli.cmd_show(args)
        header = _header_block(out.getvalue().splitlines())
        mystery_index = next(i for i, line in enumerate(header) if "mystery:" in line)
        modified_index = next(i for i, line in enumerate(header) if "modified:" in line)
        self.assertGreater(mystery_index, modified_index)
        self.assertNotIn("modified:", header[mystery_index])

    def _run_json(self, argv):
        out = io.StringIO()
        args = cli.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(out):
            cli.cmd_show(args)
        return out.getvalue()


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
        with _silenced():
            self.assertEqual(cli.cmd_check(args), 0)

    def test_dangling_parent_exits_one(self):
        _write(
            self.directory,
            "root-plan",
            "---\nstatus: not-started\nintent: unset\nparent: no-such-plan\n---\n\n# Root\n",
        )
        args = cli.build_parser().parse_args(["check"])
        with _silenced():
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

    def test_unreadable_file_is_reported_and_survives(self):
        _write(self.directory, "ok", "# Ok\n\n## Progress\n- [x] a\n")
        secret = self.directory / "secret.md"
        secret.write_text("# Secret\n")
        secret.chmod(0)
        self.addCleanup(secret.chmod, 0o644)
        out = io.StringIO()
        err = io.StringIO()
        args = cli.build_parser().parse_args(["check"])
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = cli.cmd_check(args)
        self.assertEqual(result, 1)
        self.assertIn("unreadable-file", out.getvalue())
        self.assertIn("secret.md", err.getvalue())


class HostileCorpusTests(unittest.TestCase):
    """A single unreadable/malformed file must not crash the corpus-wide commands."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)
        _write(self.directory, "ok", "# Ok\n\n## Progress\n- [x] a\n")
        (self.directory / "latin1.md").write_bytes(b"# Latin1 \xe9\xe9\n")
        (self.directory / "binary.md").write_bytes(b"\x00\xff binary")
        (self.directory / "dangle.md").symlink_to(self.directory / "nonexistent.md")
        (self.directory / "adir.md").mkdir()
        secret = self.directory / "secret.md"
        secret.write_text("# Secret\n")
        secret.chmod(0)
        self.addCleanup(secret.chmod, 0o644)

    def test_list_survives_and_lists_the_ok_plan(self):
        out = io.StringIO()
        args = cli.build_parser().parse_args(["list", "--color", "never"])
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            result = cli.cmd_list(args)
        self.assertIn(result, (0, 1))
        self.assertIn("ok", out.getvalue())

    def test_tree_survives_and_lists_the_ok_plan(self):
        out = io.StringIO()
        args = cli.build_parser().parse_args(["tree", "--color", "never"])
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            result = cli.cmd_tree(args)
        self.assertIn(result, (0, 1))
        self.assertIn("Ok", out.getvalue())

    def test_check_survives(self):
        args = cli.build_parser().parse_args(["check"])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = cli.cmd_check(args)
        self.assertIn(result, (0, 1))

    def test_index_survives(self):
        args = cli.build_parser().parse_args(["index"])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = cli.cmd_index(args)
        self.assertIn(result, (0, 1))


class MainTopLevelHandlerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_oserror_from_a_command_is_caught_and_reported(self):
        err = io.StringIO()
        with mock.patch.dict(cli.COMMANDS, {"list": mock.Mock(side_effect=OSError("boom"))}):
            with contextlib.redirect_stderr(err):
                result = cli.main(["list"])
        self.assertEqual(result, 1)
        self.assertIn("pentimento: boom", err.getvalue())

    def test_unicodedecodeerror_from_a_command_is_caught_and_reported(self):
        exc = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        err = io.StringIO()
        with mock.patch.dict(cli.COMMANDS, {"list": mock.Mock(side_effect=exc)}):
            with contextlib.redirect_stderr(err):
                result = cli.main(["list"])
        self.assertEqual(result, 1)
        self.assertIn("pentimento:", err.getvalue())


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

    def test_resolves_a_short_id(self):
        _write(self.directory, "is-it-possible-to-abundant-rabbit", "# Root\n")
        out = io.StringIO()
        args = cli.build_parser().parse_args(["history", "abundant-rabbit"])
        with contextlib.redirect_stdout(out):
            result = cli.cmd_history(args)
        self.assertEqual(result, 0)
        self.assertIn("no session history for is-it-possible-to-abundant-rabbit", out.getvalue())


class AmbiguousShortIdTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_ambiguous_short_id_exits_one_with_ambiguity_message(self):
        _write(self.directory, "foo-abundant-rabbit", "# Foo\n")
        _write(self.directory, "bar-abundant-rabbit", "# Bar\n")
        out = io.StringIO()
        args = cli.build_parser().parse_args(["show", "abundant-rabbit"])
        with contextlib.redirect_stderr(out):
            result = cli.cmd_show(args)
        self.assertEqual(result, 1)
        self.assertIn("ambiguous plan id: abundant-rabbit", out.getvalue())
        self.assertIn("foo-abundant-rabbit", out.getvalue())
        self.assertIn("bar-abundant-rabbit", out.getvalue())


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

    def test_only_restricts_writes_to_the_named_id(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        _write(self.directory, "other-plan", "# Other\n\n## Progress\n- [x] done\n")
        args = cli.build_parser().parse_args(["backfill", "--only", "root-plan", "--quiet"])
        self.assertEqual(cli.cmd_backfill(args), 0)

        reloaded = {p.id: p for p in corpus.load_all(self.directory)}
        self.assertEqual(reloaded["root-plan"].fields["status"], "complete")
        self.assertEqual(reloaded["other-plan"].fields, {})


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
        args = cli.build_parser().parse_args(
            ["list", "--status", "not-started", "--color", "never"]
        )
        output = self._run(args)
        self.assertIn("0 of 1 plan", output)

    def test_tree_empty_filter_reports_summary(self):
        _write(self.directory, "root-plan", "---\nstatus: complete\n---\n\n# Root\n")
        args = cli.build_parser().parse_args(
            ["tree", "--status", "not-started", "--color", "never"]
        )
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

    def test_created_sort_uses_the_printed_created_field(self):
        # "recent-plan" is written (and so gets a birthtime) before
        # "glowing-penguin", but its `created` field is the later date -- the
        # sort must follow the field, not the file's own birthtime.
        _write(self.directory, "recent-plan", "---\ncreated: 2026-09-01\n---\n\n# Recent\n")
        _write(self.directory, "glowing-penguin", "---\ncreated: 2026-08-11\n---\n\n# Penguin\n")
        args = cli.build_parser().parse_args(["list", "--sort", "created"])
        plans = corpus.load_all(self.directory)
        ordered = sorted(plans, key=cli._sort_key(args), reverse=cli._sort_descending(args))
        self.assertEqual([p.id for p in ordered], ["glowing-penguin", "recent-plan"])

    def test_created_sort_falls_back_to_created_at_on_a_tie(self):
        _write(self.directory, "first-plan", "---\ncreated: 2026-09-01\n---\n\n# First\n")
        _write(self.directory, "second-plan", "---\ncreated: 2026-09-01\n---\n\n# Second\n")
        args = cli.build_parser().parse_args(["list", "--sort", "created"])
        plans = corpus.load_all(self.directory)
        ordered = sorted(plans, key=cli._sort_key(args), reverse=cli._sort_descending(args))
        self.assertEqual([p.id for p in ordered], ["first-plan", "second-plan"])

    def test_created_sort_does_not_raise_on_missing_or_junk_created(self):
        _write(self.directory, "no-created-field", "# No field\n")
        _write(self.directory, "junk-created", "---\ncreated: not-a-date\n---\n\n# Junk\n")
        args = cli.build_parser().parse_args(["list", "--sort", "created"])
        plans = corpus.load_all(self.directory)
        ordered = sorted(plans, key=cli._sort_key(args), reverse=cli._sort_descending(args))
        self.assertEqual({p.id for p in ordered}, {"no-created-field", "junk-created"})


class VersionTests(unittest.TestCase):
    def test_version_flag_exits_zero(self):
        with _silenced(), self.assertRaises(SystemExit) as ctx:
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
        with _silenced():
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


class CmdHookTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def _run_hook(self, payload: str) -> int:
        with mock.patch.object(sys, "stdin", io.StringIO(payload)), _silenced():
            return cli.cmd_hook(None)

    def test_scoping_leaves_a_second_plan_byte_identical(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        other_text = "# Other\n\n## Progress\n- [x] done\n"
        _write(self.directory, "other-plan", other_text)

        path = self.directory / "root-plan.md"
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        self.assertEqual(self._run_hook(payload), 0)

        self.assertEqual((self.directory / "other-plan.md").read_text(), other_text)
        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["intent"], "unset")

    def test_status_safety_all_checked_progress_stops_at_partial(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        path = self.directory / "root-plan.md"
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        self.assertEqual(self._run_hook(payload), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "partial")

    def test_mixed_box_progress_reaches_partial(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n- [ ] todo\n")
        path = self.directory / "root-plan.md"
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        self.assertEqual(self._run_hook(payload), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields["status"], "partial")

    def test_mtime_preserved_across_the_hook_write(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        path = self.directory / "root-plan.md"
        before = path.stat().st_mtime
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        self.assertEqual(self._run_hook(payload), 0)
        after = path.stat().st_mtime
        self.assertEqual(before, after)

    def test_non_plan_path_exits_zero_writing_nothing(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        path = self.directory / "elsewhere" / "root-plan.md"
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        self.assertEqual(self._run_hook(payload), 0)

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields, {})

    def test_garbage_stdin_exits_zero_writing_nothing(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        self.assertEqual(self._run_hook("garbage"), 0)

    def test_debug_env_prints_traceback_on_crash_but_still_exits_zero(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        path = self.directory / "root-plan.md"
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        with mock.patch.dict(os.environ, {"PENTIMENTO_DEBUG": "1"}):
            with mock.patch(
                "pentimento.cli.sessions_module.load", side_effect=RuntimeError("boom")
            ):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    result = self._run_hook(payload)
        self.assertEqual(result, 0)
        self.assertIn("RuntimeError", err.getvalue())
        self.assertIn("boom", err.getvalue())

    def test_without_debug_env_a_crash_is_silent(self):
        _write(self.directory, "root-plan", "# Root\n\n## Progress\n- [x] done\n")
        path = self.directory / "root-plan.md"
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        with mock.patch.dict(os.environ):
            os.environ.pop("PENTIMENTO_DEBUG", None)
            with mock.patch(
                "pentimento.cli.sessions_module.load", side_effect=RuntimeError("boom")
            ):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    result = self._run_hook(payload)
        self.assertEqual(result, 0)
        self.assertEqual(err.getvalue(), "")

        reloaded = corpus.by_id(corpus.load_all(self.directory, sessions={}), "root-plan")
        self.assertEqual(reloaded.fields, {})


class HelpTextTests(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()
        self.subparsers = _subparsers_action(self.parser).choices

    def test_top_level_has_description_and_epilog(self):
        self.assertTrue(self.parser.description)
        self.assertTrue(self.parser.epilog)

    def test_every_subcommand_has_description_and_help(self):
        action = _subparsers_action(self.parser)
        help_by_name = {choice.dest: choice.help for choice in action._choices_actions}
        for name, subparser in self.subparsers.items():
            self.assertTrue(subparser.description, msg=name)
            self.assertTrue(help_by_name.get(name), msg=name)

    def test_epilog_examples_parse(self):
        for name, subparser in self.subparsers.items():
            if not subparser.epilog:
                continue
            lines = subparser.epilog.splitlines()
            examples = [line.strip() for line in lines if line.strip().startswith("pentimento ")]
            for example in examples:
                tokens = shlex.split(example)[1:]
                if tokens and tokens[0] == name:
                    tokens = tokens[1:]
                try:
                    subparser.parse_args(tokens)
                except SystemExit:
                    self.fail(f"epilog example failed to parse: {example}")

    def test_help_exits_zero_for_top_level_and_every_subcommand(self):
        for argv in [["--help"]] + [[name, "--help"] for name in self.subparsers]:
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
                self.parser.parse_args(argv)
            self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
