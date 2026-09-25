from __future__ import annotations

import dataclasses
import datetime
import re
import unittest
from pathlib import Path
from unittest import mock

from pentimento import style, tree


@dataclasses.dataclass
class FakePlan:
    id: str
    title: str
    status: str = "not-started"
    pinned: bool = False
    intent: str = "unset"
    tags: list = dataclasses.field(default_factory=list)
    parent: str | None = None
    project: str | None = "example"
    source: str = "claude"
    path: Path = Path("fake.md")
    started: str = "2026-01-01T00:00:00.000Z"
    mtime: float = 0.0
    fields: dict = dataclasses.field(default_factory=dict)
    findings: list = dataclasses.field(default_factory=list)
    created: str | None = None

    @property
    def modified(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.mtime, tz=datetime.timezone.utc)


class FlattenTests(unittest.TestCase):
    def test_flatten_lists_every_plan_depth_first_without_children(self):
        plans = [
            FakePlan(id="root-a", title="A"),
            FakePlan(id="kid-a1", title="A1", parent="root-a"),
            FakePlan(id="deep-a1x", title="A1x", parent="kid-a1"),
            FakePlan(id="kid-a2", title="A2", parent="root-a"),
            FakePlan(id="root-b", title="B"),
        ]
        records = tree.as_records(plans, key=lambda p: p.id)
        rows = tree.flatten(records)
        self.assertEqual(
            [row["id"] for row in rows], ["root-a", "kid-a1", "deep-a1x", "kid-a2", "root-b"]
        )
        self.assertTrue(all("children" not in row for row in rows))
        self.assertEqual(rows[1]["parent"], "root-a")


def _with_width(width, fn):
    with mock.patch("pentimento.style.terminal_width", return_value=width):
        return fn()


