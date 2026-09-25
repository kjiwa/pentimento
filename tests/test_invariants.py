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

from pentimento import cli, corpus, frontmatter

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
                "CURSOR_SESSIONS_DIR": str(cls.directory / "no-such-cursor-sessions-dir"),
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
                with path.open(encoding="utf-8", newline="") as handle:
                    text = handle.read()
                fields, body, extras = frontmatter.parse(text)
                self.assertEqual(frontmatter.serialize(fields, body, extras), text)


def _mirror(nodes) -> list:
    """Sibling order reversed at every level: what `asc` becomes under `desc`."""
    return [{"id": n["id"], "children": _mirror(n["children"])} for n in reversed(nodes)]


def _shape(nodes) -> list:
    return [{"id": n["id"], "children": _shape(n["children"])} for n in nodes]


class OrderTests(FixtureCorpusTestCase):
    def test_desc_is_asc_reversed_for_every_sort_key(self):
        for key in cli.SORT_CHOICES:
            with self.subTest(command="list", sort=key):
                asc = [r["id"] for r in _json(["list", "--sort", key])]
                desc = [r["id"] for r in _json(["list", "--sort", key, "--order", "desc"])]
                self.assertEqual(desc, asc[::-1])

    def test_tree_desc_mirrors_asc_for_every_sort_key(self):
        for key in cli.SORT_CHOICES:
            with self.subTest(command="tree", sort=key):
                asc = _shape(_json(["tree", "--sort", key]))
                desc = _shape(_json(["tree", "--sort", key, "--order", "desc"]))
                self.assertEqual(desc, _mirror(asc))

    def test_flattened_tree_desc_visits_the_same_plans_as_list_desc(self):
        for key in cli.SORT_CHOICES:
            with self.subTest(sort=key):
                _, rows = _tsv(["tree", "--sort", key, "--order", "desc"])
                self.assertEqual(
                    sorted(row[0] for row in rows),
                    sorted(r["id"] for r in _json(["list", "--sort", key, "--order", "desc"])),
                )


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


WIDTHS = (40, 60, 80, 110)


def _run_at(width: int, argv) -> str:
    with mock.patch.dict(os.environ, {"COLUMNS": str(width)}):
        return _run(argv if argv[0] == "set" else [*argv, "--color", "never"])


def _help_at(width: int, argv) -> str:
    with mock.patch.dict(os.environ, {"COLUMNS": str(width)}):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            with contextlib.suppress(SystemExit):
                cli.main([*argv, "--help"])
        return out.getvalue()


def _is_exempt(line: str, in_usage: bool, in_examples: bool) -> bool:
    """Lines that cannot narrow: one unbreakable token; argparse usage lines,
    which it aligns under the program name; Examples, kept verbatim to stay
    copy-pasteable."""
    return len(line.split()) <= 1 or in_usage or in_examples


def _overwide(text: str, width: int, *, help_text: bool = False) -> list[str]:
    lines = text.splitlines()
    examples_at = next((i for i, line in enumerate(lines) if line == "Examples:"), len(lines))
    usage_end = lines.index("") if help_text and "" in lines else 0
    return [
        line
        for index, line in enumerate(lines)
        if len(line) > width
        and not _is_exempt(line, index < usage_end, help_text and index > examples_at)
    ]


class WidthTests(FixtureCorpusTestCase):
    COMMANDS = (
        ["list"],
        ["list", "--columns", "all"],
        ["tree"],
        ["check"],
        ["history", HISTORY_PLAN],
        ["show", HISTORY_PLAN],
        ["set", HISTORY_PLAN, "--intent", "active", "--dry-run"],
    )
    HELPS = (
        [],
        *([name] for name in ("list", "tree", "show", "set", "backfill", "hook")),
        *([name] for name in ("index", "check", "history", "completion")),
    )

    def test_no_output_line_is_wider_than_the_terminal(self):
        for width in WIDTHS:
            for argv in self.COMMANDS:
                with self.subTest(width=width, argv=argv):
                    self.assertEqual(_overwide(_run_at(width, argv), width), [])

    def test_no_help_line_is_wider_than_the_terminal(self):
        for width in WIDTHS:
            for argv in self.HELPS:
                with self.subTest(width=width, argv=argv):
                    self.assertEqual(_overwide(_help_at(width, argv), width, help_text=True), [])


class IdentityTests(FixtureCorpusTestCase):
    def setUp(self):
        self.plans = corpus.load_all()

    def assert_resolves(self, shown: str, expected: str):
        found = corpus.by_id(self.plans, shown)
        self.assertIsNotNone(found, shown)
        self.assertEqual(found.id, expected)

    def test_every_list_row_id_resolves_to_its_plan(self):
        lines = _run_at(200, ["list", "--columns", "id,title"]).splitlines()
        for record in _json(["list"]):
            row = next(line for line in lines if record["title"] in line)
            with self.subTest(plan=record["id"]):
                self.assert_resolves(row.split()[0], record["id"])

    def test_every_tree_row_id_resolves_to_its_plan(self):
        lines = _run_at(200, ["tree"]).splitlines()
        for record in _json(["list"]):
            at = next(i for i, line in enumerate(lines) if line.endswith(record["title"]))
            with self.subTest(plan=record["id"]):
                self.assert_resolves(lines[at + 1].replace("|", " ").split()[0], record["id"])

    def test_every_check_row_id_resolves_to_its_plan(self):
        lines = _run_at(200, ["check"]).splitlines()[1:]
        records = _json(["check"])
        for line, record in zip(lines, records):
            with self.subTest(plan=record["id"], code=record["code"]):
                self.assert_resolves(line.split()[1], record["id"])


if __name__ == "__main__":
    unittest.main()
