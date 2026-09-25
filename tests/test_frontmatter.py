import unittest
from pathlib import Path

from pentimento import frontmatter

FIXTURES = Path(__file__).parent / "fixtures"


class UnknownNamespacedKeyTests(unittest.TestCase):
    TEXT = "---\npentimento:\n  status: complete\n  note: see: this\n---\n# T\n"

    def test_unknown_key_in_the_block_stays_verbatim_in_the_block(self):
        fields, body, extras = frontmatter.parse(self.TEXT)
        self.assertNotIn("note", fields)
        self.assertEqual(frontmatter.serialize(fields, body, extras), self.TEXT)

    def test_writing_a_known_field_keeps_the_unknown_key(self):
        fields, body, extras = frontmatter.parse(self.TEXT)
        fields["intent"] = "active"
        out = frontmatter.serialize(fields, body, extras)
        self.assertEqual(
            out,
            "---\npentimento:\n  status: complete\n  intent: active\n  note: see: this\n---\n# T\n",
        )


class ParseTests(unittest.TestCase):
    def test_no_frontmatter_returns_whole_text_as_body(self):
        text = "# Title\n\nsome body\n"
        fields, body, extras = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)
        self.assertIsNone(extras)

    def test_body_horizontal_rule_is_not_parsed_as_frontmatter(self):
        text = "# Title\n\nabove\n\n---\n\nbelow\n"
        fields, body, _ = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_golden_fixture_body_rule_is_not_parsed_as_frontmatter(self):
        text = (FIXTURES / "body-rule.md").read_text()
        fields, body, _ = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_frontmatter_at_byte_zero_is_parsed(self):
        text = "---\nstatus: complete\nintent: active\n---\n# Title\n\nbody\n"
        fields, body, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "intent": "active"})
        self.assertEqual(body, "# Title\n\nbody\n")

    def test_unclosed_frontmatter_block_is_not_parsed(self):
        text = "---\nstatus: complete\n# Title\n\nbody\n"
        fields, body, _ = frontmatter.parse(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_nested_pentimento_block_is_parsed(self):
        text = "---\npentimento:\n  status: complete\n  intent: active\n---\n# Title\n\nbody\n"
        fields, body, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "intent": "active"})
        self.assertEqual(body, "# Title\n\nbody\n")

    def test_legacy_flat_block_still_parses(self):
        text = "---\nstatus: complete\nintent: active\n---\nbody\n"
        fields, body, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "intent": "active"})
        self.assertEqual(body, "body\n")

    def test_pentimento_opener_does_not_leak_as_a_key(self):
        text = "---\npentimento:\n  status: complete\n---\nbody\n"
        fields, _, _ = frontmatter.parse(text)
        self.assertNotIn("pentimento", fields)

    def test_unknown_top_level_keys_survive_nested_block(self):
        text = "---\npentimento:\n  status: complete\nfoo: bar\n---\nbody\n"
        fields, _, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "foo": "bar"})

    def test_inline_comments_are_stripped(self):
        text = (
            "---\npentimento:\n  status: partial # in progress\n"
            "  parent: root-plan # omitted for roots\n---\nbody\n"
        )
        fields, _, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "partial", "parent": "root-plan"})

    def test_full_line_comments_are_ignored(self):
        text = (
            "---\n# top-level comment\npentimento:\n  # indented comment\n"
            "  status: complete\n---\nbody\n"
        )
        fields, _, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete"})

    def test_quoted_scalars_are_unquoted(self):
        text = "---\npentimento:\n  status: \"complete\"\n  project: 'pentimento'\n---\nbody\n"
        fields, _, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete", "project": "pentimento"})

    def test_empty_values_are_omitted(self):
        text = "---\npentimento:\n  status: complete\n  parent:\n---\nbody\n"
        fields, _, _ = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete"})

    def test_crlf_line_endings_parse(self):
        text = "---\r\npentimento:\r\n  status: complete\r\n---\r\n# Title\r\n\r\nbody\r\n"
        fields, body, extras = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete"})
        self.assertEqual(body, "# Title\r\n\r\nbody\r\n")
        self.assertEqual(extras.newline, "\r\n")

    def test_sibling_foreign_block_survives_parse(self):
        text = (
            "---\nother-tool:\n  key: value\n  nested: thing\n"
            "pentimento:\n  status: complete\n---\nbody\n"
        )
        fields, _, extras = frontmatter.parse(text)
        self.assertEqual(fields, {"status": "complete"})
        self.assertIn("other-tool:", extras.lines)
        self.assertIn("  key: value", extras.lines)
        self.assertIn("  nested: thing", extras.lines)


