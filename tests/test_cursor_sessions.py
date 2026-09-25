import dataclasses
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pentimento import backfill, corpus, cursor_sessions, lineage
from pentimento import plan as plan_module

FIXTURES = Path(__file__).parent / "fixtures" / "cursor"
TRANSCRIPTS = FIXTURES / "projects"
HOME = Path("/home/user")

PARENT_ID = "skip_list_range_query_d3d1b015"
CHILD_ID = "range_vs_submap_benchmark_4a0ba26d"


def _user(query):
    text = f"<timestamp>Friday</timestamp>\n<user_query>\n{query}\n</user_query>"
    return {"role": "user", "message": {"content": [{"type": "text", "text": text}]}}


def _create_plan(name):
    block = {"type": "tool_use", "name": "CreatePlan", "input": {"name": name}}
    return {"role": "assistant", "message": {"content": [block]}}


def _read(path):
    block = {"type": "tool_use", "name": "Read", "input": {"path": path}}
    return {"role": "assistant", "message": {"content": [block]}}


def _write_transcript(root, slug, chat_id, records):
    directory = root / slug / "agent-transcripts" / chat_id
    directory.mkdir(parents=True)
    body = "\n".join(json.dumps(r) for r in records) + "\n"
    (directory / f"{chat_id}.jsonl").write_text(body)


def _plan(directory, plan_id, name, body="# Plan\n"):
    path = directory / f"{plan_id}.plan.md"
    path.write_text(f"---\nname: {name}\noverview: x\n---\n{body}")
    return plan_module.load(path, source="cursor")


class _Isolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        self.transcripts = self.directory / "projects"
        self.plans_dir = self.directory / "plans"
        self.plans_dir.mkdir()
        for patcher in (
            mock.patch.object(Path, "home", return_value=HOME),
            mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.directory / "cache")}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)


class FixtureTests(_Isolated):
    def setUp(self):
        super().setUp()
        self.plans = [
            plan_module.load(p, source="cursor") for p in sorted(FIXTURES.glob("*.plan.md"))
        ]
        self.result = cursor_sessions.load(self.plans, TRANSCRIPTS)

    def test_project_per_plan(self):
        projects = {plan_id: s.project for plan_id, s in self.result.items()}
        self.assertEqual(
            projects,
            {
                "add_dry-run_flag_c900747b": "amcrest-downloader",
                "quiet_flag_83cddd33": "dircompare",
                PARENT_ID: "java-skip-list",
                CHILD_ID: "java-skip-list",
            },
        )

    def test_started_and_ended_are_the_plans_own(self):
        for plan in self.plans:
            session = self.result[plan.id]
            self.assertEqual((session.started, session.ended), (plan.started, plan.ended))

    def test_prompt_is_the_first_user_query(self):
        self.assertTrue(self.result[PARENT_ID].prompt.startswith("Add a range query"))
        self.assertNotIn("<user_query>", self.result[PARENT_ID].prompt)

    def test_prompt_lineage_resolves_the_parent(self):
        parent = next(p for p in self.plans if p.id == PARENT_ID)
        child = next(p for p in self.plans if p.id == CHILD_ID)
        parent.started, child.started = "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"
        parent.fields["project"] = child.fields["project"] = "java-skip-list"
        child = dataclasses.replace(child, body="# Benchmark\n")
        self.assertIn("d3d1b015", self.result[CHILD_ID].prompt)
        self.assertEqual(lineage.derive_parent(child, [parent, child], self.result), PARENT_ID)

    def test_a_plan_with_no_transcript_gets_nothing(self):
        plan = _plan(self.plans_dir, "unrelated_11111111", "Unrelated plan")
        self.assertNotIn(plan.id, cursor_sessions.load([plan], TRANSCRIPTS))

    def test_ask_mode_transcript_matches_no_plan(self):
        self.assertEqual(len(self.result), 4)


class MatchTests(_Isolated):
    def _transcript(self, chat_id, name, slug="home-user-src-example", path=None):
        path = path or "/home/user/src/example/main.py"
        _write_transcript(
            self.transcripts, slug, chat_id, [_user("go"), _read(path), _create_plan(name)]
        )

    def test_two_transcripts_with_one_name_match_no_plan(self):
        self._transcript("chat-1", "Same")
        self._transcript("chat-2", "Same")
        plan = _plan(self.plans_dir, "same_aaaaaaaa", "Same")
        self.assertEqual(cursor_sessions.load([plan], self.transcripts), {})

    def test_two_plans_with_one_name_match_neither(self):
        self._transcript("chat-1", "Same")
        plans = [_plan(self.plans_dir, f"same_{c * 8}", "Same") for c in "ab"]
        self.assertEqual(cursor_sessions.load(plans, self.transcripts), {})

    def test_quoted_name_matches(self):
        self._transcript("chat-1", "Plan: the sequel")
        plan = _plan(self.plans_dir, "seq_aaaaaaaa", '"Plan: the sequel"')
        self.assertIn(plan.id, cursor_sessions.load([plan], self.transcripts))

    def test_a_slug_no_path_encodes_to_leaves_project_empty(self):
        self._transcript("chat-1", "Plan", slug="home-user-src-elsewhere")
        plan = _plan(self.plans_dir, "plan_aaaaaaaa", "Plan")
        session = cursor_sessions.load([plan], self.transcripts)[plan.id]
        self.assertEqual(session.project, "")

    def test_underscore_repo_name(self):
        self._transcript(
            "chat-1",
            "Plan",
            slug="home-user-src-unused-ami",
            path="/home/user/src/unused_ami/x.py",
        )
        plan = _plan(self.plans_dir, "plan_aaaaaaaa", "Plan")
        session = cursor_sessions.load([plan], self.transcripts)[plan.id]
        self.assertEqual(session.project, "unused_ami")

    def test_error_only_transcript_is_ignored(self):
        _write_transcript(
            self.transcripts,
            "home-user-src-example",
            "chat-1",
            [_user("go"), {"type": "turn_ended", "status": "error", "error": "quota"}],
        )
        plan = _plan(self.plans_dir, "plan_aaaaaaaa", "Plan")
        self.assertEqual(cursor_sessions.load([plan], self.transcripts), {})

    def test_missing_directory_yields_nothing(self):
        plan = _plan(self.plans_dir, "plan_aaaaaaaa", "Plan")
        self.assertEqual(cursor_sessions.load([plan], self.directory / "absent"), {})

    def test_directory_comes_from_the_environment(self):
        self._transcript("chat-1", "Plan")
        plan = _plan(self.plans_dir, "plan_aaaaaaaa", "Plan")
        with mock.patch.dict(os.environ, {"CURSOR_SESSIONS_DIR": str(self.transcripts)}):
            self.assertIn(plan.id, cursor_sessions.load([plan]))


class BackfillTests(_Isolated):
    def test_backfill_fills_project_for_cursor_plans(self):
        for path in FIXTURES.glob("*.plan.md"):
            shutil.copy(path, self.plans_dir / path.name)
        plans = corpus.load_all(self.plans_dir, sessions={})
        sessions = cursor_sessions.load(plans, TRANSCRIPTS)
        backfill.run(plans, sessions)
        reloaded = {p.id: p.project for p in corpus.load_all(self.plans_dir, sessions={})}
        self.assertEqual(
            reloaded,
            {
                "add_dry-run_flag_c900747b": "amcrest-downloader",
                "quiet_flag_83cddd33": "dircompare",
                PARENT_ID: "java-skip-list",
                CHILD_ID: "java-skip-list",
            },
        )


if __name__ == "__main__":
    unittest.main()
