import unittest
from pathlib import Path


def _extract_sample(readme_text: str, name: str) -> list[str]:
    start_marker = f"<!-- sample:{name} -->"
    start = readme_text.index(start_marker)
    end = readme_text.index("<!-- /sample -->", start)
    block = readme_text[start:end]
    fence_start = block.index("```") + 3
    fence_end = block.index("```", fence_start)
    return block[fence_start:fence_end].strip("\n").splitlines()


def _header_block(lines: list[str]) -> list[str]:
    body_start = lines.index("", 2)
    return lines[2:body_start]


class ReadmeShowSampleTests(unittest.TestCase):
    """Shape assertions only -- the fixture's dates are relative to now."""

    def setUp(self):
        readme_path = Path(__file__).parent.parent / "README.md"
        self.header = _header_block(_extract_sample(readme_path.read_text(), "show"))

    def test_id_line_holds_only_id(self):
        id_line = next(line for line in self.header if "id:" in line)
        self.assertNotIn("status:", id_line)

    def test_status_and_intent_share_a_line(self):
        state_line = next(line for line in self.header if "status:" in line)
        self.assertIn("intent:", state_line)

    def test_parent_and_project_share_a_line(self):
        lineage_line = next(line for line in self.header if "parent:" in line)
        self.assertIn("project:", lineage_line)

    def test_created_source_and_modified_share_a_line(self):
        provenance_line = next(line for line in self.header if "created:" in line)
        self.assertIn("source:", provenance_line)
        self.assertIn("modified:", provenance_line)


if __name__ == "__main__":
    unittest.main()
