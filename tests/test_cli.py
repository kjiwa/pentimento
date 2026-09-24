import contextlib
import datetime
import io
import json
import os
import shlex
import subprocess
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


def _main(argv):
    """`cli.main(argv)` as `(exit code, stdout, stderr)`, including argparse's `SystemExit`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def _fake_stdout(flush_error=None):
    """A stdout stand-in on fd 99, with `os.dup2` captured so the real fd survives."""
    fake = mock.Mock()
    fake.fileno.return_value = 99
    fake.flush.side_effect = flush_error
    with mock.patch.object(cli.sys, "stdout", fake), mock.patch.object(cli.os, "dup2") as dup2:
        yield dup2


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


class CmdTreeLineageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def _run(self, argv):
        out = io.StringIO()
        args = cli.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(out):
            result = cli.COMMANDS[args.command](args)
        return result, out.getvalue()

    def _write_thread(self):
        _write(self.directory, "root", "---\nproject: p\n---\n\n# Root\n")
        _write(self.directory, "child", "---\nproject: p\nparent: root\n---\n\n# Child\n")
        _write(
            self.directory,
            "untagged-child",
            "---\nproject: p\nparent: root\n---\n\n# Untagged Child\n",
        )
        _write(self.directory, "unrelated", "---\nproject: p\n---\n\n# Unrelated\n")

    def test_tree_id_renders_the_subtree_and_omits_unrelated_plans(self):
        self._write_thread()
        _, output = self._run(["tree", "root", "--color", "never"])
        self.assertIn("Root", output)
        self.assertIn("Child", output)
        self.assertNotIn("Unrelated", output)

    def test_tree_id_keeps_untagged_subplan_that_tag_would_drop(self):
        _write(self.directory, "root", "---\nproject: p\ntags: [publish]\n---\n\n# Root\n")
        _write(
            self.directory,
            "untagged-child",
            "---\nproject: p\nparent: root\n---\n\n# Untagged Child\n",
        )
        _, output = self._run(["tree", "root", "--color", "never"])
        self.assertIn("Untagged Child", output)

    def test_tree_accepts_a_short_id(self):
        _write(self.directory, "is-it-possible-to-abundant-rabbit", "---\nproject: p\n---\n\n# R\n")
        _, output = self._run(["tree", "abundant-rabbit", "--color", "never"])
        self.assertIn("R", output)

    def test_ancestors_includes_the_spine_and_excludes_spine_siblings(self):
        _write(self.directory, "grandparent", "---\nproject: p\n---\n\n# Grandparent\n")
        _write(
            self.directory,
            "gp-sibling",
            "---\nproject: p\nparent: grandparent\n---\n\n# GP Sibling\n",
        )
        _write(
            self.directory,
            "parent",
            "---\nproject: p\nparent: grandparent\n---\n\n# Parent\n",
        )
        _write(self.directory, "target", "---\nproject: p\nparent: parent\n---\n\n# Target\n")
        _, output = self._run(["tree", "target", "--ancestors", "--color", "never"])
        self.assertIn("Grandparent", output)
        self.assertIn("Parent", output)
        self.assertIn("Target", output)
        self.assertNotIn("GP Sibling", output)

    def test_annotates_parent_elided_on_the_cut_parent(self):
        self._write_thread()
        _, output = self._run(["tree", "child", "--color", "never"])
        self.assertIn("(parent elided: root)", output)

    def test_status_filter_applies_within_the_selection(self):
        _write(self.directory, "root", "---\nproject: p\nstatus: not-started\n---\n\n# Root\n")
        _write(
            self.directory,
            "child",
            "---\nproject: p\nparent: root\nstatus: partial\n---\n\n# Child\n",
        )
        _, output = self._run(["tree", "root", "--status", "partial", "--color", "never"])
        self.assertNotIn("Root\n", output)
        self.assertIn("Child", output)

    def test_ancestors_without_id_is_a_usage_error(self):
        code, _, err = _main(["tree", "--ancestors"])
        self.assertEqual(code, 2)
        self.assertIn("pentimento: --ancestors requires a plan id", err)

    def test_post_parse_usage_error_shows_the_subcommands_usage(self):
        _, _, err = _main(["tree", "--ancestors"])
        self.assertIn("usage: pentimento tree", err)

    def test_no_such_plan_exits_one_with_suggestion(self):
        _write(self.directory, "root-plan", "# Root\n")
        args = cli.build_parser().parse_args(["tree", "nope-nope"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = cli.cmd_tree(args)
        self.assertEqual(result, 1)
        self.assertIn("no such plan", err.getvalue())

    def test_ambiguous_short_id_exits_one(self):
        _write(self.directory, "foo-abundant-rabbit", "# Foo\n")
        _write(self.directory, "bar-abundant-rabbit", "# Bar\n")
        args = cli.build_parser().parse_args(["tree", "abundant-rabbit"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = cli.cmd_tree(args)
        self.assertEqual(result, 1)
        self.assertIn("ambiguous plan id", err.getvalue())

    def test_json_format_nests_only_the_selected_plans(self):
        self._write_thread()
        _, output = self._run(["tree", "root", "--format", "json"])
        records = json.loads(output)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "root")
        child_ids = {c["id"] for c in records[0]["children"]}
        self.assertEqual(child_ids, {"child", "untagged-child"})

    def test_footer_reports_selected_of_corpus_not_selected_of_selected(self):
        self._write_thread()
        _, output = self._run(["tree", "root", "--color", "never"])
        self.assertIn("3 of 4 plans", output.splitlines()[-1])


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

    def test_invalid_grep_pattern_is_a_usage_error(self):
        _write(self.directory, "root-plan", "# Root\n")
        code, _, err = _main(["list", "--grep", "(unclosed"])
        self.assertEqual(code, 2)
        self.assertIn("pentimento: argument --grep: invalid regex", err)

    def test_title_matches_case_insensitively(self):
        _write(self.directory, "auth-plan", "# Auth Redesign\n")
        _write(self.directory, "billing-plan", "# Billing\n")
        matched = json.loads(self._run_json(["list", "--title", "AUTH", "--format", "json"]))
        self.assertEqual([p["id"] for p in matched], ["auth-plan"])

    def test_title_does_not_match_body_only_text(self):
        _write(self.directory, "root-plan", "# Root\n\nMentions authentication.\n")
        matched = json.loads(
            self._run_json(["list", "--title", "authentication", "--format", "json"])
        )
        self.assertEqual(matched, [])

    def test_title_ands_with_other_filters(self):
        _write(self.directory, "one", "---\nstatus: complete\n---\n\n# Auth one\n")
        _write(self.directory, "two", "---\nstatus: partial\n---\n\n# Auth two\n")
        matched = json.loads(
            self._run_json(["list", "--title", "auth", "--status", "partial", "--format", "json"])
        )
        self.assertEqual([p["id"] for p in matched], ["two"])

    def test_invalid_title_pattern_is_a_usage_error(self):
        code, _, err = _main(["list", "--title", "(unclosed"])
        self.assertEqual(code, 2)
        self.assertIn("pentimento: argument --title: invalid regex", err)

    def test_empty_project_filter_matches_nothing(self):
        _write(self.directory, "root-plan", "---\nproject: example\n---\n\n# Root\n")
        matched = json.loads(self._run_json(["list", "--project", "", "--format", "json"]))
        self.assertEqual(matched, [])

    def test_non_integer_limit_has_a_plain_message(self):
        code, _, err = _main(["list", "-n", "abc"])
        self.assertEqual(code, 2)
        self.assertIn("not an integer: abc", err)
        self.assertNotIn("_non_negative_int", err)

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

    def test_path_under_home_is_collapsed_to_a_tilde(self):
        _write(self.directory, "root-plan", "# Root\n")
        with mock.patch("pentimento.cli.Path.home", return_value=self.directory):
            header = self._show_header_lines("root-plan", "200")
        self.assertEqual(header[1], "path: ~/root-plan.md")

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
        self.assertEqual(result, 2)
        self.assertIn("pentimento: boom", err.getvalue())

    def test_unicodedecodeerror_from_a_command_is_caught_and_reported(self):
        exc = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        err = io.StringIO()
        with mock.patch.dict(cli.COMMANDS, {"list": mock.Mock(side_effect=exc)}):
            with contextlib.redirect_stderr(err):
                result = cli.main(["list"])
        self.assertEqual(result, 2)
        self.assertIn("pentimento:", err.getvalue())

    def test_value_error_from_a_command_exits_two(self):
        err = io.StringIO()
        with mock.patch.dict(cli.COMMANDS, {"list": mock.Mock(side_effect=ValueError("bad"))}):
            with contextlib.redirect_stderr(err):
                result = cli.main(["list"])
        self.assertEqual(result, 2)
        self.assertIn("pentimento: bad", err.getvalue())

    def test_broken_pipe_exits_141_and_repoints_stdout(self):
        with mock.patch.dict(cli.COMMANDS, {"list": mock.Mock(side_effect=BrokenPipeError())}):
            with _fake_stdout() as dup2:
                result = cli.main(["list"])
        self.assertEqual(result, 141)
        self.assertEqual(dup2.call_args.args[1], 99)

    def test_broken_pipe_on_the_final_flush_is_caught(self):
        with mock.patch.dict(cli.COMMANDS, {"list": mock.Mock(return_value=0)}):
            with _fake_stdout(flush_error=BrokenPipeError()):
                self.assertEqual(cli.main(["list"]), 141)

    def test_broken_pipe_covers_the_completion_branch(self):
        with mock.patch.object(cli.completion, "complete", side_effect=BrokenPipeError()):
            with _fake_stdout():
                self.assertEqual(cli.main(["__complete", "list", ""]), 141)

    def test_closed_pipe_leaves_stderr_quiet_end_to_end(self):
        _write(self.directory, "root-plan", "# Root\n")
        repo = Path(cli.__file__).resolve().parent.parent
        proc = subprocess.Popen(
            [sys.executable, "-m", "pentimento", "list", "--format", "json"],
            cwd=repo,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.stdout.close()
        _, stderr = proc.communicate()
        self.assertEqual(proc.returncode, 141)
        self.assertEqual(stderr, b"")


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

    def test_check_prints_one_hint_per_code_after_the_summary(self):
        body = (
            "---\nparent: nope\nstatus: partial\n---\n\n# {}\n\n"
            "## Progress\n- [ ] todo\n- [x] done\n"
        )
        _write(self.directory, "dangler", body.format("D"))
        _write(self.directory, "dangler-two", body.format("D2"))
        args = cli.build_parser().parse_args(["check", "--color", "never"])
        lines = self._run(args).splitlines()
        summary = next(i for i, line in enumerate(lines) if "plans checked" in line)
        self.assertEqual(lines[summary - 1], "")
        self.assertEqual(len(lines) - summary - 1, 1)
        self.assertTrue(lines[summary + 1].startswith("dangling-parent: "))

    def test_check_keeps_the_code_column_at_width_80(self):
        _write(self.directory, "dangler", "---\nparent: nope\n---\n\n# D\n")
        args = cli.build_parser().parse_args(["check", "--color", "never"])
        with mock.patch.dict(os.environ, {"COLUMNS": "80"}):
            output = self._run(args)
        self.assertIn("CODE", output.splitlines()[0])

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


class CmdListColumnsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)
        previous = os.environ.pop("PENTIMENTO_COLUMNS", None)
        self.addCleanup(_restore_env, "PENTIMENTO_COLUMNS", previous)

    def _run(self, argv):
        out = io.StringIO()
        args = cli.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(out):
            result = cli.cmd_list(args)
        return result, out.getvalue()

    def test_columns_flag_selects_and_orders_columns(self):
        _write(self.directory, "root-plan", "# Root\n")
        _, output = self._run(["list", "--columns", "title,status", "--color", "never"])
        self.assertEqual(output.splitlines()[0].split(), ["TITLE", "STATUS"])

    def test_invalid_columns_value_is_rejected_by_argparse(self):
        with self.assertRaises(SystemExit):
            with _silenced(), contextlib.redirect_stderr(io.StringIO()):
                cli.build_parser().parse_args(["list", "--columns", "bogus"])

    def test_columns_flag_with_json_format_is_a_usage_error(self):
        code, _, err = _main(["list", "--columns", "title", "--format", "json"])
        self.assertEqual(code, 2)
        self.assertIn("pentimento: --columns only applies", err)

    def test_columns_accept_record_field_names(self):
        _write(self.directory, "root-plan", "# Root\n")
        _, output = self._run(["list", "--columns", "id,modified", "--color", "never"])
        self.assertEqual(output.splitlines()[0].split(), ["PLAN", "UPDATED"])

    def test_columns_reject_the_old_display_names(self):
        code, _, err = _main(["list", "--columns", "updated"])
        self.assertEqual(code, 2)
        self.assertIn("unknown column: updated", err)

    def test_bare_plus_reports_a_missing_name(self):
        code, _, err = _main(["list", "--columns", "+"])
        self.assertEqual(code, 2)
        self.assertIn("missing column name", err)

    def test_env_var_supplies_the_default_when_flag_is_absent(self):
        _write(self.directory, "root-plan", "# Root\n")
        os.environ["PENTIMENTO_COLUMNS"] = "title,status"
        _, output = self._run(["list", "--color", "never"])
        self.assertEqual(output.splitlines()[0].split(), ["TITLE", "STATUS"])

    def test_explicit_flag_overrides_the_env_var(self):
        _write(self.directory, "root-plan", "# Root\n")
        os.environ["PENTIMENTO_COLUMNS"] = "title"
        _, output = self._run(["list", "--columns", "status", "--color", "never"])
        self.assertEqual(output.splitlines()[0].split(), ["STATUS"])

    def test_bad_env_var_message_and_exit_code_on_stderr(self):
        _write(self.directory, "root-plan", "# Root\n")
        os.environ["PENTIMENTO_COLUMNS"] = "bogus"
        code, _, err = _main(["list"])
        self.assertEqual(code, 2)
        self.assertIn("pentimento: PENTIMENTO_COLUMNS:", err)

    def test_env_var_ignored_for_json_format(self):
        _write(self.directory, "root-plan", "# Root\n")
        os.environ["PENTIMENTO_COLUMNS"] = "bogus"
        result, output = self._run(["list", "--format", "json"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output)[0]["id"], "root-plan")

    def test_sort_created_pins_the_created_column(self):
        _write(self.directory, "root-plan", "---\ncreated: 2026-01-01\n---\n\n# Root\n")
        _, output = self._run(["list", "--sort", "created", "--color", "never"])
        self.assertIn("CREATED", output.splitlines()[0])


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


class DateFilterTests(unittest.TestCase):
    """Three plans whose created and modified days diverge, with "now" fixed at 2026-09-23."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)
        previous = os.environ.get("PENTIMENTO_NOW")
        os.environ["PENTIMENTO_NOW"] = "2026-09-23T12:00:00Z"
        self.addCleanup(_restore_env, "PENTIMENTO_NOW", previous)
        for name, created, modified in (
            ("plan-a", "2026-09-01", "2026-09-02"),
            ("plan-b", "2026-09-10", "2026-09-20"),
            ("plan-c", "2026-09-20", "2026-09-22"),
        ):
            _write(self.directory, name, f"---\ncreated: {created}\n---\n\n# {name}\n")
            stamp = datetime.datetime.fromisoformat(f"{modified}T12:00:00+00:00").timestamp()
            os.utime(self.directory / f"{name}.md", (stamp, stamp))

    def _ids(self, argv):
        code, out, err = _main(["list", "--format", "json", *argv])
        self.assertEqual(code, 0, msg=err)
        return {p["id"] for p in json.loads(out)}

    def test_iso_range_is_inclusive_at_both_ends(self):
        self.assertEqual(
            self._ids(["--since", "2026-09-02", "--until", "2026-09-20"]), {"plan-a", "plan-b"}
        )

    def test_since_alone(self):
        self.assertEqual(self._ids(["--since", "2026-09-21"]), {"plan-c"})

    def test_until_alone(self):
        self.assertEqual(self._ids(["--until", "2026-09-02"]), {"plan-a"})

    def test_age_form_counts_back_from_now(self):
        self.assertEqual(self._ids(["--since", "3d"]), {"plan-b", "plan-c"})

    def test_week_age_form(self):
        self.assertEqual(self._ids(["--since", "1w"]), {"plan-b", "plan-c"})

    def test_date_created_diverges_from_modified(self):
        window = ["--since", "2026-09-10", "--until", "2026-09-19"]
        self.assertEqual(self._ids([*window, "--date", "created"]), {"plan-b"})
        self.assertEqual(self._ids([*window, "--date", "modified"]), set())

    def test_tree_takes_the_same_filters(self):
        code, out, _ = _main(["tree", "--format", "json", "--since", "3d"])
        self.assertEqual(code, 0)
        self.assertEqual({r["id"] for r in json.loads(out)}, {"plan-b", "plan-c"})

    def test_inverted_range_is_a_usage_error(self):
        code, _, err = _main(["list", "--since", "2026-09-20", "--until", "2026-09-02"])
        self.assertEqual(code, 2)
        self.assertIn("pentimento: --since 2026-09-20 is after --until 2026-09-02", err)

    def test_invalid_value_names_both_forms(self):
        code, _, err = _main(["list", "--since", "yesterday"])
        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM-DD", err)
        self.assertIn("3d", err)

    def test_date_without_a_bound_is_a_usage_error(self):
        code, _, err = _main(["list", "--date", "created"])
        self.assertEqual(code, 2)
        self.assertIn("--date needs --since or --until", err)


class UsageErrorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)
        _write(self.directory, "root-plan", "# Root\n")
        _write(self.directory, "other-plan", "# Other\n")

    def test_set_conflicting_flags_are_rejected(self):
        for flags in (
            ["--parent", "other-plan", "--clear-parent"],
            ["--project", "x", "--clear-project"],
            ["--status", "complete", "--unpin"],
            ["--clear-tags", "--add-tag", "auth"],
            ["--clear-tags", "--remove-tag", "auth"],
        ):
            code, _, err = _main(["set", "root-plan", *flags])
            self.assertEqual(code, 2, msg=flags)
            self.assertIn("pentimento:", err)

    def test_set_without_a_field_flag_is_a_usage_error(self):
        code, _, err = _main(["set", "root-plan"])
        self.assertEqual(code, 2)
        self.assertIn("nothing to set", err)

    def test_set_dry_run_alone_is_still_nothing_to_set(self):
        code, _, _ = _main(["set", "root-plan", "--dry-run"])
        self.assertEqual(code, 2)

    def test_unknown_plan_still_exits_one_with_the_prefix(self):
        code, _, err = _main(["show", "no-such-plan"])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("pentimento: no such plan"))

    def test_tree_of_an_unknown_plan_exits_one(self):
        self.assertEqual(_main(["tree", "no-such-plan"])[0], 1)

    def test_check_findings_still_exit_one(self):
        _write(self.directory, "dangler", "---\nparent: nope\n---\n\n# D\n")
        self.assertEqual(_main(["check"])[0], 1)


class MachineFormatTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)

    def test_tsv_prints_pinned_as_lowercase_boolean(self):
        _write(self.directory, "pinned-plan", "---\nstatus: complete\npinned: true\n---\n\n# P\n")
        _write(self.directory, "loose-plan", "# L\n")
        _, out, _ = _main(["list", "--format", "tsv"])
        rows = [line.split("\t") for line in out.splitlines()]
        pinned_at = rows[0].index("pinned")
        self.assertEqual({r[pinned_at] for r in rows[1:]}, {"true", "false"})

    def test_json_timestamps_are_utc_whole_seconds(self):
        _write(self.directory, "root-plan", "---\ncreated: 2026-09-01\n---\n\n# Root\n")
        record = json.loads(_main(["list", "--format", "json"])[1])[0]
        self.assertRegex(record["modified"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertRegex(record["started"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(record["created"], "2026-09-01")

    def test_show_json_and_tsv_include_the_body(self):
        _write(self.directory, "root-plan", "# Root\n\nthe body text\n")
        record = json.loads(_main(["show", "root-plan", "--format", "json"])[1])[0]
        self.assertIn("the body text", record["body"])
        header, row = _main(["show", "root-plan", "--format", "tsv"])[1].splitlines()[:2]
        self.assertEqual(header.split("\t")[-1], "body")
        self.assertIn("the body text", row)

    def test_check_records_use_id_in_table_column_order(self):
        _write(self.directory, "dangler", "---\nparent: nope\n---\n\n# D\n")
        _, out, _ = _main(["check", "--format", "json"])
        record = json.loads(out)[0]
        self.assertEqual(list(record), ["code", "id", "message", "hint"])
        self.assertEqual(record["id"], "dangler")
        self.assertIn("pentimento set", record["hint"])
        header = _main(["check", "--format", "tsv"])[1].splitlines()[0]
        self.assertEqual(header, "code\tid\tmessage\thint")

    def test_check_on_an_empty_corpus_prints_the_list_hint(self):
        empty = self.directory / "no-such-plans-dir"
        os.environ["AGENT_PLANS_DIR"] = str(empty)
        _, _, err = _main(["check"])
        self.assertIn("pentimento: no plans found; searched:", err)

    def test_empty_corpus_hint_carries_the_prefix(self):
        os.environ["AGENT_PLANS_DIR"] = str(self.directory / "no-such-plans-dir")
        _, _, err = _main(["list"])
        self.assertTrue(err.startswith("pentimento: no plans found"))


class BackfillOnlyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)
        _write(self.directory, "what-s-left-to-do-federated-tower", "# Tower\n")
        _write(self.directory, "other-plan", "# Other\n")

    def test_only_resolves_short_ids_filenames_and_paths(self):
        full = "what-s-left-to-do-federated-tower"
        for value in (
            "federated-tower",
            f"{full}.md",
            str(self.directory / f"{full}.md"),
            full,
        ):
            code, out, _ = _main(["backfill", "--dry-run", "--only", value])
            self.assertEqual(code, 0, msg=value)
            self.assertIn("1 plan would change", out, msg=value)
            self.assertIn(full, out, msg=value)
            self.assertNotIn("other-plan", out, msg=value)

    def test_only_with_an_unknown_value_reports_no_such_plan(self):
        code, _, err = _main(["backfill", "--only", "no-such-plan"])
        self.assertEqual(code, 1)
        self.assertIn("pentimento: no such plan: no-such-plan", err)

    def test_dry_run_lists_field_changes_under_each_id(self):
        code, out, _ = _main(["backfill", "--dry-run", "--only", "other-plan"])
        lines = out.splitlines()
        self.assertEqual(lines[0], "other-plan")
        self.assertIn("  status: set to 'unknown'", lines)
        self.assertTrue(any(line.startswith("  intent: set to") for line in lines))

    def test_real_run_lists_field_changes_and_quiet_suppresses_them(self):
        _, out, _ = _main(["backfill", "--only", "other-plan"])
        self.assertIn("  status: set to 'unknown'", out.splitlines())
        _write(self.directory, "quiet-plan", "# Q\n")
        _, out, _ = _main(["backfill", "--quiet", "--only", "quiet-plan"])
        self.assertEqual(out, "")

    def test_rederive_preview_shows_the_old_and_new_value(self):
        _write(
            self.directory,
            "done-plan",
            "---\nstatus: not-started\n---\n\n# Done\n\n## Progress\n- [x] all\n",
        )
        _, out, _ = _main(["backfill", "--dry-run", "--rederive", "--only", "done-plan"])
        self.assertIn("  status: 'not-started' -> 'complete'", out.splitlines())


class TreeCycleRootTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)
        _write(self.directory, "loop-a", "---\nproject: p\nparent: loop-b\n---\n\n# Loop A\n")
        _write(self.directory, "loop-b", "---\nproject: p\nparent: loop-a\n---\n\n# Loop B\n")

    def test_requested_plan_roots_its_cycle(self):
        for target in ("loop-a", "loop-b"):
            _, out, _ = _main(["tree", target, "--format", "json"])
            self.assertEqual([r["id"] for r in json.loads(out)], [target])

    def test_ancestors_on_a_cycle_does_not_repeat_plans(self):
        _, out, _ = _main(["tree", "loop-b", "--ancestors", "--color", "never"])
        self.assertEqual(out.splitlines()[-1], "2 plans")


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
