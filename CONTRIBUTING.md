# Contributing

## Setup and checks

```sh
python3 -m unittest discover
uvx ruff check
uvx ruff format --check
```

CI also regenerates the README's sample blocks and fails if they drift:

```sh
sh demo/capture.sh && git diff --exit-code README.md
```

If your change touches CLI output, table rendering, or anything else a
sample might show, run that command before opening a PR.

## Scope

pentimento is a personal, single-maintainer project: one person reviews and
merges PRs. Separately, the tool itself is single-operator by design, not
just by current use — see the README's
[Scope](https://github.com/kjiwa/pentimento/blob/main/README.md#scope)
section for why shared or multi-author planning is out of scope rather than
just unimplemented. It stays stdlib-only, zero runtime dependencies, and
scoped to one job: status, intent, and lineage over plan files. PRs that add
a runtime dependency, a new plan-file format, or scope beyond that will
likely be declined, however well-built — that's not a reflection on the
work, just a fit issue. Bug reports and fixes are always welcome.
