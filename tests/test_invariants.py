"""Properties that hold across every command, checked over the demo fixture corpus."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pentimento import cli, frontmatter

ROOT = Path(__file__).parent.parent
HISTORY_PLAN = "api-auth-cleanup"


def _run(argv) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        cli.main(argv)
    return out.getvalue()


def _tsv(argv) -> tuple[list[str], list[list[str]]]:
    lines = _run([*argv, "--format", "tsv"]).splitlines()
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


def _json(argv):
    return json.loads(_run([*argv, "--format", "json"]))


def _count_nodes(nodes) -> int:
    return sum(1 + _count_nodes(node["children"]) for node in nodes)


class FixtureCorpusTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.directory = Path(cls._tmp.name) / "plans"
        subprocess.run(["sh", str(ROOT / "demo" / "fixture.sh"), str(cls.directory)], check=True)
        env = mock.patch.dict(
            os.environ,
            {
                "AGENT_PLANS_DIR": str(cls.directory),
                "AGENT_SESSIONS_DIR": str(cls.directory / "sessions"),
                "CURSOR_PLANS_DIR": str(cls.directory / "no-such-cursor-plans-dir"),
                "XDG_CACHE_HOME": str(Path(cls._tmp.name) / "cache"),
            },
        )
        env.start()
        cls.addClassCleanup(env.stop)


class RoundTripTests(FixtureCorpusTestCase):
    def test_serializing_a_parsed_plan_reproduces_the_file(self):
        paths = sorted(self.directory.glob("*.md"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(plan=path.name):
                text = path.read_text(newline="")
                fields, body, extras = frontmatter.parse(text)
                self.assertEqual(frontmatter.serialize(fields, body, extras), text)


class ProjectionTests(FixtureCorpusTestCase):
    def test_list_json_keys_and_rows_match_tsv(self):
        records = _json(["list"])
        header, rows = _tsv(["list"])
        self.assertTrue(records)
        self.assertEqual(header, list(records[0]))
        self.assertEqual(len(rows), len(records))

    def test_tree_json_keys_and_rows_match_tsv(self):
        nodes = _json(["tree"])
        header, rows = _tsv(["tree"])
        self.assertEqual(header, [key for key in nodes[0] if key != "children"])
        self.assertEqual(len(rows), _count_nodes(nodes))
        self.assertEqual(len(rows), len(_json(["list"])))

    def test_tree_tsv_rows_keep_parents_before_children(self):
        header, rows = _tsv(["tree"])
        id_at, parent_at = header.index("id"), header.index("parent")
        position = {row[id_at]: index for index, row in enumerate(rows)}
        for index, row in enumerate(rows):
            parent = row[parent_at]
            if parent in position:
                with self.subTest(plan=row[id_at]):
                    self.assertLess(position[parent], index)

    def test_check_json_keys_and_rows_match_tsv(self):
        records = _json(["check"])
        header, rows = _tsv(["check"])
        self.assertTrue(records)
        self.assertEqual(header, list(records[0]))
        self.assertEqual(len(rows), len(records))

    def test_history_json_keys_and_rows_match_tsv(self):
        records = _json(["history", HISTORY_PLAN])
        header, rows = _tsv(["history", HISTORY_PLAN])
        self.assertTrue(records)
        self.assertEqual(header, list(records[0]))
        self.assertEqual(len(rows), len(records))

    def test_show_json_keys_and_rows_match_tsv(self):
        records = _json(["show", HISTORY_PLAN])
        header, rows = _tsv(["show", HISTORY_PLAN])
        self.assertEqual(header, list(records[0]))
        self.assertEqual(len(rows), len(records))


if __name__ == "__main__":
    unittest.main()
