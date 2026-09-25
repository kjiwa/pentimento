#!/bin/sh
# Write a synthetic plan corpus for README samples and the VHS demo.
#
# Usage: fixture.sh TARGET_DIR
#
# Spans every status and intent, a two-level parent chain, two projects,
# one raw (frontmatter-less) plan for the backfill step to work on, one
# deliberate dangling parent for the check step to flag, and one untagged plan
# (`api-auth-docs`) beside its tagged sibling for `unadopted-tag`. mtimes are
# set relative to now so the relative-time column stays truthful whenever
# samples are regenerated. A synthetic session log under
# `$TARGET_DIR/sessions/` gives the api-auth-* chain real touch history: one
# authoring session per plan (timestamped to that plan's own mtime, so the
# `list`/`tree` samples don't shift) and one later session that works
# `api-auth-cleanup` despite its `not-started` status, so the `check` sample
# gains `status-behind-history`.
set -eu

_stamp_days_ago() {
  python3 "$SCRIPT_DIR/stamp.py" "$1"
}

_write_session() {
  _write_session_dir=$1
  _write_session_file=$2
  _write_session_slug=$3
  _write_session_cwd=$4
  _write_session_days_ago=$5
  _write_session_tool=$6
  _write_session_plan_path=$7

  _write_session_ts=$(_stamp_days_ago "$_write_session_days_ago" | sed -n '3p')

  mkdir -p "$_write_session_dir"
  printf '{"type": "assistant", "slug": "%s", "cwd": "%s", "timestamp": "%s", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "%s", "input": {"file_path": "%s"}}]}}\n' \
    "$_write_session_slug" "$_write_session_cwd" "$_write_session_ts" "$_write_session_tool" "$_write_session_plan_path" \
    >"$_write_session_dir/$_write_session_file"
}

_write_plan() {
  _write_plan_id=$1
  _write_plan_title=$2
  _write_plan_status=$3
  _write_plan_intent=$4
  _write_plan_project=$5
  _write_plan_parent=$6
  _write_plan_days_ago=$7
  _write_plan_progress=$8
  _write_plan_tags=${9:-}

  _write_plan_path="$TARGET_DIR/$_write_plan_id.md"
  _write_plan_stamps=$(_stamp_days_ago "$_write_plan_days_ago")
  _write_plan_touch_ts=$(printf '%s\n' "$_write_plan_stamps" | sed -n '1p')
  _write_plan_created=$(printf '%s\n' "$_write_plan_stamps" | sed -n '2p')

  {
    printf '%s\n' '---'
    printf 'pentimento:\n'
    printf '  status: %s\n' "$_write_plan_status"
    printf '  intent: %s\n' "$_write_plan_intent"
    if [ -n "$_write_plan_tags" ]; then
      printf '  tags: %s\n' "$_write_plan_tags"
    fi
    if [ -n "$_write_plan_parent" ]; then
      printf '  parent: %s\n' "$_write_plan_parent"
    fi
    if [ -n "$_write_plan_project" ]; then
      printf '  project: %s\n' "$_write_plan_project"
    fi
    printf '  created: %s\n' "$_write_plan_created"
    printf '%s\n' '---'
    printf '\n'
    printf '# %s\n' "$_write_plan_title"
    printf '\n'
    printf '%s\n' "$_write_plan_progress"
  } >"$_write_plan_path"

  touch -t "$_write_plan_touch_ts" "$_write_plan_path"
}

_write_raw_plan() {
  _write_raw_plan_id=$1
  _write_raw_plan_title=$2
  _write_raw_plan_days_ago=$3
  _write_raw_plan_progress=$4

  _write_raw_plan_path="$TARGET_DIR/$_write_raw_plan_id.md"
  _write_raw_plan_stamps=$(_stamp_days_ago "$_write_raw_plan_days_ago")
  _write_raw_plan_touch_ts=$(printf '%s\n' "$_write_raw_plan_stamps" | sed -n '1p')

  {
    printf '# %s\n' "$_write_raw_plan_title"
    printf '\n'
    printf '%s\n' "$_write_raw_plan_progress"
  } >"$_write_raw_plan_path"

  touch -t "$_write_raw_plan_touch_ts" "$_write_raw_plan_path"
}

