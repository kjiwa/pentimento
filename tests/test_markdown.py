from __future__ import annotations

import unittest

from pentimento import markdown, style


def _render(body, width=40, on_color=False, unicode_ok=True):
    return markdown.render(body, on_color=on_color, unicode_ok=unicode_ok, width=width)


class WrapTests(unittest.TestCase):
    def test_greedy_pack_never_exceeds_width(self):
        text = "one two three four five six seven eight nine ten"
        lines = _render(text, width=20)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 20)

    def test_wide_char_paragraph_counts_double_width(self):
        text = "文字 " * 10
        lines = _render(text.strip(), width=20)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 20)
        self.assertGreater(len(lines), 1)

    def test_hanging_indent_aligns_continuation_under_text(self):
        text = "- a long item that must wrap onto more than one output line for sure"
        lines = _render(text, width=20)
        self.assertTrue(lines[0].startswith("• "))
        for line in lines[1:]:
            self.assertTrue(line.startswith("  "))
            self.assertFalse(line.startswith("  •"))

    def test_a_token_wider_than_the_width_is_broken_into_full_rows(self):
        token = "a" * 60
        lines = _render(token, width=20)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 20)
        self.assertEqual("".join(lines), token)

    def test_a_token_wider_than_its_table_cell_is_broken(self):
        token = "b" * 60
        body = f"| col |\n| --- |\n| {token} |"
        lines = _render(body, width=20)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 20)
        self.assertIn(token, "".join(lines))

    def test_a_wide_cjk_token_is_split_on_a_character_boundary(self):
        token = "文" * 30
        lines = _render(token, width=20)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 20)
            self.assertNotIn("�", line)
        self.assertEqual("".join(lines), token)

    def test_fenced_code_with_a_wide_token_is_still_not_reflowed(self):
        body = "```sh\n" + "a" * 60 + "\n```"
        lines = _render(body, width=20)
        self.assertEqual(len(lines), 1)


class ListItemContinuationTests(unittest.TestCase):
    def test_fenced_code_nested_under_a_bullet_is_not_folded_into_prose(self):
        body = '- Sweep the tree:\n   ```sh\n   for d in a b; do echo "$d"; done\n   ```\n   Done.'
        lines = _render(body, width=100)
        joined = "\n".join(lines)
        self.assertIn('for d in a b; do echo "$d"; done', joined)
        self.assertNotIn("`", joined)


class GlyphTests(unittest.TestCase):
    def test_checked_box_unicode(self):
        lines = _render("- [x] done", unicode_ok=True)
        self.assertEqual(lines, ["✓ done"])

    def test_checked_box_ascii(self):
        lines = _render("- [x] done", unicode_ok=False)
        self.assertEqual(lines, ["[x] done"])

    def test_unchecked_box_unicode(self):
        lines = _render("- [ ] todo", unicode_ok=True)
        self.assertEqual(lines, ["☐ todo"])

    def test_unchecked_box_ascii(self):
        lines = _render("- [ ] todo", unicode_ok=False)
        self.assertEqual(lines, ["[ ] todo"])

    def test_bullet_unicode(self):
        lines = _render("- item", unicode_ok=True)
        self.assertEqual(lines, ["• item"])

    def test_bullet_ascii(self):
        lines = _render("- item", unicode_ok=False)
        self.assertEqual(lines, ["- item"])

    def test_checked_box_is_painted_green(self):
        lines = _render("- [x] done", on_color=True, unicode_ok=True)
        self.assertIn(style.GREEN, lines[0])


class HeadingTests(unittest.TestCase):
    def test_a_long_heading_wraps_with_its_indent_preserved(self):
        body = "### " + "word " * 20
        lines = _render(body, width=20)
        heading_lines = [line for line in lines if line.strip()]
        self.assertGreater(len(heading_lines), 1)
        for line in heading_lines:
            self.assertLessEqual(style.display_width(line), 20)
            self.assertTrue(line.startswith("  "))


class FencedCodeTests(unittest.TestCase):
    def test_fenced_code_is_indented_and_truncated(self):
        body = "```sh\ndocker exec -w /app foo php test.php\n```"
        lines = _render(body, width=20)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("    "))
        self.assertLessEqual(style.display_width(lines[0]), 20)
        self.assertTrue(lines[0].endswith("…"))

    def test_fenced_code_is_never_reflowed(self):
        body = "```\none two three four five six seven eight nine ten\n```"
        lines = _render(body, width=15)
        self.assertEqual(len(lines), 1)


