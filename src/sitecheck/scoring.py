"""Turns a SiteReport's raw findings into a 0-100 score and an A-F grade.

Kept separate from the network/parsing code so the scoring logic can be
unit tested purely with constructed SiteReport objects.
"""

from __future__ import annotations

from .models import SiteReport, Severity, TlsInfo

MAX_SCORE = 100

HEADER_WEIGHTS: dict[str, int] = {
    "Strict-Transport-Security": 15,
    "Content-Security-Policy": 15,
    "Frame protection": 10,
    "X-Content-Type-Options": 8,
    "Referrer-Policy": 5,
    "Permissions-Policy": 5,
}
DEFAULT_HEADER_WEIGHT = 5

TLS_INVALID_PENALTY = 40
TLS_EXPIRY_WARN_PENALTY = 10
TLS_OLD_VERSION_PENALTY = 15
NO_REDIRECT_PENALTY = 15
INFO_LEAK_PENALTY = 5
COOKIE_ISSUE_PENALTY = 5

OLD_TLS_VERSIONS = {"SSLv2", "SSLv3", "TLSv1", "TLSv1.1"}

GRADE_ORDER = ["F", "D", "C", "B", "A"]
GRADE_THRESHOLDS = [(90, "A"), (80, "B"), (70, "C"), (60, "D")]


def score_report(report: SiteReport) -> tuple[int, str]:
    """Compute (score, grade) for a fully- or partially-populated SiteReport."""
    if report.fetch_error:
        return 0, "F"

    penalty = (
        _header_penalty(report)
        + _tls_penalty(report.tls)
        + _redirect_penalty(report.redirects_to_https)
        + _info_leak_penalty(report)
        + _cookie_penalty(report)
    )
    score = max(0, min(MAX_SCORE, MAX_SCORE - penalty))
    return score, grade_for_score(score)


def grade_for_score(score: int) -> str:
    """Map a 0-100 score to an A-F letter grade."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def grade_meets_threshold(grade: str, threshold: str) -> bool:
    """Return True if `grade` is at least as good as `threshold` (e.g. B >= C)."""
    return GRADE_ORDER.index(grade) >= GRADE_ORDER.index(threshold)


def _header_penalty(report: SiteReport) -> int:
    penalty = 0
    for item in report.header_checks:
        weight = HEADER_WEIGHTS.get(item.name, DEFAULT_HEADER_WEIGHT)
        if item.severity == Severity.FAIL:
            penalty += weight
        elif item.severity == Severity.WARN:
            penalty += weight // 2
    return penalty


def _tls_penalty(tls: TlsInfo | None) -> int:
    if tls is None or not tls.valid:
        return TLS_INVALID_PENALTY
    penalty = 0
    if tls.days_to_expiry is not None and tls.days_to_expiry < 14:
        penalty += TLS_EXPIRY_WARN_PENALTY
    if tls.tls_version in OLD_TLS_VERSIONS:
        penalty += TLS_OLD_VERSION_PENALTY
    return penalty


def _redirect_penalty(redirects_to_https: bool | None) -> int:
    return NO_REDIRECT_PENALTY if redirects_to_https is False else 0


def _info_leak_penalty(report: SiteReport) -> int:
    return sum(INFO_LEAK_PENALTY for item in report.info_leaks if item.severity == Severity.WARN)


def _cookie_penalty(report: SiteReport) -> int:
    return sum(COOKIE_ISSUE_PENALTY for item in report.cookie_checks if item.severity == Severity.WARN)
