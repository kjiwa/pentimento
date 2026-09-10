from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pentimento import index
from pentimento import plan as plan_module


class IndexRenderTests(unittest.TestCase):
    def test_renders_filename_when_base_dir_is_none(self):
        plan = plan_module.Plan(
            id="plan-a",
            path=Path("/claude/plans/plan-a.md"),
            fields={"status": "complete"},
            body="# Plan A\n",
            mtime=1000.0,
            started="",
        )
        rendered = index.render([plan])
        self.assertIn("- [Plan A](plan-a.md) (`plan-a`)", rendered)

    def test_renders_relative_path_when_base_dir_is_given(self):
        claude_dir = Path("/home/user/.claude/plans")
        cursor_plan_path = Path("/home/user/.cursor/plans/auth.plan.md")
        plan = plan_module.Plan(
            id="auth",
            path=cursor_plan_path,
            fields={"status": "in-progress"},
            body="# Auth Plan\n",
            mtime=1000.0,
            started="",
            source="cursor",
        )
        rendered = index.render([plan], base_dir=claude_dir)
        self.assertIn("- [Auth Plan](../../.cursor/plans/auth.plan.md) (`auth`)", rendered)

    def test_write_creates_directory_and_writes_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "sub" / "plans"
            plan = plan_module.Plan(
                id="plan-b",
                path=target_dir / "plan-b.md",
                fields={"status": "not-started"},
                body="# Plan B\n",
                mtime=1000.0,
                started="",
            )
            index.write([plan], target_dir)
            index_file = target_dir / "INDEX.md"
            self.assertTrue(index_file.is_file())
            content = index_file.read_text(encoding="utf-8")
            self.assertIn("- [Plan B](plan-b.md) (`plan-b`)", content)


if __name__ == "__main__":
    unittest.main()
