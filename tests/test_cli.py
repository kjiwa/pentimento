import os
import tempfile
import unittest
from pathlib import Path

from pentimento import cli, corpus


def _write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.md").write_text(text)


class CmdSetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

        previous = os.environ.get("AGENT_PLANS_DIR")
        os.environ["AGENT_PLANS_DIR"] = str(self.directory)
        self.addCleanup(_restore_env, "AGENT_PLANS_DIR", previous)

        previous_sessions = os.environ.get("AGENT_SESSIONS_DIR")
        os.environ["AGENT_SESSIONS_DIR"] = str(self.directory / "no-such-sessions-dir")
        self.addCleanup(_restore_env, "AGENT_SESSIONS_DIR", previous_sessions)

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

        previous = os.environ.get("AGENT_PLANS_DIR")
        os.environ["AGENT_PLANS_DIR"] = str(self.directory)
        self.addCleanup(_restore_env, "AGENT_PLANS_DIR", previous)

        previous_sessions = os.environ.get("AGENT_SESSIONS_DIR")
        os.environ["AGENT_SESSIONS_DIR"] = str(self.directory / "no-such-sessions-dir")
        self.addCleanup(_restore_env, "AGENT_SESSIONS_DIR", previous_sessions)

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

        previous = os.environ.get("AGENT_PLANS_DIR")
        os.environ["AGENT_PLANS_DIR"] = str(self.directory)
        self.addCleanup(_restore_env, "AGENT_PLANS_DIR", previous)

        previous_sessions = os.environ.get("AGENT_SESSIONS_DIR")
        os.environ["AGENT_SESSIONS_DIR"] = str(self.directory / "no-such-sessions-dir")
        self.addCleanup(_restore_env, "AGENT_SESSIONS_DIR", previous_sessions)

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


def _restore_env(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


if __name__ == "__main__":
    unittest.main()
