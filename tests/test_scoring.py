from sitecheck.models import CheckItem, CookieInfo, Severity, SiteReport, TlsInfo
from sitecheck.scoring import grade_for_score, grade_meets_threshold, score_report

GOOD_TLS = TlsInfo(valid=True, issuer="Let's Encrypt", days_to_expiry=60, tls_version="TLSv1.3")


def _ok(name: str) -> CheckItem:
    return CheckItem(name, Severity.OK, "fine")


def _fail(name: str) -> CheckItem:
    return CheckItem(name, Severity.FAIL, "missing")


def test_grade_for_score_boundaries():
    assert grade_for_score(100) == "A"
    assert grade_for_score(90) == "A"
    assert grade_for_score(89) == "B"
    assert grade_for_score(80) == "B"
    assert grade_for_score(79) == "C"
    assert grade_for_score(70) == "C"
    assert grade_for_score(69) == "D"
    assert grade_for_score(60) == "D"
    assert grade_for_score(59) == "F"
    assert grade_for_score(0) == "F"


def test_grade_meets_threshold():
    assert grade_meets_threshold("A", "C")
    assert grade_meets_threshold("C", "C")
    assert not grade_meets_threshold("D", "C")
    assert not grade_meets_threshold("F", "A")


def test_perfect_site_scores_a():
    report = SiteReport(
        host="good.example",
        url="https://good.example",
        header_checks=[
            _ok("Strict-Transport-Security"),
            _ok("Content-Security-Policy"),
            _ok("Frame protection"),
            _ok("X-Content-Type-Options"),
            _ok("Referrer-Policy"),
            _ok("Permissions-Policy"),
        ],
        tls=GOOD_TLS,
        redirects_to_https=True,
        info_leaks=[CheckItem("Server", Severity.OK, "not present")],
        cookie_checks=[CheckItem("Cookies", Severity.INFO, "no cookies set")],
    )

    score, grade = score_report(report)

    assert score == 100
    assert grade == "A"


def test_missing_headers_lower_the_grade():
    report = SiteReport(
        host="bad.example",
        url="https://bad.example",
        header_checks=[
            _fail("Strict-Transport-Security"),
            _fail("Content-Security-Policy"),
            _fail("Frame protection"),
            _fail("X-Content-Type-Options"),
        ],
        tls=GOOD_TLS,
        redirects_to_https=True,
    )

    score, grade = score_report(report)

    assert score == 100 - (15 + 15 + 10 + 8)
    assert grade == "F"


def test_invalid_tls_is_severely_penalized():
    report = SiteReport(
        host="bad-tls.example",
        url="https://bad-tls.example",
        tls=TlsInfo(valid=False, error="certificate verification failed"),
        redirects_to_https=True,
    )

    score, grade = score_report(report)

    assert score == 100 - 40
    assert grade == "D"


def test_expiring_cert_gets_a_warning_penalty():
    report = SiteReport(
        host="expiring.example",
        url="https://expiring.example",
        tls=TlsInfo(valid=True, issuer="CA", days_to_expiry=5, tls_version="TLSv1.3"),
        redirects_to_https=True,
    )

    score, _ = score_report(report)

    assert score == 100 - 10


def test_old_tls_version_is_penalized():
    report = SiteReport(
        host="old-tls.example",
        url="https://old-tls.example",
        tls=TlsInfo(valid=True, issuer="CA", days_to_expiry=100, tls_version="TLSv1.1"),
        redirects_to_https=True,
    )

    score, _ = score_report(report)

    assert score == 100 - 15


def test_no_https_redirect_is_penalized():
    report = SiteReport(
        host="no-redirect.example",
        url="https://no-redirect.example",
        tls=GOOD_TLS,
        redirects_to_https=False,
    )

    score, _ = score_report(report)

    assert score == 100 - 15


def test_insecure_cookie_is_penalized():
    report = SiteReport(
        host="cookie.example",
        url="https://cookie.example",
        tls=GOOD_TLS,
        redirects_to_https=True,
        cookies=[CookieInfo(name="session", secure=False, http_only=False, same_site=None)],
        cookie_checks=[CheckItem("Cookie 'session'", Severity.WARN, "missing Secure, HttpOnly")],
    )

    score, _ = score_report(report)

    assert score == 100 - 5


def test_fetch_error_forces_grade_f():
    report = SiteReport(
        host="unreachable.example",
        url="https://unreachable.example",
        fetch_error="DNS resolution failed (host not found)",
        tls=GOOD_TLS,
        redirects_to_https=True,
    )

    score, grade = score_report(report)

    assert score == 0
    assert grade == "F"
