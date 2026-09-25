from __future__ import annotations

import io
import os
import unittest
from unittest import mock

from pentimento import style


class _FakeStream(io.StringIO):
    def __init__(self, is_tty: bool):
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


class ZeroWidthTests(unittest.TestCase):
    def test_format_characters_and_hangul_jamo_take_no_columns(self):
        self.assertEqual(style.display_width("a\u200bb"), 2)
        self.assertEqual(style.display_width("\u1112\u1161\u11ab"), 2)
        self.assertEqual(style.display_width("e\u0301"), 1)
        self.assertEqual(style.display_width("\u20dd"), 0)

    def test_split_width_keeps_zero_width_characters_with_their_prefix(self):
        self.assertEqual(style.split_width("ab\u200bcd", 2), ("ab\u200b", "cd"))


class _EnvGuard:
    def __init__(self, **overrides):
        self._overrides = overrides
        self._previous = {}

    def __enter__(self):
        for key, value in self._overrides.items():
            self._previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return self

    def __exit__(self, *exc_info):
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class EnabledTests(unittest.TestCase):
    def test_always_ignores_stream(self):
        self.assertTrue(style.enabled(_FakeStream(is_tty=False), "always"))

    def test_never_ignores_stream(self):
        self.assertFalse(style.enabled(_FakeStream(is_tty=True), "never"))

    def test_auto_off_when_not_a_tty(self):
        self.assertFalse(style.enabled(_FakeStream(is_tty=False), "auto"))

    def test_auto_on_for_a_plain_tty(self):
        with _EnvGuard(NO_COLOR=None, TERM="xterm"):
            self.assertTrue(style.enabled(_FakeStream(is_tty=True), "auto"))

    def test_auto_off_with_no_color_env(self):
        with _EnvGuard(NO_COLOR="1", TERM="xterm"):
            self.assertFalse(style.enabled(_FakeStream(is_tty=True), "auto"))

    def test_auto_off_with_dumb_term(self):
        with _EnvGuard(NO_COLOR=None, TERM="dumb"):
            self.assertFalse(style.enabled(_FakeStream(is_tty=True), "auto"))


class PaintTests(unittest.TestCase):
    def test_off_returns_input_unchanged(self):
        self.assertEqual(style.paint("hello", style.BOLD, on=False), "hello")

    def test_on_wraps_in_sgr_and_resets(self):
        painted = style.paint("hello", style.BOLD, on=True)
        self.assertTrue(painted.startswith(style.BOLD))
        self.assertTrue(painted.endswith(style.RESET))
        self.assertIn("hello", painted)

    def test_no_codes_returns_input_unchanged(self):
        self.assertEqual(style.paint("hello", on=True), "hello")


class DisplayWidthTests(unittest.TestCase):
    def test_ascii_is_one_column_per_char(self):
        self.assertEqual(style.display_width("abc"), 3)

    def test_east_asian_wide_characters_count_double(self):
        self.assertEqual(style.display_width("中文"), 4)

    def test_combining_marks_count_zero(self):
        # "e" + combining acute accent (U+0301)
        self.assertEqual(style.display_width("é"), 1)


class SplitWidthTests(unittest.TestCase):
    def test_splits_on_a_boundary(self):
        self.assertEqual(style.split_width("hello world", 5), ("hello", " world"))

    def test_splits_inside_a_wide_character(self):
        head, tail = style.split_width("中文", 1)
        self.assertEqual(head, "")
        self.assertEqual(tail, "中文")

    def test_width_past_the_end_returns_the_whole_text(self):
        self.assertEqual(style.split_width("hi", 10), ("hi", ""))

    def test_width_of_zero_returns_nothing(self):
        self.assertEqual(style.split_width("hi", 0), ("", "hi"))


class TruncateTests(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(style.truncate("hi", 10), "hi")

    def test_ellipsis_is_three_columns(self):
        result = style.truncate("hello world", 6)
        self.assertTrue(result.endswith("..."))
        self.assertEqual(style.display_width(result), 6)

    def test_cjk_text_at_a_width_no_wider_than_the_ellipsis_never_overflows(self):
        result = style.truncate("文字", 2)
        self.assertLessEqual(style.display_width(result), 2)


class RenderCellsTests(unittest.TestCase):
    def test_matches_plain_join_when_colour_is_off(self):
        cells = [("a", (style.BOLD,)), ("b", ())]
        plain, painted = style.render_cells(cells, "  ", on_color=False)
        self.assertEqual(plain, "a  b")
        self.assertEqual(painted, "a  b")

    def test_painted_carries_the_codes(self):
        cells = [("a", (style.BOLD,)), ("b", ())]
        _, painted = style.render_cells(cells, "  ", on_color=True)
        self.assertIn(style.BOLD, painted)


class WrapTests(unittest.TestCase):
    def test_wraps_at_spaces(self):
        self.assertEqual(style.wrap("aa bb cc dd", 5), ["aa bb", "cc dd"])

    def test_a_word_wider_than_the_width_hard_wraps(self):
        self.assertEqual(style.wrap("abcdefg h", 3), ["abc", "def", "g h"])

    def test_wide_characters_count_two_columns(self):
        self.assertEqual(style.wrap("文字 文字", 4), ["文字", "文字"])

    def test_empty_text_is_one_empty_line(self):
        self.assertEqual(style.wrap("", 5), [""])


class WrapFieldsTests(unittest.TestCase):
    def test_breaks_only_between_fields(self):
        cells = [("aaaa", ()), ("bbbb", ()), ("cc", ())]
        lines = style.wrap_fields(cells, "  ", 11, "> ", on_color=False)
        self.assertEqual(lines, ["> aaaa", "> bbbb  cc"])

    def test_a_field_wider_than_the_line_hard_wraps(self):
        lines = style.wrap_fields([("abcdef", ())], "  ", 5, "  ", on_color=False)
        self.assertEqual(lines, ["  abc", "  def"])

    def test_unbounded_width_keeps_one_line(self):
        cells = [("aaaa", ()), ("bbbb", ())]
        self.assertEqual(style.wrap_fields(cells, "  ", None, "", on_color=False), ["aaaa  bbbb"])

    def test_paints_after_measuring(self):
        cells = [("aaaa", (style.BOLD,)), ("bbbb", (style.GREEN,))]
        lines = style.wrap_fields(cells, "  ", 6, "", on_color=True)
        self.assertEqual(
            lines, [style.BOLD + "aaaa" + style.RESET, style.GREEN + "bbbb" + style.RESET]
        )


class TerminalWidthTests(unittest.TestCase):
    def test_columns_variable_wins(self):
        with mock.patch.dict(os.environ, {"COLUMNS": "77"}):
            self.assertEqual(style.terminal_width(), 77)

    def test_unbounded_when_not_a_tty(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("sys.stdout.isatty", return_value=False),
        ):
            self.assertIsNone(style.terminal_width())


class GlyphsTests(unittest.TestCase):
    def test_glyphs_are_ascii(self):
        for glyph in style.GLYPHS.values():
            self.assertTrue(glyph.isascii())

    def test_connectors_share_one_width(self):
        self.assertEqual({len(glyph) for glyph in style.GLYPHS.values()}, {4})


if __name__ == "__main__":
    unittest.main()
