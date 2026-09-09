import json
import tempfile
import unittest
from pathlib import Path

from pentimento import sessions


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


class LoadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def test_missing_directory_yields_empty_index(self):
        result = sessions.load(self.directory / "does-not-exist")
        self.assertEqual(result, {})

    def test_loads_slug_project_started_and_prompt(self):
        project_dir = self.directory / "-Users-kjiwa-src-github-kjiwa-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "some-plan-eager-bird",
                    "cwd": "/Users/kjiwa/src/github/kjiwa/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": [{"type": "text", "text": "do the thing"}]},
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
        project_dir = self.directory / "-Users-kjiwa-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/Users/kjiwa/example",
                    "timestamp": "2026-09-02T00:00:00.000Z",
                    "message": {"role": "user", "content": "second prompt"},
                },
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/Users/kjiwa/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "first prompt"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-a"].started, "2026-09-01T00:00:00.000Z")
        self.assertEqual(result["plan-a"].prompt, "first prompt")

    def test_ended_is_the_max_timestamp_across_a_slugs_lines(self):
        project_dir = self.directory / "-Users-kjiwa-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/Users/kjiwa/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "first"},
                },
                {
                    "type": "assistant",
                    "slug": "plan-a",
                    "cwd": "/Users/kjiwa/example",
                    "timestamp": "2026-09-03T00:00:00.000Z",
                    "message": {"role": "assistant", "content": "last"},
                },
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/Users/kjiwa/example",
                    "timestamp": "2026-09-02T00:00:00.000Z",
                    "message": {"role": "user", "content": "middle"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-a"].ended, "2026-09-03T00:00:00.000Z")

    def test_ended_is_the_max_timestamp_across_multiple_logs(self):
        project_dir = self.directory / "-Users-kjiwa-example"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session-1.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-a",
                    "cwd": "/Users/kjiwa/example",
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
                    "cwd": "/Users/kjiwa/example",
                    "timestamp": "2026-09-05T00:00:00.000Z",
                    "message": {"role": "user", "content": "resumed"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-a"].ended, "2026-09-05T00:00:00.000Z")

    def test_malformed_json_lines_are_skipped(self):
        project_dir = self.directory / "-Users-kjiwa-example"
        project_dir.mkdir()
        (project_dir / "session.jsonl").write_text(
            "not json\n"
            + json.dumps(
                {
                    "type": "user",
                    "slug": "plan-b",
                    "cwd": "/Users/kjiwa/example",
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "hello"},
                }
            )
            + "\n"
        )
        result = sessions.load(self.directory)
        self.assertIn("plan-b", result)

    def test_home_cwd_maps_to_home_project(self):
        project_dir = self.directory / "-Users-kjiwa"
        project_dir.mkdir()
        _write_jsonl(
            project_dir / "session.jsonl",
            [
                {
                    "type": "user",
                    "slug": "plan-c",
                    "cwd": str(Path.home()),
                    "timestamp": "2026-09-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "hi"},
                },
            ],
        )
        result = sessions.load(self.directory)
        self.assertEqual(result["plan-c"].project, "home")


if __name__ == "__main__":
    unittest.main()
