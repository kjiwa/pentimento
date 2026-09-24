import json
import os
import tempfile
import unittest
from pathlib import Path

from pentimento import sessions


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


class LoadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_cache(self)

    def test_missing_directory_yields_empty_index(self):
        result = sessions.load(self.directory / "does-not-exist")
        self.assertEqual(result, {})

    def test_loads_slug_project_started_and_prompt(self):
        project_dir = self.directory / "-home-user-src-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "some-plan-eager-bird",
                    "cwd": "/home/user/src/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "do the thing"}],
                    },
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertIn("some-plan-eager-bird", result)
        session = result["some-plan-eager-bird"]
        self.assertEqual(session.project, "example")
        self.assertEqual(session.started, "2026-09-01T00:00:00.000Z")
        self.assertEqual(session.prompt, "do the thing")

    def test_earliest_timestamp_and_first_user_prompt_win(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-02T00:00:00.000Z",
                    "message": {"role": "user", "content": "second prompt"},
                },
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "first prompt"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-a"].started, "2026-09-01T00:00:00.000Z")
        self.assertEqual(result["plan-a"].prompt, "first prompt")

    def test_ended_is_the_max_timestamp_across_a_slugs_lines(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "first"},
                },
                {
                    "type": "assistant",
                    "slug": "plan-a",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-03T00:00:00.000Z",
                    "message": {"role": "assistant", "content": "last"},
                },
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-02T00:00:00.000Z",
                    "message": {"role": "user", "content": "middle"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-a"].ended, "2026-09-03T00:00:00.000Z")

    def test_ended_is_the_max_timestamp_across_multiple_logs(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session-1.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "first"},
                },
            ],
        )
        _write_jsonl(
            project_dir / "session-2.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-05T00:00:00.000Z",
                    "message": {"role": "user", "content": "resumed"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-a"].ended, "2026-09-05T00:00:00.000Z")

    def test_malformed_json_lines_are_skipped(self):
        project_dir = self.directory / "-home-user-example"
        project_dir.mkdir()
        (project_dir / "session.jsonl").write_text(
            "not json\n"
            + json.dumps(
                {
                    "type": "user",
                    "slug": "plan-b",
                    "cwd": "/home/user/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "hello"},
                }
            )
            + "\n"
        )
        result = sessions.load(self.directory)
        self.assertIn("plan-b", result)

    def _home_session(self, slug, cwds, tool_paths=(), name="session"):
        project_dir = self.directory / "-home"
        project_dir.mkdir(exist_ok=True)
        records = [
            {"type": "user", "slug": slug, "cwd": cwd, "timestamp": f"2026-09-01T00:00:0{i}.000Z"}
            for i, cwd in enumerate(cwds)
        ]
        records.extend(
            {
                "type": "assistant",
                "slug": slug,
                "cwd": cwds[0],
                "timestamp": "2026-09-01T00:01:00.000Z",
                "message": {
                    "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": t}}]
                },
            }
            for t in tool_paths
        )
        _write_jsonl(project_dir / f"{name}.jsonl", records)

    def test_home_session_without_evidence_is_named_for_home(self):
        home = Path.home()
        self._home_session("plan-c", [str(home)])
        self.assertEqual(sessions.load(self.directory)["plan-c"].project, home.name)

    def test_home_session_takes_launch_root_of_its_cwds(self):
        home = Path.home()
        self._home_session("launcher", [str(home / "src" / "app")], name="launcher")
        self._home_session("plan-d", [str(home), str(home / "src" / "app" / "lib")], name="d")
        self.assertEqual(sessions.load(self.directory)["plan-d"].project, "app")

    def test_home_session_takes_launch_root_of_tool_paths(self):
        home = Path.home()
        self._home_session("launcher", [str(home / "src" / "app")], name="launcher")
        self._home_session("plan-e", [str(home)], [str(home / "src" / "app" / "x.py")], name="e")
        self.assertEqual(sessions.load(self.directory)["plan-e"].project, "app")

    def test_home_session_prefers_outermost_launch_root(self):
        home = Path.home()
        self._home_session("outer", [str(home / "src" / "app")], name="outer")
        self._home_session("inner", [str(home / "src" / "app" / "core")], name="inner")
        self._home_session(
            "plan-f", [str(home)], [str(home / "src" / "app" / "core" / "x")], name="f"
        )
        self.assertEqual(sessions.load(self.directory)["plan-f"].project, "app")

    def test_home_session_ignores_paths_outside_launch_roots(self):
        home = Path.home()
        self._home_session("launcher", [str(home / "src" / "app")], name="launcher")
        self._home_session(
            "plan-g",
            [str(home)],
            [str(home / "src" / "app" / "x"), str(home / "Downloads" / "shot.png")],
            name="g",
        )
        self.assertEqual(sessions.load(self.directory)["plan-g"].project, "app")

    def test_home_session_stays_home_on_tied_launch_roots(self):
        home = Path.home()
        self._home_session("a", [str(home / "src" / "a")], name="a")
        self._home_session("b", [str(home / "src" / "b")], name="b")
        self._home_session(
            "plan-h",
            [str(home)],
            [str(home / "src" / "a" / "x"), str(home / "src" / "b" / "y")],
            name="h",
        )
        self.assertEqual(sessions.load(self.directory)["plan-h"].project, home.name)

    def test_session_launched_in_home_directory_root_can_be_a_project(self):
        home = Path.home()
        self._home_session("plan-i", [str(home)], [str(home / ".claude" / "x")], name="i")
        self._home_session("claude", [str(home / ".claude")], name="claude")
        self.assertEqual(sessions.load(self.directory)["plan-i"].project, ".claude")

    def test_project_is_isolated_per_slug(self):
        project_dir = self.directory / "-home-user-src"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/home/user/src/project-a",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "hi a"},
                },
                {
                    "type": "user",
                    "slug": "plan-b",
                    "cwd": "/home/user/src/project-b",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "hi b"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-a"].project, "project-a")
        self.assertEqual(result["plan-b"].project, "project-b")

    def test_unreadable_or_corrupted_file_does_not_crash(self):
        project_dir = self.directory / "-home-user"
        project_dir.mkdir()
        (project_dir / "bad.jsonl").write_bytes(b"\xff\xfe\x00\x00not valid json\n")
        result = sessions.load(self.directory)
        self.assertEqual(result, {})


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
                    "[1, 2]",
                    '"just a string"',
                    "42",
                    "null",
                    json.dumps(
                        {
                            "type": "user",
                            "slug": "ok-plan",
                            "cwd": "/home/user/example",
                            "timestamp": "2026-09-01T00:00:00.000Z",
                            "message": "not an object",
                        }
                    ),
                ]
            )
            + "\n"
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["ok-plan"].project, "example")
        self.assertEqual(result["ok-plan"].prompt, "")


class ProjectNameTests(unittest.TestCase):
    def test_malformed_relative_cwd_mixed_with_absolute_does_not_crash(self):
        name = sessions._project_name(["not/absolute", "/home/user/src/project-a"], [], set())
        self.assertEqual(name, "project-a")

    def test_all_relative_cwds_yield_empty_project(self):
        self.assertEqual(sessions._project_name(["relative/one", "relative/two"], [], set()), "")


if __name__ == "__main__":
    unittest.main()
