import httpx

from sitecheck.cookies import check_cookies, parse_cookies
from sitecheck.models import Severity


def test_parse_cookie_with_all_attributes():
    headers = httpx.Headers(
        [("set-cookie", "session=abc123; Secure; HttpOnly; SameSite=Strict; Path=/")]
    )

    cookies = parse_cookies(headers)

    assert len(cookies) == 1
    cookie = cookies[0]
    assert cookie.name == "session"
    assert cookie.secure is True
    assert cookie.http_only is True
    assert cookie.same_site == "Strict"


def test_parse_cookie_missing_attributes():
    headers = httpx.Headers([("set-cookie", "tracking=xyz; Path=/")])

    cookie = parse_cookies(headers)[0]

    assert cookie.secure is False
    assert cookie.http_only is False
    assert cookie.same_site is None


def test_parse_multiple_cookies():
    headers = httpx.Headers(
        [
            ("set-cookie", "a=1; Secure; HttpOnly; SameSite=Lax"),
            ("set-cookie", "b=2"),
        ]
    )

    cookies = parse_cookies(headers)

    assert [c.name for c in cookies] == ["a", "b"]


def test_check_cookies_no_cookies_is_informational():
    results = check_cookies([])

    assert len(results) == 1
    assert results[0].severity == Severity.INFO


def test_check_cookies_flags_missing_attributes():
    headers = httpx.Headers([("set-cookie", "session=abc; Path=/")])
    cookies = parse_cookies(headers)

    results = check_cookies(cookies)

    assert results[0].severity == Severity.WARN
    assert "Secure" in results[0].message
    assert "HttpOnly" in results[0].message
    assert "SameSite" in results[0].message


def test_check_cookies_all_secure_is_ok():
    headers = httpx.Headers([("set-cookie", "session=abc; Secure; HttpOnly; SameSite=Strict")])
    cookies = parse_cookies(headers)

    results = check_cookies(cookies)

    assert results[0].severity == Severity.OK
