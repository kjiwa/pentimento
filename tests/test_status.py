import unittest

from pentimento import status


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


if __name__ == "__main__":
    unittest.main()
