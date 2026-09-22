import re
import unittest
from pathlib import Path

from pentimento import cli
from tests import _header_block, _subparsers_action

_FLAG_RE = re.compile(r"(-{1,2}[a-zA-Z][\w-]*)(?:\s+([A-Za-z0-9_|]+))?")


def _extract_commands_block(readme_text: str) -> list[str]:
    start = readme_text.index("## Commands")
    fence_start = readme_text.index("```", start) + 3
    fence_end = readme_text.index("```", fence_start)
    lines = readme_text[fence_start:fence_end].strip("\n").splitlines()
    return [
        line
        for line in lines
        if line.startswith("pentimento ") and not line.split()[1].startswith("-")
    ]


def _extract_sample(readme_text: str, name: str) -> list[str]:
    start_marker = f"<!-- sample:{name} -->"
    start = readme_text.index(start_marker)
    end = readme_text.index("<!-- /sample -->", start)
    block = readme_text[start:end]
    fence_start = block.index("```") + 3
    fence_end = block.index("```", fence_start)
    return block[fence_start:fence_end].strip("\n").splitlines()


class ReadmeShowSampleTests(unittest.TestCase):
    """Shape assertions only -- the fixture's dates are relative to now."""

    def setUp(self):
        readme_path = Path(__file__).parent.parent / "README.md"
        self.header = _header_block(_extract_sample(readme_path.read_text(), "show"))

    def test_id_line_holds_only_id(self):
        id_line = next(line for line in self.header if "id:" in line)
        self.assertNotIn("status:", id_line)

    def test_path_follows_id_on_its_own_line(self):
        path_line = next(line for line in self.header if "path:" in line)
        self.assertTrue(path_line.startswith("path: ~/.claude/plans/"))
        self.assertNotIn("id:", path_line)

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


class ReadmeCommandsTests(unittest.TestCase):
    """The `## Commands` block's flags must match the parser exactly."""

    def setUp(self):
        reference_path = Path(__file__).parent.parent / "docs" / "reference.md"
        self.lines = _extract_commands_block(reference_path.read_text())
        parser = cli.build_parser()
        subparsers_action = _subparsers_action(parser)
        self.subparsers = subparsers_action.choices

    def test_every_subcommand_is_listed(self):
        listed = {line.split()[1] for line in self.lines}
        self.assertEqual(listed, set(self.subparsers))

    def _canonical_options(self, subparser):
        """The option string argparse itself would show in a usage line: the
        first one registered for each action, skipping `-h/--help`."""
        seen = set()
        options = {}
        for action in subparser._option_string_actions.values():
            if action.dest == "help" or action in seen:
                continue
            seen.add(action)
            options[action.option_strings[0]] = action
        return options

    def test_flags_match_in_both_directions(self):
        for line in self.lines:
            name = line.split()[1]
            expected = set(self._canonical_options(self.subparsers[name]))
            found = {flag for flag, _ in _FLAG_RE.findall(line)}
            self.assertEqual(found, expected, msg=name)

    def test_choices_and_metavars_match(self):
        for line in self.lines:
            name = line.split()[1]
            options = self._canonical_options(self.subparsers[name])
            for flag, value in _FLAG_RE.findall(line):
                action = options[flag]
                if not value:
                    continue
                if "|" in value:
                    self.assertEqual(set(value.split("|")), set(action.choices), msg=flag)
                else:
                    metavar = action.metavar or action.dest.upper()
                    self.assertEqual(value, metavar, msg=flag)


if __name__ == "__main__":
    unittest.main()
