from __future__ import annotations

import dataclasses
import datetime
import unittest
from unittest import mock

from pentimento import listing, style


@dataclasses.dataclass
class FakePlan:
    id: str
    title: str
    has_title: bool = True
    status: str = "not-started"
    intent: str = "unset"
    tags: list = dataclasses.field(default_factory=list)
    project: str | None = "example"
    source: str = "claude"
    mtime: float = 0.0
    fields: dict = dataclasses.field(default_factory=dict)

    @property
    def modified(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.mtime, tz=datetime.timezone.utc)


def _with_width(width, fn):
    with mock.patch("pentimento.style.terminal_width", return_value=width):
        return fn()


class RenderTests(unittest.TestCase):
    def test_header_row_lists_columns(self):
        plans = [FakePlan(id="a", title="Alpha")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertEqual(header.split(), ["STATUS", "INTENT", "PLAN", "TITLE", "UPDATED"])

    def test_plan_column_holds_the_id(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        self.assertIn("a-plan", record_line)

    def test_title_column_holds_the_h1(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        self.assertIn("Alpha", record_line)

    def test_title_column_blank_when_plan_has_no_title(self):
        plans = [FakePlan(id="a-plan", title="a-plan", has_title=False)]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        # Only STATUS, INTENT, PLAN, and UPDATED tokens should appear -- TITLE is blank.
        self.assertEqual(len(record_line.split()), 4)

    def test_relative_age_column_is_rightmost(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        self.assertTrue(record_line.rstrip().endswith("y") or "just now" in record_line)

    def test_project_column_dropped_when_uniform(self):
        plans = [FakePlan(id="a", title="Alpha"), FakePlan(id="b", title="Beta")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertNotIn("PROJECT", header)

    def test_project_column_shown_when_mixed(self):
        plans = [
            FakePlan(id="a", title="Alpha", project="one"),
            FakePlan(id="b", title="Beta", project="two"),
        ]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("PROJECT", header)

    def test_source_column_dropped_when_uniform(self):
        plans = [FakePlan(id="a", title="Alpha"), FakePlan(id="b", title="Beta")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertNotIn("SOURCE", header)

    def test_source_column_shown_when_mixed(self):
        plans = [
            FakePlan(id="a", title="Alpha", source="claude"),
            FakePlan(id="b", title="Beta", source="cursor"),
        ]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("SOURCE", header)

    def test_tags_column_shown_when_any_plan_has_tags(self):
        plans = [FakePlan(id="a-plan", title="Alpha", tags=["auth", "security"])]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=False))
        self.assertIn("TAGS", rendered.split("\n")[0])
        self.assertIn("auth, security", rendered.split("\n")[1])

    def test_tags_column_omitted_when_absent(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertNotIn("TAGS", header)

    def test_created_column_shown_when_any_plan_has_it(self):
        plans = [FakePlan(id="a-plan", title="Alpha", fields={"created": "2026-01-01"})]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=False))
        self.assertIn("CREATED", rendered.split("\n")[0])
        self.assertIn("2026-01-01", rendered.split("\n")[1])

    def test_created_column_omitted_when_absent(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertNotIn("CREATED", header)

    def test_no_ansi_bytes_when_color_off(self):
        plans = [FakePlan(id="a", title="Alpha")]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=False))
        self.assertNotIn("\033", rendered)

    def test_ansi_bytes_present_when_color_on(self):
        plans = [FakePlan(id="a", title="Alpha")]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=True))
        self.assertIn("\033", rendered)


class FitGuaranteeTests(unittest.TestCase):
    def _plans(self):
        return [
            FakePlan(
                id="api-auth-redesign", title="Redesign the auth API", status="complete", mtime=1,
                fields={"created": "2026-01-01"},
            ),
            FakePlan(
                id="api-auth-rollout",
                title="Roll out the new auth API",
                status="partial",
                intent="active",
                tags=["auth", "security"],
                project="platform",
                mtime=2,
                fields={"created": "2026-01-02"},
            ),
            FakePlan(
                id="billing-invoice-retry",
                title="Retry failed invoice charges",
                status="unknown",
                project="billing",
                source="cursor",
                mtime=3,
                fields={"created": "2026-01-03"},
            ),
        ]

    def test_every_line_fits_every_width(self):
        for width in range(20, 201):
            rendered = _with_width(width, lambda: listing.render(self._plans(), on_color=False))
            for line in rendered.split("\n"):
                self.assertLessEqual(
                    style.display_width(line), width, f"width={width} overflowed: {line!r}"
                )

    def test_no_column_is_stretched_at_a_wide_width(self):
        rendered = _with_width(200, lambda: listing.render(self._plans(), on_color=False))
        header = rendered.split("\n")[0]
        self.assertLess(style.display_width(header), 150)

    def test_drop_order_fires_in_sequence(self):
        plans = self._plans()
        wide_header = _with_width(200, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        for column in ("STATUS", "INTENT", "PROJECT", "SOURCE", "PLAN", "TITLE", "TAGS", "CREATED", "UPDATED"):
            self.assertIn(column, wide_header)

        narrow_header = _with_width(60, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertNotIn("CREATED", narrow_header)
        self.assertNotIn("TAGS", narrow_header)

        narrower_header = _with_width(40, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("TITLE", narrower_header)
        self.assertNotIn("PLAN", narrower_header)


if __name__ == "__main__":
    unittest.main()
