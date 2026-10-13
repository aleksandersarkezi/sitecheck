"""End-to-end analyze() tests using httpx.MockTransport, so no real network call
is ever made. The TLS check (a raw socket handshake) is monkeypatched separately
since it does not go through httpx.
"""

import httpx
import pytest

from sitecheck.engine import analyze
from sitecheck.models import TlsInfo

GOOD_TLS = TlsInfo(valid=True, issuer="Let's Encrypt", days_to_expiry=60, tls_version="TLSv1.3")


@pytest.fixture
def mock_good_tls(monkeypatch):
    monkeypatch.setattr("sitecheck.engine.check_tls", lambda host, timeout=10.0: GOOD_TLS)


def test_analyze_well_configured_site(mock_good_tls):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "http":
            return httpx.Response(301, headers={"location": "https://good.example/"})
        return httpx.Response(
            200,
            headers={
                "strict-transport-security": "max-age=31536000; includeSubDomains",
                "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
                "x-content-type-options": "nosniff",
                "referrer-policy": "no-referrer",
                "permissions-policy": "geolocation=()",
                "set-cookie": "session=abc; Secure; HttpOnly; SameSite=Strict",
            },
        )

    transport = httpx.MockTransport(handler)

    report = analyze("good.example", transport=transport)

    assert report.fetch_error is None
    assert report.status_code == 200
    assert report.redirects_to_https is True
    assert report.grade == "A"
    assert report.score == 100


def test_analyze_insecure_site(mock_good_tls):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "http":
            return httpx.Response(200, text="no redirect here")
        return httpx.Response(200, headers={"server": "Apache/2.4.1"})

    transport = httpx.MockTransport(handler)

    report = analyze("insecure.example", transport=transport)

    assert report.fetch_error is None
    assert report.redirects_to_https is False
    assert report.grade in {"C", "D", "F"}
    assert report.score is not None and report.score < 100


def test_analyze_unreachable_host(mock_good_tls):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Name or service not known", request=request)

    transport = httpx.MockTransport(handler)

    report = analyze("doesnotexist.invalid", transport=transport)

    assert report.fetch_error is not None
    assert "DNS" in report.fetch_error
    assert report.score == 0
    assert report.grade == "F"
