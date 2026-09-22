#!/bin/sh
# Cut a pentimento release: bump the version, run the same checks CI runs,
# tag, push, and create the GitHub release from the matching CHANGELOG
# section. The next release should be reproducible from this script rather
# than reconstructed from memory.
#
# Usage: sh scripts/release.sh [--dry-run] <version>
#
# <version> is bare (0.1.8, not v0.1.8). --dry-run runs every check and
# prints each mutating command instead of running it.
set -eu

REPO_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PYPROJECT="$REPO_ROOT/pyproject.toml"
CHANGELOG="$REPO_ROOT/CHANGELOG.md"

DRY_RUN=0
VERSION=""
TAG=""

_run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ $*"
  else
    "$@"
  fi
}

_parse_args() {
  while [ $# -gt 0 ]; do
    case $1 in
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -*)
        echo "release: unknown option '$1'" >&2
        exit 2
        ;;
      *)
        if [ -n "$VERSION" ]; then
          echo "release: unexpected argument '$1'" >&2
          exit 2
        fi
        VERSION=$1
        shift
        ;;
    esac
  done

  if [ -z "$VERSION" ]; then
    echo "usage: sh scripts/release.sh [--dry-run] <version>" >&2
    exit 2
  fi
  if ! echo "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "release: version '$VERSION' does not match X.Y.Z" >&2
    exit 1
  fi
  TAG="v$VERSION"
}

_check_preconditions() {
  _check_preconditions_branch=$(git -C "$REPO_ROOT" branch --show-current)
  if [ "$_check_preconditions_branch" != "main" ]; then
    echo "release: must be on main, not '$_check_preconditions_branch'" >&2
    exit 1
  fi

  if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
    echo "release: worktree is not clean" >&2
    exit 1
  fi

  git -C "$REPO_ROOT" fetch origin main

  _check_preconditions_local=$(git -C "$REPO_ROOT" rev-parse main)
  _check_preconditions_remote=$(git -C "$REPO_ROOT" rev-parse origin/main)
  if [ "$_check_preconditions_local" != "$_check_preconditions_remote" ]; then
    echo "release: main has diverged from origin/main" >&2
    exit 1
  fi

  if git -C "$REPO_ROOT" tag --list "$TAG" | grep -Fxq "$TAG"; then
    echo "release: tag '$TAG' already exists locally" >&2
    exit 1
  fi

  if git -C "$REPO_ROOT" ls-remote --tags origin "$TAG" | grep -q "$TAG"; then
    echo "release: tag '$TAG' already exists on origin" >&2
    exit 1
  fi

  if gh release view "$TAG" >/dev/null 2>&1; then
    echo "release: release '$TAG' already exists" >&2
    exit 1
  fi
}

_bump_version() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ set pyproject.toml version to $VERSION"
    return
  fi
  _bump_version_tmp=$(mktemp "${TMPDIR:-/tmp}/release-pyproject.XXXXXX")
  trap 'rm -f "$_bump_version_tmp"' EXIT
  sed "s/^version = \".*\"\$/version = \"$VERSION\"/" "$PYPROJECT" >"$_bump_version_tmp"
  mv "$_bump_version_tmp" "$PYPROJECT"
  trap - EXIT
}

_run_release_check() {
  sh "$REPO_ROOT/scripts/check-release.sh" "$TAG" "$TAG"
}

_run_tests() {
  (cd "$REPO_ROOT" && python3 -m unittest discover)
  (cd "$REPO_ROOT" && uvx ruff check)
  (cd "$REPO_ROOT" && uvx ruff format --check)
}

_commit_and_push() {
  if [ -n "$(git -C "$REPO_ROOT" status --porcelain -- "$PYPROJECT")" ]; then
    _run git -C "$REPO_ROOT" add "$PYPROJECT"
    _run git -C "$REPO_ROOT" commit -m "Release $VERSION"
  fi
  _run git -C "$REPO_ROOT" push origin main
}

_tag_and_push() {
  _run git -C "$REPO_ROOT" tag -a "$TAG" -m "$TAG"
  _run git -C "$REPO_ROOT" push origin "$TAG"
}

_create_github_release() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh release create $TAG --title $TAG --notes-file <## $VERSION CHANGELOG section>"
    return
  fi
  _create_github_release_notes=$(mktemp "${TMPDIR:-/tmp}/release-notes.XXXXXX")
  trap 'rm -f "$_create_github_release_notes"' EXIT
  awk -v ver="## $VERSION" '
    $0 == ver { found = 1; next }
    found && /^## / { exit }
    found { print }
  ' "$CHANGELOG" >"$_create_github_release_notes"
  gh release create "$TAG" --title "$TAG" --notes-file "$_create_github_release_notes"
  rm -f "$_create_github_release_notes"
  trap - EXIT
}

main() {
  _parse_args "$@"
  _check_preconditions
  _bump_version
  _run_release_check
  _run_tests
  _commit_and_push
  _tag_and_push
  _create_github_release
}

main "$@"
