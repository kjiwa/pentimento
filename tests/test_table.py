from __future__ import annotations

import unittest

from pentimento import style, table

WIDTHS = (40, 60, 110, 140, None)

COLUMNS = (
    table.Column("PLAN"),
    table.Column("STATUS"),
    table.Column("TITLE", fit=table.TRUNCATE, floor=30),
    table.Column("UPDATED", align="right"),
)
ROWS = [
    (
        ("api-auth-redesign", ()),
        ("complete", ()),
        ("Redesign the auth API for the whole platform", ()),
        ("5w", ()),
    ),
    (
        ("api-auth-rollout", ()),
        ("partial", ()),
        ("Roll out the new auth API", ()),
        ("just now", ()),
    ),
]
FIXED_CELLS = ("api-auth-redesign", "complete", "5w", "api-auth-rollout", "partial", "just now")
# 17 + 8 + 30 + 8 (widest UPDATED cell) + 3 gutters
TABLE_THRESHOLD = 17 + 8 + 30 + 8 + 3 * style.GUTTER


def _render(columns, rows, width):
    return table.render(columns, rows, on_color=False, width=width)


class PaddingTests(unittest.TestCase):
    def test_wide_characters_pad_by_display_width(self):
        columns = (table.Column("NAME"), table.Column("N", align="right"))
        rows = [(("\u65e5\u672c", ()), ("1", ())), (("abcd", ()), ("2", ()))]
        lines = table.render(columns, rows, on_color=False, width=None).split("\n")
        self.assertEqual([style.display_width(line) for line in lines[1:]], [4 + 2 + 1] * 2)
        self.assertEqual(lines[1], "\u65e5\u672c  1")


class NaturalWidthTests(unittest.TestCase):
    def test_no_trailing_whitespace_and_no_padding_to_width(self):
        rendered = _render(COLUMNS, ROWS, 200)
        for line in rendered.split("\n"):
            self.assertEqual(line, line.rstrip())
            self.assertLess(style.display_width(line), 200)

    def test_unbounded_width_never_truncates(self):
        rendered = _render(COLUMNS, ROWS, None)
        self.assertIn("Redesign the auth API for the whole platform", rendered)
        self.assertTrue(rendered.startswith("PLAN"))


class LayoutSwitchTests(unittest.TestCase):
    def test_table_at_the_threshold_and_stacked_one_below(self):
        at = _render(COLUMNS, ROWS, TABLE_THRESHOLD)
        below = _render(COLUMNS, ROWS, TABLE_THRESHOLD - 1)
        self.assertTrue(at.startswith("PLAN"))
        self.assertFalse(below.startswith("PLAN"))
        self.assertNotIn("PLAN", below)

    def test_table_titles_truncate_to_the_remaining_width(self):
        rendered = _render(COLUMNS, ROWS, TABLE_THRESHOLD)
        self.assertIn("Redesign the auth API for t...", rendered)

    def test_every_width_keeps_every_fixed_cell_whole(self):
        for width in WIDTHS:
            rendered = _render(COLUMNS, ROWS, width)
            for cell in FIXED_CELLS:
                self.assertIn(cell, rendered, f"width={width}")

    def test_table_rows_are_one_physical_line_each(self):
        for width in (TABLE_THRESHOLD, 140, None):
            lines = _render(COLUMNS, ROWS, width).split("\n")
            self.assertEqual(len(lines), 1 + len(ROWS), f"width={width}")

    def test_no_line_exceeds_the_width_at_or_above_the_widest_field(self):
        for width in range(40, 200):
            for line in _render(COLUMNS, ROWS, width).split("\n"):
                self.assertLessEqual(style.display_width(line), width, f"width={width}: {line!r}")


