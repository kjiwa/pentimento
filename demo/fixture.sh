#!/bin/sh
# Write a synthetic plan corpus for README samples and the VHS demo.
#
# Usage: fixture.sh TARGET_DIR
#
# Spans every status and intent, a two-level parent chain, two projects,
# one raw (frontmatter-less) plan for the backfill step to work on, and
# one deliberate dangling parent for the check step to flag. mtimes are
# set relative to now so the relative-time column stays truthful whenever
# samples are regenerated. A synthetic session log under
# `$TARGET_DIR/sessions/` gives the api-auth-* chain real touch history: one
# authoring session per plan (timestamped to that plan's own mtime, so the
# `list`/`tree` samples don't shift) and one later session that works
# `api-auth-cleanup` despite its `not-started` status, so the `check` sample
# gains `status-behind-history`.
set -eu

# Emits touch -t stamp, local created date, and UTC session timestamp, all
# for the same instant, so a plan's mtime and its authoring session's
# timestamp agree exactly.
_stamp_days_ago() {
  _fixture_days=$1
  python3 -c '
import datetime, sys
d = (datetime.datetime.now() - datetime.timedelta(days=int(sys.argv[1]))).replace(microsecond=0)
utc = d.astimezone().astimezone(datetime.timezone.utc)
print(d.strftime("%Y%m%d%H%M.%S"))
print(d.strftime("%Y-%m-%d"))
print(utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
' "$_fixture_days"
}

_write_session() {
  _fixture_dir=$1
  _fixture_file=$2
  _fixture_slug=$3
  _fixture_cwd=$4
  _fixture_ts=$5
  _fixture_tool=$6
  _fixture_plan_path=$7

  mkdir -p "$_fixture_dir"
  printf '{"type": "assistant", "slug": "%s", "cwd": "%s", "timestamp": "%s", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "%s", "input": {"file_path": "%s"}}]}}\n' \
    "$_fixture_slug" "$_fixture_cwd" "$_fixture_ts" "$_fixture_tool" "$_fixture_plan_path" \
    >"$_fixture_dir/$_fixture_file"
}

_write_plan() {
  _fixture_id=$1
  _fixture_title=$2
  _fixture_status=$3
  _fixture_intent=$4
  _fixture_project=$5
  _fixture_parent=$6
  _fixture_days_ago=$7
  _fixture_progress=$8
  _fixture_tags=${9:-}

  _fixture_path="$TARGET_DIR/$_fixture_id.md"
  _fixture_stamps=$(_stamp_days_ago "$_fixture_days_ago")
  _fixture_touch_ts=$(printf '%s\n' "$_fixture_stamps" | sed -n '1p')
  _fixture_created=$(printf '%s\n' "$_fixture_stamps" | sed -n '2p')
  FIXTURE_SESSION_TS=$(printf '%s\n' "$_fixture_stamps" | sed -n '3p')

  {
    printf '%s\n' '---'
    printf 'pentimento:\n'
    printf '  status: %s\n' "$_fixture_status"
    printf '  intent: %s\n' "$_fixture_intent"
    if [ -n "$_fixture_tags" ]; then
      printf '  tags: %s\n' "$_fixture_tags"
    fi
    if [ -n "$_fixture_parent" ]; then
      printf '  parent: %s\n' "$_fixture_parent"
    fi
    if [ -n "$_fixture_project" ]; then
      printf '  project: %s\n' "$_fixture_project"
    fi
    printf '  created: %s\n' "$_fixture_created"
    printf '%s\n' '---'
    printf '\n'
    printf '# %s\n' "$_fixture_title"
    printf '\n'
    printf '%s\n' "$_fixture_progress"
  } >"$_fixture_path"

  touch -t "$_fixture_touch_ts" "$_fixture_path"
}

_write_raw_plan() {
  _fixture_id=$1
  _fixture_title=$2
  _fixture_days_ago=$3
  _fixture_progress=$4

  _fixture_path="$TARGET_DIR/$_fixture_id.md"
  _fixture_stamps=$(_stamp_days_ago "$_fixture_days_ago")
  _fixture_touch_ts=$(printf '%s\n' "$_fixture_stamps" | sed -n '1p')

  {
    printf '# %s\n' "$_fixture_title"
    printf '\n'
    printf '%s\n' "$_fixture_progress"
  } >"$_fixture_path"

  touch -t "$_fixture_touch_ts" "$_fixture_path"
}

main() {
  if [ $# -ne 1 ]; then
    echo "usage: fixture.sh TARGET_DIR" >&2
    return 1
  fi
  TARGET_DIR=$1
  mkdir -p "$TARGET_DIR"

  _write_plan api-auth-redesign "Redesign the auth API" complete abandoned \
    platform "" 40 \
    '## Progress

- [x] Draft the new token schema
- [x] Migrate existing sessions' \
    '[auth, security]'
  _write_session "$TARGET_DIR/sessions/platform" api-auth-redesign-session.jsonl \
    api-auth-redesign /Users/kjiwa/src/github/kjiwa/pentimento "$FIXTURE_SESSION_TS" \
    Write /Users/kjiwa/.claude/plans/api-auth-redesign.md

  _write_plan api-auth-rollout "Roll out the new auth API" partial active \
    platform api-auth-redesign 20 \
    '## Progress

- [x] Ship behind a feature flag
- [ ] Flip the flag for all tenants

## Context

Tenants opt in via the `auth_v2` flag in `tenant_settings`. Watch error rates
before flipping the remaining cohort.' \
    '[auth, security]'
  _write_session "$TARGET_DIR/sessions/platform" api-auth-rollout-session.jsonl \
    api-auth-rollout /Users/kjiwa/src/github/kjiwa/pentimento "$FIXTURE_SESSION_TS" \
    Write /Users/kjiwa/.claude/plans/api-auth-rollout.md

  _write_plan api-auth-cleanup "Remove the old auth API" not-started queued \
    platform api-auth-rollout 15 \
    '## Progress

- [ ] Delete the legacy endpoints
- [ ] Drop the compatibility shim' \
    '[auth, security]'
  _write_session "$TARGET_DIR/sessions/platform" api-auth-cleanup-session.jsonl \
    api-auth-cleanup /Users/kjiwa/src/github/kjiwa/pentimento "$FIXTURE_SESSION_TS" \
    Write /Users/kjiwa/.claude/plans/api-auth-cleanup.md

  _fixture_worked_ts=$(_stamp_days_ago 3 | sed -n '3p')
  _write_session "$TARGET_DIR/sessions/platform" implement-api-auth-cleanup-eager-wolf.jsonl \
    implement-api-auth-cleanup-eager-wolf /Users/kjiwa/src/github/kjiwa/pentimento "$_fixture_worked_ts" \
    Read /Users/kjiwa/.claude/plans/api-auth-cleanup.md

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
