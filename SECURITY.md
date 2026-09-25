# Security

pentimento reads plan markdown files (`~/.claude/plans`, and Cursor's plan
directories) and, for lineage and history enrichment, Claude Code session
transcripts (`~/.claude/projects`) and Cursor agent transcripts
(`~/.cursor/projects`), on the machine it runs on. It writes frontmatter into
plan files (`set`, `backfill`, `hook`), `INDEX.md` into the plans directory
(`index`), and a cache of transcript-derived data (working directories, first
prompts, project names, touched paths) under `$XDG_CACHE_HOME/pentimento`
(default `~/.cache/pentimento`). It does not send that data anywhere — no
network access, no telemetry.

## Reporting a vulnerability

Please use
[GitHub's private vulnerability reporting](https://github.com/kjiwa/pentimento/security/advisories/new)
for this repository rather than opening a public issue. If that option isn't
available yet, email kamil.jiwa@gmail.com instead.
