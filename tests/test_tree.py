from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from pentimento import tree


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


class RenderTests(unittest.TestCase):
    def test_node_shape_is_title_then_metadata(self):
        root = FakePlan(id="root", title="Root Plan")
        lines = tree.render([root]).split("\n")
        self.assertEqual(lines[0], "`- Root Plan")
        self.assertEqual(lines[1], "     root  not-started  unset")

    def test_two_children_use_branch_and_final_connectors(self):
        root = FakePlan(id="root", title="Root")
        a = FakePlan(id="a", title="A", parent="root")
        b = FakePlan(id="b", title="B", parent="root")
        lines = tree.render([root, a, b]).split("\n")
        self.assertTrue(lines[2].startswith("   +- A"))
        self.assertTrue(lines[4].startswith("   `- B"))

    def test_promoted_root_is_annotated_with_elided_parent(self):
        orphan = FakePlan(id="orphan", title="Orphan", parent="missing-parent")
        lines = tree.render([orphan]).split("\n")
        self.assertIn("(parent elided: missing-parent)", lines[0])

    def test_cycle_is_annotated(self):
        a = FakePlan(id="a", title="A", parent="b")
        b = FakePlan(id="b", title="B", parent="a")
        rendered = tree.render([a, b])
        self.assertIn("(cycle)", rendered)

    def test_render_grouped_headings_are_sorted_with_blank_line_between(self):
        p1 = FakePlan(id="p1", title="P1", project="zeta")
        p2 = FakePlan(id="p2", title="P2", project="alpha")
        rendered = tree.render_grouped([p1, p2])
        self.assertLess(rendered.index("alpha"), rendered.index("zeta"))
        self.assertIn("\n\n", rendered)


class AsRecordsTests(unittest.TestCase):
    def test_children_nest_under_parent(self):
        root = FakePlan(id="root", title="Root")
        child = FakePlan(id="child", title="Child", parent="root")
        records = tree.as_records([root, child])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "root")
        self.assertEqual(len(records[0]["children"]), 1)
        self.assertEqual(records[0]["children"][0]["id"], "child")

    def test_cycle_does_not_recurse_forever(self):
        a = FakePlan(id="a", title="A", parent="b")
        b = FakePlan(id="b", title="B", parent="a")
        records = tree.as_records([a, b])
        self.assertTrue(records)


if __name__ == "__main__":
    unittest.main()
