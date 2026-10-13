import httpx

from sitecheck.headers import check_headers
from sitecheck.models import Severity


def _find(items, name):
    return next(item for item in items if item.name == name)


def test_all_headers_present_and_valid():
    headers = httpx.Headers(
        {
            "strict-transport-security": "max-age=31536000; includeSubDomains",
            "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "permissions-policy": "geolocation=()",
        }
    )

    results = check_headers(headers)

    assert all(item.severity == Severity.OK for item in results)


def test_missing_headers_are_flagged():
    headers = httpx.Headers({})

    results = check_headers(headers)

    assert _find(results, "Strict-Transport-Security").severity == Severity.FAIL
    assert _find(results, "Content-Security-Policy").severity == Severity.FAIL
    assert _find(results, "Frame protection").severity == Severity.FAIL
    assert _find(results, "X-Content-Type-Options").severity == Severity.FAIL
    assert _find(results, "Referrer-Policy").severity == Severity.WARN
    assert _find(results, "Permissions-Policy").severity == Severity.WARN


def test_weak_hsts_max_age_warns():
    headers = httpx.Headers({"strict-transport-security": "max-age=60"})

    result = _find(check_headers(headers), "Strict-Transport-Security")

    assert result.severity == Severity.WARN


def test_frame_ancestors_in_csp_satisfies_frame_protection():
    headers = httpx.Headers(
        {"content-security-policy": "default-src 'self'; frame-ancestors 'self'"}
    )

    result = _find(check_headers(headers), "Frame protection")

    assert result.severity == Severity.OK
    assert "frame-ancestors" in result.message


def test_x_frame_options_deny_is_ok():
    headers = httpx.Headers({"x-frame-options": "DENY"})

    result = _find(check_headers(headers), "Frame protection")

    assert result.severity == Severity.OK


def test_x_content_type_options_wrong_value_warns():
    headers = httpx.Headers({"x-content-type-options": "something-else"})

    result = _find(check_headers(headers), "X-Content-Type-Options")

    assert result.severity == Severity.WARN
