"""Shell completion: candidate engine plus per-shell integration scripts.

`pentimento completion <shell>` prints a short, static script that delegates
every candidate decision back to the hidden `pentimento __complete <words>`,
whose last word is the word being completed. All logic lives here in Python;
the emitters below are thin.
"""

from __future__ import annotations

import argparse
import contextlib
import io

from pentimento import cli as cli_module
from pentimento import corpus, listing, shortid
from pentimento import tags as tags_module

SHELLS = ("bash", "zsh", "fish")

_BASH_SCRIPT = """\
_pentimento() {
  local cur i words
  cur="${COMP_WORDS[COMP_CWORD]}"
  words=()
  for ((i = 1; i < COMP_CWORD; i++)); do
    words+=("${COMP_WORDS[i]}")
  done
  words+=("$cur")
  COMPREPLY=()
  local line
  while IFS= read -r line; do
    COMPREPLY+=("${line%%$'\\t'*}")
  done < <(pentimento __complete "${words[@]}")
}
complete -F _pentimento pentimento
"""

_ZSH_SCRIPT = """\
#compdef pentimento

_pentimento() {
  local -a args
  args=("${words[@]:1:$((CURRENT - 1))}")
  local -a lines
  lines=("${(@f)$(pentimento __complete "${args[@]}")}")
  local -a descs
  local line value desc
  for line in "${lines[@]}"; do
    [[ -z "$line" ]] && continue
    value="${line%%$'\\t'*}"
    if [[ "$line" == *$'\\t'* ]]; then
      desc="${line#*$'\\t'}"
    else
      desc="$value"
    fi
    descs+=("$value:$desc")
  done
  _describe 'pentimento' descs
}

# Autoloading this file (from fpath) only defines the function above; when
# the autoloader's own call *is* that first call, run it for real.
if [[ "$funcstack[1]" == "_pentimento" ]]; then
  _pentimento "$@"
fi
compdef _pentimento pentimento
"""

_FISH_SCRIPT = """\
function __pentimento_complete
    set -l cmd (commandline -opc)
    set -e cmd[1]
    pentimento __complete $cmd (commandline -ct)
end

complete -c pentimento -f -a '(__pentimento_complete)'
"""

_SCRIPTS = {"bash": _BASH_SCRIPT, "zsh": _ZSH_SCRIPT, "fish": _FISH_SCRIPT}


def script(shell: str) -> str:
    return _SCRIPTS[shell]


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )


