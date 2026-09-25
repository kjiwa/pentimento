"""A stock install (no `pentimento:` block, no hooks, no `backfill`) shows derived fields."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pentimento import backfill, cli, corpus, touches

FIXTURES = Path(__file__).parent / "fixtures"
REMOVED_CODES = ("underived-project", "status-behind-progress", "unadopted-reference")
DERIVED_FIELDS = ("status", "intent", "parent", "project")
OLD_MTIME_NS = 1_600_000_000 * 10**9

CLAUDE_PLAN = "# Stock plan\n\n## Progress\n\n- [x] First\n- [ ] Second\n"
CLAUDE_SESSION = (
    '{"type": "assistant", "slug": "stock-plan", "cwd": "/home/user/src/stock-project",'
    ' "timestamp": "2026-01-02T03:04:05.000Z", "message": {"role": "assistant", "content":'
    ' [{"type": "tool_use", "name": "Write", "input": {"file_path": "%s"}}]}}\n'
)


def _seed_claude(root: Path) -> dict[str, str]:
    plans = root / "claude" / "plans"
    plans.mkdir(parents=True)
    plan = plans / "stock-plan.md"
    plan.write_text(CLAUDE_PLAN, encoding="utf-8")
    sessions = root / "claude-sessions" / "stock-project"
    sessions.mkdir(parents=True)
    (sessions / "stock.jsonl").write_text(CLAUDE_SESSION % plan, encoding="utf-8")
    return {
        "AGENT_PLANS_DIR": str(plans),
        "AGENT_SESSIONS_DIR": str(root / "claude-sessions"),
        "CURSOR_PLANS_DIR": str(root / "no-cursor-plans"),
        "CURSOR_SESSIONS_DIR": str(root / "no-cursor-sessions"),
    }


def _seed_cursor(root: Path) -> dict[str, str]:
    plans = root / "cursor" / "plans"
    shutil.copytree(FIXTURES / "cursor", plans, ignore=shutil.ignore_patterns("*.json", "projects"))
    return {
        "AGENT_PLANS_DIR": str(root / "no-claude-plans"),
        "AGENT_SESSIONS_DIR": str(root / "no-claude-sessions"),
        "CURSOR_PLANS_DIR": str(plans),
        "CURSOR_SESSIONS_DIR": str(FIXTURES / "cursor" / "projects"),
    }


# One row per source; a new source adds one row here (Antigravity: seed its plans and
# point its sessions directory at fixtures).
SOURCES = {
    "claude": _seed_claude,
    "cursor": _seed_cursor,
}


def _run(argv) -> tuple[str, int]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    return out.getvalue(), code or 0


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def _tree_rows(nodes, parent="") -> dict:
    rows = {}
    for node in nodes:
        rows[node["id"]] = (parent, node["status"], node["project"])
        rows.update(_tree_rows(node["children"], node["id"]))
    return rows


class StockInstallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _enter(self, name: str) -> Path:
        env = SOURCES[name](self.root)
        env["XDG_CACHE_HOME"] = str(self.root / "cache")
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        plans = Path(env["AGENT_PLANS_DIR"] if name == "claude" else env["CURSOR_PLANS_DIR"])
        for path in plans.glob("*.md"):
            os.utime(path, ns=(OLD_MTIME_NS, OLD_MTIME_NS))
        return plans

    def _expected(self) -> dict[str, dict]:
        plans, sessions = corpus.load_with_sessions()
        derived = backfill.derive_all(
            plans, sessions, touches.load(), rederive=False, recreate=False, max_status=None
        )
        return {p.id: derived[p.path] for p in plans}

    def test_source_has_no_curation(self):
        for name in SOURCES:
            with self.subTest(source=name):
                for path in self._enter(name).glob("*.md"):
                    self.assertNotIn("pentimento:", path.read_text(encoding="utf-8"))

    def test_derivation_is_nonempty(self):
        for name in SOURCES:
            with self.subTest(source=name):
                self._enter(name)
                self.assertTrue(any(f.get("project") for f in self._expected().values()))

    def test_list_matches_derivation(self):
        for name in SOURCES:
            with self.subTest(source=name):
                self._enter(name)
                expected = self._expected()
                rows = json.loads(_run(["list", "--format", "json"])[0])
                self.assertEqual({r["id"] for r in rows}, set(expected))
                for row in rows:
                    for field in DERIVED_FIELDS:
                        self.assertEqual(
                            row[field] or "", expected[row["id"]].get(field, ""), (row["id"], field)
                        )

    def test_show_matches_derivation(self):
        for name in SOURCES:
            with self.subTest(source=name):
                self._enter(name)
                expected = self._expected()
                for plan_id, fields in expected.items():
                    record = json.loads(_run(["show", plan_id, "--format", "json"])[0])[0]
                    for field in DERIVED_FIELDS:
                        self.assertEqual(
                            record[field] or "", fields.get(field, ""), (plan_id, field)
                        )

    def test_tree_matches_derivation(self):
        for name in SOURCES:
            with self.subTest(source=name):
                self._enter(name)
                expected = self._expected()
                seen = _tree_rows(json.loads(_run(["tree", "--format", "json"])[0]))
                self.assertEqual(set(seen), set(expected))
                for plan_id, (parent, status, project) in seen.items():
                    self.assertEqual(status, expected[plan_id].get("status", ""))
                    self.assertEqual(project or "", expected[plan_id].get("project", ""))
                    self.assertEqual(parent or "", expected[plan_id].get("parent", ""))

    def test_index_matches_derivation(self):
        for name in SOURCES:
            with self.subTest(source=name):
                self._enter(name)
                expected = self._expected()
                _run(["index"])
                sections = {}
                heading = ""
                for line in (
                    (corpus.plans_directory() / "INDEX.md").read_text(encoding="utf-8").splitlines()
                ):
                    if line.startswith("## "):
                        heading = line[3:]
                    elif line.startswith("- "):
                        sections.setdefault(heading, set()).add(line.rsplit("`", 2)[1])
                by_status = {}
                for plan_id, fields in expected.items():
                    by_status.setdefault(fields["status"], set()).add(plan_id)
                self.assertEqual(sections, by_status)

    def test_check_emits_no_removed_codes(self):
        for name in SOURCES:
            with self.subTest(source=name):
                self._enter(name)
                out, _ = _run(["check", "--format", "json"])
                codes = {f["code"] for f in json.loads(out)}
                self.assertFalse(codes & set(REMOVED_CODES), codes)

    def test_read_commands_leave_files_untouched(self):
        for name in SOURCES:
            with self.subTest(source=name):
                plans_dir = self._enter(name)
                plan_id = next(iter(self._expected()))
                before = _snapshot(plans_dir)
                for argv in (
                    ["list"],
                    ["show", plan_id],
                    ["tree"],
                    ["check"],
                    ["history", plan_id],
                ):
                    _run([*argv, "--color", "never"])
                self.assertEqual(_snapshot(plans_dir), before)


if __name__ == "__main__":
    unittest.main()
