---
description: List, filter, and inspect plan lineage via pentimento.
disable-model-invocation: true
---

Shell out to `pentimento` (https://github.com/kjiwa/pentimento) against
`${AGENT_PLANS_DIR:-$HOME/.claude/plans}`. This command does not reimplement
any of pentimento's logic — it is a thin entry point.

1. If `$ARGUMENTS` is empty, run `pentimento list`.
2. Otherwise, run `pentimento $ARGUMENTS` verbatim — e.g. `/plans tree
   --project fankado`, `/plans show <id>`, `/plans set <id> --intent active`.
3. If `pentimento` is not on `$PATH`, report that and stop; do not attempt to
   install or reimplement it.
