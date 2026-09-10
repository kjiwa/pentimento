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

    def test_nested_pentimento_block_is_parsed(self):
        text = "---\npentimento:\n  status: complete\n  intent: active\n---\n# Title\n\nbody\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "intent": "active"})
        self.assertEqual(body, "# Title\n\nbody\n")

    def test_legacy_flat_block_still_parses(self):
        text = "---\nstatus: complete\nintent: active\n---\nbody\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "intent": "active"})
        self.assertEqual(body, "body\n")

    def test_pentimento_opener_does_not_leak_as_a_key(self):
        text = "---\npentimento:\n  status: complete\n---\nbody\n"
        fields, _ = frontmatter.parse(text)
        self.assertNotIn("pentimento", fields)

    def test_unknown_top_level_keys_survive_nested_block(self):
        text = "---\npentimento:\n  status: complete\nfoo: bar\n---\nbody\n"
        fields, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "foo": "bar"})

    def test_inline_comments_are_stripped(self):
        text = "---\npentimento:\n  status: partial # in progress\n  parent: root-plan # omitted for roots\n---\nbody\n"
        fields, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "partial", "parent": "root-plan"})

    def test_full_line_comments_are_ignored(self):
        text = "---\n# top-level comment\npentimento:\n  # indented comment\n  status: complete\n---\nbody\n"
        fields, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete"})

    def test_quoted_scalars_are_unquoted(self):
        text = "---\npentimento:\n  status: \"complete\"\n  project: 'pentimento'\n---\nbody\n"
        fields, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "project": "pentimento"})

    def test_empty_values_are_omitted(self):
        text = "---\npentimento:\n  status: complete\n  parent:\n---\nbody\n"
        fields, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete"})

    def test_crlf_line_endings_parse(self):
        text = "---\r\npentimento:\r\n  status: complete\r\n---\r\n# Title\r\n\r\nbody\r\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete"})
        self.assertEqual(body, "# Title\r\n\r\nbody\r\n")


class SerializeTests(unittest.TestCase):
    def test_empty_fields_returns_body_unchanged(self):
        body = "# Title\n\nbody\n"
        self.assertEqual(frontmatter.serialize({}, body), body)

    def test_round_trip_preserves_body_bytes_exactly(self):
        text = "---\npentimento:\n  status: complete\n  parent: eager-bird\n---\n# Title\n\n---\nrule\n"
        fields, body = frontmatter.parse(text)
        self.assertEqual(frontmatter.serialize(fields, body), text)

    def test_field_order_is_canonical(self):
        fields = {"parent": "root", "status": "complete", "intent": "active"}
        text = frontmatter.serialize(fields, "body\n")
        lines = text.split("\n")
        self.assertEqual(lines[0], "---")
        self.assertEqual(lines[1], "pentimento:")
        self.assertEqual(lines[2], "  status: complete")
        self.assertEqual(lines[3], "  intent: active")
        self.assertEqual(lines[4], "  parent: root")
        self.assertEqual(lines[5], "---")

    def test_flat_to_nested_round_trip_is_stable_on_a_second_pass(self):
        flat = "---\nstatus: complete\nintent: active\n---\nbody\n"
        fields, body = frontmatter.parse(flat)
        nested = frontmatter.serialize(fields, body)

        reparsed_fields, reparsed_body = frontmatter.parse(nested)
        self.assertEqual(reparsed_fields, fields)
        self.assertEqual(frontmatter.serialize(reparsed_fields, reparsed_body), nested)

    def test_unknown_top_level_keys_survive_serialize(self):
        fields = {"status": "complete", "foo": "bar"}
        text = frontmatter.serialize(fields, "body\n")
        lines = text.split("\n")
        self.assertEqual(lines[0], "---")
        self.assertEqual(lines[1], "pentimento:")
        self.assertEqual(lines[2], "  status: complete")
        self.assertEqual(lines[3], "foo: bar")
        self.assertEqual(lines[4], "---")


if __name__ == "__main__":
    unittest.main()