class RenderTests(unittest.TestCase):
    def test_node_shape_is_title_then_metadata(self):
        root = FakePlan(id="root", title="Root Plan")
        lines = _with_width(120, lambda: tree.render([root])).split("\n")
        self.assertEqual(lines[0], "`-- Root Plan")
        self.assertTrue(lines[1].startswith("      root  "))

    def test_meta_line_shows_the_short_id(self):
        root = FakePlan(id="is-it-possible-to-abundant-rabbit", title="Root Plan")
        other = FakePlan(id="some-other-plan-id", title="Other")
        lines = _with_width(120, lambda: tree.render([root, other])).split("\n")
        self.assertIn("abundant-rabbit", lines[1])
        self.assertNotIn("is-it-possible-to-abundant-rabbit", lines[1])

    def test_two_children_use_branch_and_final_connectors(self):
        root = FakePlan(id="root", title="Root")
        a = FakePlan(id="a", title="A", parent="root")
        b = FakePlan(id="b", title="B", parent="root")
        lines = _with_width(120, lambda: tree.render([root, a, b])).split("\n")
        self.assertTrue(lines[2].startswith("    |-- A"))
        self.assertTrue(lines[4].startswith("    `-- B"))

    def test_promoted_root_is_annotated_with_elided_parent(self):
        orphan = FakePlan(id="orphan", title="Orphan", parent="missing-parent")
        lines = _with_width(120, lambda: tree.render([orphan])).split("\n")
        self.assertIn("(parent elided: missing-parent)", lines[1])

    def test_elided_parent_annotation_is_never_cut_with_the_title(self):
        orphan = FakePlan(id="orphan", title="A long title " * 5, parent="missing-parent")
        for width in (40, 60, None):
            rendered = _with_width(width, lambda: tree.render([orphan]))
            text = " ".join(line.strip() for line in rendered.split("\n")[1:])
            self.assertIn("(parent elided: missing-parent)", text, f"width={width}")

    def test_cycle_is_annotated(self):
        a = FakePlan(id="a", title="A", parent="b")
        b = FakePlan(id="b", title="B", parent="a")
        rendered = _with_width(120, lambda: tree.render([a, b]))
        self.assertIn("(cycle)", rendered)

    def test_render_grouped_always_shows_status_and_intent(self):
        p1 = FakePlan(id="p1a", title="P1A", project="p1", status="not-started", intent="unset")
        p2 = FakePlan(id="p2a", title="P2A", project="p2", status="complete", intent="active")
        rendered = _with_width(120, lambda: tree.render_grouped([p1, p2]))
        self.assertIn("not-started", rendered)
        self.assertIn("unset", rendered)
        self.assertIn("complete", rendered)
        self.assertIn("active", rendered)

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
        rendered = _with_width(
            120, lambda: tree.render([root, a, b], key=lambda p: p.mtime, reverse=True)
        )
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

    def test_meta_line_field_order_is_id_status_intent_tags_created_age(self):
        root = FakePlan(
            id="root",
            title="Root",
            tags=["auth"],
            created="2026-01-01",
            mtime=1,
        )
        lines = _with_width(120, lambda: tree.render([root])).split("\n")
        meta = lines[1]
        self.assertLess(meta.index("root"), meta.index("not-started"))
        self.assertLess(meta.index("not-started"), meta.index("unset"))
        self.assertLess(meta.index("unset"), meta.index("[auth]"))
        self.assertLess(meta.index("[auth]"), meta.index("2026-01-01"))
        self.assertLess(meta.index("2026-01-01") + len("2026-01-01"), len(meta))

    def test_meta_line_shows_created_stamp_when_present(self):
        root = FakePlan(id="root", title="Root", created="2026-01-01")
        lines = _with_width(120, lambda: tree.render([root])).split("\n")
        self.assertIn("2026-01-01", lines[1])

    def test_meta_line_omits_created_stamp_when_absent(self):
        root = FakePlan(id="root", title="Root")
        lines = _with_width(120, lambda: tree.render([root])).split("\n")
        self.assertNotIn("2026-", lines[1])

    def test_narrow_width_with_color_fits_after_stripping_escapes_and_balances_them(self):
        root = FakePlan(
            id="root",
            title="Root",
            status="complete",
            intent="active",
            tags=["auth", "security"],
            created="2026-01-01",
            mtime=1,
        )
        for width in range(20, 60):
            rendered = _with_width(width, lambda: tree.render([root], on_color=True))
            meta = rendered.split("\n")[1]
            stripped = re.sub(r"\033\[[0-9;]*m", "", meta)
            self.assertLessEqual(style.display_width(stripped), width)
            self.assertNotIn("\033", stripped)


class FitGuaranteeTests(unittest.TestCase):
    def _plans(self):
        root = FakePlan(
            id="api-auth-redesign", title="Redesign the auth API", status="complete", mtime=1
        )
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


class LayoutTests(unittest.TestCase):
    def _plan(self):
        return FakePlan(
            id="api-auth-rollout",
            title="Roll out the new auth API across every service",
            status="partial",
            intent="active",
            tags=["auth", "security", "platform"],
            created="2026-01-02",
            mtime=2,
        )

    def _meta_fields(self, width):
        rendered = _with_width(width, lambda: tree.render([self._plan()]))
        return rendered.split("\n")[1:]

    def test_every_meta_field_survives_every_width_in_order(self):
        for width in (40, 60, 110, 140, None):
            text = " ".join(self._meta_fields(width))
            positions = [
                text.index(field)
                for field in (
                    "auth-rollout",
                    "partial",
                    "active",
                    "[auth, security, platform]",
                    "2026-01-02",
                )
            ]
            self.assertEqual(positions, sorted(positions), f"width={width}")
            self.assertRegex(text, r"\d+y", f"width={width}")

    def test_meta_line_wraps_under_its_own_indent(self):
        lines = self._meta_fields(40)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(line.startswith("      ") for line in lines))

    def test_title_truncates_with_an_ellipsis(self):
        title = _with_width(40, lambda: tree.render([self._plan()])).split("\n")[0]
        self.assertTrue(title.endswith("..."))
        self.assertLessEqual(style.display_width(title), 40)

    def test_unbounded_width_shortens_nothing(self):
        lines = _with_width(None, lambda: tree.render([self._plan()])).split("\n")
        self.assertEqual(len(lines), 2)
        self.assertIn("across every service", lines[0])


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


