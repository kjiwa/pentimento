from __future__ import annotations

import io
import unittest
from unittest import mock

from pentimento import formats, history, touches


def _touch(session, tool, at, plan_id="the-plan", cwd="/home/user/example"):
    return touches.Touch(plan_id=plan_id, session=session, tool=tool, at=at, cwd=cwd)


def _with_width(width, fn):
    with mock.patch("pentimento.style.terminal_width", return_value=width):
        return fn()


class RecordKeyOrderTests(unittest.TestCase):
    def test_record_keys_follow_the_field_order(self):
        plan_touches = [_touch("the-plan", "Write", "2026-09-01T00:00:00.000Z")]
        records = history.as_records("the-plan", plan_touches)
        self.assertEqual(tuple(records[0]), history.FIELDS)


class GroupTests(unittest.TestCase):
    def test_authoring_session_is_marked_authored(self):
        plan_touches = [_touch("the-plan", "Write", "2026-09-01T00:00:00.000Z")]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual(groups[0].what, "authored")
        self.assertEqual(groups[0].session, "the-plan")

    def test_differently_slugged_writing_session_is_marked_authored(self):
        plan_touches = [
            _touch("borrowed-slug", "Write", "2026-09-01T00:00:00.000Z"),
            _touch("later-slug", "Edit", "2026-09-05T00:00:00.000Z"),
        ]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual([g.what for g in groups], ["authored", "worked"])

    def test_other_session_with_an_edit_is_marked_worked(self):
        plan_touches = [_touch("implement-it-later", "Edit", "2026-09-05T00:00:00.000Z")]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual(groups[0].what, "worked")

    def test_other_session_with_only_reads_is_marked_read(self):
        plan_touches = [_touch("implement-it-later", "Read", "2026-09-05T00:00:00.000Z")]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual(groups[0].what, "read")

    def test_mixed_read_and_edit_session_is_marked_worked_wherever_the_edit_falls(self):
        plan_touches = [
            _touch("implement-it-later", "Read", "2026-09-05T00:00:00.000Z"),
            _touch("implement-it-later", "Edit", "2026-09-05T00:10:00.000Z"),
        ]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual(groups[0].what, "worked")

    def test_touches_within_a_session_are_counted(self):
        plan_touches = [
            _touch("implement-it-later", "Read", "2026-09-05T00:00:00.000Z"),
            _touch("implement-it-later", "Edit", "2026-09-05T00:10:00.000Z"),
        ]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].touches, 2)

    def test_sessions_group_in_first_appearance_order(self):
        plan_touches = [
            _touch("the-plan", "Write", "2026-09-01T00:00:00.000Z"),
            _touch("implement-it-later", "Read", "2026-09-05T00:00:00.000Z"),
        ]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual([g.session for g in groups], ["the-plan", "implement-it-later"])


class AsRecordsTests(unittest.TestCase):
    def test_one_record_per_session_group(self):
        plan_touches = [
            _touch("the-plan", "Write", "2026-09-01T00:00:00.000Z"),
            _touch("implement-it-later", "Edit", "2026-09-05T00:00:00.000Z"),
        ]
        records = history.as_records("the-plan", plan_touches)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["session"], "the-plan")
        self.assertEqual(records[0]["what"], "authored")
        self.assertEqual(records[1]["session"], "implement-it-later")
        self.assertEqual(records[1]["what"], "worked")

    def test_when_is_utc_whole_seconds(self):
        plan_touches = [_touch("s", "Read", "2026-09-05T00:00:00.456Z")]
        records = history.as_records("the-plan", plan_touches)
        self.assertEqual(records[0]["when"], "2026-09-05T00:00:00Z")


class FieldsTests(unittest.TestCase):
    def test_fields_matches_the_table_column_order(self):
        self.assertEqual(history.FIELDS, ("when", "what", "session", "touches"))

    def test_tsv_header_agrees_with_the_table_header(self):
        plan_touches = [_touch("implement-it-later", "Edit", "2026-09-05T00:00:00.000Z")]
        records = history.as_records("the-plan", plan_touches)
        out = io.StringIO()
        formats.emit(records, "tsv", out, history.FIELDS)
        header = out.getvalue().splitlines()[0]
        self.assertEqual(header.split("\t"), ["when", "what", "session", "touches"])


class RenderTests(unittest.TestCase):
    def test_render_lists_columns_and_sessions(self):
        plan_touches = [_touch("implement-it-later", "Edit", "2026-09-05T00:00:00.000Z")]
        rendered = _with_width(
            120, lambda: history.render("the-plan", plan_touches, on_color=False, short_ids={})
        )
        lines = rendered.split("\n")
        self.assertEqual(lines[0].split(), ["WHEN", "WHAT", "SESSION", "TOUCHES"])
        self.assertIn("implement-it-later", lines[1])
        self.assertIn("worked", lines[1])

    def test_a_narrow_width_stacks_with_every_field_kept(self):
        plan_touches = [_touch("implement-it-later", "Edit", "2026-09-05T00:00:00.000Z")]
        rendered = _with_width(
            30, lambda: history.render("the-plan", plan_touches, on_color=False, short_ids={})
        )
        lines = rendered.split("\n")
        self.assertEqual(lines[0], "implement-it-later")
        self.assertIn("worked", lines[1])
        self.assertRegex(lines[1], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        self.assertNotIn("WHEN", rendered)
        self.assertIn("touches 1", rendered)

    def test_unbounded_width_never_truncates_the_session(self):
        session = "implement-a-session-name-that-is-longer-than-any-floor"
        plan_touches = [_touch(session, "Read", "2026-09-05T00:00:00.000Z")]
        rendered = _with_width(
            None, lambda: history.render("the-plan", plan_touches, on_color=False, short_ids={})
        )
        self.assertIn(session, rendered)


class SessionShortIdTests(unittest.TestCase):
    def test_the_session_column_shows_the_short_id(self):
        session = "is-it-possible-to-abundant-rabbit"
        plan_touches = [_touch(session, "Read", "2026-09-05T00:00:00.000Z")]
        rendered = _with_width(
            120,
            lambda: history.render(
                "the-plan", plan_touches, on_color=False, short_ids={session: "abundant-rabbit"}
            ),
        )
        self.assertIn("abundant-rabbit", rendered)
        self.assertNotIn(session, rendered)


if __name__ == "__main__":
    unittest.main()
