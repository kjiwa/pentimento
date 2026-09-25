import json
import os
import tempfile
import unittest
from pathlib import Path

from pentimento import touches


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _restore_cache_env(previous):
    if previous is None:
        os.environ.pop("XDG_CACHE_HOME", None)
    else:
        os.environ["XDG_CACHE_HOME"] = previous


def _isolate_cache(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    previous = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = tmp.name
    test.addCleanup(_restore_cache_env, previous)


def _tool_use_record(*, slug, cwd, timestamp, tool, input_):
    return {
        "slug": slug,
        "cwd": cwd,
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": tool, "input": input_}],
        },
    }


class LoadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_cache(self)

    def test_missing_directory_yields_empty_index(self):
        result = touches.load(self.directory / "does-not-exist")
        self.assertEqual(result, {})

    def test_write_of_the_plan_itself_is_authored(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                _tool_use_record(
                    slug="some-plan-eager-bird",
                    cwd="/home/user/example",
                    timestamp="2026-09-01T00:00:00.000Z",
                    tool="Write",
                    input_={"file_path": "/home/user/.claude/plans/some-plan-eager-bird.md"},
                ),
            ],
        )
        result = touches.load(self.directory)
        self.assertIn("some-plan-eager-bird", result)
        touch = result["some-plan-eager-bird"][0]
        self.assertEqual(touch.session, "some-plan-eager-bird")
        self.assertEqual(touch.tool, "Write")
        self.assertEqual(touch.at, "2026-09-01T00:00:00.000Z")
        self.assertEqual(
            touches.authored(result["some-plan-eager-bird"], "some-plan-eager-bird"), [touch]
        )
        self.assertEqual(touches.worked(result["some-plan-eager-bird"], "some-plan-eager-bird"), [])

    def test_edit_from_a_later_differently_slugged_session_is_worked(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                _tool_use_record(
                    slug="implement-the-plan-later-fox",
                    cwd="/home/user/example",
                    timestamp="2026-09-05T00:00:00.000Z",
                    tool="Edit",
                    input_={"file_path": "/home/user/.claude/plans/some-plan-eager-bird.md"},
                ),
            ],
        )
        result = touches.load(self.directory)
        touch = result["some-plan-eager-bird"][0]
        self.assertEqual(touch.session, "implement-the-plan-later-fox")
        self.assertEqual(
            touches.worked(result["some-plan-eager-bird"], "some-plan-eager-bird"), [touch]
        )

    def test_read_from_a_later_session_is_not_worked(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                _tool_use_record(
                    slug="implement-the-plan-later-fox",
                    cwd="/home/user/example",
                    timestamp="2026-09-05T00:00:00.000Z",
                    tool="Read",
                    input_={"file_path": "/home/user/.claude/plans/some-plan-eager-bird.md"},
                ),
            ],
        )
        result = touches.load(self.directory)["some-plan-eager-bird"]
        self.assertEqual(touches.worked(result, "some-plan-eager-bird"), [])

    def test_cursor_plan_suffix_resolves_to_the_bare_id(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                _tool_use_record(
                    slug="some-session",
                    cwd="/home/user/example",
                    timestamp="2026-09-01T00:00:00.000Z",
                    tool="Edit",
                    input_={"file_path": "/home/user/.cursor/plans/cursor-plan.plan.md"},
                ),
            ],
        )
        result = touches.load(self.directory)
        self.assertIn("cursor-plan", result)

    def test_tool_outside_the_watched_set_is_ignored(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                _tool_use_record(
                    slug="some-session",
                    cwd="/home/user/example",
                    timestamp="2026-09-01T00:00:00.000Z",
                    tool="Bash",
                    input_={"command": "cat /home/user/.claude/plans/some-plan.md"},
                ),
            ],
        )
        result = touches.load(self.directory)
        self.assertEqual(result, {})

    def test_free_text_mention_without_tool_use_is_ignored(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "slug": "some-session",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "see ~/.claude/plans/some-plan.md"}],
                    },
                },
            ],
        )
        result = touches.load(self.directory)
        self.assertEqual(result, {})

    def test_subagent_transcripts_under_a_session_directory_are_included(self):
        session_dir = self.directory / "-home-user-example" / "some-uuid" / "subagents"
        session_dir.mkdir(parents=True)
        _write_jsonl(
            session_dir / "agent-abc.jsonl",
            [
                _tool_use_record(
                    slug="implement-plan-later-fox",
                    cwd="/home/user/example",
                    timestamp="2026-09-05T00:00:00.000Z",
                    tool="Task",
                    input_={"prompt": "Execute the plan at /home/user/.claude/plans/some-plan.md"},
                ),
            ],
        )
        result = touches.load(self.directory)
        self.assertIn("some-plan", result)

    def test_touches_for_a_plan_are_sorted_by_timestamp(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                _tool_use_record(
                    slug="second-session",
                    cwd="/home/user/example",
                    timestamp="2026-09-05T00:00:00.000Z",
                    tool="Read",
                    input_={"file_path": "/home/user/.claude/plans/some-plan.md"},
                ),
                _tool_use_record(
                    slug="some-plan",
                    cwd="/home/user/example",
                    timestamp="2026-09-01T00:00:00.000Z",
                    tool="Write",
                    input_={"file_path": "/home/user/.claude/plans/some-plan.md"},
                ),
            ],
        )
        result = touches.load(self.directory)
        self.assertEqual(
            [t.at for t in result["some-plan"]],
            ["2026-09-01T00:00:00.000Z", "2026-09-05T00:00:00.000Z"],
        )

    def test_malformed_json_lines_are_skipped(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        (project_dir / "session.jsonl").write_text(
            "not json but mentions /plans/ anyway\n"
            + json.dumps(
                _tool_use_record(
                    slug="some-session",
                    cwd="/home/user/example",
                    timestamp="2026-09-01T00:00:00.000Z",
                    tool="Read",
                    input_={"file_path": "/home/user/.claude/plans/some-plan.md"},
                )
            )
            + "\n"
        )
        result = touches.load(self.directory)
        self.assertIn("some-plan", result)

    def test_unreadable_or_corrupted_file_does_not_crash(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        (project_dir / "bad.jsonl").write_bytes(b"\xff\xfe\x00\x00 /plans/ not valid json\n")
        result = touches.load(self.directory)
        self.assertEqual(result, {})


class AuthorTests(unittest.TestCase):
    def _touch(self, session, tool, at):
        return touches.Touch(
            plan_id="the-plan", session=session, tool=tool, at=at, cwd="/home/user/example"
        )

    def test_author_is_the_earliest_write_session_when_no_touch_has_the_plan_id(self):
        plan_touches = [
            self._touch("borrowed-slug", "Write", "2026-09-01T00:00:00.000Z"),
            self._touch("later-slug", "Write", "2026-09-02T00:00:00.000Z"),
        ]
        self.assertEqual(touches.author(plan_touches, "the-plan"), "borrowed-slug")

    def test_author_is_the_plan_id_when_a_touch_has_it(self):
        plan_touches = [
            self._touch("borrowed-slug", "Write", "2026-09-01T00:00:00.000Z"),
            self._touch("the-plan", "Edit", "2026-09-02T00:00:00.000Z"),
        ]
        self.assertEqual(touches.author(plan_touches, "the-plan"), "the-plan")

    def test_author_is_the_plan_id_without_a_write_touch(self):
        plan_touches = [self._touch("other", "Read", "2026-09-01T00:00:00.000Z")]
        self.assertEqual(touches.author(plan_touches, "the-plan"), "the-plan")
        self.assertEqual(touches.author([], "the-plan"), "the-plan")

    def test_authored_and_worked_treat_the_writing_session_as_author(self):
        write = self._touch("borrowed-slug", "Write", "2026-09-01T00:00:00.000Z")
        edit = self._touch("borrowed-slug", "Edit", "2026-09-01T01:00:00.000Z")
        later = self._touch("later-slug", "Edit", "2026-09-02T00:00:00.000Z")
        plan_touches = [write, edit, later]
        self.assertEqual(touches.authored(plan_touches, "the-plan"), [write, edit])
        self.assertEqual(touches.worked(plan_touches, "the-plan"), [later])


class HostileRecordTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_cache(self)

    def test_non_object_lines_and_string_messages_are_skipped(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        (project_dir / "s.jsonl").write_text(
            "\n".join(
                [
                    '["/plans/x.md"]',
                    '"/plans/x.md"',
                    json.dumps({"slug": "s", "message": "/plans/x.md"}),
                    json.dumps(
                        _tool_use_record(
                            slug="s",
                            cwd="/home/user/example",
                            timestamp="2026-09-01T00:00:00.000Z",
                            tool="Read",
                            input_={"file_path": "/home/user/.claude/plans/some-plan.md"},
                        )
                    ),
                ]
            )
            + "\n"
        )
        self.assertEqual(list(touches.load(self.directory)), ["some-plan"])


if __name__ == "__main__":
    unittest.main()
