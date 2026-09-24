from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from pentimento import check, cli, completion, listing, vocabulary


def _write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.md").write_text(text)


def _restore_env(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


def _isolate_env(test, directory):
    for key, value in (
        ("AGENT_PLANS_DIR", str(directory)),
        ("AGENT_SESSIONS_DIR", str(directory / "no-such-sessions-dir")),
        ("CURSOR_PLANS_DIR", str(directory / "no-such-cursor-plans-dir")),
    ):
        previous = os.environ.get(key)
        os.environ[key] = value
        test.addCleanup(_restore_env, key, previous)


class DriftGuardTests(unittest.TestCase):
    """Every parser option string must be reachable as a `-` candidate."""

    def test_every_option_is_reachable(self):
        parser = cli.build_parser()
        sub_action = completion._subparsers_action(parser)
        for name, subparser in sub_action.choices.items():
            values = {value for value, _ in completion.candidates([name, "-"])}
            for action in subparser._actions:
                if action.dest == "help" or not action.option_strings:
                    continue
                for opt in action.option_strings:
                    self.assertIn(opt, values, msg=f"{name} {opt}")


class TopLevelTests(unittest.TestCase):
    def test_offers_subcommands_and_version(self):
        values = {value for value, _ in completion.candidates([""])}
        self.assertIn("list", values)
        self.assertIn("show", values)
        self.assertIn("--version", values)
        self.assertIn("--help", values)

    def test_prefix_filters(self):
        values = {value for value, _ in completion.candidates(["sh"])}
        self.assertEqual(values, {"show"})


class _CorpusTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_env(self, self.directory)
        _write(
            self.directory,
            "is-it-possible-to-abundant-rabbit",
            "---\npentimento:\n"
            "  project: platform\n  tags: [auth, security]\n---\n# Roll out auth\n",
        )
        _write(
            self.directory,
            "can-we-ship-glimmering-pizza",
            "---\npentimento:\n"
            "  project: billing\n  tags: [billing]\n---\n# Ship the pizza feature\n",
        )


class ChoicesFlagTests(_CorpusTestCase):
    def test_status_choices(self):
        values = {value for value, _ in completion.candidates(["list", "--status", ""])}
        self.assertEqual(values, set(vocabulary.STATUS_ORDER))

    def test_source_choices(self):
        values = {value for value, _ in completion.candidates(["list", "--source", ""])}
        self.assertEqual(values, {"claude", "cursor"})


class ColumnsChoicesTests(_CorpusTestCase):
    def test_columns_offers_column_names_plus_all(self):
        values = {value for value, _ in completion.candidates(["list", "--columns", ""])}
        self.assertEqual(values, set(listing.NAMES) | {"all"})


class ProjectTagTests(_CorpusTestCase):
    def test_project_offers_corpus_projects_plus_dot(self):
        values = {value for value, _ in completion.candidates(["list", "--project", ""])}
        self.assertEqual(values, {"platform", "billing", "."})

    def test_tag_offers_corpus_tags(self):
        values = {value for value, _ in completion.candidates(["list", "--tag", ""])}
        self.assertEqual(values, {"auth", "security", "billing"})

    def test_add_tag_offers_corpus_tags(self):
        words = ["set", "abundant-rabbit", "--add-tag", ""]
        values = {value for value, _ in completion.candidates(words)}
        self.assertEqual(values, {"auth", "security", "billing"})

    def test_remove_tag_scopes_to_named_plan(self):
        values = {
            value
            for value, _ in completion.candidates(["set", "abundant-rabbit", "--remove-tag", ""])
        }
        self.assertEqual(values, {"auth", "security"})

    def test_remove_tag_falls_back_to_all_tags_without_a_named_plan(self):
        values = {value for value, _ in completion.candidates(["set", "--remove-tag", ""])}
        self.assertEqual(values, {"auth", "security", "billing"})


class PlanIdTests(_CorpusTestCase):
    def test_show_id_offers_short_ids_with_titles(self):
        pairs = dict(completion.candidates(["show", ""]))
        self.assertIn("abundant-rabbit", pairs)
        self.assertEqual(pairs["abundant-rabbit"], "Roll out auth")

    def test_empty_word_offers_only_short_ids(self):
        values = {value for value, _ in completion.candidates(["show", ""])}
        self.assertEqual(values, {"abundant-rabbit", "glimmering-pizza"})

    def test_full_id_prefix_reaches_the_long_form(self):
        values = {value for value, _ in completion.candidates(["show", "is-it-possible"])}
        self.assertIn("is-it-possible-to-abundant-rabbit", values)

    def test_set_parent_offers_plan_ids(self):
        words = ["set", "abundant-rabbit", "--parent", ""]
        values = {value for value, _ in completion.candidates(words)}
        self.assertIn("glimmering-pizza", values)

    def test_backfill_only_offers_plan_ids(self):
        values = {value for value, _ in completion.candidates(["backfill", "--only", ""])}
        self.assertIn("abundant-rabbit", values)


class FreeformFlagTests(_CorpusTestCase):
    def test_grep_offers_nothing(self):
        self.assertEqual(completion.candidates(["list", "--grep", ""]), [])

    def test_title_offers_nothing(self):
        self.assertEqual(completion.candidates(["list", "--title", ""]), [])

    def test_since_and_until_offer_nothing(self):
        self.assertEqual(completion.candidates(["list", "--since", ""]), [])
        self.assertEqual(completion.candidates(["tree", "--until", ""]), [])

    def test_date_offers_its_choices(self):
        values = {value for value, _ in completion.candidates(["list", "--date", ""])}
        self.assertEqual(values, {"created", "modified"})

    def test_finding_offers_the_check_codes(self):
        values = {value for value, _ in completion.candidates(["list", "--finding", ""])}
        self.assertEqual(values, set(check.HINTS))

    def test_limit_offers_nothing(self):
        self.assertEqual(completion.candidates(["list", "-n", ""]), [])


class CompletionPositionalTests(unittest.TestCase):
    def test_shell_choices(self):
        values = {value for value, _ in completion.candidates(["completion", ""])}
        self.assertEqual(values, set(completion.SHELLS))


class ScriptTests(unittest.TestCase):
    def test_bash_uses_complete_dash_f(self):
        self.assertIn("complete -F", completion.script("bash"))

    def test_zsh_is_compdef_both_ends(self):
        text = completion.script("zsh")
        self.assertTrue(text.startswith("#compdef pentimento"))
        self.assertIn("compdef _pentimento pentimento", text)

    def test_zsh_self_invokes_on_first_autoload(self):
        # Autoloading a #compdef file only *defines* the function on its
        # first call; without a guarded self-call, the very first `<TAB>`
        # after a fresh `compinit` silently offers nothing.
        self.assertIn('$funcstack[1]" == "_pentimento"', completion.script("zsh"))

    def test_fish_uses_complete_dash_c(self):
        self.assertIn("complete -c pentimento", completion.script("fish"))

    def test_every_shell_has_a_non_empty_script(self):
        for shell in completion.SHELLS:
            self.assertTrue(completion.script(shell).strip())


class CompleteDispatchTests(_CorpusTestCase):
    def test_exits_zero_and_prints_nothing_when_plans_dir_is_missing(self):
        os.environ["AGENT_PLANS_DIR"] = str(self.directory / "no-such-plans-dir")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = completion.complete(["show", ""])
        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_exits_zero_and_prints_nothing_for_an_unreadable_plan(self):
        broken = self.directory / "broken.md"
        broken.mkdir()
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = completion.complete(["show", ""])
        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_prints_value_and_description_tab_separated(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            completion.complete(["show", "abundant-rabbit"])
        self.assertIn("abundant-rabbit\tRoll out auth", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
