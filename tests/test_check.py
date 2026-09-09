import dataclasses
import unittest

from pentimento import check


@dataclasses.dataclass
class FakePlan:
    id: str
    status: str = "not-started"
    intent: str = "unset"
    parent: str | None = None
    project: str | None = "example"


class RunTests(unittest.TestCase):
    def test_clean_corpus_has_no_findings(self):
        root = FakePlan(id="root")
        child = FakePlan(id="child", parent="root")
        self.assertEqual(check.run([root, child]), [])

    def test_dangling_parent_is_reported(self):
        plan = FakePlan(id="orphan", parent="no-such-plan")
        findings = check.run([plan])
        self.assertEqual(len(findings), 1)
        self.assertIn("orphan", findings[0])

    def test_self_parent_is_reported(self):
        plan = FakePlan(id="loopy", parent="loopy")
        findings = check.run([plan])
        self.assertTrue(any("loopy" in f for f in findings))

    def test_cross_project_parent_is_reported(self):
        parent = FakePlan(id="parent", project="project-a")
        child = FakePlan(id="child", parent="parent", project="project-b")
        findings = check.run([parent, child])
        self.assertTrue(any("child" in f for f in findings))

    def test_cycle_is_reported(self):
        a = FakePlan(id="a", parent="b")
        b = FakePlan(id="b", parent="a")
        findings = check.run([a, b])
        self.assertTrue(any("a" in f for f in findings))
        self.assertTrue(any("b" in f for f in findings))

    def test_off_vocabulary_status_is_reported(self):
        plan = FakePlan(id="weird-status", status="bogus")
        findings = check.run([plan])
        self.assertTrue(any("weird-status" in f for f in findings))

    def test_off_vocabulary_intent_is_reported(self):
        plan = FakePlan(id="weird-intent", intent="bogus")
        findings = check.run([plan])
        self.assertTrue(any("weird-intent" in f for f in findings))


if __name__ == "__main__":
    unittest.main()
