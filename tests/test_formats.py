from __future__ import annotations

import dataclasses
import datetime
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
    pinned: bool = False
    intent: str = "unset"
    tags: list = dataclasses.field(default_factory=list)
    parent: str | None = None
    project: str | None = "example"
    source: str = "claude"
    path: Path = Path("fake.md")
    started: str = "2026-01-01T00:00:00.000Z"
    mtime: float = 0.0
    fields: dict = dataclasses.field(default_factory=dict)
    findings: list = dataclasses.field(default_factory=list)
    created: str | None = None

    @property
    def modified(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.mtime, tz=datetime.timezone.utc)


def _emit(records, fmt, columns=()) -> str:
    stream = io.StringIO()
    formats.emit(records, fmt, stream, columns)
    return stream.getvalue()


class ChoicesTests(unittest.TestCase):
    def test_choices_contains_table_plus_every_format(self):
        self.assertIn(formats.TABLE, formats.CHOICES)
        for key in formats.FORMATS:
            self.assertIn(key, formats.CHOICES)


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
        rendered = _emit([record.as_dict(plan)], "tsv", record.FIELDS)
        lines = rendered.rstrip("\n").split("\n")
        header = lines[0].split("\t")
        row = lines[1].split("\t")
        self.assertEqual(len(header), len(row))
        self.assertEqual(header, list(record.FIELDS))

    def test_embedded_tab_in_title_is_sanitized(self):
        plan = FakePlan(id="a", title="Alpha\tBeta")
        rendered = _emit([record.as_dict(plan)], "tsv", record.FIELDS)
        lines = rendered.rstrip("\n").split("\n")
        row = lines[1].split("\t")
        title_index = list(record.FIELDS).index("title")
        self.assertEqual(row[title_index], "Alpha Beta")

    def test_scalar_list_is_comma_joined(self):
        plan = FakePlan(id="a", title="Alpha", tags=["auth", "security"])
        rendered = _emit([record.as_dict(plan)], "tsv", record.FIELDS)
        lines = rendered.rstrip("\n").split("\n")
        row = lines[1].split("\t")
        tags_index = list(record.FIELDS).index("tags")
        self.assertEqual(row[tags_index], "auth,security")

    def test_empty_records_still_emit_header_for_explicit_columns(self):
        rendered = _emit([], "tsv", record.FIELDS)
        self.assertEqual(rendered, "\t".join(record.FIELDS) + "\n")

    def test_no_columns_emits_nothing(self):
        self.assertEqual(_emit([], "tsv"), "")

    def test_columns_follow_the_explicit_argument_not_the_first_record(self):
        findings = [{"plan_id": "a", "code": "self-parent", "message": "a: parent is itself"}]
        rendered = _emit(findings, "tsv", ("plan_id", "code", "message"))
        lines = rendered.rstrip("\n").split("\n")
        self.assertEqual(lines[0].split("\t"), ["plan_id", "code", "message"])
        self.assertEqual(lines[1].split("\t"), ["a", "self-parent", "a: parent is itself"])

    def test_tree_records_drop_children_column(self):
        root = FakePlan(id="root", title="Root")
        child = FakePlan(id="child", title="Child", parent="root")
        records = tree.as_records([root, child])
        rendered = _emit(records, "tsv", record.FIELDS)
        header = rendered.split("\n", 1)[0].split("\t")
        self.assertNotIn("children", header)
        self.assertIn("id", header)


class TsvScrubTests(unittest.TestCase):
    def test_tab_and_newline_inside_a_list_item_do_not_add_fields(self):
        rendered = _emit([{"tags": ["a\tb", "c\nd", "e\rf"]}], "tsv", ("tags",))
        row = rendered.split("\n")[1]
        self.assertEqual(row, "a b,c d,e f")

    def test_carriage_return_in_a_scalar_is_scrubbed(self):
        rendered = _emit([{"title": "a\rb"}], "tsv", ("title",))
        self.assertEqual(rendered.split("\n")[1], "a b")

    def test_booleans_print_lowercase(self):
        rendered = _emit([{"pinned": True}, {"pinned": False}], "tsv", ("pinned",))
        self.assertEqual(rendered.split("\n")[1:3], ["true", "false"])


class RecordTimestampTests(unittest.TestCase):
    def test_created_is_the_plans_created_value(self):
        plan = FakePlan(id="p", title="P", created="2026-01-01")
        self.assertEqual(record.as_dict(plan)["created"], "2026-01-01")

    def test_findings_are_carried_as_a_list(self):
        plan = FakePlan(id="p", title="P", findings=["cycle", "missing-title"])
        self.assertEqual(record.as_dict(plan)["findings"], ["cycle", "missing-title"])

    def test_findings_join_with_commas_in_tsv(self):
        plan = FakePlan(id="p", title="P", findings=["cycle", "missing-title"])
        rendered = _emit([record.as_dict(plan)], "tsv", ("findings",))
        self.assertEqual(rendered.split("\n")[1], "cycle,missing-title")

    def test_modified_and_started_are_utc_whole_seconds(self):
        plan = FakePlan(
            id="p", title="P", mtime=1_800_000_000.5, started="2026-01-01T00:00:00.123Z"
        )
        rec = record.as_dict(plan)
        self.assertEqual(rec["modified"], "2027-01-15T08:00:00Z")
        self.assertEqual(rec["started"], "2026-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
