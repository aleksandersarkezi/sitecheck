import httpx
import pytest

from sitecheck.engine import analyze
from sitecheck.guard import (
    GuardedTransport,
    TargetNotAllowed,
    clean_host,
    ensure_public,
    is_public_ip,
    validate_target,
)
from sitecheck.models import TlsInfo

PUBLIC = "93.184.215.14"


def fake_resolver(table: dict[str, list[str]]):
    def resolve(host: str) -> list[str]:
        if host not in table:
            import socket

            raise socket.gaierror("not found")
        return table[host]

    return resolve


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("  Example.COM  ", "example.com"),
        ("https://example.com", "example.com"),
        ("http://example.com/some/path?q=1#x", "example.com"),
        ("example.com.", "example.com"),
        ("sub.domain.example.co.uk", "sub.domain.example.co.uk"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
        ("example.com/a@b", "example.com"),
    ],
)
def test_clean_host_accepts(raw, expected):
    assert clean_host(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "localhost",
        "127.0.0.1",
        "http://10.0.0.1/",
        "169.254.169.254",
        "[::1]",
        "example.com:6379",
        "https://example.com:8443/",
        "user:pass@example.com",
        "user@example.com",
        "ftp://example.com",
        "file:///etc/passwd",
        "exa mple.com",
        "-bad.example.com",
        "a" * 300 + ".com",
        "example.123",
    ],
)
def test_clean_host_rejects(raw):
    with pytest.raises(TargetNotAllowed):
        clean_host(raw)


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.215.14", True),
        ("2606:2800:21f:cb07:6820:80da:af6b:8b2c", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),  # cloud metadata
        ("100.64.0.1", False),  # carrier-grade NAT
        ("0.0.0.0", False),
        ("::1", False),
        ("fe80::1", False),
        ("fd00::1", False),
        ("::ffff:127.0.0.1", False),  # IPv4-mapped loopback
        ("224.0.0.1", False),
    ],
)
def test_is_public_ip(address, public):
    assert is_public_ip(address) is public


def test_ensure_public_rejects_if_any_address_is_private():
    resolver = fake_resolver({"mixed.example": [PUBLIC, "10.0.0.5"]})
    with pytest.raises(TargetNotAllowed, match="non-public"):
        ensure_public("mixed.example", resolver)


def test_ensure_public_error_does_not_leak_internal_address():
    resolver = fake_resolver({"internal.example": ["10.0.0.5"]})
    with pytest.raises(TargetNotAllowed) as info:
        ensure_public("internal.example", resolver)
    assert "10.0.0.5" not in str(info.value)


def test_validate_target_unknown_host():
    with pytest.raises(TargetNotAllowed, match="DNS"):
        validate_target("nope.example", fake_resolver({}))


def test_validate_target_ok():
    assert validate_target("https://ok.example/", fake_resolver({"ok.example": [PUBLIC]})) == (
        "ok.example"
    )


def _guarded(handler, table):
    return GuardedTransport(inner=httpx.MockTransport(handler), resolver=fake_resolver(table))


def test_guarded_transport_blocks_redirect_to_metadata_endpoint():
    """A public site redirecting to an internal address is the classic SSRF bypass."""
    hit_internal = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "evil.example":
            return httpx.Response(302, headers={"location": "http://metadata.example/latest/"})
        hit_internal.append(request.url)
        return httpx.Response(200, text="secret credentials")

    transport = _guarded(
        handler, {"evil.example": [PUBLIC], "metadata.example": ["169.254.169.254"]}
    )
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        with pytest.raises(httpx.ConnectError, match="blocked redirect target"):
            client.get("https://evil.example/")
    assert hit_internal == []


def test_guarded_transport_blocks_redirect_to_ip_literal():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    transport = _guarded(handler, {"evil.example": [PUBLIC]})
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        with pytest.raises(httpx.ConnectError):
            client.get("https://evil.example/")


def test_guarded_transport_blocks_odd_ports():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://other.example:6379/"})

    transport = _guarded(handler, {"evil.example": [PUBLIC], "other.example": [PUBLIC]})
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        with pytest.raises(httpx.ConnectError, match="ports"):
            client.get("https://evil.example/")


def test_guarded_transport_allows_public_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.example":
            return httpx.Response(301, headers={"location": "https://b.example/"})
        return httpx.Response(200, text="ok")

    transport = _guarded(handler, {"a.example": [PUBLIC], "b.example": [PUBLIC]})
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        response = client.get("https://a.example/")
    assert response.status_code == 200
    assert response.url.host == "b.example"


def test_analyze_with_guard_reports_blocked_redirect_as_fetch_error(monkeypatch):
    monkeypatch.setattr(
        "sitecheck.engine.check_tls",
        lambda host, timeout=10.0: TlsInfo(valid=True, days_to_expiry=60, tls_version="TLSv1.3"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    transport = _guarded(handler, {"evil.example": [PUBLIC]})
    report = analyze("evil.example", transport=transport)

    assert report.fetch_error is not None
    assert "blocked" in report.fetch_error
    assert report.grade == "F"
