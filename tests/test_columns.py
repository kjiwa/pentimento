from __future__ import annotations

import unittest

from pentimento import columns

VALID = ("status", "intent", "project", "source", "plan", "title", "tags", "created", "updated")


class ParseAbsoluteTests(unittest.TestCase):
    def test_absolute_list_keeps_given_order(self):
        selection = columns.parse("created,title,status", VALID)
        self.assertEqual(selection.absolute, ("created", "title", "status"))
        self.assertEqual(selection.add, frozenset())
        self.assertEqual(selection.remove, frozenset())

    def test_blank_segments_are_dropped(self):
        selection = columns.parse("title,, status ,", VALID)
        self.assertEqual(selection.absolute, ("title", "status"))

    def test_duplicate_name_is_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            columns.parse("title,title", VALID)
        self.assertIn("duplicate", str(ctx.exception))
        self.assertTrue(str(ctx.exception).endswith(f"valid columns: {', '.join(VALID)}"))

    def test_unknown_name_is_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            columns.parse("bogus", VALID)
        message = str(ctx.exception)
        self.assertIn("unknown column: bogus", message)
        self.assertTrue(message.endswith(f"valid columns: {', '.join(VALID)}"))

    def test_empty_spec_is_an_error(self):
        with self.assertRaises(ValueError):
            columns.parse("", VALID)
        with self.assertRaises(ValueError):
            columns.parse("  ,  ", VALID)


class ParseRelativeTests(unittest.TestCase):
    def test_add_only(self):
        selection = columns.parse("+created", VALID)
        self.assertIsNone(selection.absolute)
        self.assertEqual(selection.add, {"created"})
        self.assertEqual(selection.remove, frozenset())

    def test_remove_only(self):
        selection = columns.parse("-source,-project", VALID)
        self.assertIsNone(selection.absolute)
        self.assertEqual(selection.remove, {"source", "project"})

    def test_add_and_remove_together(self):
        selection = columns.parse("+created,-tags", VALID)
        self.assertEqual(selection.add, {"created"})
        self.assertEqual(selection.remove, {"tags"})

    def test_repeated_relative_name_is_idempotent(self):
        selection = columns.parse("+created,+created", VALID)
        self.assertEqual(selection.add, {"created"})

    def test_unknown_relative_name_is_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            columns.parse("+bogus", VALID)
        self.assertIn("unknown column: bogus", str(ctx.exception))

    def test_mixing_absolute_and_relative_is_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            columns.parse("+created,title", VALID)
        message = str(ctx.exception)
        self.assertIn("cannot mix", message)
        self.assertTrue(message.endswith(f"valid columns: {', '.join(VALID)}"))


class ParseAllTests(unittest.TestCase):
    def test_all_resolves_to_every_valid_name_in_order(self):
        selection = columns.parse("all", VALID)
        self.assertEqual(selection.absolute, VALID)


class ResolveAbsoluteTests(unittest.TestCase):
    def test_absolute_keeps_order_and_pins_everything(self):
        selection = columns.parse("created,title,status", VALID)
        names, never_drop = columns.resolve(selection, ("status", "title"), pin=("status",))
        self.assertEqual(names, ["created", "title", "status"])
        self.assertEqual(never_drop, {"created", "title", "status"})

    def test_absolute_beats_the_sort_pin(self):
        selection = columns.parse("title", VALID)
        names, never_drop = columns.resolve(selection, ("status", "title"), pin=("created",))
        self.assertEqual(names, ["title"])
        self.assertNotIn("created", never_drop)


class ResolveRelativeTests(unittest.TestCase):
    def test_no_op_selection_pins_only_the_sort_key(self):
        names, never_drop = columns.resolve(
            _no_op_selection(), ("status", "title", "created"), pin=("created",)
        )
        self.assertEqual(names, ["status", "title", "created"])
        self.assertEqual(never_drop, {"created"})

    def test_remove_drops_from_the_default_set(self):
        selection = columns.parse("-status", VALID)
        names, _ = columns.resolve(selection, ("status", "title", "created"), pin=())
        self.assertEqual(names, ["title", "created"])

    def test_add_appends_and_pins_a_name_missing_from_the_default_set(self):
        selection = columns.parse("+created", VALID)
        names, never_drop = columns.resolve(selection, ("status", "title"), pin=())
        self.assertIn("created", names)
        self.assertIn("created", never_drop)

    def test_add_pins_a_name_already_in_the_default_set(self):
        selection = columns.parse("+created", VALID)
        names, never_drop = columns.resolve(selection, ("status", "created"), pin=())
        self.assertEqual(names, ["status", "created"])
        self.assertEqual(never_drop, {"created"})

    def test_sort_pin_is_kept_alongside_relative_add(self):
        selection = columns.parse("-tags", VALID)
        names, never_drop = columns.resolve(
            selection, ("status", "tags", "created"), pin=("created",)
        )
        self.assertEqual(names, ["status", "created"])
        self.assertEqual(never_drop, {"created"})


class MissingNameTests(unittest.TestCase):
    def test_bare_sign_is_reported_as_a_missing_name(self):
        for spec in ("+", "-", "+title,-"):
            with self.assertRaises(ValueError) as ctx:
                columns.parse(spec, VALID)
            self.assertIn("missing column name", str(ctx.exception), msg=spec)


def _no_op_selection():
    return columns.Selection(absolute=None, add=frozenset(), remove=frozenset())


if __name__ == "__main__":
    unittest.main()
