#!/bin/sh
# Cut a pentimento release: land the version bump through a pull request, run
# the same checks CI runs, tag the merged commit, and create the GitHub release
# from the matching CHANGELOG section. The next release should be reproducible
# from this script rather than reconstructed from memory.
#
# Usage: sh scripts/release.sh [--dry-run] <version>
#
# <version> is bare (0.1.8, not v0.1.8). --dry-run runs every check and
# prints each mutating command instead of running it.
#
# The bump goes through a squash-merged PR, not a push to main: GitHub signs
# the squash commit, so the release shows as Verified, and the main ruleset
# requires a PR. If pyproject.toml on main already reads <version> (the bump
# PR was merged by hand, or a previous run stopped after merging), the PR
# steps are skipped and the script only tags and releases.
set -eu

REPO_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PYPROJECT="$REPO_ROOT/pyproject.toml"
CHANGELOG="$REPO_ROOT/CHANGELOG.md"

DRY_RUN=0
VERSION=""
TAG=""
BRANCH=""
PR_URL=""

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
  BRANCH="release-$VERSION"
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
  # check-release.sh reads the version straight from pyproject.toml, which
  # --dry-run never writes; simulate the bump for this one check, then
  # restore the file, so a dry run actually exercises the real gate instead
  # of failing on the version it deliberately didn't apply.
  if [ "$DRY_RUN" -eq 1 ]; then
    _run_release_check_tmp=$(mktemp "${TMPDIR:-/tmp}/release-pyproject.XXXXXX")
    cp "$PYPROJECT" "$_run_release_check_tmp"
    sed "s/^version = \".*\"\$/version = \"$VERSION\"/" "$_run_release_check_tmp" >"$PYPROJECT"
    _run_release_check_status=0
    sh "$REPO_ROOT/scripts/check-release.sh" "$TAG" "$TAG" || _run_release_check_status=$?
    mv "$_run_release_check_tmp" "$PYPROJECT"
    return "$_run_release_check_status"
  fi
  sh "$REPO_ROOT/scripts/check-release.sh" "$TAG" "$TAG"
}

_run_tests() {
  (cd "$REPO_ROOT" && python3 -m unittest discover)
  (cd "$REPO_ROOT" && uvx ruff check)
  (cd "$REPO_ROOT" && uvx ruff format --check)
}

_is_bumped() {
  _is_bumped_current=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$PYPROJECT" | head -n1)
  [ "$_is_bumped_current" = "$VERSION" ]
}

_check_branch_absent() {
  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    echo "release: branch '$BRANCH' already exists locally" >&2
    exit 1
  fi
  if git -C "$REPO_ROOT" ls-remote --heads origin "$BRANCH" | grep -q .; then
    echo "release: branch '$BRANCH' already exists on origin" >&2
    exit 1
  fi
}

_commit_and_push_branch() {
  _run git -C "$REPO_ROOT" add "$PYPROJECT"
  _run git -C "$REPO_ROOT" commit -m "Release $VERSION"
  _run git -C "$REPO_ROOT" push -u origin "$BRANCH"
  _run git -C "$REPO_ROOT" switch main
}

_open_pr() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh pr create --base main --head $BRANCH --title 'Release $VERSION'"
    PR_URL="<pr-url>"
    return
  fi
  PR_URL=$(gh pr create --base main --head "$BRANCH" --title "Release $VERSION" \
    --body "Version bump for $VERSION; scripts/release.sh tags and publishes after merge.")
}

_await_checks() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh pr checks $PR_URL --watch --fail-fast"
    return
  fi
  # A new PR reports no checks for a few seconds, and --watch on none exits
  # at once, so wait for the first check to register.
  _await_checks_tries=0
  while [ "$(gh pr checks "$PR_URL" --json name --jq length 2>/dev/null || echo 0)" -eq 0 ]; do
    _await_checks_tries=$((_await_checks_tries + 1))
    if [ "$_await_checks_tries" -gt 24 ]; then
      echo "release: no checks reported on $PR_URL after 2 minutes" >&2
      exit 1
    fi
    sleep 5
  done
  # All checks, not only the required ones: the ruleset's CodeQL rule also
  # blocks the merge until analysis finishes.
  gh pr checks "$PR_URL" --watch --fail-fast
}

_merge_pr() {
  # --match-head-commit refuses to merge if the branch moved during the wait.
  # No --admin: bypassing the ruleset is what leaves the commit unsigned.
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh pr merge $PR_URL --squash --delete-branch --match-head-commit <branch-head>"
    return
  fi
  gh pr merge "$PR_URL" --squash --delete-branch \
    --match-head-commit "$(git -C "$REPO_ROOT" rev-parse "$BRANCH")"
}

_sync_main() {
  _run git -C "$REPO_ROOT" pull --ff-only origin main
  if [ "$DRY_RUN" -eq 1 ]; then
    return
  fi
  # Tags go on HEAD, so HEAD must be the merge commit, not a later push.
  _sync_main_merged=$(gh pr view "$PR_URL" --json mergeCommit --jq .mergeCommit.oid)
  if [ "$(git -C "$REPO_ROOT" rev-parse HEAD)" != "$_sync_main_merged" ]; then
    echo "release: main moved past the release commit $_sync_main_merged" >&2
    exit 1
  fi
}

_land_bump() {
  _check_branch_absent
  _run git -C "$REPO_ROOT" switch -c "$BRANCH"
  _bump_version
  _run_release_check
  _run_tests
  _commit_and_push_branch
  _open_pr
  _await_checks
  _merge_pr
  _sync_main
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
  if _is_bumped; then
    _run_release_check
  else
    _land_bump
  fi
  _tag_and_push
  _create_github_release
}

main "$@"
