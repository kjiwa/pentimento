---
name: Add dry-run flag
overview: Add `--dry-run` as an alias of the existing `--list-only` path so the CLI searches the camera, prints recording time ranges and sizes, and exits without downloading or merging. Cover the flag with CLI tests and README updates.
todos:
  - id: cli-alias
    content: Add --dry-run as alias of --list-only in cli.py
    status: completed
  - id: tests
    content: Add parse + run tests for --dry-run in tests/test_cli.py
    status: in_progress
  - id: readme
    content: Document --dry-run (and --list-only alias) in README.md
    status: pending
isProject: false
---

# Add `--dry-run` flag

The listing behavior already exists. In [`cli.py`](cli.py), `--list-only` searches recordings then calls `_render_table` and returns without `RecordingDownloader` or `VideoMerger`. That table already includes start/end times, duration, size, and file path, plus a totals row.

## Implementation

In [`cli.py`](cli.py), register `--dry-run` on the same argument as `--list-only` (same `dest="list_only"` / `action="store_true"`). Keep `--list-only` so existing scripts and [`demo.tape`](demo.tape) keep working.

```python
parser.add_argument(
    "--dry-run",
    "--list-only",
    action="store_true",
    dest="list_only",
    help="List matching recordings (sizes and time ranges) without downloading or merging",
)
```

No change is needed in `_execute`: `args.list_only` already short-circuits after the table.

```mermaid
flowchart LR
  parse[Parse CLI] --> search[Search recordings]
  search --> dry{dry-run or list-only}
  dry -->|yes| table[Print table and exit 0]
  dry -->|no| download[Download then merge]
```

## Tests

In [`tests/test_cli.py`](tests/test_cli.py):

- Assert `--dry-run` parses to `list_only=True` (and `--list-only` still does).
- End-to-end `CLI.run([... "--dry-run"])` with a mocked `AmcrestClient`:
  - exit code 0
  - `find_recordings` called
  - `download_recording` / `RecordingDownloader` / `VideoMerger` not used
  - stdout includes start/end times and formatted size (reuse the existing recording fixture: `2026-01-16 08:00:00`–`08:15:00`, `1.0 MB`)

Existing `test_run_with_env_password_and_list_only` stays as the `--list-only` regression.

## Docs

Update [`README.md`](README.md) Features, Optional Arguments, and the list-only example so `--dry-run` is the documented name, with `--list-only` noted as an alias.