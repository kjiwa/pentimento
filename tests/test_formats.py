from __future__ import annotations

import dataclasses
import io
import json
import unittest
from pathlib import Path

from pentimento import formats, record, tree


@dataclasses.dataclass
class FakePlan:
    id: str
    title: str
    status: str = "not-started"
    intent: str = "unset"
    parent: str | None = None
    project: str | None = "example"
    path: Path = Path("fake.md")
    started: str = "2026-01-01T00:00:00.000Z"
    fields: dict = dataclasses.field(default_factory=dict)


def _emit(records, fmt) -> str:
    stream = io.StringIO()
    formats.emit(records, fmt, stream)
    return stream.getvalue()


class JsonTests(unittest.TestCase):
    def test_field_set_matches_record_as_dict(self):
        plan = FakePlan(id="a", title="Alpha")
        rendered = _emit([record.as_dict(plan)], "json")
        parsed = json.loads(rendered)
        self.assertEqual(set(parsed[0].keys()), set(record.as_dict(plan).keys()))

    def test_trailing_newline(self):
        plan = FakePlan(id="a", title="Alpha")
        rendered = _emit([record.as_dict(plan)], "json")
        self.assertTrue(rendered.endswith("\n"))

    def test_tree_nests_children(self):
        root = FakePlan(id="root", title="Root")
        child = FakePlan(id="child", title="Child", parent="root")
        records = tree.as_records([root, child])
        rendered = _emit(records, "json")
        parsed = json.loads(rendered)
        self.assertEqual(len(parsed[0]["children"]), 1)
        self.assertEqual(parsed[0]["children"][0]["id"], "child")


class TsvTests(unittest.TestCase):
    def test_header_and_column_count(self):
        plan = FakePlan(id="a", title="Alpha")
        rendered = _emit([record.as_dict(plan)], "tsv")
        lines = rendered.rstrip("\n").split("\n")
        header = lines[0].split("\t")
        row = lines[1].split("\t")
        self.assertEqual(len(header), len(row))
        self.assertEqual(header, list(record.as_dict(plan).keys()))

    def test_embedded_tab_in_title_is_sanitized(self):
        plan = FakePlan(id="a", title="Alpha\tBeta")
        rendered = _emit([record.as_dict(plan)], "tsv")
        lines = rendered.rstrip("\n").split("\n")
        row = lines[1].split("\t")
        title_index = list(record.as_dict(plan).keys()).index("title")
        self.assertEqual(row[title_index], "Alpha Beta")

    def test_empty_records_emit_no_header(self):
        self.assertEqual(_emit([], "tsv"), "")

    def test_columns_follow_record_shape_not_plan_fields(self):
        findings = [{"plan_id": "a", "code": "self-parent", "message": "a: parent is itself"}]
        rendered = _emit(findings, "tsv")
        lines = rendered.rstrip("\n").split("\n")
        self.assertEqual(lines[0].split("\t"), ["plan_id", "code", "message"])
        self.assertEqual(lines[1].split("\t"), ["a", "self-parent", "a: parent is itself"])

    def test_tree_records_drop_children_column(self):
        root = FakePlan(id="root", title="Root")
        child = FakePlan(id="child", title="Child", parent="root")
        records = tree.as_records([root, child])
        rendered = _emit(records, "tsv")
        header = rendered.split("\n", 1)[0].split("\t")
        self.assertNotIn("children", header)
        self.assertIn("id", header)


if __name__ == "__main__":
    unittest.main()