class StackedTests(unittest.TestCase):
    def test_headline_first_then_remaining_cells_in_column_order(self):
        rendered = _render(COLUMNS, ROWS, 40)
        self.assertEqual(
            rendered.split("\n")[:2],
            ["Redesign the auth API for the whole p...", "  api-auth-redesign  complete  5w"],
        )

    def test_empty_cells_are_omitted(self):
        rows = [(("p", ()), ("", ()), ("A title", ()), ("1h", ()))]
        self.assertEqual(_render(COLUMNS, rows, 10), "A title\n  p  1h")

    def test_fields_wrap_between_cells(self):
        lines = _render(COLUMNS, ROWS, 25).split("\n")
        self.assertEqual(lines[1:3], ["  api-auth-redesign", "  complete  5w"])

    def test_a_field_wider_than_the_width_hard_wraps(self):
        lines = _render(COLUMNS, ROWS, 12).split("\n")
        self.assertEqual(lines[1:3], ["  api-auth-r", "  edesign"])

    def test_no_header_line(self):
        self.assertNotIn("STATUS", _render(COLUMNS, ROWS, 40))


class ComfortTests(unittest.TestCase):
    COLUMNS = (
        table.Column("A", fit=table.TRUNCATE, floor=5, comfort=12),
        table.Column("B", fit=table.TRUNCATE, floor=5, comfort=8),
    )
    ROWS = [(("a" * 30, ()), ("b" * 30, ()))]

    def _widths(self, width):
        line = _render(self.COLUMNS, self.ROWS, width).split("\n")[1]
        first, second = line.split("  ")
        return len(first), len(second)

    def test_floors_first(self):
        self.assertEqual(self._widths(12), (5, 5))

    def test_widest_comfort_grows_first_then_the_next(self):
        self.assertEqual(self._widths(17), (10, 5))
        self.assertEqual(self._widths(22), (12, 8))

    def test_remainder_is_shared_after_every_comfort_is_met(self):
        self.assertEqual(self._widths(40), (30, 8))


class StackLabelTests(unittest.TestCase):
    def test_label_prefixes_the_field_only_when_stacked(self):
        columns = (
            table.Column("NAME", fit=table.TRUNCATE, floor=20),
            table.Column("COUNT", align="right", stack_label="count"),
        )
        rows = [(("a-name", ()), ("3", ()))]
        self.assertEqual(_render(columns, rows, 10), "a-name\n  count 3")
        self.assertEqual(_render(columns, rows, 40).split("\n")[1], "a-name      3")


class WrapColumnTests(unittest.TestCase):
    COLUMNS = (
        table.Column("CODE"),
        table.Column("MESSAGE", fit=table.WRAP, floor=20),
    )
    ROWS = [
        (("some-code", ()), ("status 'a' but 2 later sessions worked this plan", ())),
    ]

    def test_message_wraps_within_the_table_up_to_three_lines(self):
        rendered = _render(self.COLUMNS, self.ROWS, 40)
        self.assertEqual(
            rendered.split("\n"),
            [
                "CODE       MESSAGE",
                "some-code  status 'a' but 2 later",
                "           sessions worked this plan",
            ],
        )

    def test_a_message_needing_more_than_three_lines_stacks(self):
        rendered = _render(self.COLUMNS, self.ROWS, 24)
        self.assertNotIn("CODE", rendered)
        self.assertEqual(rendered.split("\n")[-1], "  some-code")

    def test_stacked_message_wraps_at_full_width(self):
        rendered = _render(self.COLUMNS, self.ROWS, 24)
        self.assertEqual(rendered.split("\n")[0], "status 'a' but 2 later")

    def test_unbounded_message_is_one_line(self):
        self.assertEqual(len(_render(self.COLUMNS, self.ROWS, None).split("\n")), 2)


class TagsColumnTests(unittest.TestCase):
    COLUMNS = (
        table.Column("PLAN"),
        table.Column("TAGS", fit=table.TRUNCATE, floor=10, shorten=lambda t, w: t[:w]),
    )

    def test_shorten_hook_is_used_for_truncate_columns(self):
        rows = [(("p", ()), ("[alpha, beta, gamma]", ()))]
        rendered = _render(self.COLUMNS, rows, 17)
        self.assertEqual(rendered.split("\n")[1], "p     [alpha, bet")


class AllFixedTests(unittest.TestCase):
    def test_a_table_with_no_flexible_column_is_never_stacked(self):
        columns = (table.Column("A"), table.Column("B"))
        rows = [(("aaaaaaaa", ()), ("bbbbbbbb", ()))]
        self.assertTrue(_render(columns, rows, 5).startswith("A"))


if __name__ == "__main__":
    unittest.main()
