# shellcheck shell=sh
# Sourced by `gh cut`; see https://github.com/kjiwa/gh-cut.

release_version() {
  sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n1
}

release_bump() {
  sed "s/^version = \".*\"\$/version = \"$1\"/" pyproject.toml >pyproject.toml.new
  mv pyproject.toml.new pyproject.toml
}

release_checks() {
  python3 -m unittest discover
  uvx ruff check
  uvx ruff format --check
}
