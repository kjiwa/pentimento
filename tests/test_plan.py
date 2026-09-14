import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pentimento import frontmatter
from pentimento import plan as plan_module


class BodyBelowTitleTests(unittest.TestCase):
    def test_drops_leading_h1_and_blank_lines(self):
        body = "# Title\n\n## Progress\n\nNot started.\n"
        self.assertEqual(plan_module.body_below_title(body), "## Progress\n\nNot started.\n")

    def test_skips_a_blank_separator_line_before_the_h1(self):
        body = "\n# Title\n\n## Progress\n\nNot started.\n"
        self.assertEqual(plan_module.body_below_title(body), "## Progress\n\nNot started.\n")

    def test_body_with_no_h1_is_unchanged(self):
        body = "## Progress\n\nNot started.\n"
        self.assertEqual(plan_module.body_below_title(body), body)


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

    def test_modified_prefers_a_later_mtime_over_a_stale_ended(self):
        later_mtime = datetime.datetime(2026, 9, 10, tzinfo=datetime.timezone.utc).timestamp()
        target = plan_module.Plan(
            id="root-plan",
            path=Path("root-plan.md"),
            fields={},
            body="",
            mtime=later_mtime,
            started="",
            ended="2026-09-05T00:00:00.000Z",
        )
        self.assertEqual(
            target.modified,
            datetime.datetime.fromtimestamp(later_mtime, tz=datetime.timezone.utc),
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

    def test_save_leaves_original_intact_when_serializer_raises_mid_save(self):
        path = self.directory / "root-plan.md"
        original = "# Root\n"
        path.write_text(original)

        target = plan_module.load(path, sessions={})
        target.fields = {"status": "complete"}
        with mock.patch.object(frontmatter, "serialize", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                plan_module.save(target)

        self.assertEqual(path.read_text(), original)
        tmp_files = [p for p in self.directory.iterdir() if p.name != "root-plan.md"]
        self.assertEqual(tmp_files, [])

    def test_save_preserves_permission_bits(self):
        path = self.directory / "root-plan.md"
        path.write_text("# Root\n")
        os.chmod(path, 0o640)

        target = plan_module.load(path, sessions={})
        target.fields = {"status": "complete"}
        plan_module.save(target)

        self.assertEqual(path.stat().st_mode & 0o777, 0o640)

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

    def test_has_title_true_when_h1_present(self):
        path = self.directory / "titled-plan.md"
        path.write_text("# Titled Plan\n", encoding="utf-8")
        target = plan_module.load(path)
        self.assertTrue(target.has_title)

    def test_has_title_false_when_h1_missing(self):
        path = self.directory / "titleless-plan.md"
        path.write_text("no heading here\n", encoding="utf-8")
        target = plan_module.load(path)
        self.assertFalse(target.has_title)


class TagsTests(unittest.TestCase):
    def test_tags_property_parses_frontmatter_field(self):
        target = plan_module.Plan(
            id="root-plan",
            path=Path("root-plan.md"),
            fields={"tags": "[auth, security]"},
            body="",
            mtime=1000.0,
            started="",
        )
        self.assertEqual(target.tags, ["auth", "security"])

    def test_tags_property_defaults_to_empty_list(self):
        target = plan_module.Plan(
            id="root-plan",
            path=Path("root-plan.md"),
            fields={},
            body="",
            mtime=1000.0,
            started="",
        )
        self.assertEqual(target.tags, [])


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
