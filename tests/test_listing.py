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
            header.split(), ["STATUS", "INTENT", "PROJECT", "SOURCE", "PLAN", "TITLE", "UPDATED"]
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

    def test_finding_column_drops_last_and_truncates_before_dropping(self):
        plans = [FakePlan(id="a-plan", title="Alpha", findings=["underivable-status"])]
        for width in (60, 40):
            lines = _with_width(width, lambda: listing.render(plans, on_color=False)).split("\n")
            self.assertIn("FINDING", lines[0])
            self.assertTrue(all(len(line) <= width for line in lines))

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


class FitGuaranteeTests(unittest.TestCase):
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
                intent="active",
                tags=["auth", "security"],
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

    def test_every_line_fits_every_width(self):
        for width in range(20, 201):
            rendered = _with_width(width, lambda: listing.render(self._plans(), on_color=False))
            for line in rendered.split("\n"):
                self.assertLessEqual(
                    style.display_width(line), width, f"width={width} overflowed: {line!r}"
                )

    def test_plan_column_is_never_truncated_at_any_width_where_it_is_present(self):
        plans = self._plans()
        for width in range(20, 201):
            header = _with_width(width, lambda: listing.render(plans, on_color=False)).split("\n")[
                0
            ]
            if "PLAN" not in header:
                continue
            rendered = _with_width(width, lambda: listing.render(plans, on_color=False))
            plan_column_start = header.index("PLAN")
            for line in rendered.split("\n")[1:]:
                cell = line[plan_column_start:].split("  ")[0]
                self.assertNotIn("…", cell, f"width={width} truncated PLAN: {line!r}")

    def test_no_column_is_stretched_at_a_wide_width(self):
        rendered = _with_width(200, lambda: listing.render(self._plans(), on_color=False))
        header = rendered.split("\n")[0]
        self.assertLess(style.display_width(header), 150)

    def test_drop_order_fires_in_sequence(self):
        plans = self._plans()
        wide_header = _with_width(200, lambda: listing.render(plans, on_color=False)).split("\n")[0]
        for column in (
            "STATUS",
            "INTENT",
            "PROJECT",
            "SOURCE",
            "PLAN",
            "TITLE",
            "TAGS",
            "CREATED",
            "UPDATED",
        ):
            self.assertIn(column, wide_header)

        narrow_header = _with_width(60, lambda: listing.render(plans, on_color=False)).split("\n")[
            0
        ]
        self.assertNotIn("CREATED", narrow_header)
        self.assertNotIn("TAGS", narrow_header)
        self.assertIn("PLAN", narrow_header)  # the only addressable handle on a row -- drops last

        narrower_header = _with_width(40, lambda: listing.render(plans, on_color=False)).split(
            "\n"
        )[0]
        self.assertIn("TITLE", narrower_header)
        self.assertNotIn("PLAN", narrower_header)


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

    def test_explicit_column_survives_a_width_that_would_otherwise_drop_it(self):
        plans = self._plans()
        without_selection = _with_width(90, lambda: listing.render(plans, on_color=False)).split(
            "\n"
        )[0]
        self.assertNotIn("CREATED", without_selection)

        spec = ",".join(name for name in listing.NAMES if name != "finding")
        selection = columns.parse(spec, listing.NAMES)
        header = _with_width(
            90, lambda: listing.render(plans, on_color=False, selection=selection)
        ).split("\n")[0]
        self.assertIn("CREATED", header)

    def test_sort_key_pins_its_column_without_an_explicit_selection(self):
        header = _with_width(
            90, lambda: listing.render(self._plans(), on_color=False, pin=("created",))
        ).split("\n")[0]
        self.assertIn("CREATED", header)

    def test_absolute_selection_beats_the_sort_pin(self):
        selection = columns.parse("title", listing.NAMES)
        header = _with_width(
            120,
            lambda: listing.render(
                self._plans(), on_color=False, selection=selection, pin=("created",)
            ),
        ).split("\n")[0]
        self.assertEqual(header.split(), ["TITLE"])


if __name__ == "__main__":
    unittest.main()