main() {
  if [ $# -ne 1 ]; then
    echo "usage: fixture.sh TARGET_DIR" >&2
    return 1
  fi
  SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
  readonly SCRIPT_DIR
  TARGET_DIR=$1
  readonly TARGET_DIR
  mkdir -p "$TARGET_DIR"

  _write_plan api-auth-redesign "Redesign the auth API" complete abandoned \
    platform "" 40 \
    '## Progress

- [x] Draft the new token schema
- [x] Migrate existing sessions' \
    '[auth, security]'
  _write_session "$TARGET_DIR/sessions/platform" api-auth-redesign-session.jsonl \
    api-auth-redesign /home/user/src/example 40 \
    Write /home/user/.claude/plans/api-auth-redesign.md

  # shellcheck disable=SC2016 # backticks in the plan body are literal Markdown
  _write_plan api-auth-rollout "Roll out the new auth API" partial active \
    platform api-auth-redesign 20 \
    '## Progress

- [x] Ship behind a feature flag
- [ ] Flip the flag for all tenants

## Context

Tenants opt in via the `auth_v2` flag in `tenant_settings`. Watch error rates
before flipping the remaining cohort. See the [rollout runbook](docs/auth-rollout.md).

| Cohort | Status |
| --- | --- |
| internal | complete |
| beta | in progress |' \
    '[auth, security]'
  _write_session "$TARGET_DIR/sessions/platform" api-auth-rollout-session.jsonl \
    api-auth-rollout /home/user/src/example 20 \
    Write /home/user/.claude/plans/api-auth-rollout.md

  _write_plan api-auth-cleanup "Remove the old auth API" not-started queued \
    platform api-auth-rollout 15 \
    '## Progress

- [ ] Delete the legacy endpoints
- [ ] Drop the compatibility shim' \
    '[auth, security]'
  _write_session "$TARGET_DIR/sessions/platform" api-auth-cleanup-session.jsonl \
    api-auth-cleanup /home/user/src/example 15 \
    Write /home/user/.claude/plans/api-auth-cleanup.md

  _write_plan api-auth-docs "Document the new auth API" not-started unset \
    platform api-auth-rollout 12 \
    '## Progress

- [ ] Write the migration guide'
  _write_session "$TARGET_DIR/sessions/platform" api-auth-docs-session.jsonl \
    api-auth-docs /home/user/src/example 12 \
    Write /home/user/.claude/plans/api-auth-docs.md

  _write_session "$TARGET_DIR/sessions/platform" implement-api-auth-cleanup-eager-wolf.jsonl \
    implement-api-auth-cleanup-eager-wolf /home/user/src/example 3 \
    Edit /home/user/.claude/plans/api-auth-cleanup.md

  _write_plan billing-invoice-retry "Retry failed invoice charges" unknown unset \
    billing no-such-plan 10 \
    '## Progress

Notes only, no checklist yet.' \
    '[billing]'

  _write_plan billing-dunning-copy "Rewrite dunning email copy" complete someday \
    billing "" 25 \
    '## Progress

- [x] Draft new copy
- [x] Get legal sign-off' \
    '[billing]'

  _write_plan docs-style-guide "Write a docs style guide" superseded abandoned \
    platform "" 45 \
    '## Progress

- [x] Outline sections
- [ ] Fill in examples'

  _write_plan search-relevance-tuning "Tune search relevance" not-started active \
    billing "" 5 \
    '## Progress

- [ ] Collect query logs
- [ ] Retrain ranking model' \
    '[search]'

  _write_raw_plan onboarding-checklist "Write the onboarding checklist" 1 \
    '## Progress

- [ ] List required accounts
- [ ] List required tooling'
}

main "$@"
