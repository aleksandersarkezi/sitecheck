"""Command-line interface for sitecheck."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console

from .engine import analyze
from .models import SiteReport, report_to_dict
from .report_view import render_report
from .scoring import GRADE_ORDER, grade_meets_threshold


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sitecheck",
        description="Passively check a website's security headers, TLS setup, and cookies, "
        "and grade it A-F.",
    )
    parser.add_argument(
        "hosts",
        nargs="*",
        help="Hostnames or URLs to check, e.g. example.com",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Path to a text file with one host/URL per line (blank lines and "
        "lines starting with # are ignored)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a formatted table",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request network timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--fail-under",
        choices=GRADE_ORDER,
        default=None,
        metavar="{A,B,C,D,F}",
        help="Exit with a non-zero status if any site's grade is worse than this "
        "(useful in CI)",
    )
    return parser


def _collect_hosts(args: argparse.Namespace, console: Console) -> list[str] | None:
    hosts = list(args.hosts)
    if args.file:
        try:
            lines = args.file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            console.print(f"[red]Could not read {args.file}: {exc}[/red]")
            return None
        hosts.extend(
            line.strip() for line in lines if line.strip() and not line.strip().startswith("#")
        )

    if not hosts:
        console.print("[red]No hosts given. Pass a host or use -f/--file.[/red]")
        return None
    return hosts


def run(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, run checks, print results, and return an exit code."""
    args = build_parser().parse_args(argv)
    console = Console()

    hosts = _collect_hosts(args, console)
    if hosts is None:
        return 2

    reports: list[SiteReport] = [analyze(host, timeout=args.timeout) for host in hosts]

    if args.json:
        print(json.dumps([report_to_dict(report) for report in reports], indent=2))
    else:
        for report in reports:
            render_report(console, report)

    if args.fail_under is not None:
        if any(not grade_meets_threshold(r.grade or "F", args.fail_under) for r in reports):
            return 1
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