def _positional_actions(subparser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [action for action in subparser._actions if not action.option_strings]


def _option_candidates(subparser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    seen = set()
    result = []
    for action in subparser._actions:
        if action.dest == "help" or not action.option_strings:
            continue
        for opt in action.option_strings:
            if opt in seen:
                continue
            seen.add(opt)
            result.append((opt, action.help or ""))
    return result


def _pending_option(subparser: argparse.ArgumentParser, prev: str | None) -> argparse.Action | None:
    """The option `prev` names, if it still expects a value."""
    if prev is None:
        return None
    action = subparser._option_string_actions.get(prev)
    if action is None or action.nargs == 0:
        return None
    return action


def _assigned_positionals(
    subparser: argparse.ArgumentParser, prior_words: list[str]
) -> tuple[dict, int]:
    """dest -> value for each positional already fully typed in `prior_words`,
    plus the count of positionals consumed, so the next slot is known."""
    positionals = _positional_actions(subparser)
    assigned: dict = {}
    count = 0
    i = 0
    while i < len(prior_words):
        token = prior_words[i]
        action = subparser._option_string_actions.get(token) if token.startswith("-") else None
        if action is not None:
            i += 1
            if action.nargs != 0:
                i += 1
            continue
        if count < len(positionals):
            assigned[positionals[count].dest] = token
            count += 1
        i += 1
    return assigned, count


def _positional_slot(
    subparser: argparse.ArgumentParser, prior_words: list[str]
) -> argparse.Action | None:
    positionals = _positional_actions(subparser)
    _, count = _assigned_positionals(subparser, prior_words)
    if count < len(positionals):
        return positionals[count]
    return None


def _plan_candidates(plans, word: str) -> list[tuple[str, str]]:
    """Every plan's short id, plus any full id starting with `word`."""
    ids = [p.id for p in plans]
    titles = {p.id: p.title for p in plans}
    short_by_id = shortid.shorten(ids)
    by_value = {}
    for full_id, short in short_by_id.items():
        by_value[short] = titles[full_id]
    if word:
        for full_id in ids:
            if full_id.startswith(word):
                by_value[full_id] = titles[full_id]
    return sorted((value, title) for value, title in by_value.items() if value.startswith(word))


def _all_tags(plans) -> set[str]:
    tags: set[str] = set()
    for plan in plans:
        tags.update(tags_module.normalize(t) for t in plan.tags)
    return tags


def _tag_candidates(plans, word: str) -> list[tuple[str, str]]:
    return [(t, "") for t in sorted(_all_tags(plans)) if t.startswith(word)]


def _remove_tag_candidates(plans, subparser, prior_words, word: str) -> list[tuple[str, str]]:
    assigned, _ = _assigned_positionals(subparser, prior_words)
    target = corpus.by_id(plans, assigned["id"]) if "id" in assigned else None
    pool = {tags_module.normalize(t) for t in target.tags} if target else _all_tags(plans)
    return [(t, "") for t in sorted(pool) if t.startswith(word)]


def _project_candidates(plans, word: str) -> list[tuple[str, str]]:
    projects = sorted({p.project for p in plans if p.project}) + ["."]
    return [(p, "") for p in projects if p.startswith(word)]


def _option_value_candidates(
    action, subparser, prior_words, word: str, plans
) -> list[tuple[str, str]]:
    if action.choices:
        return [(str(c), "") for c in action.choices if str(c).startswith(word)]
    dest = action.dest
    if dest == "project":
        return _project_candidates(plans(), word)
    if dest in ("tag", "add_tag"):
        return _tag_candidates(plans(), word)
    if dest == "remove_tag":
        return _remove_tag_candidates(plans(), subparser, prior_words, word)
    if dest in ("parent", "only"):
        return _plan_candidates(plans(), word)
    if dest == "columns":
        return [(c, "") for c in listing.NAMES + ("all",) if c.startswith(word)]
    return []


def _positional_candidates(action, word: str, plans) -> list[tuple[str, str]]:
    if action.dest == "id":
        return _plan_candidates(plans(), word)
    if action.choices:
        return [(str(c), "") for c in action.choices if str(c).startswith(word)]
    return []


def _top_level_candidates(parser: argparse.ArgumentParser, word: str) -> list[tuple[str, str]]:
    sub_action = _subparsers_action(parser)
    help_by_name = {choice.dest: choice.help for choice in sub_action._choices_actions}
    items = [(name, help_by_name.get(name) or "") for name in sub_action.choices]
    for action in parser._actions:
        if action is sub_action or not action.option_strings:
            continue
        for opt in action.option_strings:
            items.append((opt, action.help or ""))
    return [(value, description) for value, description in items if value.startswith(word)]


def candidates(words) -> list[tuple[str, str]]:
    """(value, description) pairs for the word being completed.

    `words` is everything after `pentimento` on the command line, with the
    last element being the (possibly empty) word under the cursor.
    """
    words = list(words) if words else [""]
    word = words[-1]
    parser = cli_module.build_parser()
    if len(words) == 1:
        return _top_level_candidates(parser, word)

    sub_action = _subparsers_action(parser)
    name = words[0]
    if name not in sub_action.choices:
        return []
    subparser = sub_action.choices[name]
    prior_words = words[1:-1]
    prev = prior_words[-1] if prior_words else None

    plans_cache: list | None = None

    def plans():
        nonlocal plans_cache
        if plans_cache is None:
            plans_cache = corpus.load_all(sessions={})
        return plans_cache

    pending = _pending_option(subparser, prev)
    if pending is not None:
        return _option_value_candidates(pending, subparser, prior_words, word, plans)
    if word.startswith("-"):
        return [(opt, desc) for opt, desc in _option_candidates(subparser) if opt.startswith(word)]
    positional = _positional_slot(subparser, prior_words)
    if positional is None:
        return []
    return _positional_candidates(positional, word, plans)


def complete(words) -> int:
    """Print `value` or `value\\tdescription` per candidate. Never fails: any
    error, and the corpus's own "skipping unreadable plan" stderr line, are
    swallowed so a tab press never disturbs the prompt."""
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            pairs = candidates(words)
        for value, description in pairs:
            if description:
                print(f"{value}\t{description}")
            else:
                print(value)
    except Exception:
        pass
    return 0
