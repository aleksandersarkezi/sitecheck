"""Web service tests. The analyzer and DNS resolver are faked, so no network."""

import pytest
from fastapi.testclient import TestClient

from sitecheck.models import CheckItem, Severity, SiteReport, TlsInfo
from sitecheck.service.app import Settings, create_app
from sitecheck.service.store import Store

PUBLIC = "93.184.215.14"


def make_report(host: str, grade: str = "B", score: int = 85) -> SiteReport:
    return SiteReport(
        host=host,
        url=f"https://{host}",
        status_code=200,
        header_checks=[CheckItem("Content-Security-Policy", Severity.FAIL, "header missing")],
        tls=TlsInfo(valid=True, issuer="Test CA", days_to_expiry=60, tls_version="TLSv1.3"),
        redirects_to_https=True,
        redirect_message="http:// redirects to https://",
        score=score,
        grade=grade,
    )


class FakeAnalyzer:
    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, host: str) -> SiteReport:
        self.calls.append(host)
        return make_report(host)


def resolver(host: str) -> list[str]:
    return {"internal.example": ["10.0.0.7"]}.get(host, [PUBLIC])


@pytest.fixture
def analyzer():
    return FakeAnalyzer()


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "test.db"), rate_limit_per_minute=3)


@pytest.fixture
def client(settings, analyzer):
    return TestClient(create_app(settings, analyzer=analyzer, resolver=resolver))


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_check_returns_report(client, analyzer):
    response = client.get("/api/check", params={"host": "https://Good.example/path"})
    assert response.status_code == 200
    body = response.json()
    assert body["host"] == "good.example"
    assert body["grade"] == "B"
    assert body["cached"] is False
    assert analyzer.calls == ["good.example"]


def test_api_check_uses_cache(client, analyzer):
    client.get("/api/check", params={"host": "good.example"})
    second = client.get("/api/check", params={"host": "good.example"})
    assert second.json()["cached"] is True
    assert analyzer.calls == ["good.example"]


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "example.com:22", "a@b.example"])
def test_api_check_rejects_bad_input(client, analyzer, host):
    response = client.get("/api/check", params={"host": host})
    assert response.status_code == 400
    assert "error" in response.json()
    assert analyzer.calls == []


def test_api_check_rejects_hosts_resolving_to_private_ip(client, analyzer):
    response = client.get("/api/check", params={"host": "internal.example"})
    assert response.status_code == 400
    assert "10.0.0.7" not in response.text
    assert analyzer.calls == []


def test_api_check_rate_limits_per_client(client):
    statuses = [
        client.get("/api/check", params={"host": f"site{i}.example"}).status_code for i in range(5)
    ]
    assert statuses == [200, 200, 200, 429, 429]


def test_cached_results_do_not_count_against_rate_limit(client):
    for _ in range(10):
        assert client.get("/api/check", params={"host": "same.example"}).status_code == 200


def test_busy_when_no_scan_slots(tmp_path):
    settings = Settings(db_path=str(tmp_path / "t.db"), max_concurrent_scans=1)
    app_holder = {}

    def nested_analyzer(host: str) -> SiteReport:
        # While this scan holds the only slot, a second request must get 503.
        inner = app_holder["client"].get("/api/check", params={"host": "other.example"})
        app_holder["inner_status"] = inner.status_code
        return make_report(host)

    client = TestClient(create_app(settings, analyzer=nested_analyzer, resolver=resolver))
    app_holder["client"] = client
    assert client.get("/api/check", params={"host": "first.example"}).status_code == 200
    assert app_holder["inner_status"] == 503


def test_security_headers_present(client):
    response = client.get("/")
    for header in (
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
    ):
        assert header in response.headers
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_html_page_escapes_user_input(client):
    response = client.get("/", params={"host": "<script>alert(1)</script>"})
    assert response.status_code == 400
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_html_page_escapes_values_from_scanned_site(settings):
    def hostile(host: str) -> SiteReport:
        report = make_report(host)
        report.header_checks = [CheckItem("Server", Severity.INFO, "<img src=x onerror=alert(1)>")]
        return report

    client = TestClient(create_app(settings, analyzer=hostile, resolver=resolver))
    response = client.get("/", params={"host": "hostile.example"})
    assert response.status_code == 200
    assert "<img src=x" not in response.text
    assert "&lt;img src=x" in response.text


def test_html_page_shows_result(client):
    response = client.get("/", params={"host": "good.example"})
    assert response.status_code == 200
    assert "good.example" in response.text
    assert "Score 85/100" in response.text