class TableTests(unittest.TestCase):
    def test_header_and_delimiter_render_a_bold_header_row(self):
        body = "| a | b |\n| --- | --- |\n| 1 | 2 |"
        lines = _render(body, on_color=True, width=100)
        self.assertIn(style.BOLD, lines[0])
        self.assertNotIn("|", "".join(lines))
        self.assertIn("1", lines[1])
        self.assertIn("2", lines[1])

    def test_right_aligned_column(self):
        body = "| name | count |\n| --- | ---: |\n| a | 1 |"
        lines = _render(body, width=100)
        header, row = lines[0], lines[1]
        self.assertTrue(header.rstrip().endswith("count"))
        self.assertTrue(row.rstrip().endswith("1"))

    def test_no_delimiter_row_has_no_header(self):
        body = "| a | b |\n| c | d |"
        lines = _render(body, on_color=True, width=100)
        self.assertNotIn(style.BOLD, lines[0])
        self.assertEqual(len(lines), 2)

    def test_escaped_pipe_is_unescaped_in_a_cell(self):
        body = r"| a\|b | c |" + "\n| --- | --- |"
        lines = _render(body, width=100)
        self.assertIn("a|b", lines[0])

    def test_ragged_row_is_padded(self):
        body = "| a | b |\n| --- | --- |\n| 1 |"
        lines = _render(body, width=100)
        self.assertEqual(len(lines), 2)

    def test_wide_row_wraps_instead_of_truncating(self):
        body = "| col |\n| --- |\n| " + "word " * 30 + "|"
        lines = _render(body, width=20)
        joined = "\n".join(lines)
        self.assertNotIn("…", joined)
        self.assertGreater(len(lines), 2)

    def test_narrow_width_hits_the_column_floor(self):
        body = (
            "| aa aa aa aa | bb bb bb bb | cc cc cc cc |\n"
            "| --- | --- | --- |\n"
            "| x x x x | y y y y | z z z z |"
        )
        lines = _render(body, width=10)
        self.assertGreater(len(lines), 2)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 10)

    def test_six_narrow_columns_fit_the_width(self):
        header = "| " + " | ".join("aaaaaa" for _ in range(6)) + " |"
        delimiter = "| " + " | ".join("---" for _ in range(6)) + " |"
        row = "| " + " | ".join("x x x x" for _ in range(6)) + " |"
        body = f"{header}\n{delimiter}\n{row}"
        lines = _render(body, width=20)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 20)


class LinkTests(unittest.TestCase):
    def test_plain_link_is_painted_cyan_with_markers_removed(self):
        lines = _render("[some text](https://example.com/x)", on_color=True, width=100)
        self.assertNotIn("](", lines[0])
        self.assertNotIn("example.com", lines[0])
        self.assertIn(style.CYAN, lines[0])
        self.assertIn("some", lines[0])
        self.assertIn("text", lines[0])

    def test_link_containing_a_code_span_paints_both(self):
        lines = _render("[`code`](https://example.com)", on_color=True, width=100)
        self.assertNotIn("`", lines[0])
        self.assertIn(style.CYAN, lines[0])
        self.assertIn("code", lines[0])

    def test_unmatched_bracket_stays_literal(self):
        lines = _render("[not a link", width=100)
        self.assertIn("[not", lines[0])

    def test_link_glued_to_adjacent_punctuation(self):
        lines = _render("([link](https://example.com/x))", width=100)
        self.assertIn("(link)", lines[0])

    def test_link_as_the_last_token_on_a_wrapped_line(self):
        text = "one two three four five [linktext](https://example.com/page)"
        lines = _render(text, width=20)
        self.assertIn("linktext", "\n".join(lines))

    def test_image_syntax_is_left_alone(self):
        lines = _render("![alt](image.png)", width=100)
        self.assertIn("![alt](image.png)", lines[0])


