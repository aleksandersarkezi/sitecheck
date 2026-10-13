"""Renders a SiteReport as a colorful table using rich."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from .models import CheckItem, Severity, SiteReport, TlsInfo

SEVERITY_STYLES: dict[Severity, str] = {
    Severity.OK: "green",
    Severity.WARN: "yellow",
    Severity.FAIL: "red",
    Severity.INFO: "cyan",
}

GRADE_STYLES: dict[str, str] = {
    "A": "bold green",
    "B": "bold green",
    "C": "bold yellow",
    "D": "bold yellow",
    "F": "bold red",
}


def render_report(console: Console, report: SiteReport) -> None:
    """Print one site's findings and final grade to `console`."""
    console.rule(f"[bold]{report.host}[/bold]")

    if report.fetch_error:
        console.print(f"[red]Could not reach {report.url}: {report.fetch_error}[/red]")
        _print_grade(console, report)
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")

    for item in (*report.header_checks, *report.info_leaks, *report.cookie_checks):
        _add_item_row(table, item)

    _add_tls_row(table, report.tls)
    _add_redirect_row(table, report)

    console.print(table)
    _print_grade(console, report)


def _add_item_row(table: Table, item: CheckItem) -> None:
    style = SEVERITY_STYLES[item.severity]
    table.add_row(item.name, f"[{style}]{item.severity.value.upper()}[/{style}]", item.message)


def _add_tls_row(table: Table, tls: TlsInfo | None) -> None:
    if tls is None:
        return
    if not tls.valid:
        table.add_row("TLS Certificate", "[red]FAIL[/red]", tls.error or "invalid certificate")
        return
    severity = (
        Severity.WARN
        if tls.days_to_expiry is not None and tls.days_to_expiry < 14
        else Severity.OK
    )
    style = SEVERITY_STYLES[severity]
    details = f"issuer={tls.issuer}, expires in {tls.days_to_expiry}d, {tls.tls_version}"
    table.add_row("TLS Certificate", f"[{style}]{severity.value.upper()}[/{style}]", details)


def _add_redirect_row(table: Table, report: SiteReport) -> None:
    if report.redirects_to_https is None:
        severity = Severity.INFO
    elif report.redirects_to_https:
        severity = Severity.OK
    else:
        severity = Severity.FAIL
    style = SEVERITY_STYLES[severity]
    table.add_row(
        "HTTP -> HTTPS redirect",
        f"[{style}]{severity.value.upper()}[/{style}]",
        report.redirect_message,
    )


def _print_grade(console: Console, report: SiteReport) -> None:
    style = GRADE_STYLES.get(report.grade or "F", "bold red")
    console.print(f"Score: {report.score}/100  Grade: [{style}]{report.grade}[/{style}]\n")
