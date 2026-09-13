from __future__ import annotations

import dataclasses
import datetime
import unittest
from pathlib import Path
from unittest import mock

from pentimento import style, tree


@dataclasses.dataclass
class FakePlan:
    id: str
    title: str
    status: str = "not-started"
    intent: str = "unset"
    tags: list = dataclasses.field(default_factory=list)
    parent: str | None = None
    project: str | None = "example"
    source: str = "claude"
    path: Path = Path("fake.md")
    started: str = "2026-01-01T00:00:00.000Z"
    mtime: float = 0.0
    fields: dict = dataclasses.field(default_factory=dict)

    @property
    def modified(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.mtime, tz=datetime.timezone.utc)


def _with_width(width, fn):
    with mock.patch("pentimento.style.terminal_width", return_value=width):
        return fn()


class RenderTests(unittest.TestCase):
    def test_node_shape_is_title_then_metadata(self):
        root = FakePlan(id="root", title="Root Plan")
        lines = _with_width(120, lambda: tree.render([root])).split("\n")
        self.assertEqual(lines[0], "`- Root Plan")
        self.assertTrue(lines[1].startswith("     root  "))

    def test_two_children_use_branch_and_final_connectors(self):
        root = FakePlan(id="root", title="Root")
        a = FakePlan(id="a", title="A", parent="root")
        b = FakePlan(id="b", title="B", parent="root")
        lines = _with_width(120, lambda: tree.render([root, a, b])).split("\n")
        self.assertTrue(lines[2].startswith("   +- A"))
        self.assertTrue(lines[4].startswith("   `- B"))

    def test_unicode_glyphs_use_box_drawing_connectors(self):
        a = FakePlan(id="a", title="A")
        b = FakePlan(id="b", title="B", parent="a")
        rendered = _with_width(
            120, lambda: tree.render([a, b], glyphs=style.GLYPHS_UNICODE, unicode_ok=True)
        )
        self.assertIn("└─ ", rendered)

    def test_promoted_root_is_annotated_with_elided_parent(self):
        orphan = FakePlan(id="orphan", title="Orphan", parent="missing-parent")
        lines = _with_width(120, lambda: tree.render([orphan])).split("\n")
        self.assertIn("(parent elided: missing-parent)", lines[0])

    def test_cycle_is_annotated(self):
        a = FakePlan(id="a", title="A", parent="b")
        b = FakePlan(id="b", title="B", parent="a")
        rendered = _with_width(120, lambda: tree.render([a, b]))
        self.assertIn("(cycle)", rendered)

    def test_render_grouped_headings_are_sorted_with_blank_line_between(self):
        p1 = FakePlan(id="p1", title="P1", project="zeta")
        p2 = FakePlan(id="p2", title="P2", project="alpha")
        rendered = _with_width(120, lambda: tree.render_grouped([p1, p2]))
        self.assertLess(rendered.index("alpha"), rendered.index("zeta"))
        self.assertIn("\n\n", rendered)

    def test_siblings_follow_the_given_sort_key(self):
        root = FakePlan(id="root", title="Root")
        a = FakePlan(id="a", title="A", parent="root", mtime=100)
        b = FakePlan(id="b", title="B", parent="root", mtime=200)
        rendered = _with_width(120, lambda: tree.render([root, a, b], key=lambda p: p.mtime, reverse=True))
        self.assertLess(rendered.index("B"), rendered.index("A"))

    def test_meta_line_shows_tags_when_present(self):
        root = FakePlan(id="root", title="Root", tags=["auth", "security"])
        lines = _with_width(120, lambda: tree.render([root])).split("\n")
        self.assertIn("[auth, security]", lines[1])

    def test_meta_line_omits_tags_when_absent(self):
        root = FakePlan(id="root", title="Root")
        lines = _with_width(120, lambda: tree.render([root])).split("\n")
        self.assertNotIn("[", lines[1])

    def test_status_and_intent_are_painted_when_color_on(self):
        root = FakePlan(id="root", title="Root", status="complete", intent="active")
        lines = _with_width(120, lambda: tree.render([root], on_color=True)).split("\n")
        self.assertIn(style.GREEN, lines[1])
        self.assertIn(style.MAGENTA, lines[1])

    def test_no_ansi_bytes_when_color_off(self):
        root = FakePlan(id="root", title="Root", status="complete", intent="active")
        rendered = _with_width(120, lambda: tree.render([root], on_color=False))
        self.assertNotIn("\033", rendered)


class FitGuaranteeTests(unittest.TestCase):
    def _plans(self):
        root = FakePlan(id="api-auth-redesign", title="Redesign the auth API", status="complete", mtime=1)
        child = FakePlan(
            id="api-auth-rollout",
            title="Roll out the new auth API",
            status="partial",
            intent="active",
            tags=["auth", "security"],
            parent="api-auth-redesign",
            mtime=2,
        )
        return [root, child]

    def test_every_line_fits_every_width(self):
        for width in range(20, 201):
            rendered = _with_width(width, lambda: tree.render(self._plans(), on_color=False))
            for line in rendered.split("\n"):
                self.assertLessEqual(
                    style.display_width(line), width, f"width={width} overflowed: {line!r}"
                )


class AsRecordsTests(unittest.TestCase):
    def test_children_nest_under_parent(self):
        root = FakePlan(id="root", title="Root")
        child = FakePlan(id="child", title="Child", parent="root")
        records = tree.as_records([root, child])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "root")
        self.assertEqual(len(records[0]["children"]), 1)
        self.assertEqual(records[0]["children"][0]["id"], "child")

    def test_cycle_does_not_recurse_forever(self):
        a = FakePlan(id="a", title="A", parent="b")
        b = FakePlan(id="b", title="B", parent="a")
        records = tree.as_records([a, b])
        self.assertTrue(records)


if __name__ == "__main__":
    unittest.main()
