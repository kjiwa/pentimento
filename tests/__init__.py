import argparse


def _header_block(lines: list[str]) -> list[str]:
    """The flowed frontmatter lines: after the title and its blank line, up to the next blank."""
    body_start = lines.index("", 2)
    return lines[2:body_start]


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
