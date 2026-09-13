from __future__ import annotations

import unittest

from pentimento import style, table


def _column(header, **kwargs):
    return table.Column(header, **kwargs)


class NaturalWidthTests(unittest.TestCase):
    def test_no_row_is_padded_to_width(self):
        columns = (_column("A"), _column("B"))
        rows = [((("x", ()), ("y", ())))]
        rendered = table.render(columns, rows, on_color=False, unicode_ok=True, width=200)
        for line in rendered.split("\n"):
            self.assertLess(style.display_width(line), 200)

    def test_no_trailing_whitespace(self):
        columns = (_column("A"), _column("B"))
        rows = [(("x", ()), ("y", ()))]
        rendered = table.render(columns, rows, on_color=False, unicode_ok=True, width=200)
        for line in rendered.split("\n"):
            self.assertEqual(line, line.rstrip())


class ShrinkBeforeDropTests(unittest.TestCase):
    def test_flex_column_shrinks_to_comfort_before_anything_drops(self):
        columns = (
            _column("FIXED"),
            _column("FLEX", flex=1, comfort=5, floor=2, drop=1),
        )
        rows = [(("fixed-value", ()), ("a very long flexible value", ()))]
        width = style.display_width("fixed-value") + style.GUTTER + 5
        rendered = table.render(columns, rows, on_color=False, unicode_ok=True, width=width)
        header = rendered.split("\n")[0]
        self.assertIn("FIXED", header)
        self.assertIn("FLEX", header)


class DropOrderTests(unittest.TestCase):
    def test_lowest_drop_value_goes_first(self):
        columns = (
            _column("KEEP"),
            _column("FIRST", drop=1),
            _column("SECOND", drop=2),
        )
        rows = [(("keep", ()), ("first", ()), ("second", ()))]
        # Wide enough for natural widths, narrow enough to force a drop.
        width = style.display_width("keep") + style.GUTTER + style.display_width("second") + 1
        rendered = table.render(columns, rows, on_color=False, unicode_ok=True, width=width)
        header = rendered.split("\n")[0]
        self.assertNotIn("FIRST", header)
        self.assertIn("SECOND", header)


class FloorPassTests(unittest.TestCase):
    def test_shrinks_to_floor_once_dropping_is_exhausted(self):
        columns = (_column("FLEX", flex=1, comfort=10, floor=3),)
        rows = [(("x" * 30, ()),)]
        rendered = table.render(columns, rows, on_color=False, unicode_ok=True, width=3)
        for line in rendered.split("\n"):
            self.assertLessEqual(style.display_width(line), 3)


class UnconditionalFitTests(unittest.TestCase):
    def test_every_line_fits_every_width_both_glyph_sets(self):
        columns = (
            _column("STATUS", drop=3),
            _column("PLAN", flex=2, comfort=24, floor=10, drop=2),
            _column("TITLE", flex=1, comfort=32, floor=16),
            _column("AGE", align="right"),
        )
        rows = [
            (("complete", ()), ("api-auth-redesign", ()), ("Redesign the auth API", ()), ("5w", ())),
            (("partial", ()), ("api-auth-rollout", ()), ("Roll out the new auth API", ()), ("2w", ())),
        ]
        for unicode_ok in (True, False):
            for width in range(10, 201):
                rendered = table.render(columns, rows, on_color=False, unicode_ok=unicode_ok, width=width)
                for line in rendered.split("\n"):
                    self.assertLessEqual(
                        style.display_width(line), width, f"width={width} overflowed: {line!r}"
                    )


if __name__ == "__main__":
    unittest.main()
