"""FastAPI web service around sitecheck.

Endpoints
    GET /                         HTML form; with ?host=... runs a check
    GET /api/check?host=...       JSON report (same shape as `sitecheck --json`)
    GET /api/monitored            latest monitor result per site
    GET /api/monitored/{host}     monitor history for one site
    GET /healthz                  liveness/readiness for Docker and uptime checks
    GET /metrics                  Prometheus metrics (blocked from the internet by Caddy)

Run locally:
    uvicorn sitecheck.service.app:create_app_from_env --factory --reload
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from .. import __version__
from ..engine import analyze
from ..guard import (
    GuardedTransport,
    Resolver,
    TargetNotAllowed,
    clean_host,
    default_resolver,
    ensure_public,
)
from ..models import SiteReport, report_to_dict
from . import views
from .ratelimit import RateLimiter, TTLCache
from .store import Store

log = logging.getLogger("sitecheck.service")

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

Analyzer = Callable[[str], SiteReport]


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/sitecheck.db"
    rate_limit_per_minute: int = 6
    cache_seconds: float = 600
    max_concurrent_scans: int = 4
    scan_timeout: float = 8.0
    public_url: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            db_path=env.get("SITECHECK_DB", cls.db_path),
            rate_limit_per_minute=int(env.get("SITECHECK_RATE_LIMIT", cls.rate_limit_per_minute)),
            cache_seconds=float(env.get("SITECHECK_CACHE_SECONDS", cls.cache_seconds)),
            max_concurrent_scans=int(env.get("SITECHECK_MAX_CONCURRENT", cls.max_concurrent_scans)),
            scan_timeout=float(env.get("SITECHECK_SCAN_TIMEOUT", cls.scan_timeout)),
            public_url=env.get("SITECHECK_PUBLIC_URL") or None,
        )


class CheckError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Metrics:
    """All Prometheus metrics, on a private registry so tests can build many apps."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.checks = Counter(
            "sitecheck_checks_total", "Checks served", ["result"], registry=self.registry
        )
        self.grades = Counter(
            "sitecheck_grades_total", "Grades of fresh checks", ["grade"], registry=self.registry
        )
        self.duration = Histogram(
            "sitecheck_scan_seconds",
            "Time spent scanning a site",
            buckets=(0.5, 1, 2, 4, 8, 16, 32),
            registry=self.registry,
        )
        self.monitored_score = Gauge(
            "sitecheck_monitored_score",
            "Latest monitor score per site",
            ["host"],
            registry=self.registry,
        )
        self.monitored_cert_days = Gauge(
            "sitecheck_monitored_cert_days",
            "Days until the TLS certificate expires, per monitored site",
            ["host"],
            registry=self.registry,
        )


def _default_analyzer(settings: Settings, resolver: Resolver) -> Analyzer:
    def run(host: str) -> SiteReport:
        transport = GuardedTransport(resolver=resolver)
        try:
            return analyze(host, timeout=settings.scan_timeout, transport=transport)
        finally:
            transport.close()

    return run


