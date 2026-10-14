"""Decides *what* is worth alerting on and sends it to a chat webhook.

The decision logic (`find_alerts`) is pure: it compares the new report with
the previous stored result and returns a list of Alert objects. Sending is a
separate step so the logic can be tested without any network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import httpx

from ..models import SiteReport
from ..scoring import GRADE_ORDER
from .store import StoredCheck

log = logging.getLogger(__name__)

CERT_EXPIRY_ALERT_DAYS = 14


class AlertKind(StrEnum):
    GRADE_DROP = "grade_drop"
    GRADE_RECOVERED = "grade_recovered"
    SITE_DOWN = "site_down"
    SITE_RECOVERED = "site_recovered"
    CERT_EXPIRING = "cert_expiring"
    CERT_INVALID = "cert_invalid"


@dataclass(frozen=True)
class Alert:
    host: str
    kind: AlertKind
    message: str


def find_alerts(report: SiteReport, previous: StoredCheck | None) -> list[Alert]:
    """Compare a fresh report with the last stored one.

    Alerts fire on *changes* (grade dropped, site went down) so a broken site
    doesn't spam the channel every run. Certificate expiry is the exception:
    it alerts every run while under the threshold, because it gets more urgent
    each day and someone needs to act.
    """
    alerts: list[Alert] = []
    host = report.host
    was_down = previous is not None and previous.fetch_error is not None

    if report.fetch_error:
        if not was_down:
            message = f"{host} unreachable: {report.fetch_error}"
            alerts.append(Alert(host, AlertKind.SITE_DOWN, message))
        return alerts

    if was_down:
        alerts.append(Alert(host, AlertKind.SITE_RECOVERED, f"{host} is reachable again"))

    if previous is not None and previous.grade and report.grade and not was_down:
        old, new = GRADE_ORDER.index(previous.grade), GRADE_ORDER.index(report.grade)
        if new < old:
            alerts.append(
                Alert(
                    host,
                    AlertKind.GRADE_DROP,
                    f"{host} dropped from {previous.grade} to {report.grade} "
                    f"(score {previous.score} -> {report.score})",
                )
            )
        elif new > old:
            alerts.append(
                Alert(
                    host,
                    AlertKind.GRADE_RECOVERED,
                    f"{host} improved from {previous.grade} to {report.grade}",
                )
            )

    tls = report.tls
    if tls is not None and not tls.valid:
        previous_tls_ok = previous is None or (previous.report.get("tls") or {}).get("valid", True)
        if previous_tls_ok:
            alerts.append(Alert(host, AlertKind.CERT_INVALID, f"{host} TLS problem: {tls.error}"))
    elif tls is not None and tls.days_to_expiry is not None:
        if tls.days_to_expiry < CERT_EXPIRY_ALERT_DAYS:
            alerts.append(
                Alert(
                    host,
                    AlertKind.CERT_EXPIRING,
                    f"{host} certificate expires in {tls.days_to_expiry} days",
                )
            )
    return alerts


def format_message(alerts: list[Alert]) -> str:
    icons = {
        AlertKind.GRADE_DROP: "🔻",
        AlertKind.GRADE_RECOVERED: "✅",
        AlertKind.SITE_DOWN: "🔴",
        AlertKind.SITE_RECOVERED: "✅",
        AlertKind.CERT_EXPIRING: "⏳",
        AlertKind.CERT_INVALID: "🔴",
    }
    lines = [f"{icons[a.kind]} {a.message}" for a in alerts]
    return "**sitecheck monitor**\n" + "\n".join(lines)


def send_webhook(
    url: str,
    alerts: list[Alert],
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """POST alerts to a Discord or Slack incoming webhook. Returns success.

    Discord expects {"content": ...}, Slack expects {"text": ...}; sending both
    keys works for either. Failures are logged, never raised: a broken webhook
    must not stop the monitor from recording results.
    """
    if not alerts:
        return True
    text = format_message(alerts)
    # Discord rejects messages over 2000 characters.
    if len(text) > 1900:
        text = text[:1900] + "\n…"
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.post(url, json={"content": text, "text": text})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        # The webhook URL contains a secret token, so don't log it.
        log.error("webhook delivery failed: %s", type(exc).__name__)
        return False
    return True
