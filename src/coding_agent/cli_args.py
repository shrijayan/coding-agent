"""Command-line flag parsing for the REPL entry point.

Kept separate from cli.py's REPL loop so argument parsing - a distinct
responsibility - doesn't get tangled with terminal I/O wiring.
"""

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class CliArgs:
    """Everything parsed from the command line."""

    enabled_optimizations: list[str]
    benchmark: bool


def parse_args(argv: list[str] | None = None) -> CliArgs:
    """Parse the coding-agent command line.

    --enable accepts both repeated flags (--enable a --enable b) and
    comma-separated values within one flag (--enable a,b), and any mix
    of the two - so enabling one optimization or a combination is
    equally natural to type.

    --benchmark runs the fixed benchmark task suite instead of starting
    an interactive session - see benchmark/report.py.
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
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help=(
            "Run the fixed benchmark task suite (see benchmark/tasks.py) "
            "instead of starting an interactive session, and print a "
            "pass-rate/tokens/cost report. Combine with --enable to "
            "measure an optimization's effect."
        ),
    )
    args = parser.parse_args(argv)

    names: list[str] = []
    for value in args.enable:
        names.extend(part.strip() for part in value.split(",") if part.strip())

    return CliArgs(enabled_optimizations=names, benchmark=args.benchmark)
