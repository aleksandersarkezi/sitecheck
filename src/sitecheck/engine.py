"""Orchestrates all checks for a single host into one SiteReport."""

from __future__ import annotations

from .cookies import check_cookies, parse_cookies
from .fetcher import FetchError, fetch
from .headers import check_headers
from .info_leak import check_info_leaks
from .models import SiteReport
from .redirect import check_https_redirect
from .scoring import score_report
from .tls import check_tls


def normalize_host(raw: str) -> tuple[str, str]:
    """Return (host, https_url) for a user-supplied hostname or URL."""
    value = raw.strip()
    if value.startswith("http://"):
        value = value[len("http://") :]
    elif value.startswith("https://"):
        value = value[len("https://") :]
    host = value.split("/", 1)[0]
    return host, f"https://{host}"


def analyze(raw_host: str, timeout: float = 10.0) -> SiteReport:
    """Run every passive check against `raw_host` and return the full report."""
    host, url = normalize_host(raw_host)
    report = SiteReport(host=host, url=url)

    report.tls = check_tls(host, timeout=timeout)
    report.redirects_to_https, report.redirect_message = check_https_redirect(
        host, timeout=timeout
    )

    try:
        response = fetch(url, timeout=timeout)
    except FetchError as exc:
        report.fetch_error = str(exc)
        report.score, report.grade = score_report(report)
        return report

    report.status_code = response.status_code
    report.header_checks = check_headers(response.headers)
    report.info_leaks = check_info_leaks(response.headers)
    report.cookies = parse_cookies(response.headers)
    report.cookie_checks = check_cookies(report.cookies)

    report.score, report.grade = score_report(report)
    return report
