from __future__ import annotations

import dataclasses
import datetime
import unittest
from unittest import mock

from pentimento import columns, listing, style


@dataclasses.dataclass
class FakePlan:
    id: str
    title: str
    has_title: bool = True
    status: str = "not-started"
    pinned: bool = False
    intent: str = "unset"
    tags: list = dataclasses.field(default_factory=list)
    project: str | None = "example"
    source: str = "claude"
    mtime: float = 0.0
    fields: dict = dataclasses.field(default_factory=dict)
    created_date: datetime.date | None = None
    findings: list = dataclasses.field(default_factory=list)

    @property
    def modified(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.mtime, tz=datetime.timezone.utc)

    @property
    def created(self) -> str | None:
        return self.created_date.isoformat() if self.created_date else None


def _with_width(width, fn):
    with mock.patch("pentimento.style.terminal_width", return_value=width):
        return fn()


class RenderTests(unittest.TestCase):
    def test_header_row_lists_columns(self):
        plans = [FakePlan(id="a", title="Alpha")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertEqual(
            header.split(), ["PLAN", "STATUS", "INTENT", "PROJECT", "SOURCE", "TITLE", "UPDATED"]
        )

    def test_plan_column_holds_the_id(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        self.assertIn("a-plan", record_line)

    def test_plan_column_holds_the_short_id(self):
        plans = [
            FakePlan(id="is-it-possible-to-abundant-rabbit", title="Alpha"),
            FakePlan(id="some-other-plan-id", title="Beta"),
        ]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=False))
        record_line = rendered.split("\n")[1]
        self.assertIn("abundant-rabbit", record_line)
        self.assertNotIn("is-it-possible-to-abundant-rabbit", record_line)

    def test_explicit_short_ids_mapping_is_honoured(self):
        plans = [FakePlan(id="a-plan-id", title="Alpha")]
        rendered = _with_width(
            120, lambda: listing.render(plans, on_color=False, short_ids={"a-plan-id": "custom"})
        )
        record_line = rendered.split("\n")[1]
        self.assertIn("custom", record_line)
        self.assertNotIn("a-plan-id", record_line)

    def test_title_column_holds_the_h1(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        self.assertIn("Alpha", record_line)

    def test_title_column_blank_when_plan_has_no_title(self):
        plans = [FakePlan(id="a-plan", title="a-plan", has_title=False)]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        # STATUS, INTENT, PROJECT, SOURCE, PLAN and UPDATED tokens should
        # appear -- TITLE is blank.
        self.assertEqual(len(record_line.split()), 6)

    def test_relative_age_column_is_rightmost(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        self.assertTrue(record_line.rstrip().endswith("y") or "just now" in record_line)

    def test_status_column_shown_when_uniform(self):
        plans = [FakePlan(id="a", title="Alpha"), FakePlan(id="b", title="Beta")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("STATUS", header)

    def test_status_column_shown_when_mixed(self):
        plans = [
            FakePlan(id="a", title="Alpha", status="complete"),
            FakePlan(id="b", title="Beta", status="not-started"),
        ]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("STATUS", header)

    def test_intent_column_shown_when_uniform(self):
        plans = [FakePlan(id="a", title="Alpha"), FakePlan(id="b", title="Beta")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("INTENT", header)

    def test_intent_column_shown_when_mixed(self):
        plans = [
            FakePlan(id="a", title="Alpha", intent="active"),
            FakePlan(id="b", title="Beta", intent="unset"),
        ]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("INTENT", header)

    def test_project_column_shown_when_uniform(self):
        plans = [FakePlan(id="a", title="Alpha"), FakePlan(id="b", title="Beta")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("PROJECT", header)

    def test_project_column_shown_when_mixed(self):
        plans = [
            FakePlan(id="a", title="Alpha", project="one"),
            FakePlan(id="b", title="Beta", project="two"),
        ]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("PROJECT", header)

    def test_source_column_shown_when_uniform(self):
        plans = [FakePlan(id="a", title="Alpha"), FakePlan(id="b", title="Beta")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertIn("SOURCE", header)

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

    def test_finding_column_shown_when_any_plan_has_findings(self):
        plans = [FakePlan(id="a-plan", title="Alpha", findings=["cycle", "missing-title"])]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=False))
        self.assertIn("FINDING", rendered.split("\n")[0])
        self.assertIn("cycle, missing-title", rendered.split("\n")[1])

    def test_finding_column_omitted_when_no_plan_has_findings(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertNotIn("FINDING", header)

    def test_finding_cell_is_never_truncated(self):
        plans = [FakePlan(id="a-plan", title="Alpha", findings=["underivable-status"])]
        for width in (110, 60, 40, None):
            rendered = _with_width(width, lambda: listing.render(plans, on_color=False))
            self.assertIn("underivable-status", rendered, f"width={width}")

    def test_created_column_shown_when_any_plan_has_it(self):
        plans = [FakePlan(id="a-plan", title="Alpha", created_date=datetime.date(2026, 1, 1))]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=False))
        self.assertIn("CREATED", rendered.split("\n")[0])
        self.assertIn("2026-01-01", rendered.split("\n")[1])

    def test_created_column_omitted_when_absent(self):
        plans = [FakePlan(id="a-plan", title="Alpha")]
        header = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        self.assertNotIn("CREATED", header)

    def test_created_cell_prints_the_derived_date_not_the_raw_field(self):
        plans = [
            FakePlan(
                id="a-plan",
                title="Alpha",
                fields={"created": "not-a-date"},
                created_date=datetime.date(2026, 3, 4),
            )
        ]
        record_line = _with_width(120, lambda: listing.render(plans, on_color=False)).split("\n")[1]
        self.assertIn("2026-03-04", record_line)
        self.assertNotIn("not-a-date", record_line)

    def test_no_ansi_bytes_when_color_off(self):
        plans = [FakePlan(id="a", title="Alpha")]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=False))
        self.assertNotIn("\033", rendered)

    def test_ansi_bytes_present_when_color_on(self):
        plans = [FakePlan(id="a", title="Alpha")]
        rendered = _with_width(120, lambda: listing.render(plans, on_color=True))
        self.assertIn("\033", rendered)


def _is_table(rendered):
    return rendered.startswith("PLAN")


class LayoutTests(unittest.TestCase):
    def _plans(self):
        return [
            FakePlan(
                id="api-auth-redesign",
                title="Redesign the auth API",
                status="complete",
                mtime=1,
                created_date=datetime.date(2026, 1, 1),
            ),
            FakePlan(
                id="api-auth-rollout",
                title="Roll out the new auth API for the whole platform now",
                status="partial",
                intent="active",
                tags=["auth", "billing", "platform", "security"],
                project="platform",
                mtime=2,
                created_date=datetime.date(2026, 1, 2),
            ),
            FakePlan(
                id="billing-invoice-retry",
                title="Retry failed invoice charges",
                status="unknown",
                project="billing",
                source="cursor",
                mtime=3,
                created_date=datetime.date(2026, 1, 3),
            ),
        ]

    def _render(self, width):
        return _with_width(width, lambda: listing.render(self._plans(), on_color=False))

    def _fixed_cells(self):
        return ["invoice-retry", "auth-redesign", "cursor", "complete", "2026-01-03"]

    def test_the_layout_switches_once_from_stacked_to_table(self):
        kinds = [_is_table(self._render(width)) for width in range(20, 201)]
        self.assertEqual(kinds, sorted(kinds))
        self.assertFalse(kinds[0])
        self.assertTrue(kinds[-1])

    def test_the_threshold_is_the_floors_plus_gutters(self):
        header = self._render(None).split("\n")[0]
        starts = [header.index(h) for h in ("TITLE", "TAGS", "CREATED", "UPDATED")]
        title_natural = starts[1] - starts[0] - style.GUTTER
        tags_natural = starts[2] - starts[1] - style.GUTTER
        floors_saved = (title_natural - 30) + (tags_natural - 10)
        threshold = style.display_width(header) - floors_saved
        self.assertTrue(_is_table(self._render(threshold)))
        self.assertFalse(_is_table(self._render(threshold - 1)))

    def test_every_width_keeps_every_fixed_cell_whole(self):
        for width in (40, 60, 110, 140, None):
            rendered = self._render(width)
            for cell in self._fixed_cells():
                self.assertIn(cell, rendered, f"width={width}")

    def test_table_rows_are_one_physical_line_each(self):
        for width in (140, 200, None):
            rendered = self._render(width)
            self.assertTrue(_is_table(rendered), f"width={width}")
            self.assertEqual(len(rendered.split("\n")), 1 + len(self._plans()), f"width={width}")

    def test_tags_shorten_to_whole_tags_and_a_count(self):
        header = self._render(None).split("\n")[0]
        rendered = self._render(style.display_width(header) - 25)
        self.assertTrue(_is_table(rendered))
        self.assertIn("[auth, billing, platform, +1]", rendered)

    def test_unbounded_output_is_never_shortened(self):
        rendered = self._render(None)
        self.assertIn("Roll out the new auth API for the whole platform now", rendered)
        self.assertIn("[auth, billing, platform, security]", rendered)

    def test_stacked_records_keep_every_field_and_bracket_the_tags(self):
        rendered = self._render(60)
        self.assertFalse(_is_table(rendered))
        self.assertIn("[auth, billing, platform, security]", rendered)
        self.assertNotIn("PLAN", rendered)

    def test_no_stacked_line_exceeds_the_width(self):
        for width in range(30, 100):
            for line in self._render(width).split("\n"):
                self.assertLessEqual(style.display_width(line), width, f"width={width}: {line!r}")


class ColumnSelectionTests(unittest.TestCase):
    def _plans(self):
        return [
            FakePlan(
                id="api-auth-redesign",
                title="Redesign the auth API",
                status="complete",
                mtime=1,
                created_date=datetime.date(2026, 1, 1),
            ),
            FakePlan(
                id="api-auth-rollout",
                title="Roll out the new auth API",
                status="partial",
                mtime=2,
                created_date=datetime.date(2026, 1, 2),
            ),
        ]

    def test_absolute_selection_renders_in_the_given_order(self):
        selection = columns.parse("created,title,status", listing.NAMES)
        header = _with_width(
            120, lambda: listing.render(self._plans(), on_color=False, selection=selection)
        ).split("\n")[0]
        self.assertEqual(header.split(), ["CREATED", "TITLE", "STATUS"])

    def test_relative_selection_keeps_the_default_order(self):
        selection = columns.parse("-status", listing.NAMES)
        header = _with_width(
            120, lambda: listing.render(self._plans(), on_color=False, selection=selection)
        ).split("\n")[0]
        self.assertEqual(
            header.split(), ["PLAN", "INTENT", "PROJECT", "SOURCE", "TITLE", "CREATED", "UPDATED"]
        )

    def test_a_short_selection_stays_a_table_where_the_full_set_stacks(self):
        selection = columns.parse("id,status,title,modified", listing.NAMES)
        narrow = _with_width(60, lambda: listing.render(self._plans(), on_color=False))
        chosen = _with_width(
            60, lambda: listing.render(self._plans(), on_color=False, selection=selection)
        )
        self.assertFalse(narrow.startswith("PLAN"))
        self.assertEqual(chosen.split("\n")[0].split(), ["PLAN", "STATUS", "TITLE", "UPDATED"])


if __name__ == "__main__":
    unittest.main()