class SerializeTests(unittest.TestCase):
    def test_empty_fields_returns_body_unchanged(self):
        body = "# Title\n\nbody\n"
        self.assertEqual(frontmatter.serialize({}, body), body)

    def test_round_trip_preserves_body_bytes_exactly(self):
        text = (
            "---\npentimento:\n  status: complete\n  parent: eager-bird\n---\n"
            "# Title\n\n---\nrule\n"
        )
        fields, body, extras = frontmatter.parse(text)
        self.assertEqual(frontmatter.serialize(fields, body, extras), text)

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

    def test_pinned_round_trips_in_canonical_position(self):
        fields = {"status": "complete", "pinned": "true", "intent": "active"}
        text = frontmatter.serialize(fields, "body\n")
        lines = text.split("\n")
        self.assertEqual(lines[2], "  status: complete")
        self.assertEqual(lines[3], "  pinned: true")
        self.assertEqual(lines[4], "  intent: active")

        reparsed, _, _ = frontmatter.parse(text)
        self.assertEqual(reparsed["pinned"], "true")

    def test_tags_round_trip_in_canonical_position(self):
        fields = {
            "status": "complete",
            "intent": "active",
            "tags": "[auth, security]",
            "parent": "root",
        }
        text = frontmatter.serialize(fields, "body\n")
        lines = text.split("\n")
        self.assertEqual(lines[2], "  status: complete")
        self.assertEqual(lines[3], "  intent: active")
        self.assertEqual(lines[4], "  tags: [auth, security]")
        self.assertEqual(lines[5], "  parent: root")

        reparsed, _, _ = frontmatter.parse(text)
        self.assertEqual(reparsed["tags"], "[auth, security]")

    def test_flat_to_nested_round_trip_is_stable_on_a_second_pass(self):
        flat = "---\nstatus: complete\nintent: active\n---\nbody\n"
        fields, body, extras = frontmatter.parse(flat)
        nested = frontmatter.serialize(fields, body, extras)

        reparsed_fields, reparsed_body, reparsed_extras = frontmatter.parse(nested)
        self.assertEqual(reparsed_fields, fields)
        self.assertEqual(
            frontmatter.serialize(reparsed_fields, reparsed_body, reparsed_extras), nested
        )

    def test_unknown_top_level_keys_survive_serialize(self):
        fields = {"status": "complete", "foo": "bar"}
        text = frontmatter.serialize(fields, "body\n")
        lines = text.split("\n")
        self.assertEqual(lines[0], "---")
        self.assertEqual(lines[1], "pentimento:")
        self.assertEqual(lines[2], "  status: complete")
        self.assertEqual(lines[3], "foo: bar")
        self.assertEqual(lines[4], "---")

    def test_rejects_value_with_newline(self):
        with self.assertRaises(ValueError):
            frontmatter.serialize({"status": "a\nb"}, "body\n")

    def test_rejects_value_with_leading_whitespace(self):
        with self.assertRaises(ValueError):
            frontmatter.serialize({"status": " complete"}, "body\n")

    def test_rejects_value_with_hash(self):
        with self.assertRaises(ValueError):
            frontmatter.serialize({"project": "foo # bar"}, "body\n")

    def test_rejects_value_with_colon_space(self):
        with self.assertRaises(ValueError):
            frontmatter.serialize({"project": "foo: bar"}, "body\n")


class UnknownValueTests(unittest.TestCase):
    def test_hash_inside_a_value_is_not_a_comment(self):
        fields, _, _ = frontmatter.parse("---\nurl: http://x/#a\n---\nbody\n")
        self.assertEqual(fields["url"], "http://x/#a")

    def test_hash_after_whitespace_still_starts_a_comment(self):
        fields, _, _ = frontmatter.parse("---\nurl: http://x/ # note\n---\nbody\n")
        self.assertEqual(fields["url"], "http://x/")

    def test_fragment_survives_a_round_trip(self):
        text = "---\nurl: http://x/#a\npentimento:\n  status: complete\n---\nbody\n"
        fields, body, extras = frontmatter.parse(text)
        fields["status"] = "partial"
        rewritten = frontmatter.serialize(fields, body, extras)
        self.assertIn("url: http://x/#a", rewritten)

    def test_unknown_value_with_colon_space_is_passed_through(self):
        text = "---\npentimento:\n  status: complete\nname: Plan: the sequel\n---\nbody\n"
        fields, body, extras = frontmatter.parse(text)
        self.assertEqual(frontmatter.serialize(fields, body, extras), text)
        fields["status"] = "partial"
        self.assertIn("name: Plan: the sequel", frontmatter.serialize(fields, body, extras))

    def test_unknown_quoted_value_keeps_its_quotes(self):
        text = '---\nname: "Plan # one"\npentimento:\n  status: complete\n---\nbody\n'
        fields, body, extras = frontmatter.parse(text)
        fields["status"] = "partial"
        self.assertIn('name: "Plan # one"', frontmatter.serialize(fields, body, extras))

    def test_changed_known_field_values_are_still_validated(self):
        text = "---\npentimento:\n  project: ok\n---\nbody\n"
        fields, body, extras = frontmatter.parse(text)
        fields["project"] = "a: b"
        with self.assertRaises(ValueError):
            frontmatter.serialize(fields, body, extras)

    def test_unchanged_invalid_known_value_is_reemitted_verbatim(self):
        text = '---\npentimento:\n  status: complete\n  project: "a #b"\n---\nbody\n'
        fields, body, extras = frontmatter.parse(text)
        self.assertEqual(frontmatter.serialize(fields, body, extras), text)
        fields["status"] = "partial"
        self.assertIn('project: "a #b"', frontmatter.serialize(fields, body, extras))
        fields["project"] = "a #c"
        with self.assertRaises(ValueError):
            frontmatter.serialize(fields, body, extras)


