"""Command-line flag parsing for the REPL entry point.

Kept separate from cli.py's REPL loop so argument parsing - a distinct
responsibility - doesn't get tangled with terminal I/O wiring.
"""

import argparse


def parse_enabled_optimizations(argv: list[str] | None = None) -> list[str]:
    """Parse --enable flags into a flat list of optimization names.

    Accepts both repeated flags (--enable a --enable b) and comma-
    separated values within one flag (--enable a,b), and any mix of the
    two - so enabling one optimization or a combination is equally
    natural to type: `--enable conversation-summary` or
    `--enable conversation-summary,caching`.
    """
    parser = argparse.ArgumentParser(prog="coding-agent")
    parser.add_argument(
        "--enable",
        action="append",
        default=[],
        metavar="OPTIMIZATION",
        help=(
            "Enable an optimization by name. Repeatable, and each value "
            "may be a comma-separated list - `--enable a,b` and "
            "`--enable a --enable b` both work."
        ),
    )
    args = parser.parse_args(argv)

    names: list[str] = []
    for value in args.enable:
        names.extend(part.strip() for part in value.split(",") if part.strip())
    return names
