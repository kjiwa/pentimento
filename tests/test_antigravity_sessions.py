import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pentimento import antigravity_sessions, corpus, lineage
from pentimento import plan as plan_module

HOME = Path("/home/user")
GEMINI = str(HOME / ".gemini")
REPO = str(HOME / "src" / "tools")
OTHER = str(HOME / "src" / "models")


def _request(text, extra=""):
    content = f"<USER_REQUEST>\n{text}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\n{extra}\n"
    return {"created_at": "2026-10-15T22:11:50Z", "type": "USER_INPUT", "content": content}


def _call(created_at, **args):
    """A step whose tool-call args are JSON-encoded strings, as Antigravity writes them."""
    encoded = {key: json.dumps(value) for key, value in args.items()}
    return {
        "created_at": created_at,
        "type": "PLANNER_RESPONSE",
        "tool_calls": [{"name": "run_command", "args": encoded}],
    }


class _Brain(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.brain = Path(self._tmp.name) / "brain"
        for patcher in (
            mock.patch.object(Path, "home", return_value=HOME),
            mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(Path(self._tmp.name) / "cache")}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def conversation(self, uuid, records, plan_name="plan.md", body="# Plan\n"):
        directory = self.brain / uuid
        log = directory / antigravity_sessions.TRANSCRIPT
        log.parent.mkdir(parents=True)
        log.write_text("".join(json.dumps(r) + "\n" for r in records))
        path = directory / plan_name
        path.write_text(body)
        return plan_module.load(path, source="antigravity")


class LoadTests(_Brain):
    def test_session_from_the_plans_own_transcript(self):
        plan = self.conversation(
            "aaaa",
            [
                _request("/plan Add tests", "local time"),
                _call("2026-10-15T22:12:00Z", Cwd=GEMINI + "/antigravity/scratch"),
                _call("2026-10-15T22:13:00Z", Cwd=REPO),
                _call("2026-10-15T22:25:21Z", Cwd=OTHER),
            ],
        )
        session = antigravity_sessions.load([plan])[plan.id]
        self.assertEqual(session.project, "tools")
        self.assertEqual(session.started, "2026-10-15T22:11:50Z")
        self.assertEqual(session.ended, "2026-10-15T22:25:21Z")
        self.assertEqual(session.prompt, "/plan Add tests")

    def test_prompt_is_the_first_user_input_only(self):
        plan = self.conversation("aaaa", [_request("first"), _request("second")])
        self.assertEqual(antigravity_sessions.load([plan])[plan.id].prompt, "first")

    def test_undecodable_cwd_is_kept_raw(self):
        record = {
            "created_at": "2026-10-15T22:12:00Z",
            "tool_calls": [{"args": {"Cwd": REPO}}],
        }
        plan = self.conversation("aaaa", [_request("x"), record])
        self.assertEqual(antigravity_sessions.load([plan])[plan.id].project, "tools")

    def test_no_cwd_outside_gemini_means_no_project(self):
        plan = self.conversation("aaaa", [_request("x"), _call("2026-10-15T22:12:00Z", Cwd=GEMINI)])
        self.assertEqual(antigravity_sessions.load([plan])[plan.id].project, "")

    def test_home_launch_is_resolved_from_where_the_work_landed(self):
        home_plan = self.conversation(
            "aaaa",
            [
                _request("x"),
                _call("2026-10-15T22:12:00Z", Cwd=str(HOME)),
                _call("2026-10-15T22:13:00Z", TargetFile=REPO + "/a.py"),
            ],
        )
        repo_plan = self.conversation(
            "bbbb", [_request("y"), _call("2026-10-15T22:12:00Z", Cwd=REPO)]
        )
        result = antigravity_sessions.load([home_plan, repo_plan])
        self.assertEqual(result[home_plan.id].project, "tools")

    def test_plan_without_a_transcript_gets_no_session(self):
        plan = self.conversation("aaaa", [_request("x")])
        (self.brain / "aaaa" / antigravity_sessions.TRANSCRIPT).unlink()
        self.assertEqual(antigravity_sessions.load([plan]), {})

    def test_other_sources_are_ignored(self):
        plan = self.conversation("aaaa", [_request("x")])
        plan.source = "claude"
        self.assertEqual(antigravity_sessions.load([plan]), {})

    def test_cache_is_reused_until_the_transcript_changes(self):
        plan = self.conversation("aaaa", [_request("x"), _call("2026-10-15T22:12:00Z", Cwd=REPO)])
        antigravity_sessions.load([plan])
        with mock.patch.object(antigravity_sessions, "_parse_transcript") as parse:
            antigravity_sessions.load([plan])
        parse.assert_not_called()

        log = plan.path.parent / antigravity_sessions.TRANSCRIPT
        log.write_text(log.read_text() + json.dumps(_request("later")) + "\n")
        with mock.patch.object(
            antigravity_sessions,
            "_parse_transcript",
            return_value={"started": "", "ended": "", "prompt": "", "launch": None, "paths": []},
        ) as parse:
            antigravity_sessions.load([plan])
        parse.assert_called_once()

    def test_corpus_merges_the_session_into_the_plan(self):
        self.conversation("aaaa", [_request("x"), _call("2026-10-15T22:12:00Z", Cwd=REPO)])
        with mock.patch.dict(
            os.environ,
            {
                "AGENT_PLANS_DIR": str(self.brain / "none"),
                "AGENT_SESSIONS_DIR": str(self.brain / "none"),
                "CURSOR_PLANS_DIR": str(self.brain / "none"),
                "CURSOR_SESSIONS_DIR": str(self.brain / "none"),
                "ANTIGRAVITY_BRAIN_DIR": str(self.brain),
            },
        ):
            (self.brain / "aaaa" / "plan.md.metadata.json").write_text("{}")
            plans, sessions = corpus.load_with_sessions()
        self.assertEqual([p.id for p in plans], ["plan"])
        self.assertEqual(plans[0].started, "2026-10-15T22:11:50Z")
        self.assertEqual(sessions["plan"].project, "tools")


class GenericNameTests(_Brain):
    def test_implementation_plan_ids_carry_the_conversation(self):
        first = self.conversation(
            "aaaaaaaa-1111", [_request("x")], plan_name="implementation_plan.md"
        )
        second = self.conversation(
            "bbbbbbbb-2222", [_request("y")], plan_name="implementation_plan.md"
        )
        self.assertEqual(
            [first.id, second.id], ["implementation_plan-aaaaaaaa", "implementation_plan-bbbbbbbb"]
        )
        self.assertEqual(sorted(antigravity_sessions.load([first, second])), [first.id, second.id])

    def test_other_names_and_sources_keep_the_stem(self):
        self.assertEqual(
            self.conversation("aaaa", [_request("x")], plan_name="release.md").id, "release"
        )
        path = self.brain / "aaaa" / "implementation_plan.md"
        self.assertEqual(plan_module._id_for(path, "claude"), "implementation_plan")


class LineageTests(_Brain):
    def test_follow_up_prompt_yields_its_parent(self):
        parent = self.conversation(
            "aaaa",
            [_request("import"), _call("2026-10-15T22:12:00Z", Cwd=OTHER)],
            plan_name="import_models_plan.md",
        )
        child = self.conversation(
            "bbbb",
            [
                {
                    **_request("/plan Follow-up to import_models_plan.md: iterate"),
                    "created_at": "2026-10-15T22:28:02Z",
                },
                _call("2026-10-15T22:29:00Z", Cwd=OTHER),
            ],
            plan_name="pegboard_models_iteration_plan.md",
        )
        sessions = antigravity_sessions.load([parent, child])
        for plan in (parent, child):
            plan.fields["project"] = sessions[plan.id].project
            plan.started = sessions[plan.id].started
        self.assertEqual(
            lineage.derive_parent(child, [parent, child], sessions), "import_models_plan"
        )


if __name__ == "__main__":
    unittest.main()