class RemovingTheLastFieldTests(unittest.TestCase):
    def test_foreign_frontmatter_survives_without_the_namespace_opener(self):
        text = "---\nother:\n  k: v\n# a note\npentimento:\n  status: complete\n---\nbody\n"
        fields, body, extras = frontmatter.parse(text)
        fields.pop("status")
        self.assertEqual(
            frontmatter.serialize(fields, body, extras),
            "---\nother:\n  k: v\n# a note\n---\nbody\n",
        )

    def test_a_block_holding_only_pentimento_fields_becomes_the_bare_body(self):
        text = "---\npentimento:\n  status: complete\n---\nbody\n"
        fields, body, extras = frontmatter.parse(text)
        fields.pop("status")
        self.assertEqual(frontmatter.serialize(fields, body, extras), "body\n")


class CleanValueTests(unittest.TestCase):
    def test_decodes_yaml_quoting_and_comments(self):
        cases = {
            "plain # note": "plain",
            "'It''s ok'": "It's ok",
            '"Say \\"hi\\""': 'Say "hi"',
            '"tab\\there"': "tab\there",
            '"quoted" # note': "quoted",
            '"unterminated': "unterminated",
            "": "",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(frontmatter.clean_value(raw), expected)


class IsValidValueTests(unittest.TestCase):
    def test_plain_value_is_valid(self):
        self.assertTrue(frontmatter.is_valid_value("pentimento"))

    def test_rejects_newline(self):
        self.assertFalse(frontmatter.is_valid_value("a\nb"))

    def test_rejects_trailing_whitespace(self):
        self.assertFalse(frontmatter.is_valid_value("a "))

    def test_rejects_hash(self):
        self.assertFalse(frontmatter.is_valid_value("a#b"))

    def test_rejects_colon_space(self):
        self.assertFalse(frontmatter.is_valid_value("a: b"))


class RoundTripPropertyTests(unittest.TestCase):
    """`serialize(*parse(text)) == text` when no field is changed."""

    def assert_round_trips(self, text: str) -> None:
        fields, body, extras = frontmatter.parse(text)
        self.assertEqual(frontmatter.serialize(fields, body, extras), text)

    def test_plain_nested_block(self):
        self.assert_round_trips(
            "---\npentimento:\n  status: complete\n  parent: eager-bird\n---\nbody\n"
        )

    def test_sibling_foreign_block(self):
        self.assert_round_trips(
            "---\nother-tool:\n  key: value\n  nested: thing\n"
            "pentimento:\n  status: complete\n---\nbody\n"
        )

    def test_top_level_comment(self):
        self.assert_round_trips(
            "---\n# a top-level comment\npentimento:\n  status: complete\n---\nbody\n"
        )

    def test_top_level_blank_line(self):
        self.assert_round_trips("---\n\npentimento:\n  status: complete\n---\nbody\n")

    def test_flush_left_sequence_items_stay_in_their_block(self):
        self.assert_round_trips(
            "---\ntodos:\n- id: a\n  status: pending\n- id: b\n  status: completed\n"
            "other:\n  key: value\npentimento:\n  status: partial\n---\nbody\n"
        )

    def test_flush_left_items_are_not_top_level_fields(self):
        fields, _, _ = frontmatter.parse("---\ntodos:\n- id: a\n- id: b\n---\nbody\n")
        self.assertEqual(fields, {})

    def test_crlf_line_endings(self):
        self.assert_round_trips(
            "---\r\npentimento:\r\n  status: complete\r\n---\r\n# Title\r\n\r\nbody\r\n"
        )


if __name__ == "__main__":
    unittest.main()
