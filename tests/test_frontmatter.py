import unittest
from pathlib import Path

from pentimento import frontmatter

FIXTURES = Path(__file__).parent / "fixtures"


class ParseTests(unittest.TestCase):
    def test_no_frontmatter_returns_whole_text_as_body(self):
        text = "# Title\n\nsome body\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_body_horizontal_rule_is_not_parsed_as_frontmatter(self):
        text = "# Title\n\nabove\n\n---\n\nbelow\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_golden_fixture_body_rule_is_not_parsed_as_frontmatter(self):
        text = (FIXTURES / "body-rule.md").read_text()
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_frontmatter_at_byte_zero_is_parsed(self):
        text = "---\nstatus: complete\nintent: active\n---\n# Title\n\nbody\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "intent": "active"})
        self.assertEqual(body, "# Title\n\nbody\n")

    def test_unclosed_frontmatter_block_is_not_parsed(self):
        text = "---\nstatus: complete\n# Title\n\nbody\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)


class SerializeTests(unittest.TestCase):
    def test_empty_fields_returns_body_unchanged(self):
        body = "# Title\n\nbody\n"
        self.assertEqual(frontmatter.serialize({}, body), body)

    def test_round_trip_preserves_body_bytes_exactly(self):
        text = "---\nstatus: complete\nparent: eager-bird\n---\n# Title\n\n---\nrule\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(frontmatter.serialize(fields, body), text)

    def test_field_order_is_canonical(self):
        fields = {"parent": "root", "status": "complete", "intent": "active"}
        text = frontmatter.serialize(fields, "body\n")
        lines = text.split("\n")
        self.assertEqual(lines[0], "---")
        self.assertEqual(lines[1], "status: complete")
        self.assertEqual(lines[2], "intent: active")
        self.assertEqual(lines[3], "parent: root")
        self.assertEqual(lines[4], "---")


if __name__ == "__main__":
    unittest.main()
