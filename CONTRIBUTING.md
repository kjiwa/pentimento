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

Run it when a change could alter what a sample shows.

## Releasing

```sh
sh scripts/release.sh [--dry-run] <version>
```

`<version>` is bare (`0.1.8`, not `v0.1.8`). The script bumps
`pyproject.toml`, runs the same checks CI runs, tags, pushes, and creates the
GitHub release from the matching `CHANGELOG.md` section — the version needs
a `## <version>` heading there before you run it. `--dry-run` runs every
check and prints each mutating command instead of running it.

The release event triggers `publish.yml`, which re-runs
`scripts/check-release.sh` (the tag, its title, and the `CHANGELOG.md`
heading must all agree) before building and publishing to PyPI, so a
hand-cut release that skips `release.sh` still gets caught.

## Scope

pentimento is a single-maintainer project and single-operator by design; see
the README's
[Scope](https://github.com/kjiwa/pentimento/blob/main/README.md#scope). It
stays stdlib-only, with zero runtime dependencies, and does one job: status,
intent, and lineage over plan files. PRs that add a runtime dependency, a new
plan-file format, or scope beyond that are declined. Bug reports and fixes are
welcome.
