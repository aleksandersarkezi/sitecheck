"""Checks for the presence and basic sanity of security-relevant HTTP headers."""

from __future__ import annotations

import httpx

from .models import CheckItem, Severity

MIN_HSTS_MAX_AGE = 15_768_000  # ~6 months, a commonly recommended floor


def check_headers(headers: httpx.Headers) -> list[CheckItem]:
    """Run all header checks and return one CheckItem per header."""
    return [
        _check_hsts(headers),
        _check_csp(headers),
        _check_frame_protection(headers),
        _check_content_type_options(headers),
        _check_referrer_policy(headers),
        _check_permissions_policy(headers),
    ]


def _check_hsts(headers: httpx.Headers) -> CheckItem:
    value = headers.get("strict-transport-security")
    if value is None:
        return CheckItem(
            "Strict-Transport-Security",
            Severity.FAIL,
            "header missing: browsers may be tricked into using plain HTTP",
        )
    max_age = _parse_max_age(value)
    if max_age is not None and max_age < MIN_HSTS_MAX_AGE:
        return CheckItem(
            "Strict-Transport-Security",
            Severity.WARN,
            f"max-age is only {max_age}s (recommended >= {MIN_HSTS_MAX_AGE}s)",
        )
    return CheckItem("Strict-Transport-Security", Severity.OK, value)


def _parse_max_age(value: str) -> int | None:
    for part in value.split(";"):
        key, _, raw_value = part.strip().partition("=")
        if key.strip().lower() == "max-age":
            try:
                return int(raw_value.strip())
            except ValueError:
                return None
    return None


def _check_csp(headers: httpx.Headers) -> CheckItem:
    value = headers.get("content-security-policy")
    if value is None:
        return CheckItem(
            "Content-Security-Policy",
            Severity.FAIL,
            "header missing: no mitigation against XSS/injection via content restrictions",
        )
    return CheckItem("Content-Security-Policy", Severity.OK, value)


def _check_frame_protection(headers: httpx.Headers) -> CheckItem:
    xfo = headers.get("x-frame-options")
    if xfo is not None:
        if xfo.strip().upper() in {"DENY", "SAMEORIGIN"}:
            return CheckItem("Frame protection", Severity.OK, f"X-Frame-Options: {xfo}")
        return CheckItem(
            "Frame protection", Severity.WARN, f"X-Frame-Options has unusual value: {xfo}"
        )
    csp = headers.get("content-security-policy", "")
    if "frame-ancestors" in csp.lower():
        return CheckItem(
            "Frame protection", Severity.OK, "enforced via CSP frame-ancestors"
        )
    return CheckItem(
        "Frame protection",
        Severity.FAIL,
        "no X-Frame-Options and no CSP frame-ancestors: page can be framed (clickjacking risk)",
    )


def _check_content_type_options(headers: httpx.Headers) -> CheckItem:
    value = headers.get("x-content-type-options")
    if value is None:
        return CheckItem(
            "X-Content-Type-Options",
            Severity.FAIL,
            "header missing: browsers may MIME-sniff responses",
        )
    if value.strip().lower() != "nosniff":
        return CheckItem(
            "X-Content-Type-Options", Severity.WARN, f"unexpected value: {value}"
        )
    return CheckItem("X-Content-Type-Options", Severity.OK, value)


def _check_referrer_policy(headers: httpx.Headers) -> CheckItem:
    value = headers.get("referrer-policy")
    if value is None:
        return CheckItem(
            "Referrer-Policy",
            Severity.WARN,
            "header missing: full URLs (possibly with sensitive query params) may leak via Referer",
        )
    return CheckItem("Referrer-Policy", Severity.OK, value)


def _check_permissions_policy(headers: httpx.Headers) -> CheckItem:
    value = headers.get("permissions-policy")
    if value is None:
        return CheckItem(
            "Permissions-Policy",
            Severity.WARN,
            "header missing: browser features (camera, mic, geolocation, ...) are not explicitly restricted",
        )
    return CheckItem("Permissions-Policy", Severity.OK, value)
