# Contributing

## Setup and checks

```sh
python3 -m unittest discover
uvx ruff check
uvx ruff format --check
```

CI runs the suite on Python 3.9, the supported minimum, and 3.13. To check 3.9 locally:

```sh
uv run --python 3.9 --no-project python -m unittest discover
```

CI also regenerates the README's sample blocks and fails if they drift:

```sh
sh demo/capture.sh && git diff --exit-code README.md
```

Run it when a change could alter what a sample shows.

A separate CI job drives the real Claude Code CLI against a scripted local endpoint
(no account or subscription) to check the shipped hooks. It needs `claude` and
`pentimento` on `PATH` and a free loopback port:

```sh
sh tests/e2e/claude.sh
```

Run it when a change touches `pentimento hook`, `backfill`, or
`integrations/claude/`.

User-visible output must satisfy `tests/test_invariants.py`. A defect found in
review is fixed with a test for its class, not only its instance.

## Releasing

```sh
sh scripts/release.sh [--dry-run] <version>
```

`<version>` is bare (`0.1.8`, not `v0.1.8`). Run it on a clean, synced `main`.
The script runs the same checks CI runs, opens a `release-<version>` PR with
the `pyproject.toml` bump, waits for its checks, and squash-merges it. GitHub
signs the squash commit, so the release shows as Verified. It then tags the
merged commit and creates the GitHub release from the matching `CHANGELOG.md`
section — the version needs a `## <version>` heading there before you run it.
If the bump is already on `main`, it skips the PR and only tags and releases,
so a run that stopped after the merge can be repeated. `--dry-run` runs every
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
