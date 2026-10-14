"""Scheduled monitoring: check every site on a watchlist, store, alert.

Run once (for cron / systemd timers):
    sitecheck-monitor --watchlist sites.txt --db data/sitecheck.db

Or keep running and repeat every N seconds (what docker-compose does):
    sitecheck-monitor --watchlist sites.txt --db data/sitecheck.db --every 21600

The webhook URL comes from the SITECHECK_WEBHOOK_URL environment variable so
it never ends up in shell history, the compose file or git.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from ..engine import analyze
from ..guard import GuardedTransport, TargetNotAllowed, clean_host
from ..models import SiteReport
from .alerts import Alert, find_alerts, send_webhook
from .store import Store

log = logging.getLogger("sitecheck.monitor")

MIN_INTERVAL_SECONDS = 300

Analyzer = Callable[[str], SiteReport]


def load_watchlist(path: Path) -> list[str]:
    """Read hosts (one per line, # comments). Invalid lines are logged and skipped."""
    hosts: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        try:
            host = clean_host(value)
        except TargetNotAllowed as exc:
            log.warning("%s:%d skipped %r: %s", path, lineno, value, exc)
            continue
        if host not in hosts:
            hosts.append(host)
    return hosts


def default_analyzer(timeout: float) -> Analyzer:
    def run(host: str) -> SiteReport:
        # Same SSRF guard as the web service: a monitored site that starts
        # redirecting into a private network must not be followed.
        transport = GuardedTransport()
        try:
            return analyze(host, timeout=timeout, transport=transport)
        finally:
            transport.close()

    return run


def run_once(
    hosts: Sequence[str],
    store: Store,
    analyzer: Analyzer,
    webhook_url: str | None = None,
    send: Callable[[str, list[Alert]], bool] = send_webhook,
) -> list[Alert]:
    """Check every host once, persist results, deliver alerts. Returns all alerts."""
    all_alerts: list[Alert] = []
    for host in hosts:
        previous = store.latest(host)
        try:
            report = analyzer(host)
        except Exception:  # one broken site must not stop the whole run
            log.exception("check failed for %s", host)
            continue
        store.save(report)
        alerts = find_alerts(report, previous)
        log.info("%s grade=%s score=%s alerts=%d", host, report.grade, report.score, len(alerts))
        all_alerts.extend(alerts)

    removed = store.prune()
    if removed:
        log.info("pruned %d old rows", removed)

    if all_alerts:
        if webhook_url:
            send(webhook_url, all_alerts)
        else:
            for alert in all_alerts:
                log.warning("ALERT %s", alert.message)
    return all_alerts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sitecheck-monitor", description="Check a list of sites, store results, alert."
    )
    parser.add_argument("--watchlist", type=Path, required=True, help="file with one host per line")
    parser.add_argument(
        "--db", default=os.environ.get("SITECHECK_DB", "data/sitecheck.db"), help="SQLite file"
    )
    parser.add_argument(
        "--every",
        type=int,
        default=None,
        metavar="SECONDS",
        help=f"repeat forever with this interval (min {MIN_INTERVAL_SECONDS}); omit to run once",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    if args.every is not None and args.every < MIN_INTERVAL_SECONDS:
        log.error("--every must be at least %d seconds", MIN_INTERVAL_SECONDS)
        return 2

    store = Store(args.db)
    analyzer = default_analyzer(args.timeout)
    webhook_url = os.environ.get("SITECHECK_WEBHOOK_URL") or None
    if webhook_url is None:
        log.warning("SITECHECK_WEBHOOK_URL not set, alerts only go to the log")

    stop = threading.Event()
    # `docker stop` sends SIGTERM; finish the current site and exit cleanly
    # instead of waiting out the interval and getting SIGKILLed.
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    while True:
        try:
            hosts = load_watchlist(args.watchlist)
        except OSError as exc:
            log.error("cannot read watchlist %s: %s", args.watchlist, exc)
            return 2
        started = time.monotonic()
        log.info("checking %d sites", len(hosts))
        run_once(hosts, store, analyzer, webhook_url)
        log.info("run finished in %.1fs", time.monotonic() - started)

        if args.every is None:
            return 0
        if stop.wait(args.every):
            log.info("received stop signal, exiting")
            return 0


if __name__ == "__main__":
    sys.exit(main())
