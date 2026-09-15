# Security

pentimento reads files under `~/.claude` on the machine it runs on: plan
markdown files and, for lineage and history enrichment, session transcripts
under `~/.claude/projects`. It does not send that data anywhere — no network
access, no telemetry.

## Reporting a vulnerability

Please use
[GitHub's private vulnerability reporting](https://github.com/kjiwa/pentimento/security/advisories/new)
for this repository rather than opening a public issue. If that option isn't
available yet, email kamil.jiwa@gmail.com instead.
