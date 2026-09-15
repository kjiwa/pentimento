# Changelog

## 0.1.1

`list` and `tree` now always render STATUS, INTENT, PROJECT, and SOURCE,
instead of hiding a column when every plan in the result shares one value.
Narrow terminals still drop columns by the existing fit-driven priority.

## 0.1.0

First release. Reads a directory of agent plan files (Claude Code, Cursor),
derives status, intent, lineage, and project into a frontmatter block, and
provides a CLI (`list`, `tree`, `show`, `set`, `backfill`, `hook`, `index`,
`check`, `history`) to work with the corpus.