def test_monitored_endpoints(settings, analyzer):
    store = Store(settings.db_path)
    store.save(make_report("watched.example", "A", 95))
    store.save(make_report("watched.example", "C", 72))

    client = TestClient(create_app(settings, analyzer=analyzer, resolver=resolver))
    latest = client.get("/api/monitored").json()
    assert latest == [
        {
            "host": "watched.example",
            "grade": "C",
            "score": 72,
            "days_to_expiry": 60,
            "fetch_error": None,
            "checked_at": latest[0]["checked_at"],
        }
    ]
    history = client.get("/api/monitored/watched.example").json()
    assert [h["grade"] for h in history] == ["C", "A"]
    assert client.get("/api/monitored/unknown.example").status_code == 404
    assert "watched.example" in client.get("/").text


def test_metrics(client, settings):
    Store(settings.db_path).save(make_report("watched.example", "A", 95))
    client.get("/api/check", params={"host": "good.example"})
    text = client.get("/metrics").text
    assert 'sitecheck_checks_total{result="fresh"} 1.0' in text
    assert 'sitecheck_monitored_score{host="watched.example"} 95.0' in text
    assert 'sitecheck_monitored_cert_days{host="watched.example"} 60.0' in text


def test_static_css_served(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_csp_allows_self_hosted_font(client):
    csp = client.get("/").headers["content-security-policy"]
    assert "font-src 'self'" in csp
    assert "script-src" not in csp  # no scripts at all
    assert client.get("/static/fonts/archivo.woff2").status_code == 200


def test_report_groups_checks(client):
    text = client.get("/", params={"host": "good.example"}).text
    assert "Connection" in text
    assert "Content protection" in text
    assert "1 problem out of" in text


def test_rate_limit_message_on_html_page(client):
    for i in range(3):
        client.get("/", params={"host": f"s{i}.example"})
    response = client.get("/", params={"host": "s9.example"})
    assert response.status_code == 429
    assert "Try again shortly" in response.text


def test_stylesheet_url_is_versioned(client):
    import re

    text = client.get("/").text
    match = re.search(r'href="(/static/style\.css\?v=[0-9a-f]{10})"', text)
    assert match
    assert client.get(match.group(1)).status_code == 200


def test_home_page_is_indexable_with_seo_tags(client):
    text = client.get("/").text
    assert 'rel="canonical"' in text
    assert 'property="og:image"' in text
    assert "application/ld+json" in text
    assert "Aleksander Šarkezi" in text
    assert "noindex" not in text


def test_result_pages_are_not_indexed(client):
    text = client.get("/", params={"host": "good.example"}).text
    assert 'content="noindex, follow"' in text
    assert 'rel="canonical"' not in text


def test_public_url_setting_wins(tmp_path, analyzer):
    settings = Settings(db_path=str(tmp_path / "t.db"), public_url="https://sc.example.com/")
    client = TestClient(create_app(settings, analyzer=analyzer, resolver=resolver))
    assert '<link rel="canonical" href="https://sc.example.com/">' in client.get("/").text
    assert "Sitemap: https://sc.example.com/sitemap.xml" in client.get("/robots.txt").text


def test_robots_and_sitemap(client):
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /api/" in robots.text
    assert "Sitemap: http://testserver/sitemap.xml" in robots.text
    sitemap = client.get("/sitemap.xml")
    assert sitemap.headers["content-type"].startswith("application/xml")
    assert "<loc>http://testserver/</loc>" in sitemap.text


def test_structured_data_is_valid_json(client):
    import json
    import re

    text = client.get("/").text
    raw = re.search(r'<script type="application/ld\+json">(.*?)</script>', text).group(1)
    data = json.loads(raw)
    assert data["author"]["name"] == "Aleksander Šarkezi"


def test_static_social_assets(client):
    assert client.get("/static/og.png").headers["content-type"] == "image/png"
    assert client.get("/static/favicon.svg").status_code == 200


def test_favicon_ico_served_at_root(client):
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/x-icon"
    assert client.get("/static/apple-touch-icon.png").status_code == 200


def test_badge_for_monitored_site(settings, analyzer):
    Store(settings.db_path).save(make_report("watched.example", "A", 95))
    client = TestClient(create_app(settings, analyzer=analyzer, resolver=resolver))
    response = client.get("/badge/watched.example.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "max-age=300" in response.headers["cache-control"]
    assert ">A</text>" in response.text
    assert "95/100, checked just now" in response.text
    assert analyzer.calls == []  # never scans


def test_badge_for_unmonitored_site_does_not_scan(client, analyzer):
    response = client.get("/badge/other.example.svg")
    assert response.status_code == 200
    assert "not monitored" in response.text
    assert analyzer.calls == []


def test_badge_rejects_bad_hosts(client):
    assert client.get("/badge/localhost.svg").status_code == 404
    assert client.get("/badge/%3Cscript%3E.svg").status_code == 404


def test_badge_age_text():
    from datetime import UTC, datetime, timedelta

    from sitecheck.service.store import StoredCheck
    from sitecheck.service.views import badge_svg

    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    check = StoredCheck("a.example", now - timedelta(hours=3), 88, "B", 50, None, {})
    svg = badge_svg("a.example", check, now)
    assert "88/100, checked 3 h ago" in svg
    assert ">B</text>" in svg
