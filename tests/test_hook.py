from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from pentimento import hook


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(harness: str, name: str) -> str:
    return (FIXTURES / harness / name).read_text()


def _restore_env(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


class TouchedPlanPathTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        self.plans_dir = self.directory / "plans"
        self.plans_dir.mkdir()

        for key, value in (
            ("AGENT_PLANS_DIR", str(self.plans_dir)),
            ("CURSOR_PLANS_DIR", str(self.directory / "no-such-cursor-plans-dir")),
        ):
            previous = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(_restore_env, key, previous)

    def _payload(self, tool_name: str, file_path) -> str:
        return json.dumps({"tool_name": tool_name, "tool_input": {"file_path": file_path}})

    def test_write_payload_returns_path(self):
        path = self.plans_dir / "root-plan.md"
        self.assertEqual(hook.touched_plan_path(self._payload("Write", str(path))), path)

    def test_edit_payload_returns_path(self):
        path = self.plans_dir / "root-plan.md"
        self.assertEqual(hook.touched_plan_path(self._payload("Edit", str(path))), path)

    def test_path_outside_every_source_is_none(self):
        path = self.directory / "elsewhere" / "root-plan.md"
        self.assertIsNone(hook.touched_plan_path(self._payload("Write", str(path))))

    def test_index_md_is_none(self):
        path = self.plans_dir / "INDEX.md"
        self.assertIsNone(hook.touched_plan_path(self._payload("Write", str(path))))

    def test_readme_md_is_none(self):
        path = self.plans_dir / "README.md"
        self.assertIsNone(hook.touched_plan_path(self._payload("Write", str(path))))

    def test_non_md_file_is_none(self):
        path = self.plans_dir / "root-plan.txt"
        self.assertIsNone(hook.touched_plan_path(self._payload("Write", str(path))))

    def test_nested_subdirectory_is_none(self):
        nested = self.plans_dir / "nested"
        nested.mkdir()
        path = nested / "root-plan.md"
        self.assertIsNone(hook.touched_plan_path(self._payload("Write", str(path))))

    def test_tilde_prefixed_path_expands(self):
        home_plans = Path.home() / ".claude" / "plans-test-marker"
        # Use the configured plans dir itself via a literal ~ prefix isn't meaningful
        # unless AGENT_PLANS_DIR is under $HOME; instead verify expansion happens by
        # pointing AGENT_PLANS_DIR at a directory under HOME.
        del home_plans
        home_plans_dir = Path.home() / "pentimento-hook-test-plans"
        previous = os.environ.get("AGENT_PLANS_DIR")
        os.environ["AGENT_PLANS_DIR"] = str(home_plans_dir)
        self.addCleanup(_restore_env, "AGENT_PLANS_DIR", previous)

        rel = "~/pentimento-hook-test-plans/root-plan.md"
        result = hook.touched_plan_path(self._payload("Write", rel))
        self.assertEqual(result, home_plans_dir / "root-plan.md")

    def test_cursor_plan_md_under_cursor_plans_dir(self):
        cursor_dir = self.directory / "cursor-plans"
        cursor_dir.mkdir()
        previous = os.environ.get("CURSOR_PLANS_DIR")
        os.environ["CURSOR_PLANS_DIR"] = str(cursor_dir)
        self.addCleanup(_restore_env, "CURSOR_PLANS_DIR", previous)

        path = cursor_dir / "refactor-auth.plan.md"
        self.assertEqual(hook.touched_plan_path(self._payload("Write", str(path))), path)

    def test_claude_post_tool_use_write_fixture_returns_path(self):
        plans_dir = Path("/home/user/.claude/plans")
        os.environ["AGENT_PLANS_DIR"] = str(plans_dir)
        result = hook.touched_plan_path(_fixture("claude", "post-tool-use-write.json"))
        self.assertEqual(result, plans_dir / "what-do-you-think-cozy-twilight.md")

    def test_cursor_payloads_name_no_plan_file(self):
        os.environ["CURSOR_PLANS_DIR"] = "/home/user/.cursor/plans"
        for name in sorted(p.name for p in (FIXTURES / "cursor").glob("*.json")):
            with self.subTest(name):
                self.assertIsNone(hook.touched_plan_path(_fixture("cursor", name)))

    def test_empty_string_is_none(self):
        self.assertIsNone(hook.touched_plan_path(""))

    def test_not_json_is_none(self):
        self.assertIsNone(hook.touched_plan_path("not json"))

    def test_json_null_is_none(self):
        self.assertIsNone(hook.touched_plan_path("null"))

    def test_json_array_is_none(self):
        self.assertIsNone(hook.touched_plan_path("[]"))

    def test_json_number_is_none(self):
        self.assertIsNone(hook.touched_plan_path("3"))

    def test_empty_tool_input_is_none(self):
        self.assertIsNone(hook.touched_plan_path(json.dumps({"tool_input": {}})))

    def test_non_string_file_path_is_none(self):
        self.assertIsNone(hook.touched_plan_path(json.dumps({"tool_input": {"file_path": 5}})))


if __name__ == "__main__":
    unittest.main()
