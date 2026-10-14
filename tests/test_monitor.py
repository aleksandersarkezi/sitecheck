"""Monitor, alert rules, storage and rate-limit helpers. No network."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from sitecheck.models import SiteReport, TlsInfo
from sitecheck.service.alerts import AlertKind, find_alerts, format_message, send_webhook
from sitecheck.service.monitor import load_watchlist, main, run_once
from sitecheck.service.ratelimit import RateLimiter, TTLCache
from sitecheck.service.store import Store


def report(host="a.example", grade="A", score=95, days=60, error=None, tls_valid=True):
    tls = (
        TlsInfo(valid=True, issuer="CA", days_to_expiry=days, tls_version="TLSv1.3")
        if tls_valid
        else TlsInfo(valid=False, error="certificate verification failed: expired")
    )
    return SiteReport(
        host=host, url=f"https://{host}", fetch_error=error, tls=tls, score=score, grade=grade
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "m.db")


def kinds(alerts):
    return [a.kind for a in alerts]


# --- alert rules -----------------------------------------------------------


def test_first_run_healthy_site_no_alerts(store):
    assert find_alerts(report(), None) == []


def test_grade_drop_alerts(store):
    store.save(report(grade="A", score=95))
    alerts = find_alerts(report(grade="C", score=72), store.latest("a.example"))
    assert kinds(alerts) == [AlertKind.GRADE_DROP]
    assert "A to C" in alerts[0].message


def test_grade_improvement_alerts(store):
    store.save(report(grade="D", score=62))
    assert kinds(find_alerts(report(grade="B", score=85), store.latest("a.example"))) == [
        AlertKind.GRADE_RECOVERED
    ]


def test_same_grade_is_quiet(store):
    store.save(report(grade="B", score=85))
    assert find_alerts(report(grade="B", score=82), store.latest("a.example")) == []


def test_site_down_alerts_once(store):
    down = report(grade="F", score=0, error="DNS resolution failed")
    assert kinds(find_alerts(down, None)) == [AlertKind.SITE_DOWN]
    store.save(down)
    # Still down on the next run: no repeat alert.
    assert find_alerts(down, store.latest("a.example")) == []


def test_site_recovered(store):
    store.save(report(grade="F", score=0, error="timeout"))
    alerts = find_alerts(report(grade="A"), store.latest("a.example"))
    # Recovery is reported; the jump from F to A is not a separate "improved" alert.
    assert kinds(alerts) == [AlertKind.SITE_RECOVERED]


def test_cert_expiring_alerts_every_run(store):
    store.save(report(days=10))
    assert kinds(find_alerts(report(days=9), store.latest("a.example"))) == [
        AlertKind.CERT_EXPIRING
    ]


def test_cert_invalid_alerts_on_change_only(store):
    broken = report(tls_valid=False, grade="F", score=40)
    store.save(report())
    assert AlertKind.CERT_INVALID in kinds(find_alerts(broken, store.latest("a.example")))
    store.save(broken)
    assert AlertKind.CERT_INVALID not in kinds(find_alerts(broken, store.latest("a.example")))


def test_format_message():
    alerts = find_alerts(report(days=3), None)
    text = format_message(alerts)
    assert text.startswith("**sitecheck monitor**")
    assert "expires in 3 days" in text


# --- webhook ---------------------------------------------------------------


def test_send_webhook_posts_discord_and_slack_keys():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(204)

    ok = send_webhook(
        "https://hooks.example/x",
        find_alerts(report(days=3), None),
        transport=httpx.MockTransport(handler),
    )
    assert ok is True
    assert b'"content"' in seen["body"] and b'"text"' in seen["body"]


def test_send_webhook_failure_is_not_raised(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    ok = send_webhook(
        "https://hooks.example/secret-token",
        find_alerts(report(days=3), None),
        transport=httpx.MockTransport(handler),
    )
    assert ok is False
    assert "secret-token" not in caplog.text


def test_send_webhook_noop_without_alerts():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("should not send")

    assert send_webhook("https://hooks.example/x", [], transport=httpx.MockTransport(handler))


# --- store -----------------------------------------------------------------


def test_store_latest_all_and_history(store):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    store.save(report("b.example", "A"), t0)
    store.save(report("a.example", "B"), t0)
    store.save(report("a.example", "C"), t0 + timedelta(hours=6))

    latest = store.latest_all()
    assert [(c.host, c.grade) for c in latest] == [("a.example", "C"), ("b.example", "A")]
    assert [c.grade for c in store.history("a.example")] == ["C", "B"]
    assert store.latest("missing.example") is None


def test_store_prune_keeps_newest(store):
    for score in range(10):
        store.save(report(score=score))
    removed = store.prune(keep_per_host=3)
    assert removed == 7
    assert [c.score for c in store.history("a.example")] == [9, 8, 7]


# --- watchlist + run --------------------------------------------------------


def test_load_watchlist(tmp_path):
    path = tmp_path / "sites.txt"
    path.write_text(
        "# my sites\nexample.com\nhttps://Example.com/\n\nlocalhost\nshop.example.si  # client\n"
        "127.0.0.1\n",
        encoding="utf-8",
    )
    assert load_watchlist(path) == ["example.com", "shop.example.si"]


def test_run_once_saves_and_sends(store):
    store.save(report("a.example", "A", 95))
    sent = []

    def analyzer(host):
        if host == "broken.example":
            raise RuntimeError("boom")
        return report(host, "D", 62)

    alerts = run_once(
        ["a.example", "broken.example", "new.example"],
        store,
        analyzer,
        webhook_url="https://hooks.example/x",
        send=lambda url, a: sent.append(a) or True,
    )

    assert kinds(alerts) == [AlertKind.GRADE_DROP]
    assert len(sent) == 1
    assert store.latest("new.example").grade == "D"
    assert store.latest("broken.example") is None


def test_run_once_without_webhook_logs(store, caplog):
    run_once(["a.example"], store, lambda h: report(h, days=2), webhook_url=None)
    assert "ALERT" in caplog.text


def test_main_rejects_too_short_interval(tmp_path):
    (tmp_path / "s.txt").write_text("example.com\n")
    code = main(
        ["--watchlist", str(tmp_path / "s.txt"), "--db", str(tmp_path / "d.db"), "--every", "5"]
    )
    assert code == 2


def test_main_missing_watchlist(tmp_path):
    code = main(["--watchlist", str(tmp_path / "nope.txt"), "--db", str(tmp_path / "d.db")])
    assert code == 2


# --- rate limiter / cache ---------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_rate_limiter_window():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window=60, clock=clock)
    assert limiter.allow("ip") and limiter.allow("ip")
    assert not limiter.allow("ip")
    assert limiter.allow("other-ip")
    clock.now = 61
    assert limiter.allow("ip")


def test_ttl_cache_expiry_and_bound():
    clock = FakeClock()
    cache: TTLCache[int] = TTLCache(ttl=10, max_items=2, clock=clock)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # evicts "a"
    assert cache.get("a") is None
    assert cache.get("c") == 3
    clock.now = 11
    assert cache.get("c") is None