def create_app(
    settings: Settings | None = None,
    analyzer: Analyzer | None = None,
    resolver: Resolver = default_resolver,
) -> FastAPI:
    """App factory. Tests pass a fake analyzer/resolver so nothing touches the network."""
    settings = settings or Settings.from_env()
    analyzer = analyzer or _default_analyzer(settings, resolver)
    store = Store(settings.db_path)
    limiter = RateLimiter(settings.rate_limit_per_minute, 60)
    cache: TTLCache[dict] = TTLCache(settings.cache_seconds)
    scan_slots = threading.BoundedSemaphore(settings.max_concurrent_scans)
    metrics = Metrics()

    app = FastAPI(title="sitecheck", version=__version__, docs_url="/api/docs", redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(files(__package__) / "static")), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/") or request.url.path == "/":
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def run_check(raw_host: str, client_ip: str) -> tuple[dict, bool]:
        """Validate, rate-limit and scan. Returns (report_dict, was_cached)."""
        try:
            host = clean_host(raw_host)
        except TargetNotAllowed as exc:
            metrics.checks.labels("rejected").inc()
            raise CheckError(400, str(exc)) from exc

        cached = cache.get(host)
        if cached is not None:
            metrics.checks.labels("cached").inc()
            return cached, True

        if not limiter.allow(client_ip):
            metrics.checks.labels("rate_limited").inc()
            raise CheckError(429, "Too many checks, try again in a minute.")

        try:
            ensure_public(host, resolver)
        except TargetNotAllowed as exc:
            metrics.checks.labels("rejected").inc()
            raise CheckError(400, str(exc)) from exc

        if not scan_slots.acquire(blocking=False):
            metrics.checks.labels("busy").inc()
            raise CheckError(503, "Server is busy, try again in a few seconds.")
        try:
            started = time.perf_counter()
            report = analyzer(host)
            metrics.duration.observe(time.perf_counter() - started)
        finally:
            scan_slots.release()

        result = report_to_dict(report)
        cache.set(host, result)
        metrics.checks.labels("fresh").inc()
        metrics.grades.labels(report.grade or "none").inc()
        log.info("checked %s grade=%s ip=%s", host, report.grade, client_ip)
        return result, False

    def public_base(request: Request) -> str:
        """The site's own URL for canonical links and the sitemap.

        SITECHECK_PUBLIC_URL wins when set; otherwise the request decides
        (uvicorn's --proxy-headers makes this https:// behind Caddy).
        """
        return settings.public_url or str(request.base_url)

    def client_ip(request: Request) -> str:
        # uvicorn runs with --proxy-headers behind Caddy, so this is the
        # visitor's address, not the proxy's.
        return request.client.host if request.client else "unknown"

    # Plain `def` endpoints: FastAPI runs them in a thread pool, which is what
    # we want for the blocking socket/httpx calls inside analyze().

    @app.get("/healthz")
    def healthz() -> dict:
        store.latest_all()  # fails loudly if the database is unreadable
        return {"status": "ok", "version": __version__}

    @app.get("/api/check")
    def api_check(
        request: Request, host: Annotated[str, Query(min_length=1, max_length=300)]
    ) -> JSONResponse:
        try:
            result, cached = run_check(host, client_ip(request))
        except CheckError as exc:
            return JSONResponse({"error": exc.message}, status_code=exc.status)
        return JSONResponse({**result, "cached": cached})

    @app.get("/api/monitored")
    def api_monitored() -> list[dict]:
        return [
            {
                "host": c.host,
                "grade": c.grade,
                "score": c.score,
                "days_to_expiry": c.days_to_expiry,
                "fetch_error": c.fetch_error,
                "checked_at": c.checked_at.isoformat(),
            }
            for c in store.latest_all()
        ]

    @app.get("/api/monitored/{host}")
    def api_monitored_history(host: str, limit: Annotated[int, Query(ge=1, le=200)] = 30):
        history = store.history(host.lower(), limit)
        if not history:
            return JSONResponse({"error": "site is not monitored"}, status_code=404)
        return [
            {
                "checked_at": c.checked_at.isoformat(),
                "grade": c.grade,
                "score": c.score,
                "days_to_expiry": c.days_to_expiry,
                "fetch_error": c.fetch_error,
            }
            for c in history
        ]

    @app.get("/metrics")
    def metrics_endpoint() -> Response:
        for check in store.latest_all():
            if check.score is not None:
                metrics.monitored_score.labels(check.host).set(check.score)
            if check.days_to_expiry is not None:
                metrics.monitored_cert_days.labels(check.host).set(check.days_to_expiry)
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, host: Annotated[str | None, Query(max_length=300)] = None):
        parts = [views.hero(host or "", compact=bool(host))]
        status = 200
        if not host:
            parts.append(views.explainer())
        else:
            try:
                result, cached = run_check(host, client_ip(request))
                parts.append(views.report_view(result, cached))
            except CheckError as exc:
                status = exc.status
                parts.append(views.error_box(exc.message, exc.status))
        parts.append(views.monitored_view(store.latest_all()))
        title = (
            f"{host} – sitecheck"
            if host
            else "sitecheck – free website security checker by Aleksander Šarkezi"
        )
        html = views.page(
            "\n".join(parts), title, base_url=public_base(request), indexable=not host
        )
        return HTMLResponse(html, status_code=status)

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots(request: Request) -> str:
        return views.robots_txt(public_base(request))

    @app.get("/sitemap.xml")
    def sitemap(request: Request) -> Response:
        return Response(views.sitemap_xml(public_base(request)), media_type="application/xml")

    return app


def _lazy_app() -> FastAPI:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return create_app()


# `uvicorn sitecheck.service.app:app` needs a module-level object, but building
# it at import time would create a database file whenever tests import this
# module. `--factory` with `create_app_from_env` avoids that; see Dockerfile.
create_app_from_env = _lazy_app
