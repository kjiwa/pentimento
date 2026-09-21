import contextlib
import io
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pentimento import pager


def _env(**overrides):
    """Replace the environment with `overrides`, so the developer's own PAGER never leaks in."""
    return mock.patch.dict(os.environ, overrides, clear=True)


class CommandTests(unittest.TestCase):
    def test_unset_defaults_to_less(self):
        with _env():
            self.assertEqual(pager.command(), ["less"])

    def test_value_is_split_with_shell_quoting(self):
        with _env(PAGER="less -S"):
            self.assertEqual(pager.command(), ["less", "-S"])
        with _env(PAGER="'my pager' --flag"):
            self.assertEqual(pager.command(), ["my pager", "--flag"])

    def test_empty_disables_paging(self):
        with _env(PAGER=""):
            self.assertIsNone(pager.command())

    def test_unparseable_disables_paging(self):
        with _env(PAGER="less 'unterminated"):
            self.assertIsNone(pager.command())


class EnvironmentTests(unittest.TestCase):
    def test_less_gets_default_flags_when_less_is_unset(self):
        with _env():
            self.assertEqual(pager._environment(["less"])["LESS"], "FRX")

    def test_less_is_matched_by_basename(self):
        with _env():
            self.assertEqual(pager._environment(["/usr/bin/less", "-S"])["LESS"], "FRX")

    def test_operators_less_variable_is_kept(self):
        with _env(LESS="-i"):
            self.assertEqual(pager._environment(["less"])["LESS"], "-i")

    def test_other_pagers_get_no_less_variable(self):
        with _env():
            self.assertNotIn("LESS", pager._environment(["more"]))


class PageTests(unittest.TestCase):
    def _print_output(self, lines):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pager.page(lines)
        return out.getvalue()

    def test_lines_reach_the_pagers_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "captured"
            with _env(PAGER=f"sh -c 'cat > \"$0\"' {shlex.quote(str(target))}"):
                pager.page(["one", "two"])
            self.assertEqual(target.read_text(), "one\ntwo\n")

    def test_missing_binary_falls_back_to_printing(self):
        with _env(PAGER="no-such-pager-binary"):
            self.assertEqual(self._print_output(["one", "two"]), "one\ntwo\n")

    def test_disabled_pager_prints(self):
        with _env(PAGER=""):
            self.assertEqual(self._print_output(["one"]), "one\n")

    def _mock_proc(self):
        proc = mock.MagicMock()
        proc.stdin.__exit__.return_value = False
        return proc

    def test_broken_pipe_is_swallowed(self):
        proc = self._mock_proc()
        proc.stdin.write.side_effect = BrokenPipeError
        with _env(PAGER="less"), mock.patch.object(pager.subprocess, "Popen", return_value=proc):
            pager.page(["one"])
        proc.wait.assert_called_once()

    def test_ctrl_c_keeps_waiting_for_the_pager(self):
        proc = self._mock_proc()
        proc.wait.side_effect = [KeyboardInterrupt, 0]
        with _env(PAGER="less"), mock.patch.object(pager.subprocess, "Popen", return_value=proc):
            pager.page(["one"])
        self.assertEqual(proc.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
