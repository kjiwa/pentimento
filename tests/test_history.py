from __future__ import annotations

import unittest
from unittest import mock

from pentimento import history, touches


def _touch(session, tool, at, plan_id="the-plan", cwd="/Users/kjiwa/example"):
    return touches.Touch(plan_id=plan_id, session=session, tool=tool, at=at, cwd=cwd)


def _with_width(width, fn):
    with mock.patch("pentimento.style.terminal_width", return_value=width):
        return fn()


class GroupTests(unittest.TestCase):
    def test_authoring_session_is_marked_authored(self):
        plan_touches = [_touch("the-plan", "Write", "2026-09-01T00:00:00.000Z")]
        groups = history.group("the-plan", plan_touches)
        self.assertEqual(groups[0].what, "authored")
        self.assertEqual(groups[0].session, "the-plan")

    def test_other_session_is_marked_worked(self):
        plan_touches = [_touch("implement-it-later", "Read", "2026-09-05T00:00:00.000Z")]
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
            _touch("implement-it-later", "Read", "2026-09-05T00:00:00.000Z"),
        ]
        records = history.as_records("the-plan", plan_touches)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["session"], "the-plan")
        self.assertEqual(records[0]["what"], "authored")
        self.assertEqual(records[1]["session"], "implement-it-later")
        self.assertEqual(records[1]["what"], "worked")


class RenderTests(unittest.TestCase):
    def test_render_lists_columns_and_sessions(self):
        plan_touches = [_touch("implement-it-later", "Read", "2026-09-05T00:00:00.000Z")]
        rendered = _with_width(120, lambda: history.render("the-plan", plan_touches, on_color=False))
        lines = rendered.split("\n")
        self.assertEqual(lines[0].split(), ["WHEN", "WHAT", "SESSION", "TOUCHES"])
        self.assertIn("implement-it-later", lines[1])
        self.assertIn("worked", lines[1])


if __name__ == "__main__":
    unittest.main()
