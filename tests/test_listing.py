from __future__ import annotations

import dataclasses
import unittest

from pentimento import listing


@dataclasses.dataclass
class FakePlan:
    id: str
    title: str
    status: str = "not-started"
    intent: str = "unset"
    project: str | None = "example"


class RenderTests(unittest.TestCase):
    def test_header_row_lists_columns(self):
        plans = [FakePlan(id="a", title="Alpha")]
        lines = listing.render(plans, on_color=False).split("\n")
        self.assertEqual(lines[0].split(), ["STATUS", "INTENT", "PLAN"])

    def test_continuation_line_holds_the_id(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        lines = listing.render(plans, on_color=False).split("\n")
        self.assertEqual(lines[2].strip(), "a-plan")

    def test_continuation_indent_matches_plan_column(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        lines = listing.render(plans, on_color=False).split("\n")
        record_line = lines[1]
        continuation_line = lines[2]
        plan_column_start = record_line.index("Alpha")
        indent = len(continuation_line) - len(continuation_line.lstrip(" "))
        self.assertEqual(indent, plan_column_start)

    def test_project_column_dropped_when_uniform(self):
        plans = [FakePlan(id="a", title="Alpha"), FakePlan(id="b", title="Beta")]
        header = listing.render(plans, on_color=False).split("\n")[0]
        self.assertNotIn("PROJECT", header)

    def test_project_column_shown_when_mixed(self):
        plans = [
            FakePlan(id="a", title="Alpha", project="one"),
            FakePlan(id="b", title="Beta", project="two"),
        ]
        header = listing.render(plans, on_color=False).split("\n")[0]
        self.assertIn("PROJECT", header)

    def test_no_ansi_bytes_when_color_off(self):
        plans = [FakePlan(id="a", title="Alpha")]
        rendered = listing.render(plans, on_color=False)
        self.assertNotIn("\033", rendered)

    def test_ansi_bytes_present_when_color_on(self):
        plans = [FakePlan(id="a", title="Alpha")]
        rendered = listing.render(plans, on_color=True)
        self.assertIn("\033", rendered)


if __name__ == "__main__":
    unittest.main()
