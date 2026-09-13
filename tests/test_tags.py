import unittest

from pentimento import tags


class ParseTests(unittest.TestCase):
    def test_parses_bracketed_list(self):
        self.assertEqual(tags.parse("[auth, security]"), ["auth", "security"])

    def test_parses_bare_comma_separated_values(self):
        self.assertEqual(tags.parse("auth, security"), ["auth", "security"])

    def test_case_is_preserved_faithfully(self):
        self.assertEqual(tags.parse("[Auth, security]"), ["Auth", "security"])

    def test_dedupes_and_sorts(self):
        self.assertEqual(tags.parse("[security, auth, security]"), ["auth", "security"])

    def test_empty_elements_are_dropped(self):
        self.assertEqual(tags.parse("[auth, , security]"), ["auth", "security"])

    def test_none_returns_empty_list(self):
        self.assertEqual(tags.parse(None), [])

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(tags.parse(""), [])

    def test_single_bare_value(self):
        self.assertEqual(tags.parse("auth"), ["auth"])


class RenderTests(unittest.TestCase):
    def test_renders_flow_style_list(self):
        self.assertEqual(tags.render(["auth", "security"]), "[auth, security]")

    def test_empty_list_renders_empty_string(self):
        self.assertEqual(tags.render([]), "")

    def test_round_trips_through_parse(self):
        rendered = tags.render(["auth", "security"])
        self.assertEqual(tags.parse(rendered), ["auth", "security"])


class NormalizeTests(unittest.TestCase):
    def test_lowercases_and_strips(self):
        self.assertEqual(tags.normalize("  Auth  "), "auth")


class IsValidTests(unittest.TestCase):
    def test_lowercase_alphanumeric_is_valid(self):
        self.assertTrue(tags.is_valid("auth"))

    def test_allows_dots_underscores_slashes_hyphens(self):
        self.assertTrue(tags.is_valid("a1.b_c/d-e"))

    def test_rejects_uppercase(self):
        self.assertFalse(tags.is_valid("Auth"))

    def test_rejects_leading_symbol(self):
        self.assertFalse(tags.is_valid("-auth"))

    def test_rejects_comma(self):
        self.assertFalse(tags.is_valid("auth,security"))

    def test_rejects_brackets(self):
        self.assertFalse(tags.is_valid("[auth]"))

    def test_rejects_hash(self):
        self.assertFalse(tags.is_valid("auth#1"))

    def test_rejects_empty_string(self):
        self.assertFalse(tags.is_valid(""))


if __name__ == "__main__":
    unittest.main()
