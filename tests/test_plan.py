import datetime
import os
import tempfile
import unittest
from pathlib import Path

from pentimento import plan as plan_module


class ModifiedTests(unittest.TestCase):
    def test_modified_prefers_ended_over_mtime(self):
        target = plan_module.Plan(
            id="root-plan",
            path=Path("root-plan.md"),
            fields={},
            body="",
            mtime=1000.0,
            started="",
            ended="2026-09-05T00:00:00.000Z",
        )
        self.assertEqual(
            target.modified,
            datetime.datetime(2026, 9, 5, tzinfo=datetime.timezone.utc),
        )

    def test_modified_falls_back_to_mtime_when_no_ended(self):
        target = plan_module.Plan(
            id="root-plan",
            path=Path("root-plan.md"),
            fields={},
            body="",
            mtime=1000.0,
            started="",
            ended="",
        )
        self.assertEqual(
            target.modified,
            datetime.datetime.fromtimestamp(1000.0, tz=datetime.timezone.utc),
        )


class SaveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def test_save_with_keep_mtime_leaves_mtime_untouched_while_changing_bytes(self):
        path = self.directory / "root-plan.md"
        path.write_text("# Root\n")
        os.utime(path, (1000, 1000))

        target = plan_module.load(path, sessions={})
        target.fields = {"status": "complete"}
        plan_module.save(target, keep_mtime=True)

        self.assertEqual(path.stat().st_mtime, 1000)
        self.assertIn("status: complete", path.read_text())

    def test_save_without_keep_mtime_updates_mtime(self):
        path = self.directory / "root-plan.md"
        path.write_text("# Root\n")
        os.utime(path, (1000, 1000))

        target = plan_module.load(path, sessions={})
        target.fields = {"status": "complete"}
        plan_module.save(target)

        self.assertNotEqual(path.stat().st_mtime, 1000)

    def test_load_cursor_plan_id_resolution(self):
        path = self.directory / "refactor-auth.plan.md"
        path.write_text("# Refactor Auth\n", encoding="utf-8")
        target = plan_module.load(path)
        self.assertEqual(target.id, "refactor-auth")

    def test_load_utf8_encoding(self):
        path = self.directory / "unicode-plan.md"
        path.write_text("# Plan with üñîçødé\n", encoding="utf-8")
        target = plan_module.load(path)
        self.assertEqual(target.title, "Plan with üñîçødé")
class ByIdTests(unittest.TestCase):
    def test_by_id_matches_stem_and_plan_md(self):
        from pentimento import corpus

        p1 = plan_module.Plan(
            id="auth",
            path=Path("/cursor/plans/auth.plan.md"),
            fields={},
            body="# Auth",
            mtime=1000.0,
            started="",
            source="cursor",
        )
        p2 = plan_module.Plan(
            id="login",
            path=Path("/claude/plans/login.md"),
            fields={},
            body="# Login",
            mtime=1000.0,
            started="",
            source="claude",
        )
        self.assertEqual(corpus.by_id([p1, p2], "auth"), p1)
        self.assertEqual(corpus.by_id([p1, p2], "auth.plan.md"), p1)
        self.assertEqual(corpus.by_id([p1, p2], "auth.md"), p1)
        self.assertEqual(corpus.by_id([p1, p2], "login.md"), p2)
        self.assertEqual(corpus.by_id([p1, p2], "login"), p2)





if __name__ == "__main__":
    unittest.main()