class InlineSpanTests(unittest.TestCase):
    def test_bold_is_painted_and_markers_removed(self):
        lines = _render("**bold** text", on_color=True, width=100)
        self.assertNotIn("**", lines[0])
        self.assertIn(style.BOLD, lines[0])

    def test_code_span_is_painted_and_markers_removed(self):
        lines = _render("`code` text", on_color=True, width=100)
        self.assertNotIn("`", lines[0])
        self.assertIn(style.CYAN, lines[0])

    def test_unmatched_marker_stays_literal(self):
        lines = _render("this **has no closer", width=100)
        self.assertIn("**", lines[0])

    def test_unmatched_backtick_stays_literal(self):
        lines = _render("this `has no closer", width=100)
        self.assertIn("`", lines[0])

    def test_punctuation_glued_to_a_closing_marker_gets_no_space(self):
        lines = _render("see `tenant_settings`. done", width=100)
        self.assertIn("tenant_settings.", lines[0])
        self.assertNotIn("tenant_settings .", lines[0])

    def test_glued_code_spans_render_with_no_extra_space_or_duplication(self):
        lines = _render("`sh -n`/`shellcheck` on the new script clean", width=100)
        self.assertEqual(lines, ["sh -n/shellcheck on the new script clean"])
        self.assertNotIn("`", lines[0])
        self.assertNotIn("shellcheck shellcheck", lines[0])

    def test_very_long_code_span_still_wraps(self):
        text = "`" + " ".join(f"word{n}" for n in range(30)) + "`"
        lines = _render(text, width=40)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 40)


class BlockquoteTests(unittest.TestCase):
    def test_long_blockquote_wraps_to_width(self):
        text = "> " + " ".join(f"word{n}" for n in range(40))
        lines = _render(text, width=30)
        for line in lines:
            self.assertLessEqual(style.display_width(line), 30)
        self.assertGreater(len(lines), 1)

    def test_blockquote_is_indented_and_dim(self):
        lines = _render("> a quote", on_color=True, width=100)
        self.assertIn(style.DIM, lines[0])
        self.assertIn("  a quote", lines[0])


class SqueezeTests(unittest.TestCase):
    def test_leading_blanks_are_dropped(self):
        self.assertEqual(markdown._squeeze(["", "", "a", "b"]), ["a", "b"])

    def test_trailing_blanks_are_dropped(self):
        self.assertEqual(markdown._squeeze(["a", "b", "", ""]), ["a", "b"])

    def test_interior_runs_collapse_to_one(self):
        self.assertEqual(markdown._squeeze(["a", "", "", "", "b"]), ["a", "", "b"])

    def test_render_has_no_doubled_blank_before_a_heading(self):
        lines = _render("intro\n\n## Heading\n\nbody", width=40)
        self.assertEqual(lines, ["intro", "", "Heading", "", "body"])

    def test_render_has_no_trailing_blank(self):
        lines = _render("## Heading\n\n", width=40)
        self.assertNotEqual(lines[-1], "")


class ClipTests(unittest.TestCase):
    def test_under_limit_is_unchanged(self):
        lines = ["a", "b", "c"]
        self.assertEqual(markdown.clip(lines, 10, "hint", on_color=False, unicode_ok=True), lines)

    def test_limit_none_is_unchanged(self):
        lines = ["a", "b", "c"]
        self.assertEqual(markdown.clip(lines, None, "hint", on_color=False, unicode_ok=True), lines)

    def test_at_limit_is_unchanged(self):
        lines = ["a", "b", "c"]
        self.assertEqual(markdown.clip(lines, 3, "hint", on_color=False, unicode_ok=True), lines)

    def test_over_limit_trims_and_appends_hint(self):
        lines = [str(n) for n in range(10)]
        clipped = markdown.clip(
            lines, 5, "pentimento show foo --full", on_color=False, unicode_ok=True
        )
        self.assertEqual(len(clipped), markdown.MIN_BODY_LINES + 1)
        self.assertIn("more lines", clipped[-1])
        self.assertIn("pentimento show foo --full", clipped[-1])

    def test_over_limit_trims_trailing_blank_lines(self):
        lines = ["0", "1", "2", "3", "4", "", "6", "7"]
        clipped = markdown.clip(lines, 6, "hint", on_color=False, unicode_ok=True)
        self.assertEqual(clipped[:-1], ["0", "1", "2", "3", "4"])
        self.assertIn("more lines", clipped[-1])

    def test_ascii_mode_never_emits_unicode_clip_glyphs(self):
        lines = [str(n) for n in range(10)]
        clipped = markdown.clip(lines, 5, "hint", on_color=False, unicode_ok=False)
        self.assertNotIn("…", clipped[-1])
        self.assertNotIn("—", clipped[-1])


if __name__ == "__main__":
    unittest.main()
