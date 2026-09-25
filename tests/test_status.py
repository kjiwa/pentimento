import unittest
from pathlib import Path

from pentimento import frontmatter, status

CURSOR_FIXTURES = Path(__file__).parent / "fixtures" / "cursor"


class DeriveStatusTests(unittest.TestCase):
    def test_all_checked_is_complete(self):
        body = "# Title\n\n## Progress\n- [x] one\n- [x] two\n"
        self.assertEqual(status.derive_status(body), "complete")

    def test_all_unchecked_is_not_started(self):
        body = "# Title\n\n## Progress\n- [ ] one\n- [ ] two\n"
        self.assertEqual(status.derive_status(body), "not-started")

    def test_mixed_is_partial(self):
        body = "# Title\n\n## Progress\n- [x] one\n- [ ] two\n"
        self.assertEqual(status.derive_status(body), "partial")

    def test_prose_fallback_nothing_started(self):
        body = "# Title\n\n## Progress\nNothing started. Planning only.\n"
        self.assertEqual(status.derive_status(body), "not-started")

    def test_no_progress_section_is_unknown(self):
        body = "# Title\n\nJust prose, no Progress section.\n"
        self.assertEqual(status.derive_status(body), "unknown")

    def test_progress_section_with_neither_signal_is_unknown(self):
        body = "# Title\n\n## Progress\nSome unrelated prose.\n"
        self.assertEqual(status.derive_status(body), "unknown")

    def test_progress_section_stops_at_next_heading(self):
        body = "# Title\n\n## Progress\n- [x] one\n\n## Context\n- [ ] not part of progress\n"
        self.assertEqual(status.derive_status(body), "complete")


def _cursor(name):
    _, body, extras = frontmatter.parse((CURSOR_FIXTURES / name).read_text())
    return body, extras


def _todos(*statuses):
    items = "".join(f"  - id: t{i}\n    content: c\n    status: {v}\n" for i, v in enumerate(statuses))
    text = f"---\nname: N\ntodos:\n{items}pentimento:\n  status: unknown\n---\n# Body\n"
    _, body, extras = frontmatter.parse(text)
    return body, extras


class CursorTodosTests(unittest.TestCase):
    def test_all_completed_is_complete(self):
        self.assertEqual(status.derive_status(*_cursor("quiet_flag_83cddd33.plan.md")), "complete")

    def test_all_pending_is_not_started(self):
        for name in (
            "skip_list_range_query_d3d1b015.plan.md",
            "range_vs_submap_benchmark_4a0ba26d.plan.md",
        ):
            with self.subTest(name=name):
                self.assertEqual(status.derive_status(*_cursor(name)), "not-started")

    def test_mixed_is_partial(self):
        self.assertEqual(status.derive_status(*_cursor("add_dry-run_flag_c900747b.plan.md")), "partial")

    def test_in_progress_alone_is_partial(self):
        self.assertEqual(status.derive_status(*_todos("in_progress")), "partial")

    def test_unseen_value_is_unknown(self):
        self.assertEqual(status.derive_status(*_todos("completed", "cancelled")), "unknown")

    def test_empty_todos_is_unknown(self):
        self.assertEqual(status.derive_status(*_todos()), "unknown")

    def test_pentimento_block_status_is_not_read_as_a_todo(self):
        body, extras = _todos("completed")
        self.assertEqual(status.derive_status(body, extras), "complete")

    def test_progress_wins_over_todos(self):
        _, extras = _todos("completed")
        self.assertEqual(status.derive_status("## Progress\n- [ ] a\n", extras), "not-started")

    def test_body_checkboxes_win_over_todos(self):
        _, extras = _todos("completed")
        self.assertEqual(status.derive_status("- [ ] a\n", extras), "not-started")


if __name__ == "__main__":
    unittest.main()
