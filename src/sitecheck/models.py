"""Data models shared across sitecheck's checks, scoring, and output."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Severity(StrEnum):
    """How serious a single check's finding is."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"


@dataclass
class CheckItem:
    """A single pass/fail/warn finding, e.g. one security header."""

    name: str
    severity: Severity
    message: str


@dataclass
class CookieInfo:
    """A single Set-Cookie header, parsed into its relevant attributes."""

    name: str
    secure: bool
    http_only: bool
    same_site: str | None


@dataclass
class TlsInfo:
    """Result of inspecting a host's TLS certificate and protocol version."""

    valid: bool
    issuer: str | None = None
    not_after: datetime | None = None
    days_to_expiry: int | None = None
    tls_version: str | None = None
    error: str | None = None


@dataclass
class SiteReport:
    """The full result of analyzing one site, including its final score."""

    host: str
    url: str
    fetch_error: str | None = None
    status_code: int | None = None
    header_checks: list[CheckItem] = field(default_factory=list)
    tls: TlsInfo | None = None
    redirects_to_https: bool | None = None
    redirect_message: str = ""
    info_leaks: list[CheckItem] = field(default_factory=list)
    cookies: list[CookieInfo] = field(default_factory=list)
    cookie_checks: list[CheckItem] = field(default_factory=list)
    score: int | None = None
    grade: str | None = None


def report_to_dict(report: SiteReport) -> dict:
    """Convert a SiteReport into a JSON-serializable plain dict."""
    return {
        "host": report.host,
        "url": report.url,
        "fetch_error": report.fetch_error,
        "status_code": report.status_code,
        "score": report.score,
        "grade": report.grade,
        "header_checks": [_item_to_dict(item) for item in report.header_checks],
        "tls": _tls_to_dict(report.tls),
        "redirects_to_https": report.redirects_to_https,
        "redirect_message": report.redirect_message,
        "info_leaks": [_item_to_dict(item) for item in report.info_leaks],
        "cookies": [_cookie_to_dict(cookie) for cookie in report.cookies],
        "cookie_checks": [_item_to_dict(item) for item in report.cookie_checks],
    }


def _item_to_dict(item: CheckItem) -> dict:
    return {"name": item.name, "severity": item.severity.value, "message": item.message}


def _cookie_to_dict(cookie: CookieInfo) -> dict:
    return {
        "name": cookie.name,
        "secure": cookie.secure,
        "http_only": cookie.http_only,
        "same_site": cookie.same_site,
    }


def _tls_to_dict(tls: TlsInfo | None) -> dict | None:
    if tls is None:
        return None
    return {
        "valid": tls.valid,
        "issuer": tls.issuer,
        "not_after": tls.not_after.isoformat() if tls.not_after else None,
        "days_to_expiry": tls.days_to_expiry,
        "tls_version": tls.tls_version,
        "error": tls.error,
    }
