from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pentimento import sources


CURSOR_FIXTURES = Path(__file__).parent / "fixtures" / "cursor"


def _restore_env(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


class _EnvIsolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

        for key in ("AGENT_PLANS_DIR", "CURSOR_PLANS_DIR"):
            previous = os.environ.get(key)
            os.environ[key] = str(self.directory / "no-such-dir")
            self.addCleanup(_restore_env, key, previous)


class ClaudeSourceTests(_EnvIsolated):
    def test_uses_agent_plans_dir(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        os.environ["AGENT_PLANS_DIR"] = str(plans_dir)
        source = sources.claude_source()
        self.assertEqual(source.directories, [plans_dir])
        self.assertEqual(source.suffix, ".md")


class CursorSourceTests(_EnvIsolated):
    def test_uses_pathsep_separated_cursor_plans_dir(self):
        first = self.directory / "one"
        second = self.directory / "two"
        os.environ["CURSOR_PLANS_DIR"] = os.pathsep.join([str(first), str(second)])
        source = sources.cursor_source()
        self.assertEqual(source.directories, [first, second])
        self.assertEqual(source.suffix, ".plan.md")


class FilesTests(_EnvIsolated):
    def test_missing_directory_contributes_nothing(self):
        source = sources.Source(
            name="claude",
            directories=[self.directory / "missing"],
            suffix=".md",
            strip_suffix=".md",
        )
        self.assertEqual(sources.files(source), [])

    def test_claude_source_excludes_readme_and_index(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        (plans_dir / "root-plan.md").write_text("# Root\n")
        (plans_dir / "README.md").write_text("# readme\n")
        (plans_dir / "INDEX.md").write_text("# index\n")
        source = sources.Source(
            name="claude", directories=[plans_dir], suffix=".md", strip_suffix=".md"
        )
        found = sources.files(source)
        self.assertEqual([p.name for p in found], ["root-plan.md"])

    def test_cursor_source_matches_plan_md_suffix(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        (plans_dir / "refactor-auth.plan.md").write_text("# Refactor auth\n")
        (plans_dir / "notes.md").write_text("# not a plan\n")
        source = sources.Source(
            name="cursor", directories=[plans_dir], suffix=".plan.md", strip_suffix=".plan.md"
        )
        found = sources.files(source)
        self.assertEqual([p.name for p in found], ["refactor-auth.plan.md"])


class AllSourcesTests(_EnvIsolated):
    def test_returns_claude_and_cursor(self):
        found = sources.all_sources()
        self.assertEqual([s.name for s in found], ["claude", "cursor"])


class ContainsTests(_EnvIsolated):
    def test_matching_file_in_directory(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        source = sources.Source(
            name="claude", directories=[plans_dir], suffix=".md", strip_suffix=".md"
        )
        self.assertTrue(sources.contains(source, plans_dir / "root-plan.md"))

    def test_file_need_not_exist(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        source = sources.Source(
            name="claude", directories=[plans_dir], suffix=".md", strip_suffix=".md"
        )
        self.assertTrue(sources.contains(source, plans_dir / "not-yet-written.md"))

    def test_excluded_filename_is_false(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        source = sources.Source(
            name="claude", directories=[plans_dir], suffix=".md", strip_suffix=".md"
        )
        self.assertFalse(sources.contains(source, plans_dir / "README.md"))
        self.assertFalse(sources.contains(source, plans_dir / "INDEX.md"))

    def test_wrong_suffix_is_false(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        source = sources.Source(
            name="cursor", directories=[plans_dir], suffix=".plan.md", strip_suffix=".plan.md"
        )
        self.assertFalse(sources.contains(source, plans_dir / "notes.md"))

    def test_nested_subdirectory_is_false(self):
        plans_dir = self.directory / "plans"
        nested = plans_dir / "nested"
        nested.mkdir(parents=True)
        source = sources.Source(
            name="claude", directories=[plans_dir], suffix=".md", strip_suffix=".md"
        )
        self.assertFalse(sources.contains(source, nested / "root-plan.md"))

    def test_outside_every_directory_is_false(self):
        plans_dir = self.directory / "plans"
        plans_dir.mkdir()
        other = self.directory / "elsewhere"
        other.mkdir()
        source = sources.Source(
            name="claude", directories=[plans_dir], suffix=".md", strip_suffix=".md"
        )
        self.assertFalse(sources.contains(source, other / "root-plan.md"))


class DiscoverTests(_EnvIsolated):
    def test_real_cursor_plans_are_discovered_by_suffix(self):
        os.environ["CURSOR_PLANS_DIR"] = str(CURSOR_FIXTURES)
        names = sorted(p.name for name, p in sources.discover() if name == "cursor")
        self.assertEqual(
            names,
            [
                "add_dry-run_flag_c900747b.plan.md",
                "quiet_flag_83cddd33.plan.md",
                "range_vs_submap_benchmark_4a0ba26d.plan.md",
                "skip_list_range_query_d3d1b015.plan.md",
            ],
        )

    def test_pairs_carry_source_name(self):
        claude_dir = self.directory / "claude-plans"
        claude_dir.mkdir()
        (claude_dir / "root-plan.md").write_text("# Root\n")
        cursor_dir = self.directory / "cursor-plans"
        cursor_dir.mkdir()
        (cursor_dir / "refactor-auth.plan.md").write_text("# Refactor auth\n")

        os.environ["AGENT_PLANS_DIR"] = str(claude_dir)
        os.environ["CURSOR_PLANS_DIR"] = str(cursor_dir)

        pairs = sources.discover()
        self.assertIn(("claude", claude_dir / "root-plan.md"), pairs)
        self.assertIn(("cursor", cursor_dir / "refactor-auth.plan.md"), pairs)

    def test_absent_directories_yield_nothing(self):
        self.assertEqual(sources.discover(), [])


if __name__ == "__main__":
    unittest.main()