class SubtreeTests(unittest.TestCase):
    def test_returns_root_plus_all_descendants(self):
        root = FakePlan(id="root", title="Root")
        child = FakePlan(id="child", title="Child", parent="root")
        grandchild = FakePlan(id="grandchild", title="Grandchild", parent="child")
        result = tree.subtree([root, child, grandchild], root)
        self.assertEqual({p.id for p in result}, {"root", "child", "grandchild"})

    def test_excludes_siblings_and_ancestors(self):
        grandparent = FakePlan(id="grandparent", title="Grandparent")
        parent = FakePlan(id="parent", title="Parent", parent="grandparent")
        sibling = FakePlan(id="sibling", title="Sibling", parent="grandparent")
        target = FakePlan(id="target", title="Target", parent="parent")
        result = tree.subtree([grandparent, parent, sibling, target], parent)
        self.assertEqual({p.id for p in result}, {"parent", "target"})

    def test_leaf_returns_itself_alone(self):
        leaf = FakePlan(id="leaf", title="Leaf")
        other = FakePlan(id="other", title="Other")
        result = tree.subtree([leaf, other], leaf)
        self.assertEqual({p.id for p in result}, {"leaf"})

    def test_terminates_on_a_parent_cycle(self):
        a = FakePlan(id="a", title="A", parent="b")
        b = FakePlan(id="b", title="B", parent="a")
        result = tree.subtree([a, b], a)
        self.assertEqual({p.id for p in result}, {"a", "b"})


class SpineTests(unittest.TestCase):
    def test_returns_ancestors_nearest_first(self):
        grandparent = FakePlan(id="grandparent", title="Grandparent")
        parent = FakePlan(id="parent", title="Parent", parent="grandparent")
        child = FakePlan(id="child", title="Child", parent="parent")
        chain = tree.spine([grandparent, parent, child], child)
        self.assertEqual([p.id for p in chain], ["parent", "grandparent"])

    def test_root_has_empty_spine(self):
        root = FakePlan(id="root", title="Root")
        self.assertEqual(tree.spine([root], root), [])

    def test_omits_ancestors_other_children(self):
        parent = FakePlan(id="parent", title="Parent")
        child = FakePlan(id="child", title="Child", parent="parent")
        sibling = FakePlan(id="sibling", title="Sibling", parent="parent")
        chain = tree.spine([parent, child, sibling], child)
        self.assertEqual([p.id for p in chain], ["parent"])

    def test_terminates_on_a_cycle(self):
        a = FakePlan(id="a", title="A", parent="b")
        b = FakePlan(id="b", title="B", parent="a")
        chain = tree.spine([a, b], a)
        self.assertEqual([p.id for p in chain], ["b"])

    def test_stops_where_parent_names_a_plan_outside_the_corpus(self):
        orphan = FakePlan(id="orphan", title="Orphan", parent="missing-parent")
        self.assertEqual(tree.spine([orphan], orphan), [])


class CycleRootTests(unittest.TestCase):
    def setUp(self):
        self.a = FakePlan(id="loop-a", title="A", parent="loop-b")
        self.b = FakePlan(id="loop-b", title="B", parent="loop-a")

    def test_records_root_at_the_requested_plan(self):
        records = tree.as_records([self.a, self.b], root_id="loop-b")
        self.assertEqual([r["id"] for r in records], ["loop-b"])

    def test_default_root_is_the_first_by_key(self):
        records = tree.as_records([self.a, self.b])
        self.assertEqual([r["id"] for r in records], ["loop-a"])

    def test_render_roots_at_the_requested_plan(self):
        rendered = _with_width(120, lambda: tree.render([self.a, self.b], root_id="loop-b"))
        self.assertTrue(rendered.split("\n")[0].endswith("B"))


if __name__ == "__main__":
    unittest.main()
