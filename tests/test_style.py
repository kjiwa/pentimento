from __future__ import annotations

import io
import os
import unittest

from pentimento import style


class _FakeStream(io.StringIO):
    def __init__(self, is_tty: bool):
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


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


class TruncateTests(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(style.truncate("hi", 10, unicode_ok=True), "hi")

    def test_unicode_ellipsis_is_one_column(self):
        result = style.truncate("hello world", 6, unicode_ok=True)
        self.assertTrue(result.endswith("…"))
        self.assertEqual(style.display_width(result), 6)

    def test_ascii_ellipsis_is_three_columns(self):
        result = style.truncate("hello world", 6, unicode_ok=False)
        self.assertTrue(result.endswith("..."))
        self.assertEqual(style.display_width(result), 6)

    def test_cjk_text_at_a_width_no_wider_than_the_ellipsis_never_overflows(self):
        result = style.truncate("文字", 2, unicode_ok=False)
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


class TruncateCellsTests(unittest.TestCase):
    def test_never_exceeds_the_width(self):
        cells = [("aaaaaaaaaa", ()), ("bbbbbbbbbb", ()), ("cccccccccc", ())]
        result = style.truncate_cells(cells, "  ", 10, unicode_ok=True, on_color=False)
        self.assertLessEqual(style.display_width(result), 10)

    def test_never_emits_a_partial_escape(self):
        cells = [("aaaaaaaaaa", (style.BOLD,)), ("bbbbbbbbbb", (style.GREEN,))]
        result = style.truncate_cells(cells, "  ", 8, unicode_ok=True, on_color=True)
        self.assertEqual(result.count(style.RESET), result.count(style.BOLD) + result.count(style.GREEN))

    def test_identical_to_plain_join_when_colour_is_off_and_it_fits(self):
        cells = [("a", (style.BOLD,)), ("b", (style.GREEN,))]
        result = style.truncate_cells(cells, "  ", 20, unicode_ok=True, on_color=False)
        self.assertEqual(result, "a  b")


class GlyphsTests(unittest.TestCase):
    def test_unicode_glyphs_selected(self):
        self.assertEqual(style.glyphs(True), style.GLYPHS_UNICODE)

    def test_ascii_glyphs_selected(self):
        self.assertEqual(style.glyphs(False), style.GLYPHS_ASCII)


class _FakeEncodedStream:
    def __init__(self, encoding: str):
        self.encoding = encoding

    def isatty(self) -> bool:
        return True


class UnicodeEnabledTests(unittest.TestCase):
    def _stream(self, encoding: str):
        return _FakeEncodedStream(encoding)

    def test_ascii_flag_forces_off(self):
        with _EnvGuard(TERM="xterm"):
            self.assertFalse(style.unicode_enabled(self._stream("utf-8"), True))

    def test_dumb_term_forces_off(self):
        with _EnvGuard(TERM="dumb"):
            self.assertFalse(style.unicode_enabled(self._stream("utf-8"), False))

    def test_utf8_encoding_enables_it(self):
        with _EnvGuard(TERM="xterm"):
            self.assertTrue(style.unicode_enabled(self._stream("utf-8"), False))

    def test_non_utf_encoding_disables_it(self):
        with _EnvGuard(TERM="xterm"):
            self.assertFalse(style.unicode_enabled(self._stream("ascii"), False))


if __name__ == "__main__":
    unittest.main()
