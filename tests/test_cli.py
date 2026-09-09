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


def _restore_env(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


if __name__ == "__main__":
    unittest.main()
